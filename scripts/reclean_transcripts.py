"""
Script Reclean & Tái nạp dữ liệu phiên âm Video lên Qdrant Cloud (Stage 2 Tech Canonicalizer)
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Tính năng:
- Quét toàn bộ thư mục data/transcripts/ để chuẩn hóa lại các từ khóa âm học (float, char, byte, cin, cout,...).
- Lọc triệt để ảo giác âm học Whisper (tiếng Anh vô nghĩa trên nền im lặng/nhạc).
- Tái tạo embeddings kép (Dense E5 với tiền tố 'passage: ' + Sparse BM25).
- Cập nhật idempotent lên Qdrant Cloud theo deterministic UUIDv5 (không bao giờ nhân đôi dữ liệu).
"""

import sys
import json
import uuid
import re
import argparse
from pathlib import Path
from typing import List, Dict, Any
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ingest_video import normalize_text, time_aware_chunking
from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.config import settings

_DENSE_MODEL = None
_SPARSE_MODEL = None
_QDRANT_CLIENT = None


def get_dense_model():
    global _DENSE_MODEL
    if _DENSE_MODEL is None:
        _DENSE_MODEL = TextEmbedding("intfloat/multilingual-e5-large")
    return _DENSE_MODEL


def get_sparse_model():
    global _SPARSE_MODEL
    if _SPARSE_MODEL is None:
        _SPARSE_MODEL = SparseTextEmbedding("Qdrant/bm25")
    return _SPARSE_MODEL


def get_qdrant_client():
    global _QDRANT_CLIENT
    if _QDRANT_CLIENT is None:
        _QDRANT_CLIENT = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=60.0)
    return _QDRANT_CLIENT


def parse_metadata_from_path(file_path: Path):
    """
    Suy luận course_id, lesson_id, lesson_seq từ đường dẫn tệp:
    data/transcripts/<course_id>/<folder_name>/...
    hoặc data/transcripts/<folder_name>/...
    """
    rel_parts = file_path.resolve().relative_to((PROJECT_ROOT / "data" / "transcripts").resolve()).parts
    course_id = "cpp-core"
    folder_name = rel_parts[0]
    
    if len(rel_parts) >= 2 and rel_parts[0] in ["cpp-core", "cpp-oop", "java-core", "python-core"]:
        course_id = rel_parts[0]
        folder_name = rel_parts[1]
    elif "oop" in folder_name.lower():
        course_id = "cpp-oop"

    # Trích xuất lesson_id và lesson_seq
    match_seq = re.search(r'lesson[-_]?(\d+)', folder_name, re.IGNORECASE)
    if match_seq:
        seq_num = int(match_seq.group(1))
        lesson_id = f"lesson-{seq_num:02d}"
        lesson_seq = seq_num
    else:
        # Nhận diện theo tên c++ hoặc c++_2
        if folder_name == "c++":
            lesson_id = "lesson-01"
            lesson_seq = 1
        elif folder_name in ["c++_2", "c++2"]:
            lesson_id = "lesson-02"
            lesson_seq = 2
        else:
            lesson_id = "lesson-01"
            lesson_seq = 1

    return course_id, folder_name, lesson_id, lesson_seq


