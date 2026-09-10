from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # LLM API Keys
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # Qdrant
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_COLLECTION_NAME: str = "In-Course_Agentic_RAG_Copilot"
    QDRANT_TIMEOUT: float = 60.0

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Models & Hybrid Search
    EMBEDDING_MODEL_NAME: str = "intfloat/multilingual-e5-large"
    SPARSE_MODEL_NAME: str = "Qdrant/bm25"
    RERANKER_MODEL_NAME: str = "jinaai/jina-reranker-v2-base-multilingual"
    USE_ONNX: bool = True
    MIN_SCORE_THRESHOLD: float = 0.25
    CODE_SCORE_THRESHOLD: float = 0.35
    VIDEO_SCORE_THRESHOLD: float = 0.22
    VIDEO_FALLBACK_MIN_THRESHOLD: float = 0.15
    DEFAULT_TOP_CANDIDATES: int = 10
    DEFAULT_FINAL_TOP_K: int = 3

    # Whisper
    WHISPER_MODEL_SIZE: str = "large-v3"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"


settings = Settings()
