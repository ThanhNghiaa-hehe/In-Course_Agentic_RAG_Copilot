import sys
import re
import textwrap
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.config import settings

def sanitize_terminal_text(text: str) -> str:
    if not text:
        return ""
    # Loại bỏ ký tự carriage return và ký tự điều khiển gây lỗi giật/đè con trỏ PowerShell
    text = text.replace('\r', ' ').replace('\ufffd', '')
    # Lọc bỏ các ký tự ngoại ngữ lạ do Whisper sinh ảo giác (Hangul, Hanja,...)
    text = re.sub(r'[\uac00-\ud7af\u1100-\u11ff\u4e00-\u9fff]', '', text)
    return " ".join(text.split())

def sigmoid(logits: np.ndarray) -> np.ndarray:
    """
    Logistic Sigmoid Normalization:
    Chuyển đổi raw logits (-inf, +inf) sang xác suất thực [0.0, 1.0] chuẩn toán học.
    Đảm bảo ngưỡng lọc >= 0.35 có ý nghĩa xác suất chính xác.
    """
    clipped = np.clip(logits, -250, 250)
    return 1.0 / (1.0 + np.exp(-clipped))

def reorder_lost_in_the_middle(items):
    """
    Khắc phục hiện tượng 'Lost-in-the-Middle' (Liu et al., Stanford 2024).
    Sắp xếp các chunks theo hình chữ U:
    Chunk cao nhất ở đầu (vị trí 1), nhì ở cuối, các chunk trung bình ở giữa.
    """
    if len(items) <= 2:
        return items
    sorted_items = sorted(items, key=lambda x: x["normalized_score"], reverse=True)
    # Ví dụ với 3 items: [Top 1, Top 3, Top 2]
    reordered = [None] * len(sorted_items)
    left = 0
    right = len(sorted_items) - 1
    for i, item in enumerate(sorted_items):
        if i % 2 == 0:
            reordered[left] = item
            left += 1
        else:
            reordered[right] = item
            right -= 1
    return reordered

