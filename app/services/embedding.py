import logging
from typing import List, Tuple, Optional
import numpy as np
from fastembed import TextEmbedding, SparseTextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from app.config import settings

logger = logging.getLogger("uvicorn.error")

class EmbeddingService:
    """
    Dịch vụ quản lý Dual Embedding (Dense E5-large + Sparse BM25) & Multilingual Cross-Encoder Reranker.
    Được nạp vào bộ nhớ RAM 1 lần duy nhất lúc khởi động server (FastAPI Lifespan).
    Đảm bảo tốc độ truy xuất siêu tốc (< 50ms) cho mỗi request.
    """
    def __init__(self):
        logger.info(f"[EmbeddingService] Khởi tạo mô hình Dense: {settings.EMBEDDING_MODEL_NAME}...")
        self.dense_model = TextEmbedding(settings.EMBEDDING_MODEL_NAME)

        logger.info(f"[EmbeddingService] Khởi tạo mô hình Sparse: {settings.SPARSE_MODEL_NAME}...")
        self.sparse_model = SparseTextEmbedding(settings.SPARSE_MODEL_NAME)

        logger.info(f"[EmbeddingService] Khởi tạo mô hình Reranker Đa ngữ: {settings.RERANKER_MODEL_NAME}...")
        self.reranker_model = TextCrossEncoder(settings.RERANKER_MODEL_NAME)
        logger.info("[EmbeddingService] Nạp toàn bộ mô hình Embedding & Reranker thành công!")

    def embed_query_dense(self, query_text: str) -> List[float]:
        """
        Sinh Dense Vector 1024 chiều.
        BẮT BUỘC tuân thủ tiêu chuẩn E5: luôn có tiền tố 'query: ' cho câu truy vấn.
        """
        formatted_query = f"query: {query_text.strip()}"
        dense_vec = list(self.dense_model.embed([formatted_query]))[0]
        return dense_vec.tolist()

    def embed_query_sparse(self, query_text: str) -> Tuple[List[int], List[float]]:
        """
        Sinh Sparse BM25 Vector (indices, values).
        """
        sparse_vec = list(self.sparse_model.embed([query_text.strip()]))[0]
        return sparse_vec.indices.tolist(), sparse_vec.values.tolist()

    def rerank_documents(self, query: str, documents: List[str]) -> List[float]:
        """
        Chấm điểm tương quan chéo sâu (Cross-Attention) giữa câu hỏi và danh sách văn bản.
        Trả về danh sách điểm logit z tương ứng.
        """
        if not documents:
            return []
        scores = list(self.reranker_model.rerank(query=query, documents=documents))
        return [float(s) for s in scores]

    def warmup(self) -> None:
        """
        Khởi động nhẹ ONNX session để loại bỏ độ trễ (cold-start latency) cho người dùng đầu tiên.
        """
        logger.info("[EmbeddingService] Đang chạy Warmup mô hình Embedding & Reranker...")
        self.embed_query_dense("warmup query")
        self.embed_query_sparse("warmup query")
        self.rerank_documents("warmup query", ["warmup document"])
        logger.info("[EmbeddingService] Warmup hoàn tất!")


_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """
    Singleton Provider cho EmbeddingService.
    """
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service

