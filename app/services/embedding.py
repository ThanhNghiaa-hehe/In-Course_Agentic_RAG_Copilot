import os
import sys
import logging
from pathlib import Path
from typing import List, Tuple, Optional
import numpy as np
from fastembed import TextEmbedding, SparseTextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from app.config import settings

logger = logging.getLogger("uvicorn.error")


def _setup_cuda_dlls() -> None:
    """
    Tự động liên kết các thư viện CUDA / cuDNN runtime (cublas, cudnn) từ gói torch.lib
    vào hệ thống Windows DLL Search Path để ONNX Runtime CUDAExecutionProvider hoạt động mượt mà.
    """
    if sys.platform == "win32":
        try:
            import torch
            torch_lib = os.path.join(os.path.dirname(torch.__file__), "lib")
            if os.path.isdir(torch_lib):
                if hasattr(os, "add_dll_directory"):
                    os.add_dll_directory(torch_lib)
                current_path = os.environ.get("PATH", "")
                if torch_lib not in current_path:
                    os.environ["PATH"] = torch_lib + os.pathsep + current_path
        except Exception as e:
            logger.warning(f"[EmbeddingService] Không thể cấu hình CUDA DLLs từ torch.lib: {e}")


class EmbeddingService:
    """
    Dịch vụ quản lý Dual Embedding (Dense E5-large + Sparse BM25) & Multilingual Cross-Encoder Reranker.
    Được nạp vào bộ nhớ RAM/VRAM 1 lần duy nhất lúc khởi động server (FastAPI Lifespan).
    Kích hoạt GPU CUDA Hardware Acceleration (Sáng kiến M-05e) đưa độ trễ Re-ranking từ 16.5s về < 50ms.
    """
    def __init__(self):
        _setup_cuda_dlls()

        self.device = "cpu"
        self.providers = ["CPUExecutionProvider"]
        try:
            import torch
            if torch.cuda.is_available():
                self.device = "cuda"
                self.providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
                gpu_name = torch.cuda.get_device_name(0)
                vram_mb = torch.cuda.get_device_properties(0).total_memory / (1024 * 1024)
                logger.info(
                    f"[EmbeddingService:M-05e] Kích hoạt tăng tốc GPU VRAM CUDA: {gpu_name} "
                    f"({vram_mb:.0f} MB VRAM) - Providers: {self.providers}"
                )
            else:
                logger.info("[EmbeddingService] GPU CUDA không khả dụng, sử dụng CPUExecutionProvider.")
        except Exception as e:
            logger.warning(f"[EmbeddingService] Lỗi nhận diện CUDA ({e}), sử dụng CPUExecutionProvider.")

        logger.info(f"[EmbeddingService] Khởi tạo mô hình Dense: {settings.EMBEDDING_MODEL_NAME}...")
        self.dense_model = TextEmbedding(settings.EMBEDDING_MODEL_NAME, providers=self.providers)

        logger.info(f"[EmbeddingService] Khởi tạo mô hình Sparse: {settings.SPARSE_MODEL_NAME}...")
        self.sparse_model = SparseTextEmbedding(settings.SPARSE_MODEL_NAME, providers=self.providers)

        int8_model_dir = Path(__file__).resolve().parent.parent.parent / "data" / "models" / "jina-reranker-v2-int8"
        int8_onnx_file = int8_model_dir / "onnx" / "model.onnx"
        if getattr(settings, "USE_INT8_RERANKER", False) and int8_onnx_file.exists():
            size_mb = int8_onnx_file.stat().st_size / (1024 * 1024)
            logger.info(
                f"[EmbeddingService] Kích hoạt mô hình Reranker INT8 (ONNX PTQ AVX-512 - {size_mb:.1f}MB) từ: {int8_model_dir}..."
            )
            self.reranker_model = TextCrossEncoder(
                settings.RERANKER_MODEL_NAME,
                specific_model_path=str(int8_model_dir),
                providers=self.providers
            )
        else:
            logger.info(
                f"[EmbeddingService:M-05e] Khởi tạo mô hình Reranker Đa ngữ FP32: {settings.RERANKER_MODEL_NAME} "
                f"(Device: {self.device.upper()})..."
            )
            self.reranker_model = TextCrossEncoder(
                settings.RERANKER_MODEL_NAME,
                providers=self.providers
            )
        logger.info(f"[EmbeddingService] Nạp toàn bộ mô hình Embedding & Reranker thành công trên {self.device.upper()}!")

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

    async def rerank_documents_async(self, query: str, documents: List[str]) -> List[float]:
        """
        Phiên bản bất đồng bộ (non-blocking) của rerank_documents.
        Chạy tính toán Cross-Attention trong worker thread riêng qua asyncio.to_thread,
        ngăn chặn hoàn toàn hiện tượng Event Loop Starvation làm tê liệt FastAPI backend.
        """
        import asyncio
        return await asyncio.to_thread(self.rerank_documents, query, documents)

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

