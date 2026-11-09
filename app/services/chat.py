import asyncio
import json
import logging
import uuid
from html.parser import HTMLParser
from typing import AsyncGenerator, Dict, Any, List, Optional, Tuple
from openai import AsyncOpenAI

from app.config import settings
from app.services.curriculum import get_curriculum_service, CurriculumService
from app.services.chat_graph import get_chat_graph, commit_assistant_turn, reset_session_state
from app.agent.router import get_intent_router
from app.agent.guardrails import get_session_rate_limiter
from app.schemas.chat import ChatRequest, SuggestedTimestamp, StreamMetadataEvent

logger = logging.getLogger("uvicorn.error")

# ==============================================================================
# TRI-LAYER ANTI-CJK TOKEN LEAKAGE GUARDRAIL (TẦNG 2 - BACKEND STREAMING)
# ==============================================================================
CJK_REPLACEMENTS = {
    "大约从": "khoảng từ ",
    "大约": "khoảng ",
    "从": "từ ",
    "到": " đến ",
    "浮点数": "số thực",
    "整数": "số nguyên",
    "常量": "hằng số",
    "变量": "biến",
    "指针": "con trỏ",
    "引用": "tham chiếu",
    "。": ". ",
    "（": " (",
    "）": ") ",
    "：": ": ",
    "、": ", "
}

def is_cjk_char(c: str) -> bool:
    """Kiểm tra ký tự thuộc khối CJK (Trung/Hàn/dấu câu CJK) dựa trên khoảng Unicode (Zero Regex)."""
    code = ord(c)
    return (
        (0x4E00 <= code <= 0x9FFF) or
        (0x3400 <= code <= 0x4DBF) or
        (0xF900 <= code <= 0xFAFF) or
        (0x3000 <= code <= 0x303F)
    )


def sanitize_cjk_tokens(text: str) -> str:
    """
    Bắt và loại trừ 100% token chữ Hán hoặc dấu câu CJK từ mô hình Qwen 2.5 Coder (Zero Regex).
    """
    if not text:
        return text
    for zh, vi in CJK_REPLACEMENTS.items():
        if zh in text:
            text = text.replace(zh, vi)
    if any(is_cjk_char(c) for c in text):
        text = "".join(c for c in text if not is_cjk_char(c))
    return text


class TimestampWhitelistHTMLParser(HTMLParser):
    """
    Bộ phân tích cú pháp HTML event-driven chuẩn W3C (Zero Regex) để lọc thẻ <timestamp>.
    Chỉ giữ lại thẻ có thuộc tính sec nằm trong Whitelist valid_secs.
    """
    def __init__(self, valid_secs: set):
        super().__init__()
        self.valid_secs = valid_secs
        self.result: List[str] = []
        self.in_timestamp = False
        self.is_valid = False
        self.tag_attrs: str = ""

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        if tag == "timestamp":
            self.in_timestamp = True
            attr_dict = dict(attrs)
            sec_str = attr_dict.get("sec", "")
            if sec_str and sec_str.isdigit() and int(sec_str) in self.valid_secs:
                self.is_valid = True
                attr_text = " ".join(f'{k}="{v}"' for k, v in attrs if v is not None)
                self.tag_attrs = f" {attr_text}" if attr_text else ""
            else:
                self.is_valid = False
                self.tag_attrs = ""
        else:
            attr_text = (" " + " ".join(f'{k}="{v}"' for k, v in attrs if v is not None)) if attrs else ""
            self.result.append(f"<{tag}{attr_text}>")

    def handle_endtag(self, tag: str):
        if tag == "timestamp":
            if self.is_valid:
                self.result.append("</timestamp>")
            self.in_timestamp = False
            self.is_valid = False
            self.tag_attrs = ""
        else:
            self.result.append(f"</{tag}>")

    def handle_data(self, data: str):
        if self.in_timestamp and self.is_valid and self.tag_attrs:
            self.result.append(f"<timestamp{self.tag_attrs}>")
            self.tag_attrs = ""
        self.result.append(data)


