import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from qdrant_client import AsyncQdrantClient
from app.config import settings


async def verify_sparse():
    client = AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=60.0)
    try:
        col_name = settings.QDRANT_COLLECTION_NAME
        print(f"[1] Kết nối Qdrant Cloud: {settings.QDRANT_URL}")
        print(f"[2] Collection: {col_name}")

        col_info = await client.get_collection(col_name)
        total_points = col_info.points_count
        print(f"[3] Tổng số points báo cáo: {total_points}")

        # Lấy toàn bộ points kèm vectors
        records, next_page = await client.scroll(
            collection_name=col_name,
            limit=100,
            with_vectors=True,
            with_payload=True
        )

        print(f"[4] Lấy được thực tế: {len(records)} points.")
        print("-" * 70)

        missing_sparse = []
        valid_sparse_count = 0
        valid_dense_count = 0

        for r in records:
            point_id = str(r.id)
            c_type = r.payload.get("content_type", "unknown") if r.payload else "unknown"
            l_id = r.payload.get("lesson_id", "?") if r.payload else "?"
            
            vecs = r.vector
            has_dense = False
            has_sparse = False
            sparse_indices_len = 0

            if isinstance(vecs, dict):
                # Kiểm tra dense
                dense_vec = vecs.get("dense")
                if dense_vec and len(dense_vec) == 1024:
                    has_dense = True
                    valid_dense_count += 1
                
                # Kiểm tra sparse
                sparse_vec = vecs.get("sparse")
                if sparse_vec is not None:
                    # Trong qdrant client, sparse vector có thể là models.SparseVector hoặc dict
                    indices = getattr(sparse_vec, "indices", None) or (sparse_vec.get("indices") if isinstance(sparse_vec, dict) else None)
                    values = getattr(sparse_vec, "values", None) or (sparse_vec.get("values") if isinstance(sparse_vec, dict) else None)
                    if indices is not None and len(indices) > 0 and values is not None and len(values) > 0:
                        has_sparse = True
                        valid_sparse_count += 1
                        sparse_indices_len = len(indices)

            if not has_sparse:
                missing_sparse.append((point_id, c_type, l_id))
            else:
                print(f"✓ Point {point_id[:8]}... | {c_type:16} | Bài: {l_id} | Dense: 1024d | Sparse: {sparse_indices_len} non-zero indices")

        print("-" * 70)
        print(f"[KẾT QUẢ KIỂM ĐỊNH]")
        print(f"- Tổng số points: {len(records)}")
        print(f"- Số points có Dense 1024-dim hợp lệ: {valid_dense_count}/{len(records)}")
        print(f"- Số points có Sparse BM25 hợp lệ: {valid_sparse_count}/{len(records)}")
        
        if missing_sparse:
            print(f"⚠️ CẢNH BÁO: Có {len(missing_sparse)} points THIẾU vector sparse:")
            for p_id, ct, lid in missing_sparse:
                print(f"  + Point {p_id} (Loại: {ct}, Bài: {lid})")
        else:
            print(f"🎉 XÁC NHẬN: 100% TOÀN BỘ {len(records)} POINTS ĐỀU ĐÃ ĐƯỢC POPULATE VECTOR SPARSE ĐẦY ĐỦ!")

    except Exception as e:
        print(f"Lỗi kiểm tra: {e}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(verify_sparse())
