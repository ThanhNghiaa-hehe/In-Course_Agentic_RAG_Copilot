import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from app.config import settings

COLLECTION_NAME = settings.QDRANT_COLLECTION_NAME

async def init_qdrant_schema():
    print(f"Connecting to Qdrant at: {settings.QDRANT_URL}")
    # Đặt timeout=60.0 để tránh bị ConnectTimeout khi kết nối cluster quốc tế
    client = AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=60.0)
    
    try:
        collections = await client.get_collections()
        existing_names = [c.name for c in collections.collections]
        
        if COLLECTION_NAME not in existing_names:
            print(f"Creating collection '{COLLECTION_NAME}' with Dense + Sparse vectors...")
            await client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config={
                    "dense": models.VectorParams(
                        size=1024,
                        distance=models.Distance.COSINE,
                        hnsw_config=models.HnswConfigDiff(
                            m=16,
                            ef_construct=128
                        )
                    )
                },
                sparse_vectors_config={
                    "sparse": models.SparseVectorParams(
                        index=models.SparseIndexParams(
                            on_disk=False
                        )
                    )
                }
            )
            print(f"Successfully created collection: {COLLECTION_NAME}")
        else:
            print(f"Collection '{COLLECTION_NAME}' already exists on cluster.")

        # Tạo Payload Indexes để hỗ trợ Pre-filtering siêu tốc
        payload_indexes = [
            ("course_id", models.PayloadSchemaType.KEYWORD),
            ("lesson_id", models.PayloadSchemaType.KEYWORD),
            ("lesson_seq", models.PayloadSchemaType.INTEGER),
            ("content_type", models.PayloadSchemaType.KEYWORD),
            ("start_sec", models.PayloadSchemaType.INTEGER),
            ("code_scope", models.PayloadSchemaType.KEYWORD)
        ]
        
        for field_name, schema_type in payload_indexes:
            try:
                await client.create_payload_index(
                    collection_name=COLLECTION_NAME,
                    field_name=field_name,
                    field_schema=schema_type
                )
                print(f"Payload index verified: {field_name} ({schema_type})")
            except Exception as idx_err:
                print(f"Payload index notice for {field_name}: {repr(idx_err)}")

        print("\n=== Qdrant Schema & Collection Initialization Complete 100% ===")
    except Exception as e:
        print(f"Failed to connect to Qdrant or initialize schema: {repr(e)}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(init_qdrant_schema())