def sanitize_timestamp_tags(text: str, valid_secs: set) -> str:
    """
    Deterministic Timestamp Whitelist Guardrail (Zero Regex):
    Loại bỏ triệt để các thẻ <timestamp sec=\"X\"> không nằm trong danh mục Whitelist được bảo chứng.
    - Nếu valid_secs rỗng hoặc không có thẻ: Loại bỏ toàn bộ thẻ <timestamp>, giữ lại nội dung trơn.
    - Nếu valid_secs có phần tử: Bắt buộc sec phải thuộc valid_secs.
    """
    if not text or "<timestamp" not in text:
        return text

    parser = TimestampWhitelistHTMLParser(valid_secs)
    try:
        parser.feed(text)
        return "".join(parser.result)
    except Exception as e:
        logger.warning(f"[sanitize_timestamp_tags] Lỗi HTML parser: {e}. Trả về văn bản gốc.")
        return text


class StreamingTimestampSanitizer:
    """
    Máy trạng thái hữu hạn (FSM) 3 trạng thái kiểm chuẩn thẻ Timestamp thời gian thực trong luồng SSE:
    - Trạng thái EMIT: Phát trực tiếp các token văn bản thông thường. Khi gặp ký tự '<' có thể là thẻ mở, chuyển sang ACCUMULATE_TAG.
    - Trạng thái ACCUMULATE_TAG: Đệm toàn bộ thẻ mở <timestamp sec="X">. Bóc tách sec và đối chiếu Whitelist valid_secs.
    - Trạng thái STREAM_BODY: Thu thập nhãn hiển thị bên trong cho tới khi gặp </timestamp>.
      Nếu sec in valid_secs: giữ lại thẻ hoàn chỉnh <timestamp sec="X">label</timestamp>.
      Nếu sec not in valid_secs hoặc thẻ bị lỗi/cắt cụt: triệt tiêu thẻ, chỉ phát nhãn hiển thị.
    Hoàn toàn không dùng heuristic xả buffer len > 150.
    """
    STATE_EMIT = "EMIT"
    STATE_ACCUMULATE_TAG = "ACCUMULATE_TAG"
    STATE_STREAM_BODY = "STREAM_BODY"

    def __init__(self, valid_secs: set):
        self.valid_secs = valid_secs
        self.state = self.STATE_EMIT
        self.buffer = ""
        self.tag_open = ""
        self.is_valid_sec = False
        self.body_buffer = ""

    def process(self, token: str) -> List[str]:
        self.buffer += token
        out: List[str] = []

        while self.buffer:
            if self.state == self.STATE_EMIT:
                lt_idx = self.buffer.find("<")
                if lt_idx == -1:
                    out.append(self.buffer)
                    self.buffer = ""
                    break
                elif lt_idx > 0:
                    out.append(self.buffer[:lt_idx])
                    self.buffer = self.buffer[lt_idx:]

                # Buffer bắt đầu bằng '<'
                if "<timestamp".startswith(self.buffer):
                    # Đang khớp một phần của '<timestamp', chờ thêm token
                    break
                elif self.buffer.startswith("<timestamp"):
                    self.state = self.STATE_ACCUMULATE_TAG
                else:
                    # Ký tự '<' thông thường không phải thẻ timestamp (ví dụ i < n hoặc template <T>)
                    out.append(self.buffer[0])
                    self.buffer = self.buffer[1:]

            elif self.state == self.STATE_ACCUMULATE_TAG:
                gt_idx = self.buffer.find(">")
                if gt_idx == -1:
                    # Chưa đóng thẻ mở, chờ thêm token
                    break

                full_open_tag = self.buffer[:gt_idx + 1]
                self.buffer = self.buffer[gt_idx + 1:]

                # Bóc tách thuộc tính sec không dùng regex
                sec_val = None
                sec_idx = full_open_tag.find("sec=")
                if sec_idx != -1:
                    val_part = full_open_tag[sec_idx + 4:].lstrip(" \"'")
                    digits = []
                    for c in val_part:
                        if c.isdigit():
                            digits.append(c)
                        else:
                            break
                    if digits:
                        sec_val = int("".join(digits))

                if sec_val is not None:
                    self.is_valid_sec = (sec_val in self.valid_secs)
                    self.tag_open = full_open_tag
                else:
                    self.is_valid_sec = False
                    self.tag_open = ""

                self.body_buffer = ""
                self.state = self.STATE_STREAM_BODY

            elif self.state == self.STATE_STREAM_BODY:
                close_tag = "</timestamp>"
                close_idx = self.buffer.find(close_tag)
                if close_idx != -1:
                    body = self.body_buffer + self.buffer[:close_idx]
                    self.buffer = self.buffer[close_idx + len(close_tag):]

                    if self.is_valid_sec:
                        out.append(f"{self.tag_open}{body}{close_tag}")
                    else:
                        out.append(body)

                    # Reset trạng thái về EMIT
                    self.tag_open = ""
                    self.body_buffer = ""
                    self.is_valid_sec = False
                    self.state = self.STATE_EMIT
                else:
                    # Tìm tiền tố dài nhất của </timestamp> ở cuối buffer để tránh bị cắt vụn
                    matched_prefix_len = 0
                    for p_len in range(min(len(self.buffer), len(close_tag) - 1), 0, -1):
                        if close_tag.startswith(self.buffer[-p_len:]):
                            matched_prefix_len = p_len
                            break

                    if matched_prefix_len > 0:
                        safe_chunk = self.buffer[:-matched_prefix_len]
                        self.body_buffer += safe_chunk
                        self.buffer = self.buffer[-matched_prefix_len:]
                    else:
                        self.body_buffer += self.buffer
                        self.buffer = ""
                    break

        return out

    def flush(self) -> List[str]:
        out: List[str] = []
        if self.state == self.STATE_STREAM_BODY:
            # Thẻ bị cắt cụt trước khi có </timestamp>: triệt tiêu thẻ mở, chỉ phát nhãn hiển thị
            body = self.body_buffer + self.buffer
            if body:
                out.append(body)
        elif self.state == self.STATE_ACCUMULATE_TAG:
            # Thẻ mở bị cắt cụt: triệt tiêu hoàn toàn thẻ mở lỗi
            pass
        elif self.state == self.STATE_EMIT:
            if self.buffer:
                out.append(self.buffer)

        self.buffer = ""
        self.body_buffer = ""
        self.tag_open = ""
        self.is_valid_sec = False
        self.state = self.STATE_EMIT
        return out


