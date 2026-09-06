from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

app = FastAPI(
    title="In-Course Agentic RAG Copilot",
    version="1.0.0",
    description="Enterprise Socratic AI Teaching Assistant with Video Timestamp Seeking for Full-Stack Courses",
    debug=settings.APP_DEBUG
)

# CORS middleware for Next.js / React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "app_env": settings.APP_ENV,
        "qdrant_target": settings.QDRANT_URL,
        "collection": settings.QDRANT_COLLECTION_NAME
    }

@app.get("/")
async def root():
    return {
        "message": "In-Course Agentic RAG Copilot API is running",
        "docs_url": "/docs"
    }
