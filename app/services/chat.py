import asyncio
import json
import logging
import re
import uuid
from typing import AsyncGenerator, Dict, Any, List, Optional
from openai import AsyncOpenAI

from app.config import settings
from app.agent.prompts import (
    SOCRATIC_GROUNDED_PROMPT,
    OUT_OF_LESSON_PROMPT,
    COVERAGE_GAP_PROMPT,
    SOCRATIC_SYSTEM_PROMPT,
)
from app.agent.router import get_intent_router
from app.services.retrieval import RetrievalService, RetrievalResult, get_retrieval_service
from app.services.chat_graph import get_chat_graph, commit_assistant_turn, reset_session_state
from app.schemas.chat import ChatRequest, SuggestedTimestamp, StreamMetadataEvent

logger = logging.getLogger("uvicorn.error")


class ChatService:
    """
    Dịch vụ điều phối trò chuyện Socratic & Truyền phát dữ liệu thời gian thực (SSE Stream):
    - Tích hợp Intent Router: Fast-Path (< 1ms) cho chào hỏi / out-of-scope.
    - Tích hợp Advanced Hybrid Retrieval (Qdrant + Jina Reranker v2 + Graceful Degradation).
    - Phân định 3 trạng thái sư phạm cô lập: Grounded, Out-of-Lesson (bài tương lai), Coverage-Gap.
    - Chuẩn hóa ngữ cảnh U-shaped & trích xuất mốc <timestamp sec="xxx">mm:ss</timestamp>.
    - Kết nối OpenAI-compatible Client (hỗ trợ cả Ollama Local và OpenAI Cloud).
    """

    def __init__(
        self,
        retrieval_service: Optional[RetrievalService] = None,
        openai_client: Optional[AsyncOpenAI] = None
    ):
        self.retrieval_service = retrieval_service or get_retrieval_service()
        self.router = get_intent_router()
        self.client = openai_client or AsyncOpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.OPENAI_API_KEY or "vllm",
            default_headers={"ngrok-skip-browser-warning": "true"}
        )

    def _format_context_block(self, chunks: List[Dict[str, Any]]) -> str:
        """
        Định dạng các chunks ngữ cảnh thành khối văn bản có cấu trúc rõ ràng cho LLM.
        """
        if not chunks:
            return "[LƯU Ý: Không tìm thấy tài liệu bài giảng nào vượt qua ngưỡng tin cậy cho câu hỏi này. Hãy hướng dẫn học viên dựa trên kiến thức chuẩn của C++]."

        blocks = ["[NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC]"]
        for idx, chunk in enumerate(chunks, 1):
            c_type = chunk.get("content_type", "unknown")
            lesson_id = chunk.get("lesson_id", "unknown")
            lesson_seq = chunk.get("lesson_seq", "?")
            conf_pct = chunk.get("confidence_pct", 0.0)
            is_approx = chunk.get("is_approximate", False)

            header = f"--- Tài liệu {idx} (Loại: {c_type} | Bài: {lesson_id} (Seq: {lesson_seq}) | Độ tin cậy: {conf_pct:.1f}%"
            if is_approx:
                header += " [Mốc tham khảo gần nhất]"
            header += ") ---"

            blocks.append(header)

            if c_type == "code_ast":
                file_p = chunk.get("file_path", "")
                scope = chunk.get("code_scope", "")
                code_content = chunk.get("context_code") or chunk.get("raw_text", "")
                blocks.append(f"Mã nguồn ({file_p} - Phạm vi: {scope}):\n```cpp\n{code_content}\n```")
            else:
                tag = chunk.get("timestamp_tag", "")
                sec = chunk.get("start_sec")
                label = chunk.get("start_label", "")
                raw_t = chunk.get("raw_text", "")
                blocks.append(f"Video Timestamp: {tag} (Bắt đầu tại {label} - {sec}s)\nNội dung giảng viên: {raw_t}")

        return "\n".join(blocks)

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

        # 2. Xử lý Fast-Path (Chào hỏi xã giao, cảm ơn, danh tính, ngoài lề)
        if not final_state["is_course_query"]:
            fast_metadata = StreamMetadataEvent(
                session_id=session_id,
                turn_count=turn_count,
                intent=final_state["intent"],
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
            suggested_timestamps=[
                SuggestedTimestamp(**ts) for ts in final_state.get("suggested_timestamps", [])
            ],
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
                stream=True
            )

            retrieval_status = final_state.get("retrieval_status", "coverage_gap")
            retrieved_chunks = final_state.get("retrieved_chunks", [])

            async for chunk in stream_response:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content

                    # Deterministic Decoding Guardrail: Chặn sinh thẻ timestamp nếu không phải grounded hoặc không có chunks
                    if (retrieval_status != "grounded" or not retrieved_chunks) and ("<timestamp" in token or "</timestamp>" in token):
                        continue

                    full_assistant_response += token
                    yield {
                        "event": "delta",
                        "data": json.dumps({"content": token})
                    }

            # Lưu vết câu trả lời hoàn chỉnh của Trợ giảng vào LangGraph Checkpointer
            if full_assistant_response.strip():
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
