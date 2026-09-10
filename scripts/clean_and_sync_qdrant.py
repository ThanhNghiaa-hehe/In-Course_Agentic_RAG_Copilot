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
    print(">> TIEN TRINH DON DEP & DONG BO DU LIEU TOAN DIEN QDRANT CLOUD")
    print(f"Target Collection: {settings.QDRANT_COLLECTION_NAME}")
    print("=" * 72)

    client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=60.0)

    # 1. Xóa toàn bộ video chunks cũ của cả Bài 1 (lesson-01) và Bài 2 (lesson-02)
    print("\n[BUOC 1] Xoa sach cac video chunks cu de nap lai chuan E5 (passage:)...")
    for l_id in ["lesson-01", "lesson-02"]:
        try:
            client.delete(
                collection_name=settings.QDRANT_COLLECTION_NAME,
                points_selector=models.Filter(
                    must=[
                        models.FieldCondition(key="course_id", match=models.MatchValue(value="cpp-core")),
                        models.FieldCondition(key="lesson_id", match=models.MatchValue(value=l_id)),
                        models.FieldCondition(key="content_type", match=models.MatchValue(value="video_transcript"))
                    ]
                )
            )
            print(f"v Da xoa sach toan bo video points cu cua {l_id}.")
        except Exception as e:
            print(f"! Loi khi xoa points cua {l_id}: {e}")

    # 2. Định nghĩa danh sách các bài học video cần nạp chuẩn
    lessons = [
        {
            "course_id": "cpp-core",
            "lesson_id": "lesson-01",
            "lesson_seq": 1,
            "folder": "c++",
            "file_name": "c++_chunks.json",
            "video_title": "c++.mp4"
        },
        {
            "course_id": "cpp-core",
            "lesson_id": "lesson-02",
            "lesson_seq": 2,
            "folder": "c++_2",
            "file_name": "c++_2_chunks.json",
            "video_title": "c++_2.mp4"
        }
    ]

    dense_model = TextEmbedding("intfloat/multilingual-e5-large")
    sparse_model = SparseTextEmbedding("Qdrant/bm25")

    all_video_points = []

    for item in lessons:
        chunks_file = PROJECT_ROOT / "data" / "transcripts" / item["folder"] / item["file_name"]
        if not chunks_file.exists():
            print(f"! Khong tim thay file chunks: {chunks_file}")
            continue

        with open(chunks_file, "r", encoding="utf-8") as f:
            chunks = json.load(f)

        print(f"\n[BUOC 2] Xu ly {len(chunks)} video chunks cua {item['lesson_id']} tu: {chunks_file.name}")

        # BẮT BUỘC: Thêm tiền tố 'passage: ' cho mô hình multilingual-e5-large
        dense_inputs = [f"passage: {c['raw_text']}" for c in chunks]
        sparse_inputs = [c['raw_text'] for c in chunks]

        print(f" - Sinh E5 Dense vectors (co tien to 'passage: ') va Sparse BM25...")
        dense_embeddings = list(dense_model.embed(dense_inputs))
        sparse_embeddings = list(sparse_model.embed(sparse_inputs))

        for i, c in enumerate(chunks):
            sparse_val = sparse_embeddings[i]
            deterministic_key = f"{item['course_id']}_{item['lesson_id']}_chunk_{c['start_sec']}_{c['end_sec']}"
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
                    "course_id": item["course_id"],
                    "lesson_id": item["lesson_id"],
                    "lesson_seq": item["lesson_seq"],
                    "content_type": "video_transcript",
                    "start_sec": c["start_sec"],
                    "end_sec": c["end_sec"],
                    "start_label": c["start_label"],
                    "end_label": c["end_label"],
                    "raw_text": c["raw_text"],
                    "video_title": item["video_title"]
                }
            )
            all_video_points.append(point)

    # 3. Nạp toàn bộ video points lên Qdrant Cloud
    print(f"\n[BUOC 3] Nap tong cong {len(all_video_points)} video points chuan E5 len Qdrant Cloud...")
    with tqdm(total=len(all_video_points), desc=">> Nap Video Points", unit="pt") as pbar:
        client.upsert(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            points=all_video_points
        )
        pbar.update(len(all_video_points))

    # 4. Kiểm tra và Báo cáo Tổng số điểm sau đồng bộ
    print("\n[BUOC 4] Kiem tra tong so diem tren cluster sau khi dong bo:")
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
