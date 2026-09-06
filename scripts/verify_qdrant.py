import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
from qdrant_client import AsyncQdrantClient
from app.config import settings

async def verify():
    masked_key = (settings.QDRANT_API_KEY[:6] + "..." + settings.QDRANT_API_KEY[-4:]) if settings.QDRANT_API_KEY else "NONE"
    print(f"Cluster URL: {settings.QDRANT_URL}")
    print(f"API Key: {masked_key}")
    print(f"Target Collection: {settings.QDRANT_COLLECTION_NAME}")

    client = AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=60.0)
    try:
        collections_resp = await client.get_collections()
        collection_names = [c.name for c in collections_resp.collections]
        print(f"\n[STATUS] Connected to Qdrant Cloud successfully!")
        print(f"[COLLECTIONS] Existing collections: {collection_names}")

        if settings.QDRANT_COLLECTION_NAME in collection_names:
            col_info = await client.get_collection(settings.QDRANT_COLLECTION_NAME)
            print(f"[COLLECTION INFO]")
            print(f" - Status: {col_info.status}")
            print(f" - Dense Vector: {col_info.config.params.vectors}")
            print(f" - Sparse Vector: {col_info.config.params.sparse_vectors}")
            print(f" - Points Count: {col_info.points_count}")
        else:
            print(f"Notice: Collection '{settings.QDRANT_COLLECTION_NAME}' does not exist on cluster yet.")
    except Exception as e:
        print(f"CONNECTION ERROR: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(verify())