def reclean_single_target(raw_or_chunk_file: Path):
    course_id, folder_name, lesson_id, lesson_seq = parse_metadata_from_path(raw_or_chunk_file)
    sub_dir = raw_or_chunk_file.parent

    print(f"\n>> Đang xử lý: {raw_or_chunk_file.name}")
    print(f"   Khóa học: {course_id} | Bài học: {lesson_id} (Seq: {lesson_seq}) | Thư mục: {folder_name}")

    with open(raw_or_chunk_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks: List[Dict[str, Any]] = []

    # Trường hợp A: Tệp chứa raw segments -> Chuẩn hóa và re-chunk
    if "raw_segments" in raw_or_chunk_file.name:
        cleaned_segments = []
        for s in data:
            c_text = normalize_text(s.get("text", ""))
            if c_text:
                cleaned_segments.append({
                    "start": s.get("start", 0),
                    "end": s.get("end", 0),
                    "text": c_text
                })
        chunks = time_aware_chunking(cleaned_segments, min_duration=60, max_duration=90, overlap=15)
        print(f"   Tạo lại {len(chunks)} chunks chuẩn hóa từ {len(cleaned_segments)} raw segments.")
    else:
        # Trường hợp B: Tệp chứa chunks đã cắt -> Chuẩn hóa lại text của từng chunk
        for c in data:
            c["raw_text"] = normalize_text(c.get("raw_text", ""))
            chunks.append(c)
        print(f"   Chuẩn hóa lại văn bản cho {len(chunks)} chunks có sẵn.")

    if not chunks:
        print("   [Bỏ qua] Không có chunks hợp lệ.")
        return 0

    # Cập nhật tệp chunks cục bộ
    json_path = sub_dir / f"{lesson_id}_chunks.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    # Sinh Vector kép & Cập nhật Qdrant Cloud
    dense_model = get_dense_model()
    sparse_model = get_sparse_model()
    qdrant = get_qdrant_client()

    dense_inputs = [f"passage: {c['raw_text']}" for c in chunks]
    sparse_inputs = [c['raw_text'] for c in chunks]
    dense_embeddings = list(dense_model.embed(dense_inputs))
    sparse_embeddings = list(sparse_model.embed(sparse_inputs))

    points = []
    for i, c in enumerate(chunks):
        sparse_val = sparse_embeddings[i]
        deterministic_key = f"{course_id}_{lesson_id}_chunk_{c['start_sec']}_{c['end_sec']}"
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, deterministic_key))
        point = models.PointStruct(
            id=point_id,
            vector={
                "dense": dense_embeddings[i].tolist(),
                "sparse": models.SparseVector(
                    indices=sparse_val.indices.tolist(),
                    values=sparse_val.values.tolist()
                )
            },
            payload={
                "course_id": course_id,
                "lesson_id": lesson_id,
                "lesson_seq": lesson_seq,
                "content_type": "video_transcript",
                "start_sec": c["start_sec"],
                "end_sec": c["end_sec"],
                "start_label": c["start_label"],
                "end_label": c["end_label"],
                "raw_text": c["raw_text"],
                "video_title": f"{folder_name}.mp4"
            }
        )
        points.append(point)

    with tqdm(total=len(points), desc=f"   Upsert {lesson_id} lên Qdrant", unit="pt", leave=False) as pbar:
        qdrant.upsert(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            points=points
        )
        pbar.update(len(points))

    print(f"   ✓ Đã cập nhật thành công {len(points)} points vào Qdrant Cloud.")
    return len(points)


def main():
    parser = argparse.ArgumentParser(description="Reclean toàn bộ transcript và tái nạp Qdrant Cloud")
    parser.add_argument("--all", action="store_true", default=True, help="Quét và reclean toàn bộ thư mục data/transcripts")
    parser.add_argument("--path", type=str, default=None, help="Đường dẫn đến file JSON cụ thể")
    args = parser.parse_args()

    transcripts_root = PROJECT_ROOT / "data" / "transcripts"
    if not transcripts_root.exists():
        print(f"[LỖI] Không tìm thấy thư mục {transcripts_root}")
        return

    print("=" * 72)
    print(" BẮT ĐẦU QUY TRÌNH RECLEAN TOÀN BỘ TRANSCRIPTS (STAGE 2 CANONICALIZER)")
    print("=" * 72)

    target_files = []
    if args.path:
        target_files.append(Path(args.path))
    else:
        # Tìm ưu tiên raw_segments
        raw_files = sorted(list(transcripts_root.rglob("*raw_segments.json")))
        if raw_files:
            target_files = raw_files
        else:
            # Fallback sang chunks.json nếu không có raw_segments
            target_files = sorted(list(transcripts_root.rglob("*chunks.json")))

    if not target_files:
        print(f"Không tìm thấy file transcript JSON nào trong {transcripts_root}")
        return

    print(f"Tìm thấy {len(target_files)} tệp transcript cần chuẩn hóa. Tiến hành nạp...")
    total_points = 0
    for tf in target_files:
        try:
            total_points += reclean_single_target(tf)
        except Exception as e:
            print(f"   [LỖI] Xử lý {tf.name}: {e}")

    print("\n" + "=" * 72)
    print(f" HOÀN TẤT RECLEAN TOÀN DIỆN! Tổng cộng {total_points} points đã cập nhật lên Qdrant Cloud.")
    print("=" * 72)


if __name__ == "__main__":
    main()
