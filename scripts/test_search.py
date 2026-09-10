import sys
import asyncio
import textwrap
from typing import Optional
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.services.retrieval import get_retrieval_service
from app.services.qdrant import close_async_qdrant_client


async def run_search_probe(
    query_text: str,
    current_lesson_seq: int = 2,
    course_id: str = "cpp-core",
    top_candidates: int = 10,
    final_top_k: int = 3,
    min_score_threshold: Optional[float] = None
):
    print("=" * 72)
    print(f"🔍 CÂU HỎI HỌC VIÊN: '{query_text}'")
    print(f"Target Collection: {settings.QDRANT_COLLECTION_NAME}")
    print(f"Khóa học: {course_id} | Cửa sổ bài học: lesson_seq <= {current_lesson_seq}")
    print(f"Reranker Model: {settings.RERANKER_MODEL_NAME} (FlashAttention / Native ONNX)")
    if min_score_threshold is not None:
        print(f"Ngưỡng lọc Sigmoid tùy chỉnh: >= {min_score_threshold:.2f}")
    else:
        print(
            f"Ngưỡng lọc Phân tầng (Modality-Aware): Code >= {settings.CODE_SCORE_THRESHOLD:.2f} | "
            f"Video >= {settings.VIDEO_SCORE_THRESHOLD:.2f} (Fallback >= {settings.VIDEO_FALLBACK_MIN_THRESHOLD:.2f})"
        )
    print("=" * 72)

    retrieval_service = get_retrieval_service()
    try:
        final_assembled = await retrieval_service.search(
            query_text=query_text,
            course_id=course_id,
            current_lesson_seq=current_lesson_seq,
            top_candidates=top_candidates,
            final_top_k=final_top_k,
            min_score_threshold=min_score_threshold
        )

        print("\n" + "=" * 72, flush=True)
        print(f"KET QUA TRUY XUAT DA PHUONG THUC ({len(final_assembled)} CHUNKS TIEM VAO PROMPT):", flush=True)
        print("=" * 72, flush=True)

        if not final_assembled:
            print("\n🛡️ [GUARDRAILS KÍCH HOẠT THÀNH CÔNG] Không có chunk nào vượt qua ngưỡng tin cậy!")
            print("-> Câu hỏi bị đánh giá là LẠC ĐỀ (Out-of-Domain) hoặc không liên quan đến bài học.")
            print("-> Hệ thống chặn sinh ảo giác, từ chối trả về ngữ cảnh sai lệch.\n")
            return

        for rank, item in enumerate(final_assembled, 1):
            c_type = item.get("content_type", "video_transcript")
            conf_pct = item.get("confidence_pct", 0.0)
            rrf_score = item.get("rrf_score", 0.0)

            if c_type == "code_ast":
                file_p = item.get('file_path', 'unknown.cpp')
                scope = item.get('code_scope', 'unknown')
                s_line = item.get('start_line', 0)
                e_line = item.get('end_line', 0)
                ctx_code = textwrap.indent((item.get('context_code') or item.get('raw_text', '')).strip(), "   ")

                print(f"\n>>> [CONTEXT {rank}] [CODE AST] | Do tin cay (Sigmoid): {conf_pct:.2f}% | RRF: {rrf_score:.4f}", flush=True)
                print(f" - Tep ma nguon: {file_p} (Dong {s_line} -> {e_line})", flush=True)
                print(f" - Pham vi cu phap: {scope}", flush=True)
                print(f" - Ma nguon kem Header Context:\n{ctx_code}", flush=True)
                print("-" * 72, flush=True)
            else:
                start_sec = int(item.get('start_sec', 0))
                start_label = item.get('start_label') or f"{start_sec//60:02d}:{start_sec%60:02d}"
                end_label = item.get('end_label') or f"{start_sec//60:02d}:{start_sec%60:02d}"
                video_title = item.get('video_title') or "video_lecture.mp4"
                speech_text = item.get('raw_text', '')
                wrapped_speech = textwrap.fill(f'"{speech_text[:250]}..."', width=72, initial_indent="   ", subsequent_indent="   ")

                approx_tag = " [MỐC THAM KHẢO GẦN NHẤT]" if item.get("is_approximate") else ""
                print(f"\n>>> [CONTEXT {rank}] [VIDEO TRANSCRIPT]{approx_tag} | Do tin cay (Sigmoid): {conf_pct:.2f}% | RRF: {rrf_score:.4f}", flush=True)
                print(f" - Video: {video_title}", flush=True)
                print(f" - Moc thoi gian: [{start_label} -> {end_label}] (Giay {start_sec}s)", flush=True)
                print(f" - The tua video: <timestamp sec=\"{start_sec}\">{start_label}</timestamp>", flush=True)
                print(f" - Loi giang:\n{wrapped_speech}", flush=True)
                print("-" * 72, flush=True)

        # Mô phỏng Socratic Synthesizer
        print("\n" + "=" * 72, flush=True)
        print("[STAGE 10: MO PHONG SOCRATIC SYNTHESIZER - CHONG VAN PHONG CONG NGHIEP]", flush=True)
        print("=" * 72, flush=True)
        best_video = next((item for item in final_assembled if item.get("content_type") == "video_transcript" and "start_sec" in item), None)
        best_code = next((item for item in final_assembled if item.get("content_type") == "code_ast"), None)

        best_ts = f'<timestamp sec="{best_video["start_sec"]}">{best_video["start_label"]}</timestamp>' if best_video else '<timestamp sec="0">00:00</timestamp>'
        code_ref = f" (đối chiếu tại dòng {best_code['start_line']} file `{best_code['file_path']}`)" if best_code else ""

        print("\n--- MAU CAU TRA LOI SOCRATIC DA PHUONG THUC (VIDEO + CODE AST) ---", flush=True)
        sample_response = (
            f"Chào bạn, mình thấy bạn đang tìm hiểu về kiến thức lập trình C++{code_ref}.\n\n"
            f"1. Phân tích nguyên lý:\n"
            f"   Trong C++, các khái niệm cú pháp như hằng số (`const`) hay không gian tên (`std`) đều có "
            f"   quy tắc biên dịch chặt chẽ để đảm bảo an toàn bộ nhớ và tránh xung đột định danh.\n\n"
            f"2. Gợi ý tư duy Socratic:\n"
            f"   Khi khai báo một biến với từ khóa `const`, bạn hãy thử dự đoán: Nếu chúng ta cố tình "
            f"   gán lại một giá trị mới cho biến đó ở các dòng tiếp theo, trình biên dịch C++ sẽ thông báo điều gì?\n\n"
            f"3. Xem lại bài giảng trực quan:\n"
            f"   Thầy giáo đã giải thích rất chi tiết kiến thức này và thao tác mẫu trên Visual Studio "
            f"   ở mốc {best_ts}. Bạn hãy bấm vào mốc thời gian để xem lại đoạn video thao tác trực tiếp nhé!"
        )
        print(textwrap.fill(sample_response, width=72, replace_whitespace=False), flush=True)
        print("=" * 72 + "\n", flush=True)

    finally:
        await close_async_qdrant_client()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Test search on Qdrant Cloud with Multilingual Cross-Encoder")
    parser.add_argument("query", type=str, nargs="?", default="Tại sao dùng lệnh cout trong C++ lại bị báo đỏ gạch chân?", help="Câu hỏi tìm kiếm")
    parser.add_argument("--course", type=str, default="cpp-core", help="Mã khóa học")
    parser.add_argument("--seq", type=int, default=2, help="Thứ tự bài học hiện tại (lesson_seq <= seq)")
    parser.add_argument("--threshold", type=float, default=None, help="Ngưỡng lọc Sigmoid tùy chỉnh (mặc định theo phân tầng)")
    args = parser.parse_args()

    asyncio.run(run_search_probe(
        query_text=args.query,
        current_lesson_seq=args.seq,
        course_id=args.course,
        min_score_threshold=args.threshold
    ))


if __name__ == "__main__":
    main()

