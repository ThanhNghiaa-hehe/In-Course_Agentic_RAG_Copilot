import asyncio
import json
import logging
import re
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
            api_key=settings.OPENAI_API_KEY or "ollama"
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
        - Event 'metadata': Gửi danh sách nguồn trích dẫn, mốc timestamp đề xuất, cờ fast-path, trạng thái retrieval.
        - Event 'delta': Bắn từng token văn bản được sinh ra từ LLM.
        - Event 'done': Báo hiệu hoàn tất luồng truyền phát.
        """
        # 1. Phân loại ý định qua Intent Classifier Router
        classification = self.router.classify(request.prompt)
        logger.info(f"[ChatService] Prompt: '{request.prompt[:40]}...' -> Intent: {classification.intent}")

        # 2. Xử lý Fast-Path (Chào hỏi xã giao, cảm ơn, danh tính)
        if not classification.is_course_query:
            fast_metadata = StreamMetadataEvent(
                intent=classification.intent,
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

            direct_text = classification.direct_response or ""
            # Stream mượt mà từng từ cho trải nghiệm phản hồi tự nhiên
            words = direct_text.split(" ")
            for i, word in enumerate(words):
                chunk_token = word if i == 0 else " " + word
                yield {
                    "event": "delta",
                    "data": json.dumps({"content": chunk_token})
                }
                await asyncio.sleep(0.015)

            yield {
                "event": "done",
                "data": "[DONE]"
            }
            return

        # 3. Xử lý Course Query: Truy xuất ngữ cảnh Đa phương thức (Stage 6 -> 9)
        try:
            retrieval_result = await self.retrieval_service.search(
                query_text=request.prompt,
                course_id=request.course_id,
                current_lesson_seq=request.lesson_seq,
                top_candidates=settings.DEFAULT_TOP_CANDIDATES,
                final_top_k=settings.DEFAULT_FINAL_TOP_K
            )
        except Exception as e:
            logger.error(f"[ChatService] Lỗi khi truy xuất Qdrant/RAG: {str(e)}")
            retrieval_result = RetrievalResult(chunks=[], status="coverage_gap")

        retrieved_chunks = retrieval_result.chunks
        retrieval_status = retrieval_result.status
        is_low_confidence = retrieval_result.is_low_confidence
        target_lesson_seq = retrieval_result.target_lesson_seq

        # 4. Trích xuất Timestamp gợi ý và Nguồn tài liệu cho Frontend UI
        suggested_timestamps: List[SuggestedTimestamp] = []
        sources: List[Dict[str, Any]] = []
        has_approximate = False

        if retrieval_status == "grounded":
            for chunk in retrieved_chunks:
                if chunk.get("is_approximate"):
                    has_approximate = True

                if chunk.get("content_type") == "video_transcript" and chunk.get("start_sec") is not None:
                    suggested_timestamps.append(
                        SuggestedTimestamp(
                            sec=chunk["start_sec"],
                            label=chunk.get("start_label", f"{chunk['start_sec']//60:02d}:{chunk['start_sec']%60:02d}"),
                            title=chunk.get("video_title", "Đoạn video bài giảng liên quan")
                        )
                    )

                sources.append({
                    "id": chunk.get("id"),
                    "content_type": chunk.get("content_type"),
                    "confidence_pct": chunk.get("confidence_pct", 0.0),
                    "confidence_score": chunk.get("confidence_score", 0.0),
                    "is_approximate": chunk.get("is_approximate", False),
                    "lesson_id": chunk.get("lesson_id"),
                    "lesson_seq": chunk.get("lesson_seq"),
                    "start_sec": chunk.get("start_sec"),
                    "start_label": chunk.get("start_label"),
                    "timestamp_tag": chunk.get("timestamp_tag"),
                    "file_path": chunk.get("file_path"),
                    "code_scope": chunk.get("code_scope"),
                    "context_code": chunk.get("context_code"),
                })

        # 5. Gửi sự kiện 'metadata' đầu tiên cho Frontend
        meta_event = StreamMetadataEvent(
            intent="course_query",
            used_fast_path=False,
            retrieved_chunk_count=len(retrieved_chunks),
            is_approximate=has_approximate,
            retrieval_status=retrieval_status,
            is_low_confidence=is_low_confidence,
            target_lesson_seq=target_lesson_seq,
            suggested_timestamps=suggested_timestamps,
            sources=sources
        )
        yield {
            "event": "metadata",
            "data": meta_event.model_dump_json()
        }

        # 6. Đóng gói Prompt chuyên biệt cho từng nhánh sư phạm
        if retrieval_status == "grounded":
            active_system_prompt = SOCRATIC_GROUNDED_PROMPT
            context_block = self._format_context_block(retrieved_chunks)
            caution_notice = "\n[LƯU Ý: Một số tài liệu có độ tin cậy tham khảo, hãy định hướng học viên thận trọng.]\n" if is_low_confidence else ""
            user_message_content = f"""[CÂU HỎI THẮC MẮC CỦA HỌC VIÊN]
{request.prompt}
{caution_notice}
{context_block}

