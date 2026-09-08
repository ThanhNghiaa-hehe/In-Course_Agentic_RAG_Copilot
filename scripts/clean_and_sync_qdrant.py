import sys
import json
import uuid
from pathlib import Path
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.config import settings

def clean_and_sync():
    print("=" * 72)
    print(">> TIEN TRINH DON DEP & DONG BO DU LIEU QDRANT CLOUD")
    print(f"Target Collection: {settings.QDRANT_COLLECTION_NAME}")
    print("=" * 72)

    client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=60.0)

    # 1. Xóa toàn bộ 44 video chunks cũ/trùng lặp của Bài 1 (lesson-01)
    print("\n[BUOC 1] Xoa cac video chunks cu va trung lap cua 'lesson-01'...")
    try:
        client.delete(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            points_selector=models.Filter(
                must=[
                    models.FieldCondition(key="course_id", match=models.MatchValue(value="cpp-core")),
                    models.FieldCondition(key="lesson_id", match=models.MatchValue(value="lesson-01")),
                    models.FieldCondition(key="content_type", match=models.MatchValue(value="video_transcript"))
                ]
            )
        )
        print("v Da xoa sach toan bo video points cu cua lesson-01.")
    except Exception as e:
        print(f"! Loi khi xoa points: {e}")

    # 2. Doc file c++_chunks.json (chuan 11 chunks da qua Canonicalizer)
    chunks_file = PROJECT_ROOT / "data" / "transcripts" / "c++" / "c++_chunks.json"
    if not chunks_file.exists():
        print(f"! Khong tim thay file chunks chuan: {chunks_file}")
        return

    with open(chunks_file, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    print(f"\n[BUOC 2] Doc thanh cong {len(chunks)} video chunks chuan tu file local:")
    print(f"Path: {chunks_file}")

    # 3. Sinh Vector kep (E5 Dense voi tien to 'passage: ' + Sparse BM25)
    print("\n[BUOC 3] Sinh Vector kep (multilingual-e5-large + BM25)...")
    dense_model = TextEmbedding("intfloat/multilingual-e5-large")
    sparse_model = SparseTextEmbedding("Qdrant/bm25")

    dense_inputs = [f"passage: {c['raw_text']}" for c in chunks]
    sparse_inputs = [c['raw_text'] for c in chunks]

    dense_embeddings = list(dense_model.embed(dense_inputs))
    sparse_embeddings = list(sparse_model.embed(sparse_inputs))

    # 4. Dong goi Points tat dinh UUIDv5 va Nap lai len Qdrant Cloud
    print("\n[BUOC 4] Nap 11 video points chuan len Qdrant Cloud...")
    points = []
    course_id = "cpp-core"
    lesson_id = "lesson-01"
    lesson_seq = 1
    video_title = "c++.mp4"

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
                "video_title": video_title
            }
        )
        points.append(point)

    with tqdm(total=len(points), desc=">> Nap Video Points", unit="pt") as pbar:
        client.upsert(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            points=points
        )
        pbar.update(len(points))

    # 5. Kiem tra va Bao cao Tong so diem sau don dep
    print("\n[BUOC 5] Kiem tra tong so diem sau khi dong bo:")
    records, _ = client.scroll(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        limit=100,
        with_payload=True,
        with_vectors=False
    )
    
    l1_video = sum(1 for p in records if p.payload.get("lesson_id") == "lesson-01" and p.payload.get("content_type") == "video_transcript")
    l1_code = sum(1 for p in records if p.payload.get("lesson_id") == "lesson-01" and p.payload.get("content_type") == "code_ast")
    l2_video = sum(1 for p in records if p.payload.get("lesson_id") == "lesson-02" and p.payload.get("content_type") == "video_transcript")
    l2_code = sum(1 for p in records if p.payload.get("lesson_id") == "lesson-02" and p.payload.get("content_type") == "code_ast")
    total = len(records)

    print("-" * 72)
    print(f" - Bai 1 (lesson-01): {l1_video} video chunks + {l1_code} code AST chunks = {l1_video + l1_code} points")
    print(f" - Bai 2 (lesson-02): {l2_video} video chunks + {l2_code} code AST chunks = {l2_video + l2_code} points")
    print(f" >> TONG SO DIEM TREN CLUSTER: {total} POINTS (Tieu chuan: 27 points)")
    print("-" * 72)
    if total == 27:
        print("v CLUSTER DA DAT TRANG THAI CHUAN XAC 100% (27/27 POINTS)!")
    else:
        print(f"! So diem hien tai la {total} points.")
    print("=" * 72 + "\n")

if __name__ == "__main__":
    clean_and_sync()
