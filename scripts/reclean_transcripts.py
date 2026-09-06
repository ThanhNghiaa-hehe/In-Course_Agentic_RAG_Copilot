import sys
import json
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ingest_video import normalize_text, time_aware_chunking
from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.config import settings

import argparse

def reclean(folder_name: str = "c++", course_id: str = "cpp-core", lesson_id: str = "lesson-01", lesson_seq: int = 1):
    sub_dir = PROJECT_ROOT / "data" / "transcripts" / folder_name
    raw_path = sub_dir / f"{folder_name}_raw_segments.json"
    if not raw_path.exists():
        print(f"Không tìm thấy file {raw_path}")
        return

    print(f"Đang đọc và chuẩn hóa lại các segments của '{folder_name}' với Stage 2 Tech Canonicalizer...")
    with open(raw_path, "r", encoding="utf-8") as f:
        raw_segments = json.load(f)

    cleaned_segments = []
    for s in raw_segments:
        c_text = normalize_text(s["text"])
        if c_text:
            cleaned_segments.append({
                "start": s["start"],
                "end": s["end"],
                "text": c_text
            })

    chunks = time_aware_chunking(cleaned_segments, min_duration=60, max_duration=90, overlap=15)
    print(f"Đã tạo lại {len(chunks)} chunks chuẩn hóa thuật ngữ.")

    # Lưu lại file report và chunks trong thư mục con
    md_path = sub_dir / f"{folder_name}_report.md"
    json_path = sub_dir / f"{folder_name}_chunks.json"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Báo cáo Trích xuất Bài giảng Video (Stage 2 Canonicalized): {folder_name}.mp4\n\n")
        f.write(f"- **Mã khóa học:** `{course_id}`\n")
        f.write(f"- **Bài học:** `{lesson_id}` (Thứ tự: {lesson_seq})\n")
        f.write(f"- **Tổng số câu phiên âm:** {len(cleaned_segments)}\n")
        f.write(f"- **Số lượng Chunks:** {len(chunks)} (Khung 60-90s)\n\n")
        f.write("---\n\n")
        f.write("## Danh sách Chunks Ngữ cảnh kèm Timestamps:\n\n")
        for i, c in enumerate(chunks, 1):
            f.write(f"### Chunk {i}: Mốc [{c['start_label']} ➔ {c['end_label']}] (sec: `{c['start_sec']}` -> `{c['end_sec']}`)\n")
            f.write(f"> {c['raw_text']}\n\n")

    print(f"Đã cập nhật lại file báo cáo: {md_path}")

    # Cập nhật lên Qdrant Cloud
    print("Đang tái sinh vector và cập nhật Qdrant Cloud...")
    dense_model = TextEmbedding("intfloat/multilingual-e5-large")
    sparse_model = SparseTextEmbedding("Qdrant/bm25")

    texts = [c["raw_text"] for c in chunks]
    dense_embeddings = list(dense_model.embed(texts))
    sparse_embeddings = list(sparse_model.embed(texts))

    qdrant = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=60.0)
    
    points = []
    for i, c in enumerate(chunks):
        sparse_val = sparse_embeddings[i]
        deterministic_key = f"{course_id}_{lesson_id}_chunk_{c['start_sec']}_{c['end_sec']}"
        deterministic_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, deterministic_key))
        point = models.PointStruct(
            id=deterministic_id,
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

    qdrant.upsert(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        points=points
    )
    print(f"HOÀN TẤT CẬP NHẬT {len(points)} POINTS LÊN QDRANT CLOUD THÀNH CÔNG!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reclean transcripts from subfolder")
    parser.add_argument("--folder", type=str, default="c++", help="Tên thư mục con trong data/transcripts")
    parser.add_argument("--course", type=str, default="cpp-core", help="Mã khóa học")
    parser.add_argument("--lesson", type=str, default="lesson-01", help="Mã bài học")
    parser.add_argument("--seq", type=int, default=1, help="Thứ tự bài học")
    args = parser.parse_args()

    reclean(
        folder_name=args.folder,
        course_id=args.course,
        lesson_id=args.lesson,
        lesson_seq=args.seq
    )
