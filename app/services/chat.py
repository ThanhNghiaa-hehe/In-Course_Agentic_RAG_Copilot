import asyncio
import json
import logging
import re
import uuid
from typing import AsyncGenerator, Dict, Any, List, Optional
from openai import AsyncOpenAI

from app.config import settings
from app.services.curriculum import get_curriculum_service, CurriculumService
from app.services.chat_graph import get_chat_graph, commit_assistant_turn, reset_session_state
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

CJK_REGEX = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3000-\u303f]')

def sanitize_cjk_tokens(text: str) -> str:
    """
    Bắt và loại trừ 100% token chữ Hán hoặc dấu câu CJK từ mô hình Qwen 2.5 Coder.
    """
    if not text:
        return text
    for zh, vi in CJK_REPLACEMENTS.items():
        if zh in text:
            text = text.replace(zh, vi)
    if CJK_REGEX.search(text):
        text = CJK_REGEX.sub('', text)
    return text


def sanitize_timestamp_tags(text: str, valid_secs: set) -> str:
    """
    Deterministic Timestamp Whitelist Guardrail (ERR-02):
    Loại bỏ triệt để các thẻ <timestamp sec="X"> không nằm trong danh mục Whitelist được bảo chứng.
    - Nếu valid_secs rỗng: Loại bỏ toàn bộ thẻ <timestamp>.
    - Nếu valid_secs có phần tử: Bắt buộc sec phải thuộc valid_secs.
    - Các mốc bịa đặt (như LLM tự tăng giây 218, 219, 220) sẽ bị gỡ bỏ thẻ, giữ lại text trơn.
    """
    if not text:
        return text
    if not valid_secs:
        return re.sub(r'<timestamp\b[^>]*>(.*?)</timestamp>', r'\1', text)

    def _tag_verifier(m: re.Match) -> str:
        full_tag = m.group(0)
        inner_content = m.group(1)
        sec_m = re.search(r'sec=["\'](\d+)["\']', full_tag)
        if sec_m:
            sec_val = int(sec_m.group(1))
            if sec_val in valid_secs:
                return full_tag
        return inner_content

    return re.sub(r'<timestamp\b[^>]*>(.*?)</timestamp>', _tag_verifier, text)


class StreamingTimestampSanitizer:
    """
    Bộ đệm luồng kiểm chuẩn thẻ Timestamp thời gian thực:
    - Bắt và đệm thẻ <timestamp ... </timestamp> trong luồng SSE.
    - Kiểm chứng thuộc tính sec="" đối chiếu với tập Whitelist valid_secs.
    - Nếu mốc thời gian không nằm trong Whitelist (LLM bịa đặt), lập tức gỡ bỏ thẻ và chỉ phát text trơn.
    """
    def __init__(self, valid_secs: set):
        self.valid_secs = valid_secs
        self.buffer = ""

    def process(self, token: str) -> List[str]:
        self.buffer += token
        out = []

        while self.buffer:
            if "<timestamp" in self.buffer:
                idx = self.buffer.find("<timestamp")
                if idx > 0:
                    out.append(self.buffer[:idx])
                    self.buffer = self.buffer[idx:]

                close_idx = self.buffer.find("</timestamp>")
                if close_idx != -1:
                    tag_end = close_idx + len("</timestamp>")
                    full_tag = self.buffer[:tag_end]
                    self.buffer = self.buffer[tag_end:]
                    sanitized = sanitize_timestamp_tags(full_tag, self.valid_secs)
                    if sanitized:
                        out.append(sanitized)
                else:
                    if len(self.buffer) > 150:
                        out.append(self.buffer)
                        self.buffer = ""
                    break
            elif "<" in self.buffer:
                last_lt = self.buffer.rfind("<")
                if last_lt > 0:
                    out.append(self.buffer[:last_lt])
                    self.buffer = self.buffer[last_lt:]
                if not "<timestamp".startswith(self.buffer):
                    out.append(self.buffer)
                    self.buffer = ""
                break
            else:
                out.append(self.buffer)
                self.buffer = ""
                break
        return out

    def flush(self) -> List[str]:
        if not self.buffer:
            return []
        res = sanitize_timestamp_tags(self.buffer, self.valid_secs)
        self.buffer = ""
        return [res] if res else []


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
        if self.curriculum_service.is_navigation_query(request.prompt):
            nav_response = self.curriculum_service.generate_navigation_response(
                prompt=request.prompt,
                current_lesson_seq=request.lesson_seq,
                course_id=request.course_id
            )
            if nav_response:
                match_res = self.curriculum_service.find_lesson_for_query(
                    request.prompt,
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

                commit_assistant_turn(session_id, request.prompt, nav_response)
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
            commit_assistant_turn(session_id, request.prompt, direct_text)

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

            # Lưu vết câu trả lời hoàn chỉnh của Trợ giảng vào LangGraph Checkpointer
            if full_assistant_response.strip():
                # Hàng rào bảo vệ lần 2: Đảm bảo 100% không lọt bất kỳ thẻ timestamp ảo giác nào vào DB
                full_assistant_response = sanitize_timestamp_tags(full_assistant_response, valid_secs)
                commit_assistant_turn(session_id, request.prompt, full_assistant_response)

        except Exception as e:
            logger.error(f"[ChatService] Lỗi kết nối LLM Server ({settings.LLM_BASE_URL}): {str(e)}")
            yield {
                "event": "delta",
                "data": json.dumps({
                    "content": f"\n\n*(Hệ thống đang gặp sự cố kết nối tới LLM Local ({settings.LLM_MODEL_NAME}). Bạn vui lòng kiểm tra xem Ollama đã chạy chưa: `ollama run {settings.LLM_MODEL_NAME}`)*"
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
