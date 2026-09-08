from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.services.qdrant import get_async_qdrant_client, close_async_qdrant_client, check_qdrant_health
from app.services.embedding import get_embedding_service
from app.api import api_v1_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Quản lý vòng đời ứng dụng chuẩn Enterprise:
    1. Startup: Nạp Dual Embedding Model (E5 + BM25) vào RAM 1 lần duy nhất và warmup ONNX.
    2. Startup: Khởi tạo Connection Pool tới Qdrant Cloud.
    3. Shutdown: Đóng kết nối Qdrant Client an toàn, giải phóng tài nguyên.
    """
    # 1. Nạp và Warmup Embedding Models
    embed_service = get_embedding_service()
    embed_service.warmup()

    # 2. Khởi tạo Qdrant Client pool
    get_async_qdrant_client()

    yield

    # 3. Cleanup khi server tắt
    await close_async_qdrant_client()


app = FastAPI(
    title="In-Course Agentic RAG Copilot",
    version="1.0.0",
    description="Enterprise Socratic AI Teaching Assistant with Video Timestamp Seeking for Full-Stack Courses",
    debug=settings.APP_DEBUG,
    lifespan=lifespan
)

# CORS middleware for Next.js / React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký API v1 Routers (/api/v1/search,...)
app.include_router(api_v1_router)


@app.get("/health")
async def health_check():
    qdrant_status = await check_qdrant_health()
    return {
        "status": "healthy" if qdrant_status.get("status") == "healthy" else "degraded",
        "app_env": settings.APP_ENV,
        "qdrant": qdrant_status,
        "models": {
            "dense": settings.EMBEDDING_MODEL_NAME,
            "sparse": settings.SPARSE_MODEL_NAME
        }
    }


@app.get("/")
async def root():
    return {
        "message": "In-Course Agentic RAG Copilot API is running",
        "docs_url": "/docs"
    }
