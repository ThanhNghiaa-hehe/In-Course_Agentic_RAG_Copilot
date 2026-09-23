import sys
from pathlib import Path
from typing import Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.config import settings

def inspect_collection() -> None:
    """Kiểm toán chi tiết số lượng vector và phân bổ payload trong Qdrant Cloud."""
    print("=" * 72)
    print(f">> KIỂM TOÁN TẬP DỮ LIỆU VECTOR: {settings.QDRANT_COLLECTION_NAME}")
    print("=" * 72)

    client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=60.0)
    info = client.get_collection(settings.QDRANT_COLLECTION_NAME)

    # 1. Đếm theo content_type
    video_count = client.count(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        count_filter=models.Filter(must=[models.FieldCondition(key="content_type", match=models.MatchValue(value="video_transcript"))])
    ).count

    code_count = client.count(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        count_filter=models.Filter(must=[models.FieldCondition(key="content_type", match=models.MatchValue(value="code_ast"))])
    ).count

    print(f"Tổng số Points trong Collection: {info.points_count:,}")
    print(f" - Video Transcripts (Kho tri thức video): {video_count:,} chunks")
    print(f" - Code AST Chunks (Mã nguồn cú pháp):   {code_count:,} chunks")
    print("-" * 72)

    # 2. Chi tiết các bài học Code AST
    print(">> PHÂN BỔ MÃ NGUỒN CÚ PHÁP (CODE AST):")
    code_points = client.scroll(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        scroll_filter=models.Filter(must=[models.FieldCondition(key="content_type", match=models.MatchValue(value="code_ast"))]),
        limit=200,
        with_payload=True
    )[0]

    if not code_points:
        print("   (Chưa có chunk Code AST nào được nạp)")
    else:
        lesson_stats: Dict[str, Dict[str, int]] = {}
        for p in code_points:
            c_id = str(p.payload.get("course_id", "unknown"))
            l_id = str(p.payload.get("lesson_id", "unknown"))
            if c_id not in lesson_stats:
                lesson_stats[c_id] = {}
            lesson_stats[c_id][l_id] = lesson_stats[c_id].get(l_id, 0) + 1

        for c_id, lessons in sorted(lesson_stats.items()):
            print(f"   [{c_id}] Tổng: {sum(lessons.values())} chunks")
            for l_id, cnt in sorted(lessons.items()):
                print(f"      + {l_id:<12}: {cnt:>2} chunks")

    print("=" * 72)

if __name__ == "__main__":
    inspect_collection()
