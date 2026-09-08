import logging
import re
from typing import List, Dict, Any, Optional
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from app.config import settings
from app.services.qdrant import get_async_qdrant_client
from app.services.embedding import EmbeddingService, get_embedding_service

logger = logging.getLogger("uvicorn.error")


def sanitize_text(text: str) -> str:
    """
    Chuẩn hóa văn bản trả về:
    - Loại bỏ ký tự carriage return và các ký tự điều khiển.
    - Lọc bỏ các ký tự ngoại ngữ lạ (Hangul, Hanja,...) do lỗi âm học mô hình sinh ra.
    """
    if not text:
        return ""
    text = text.replace("\r", " ").replace("\ufffd", "")
    text = re.sub(r"[\uac00-\ud7af\u1100-\u11ff\u4e00-\u9fff]", "", text)
    return " ".join(text.split())


def reorder_lost_in_the_middle(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Khắc phục hiện tượng 'Lost-in-the-Middle' (Liu et al., Stanford 2024).
    Sắp xếp các chunks theo cấu trúc hình chữ U:
    - Chunk có độ liên quan cao nhất ở đầu (vị trí 1)
    - Chunk cao thứ nhì ở cuối danh sách
    - Các chunk còn lại nằm ở phần giữa
    Ví dụ với 3 chunks: [Top 1, Top 3, Top 2]
    """
    if len(items) <= 2:
        return items

    sorted_items = sorted(items, key=lambda x: x["rrf_score"], reverse=True)
    reordered: List[Optional[Dict[str, Any]]] = [None] * len(sorted_items)
    left = 0
    right = len(sorted_items) - 1

    for i, item in enumerate(sorted_items):
        if i % 2 == 0:
            reordered[left] = item
            left += 1
        else:
            reordered[right] = item
            right -= 1

    return [item for item in reordered if item is not None]


class RetrievalService:
    """
    Lõi Dịch vụ Tìm kiếm Đa phương thức 11 Giai đoạn (Stage 6 -> 9) chuẩn Enterprise:
    - True Hybrid Retrieval (Parallel Prefetch: Dense E5 + Sparse BM25)
    - In-HNSW Dynamic Pre-filtering (course_id & lesson_seq <= current_seq)
    - Qdrant Native Reciprocal Rank Fusion (RRF)
    - Ngưỡng tin cậy toán học (min_score_threshold >= 0.35)
    - U-shaped Context Assembly chống Lost-in-the-Middle
    """

    def __init__(
        self,
        client: Optional[AsyncQdrantClient] = None,
        embedding_service: Optional[EmbeddingService] = None
    ):
        self.client = client or get_async_qdrant_client()
        self.embedding_service = embedding_service or get_embedding_service()

    async def search(
        self,
        query_text: str,
        course_id: str = "cpp-core",
        current_lesson_seq: int = 2,
        top_candidates: int = settings.DEFAULT_TOP_CANDIDATES,
        final_top_k: int = settings.DEFAULT_FINAL_TOP_K,
        min_score_threshold: float = settings.MIN_SCORE_THRESHOLD
    ) -> List[Dict[str, Any]]:
        """
        Thực hiện tìm kiếm ngữ cảnh bài học bất đồng bộ (non-blocking).
        """
        logger.info(
            f"[RetrievalService] Query: '{query_text}' | Course: {course_id} | Window: lesson_seq <= {current_lesson_seq}"
        )

        # 1. Sinh Dual Vectors bất đồng bộ / fast ONNX
        query_dense = self.embedding_service.embed_query_dense(query_text)
        sparse_indices, sparse_values = self.embedding_service.embed_query_sparse(query_text)

        # 2. Xây dựng In-HNSW Pre-filter động (Ngăn ngừa triệt để hiện tượng lộ bài học tương lai)
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="course_id",
                    match=models.MatchValue(value=course_id)
                ),
                models.FieldCondition(
                    key="lesson_seq",
                    range=models.Range(lte=current_lesson_seq)
                )
            ]
        )

        # 3. [STAGE 6 & 7] Song song hóa Prefetch: Dense + Sparse với Native RRF Fusion
        response = await self.client.query_points(
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
                        indices=sparse_indices,
                        values=sparse_values
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
        logger.info(f"[RetrievalService] Lấy được {len(raw_candidates)} chunks ứng viên qua thuật toán RRF.")

        # 4. [STAGE 8] Lọc theo ngưỡng tin cậy RRF
        scored_items: List[Dict[str, Any]] = []
        for hit in raw_candidates:
            raw_score = float(hit.score)
            if raw_score >= min_score_threshold:
                p = hit.payload or {}
                content_type = p.get("content_type", "video_transcript")

                item: Dict[str, Any] = {
                    "id": str(hit.id),
                    "rrf_score": round(raw_score, 4),
                    "confidence_pct": round(raw_score * 100, 2),
                    "content_type": content_type,
                    "lesson_id": p.get("lesson_id", ""),
                    "lesson_seq": p.get("lesson_seq", 0),
                    "raw_text": sanitize_text(p.get("raw_text", "")),
                }

                if content_type == "code_ast":
                    item.update({
                        "file_path": p.get("file_path", ""),
                        "language": p.get("language", "cpp"),
                        "code_scope": p.get("code_scope", ""),
                        "start_line": p.get("start_line", 0),
                        "end_line": p.get("end_line", 0)
                    })
                else:
                    start_sec = int(p.get("start_sec", 0))
                    end_sec = int(p.get("end_sec", 0))
                    item.update({
                        "video_title": p.get("video_title", "video_lecture.mp4"),
                        "start_sec": start_sec,
                        "end_sec": end_sec,
                        "start_label": p.get("start_label") or f"{start_sec//60:02d}:{start_sec%60:02d}",
                        "end_label": p.get("end_label") or f"{end_sec//60:02d}:{end_sec%60:02d}",
                        "timestamp_tag": f'<timestamp sec="{start_sec}">{p.get("start_label", f"{start_sec//60:02d}:{start_sec%60:02d}")}</timestamp>'
                    })

                scored_items.append(item)

        # Lấy top K sau xếp hạng
        top_reranked = sorted(scored_items, key=lambda x: x["rrf_score"], reverse=True)[:final_top_k]

        # 5. [STAGE 9] Context Assembly chống 'Lost-in-the-Middle'
        final_assembled = reorder_lost_in_the_middle(top_reranked)
        logger.info(f"[RetrievalService] Hoàn tất U-shaped Assembly với {len(final_assembled)} chunks tốt nhất.")

        return final_assembled


_retrieval_service: Optional[RetrievalService] = None


def get_retrieval_service() -> RetrievalService:
    """
    FastAPI Dependency Provider cho RetrievalService.
    """
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService()
    return _retrieval_service
