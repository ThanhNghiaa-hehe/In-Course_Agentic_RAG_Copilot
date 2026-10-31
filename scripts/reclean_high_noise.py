"""
Script Batch Reclean cho 12 Bài Học Trong Nhóm High Noise
In-Course Agentic RAG Copilot - Tác giả: Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Tính năng:
- Tự động duyệt qua 12 bài học có mức độ nhiễu âm học cao:
  [2, 5, 10, 18, 34, 41, 55, 57, 58, 59, 67, 76]
- Gọi reclean_single_target trên từng file raw_segments.json.
- Chuẩn hóa văn bản, cắt chunk, sinh E5 1024-dim + BM25 sparse và upsert idempotent lên Qdrant Cloud.
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.reclean_transcripts import reclean_single_target

HIGH_NOISE_SEQS = [2, 5, 10, 18, 34, 41, 55, 57, 58, 59, 67, 76]
TRANSCRIPTS_ROOT = PROJECT_ROOT / "data" / "transcripts"

def run_batch():
    print("=" * 72)
    print(" BẮT ĐẦU BATCH RECLEAN CHO 12 BÀI HỌC NHÓM HIGH NOISE")
    print(f" Danh sách bài: {HIGH_NOISE_SEQS}")
    print("=" * 72)

    total_updated = 0
    start_time = time.time()

    for seq in HIGH_NOISE_SEQS:
        dirs = list(TRANSCRIPTS_ROOT.glob(f"**/*lesson-{seq:02d}*")) or list(TRANSCRIPTS_ROOT.glob(f"**/*lesson_{seq:02d}*"))
        if not dirs:
            print(f"[CẢNH BÁO] Không tìm thấy thư mục cho Bài {seq}")
            continue

        l_dir = dirs[0]
        raw_file = l_dir / f"lesson-{seq:02d}_raw_segments.json"
        chunk_file = l_dir / f"lesson-{seq:02d}_chunks.json"

        target_file = raw_file if raw_file.exists() else (chunk_file if chunk_file.exists() else None)
        if not target_file:
            print(f"[CẢNH BÁO] Không tìm thấy file dữ liệu cho Bài {seq}")
            continue

        print(f"\n[Bài {seq:2d}] Bắt đầu xử lý: {target_file.name}")
        try:
            pts = reclean_single_target(target_file)
            total_updated += pts
        except Exception as e:
            print(f"   [LỖI] Thất bại tại Bài {seq}: {e}")

    elapsed = time.time() - start_time
    print("\n" + "=" * 72)
    print(f" HOÀN TẤT BATCH RECLEAN! Đã cập nhật {total_updated} points lên Qdrant Cloud.")
    print(f" Thời gian thực thi: {elapsed:.1f} giây ({elapsed/60:.2f} phút).")
    print("=" * 72)

if __name__ == "__main__":
    run_batch()