class ChatService:
    """
    Dịch vụ điều phối trò chuyện Socratic & Truyền phát dữ liệu thời gian thực (SSE Stream):
    - Tích hợp Curriculum Navigation Dispatcher: Fast-Path (< 20ms) cho câu hỏi lộ trình/playlist.
    - Tích hợp Intent Router: Fast-Path (< 1ms) cho chào hỏi / out-of-scope.
    - Tích hợp Advanced Hybrid Retrieval & CRAG Grader qua LangGraph StateGraph.
    - Chuẩn hóa ngữ cảnh U-shaped & trích xuất mốc <timestamp sec="xxx">mm:ss</timestamp>.
    - Kết nối OpenAI-compatible Client (hỗ trợ cả Ollama Local và vLLM Remote).
    """

    def __init__(
        self,
        retrieval_service: Optional[Any] = None,
        openai_client: Optional[AsyncOpenAI] = None
    ):
        self.curriculum_service = get_curriculum_service()
        self.router = get_intent_router()
        self.client = openai_client or AsyncOpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.OPENAI_API_KEY or "vllm",
            default_headers={"ngrok-skip-browser-warning": "true"}
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Xử lý yêu cầu trò chuyện và phát luồng sự kiện SSE (Dual-Channel Server-Sent Events):
        - Hỗ trợ phiên đa lượt (Multi-turn Stateful Session) qua LangGraph Checkpointer theo thread_id.
        - Event 'metadata': Gửi session_id, turn_count, danh sách nguồn trích dẫn, mốc timestamp đề xuất.
        - Event 'delta': Bắn từng token văn bản được sinh ra từ LLM.
        - Event 'done': Báo hiệu hoàn tất luồng truyền phát và tự động lưu vết turn đối thoại.
        """
        # 1. Quản lý Session ID chuẩn hóa (Tạo mới nếu client chưa có)
        session_id = request.session_id or f"session_{uuid.uuid4().hex[:12]}"
        config = {"configurable": {"thread_id": session_id}}

        # -1. Kiểm tra Rate Limiting (Chống spam dồn dập per session)
        rate_limiter = get_session_rate_limiter()
        is_allowed, rate_msg, retry_after = rate_limiter.check_rate_limit(session_id)
        if not is_allowed:
            metadata_event = StreamMetadataEvent(
                session_id=session_id,
                turn_count=1,
                intent="rate_limited",
                used_fast_path=True,
                retrieved_chunk_count=0,
                is_approximate=False,
                retrieval_status="fast_path",
                is_low_confidence=False,
                target_lesson_seq=None,
                suggested_timestamps=[],
                sources=[]
            )
            yield {
                "event": "metadata",
                "data": metadata_event.model_dump_json()
            }
            words = (rate_msg or "Vui lòng gửi câu hỏi chậm lại để có thời gian thực hành nhé.").split(" ")
            for i, word in enumerate(words):
                chunk_token = word if i == 0 else " " + word
                yield {
                    "event": "delta",
                    "data": json.dumps({"content": chunk_token})
                }
                await asyncio.sleep(0.012)
            yield {
                "event": "done",
                "data": "[DONE]"
            }
            return

        # 0. Fast-Path Curriculum Navigation Intent Dispatcher (< 20ms)
        # Bắt các câu hỏi hỏi về bài học trong playlist ("học vòng lặp thì chọn bài nào...")
        # Bất biến phân cấp: Chỉ kích hoạt điều hướng giáo trình khi Router xác nhận là câu hỏi học tập (is_course_query == True)
        quick_clf = self.router.classify(request.prompt)
        if quick_clf.is_course_query and self.curriculum_service.is_navigation_query(request.prompt):
            # Invariant 3 (Stateful Navigation & History-Aware Dispatcher):
            # Kiểm tra xem câu hỏi có chứa đại từ chỉ định lịch sử ("câu hỏi trên", "vừa rồi", "nội dung đó")
            lookup_prompt = request.prompt
            history_prefix = ""

            try:
                graph = get_chat_graph()
                state_snapshot = graph.get_state({"configurable": {"thread_id": session_id}})
                current_values = state_snapshot.values if state_snapshot else {}
                history_msgs = current_values.get("messages", [])
                last_user_query = ""
                if history_msgs:
                    last_user_query = next((m["content"] for m in reversed(history_msgs) if m.get("role") == "user"), "")

                norm_p = request.prompt.lower()
                is_anaphora = any(ref in norm_p for ref in ("trên", "vừa rồi", "vừa hỏi", "đó", "nội dung đó"))
                if is_anaphora and last_user_query:
                    lookup_prompt = last_user_query
                    history_prefix = f"Về câu hỏi *\"{last_user_query}\"* của bạn:\n\n"
                    logger.info(f"[ChatService:Navigation] Phát hiện câu hỏi quy chiếu lịch sử -> Lookup theo last_user_query: '{last_user_query[:40]}...'")
            except Exception as e:
                logger.debug(f"[ChatService:Navigation] Lỗi đọc state checkpointer: {e}")

            nav_response = self.curriculum_service.generate_navigation_response(
                prompt=lookup_prompt,
                current_lesson_seq=request.lesson_seq,
                course_id=request.course_id
            )
            if nav_response:
                if history_prefix:
                    nav_response = history_prefix + nav_response
                match_res = self.curriculum_service.find_lesson_for_query(
                    lookup_prompt,
                    current_lesson_seq=request.lesson_seq,
                    preferred_course_id=request.course_id
                )
                target_seq = match_res[0].get("seq") if match_res else None

                suggested_ts = []
                if target_seq is not None:
                    raw_ts = self.curriculum_service.get_lesson_timestamps(target_seq)
                    for item in raw_ts:
                        suggested_ts.append(
                            SuggestedTimestamp(
                                sec=item["sec"],
                                label=item["label"],
                                title=item["title"],
                                lesson_seq=target_seq
                            )
                        )

                metadata_event = StreamMetadataEvent(
                    session_id=session_id,
                    turn_count=1,
                    intent="course_query",
                    used_fast_path=True,
                    retrieved_chunk_count=0,
                    is_approximate=False,
                    retrieval_status="fast_path",
                    is_low_confidence=False,
                    target_lesson_seq=target_seq,
                    suggested_timestamps=suggested_ts,
                    sources=[]
                )
                yield {
                    "event": "metadata",
                    "data": metadata_event.model_dump_json()
                }

                # Truyền phát từng token phản hồi định hướng bài học
                words = nav_response.split(" ")
                for i, word in enumerate(words):
                    chunk_token = word if i == 0 else " " + word
                    yield {
                        "event": "delta",
                        "data": json.dumps({"content": chunk_token})
                    }
                    await asyncio.sleep(0.012)

                commit_assistant_turn(session_id, request.prompt, nav_response, current_lesson_seq=request.lesson_seq)
                yield {
                    "event": "done",
                    "data": "[DONE]"
                }
                return

        initial_state = {
            "session_id": session_id,
            "prompt": request.prompt,
            "course_id": request.course_id,
            "lesson_seq": request.lesson_seq,
            "intent": "course_query",
            "direct_response": None,
            "is_course_query": True,
            "retrieval_status": "coverage_gap",
            "retrieved_chunks": [],
            "is_approximate": False,
            "is_low_confidence": False,
            "target_lesson_seq": None,
            "suggested_timestamps": [],
            "sources": [],
            "system_prompt": "",
            "user_message_content": "",
            "assembled_messages": []
        }


        # Khởi chạy chu trình điều phối Agentic RAG qua LangGraph StateGraph có Checkpointer
        graph = get_chat_graph()
        final_state = await graph.ainvoke(initial_state, config=config)
        turn_count = final_state.get("turn_count", 1)
        logger.info(
            f"[ChatService:LangGraph] Graph hoàn tất: Session={session_id} | Turn={turn_count} | "
            f"Intent={final_state['intent']} | Status={final_state['retrieval_status']} | "
            f"Chunks={len(final_state['retrieved_chunks'])}"
        )

        # 2. Xử lý Fast-Path (Chào hỏi xã giao, cảm ơn, danh tính, ngoài lề, hoặc xác nhận điều hướng đàm thoại)
        if not final_state["is_course_query"]:
            act = final_state.get("action")
            target_seq = final_state.get("target_lesson_seq")
            auto_seek = None
            if act and act.get("type") == "navigate_and_seek":
                target_seq = act.get("target_lesson_seq")
                auto_seek = act.get("sec")

            fast_metadata = StreamMetadataEvent(
                session_id=session_id,
                turn_count=turn_count,
                intent=final_state["intent"],
                used_fast_path=True,
                retrieved_chunk_count=0,
                is_approximate=False,
                retrieval_status="fast_path",
                is_low_confidence=False,
                target_lesson_seq=target_seq,
                auto_seek_sec=auto_seek,
                action=act,
                suggested_timestamps=[],
                sources=[]
            )
            yield {
                "event": "metadata",
                "data": fast_metadata.model_dump_json()
            }

            direct_text = final_state["direct_response"] or ""
            words = direct_text.split(" ")
            for i, word in enumerate(words):
                chunk_token = word if i == 0 else " " + word
                yield {
                    "event": "delta",
                    "data": json.dumps({"content": chunk_token})
                }
                await asyncio.sleep(0.015)

            # Lưu vết lượt Fast-Path vào Checkpointer
            commit_assistant_turn(
                session_id,
                request.prompt,
                direct_text,
                current_lesson_seq=request.lesson_seq,
                last_course_query=final_state.get("last_course_query")
            )

            yield {
                "event": "done",
                "data": "[DONE]"
            }
            return

        # 3. Gửi sự kiện 'metadata' đầu tiên cho Frontend UI từ kết quả đồ thị
        # [Zero Auto-Seek Invariant - Phương Án A]:
        # Tuyệt đối CẤM cơ chế tự ý giật màn hình hoặc ép video tự tua ở client.
        # auto_seek_sec được cố định là None; 100% việc tua video do học viên chủ động bấm nút.
        suggested_ts = [
            SuggestedTimestamp(**ts) for ts in final_state.get("suggested_timestamps", [])
        ]
        auto_seek_sec = None

        meta_event = StreamMetadataEvent(
            session_id=session_id,
            turn_count=turn_count,
            intent=final_state["intent"],
            used_fast_path=False,
            retrieved_chunk_count=len(final_state["retrieved_chunks"]),
            is_approximate=final_state["is_approximate"],
            retrieval_status=final_state["retrieval_status"],
            is_low_confidence=final_state["is_low_confidence"],
            target_lesson_seq=final_state["target_lesson_seq"],
            auto_seek_sec=auto_seek_sec,
            suggested_timestamps=suggested_ts,
            sources=final_state.get("sources", [])
        )
        yield {
            "event": "metadata",
            "data": meta_event.model_dump_json()
        }

        # Sử dụng danh sách tin nhắn ChatML đa lượt do Node context_assembly đóng gói
        messages = final_state.get("assembled_messages")
        if not messages:
            messages = [
                {"role": "system", "content": final_state["system_prompt"]},
                {"role": "user", "content": final_state["user_message_content"]}
            ]

        full_assistant_response = ""

        try:
            stream_response = await self.client.chat.completions.create(
                model=settings.LLM_MODEL_NAME,
                messages=messages,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                presence_penalty=0.5,
                frequency_penalty=0.5,
                stop=["\n\n\n", "Học viên:", "Sinh viên:", "<|im_end|>"],
                stream=True,
                timeout=8.0
            )

            retrieval_status = final_state.get("retrieval_status", "coverage_gap")
            retrieved_chunks = final_state.get("retrieved_chunks", [])

            # Tập hợp Whitelist các mốc giây được bảo chứng (ERR-02)
            valid_secs = set()
            for item in final_state.get("suggested_timestamps", []):
                if isinstance(item, dict) and item.get("sec") is not None:
                    valid_secs.add(int(item["sec"]))

            ts_sanitizer = StreamingTimestampSanitizer(valid_secs=valid_secs)

            async for chunk in stream_response:
                if chunk.choices and chunk.choices[0].delta.content:
                    raw_token = chunk.choices[0].delta.content

                    # Tri-Layer Anti-CJK Token Leakage Guardrail (Tầng 2 - Backend Streaming Sanitizer)
                    clean_token = sanitize_cjk_tokens(raw_token)
                    if not clean_token:
                        continue

                    # Deterministic Timestamp Whitelist Guardrail (Streaming Buffer)
                    sanitized_tokens = ts_sanitizer.process(clean_token)
                    for tok in sanitized_tokens:
                        full_assistant_response += tok
                        yield {
                            "event": "delta",
                            "data": json.dumps({"content": tok})
                        }

            # Xả các token còn lại trong bộ đệm cuối luồng
            final_flushed = ts_sanitizer.flush()
            for tok in final_flushed:
                full_assistant_response += tok
                yield {
                    "event": "delta",
                    "data": json.dumps({"content": tok})
                }

            # Deterministic Timestamp Fallback: Nếu có mốc bảo chứng nhưng LLM quên sinh thẻ, tự động gắn mốc video
            if valid_secs and "<timestamp" not in full_assistant_response and suggested_ts:
                ts_items = [f'<timestamp sec="{ts.sec}">{ts.label}</timestamp>' for ts in suggested_ts[:2]]
                ts_footer = f"\n\n📍 **Mốc video bài giảng:** {' | '.join(ts_items)}"
                full_assistant_response += ts_footer
                yield {
                    "event": "delta",
                    "data": json.dumps({"content": ts_footer})
                }

            # Lưu vết câu trả lời hoàn chỉnh của Trợ giảng vào LangGraph Checkpointer
            if full_assistant_response.strip():
                # Hàng rào bảo vệ lần 2: Đảm bảo 100% không lọt bất kỳ thẻ timestamp ảo giác nào vào DB
                full_assistant_response = sanitize_timestamp_tags(full_assistant_response, valid_secs)
                commit_assistant_turn(
                    session_id,
                    request.prompt,
                    full_assistant_response,
                    current_lesson_seq=request.lesson_seq,
                    last_course_query=final_state.get("last_course_query")
                )

        except Exception as e:
            logger.error(f"[ChatService] Lỗi kết nối LLM Server ({settings.LLM_BASE_URL}): {str(e)}")
            fallback_msg = f"\n\n*(Hệ thống đang gặp sự cố kết nối tới LLM Local ({settings.LLM_MODEL_NAME}). Bạn vui lòng kiểm tra xem Ollama đã chạy chưa: `ollama run {settings.LLM_MODEL_NAME}`)*"
            commit_assistant_turn(
                session_id,
                request.prompt,
                fallback_msg,
                current_lesson_seq=request.lesson_seq,
                last_course_query=final_state.get("last_course_query")
            )
            yield {
                "event": "delta",
                "data": json.dumps({
                    "content": fallback_msg
                })
            }

        yield {
            "event": "done",
            "data": "[DONE]"
        }


# Singleton ChatService instance
_chat_service: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service
