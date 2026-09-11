from fastapi import APIRouter
from app.api.v1.search import router as search_router
from app.api.v1.chat import router as chat_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(search_router)
api_v1_router.include_router(chat_router)

__all__ = ["api_v1_router"]
