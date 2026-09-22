"""
Pipeline Bóc Băng Hàng Loạt 83 Video Bài Giảng 28tech (Batch Video Ingestion Engine)
Dự án: In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Tính năng:
1. Tự động quét và sắp xếp tuần tự toàn bộ video trong data/raw_downloads/28tech_oop/
2. Tải mô hình Whisper GPU (CUDA), Dense E5, Sparse BM25 và Qdrant client 1 lần duy nhất trong RAM (Zero VRAM reload overhead)
3. Tự động kiểm tra và bỏ qua (Skip) các video đã bóc băng thành công trước đó (Idempotent & Resilient)
4. Hỗ trợ tham số --start, --limit để kiểm soát phạm vi chạy linh hoạt.
"""

import re
import sys
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import QdrantClient

from app.config import settings
from scripts.ingest_video import load_whisper_model, process_video

def parse_video_sequence(filename: str) -> int:
    """Trích xuất số thứ tự bài học từ tên tệp video."""
    match = re.match(r"^(\d+)", filename)
    if match:
        return int(match.group(1))
    return 1

def determine_course_id(seq: int, filename: str) -> str:
    """Xác định mã khóa học dựa vào số thứ tự và tiêu đề video."""
    if seq >= 53 or "Hướng Đối Tượng" in filename or "OOP" in filename:
        return "cpp-oop"
    return "cpp-core"

def is_already_ingested(video_file: Path, course_id: str, lesson_id: str) -> bool:
    """Kiểm tra xem video đã được bóc băng và sinh chunks.json trước đó chưa."""
    clean_title = re.sub(r"[^\w\-]", "_", video_file.stem)
    clean_title = re.sub(r"_+", "_", clean_title).strip("_")[:40]
    folder_name = f"{lesson_id}_{clean_title}" if clean_title else lesson_id
    
    chunks_path = PROJECT_ROOT / "data" / "transcripts" / course_id / folder_name / f"{lesson_id}_chunks.json"
    return chunks_path.exists()

def main():
    parser = argparse.ArgumentParser(description="Chạy bóc băng tự động hàng loạt video bài giảng 28tech trên GPU CUDA.")
    parser.add_argument("--dir", type=str, default="data/raw_downloads/28tech_oop", help="Thư mục chứa video tải về")
    parser.add_argument("--model", type=str, default="small", choices=["base", "small", "medium", "large-v3"], help="Kích thước mô hình Whisper")
    parser.add_argument("--start", type=int, default=1, help="Bắt đầu từ số thứ tự bài học (mặc định: 1)")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số lượng video xử lý trong lượt này")
    parser.add_argument("--force", action="store_true", help="Bắt buộc bóc băng lại kể cả khi đã có tệp chunks")
    
    args = parser.parse_args()

    videos_dir = PROJECT_ROOT / args.dir
    if not videos_dir.exists():
        print(f"❌ Lỗi: Thư mục không tồn tại tại: {videos_dir}")
        return

    all_videos = sorted(
        [f for f in videos_dir.iterdir() if f.suffix.lower() in [".webm", ".mp4", ".mkv"]],
        key=lambda f: parse_video_sequence(f.name)
    )

    if not all_videos:
        print(f"❌ Cảnh báo: Không tìm thấy file video nào trong {videos_dir}")
        return

    # Lọc theo --start
    filtered_videos = [v for v in all_videos if parse_video_sequence(v.name) >= args.start]

    # Giới hạn theo --limit nếu có
    if args.limit:
        filtered_videos = filtered_videos[:args.limit]

    total_tasks = len(filtered_videos)
    print("=" * 72)
    print(" BẮT ĐẦU CHẠY BÓC BĂNG BATCH INGESTION CHO BÀI GIẢNG 28TECH (GPU CUDA)")
    print(f" - Tổng số video cần quét: {total_tasks}/{len(all_videos)} video")
    print(f" - Mô hình Whisper: {args.model}")
    print(f" - Thiết bị tăng tốc: NVIDIA GPU CUDA (FP16)")
    print("=" * 72)

    # 1. Khởi tạo tài nguyên 1 lần duy nhất trong RAM/VRAM
    print("\n[INIT] Đang khởi tạo các mô hình nền tảng vào bộ nhớ (Zero VRAM reload)...")
    whisper_model = load_whisper_model(model_size=args.model)
    dense_model = TextEmbedding(settings.EMBEDDING_MODEL_NAME)
    sparse_model = SparseTextEmbedding(settings.SPARSE_MODEL_NAME)
    qdrant_client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=settings.QDRANT_TIMEOUT)
    print("✓ Đã khởi tạo hoàn tất toàn bộ Model & Qdrant Client!\n")

    # 2. Vòng lặp xử lý tuần tự từng video
    success_count = 0
    skipped_count = 0

    for idx, v in enumerate(filtered_videos, 1):
        seq = parse_video_sequence(v.name)
        lesson_id = f"lesson-{seq:02d}"
        course_id = determine_course_id(seq, v.name)

        print("\n" + "#" * 72)
        print(f">> [TIẾN TRÌNH {idx}/{total_tasks}] ĐANG XỬ LÝ: {v.name}")
        print(f"   Khóa học: {course_id} | Bài học: {lesson_id} (Seq: {seq})")
        print("#" * 72)

        # Kiểm tra bỏ qua nếu đã ingest
        if not args.force and is_already_ingested(v, course_id, lesson_id):
            print(f"⏩ [BỎ QUA] Bài {lesson_id} đã được bóc băng thành công trước đó. Bỏ qua.")
            skipped_count += 1
            continue

        try:
            process_video(
                video_path=str(v),
                course_id=course_id,
                lesson_id=lesson_id,
                lesson_seq=seq,
                model_size=args.model,
                clean_old_points=True,
                whisper_model=whisper_model,
                dense_model=dense_model,
                sparse_model=sparse_model,
                qdrant_client=qdrant_client
            )
            success_count += 1
            print(f"✓ Hoàn thành bài {lesson_id} ({idx}/{total_tasks})")
        except Exception as err:
            print(f"❌ Gặp lỗi khi xử lý '{v.name}': {err}")
            continue

    print("\n" + "=" * 72)
    print(f"🎉 TỔNG KẾT TIẾN TRÌNH BATCH INGESTION:")
    print(f"   - Tổng video được giao: {total_tasks}")
    print(f"   - Số video mới bóc băng thành công: {success_count}")
    print(f"   - Số video đã có sẵn và bỏ qua: {skipped_count}")
    print("=" * 72)

if __name__ == "__main__":
    main()