def search_course(query_text: str, current_lesson_seq: int = 2, top_candidates=10, final_top_k=3, min_score_threshold=0.35):
    print("=" * 65)
    print(f"🔍 CÂU HỎI HỌC VIÊN: '{query_text}'")
    print(f"Target Collection: {settings.QDRANT_COLLECTION_NAME} | Dynamic Window: lesson_seq <= {current_lesson_seq}")
    
    dense_model = TextEmbedding("intfloat/multilingual-e5-large")
    sparse_model = SparseTextEmbedding("Qdrant/bm25")

    # BẮT BUỘC: Thêm tiền tố 'query: ' cho mô hình multilingual-e5-large
    query_dense = list(dense_model.embed([f"query: {query_text}"]))[0].tolist()
    query_sparse = list(sparse_model.embed([query_text]))[0]

    client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=60.0)

    # [STAGE 6 & 7] True Hybrid Retrieval: Dense E5 + Sparse BM25 RRF với In-HNSW Pre-filtering
    print(f"\n[STAGE 6 & 7] True Hybrid Retrieval (Dense E5 + Sparse BM25 RRF) Top {top_candidates} candidates...")
    
    query_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="course_id",
                match=models.MatchValue(value="cpp-core")
            ),
            models.FieldCondition(
                key="lesson_seq",
                range=models.Range(lte=current_lesson_seq)
            )
        ]
    )

    response = client.query_points(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        prefetch=[
            models.Prefetch(
                query=query_dense,
                using="dense",
                filter=query_filter,
                limit=top_candidates
            ),
            models.Prefetch(
                query=models.SparseVector(
                    indices=query_sparse.indices.tolist(),
                    values=query_sparse.values.tolist()
                ),
                using="sparse",
                filter=query_filter,
                limit=top_candidates
            )
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=top_candidates
    )

    raw_candidates = response.points
    print(f"Lấy được {len(raw_candidates)} chunks ứng viên qua thuật toán RRF.")

    # [STAGE 8] Re-ranking & Ngưỡng RRF Normalization
    print("\n[STAGE 8] Dung hợp thứ hạng RRF & Lọc theo ngưỡng tin cậy...")
    scored_items = []
    for hit in raw_candidates:
        p = hit.payload
        raw_score = hit.score
        # Qdrant RRF Score phản ánh trực tiếp độ tương quan dung hợp đa phương thức trong [0.0 - 1.0]
        prob_score = float(raw_score)
        
        if prob_score >= min_score_threshold:
            scored_items.append({
                "raw_score": raw_score,
                "normalized_score": prob_score,
                "payload": p
            })

    # Lấy top K sau reranking
    top_reranked = sorted(scored_items, key=lambda x: x["normalized_score"], reverse=True)[:final_top_k]

    # [STAGE 9] Context Assembly chống 'Lost-in-the-Middle'
    print("[STAGE 9] Sắp xếp ngữ cảnh U-shape (Lost-in-the-Middle Mitigation)...")
    final_assembled = reorder_lost_in_the_middle(top_reranked)

    print(f"\n" + "=" * 72, flush=True)
    print(f"KET QUA TRUY XUAT DA PHUONG THUC ({len(final_assembled)} CHUNKS TIEM VAO PROMPT):", flush=True)
    print("=" * 72, flush=True)
    for rank, item in enumerate(final_assembled, 1):
        p = item["payload"]
        c_type = p.get("content_type", "video_transcript")

        if c_type == "code_ast":
            file_p = p.get('file_path', 'unknown.cpp')
            scope = p.get('code_scope', 'unknown')
            s_line = p.get('start_line', 0)
            e_line = p.get('end_line', 0)
            code_body = textwrap.indent(p.get('raw_text', '').strip(), "   ")

            print(f"\n>>> [CONTEXT {rank}] [CODE AST] | Diem RRF: {item['raw_score']:.4f} (Do tin cay: {item['normalized_score']:.2%})", flush=True)
            print(f" - Tep ma nguon: {file_p} (Dong {s_line} -> {e_line})", flush=True)
            print(f" - Pham vi cu phap: {scope}", flush=True)
            print(f" - Ma nguon AST:\n{code_body}", flush=True)
            print("-" * 72, flush=True)
        else:
            start_sec = int(p.get('start_sec', 0))
            end_sec = int(p.get('end_sec', 0))
            start_label = p.get('start_label') or f"{start_sec//60:02d}:{start_sec%60:02d}"
            end_label = p.get('end_label') or f"{end_sec//60:02d}:{end_sec%60:02d}"
            video_title = p.get('video_title') or "video_lecture.mp4"
            clean_text = sanitize_terminal_text(p.get('raw_text', ''))
            wrapped_speech = textwrap.fill(f'"{clean_text[:250]}..."', width=72, initial_indent="   ", subsequent_indent="   ")

            print(f"\n>>> [CONTEXT {rank}] [VIDEO TRANSCRIPT] | Diem RRF: {item['raw_score']:.4f} (Do tin cay: {item['normalized_score']:.2%})", flush=True)
            print(f" - Video: {video_title}", flush=True)
            print(f" - Moc thoi gian: [{start_label} -> {end_label}] (Giay {start_sec}s)", flush=True)
            print(f" - The tua video: <timestamp sec=\"{start_sec}\">{start_label}</timestamp>", flush=True)
            print(f" - Loi giang:\n{wrapped_speech}", flush=True)
            print("-" * 72, flush=True)

    # [STAGE 10] Minh hoa Socratic Synthesis chong van phong "cong nghiep"
    print("\n" + "=" * 72, flush=True)
    print("[STAGE 10: MO PHONG SOCRATIC SYNTHESIZER - CHONG VAN PHONG CONG NGHIEP]", flush=True)
    print("=" * 72, flush=True)
    
    if final_assembled:
        # Trích xuất video chunk có start_sec để tua video
        best_video = next((item["payload"] for item in final_assembled if item["payload"].get("content_type") == "video_transcript" and "start_sec" in item["payload"]), None)
        best_code = next((item["payload"] for item in final_assembled if item["payload"].get("content_type") == "code_ast"), None)

        best_ts = f'<timestamp sec="{best_video["start_sec"]}">{best_video["start_label"]}</timestamp>' if best_video else '<timestamp sec="0">00:00</timestamp>'
        code_ref = f" (đối chiếu tại dòng {best_code['start_line']} file `{best_code['file_path']}`)" if best_code else ""
        
        print("\n* NGUYEN TAC: Bo qua cac cau noi dua / tu dem tho ('ngua mat', 'loi lao', 'da gia').", flush=True)
        print("* CHAT LOC: Tap trung vao ban chat ky thuat, the tua video va vi tri code mau.", flush=True)
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
        wrapped_resp = textwrap.fill(sample_response, width=72, replace_whitespace=False)
        print(wrapped_resp, flush=True)
        print("=" * 72 + "\n", flush=True)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Test search on Qdrant Cloud")
    parser.add_argument("query", type=str, nargs="?", default="Tại sao dùng lệnh cout trong C++ lại bị báo đỏ gạch chân?", help="Câu hỏi tìm kiếm")
    parser.add_argument("--seq", type=int, default=2, help="Thứ tự bài học hiện tại (Dynamic Lesson Window: lesson_seq <= seq)")
    args = parser.parse_args()
    search_course(args.query, current_lesson_seq=args.seq)
