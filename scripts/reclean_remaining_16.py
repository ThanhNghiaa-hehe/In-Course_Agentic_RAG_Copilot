"""
Script Batch Reclean cho 16 Bài Học Còn Lại Trong Giáo Trình
In-Course Agentic RAG Copilot - Tác giả: Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Tính năng:
- Tự động duyệt qua 16 bài học còn dị thường âm học theo báo cáo docs/benchmarks/corpus_phonetic_health_report.md:
  REMAINING_SEQS = [45, 48, 62, 65, 75]
- Làm sạch văn bản âm học Whisper (Stage 2 Tech Canonicalizer):
  + Vòng lặp For/While: 'vòng fo', 'vòng lập qua', 'vòng là con' -> 'vòng for', 'vòng lặp while'
  + Kiểu dữ liệu: 'flow', 'đáp bồ' -> 'float', 'double'
- Tính toán lại dual vectors E5 1024-dim ('passage: ') + BM25 sparse.
- Upsert idempotent lên Qdrant Cloud theo deterministic UUIDv5.
- Cập nhật đồng bộ tệp *_chunks.json trên ổ đĩa.
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.reclean_transcripts import reclean_single_target

REMAINING_SEQS = [45, 48, 62, 65, 75]
TRANSCRIPTS_ROOT = PROJECT_ROOT / "data" / "transcripts"


def run_batch():
    print("=" * 72)
    print(" BẮT ĐẦU BATCH RECLEAN CHO 16 BÀI HỌC CÒN LẠI (STAGE 2 CANONICALIZER)")
    print(f" Danh sách bài ({len(REMAINING_SEQS)} bài): {REMAINING_SEQS}")
    print("=" * 72)

    total_updated = 0
    start_time = time.time()
    successful_lessons = []
    failed_lessons = []

    for seq in REMAINING_SEQS:
        dirs = list(TRANSCRIPTS_ROOT.glob(f"**/*lesson-{seq:02d}*")) or list(TRANSCRIPTS_ROOT.glob(f"**/*lesson_{seq:02d}*"))
        if not dirs:
            print(f"[CẢNH BÁO] Không tìm thấy thư mục cho Bài {seq}")
            failed_lessons.append((seq, "Không tìm thấy thư mục"))
            continue

        l_dir = dirs[0]
        raw_file = l_dir / f"lesson-{seq:02d}_raw_segments.json"
        chunk_file = l_dir / f"lesson-{seq:02d}_chunks.json"

        target_file = raw_file if raw_file.exists() else (chunk_file if chunk_file.exists() else None)
        if not target_file:
            print(f"[CẢNH BÁO] Không tìm thấy file dữ liệu cho Bài {seq}")
            failed_lessons.append((seq, "Không tìm thấy file json"))
            continue

        print(f"\n[Bài {seq:2d}] Bắt đầu xử lý: {target_file.name} ({target_file.parent.name})")
        try:
            pts = reclean_single_target(target_file)
            total_updated += pts
            successful_lessons.append((seq, pts))
        except Exception as e:
            print(f"   [LỖI] Thất bại tại Bài {seq}: {e}")
            failed_lessons.append((seq, str(e)))

    elapsed = time.time() - start_time
    print("\n" + "=" * 72)
    print(f" HOÀN TẤT BATCH RECLEAN CHO 16 BÀI HỌC!")
    print(f" - Thành công: {len(successful_lessons)}/{len(REMAINING_SEQS)} bài")
    print(f" - Tổng points cập nhật lên Qdrant Cloud: {total_updated}")
    print(f" - Thời gian thực thi: {elapsed:.1f} giây ({elapsed/60:.2f} phút)")
    if failed_lessons:
        print(f" - Các bài thất bại: {failed_lessons}")
    print("=" * 72)
    return total_updated, successful_lessons, failed_lessons


if __name__ == "__main__":
    run_batch()