HƯỚNG DẪN BẮT BUỘC:
- Hãy giải thích bản chất vấn đề và đặt câu hỏi gợi mở theo phương pháp Socratic.
- TUYỆT ĐỐI KHÔNG viết code giải hoàn chỉnh hộ học viên.
- Trích dẫn mốc thời gian từ tài liệu video trong phần ngữ cảnh trên dưới dạng thẻ bắt buộc:
  <timestamp sec="xxx">mm:ss</timestamp>
  để học viên có thể click tua nhanh video."""

        elif retrieval_status == "out_of_lesson":
            active_system_prompt = OUT_OF_LESSON_PROMPT
            target_desc = f"Bài {target_lesson_seq}" if target_lesson_seq else "các bài học sau"
            user_message_content = f"""[CÂU HỎI CỦA HỌC VIÊN]
{request.prompt}

[THÔNG TIN TIẾN ĐỘ BÀI HỌC]
- Khóa học: {request.course_id}
- Bài học hiện tại của học viên: Bài {request.lesson_seq}
- Bài học giảng dạy nội dung này: {target_desc}

HƯỚNG DẪN TRẢ LỜI:
1. Nhẹ nhàng thông báo cho học viên biết chủ đề này sẽ được học ở {target_desc}, hiện tại ở Bài {request.lesson_seq} bạn hãy nắm chắc kiến thức nền tảng trước nhé.
2. Nêu ngắn gọn 1-2 câu trực quan về khái niệm này.
3. Đặt 1 câu hỏi gợi mở Socratic liên hệ lại bài học hiện tại.
4. TUYỆT ĐỐI CẤM sinh bất kỳ thẻ <timestamp> nào."""

        else:  # coverage_gap
            active_system_prompt = COVERAGE_GAP_PROMPT
            user_message_content = f"""[CÂU HỎI CỦA HỌC VIÊN]
{request.prompt}

[THÔNG TIN PHẠM VI KHÓA HỌC]
- Khóa học: Lập trình C++ ({request.course_id}), đang ở Bài {request.lesson_seq}.
- Câu hỏi của học viên không nằm trong giáo trình bài giảng hoặc là chủ đề ngoài lề.

HƯỚNG DẪN TRẢ LỜI:
- Nếu là câu hỏi ngoài lề đời sống (ăn uống, thời tiết, giải trí,...): Phản hồi thân thiện, hài hước và nhắc học viên quay lại hỏi về bài học C++.
- Nếu là câu hỏi công nghệ/ngôn ngữ khác: Nêu ngắn gọn 1 câu khách quan và mời học viên đặt các câu hỏi liên quan đến C++.
- TUYỆT ĐỐI CẤM sinh bất kỳ thẻ <timestamp> nào."""

        messages = [
            {"role": "system", "content": active_system_prompt},
            {"role": "user", "content": user_message_content}
        ]

        try:
            stream_response = await self.client.chat.completions.create(
                model=settings.LLM_MODEL_NAME,
                messages=messages,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                presence_penalty=0.5,
                frequency_penalty=0.4,
                stop=["\n\n\n", "Học viên:", "Sinh viên:", "<|im_end|>", "User:"],
                stream=True
            )

            generated_full_text = ""
            seen_sentences = set()
            should_break_stream = False

            async for chunk in stream_response:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content

                    # Deterministic Guardrail: Chặn sinh thẻ timestamp nếu không phải grounded hoặc không có chunks
                    if (retrieval_status != "grounded" or not retrieved_chunks) and ("<timestamp" in token or "</timestamp>" in token):
                        continue

                    # Streaming Loop Breaker (Chống suy thoái lặp câu vô tận - Holtzman et al. 2019)
                    generated_full_text += token
                    if any(p in token for p in [".", "?", "!", "\n"]):
                        sentences = re.split(r"[.?!]\s+|\n+", generated_full_text)
                        for s in sentences[:-1]:
                            clean_s = s.strip()
                            if len(clean_s) >= 20:
                                if clean_s in seen_sentences:
                                    logger.warning(
                                        f"[ChatService] Phát hiện chu kỳ lặp suy thoái: '{clean_s[:30]}...', ngắt stream an toàn."
                                    )
                                    should_break_stream = True
                                    break
                                seen_sentences.add(clean_s)

                    if should_break_stream:
                        break

                    yield {
                        "event": "delta",
                        "data": json.dumps({"content": token})
                    }

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
