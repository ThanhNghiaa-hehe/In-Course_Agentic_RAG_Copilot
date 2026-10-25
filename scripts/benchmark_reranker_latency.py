"""
Benchmark Đo Lường Hiệu Năng & Độ Trễ Re-ranker (Sáng Kiến M-05e & M-05a/M-05b)
Triệt tiêu thắt nút cổ chai CPU 16.5s -> < 150ms trên GPU NVIDIA GeForce RTX 2050 CUDA.

Tác giả: Trần Thành Nghĩa (MSSV: 23DH112252) - HUFLIT
"""

import sys
import os
import time
import asyncio
from typing import List

# Đảm bảo đường dẫn gốc được nạp
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.services.embedding import get_embedding_service
from app.config import settings


def run_benchmark():
    print("=" * 70)
    print(" BẮT ĐẦU MICRO-BENCHMARK ĐỘ TRỄ RE-RANKER & DUAL EMBEDDING (SÁNG KIẾN M-05e)")
    print("=" * 70)

    # 1. Khởi tạo EmbeddingService
    t_init_start = time.perf_counter()
    embedding_service = get_embedding_service()
    init_duration_ms = (time.perf_counter() - t_init_start) * 1000

    print(f"[*] Thiết bị suy luận: {embedding_service.device.upper()}")
    print(f"[*] ONNX Runtime Providers: {embedding_service.providers}")
    print(f"[*] Thời gian nạp mô hình: {init_duration_ms:.2f} ms")
    print("-" * 70)

    # 2. Chuẩn bị mẫu truy vấn và văn bản thử nghiệm thực tế
    query = "Học về con trỏ và cấp phát bộ nhớ động trong C++"
    documents: List[str] = [
        "[Bài giảng Video 05_pointer.mp4 mốc 04:15]\nCon trỏ là biến lưu trữ địa chỉ ô nhớ của biến khác trong bộ nhớ RAM.",
        "[Mã nguồn CPP - function_main]\nint* ptr = new int(10);\nstd::cout << *ptr << std::endl;\ndelete ptr;",
        "[Bài giảng Video 02_loop.mp4 mốc 01:20]\nVòng lặp for cho phép lặp với số lần xác định trước qua biến đếm i.",
        "[Bài giảng Video 08_oop.mp4 mốc 12:40]\nTính đóng gói trong lập trình hướng đối tượng giúp che giấu dữ liệu.",
        "[Bài giảng Video 05_pointer.mp4 mốc 08:30]\nToán tử & dùng để lấy địa chỉ ô nhớ của một biến thông thường.",
        "[Mã nguồn CPP - struct_node]\nstruct Node { int data; Node* next; };",
    ]

    # 3. Warmup
    print("[*] Chạy Warmup mô hình...")
    embedding_service.warmup()
    print("[+] Warmup hoàn tất!")
    print("-" * 70)

    # 4. Đo lường Dense & Sparse Embedding
    dense_times = []
    for _ in range(5):
        t0 = time.perf_counter()
        _ = embedding_service.embed_query_dense(query)
        dense_times.append((time.perf_counter() - t0) * 1000)

    avg_dense_ms = sum(dense_times) / len(dense_times)
    min_dense_ms = min(dense_times)
    print(f"[Dense Embedding - E5-large 1024d] Trung bình: {avg_dense_ms:.2f} ms | Tốt nhất: {min_dense_ms:.2f} ms")

    sparse_times = []
    for _ in range(5):
        t0 = time.perf_counter()
        _ = embedding_service.embed_query_sparse(query)
        sparse_times.append((time.perf_counter() - t0) * 1000)

    avg_sparse_ms = sum(sparse_times) / len(sparse_times)
    min_sparse_ms = min(sparse_times)
    print(f"[Sparse Embedding - BM25]         Trung bình: {avg_sparse_ms:.2f} ms | Tốt nhất: {min_sparse_ms:.2f} ms")
    print("-" * 70)

    # 5. Đo lường Re-ranker (M-05e CUDA Execution)
    rerank_times = []
    scores = []
    for i in range(10):
        t0 = time.perf_counter()
        scores = embedding_service.rerank_documents(query, documents)
        elapsed = (time.perf_counter() - t0) * 1000
        rerank_times.append(elapsed)

    avg_rerank_ms = sum(rerank_times) / len(rerank_times)
    min_rerank_ms = min(rerank_times)
    p50_rerank_ms = sorted(rerank_times)[len(rerank_times) // 2]
    p90_rerank_ms = sorted(rerank_times)[int(len(rerank_times) * 0.9)]

    cpu_baseline_ms = 16500.0  # 16.5 giây đo được trên CPU trước tối ưu
    speedup = cpu_baseline_ms / avg_rerank_ms

    print(f"[Cross-Encoder Re-ranker (Jina v2 - 6 Chunks)]")
    print(f"  - Baseline CPU trước tối ưu:   {cpu_baseline_ms:.1f} ms (~16.5 s)")
    print(f"  - Kết quả sau Sáng kiến M-05e:")
    print(f"      + Tốt nhất (Min):          {min_rerank_ms:.2f} ms")
    print(f"      + Trung vị (P50):          {p50_rerank_ms:.2f} ms")
    print(f"      + P90:                     {p90_rerank_ms:.2f} ms")
    print(f"      + Trung bình (Mean):       {avg_rerank_ms:.2f} ms")
    print(f"  - TỐC ĐỘ TĂNG TRƯỞNG (SPEEDUP): {speedup:.1f}x LẦN!")
    print(f"  - Đạt chuẩn mục tiêu (< 150ms): {'[PASSED] DƯỚI 150MS' if avg_rerank_ms < 150 else '[FAILED]'}")
    print("-" * 70)

    # 6. Kiểm tra tính đúng đắn toán học của điểm số
    print("[*] Kiểm tra tính đúng đắn của điểm Logit & Sigmoid:")
    for idx, (doc, sc) in enumerate(zip(documents, scores)):
        prob = 1.0 / (1.0 + pow(2.718281828459045, -sc))
        doc_header = doc.splitlines()[0]
        print(f"  Chunk {idx+1}: Logit z={sc:+.4f} | Sigmoid σ(z)={prob:.4f} | {doc_header}")

    print("=" * 70)
    print(" MICRO-BENCHMARK HOÀN TẤT THÀNH CÔNG RỰC RỠ!")
    print("=" * 70)


if __name__ == "__main__":
    run_benchmark()
