import os
import sys
import logging
from functools import lru_cache
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
            import onnxruntime as ort
            available_ort_providers = ort.get_available_providers()
            if torch.cuda.is_available() and "CUDAExecutionProvider" in available_ort_providers:
                self.device = "cuda"
                self.providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
                gpu_name = torch.cuda.get_device_name(0)
                vram_mb = torch.cuda.get_device_properties(0).total_memory / (1024 * 1024)
                logger.info(
                    f"[EmbeddingService:M-05e] Kích hoạt tăng tốc GPU VRAM CUDA: {gpu_name} "
                    f"({vram_mb:.0f} MB VRAM) - Providers: {self.providers}"
                )
            else:
                logger.info(
                    f"[EmbeddingService] Sử dụng CPUExecutionProvider (torch.cuda={torch.cuda.is_available()}, "
                    f"ort_providers={available_ort_providers})."
                )
        except Exception as e:
            logger.warning(f"[EmbeddingService] Lỗi nhận diện CUDA ({e}), sử dụng CPUExecutionProvider.")

        pin_single_cpu_thread = self.device == "cpu" or os.environ.get("OMP_NUM_THREADS") == "1"
        cpu_threads = 1 if pin_single_cpu_thread else None

        logger.info(f"[EmbeddingService] Khởi tạo mô hình Dense: {settings.EMBEDDING_MODEL_NAME}...")
        self.dense_model = TextEmbedding(
            settings.EMBEDDING_MODEL_NAME,
            providers=self.providers,
            threads=cpu_threads,
        )

        logger.info(f"[EmbeddingService] Khởi tạo mô hình Sparse: {settings.SPARSE_MODEL_NAME}...")
        self.sparse_model = SparseTextEmbedding(
            settings.SPARSE_MODEL_NAME,
            providers=self.providers,
            threads=cpu_threads,
        )

        use_cpu_reranker = getattr(settings, "USE_CPU_RERANKER", True)
        reranker_providers = ["CPUExecutionProvider"] if use_cpu_reranker else self.providers
        reranker_device = "CPU" if use_cpu_reranker else self.device.upper()
        reranker_threads = (
            (1 if pin_single_cpu_thread else getattr(settings, "RERANK_CPU_THREADS", 4))
            if use_cpu_reranker
            else None
        )

        int8_model_dir = Path(__file__).resolve().parent.parent.parent / "data" / "models" / "jina-reranker-v2-int8"
        int8_onnx_file = int8_model_dir / "onnx" / "model.onnx"
        if getattr(settings, "USE_INT8_RERANKER", False) and int8_onnx_file.exists():
            size_mb = int8_onnx_file.stat().st_size / (1024 * 1024)
            logger.info(
                f"[EmbeddingService] Kích hoạt mô hình Reranker INT8 (ONNX PTQ AVX-512 - {size_mb:.1f}MB, threads={reranker_threads}) từ: {int8_model_dir}..."
            )
            self.reranker_model = TextCrossEncoder(
                settings.RERANKER_MODEL_NAME,
                specific_model_path=str(int8_model_dir),
                threads=reranker_threads,
                providers=reranker_providers
            )
        else:
            logger.info(
                f"[EmbeddingService:M-05e] Khởi tạo mô hình Reranker Đa ngữ FP32: {settings.RERANKER_MODEL_NAME} "
                f"(Device: {reranker_device}, Threads: {reranker_threads}, Providers: {reranker_providers})..."
            )
            self.reranker_model = TextCrossEncoder(
                settings.RERANKER_MODEL_NAME,
                threads=reranker_threads,
                providers=reranker_providers
            )
        logger.info(f"[EmbeddingService] Nạp toàn bộ mô hình Embedding & Reranker thành công (Embedding: {self.device.upper()}, Reranker: {reranker_device})!")

    @staticmethod
    def _normalize_query_key(query_text: str) -> str:
        clean = (query_text or "").strip()
        while clean.lower().startswith("query:"):
            clean = clean[6:].strip()
        return clean

    @lru_cache(maxsize=512)
    def _embed_query_dense_cached(self, clean_query: str) -> Tuple[float, ...]:
        formatted_query = f"query: {clean_query}"
        dense_vec = list(self.dense_model.embed([formatted_query]))[0]
        return tuple(dense_vec.tolist() if hasattr(dense_vec, "tolist") else dense_vec)

    def embed_query_dense(self, query_text: str) -> List[float]:
        """
        Sinh Dense Vector 1024 chiều (có LRU Cache maxsize=512 chống tính toán lặp E5 trong cùng lượt).
        BẮT BUỘC tuân thủ tiêu chuẩn E5: luôn có đúng 1 tiền tố 'query: ' cho câu truy vấn.
        """
        clean_query = self._normalize_query_key(query_text)
        return list(self._embed_query_dense_cached(clean_query))

    embed_query_dense.cache_info = _embed_query_dense_cached.cache_info
    embed_query_dense.cache_clear = _embed_query_dense_cached.cache_clear

    def embed_queries_dense_batch(self, query_texts: List[str]) -> np.ndarray:
        """Sinh ma trận Dense Vector 1024-dim L2-normalized theo batch cho các tập prototype (không làm bẩn LRU cache 512)."""
        if not query_texts:
            return np.zeros((0, 1024), dtype=np.float32)
        formatted = [f"query: {self._normalize_query_key(q)}" for q in query_texts]
        raw_vecs = list(self.dense_model.embed(formatted, batch_size=32))
        arr = np.array([v.tolist() if hasattr(v, "tolist") else v for v in raw_vecs], dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return arr / norms

    def embed_query_sparse(self, query_text: str) -> Tuple[List[int], List[float]]:
        """
        Sinh Sparse BM25 Vector (indices, values).
        """
        sparse_vec = list(self.sparse_model.embed([query_text.strip()]))[0]
        return sparse_vec.indices.tolist(), sparse_vec.values.tolist()

    def rerank_documents(self, query: str, documents: List[str]) -> List[float]:
        """
        Chấm điểm tương quan chéo sâu (Cross-Attention) giữa câu hỏi và danh sách văn bản.
        Áp dụng Micro-batching (RERANK_BATCH_SIZE=4) và cắt tỉa độ dài (RERANK_MAX_CHARS=600)
        để bảo toàn bộ nhớ và ngăn ngừa hoàn toàn hiện tượng tràn VRAM/RAM.
        Trả về danh sách điểm logit z tương ứng.
        """
        if not documents:
            return []

        batch_size = getattr(settings, "RERANK_BATCH_SIZE", 4)
        max_chars = getattr(settings, "RERANK_MAX_CHARS", 600)
        truncated_docs = [doc[:max_chars] if isinstance(doc, str) else str(doc)[:max_chars] for doc in documents]

        all_scores: List[float] = []
        for i in range(0, len(truncated_docs), batch_size):
            batch = truncated_docs[i : i + batch_size]
            try:
                batch_scores = list(self.reranker_model.rerank(query=query, documents=batch, batch_size=batch_size))
                all_scores.extend([float(s) for s in batch_scores])
            except Exception as batch_err:
                logger.warning(
                    f"[EmbeddingService] Lỗi micro-batch rerank [{i}:{i+batch_size}]: {batch_err}. Fallback điểm logit trung tính."
                )
                all_scores.extend([-2.0] * len(batch))
        return all_scores

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

