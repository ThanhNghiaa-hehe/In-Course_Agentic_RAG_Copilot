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
    LLM_MAX_TOKENS: int = 512
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
    USE_CPU_RERANKER: bool = True  # Tách tải Re-ranker sang CPU đa luồng để triệt tiêu 100% lỗi CUBLAS crash trên RTX 2050 (4GB)
    USE_INT8_RERANKER: bool = False
    RERANK_BATCH_SIZE: int = 4  # Micro-batching kích thước 4 tránh tràn VRAM/RAM khi tính Cross-Attention
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
    MODALITY_GATE_VIDEO_HIGH_CONFIDENCE: float = 0.40  # AGENTS.md Invariant: Early exit khi video >= 0.30
    FUTURE_PROBE_ACTIVATION_GATE: float = 0.22
    FUTURE_PROBE_MARGIN: float = 0.12
    FUTURE_PROBE_MIN_CONFIDENCE: float = 0.25
    FUTURE_PROBE_LIMIT: int = 10
    RERANK_MAX_CHARS: int = 1200
    CRAG_RRF_WEIGHT: float = 0.10
    PARETO_LOCAL_GROUNDING_THRESHOLD: float = 0.22
    PARETO_MARGINAL_VIDEO_MAX: float = 0.30
    PARETO_MARGINAL_FUTURE_MIN: float = 0.30
    PARETO_MARGINAL_MARGIN: float = 0.08
    PARETO_DOMINANCE_MARGIN: float = 0.12
    PARETO_DOMINANCE_FUTURE_MIN: float = 0.45
    PARETO_DOMINANCE_CODE_FUTURE_MIN: float = 0.52
    PARETO_DOMINANCE_CODE_MARGIN: float = 0.25
    PARETO_NAV_FUTURE_MIN: float = 0.25
    PARETO_NAV_MARGIN: float = -0.15
    PARETO_INTRA_MODULE_FUTURE_MIN: float = 0.48
    PARETO_INTRA_MODULE_MARGIN: float = 0.22
    PARETO_THEORY_GROUNDING_FLOOR: float = 0.18

    # Whisper
    WHISPER_MODEL_SIZE: str = "large-v3"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"

    # Multi-Turn Memory & Context Budget Settings (LangGraph)
    SLIDING_WINDOW_TURNS: int = 4
    MAX_HISTORY_CHARS: int = 1400
    MAX_CONTEXT_CHARS: int = 1500
    SUMMARIZER_TURN_TRIGGER: int = 6
    SOFT_NUDGE_TURN_TRIGGER: int = 6

    # Multi-Turn Intent Router & Semantic Formulation Settings
    ROUTER_TOPIC_DRIFT_THRESHOLD: float = 0.32
    ROUTER_DRIFT_COHERE_THRESHOLD: float = 0.25
    ROUTER_SOCIAL_ACK_THRESHOLD: float = 0.72
    ROUTER_PURE_SOCIAL_THRESHOLD: float = 0.88
    ROUTER_SOCIAL_PURE_THRESHOLD: float = 0.88  # Backward-compatibility alias
    ROUTER_CONTEXTUAL_COURSE_MIN_PROB: float = 0.35
    ROUTER_CONTEXTUAL_COURSE_MIN: float = 0.35  # Backward-compatibility alias
    ROUTER_CONTEXTUAL_GAIN_MARGIN: float = 0.05
    ROUTER_CONTEXTUAL_NLI_MIN_CONF: float = 0.45
    ROUTER_CONFIRM_COSINE_THRESHOLD: float = 0.88
    ROUTER_CONFIRM_MARGIN: float = 0.05
    ROUTER_CONFIRM_NLI_THRESHOLD: float = 0.70

    # Telemetry Critic Rigor & Multi-Turn Intent Fidelity Settings
    CRITIC_TOPIC_INTRUSION_PENALTY: int = 50
    CRITIC_HIJACKING_PENALTY: int = 80
    MARKOV_HIJACK_PENALTY: int = 80  # Backward-compatibility alias
    CRITIC_GREETING_LOOP_PENALTY: int = 20
    GREETING_LOOP_PENALTY: int = 20  # Backward-compatibility alias
    CRITIC_MAIN_VIOLATION_PENALTY: int = 40
    CRITIC_INCLUDE_VIOLATION_PENALTY: int = 20
    CRITIC_UNVERIFIED_TS_PENALTY: int = 15
    CRITIC_MISSING_QUESTION_PENALTY: int = 10
    CRITIC_HIGH_LATENCY_PENALTY: int = 10
    CRITIC_LATENCY_THRESHOLD_MS: int = 4000
    CRITIC_MAX_SESSION_SCORE_ON_GREETING_LOOP: int = 35
    MAX_CODE_ILLUSTRATION_LINES: int = 25


settings = Settings()
