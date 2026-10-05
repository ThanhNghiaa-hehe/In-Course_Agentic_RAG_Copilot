from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # LLM Settings (Ollama / Local / OpenAI Cloud)
    LLM_PROVIDER: str = "ollama"  # "ollama" or "openai"
    LLM_BASE_URL: str = "http://127.0.0.1:11434/v1"
    LLM_MODEL_NAME: str = "qwen2.5"
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 2048
    OPENAI_API_KEY: Optional[str] = "ollama"
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

    # Stage 6-9 Retrieval & CRAG Optimization (Chặng 2 - Modality-Aware Precision & Pareto Sufficiency)
    MODALITY_GATE_AST_THRESHOLD: float = 0.35
    MODALITY_GATE_VIDEO_THRESHOLD: float = 0.22
    MODALITY_GATE_VIDEO_EARLY_EXIT: float = 0.22  # Backward-compatibility alias for MODALITY_GATE_VIDEO_THRESHOLD
    MODALITY_GATE_VIDEO_HIGH_CONFIDENCE: float = 0.30  # AGENTS.md Invariant: Early exit khi video >= 0.30
    FUTURE_PROBE_ACTIVATION_GATE: float = 0.22
    FUTURE_PROBE_MARGIN: float = 0.12
    FUTURE_PROBE_MIN_CONFIDENCE: float = 0.25
    FUTURE_PROBE_LIMIT: int = 18
    CRAG_RRF_WEIGHT: float = 0.10
    PARETO_LOCAL_GROUNDING_THRESHOLD: float = 0.22
    PARETO_DOMINANCE_MARGIN: float = 0.20
    PARETO_DOMINANCE_FUTURE_MIN: float = 0.45
    PARETO_DOMINANCE_CODE_FUTURE_MIN: float = 0.52
    PARETO_DOMINANCE_CODE_MARGIN: float = 0.25

    # Whisper
    WHISPER_MODEL_SIZE: str = "large-v3"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"


settings = Settings()
