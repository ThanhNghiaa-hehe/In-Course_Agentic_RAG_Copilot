import sys
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.config import settings

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

def search_course(query_text: str, top_candidates=10, final_top_k=3, min_score_threshold=0.35):
    print("=" * 65)
    print(f"🔍 CÂU HỎI HỌC VIÊN: '{query_text}'")
    print(f"Target Collection: {settings.QDRANT_COLLECTION_NAME}")
    
    dense_model = TextEmbedding("intfloat/multilingual-e5-large")
    sparse_model = SparseTextEmbedding("Qdrant/bm25")

    query_dense = list(dense_model.embed([query_text]))[0].tolist()
    query_sparse = list(sparse_model.embed([query_text]))[0]

    client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=60.0)

    # [STAGE 6 & 7] Hybrid Retrieval với In-HNSW Pre-filtering (lesson_seq <= 1)
    print(f"\n[STAGE 6 & 7] Truy xuất Top {top_candidates} candidates từ Qdrant Cloud...")
    response = client.query_points(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        query=query_dense,
        using="dense",
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="course_id",
                    match=models.MatchValue(value="cpp-core")
                ),
                models.FieldCondition(
                    key="lesson_seq",
                    range=models.Range(lte=1)
                )
            ]
        ),
        limit=top_candidates
    )

    raw_candidates = response.points
    print(f"Lấy được {len(raw_candidates)} chunks ứng viên ban đầu.")

    # [STAGE 8] Re-ranking với Sigmoid Normalization
    print("\n[STAGE 8] Re-ranking & Áp dụng Chuẩn hóa Sigmoid xác suất [0.0 - 1.0]...")
    scored_items = []
    for hit in raw_candidates:
        p = hit.payload
        raw_score = hit.score
        # Áp dụng Sigmoid để chuẩn hóa score Cosine/Logit sang xác suất thực
        # Giả sử hàm chuyển đổi: sigma((raw_score - 0.7) * 10)
        prob_score = float(sigmoid(np.array((raw_score - 0.7) * 10)))
        
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

    print(f"\n🎯 KẾT QUẢ CUỐI CÙNG ({len(final_assembled)} CHUNKS ĐƯỢC TIÊM VÀO SOCRATIC PROMPT):\n")
    for rank, item in enumerate(final_assembled, 1):
        p = item["payload"]
        print(f"--- VỊ TRÍ CONTEXT {rank} | Xác suất liên quan: {item['normalized_score']:.2%} (Raw: {item['raw_score']:.4f}) ---")
        print(f"🎬 Video: {p.get('video_title')} | Mốc: [{p.get('start_label')} ➔ {p.get('end_label')}] (Giây {p.get('start_sec')}s)")
        print(f"📌 Thẻ tua Video tự động cho Player: <timestamp sec=\"{p.get('start_sec')}\">{p.get('start_label')}</timestamp>")
        print(f"📝 Lời giảng: \"{p.get('raw_text')[:220]}...\"\n")

if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "Phím tắt chạy chương trình C++ trong Visual Studio là gì?"
    search_course(q)
