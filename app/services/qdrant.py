import logging
from typing import Optional, Dict, Any
from qdrant_client import AsyncQdrantClient
from app.config import settings

logger = logging.getLogger("uvicorn.error")

_async_qdrant_client: Optional[AsyncQdrantClient] = None


def get_async_qdrant_client() -> AsyncQdrantClient:
    """
    Singleton Dependency Provider cho AsyncQdrantClient.
    Tái sử dụng Connection Pool bất đồng bộ, tránh khởi tạo lại TCP connection liên tục.
    Tuân thủ quy tắc kiến trúc: timeout=60.0s chống nghẽn đường truyền quốc tế.
    """
    global _async_qdrant_client
    if _async_qdrant_client is None:
        logger.info(f"[QdrantService] Khởi tạo AsyncQdrantClient kết nối tới: {settings.QDRANT_URL}")
        _async_qdrant_client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            timeout=settings.QDRANT_TIMEOUT
        )
    return _async_qdrant_client


async def close_async_qdrant_client() -> None:
    """
    Đóng kết nối Qdrant gracefully khi FastAPI shutdown (Lifespan cleanup).
    """
    global _async_qdrant_client
    if _async_qdrant_client is not None:
        logger.info("[QdrantService] Đang đóng AsyncQdrantClient connection pool...")
        await _async_qdrant_client.close()
        _async_qdrant_client = None
        logger.info("[QdrantService] Đã đóng kết nối Qdrant an toàn.")


async def check_qdrant_health() -> Dict[str, Any]:
    """
    Kiểm tra trạng thái cluster Qdrant và collection chính thức.
    """
    client = get_async_qdrant_client()
    try:
        collections_res = await client.get_collections()
        existing = [c.name for c in collections_res.collections]
        target = settings.QDRANT_COLLECTION_NAME
        is_ready = target in existing
        
        info = None
        if is_ready:
            c_info = await client.get_collection(collection_name=target)
            info = {
                "points_count": getattr(c_info, "points_count", 0),
                "status": str(c_info.status),
                "indexed_vectors_count": getattr(c_info, "indexed_vectors_count", None),
            }

        return {
            "status": "healthy" if is_ready else "collection_missing",
            "target_collection": target,
            "collection_exists": is_ready,
            "details": info
        }
    except Exception as e:
        logger.error(f"[QdrantService] Lỗi kiểm tra health Qdrant: {str(e)}")
        return {
            "status": "unhealthy",
            "target_collection": settings.QDRANT_COLLECTION_NAME,
            "error": str(e)
        }
