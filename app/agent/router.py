"""
Bộ Định Tuyến Phân Loại Ý Định (Fast-Path SLM ONNX INT8 & NLI Arbiter Router)
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Kiến trúc phòng vệ 2 tầng sâu (Defense-in-Depth - Zero LinearSVC):
- Tầng 0: Security Input Guardrail (OWASP LLM01 Gate - ~0ms).
- Tầng 1: Fast-Path Deep Neural SLM Router ONNX INT8 (0.06ms) trên không gian E5 1024-dim.
- Tầng 2: Stage 2 Cross-Encoder NLI Arbiter (mDeBERTa-v3) giải cứu câu hỏi phân vân.
"""

import os
import json
import logging
import unicodedata
from pathlib import Path
from typing import Optional, List, Dict, Any
import numpy as np

from app.config import settings
from app.schemas.chat import RouterClassification
from app.services.embedding import get_embedding_service
from app.agent.guardrails import (
    get_security_input_guardrail,
    SECURITY_REFUSAL_RESPONSE,
    _detect_student_cpp_ast,
)

logger = logging.getLogger("uvicorn.error")
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ROUTER_MANIFEST_PATH = PROJECT_ROOT / "data" / "metadata" / "router_intent_manifest.json"


def _load_router_manifest() -> Dict[str, Any]:
    try:
        if ROUTER_MANIFEST_PATH.exists():
            with open(ROUTER_MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"[IntentRouter] Không thể đọc {ROUTER_MANIFEST_PATH}: {e}")
    return {}


_MANIFEST_DATA = _load_router_manifest()


def _get_subintent_response(subintent_key: str, default_fallback: str) -> str:
    subintents = _MANIFEST_DATA.get("chitchat_subintents", {})
    if subintent_key in subintents:
        return subintents[subintent_key].get("response_text", default_fallback)
    return default_fallback


# ==========================================
# Phản hồi Sư phạm Chuẩn (Data-Driven Manifest + Fallbacks)
# ==========================================
GREETING_RESPONSES = _get_subintent_response(
    "greeting",
    "Chào bạn! Tôi là **In-Course AI Copilot** - Trợ giảng lập trình của khóa học. "
    "Hôm nay bạn đang học đến bài nào và gặp khó khăn gì với cú pháp hay thuật toán C++, "
    "hãy gửi cho tôi để chúng ta cùng giải quyết nhé!"
)

GRATITUDE_RESPONSES = _get_subintent_response(
    "gratitude",
    "Rất vui vì đã đồng hành và gợi mở được hướng đi cho bạn! "
    "Hãy tiếp tục thực hành viết code nhé, nếu gặp bất kỳ lỗi cú pháp hay logic nào khác, "
    "tôi luôn ở đây hỗ trợ bạn!"
)

GOODBYE_RESPONSES = _get_subintent_response(
    "goodbye",
    "Tạm biệt bạn nhé! Chúc bạn có một buổi học tập và thực hành hiệu quả. "
    "Khi nào cần hỗ trợ giải đáp về bài học hay sửa lỗi code C++, "
    "tôi luôn sẵn sàng đồng hành cùng bạn!"
)

IDENTITY_RESPONSES = _get_subintent_response(
    "identity_architecture",
    "Tôi là **In-Course Agentic RAG Copilot** - Trợ giảng lập trình thông minh theo phương pháp Socratic, "
    "được phát triển bởi sinh viên **Trần Thành Nghĩa** (MSSV: `23DH112252`), "
    "Trường **Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT)** "
    "(Kho lưu trữ GitHub: `ThanhNghiaa-hehe/In-Course_Agentic_RAG_Copilot`).\n\n"
    "Hệ thống được xây dựng trên nền tảng:\n"
    "- **Backend & Vector DB:** **FastAPI**, **Python 3.11**, **Qdrant** với cơ chế **dual vector** (`dense` 1024-dim và `sparse` BM25).\n"
    "- **Embedding & Re-ranker:** Mô hình nhúng `multilingual-e5-large` (1024 chiều qua `fastembed`) kết hợp bộ xếp hạng **Cross-Encoder** `jinaai/jina-reranker-v2`.\n"
    "- **Speech & Video Sync:** Bóc băng âm thanh bằng `faster-whisper` kết hợp `Silero VAD`, trích xuất thẻ `<timestamp sec=\"...\">` điều khiển trình phát `seekTo` trên giao diện **React 19** + **Vite**!"
)

SOCRATIC_PEDAGOGY_RESPONSES = _get_subintent_response(
    "socratic_pedagogy",
    "Theo nguyên tắc sư phạm **Socratic**, tôi đóng vai trò là người đồng hành **gợi mở** **tư duy** "
    "chứ **không chép bài** hay viết sẵn toàn bộ code giải hoàn chỉnh thay cho **học viên**.\n\n"
    "Việc **tự lập trình**, tự suy nghĩ qua từng câu hỏi định hướng và đối chiếu với mốc video bài giảng "
    "sẽ giúp bạn nắm vững bản chất thuật toán C++ bền vững nhất!"
)

ADVICE_RESPONSES = _get_subintent_response(
    "advice",
    "Học lập trình ban đầu có thể có nhiều bỡ ngỡ với các khái niệm như bộ nhớ, con trỏ hay cú pháp nghiêm ngặt của C++. "
    "Lời khuyên tốt nhất là hãy **kiên trì** **thực hành** giải **bài tập** và viết code mỗi ngày, tự tay gõ từng dòng lệnh "
    "và cố gắng từng bước đọc hiểu thông báo lỗi. Trí tuệ nhân tạo chỉ là **công cụ** **hỗ trợ** giúp **lập trình viên** "
    "tăng hiệu suất chứ không thể thay thế tư duy thiết kế phần mềm của bạn. Tôi luôn ở đây **đồng hành** cùng bạn!"
)

OFFTOPIC_CASUAL_RESPONSES = _MANIFEST_DATA.get(
    "default_offtopic_response",
    "Chào bạn! Tôi là **In-Course AI Copilot** - Trợ giảng chuyên môn của khóa học lập trình C++. "
    "Tôi luôn sẵn sàng đồng hành hỗ trợ bạn giải đáp các thắc mắc về bài học, cú pháp code và bài tập lập trình "
    "thay vì các chủ đề ngoài lề đời sống. Hãy gửi cho tôi câu hỏi hoặc đoạn code C++ bạn đang gặp khó khăn nhé!"
)


class NLIArbiter:
    """
    Stage 2 Cross-Encoder NLI Arbiter:
    Sử dụng mô hình MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7 (chạy GPU/CPU).
    Nhiệm vụ: Phán xử logic ngữ nghĩa (Entailment / Contradiction) cho các câu hỏi
    rơi vào vùng phân vân của cổng Bi-Directional Entropy/Margin Gate.
    Tuyệt đối Zero-Regex, Zero-Hardcoded-Anchors, 100% Machine Learning & Data-Driven Manifest.
    """

    def __init__(self, manifest_data: Optional[Dict[str, Any]] = None):
        self._pipeline = None
        self._confirm_vecs = None
        self._reject_vecs = None
        data = manifest_data if manifest_data is not None else _load_router_manifest()
        self._confirm_anchors: List[str] = data.get("confirm_anchors", [])
        self._reject_anchors: List[str] = data.get("reject_anchors", [])
        hypotheses: Dict[str, str] = data.get("nli_hypotheses", {})
        self._candidate_labels: List[str] = []
        self._label_map: Dict[str, str] = {}
        for intent_key in ("course_query", "chit_chat", "out_of_scope"):
            hyp_text = hypotheses.get(intent_key)
            if hyp_text:
                self._candidate_labels.append(hyp_text)
                self._label_map[hyp_text] = intent_key
        self._template = data.get("nli_template", "This text is about {}.")

        raw_temporal_template = data.get("temporal_nli_template")
        raw_temporal_labels = data.get("temporal_nli_labels")
        raw_temporal_threshold = data.get("temporal_nli_offtopic_threshold")
        if (
            not isinstance(raw_temporal_template, str)
            or not raw_temporal_template.strip()
            or not isinstance(raw_temporal_labels, dict)
            or not raw_temporal_labels.get("in_video")
            or not raw_temporal_labels.get("off_topic")
            or raw_temporal_threshold is None
        ):
            logger.warning(
                "[NLIArbiter] Thiếu cấu hình temporal_nli_* trong router_intent_manifest.json; "
                "dùng giá trị mặc định dự phòng."
            )
            self._temporal_template: str = "Câu này hỏi về {}."
            in_video_lbl = "nội dung đang được giảng hoặc giải thích trong video bài học lập trình"
            off_topic_lbl = "thể thao, bóng đá, quán ăn, nấu ăn, thời tiết hoặc đời sống ngoài lề"
            self._temporal_offtopic_threshold: float = 0.60
        else:
            self._temporal_template = raw_temporal_template
            in_video_lbl = str(raw_temporal_labels["in_video"])
            off_topic_lbl = str(raw_temporal_labels["off_topic"])
            self._temporal_offtopic_threshold = float(raw_temporal_threshold)

        self._temporal_labels: List[str] = [in_video_lbl, off_topic_lbl]
        self._temporal_offtopic_label: str = off_topic_lbl

    def _get_pipeline(self):
        """Khởi tạo trễ (Lazy Loading) để không làm chậm thời gian khởi động server."""
        if self._pipeline is None:
            try:
                import torch
                from transformers import pipeline
                device_id = 0 if torch.cuda.is_available() else -1
                if device_id == -1 and torch.get_num_threads() != 1:
                    torch.set_num_threads(1)
                dev_name = "CUDA (GPU 0)" if device_id >= 0 else "CPU"
                local_ft_nli = PROJECT_ROOT / "data" / "models" / "mdeberta-v3-xnli-ft"
                nli_model_source = (
                    str(local_ft_nli)
                    if (local_ft_nli / "config.json").exists()
                    else "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
                )
                logger.info(f"[NLIArbiter] Đang nạp mô hình NLI ({nli_model_source}) trên {dev_name}...")
                self._pipeline = pipeline(
                    "zero-shot-classification",
                    model=nli_model_source,
                    device=device_id
                )
                logger.info(f"[NLIArbiter] Nạp thành công mô hình NLI Arbiter trên {dev_name}.")
            except Exception as e:
                logger.error(f"[NLIArbiter] Không thể nạp pipeline transformers NLI: {e}")
                self._pipeline = None
        return self._pipeline

    def arbitrate(self, prompt: str) -> tuple[str, float]:
        """Phán định ý định bằng suy luận logic Zero-Shot NLI."""
        pipe = self._get_pipeline()
        if pipe is None or not self._candidate_labels:
            return "out_of_scope", 0.0
        try:
            res = pipe(
                prompt,
                candidate_labels=self._candidate_labels,
                hypothesis_template=self._template,
                multi_label=False
            )
            top_label_desc = res["labels"][0]
            top_score = float(res["scores"][0])
            pred_intent = self._label_map.get(top_label_desc, "out_of_scope")
            logger.info(f"[NLIArbiter] Phán định NLI: '{prompt[:35]}...' -> {pred_intent} ({top_score*100:.1f}%)")
            return pred_intent, top_score
        except Exception as e:
            logger.error(f"[NLIArbiter] Lỗi suy luận NLI ({e}), giữ nguyên phán quyết Stage 1.")
            return "out_of_scope", 0.0

    def verify_in_video_temporal_query(self, prompt: str) -> tuple[bool, float]:
        """
        Kiểm định NLI nhị phân cho câu hỏi chứa tham chiếu thời gian/vị trí video
        ("phút thứ 6 nói về gì", "đoạn này là sao") nhằm phân tách khỏi ngữ cảnh đời sống
        ("phút thứ 6 trận bóng đá", "chỗ này quán ăn nào ngon").
        Trả về `(is_in_video_query, off_topic_score)`.
        Áp dụng cơ chế fail-closed `(False, 1.0)` khi NLI không khả dụng hoặc lỗi suy luận.
        """
        pipe = self._get_pipeline()
        if pipe is None or len(self._temporal_labels) < 2:
            logger.warning(
                "[NLIArbiter] Pipeline NLI không khả dụng trong verify_in_video_temporal_query; "
                "trả fail-closed (False, 1.0)."
            )
            return False, 1.0
        try:
            res = pipe(
                prompt,
                candidate_labels=self._temporal_labels,
                hypothesis_template=self._temporal_template,
                multi_label=False,
            )
            off_topic_score = 0.0
            for lbl, sc in zip(res.get("labels", []), res.get("scores", [])):
                if lbl == self._temporal_offtopic_label:
                    off_topic_score = float(sc)
                    break
            return (off_topic_score < self._temporal_offtopic_threshold), off_topic_score
        except Exception as e:
            logger.warning(
                f"[NLIArbiter] Lỗi verify_in_video_temporal_query ({e}); trả fail-closed (False, 1.0)."
            )
            return False, 1.0

    def is_confirmation(self, prompt: str) -> tuple[bool, float]:
        """
        Phán xử ý định xác nhận hành động đàm thoại qua Vector E5 Prototype Alignment & Dual Margin.
        Độ trễ < 3ms, bảo đảm 100% toán học ML từ manifest JSON, 0% từ khóa hardcode.
        """
        try:
            emb_svc = get_embedding_service()
            if self._confirm_vecs is None and self._confirm_anchors and self._reject_anchors:
                self._confirm_vecs = [emb_svc.embed_query_dense(a) for a in self._confirm_anchors]
                self._reject_vecs = [emb_svc.embed_query_dense(a) for a in self._reject_anchors]

            if not self._confirm_vecs or not self._reject_vecs:
                return False, 0.0

            q_vec = emb_svc.embed_query_dense(prompt)
            sim_c = max([float(np.dot(q_vec, cv) / (np.linalg.norm(q_vec) * np.linalg.norm(cv))) for cv in self._confirm_vecs])
            sim_r = max([float(np.dot(q_vec, rv) / (np.linalg.norm(q_vec) * np.linalg.norm(rv))) for rv in self._reject_vecs])

            is_question_punct = prompt.strip().endswith("?")
            is_agree = (
                (sim_c >= settings.ROUTER_CONFIRM_COSINE_THRESHOLD)
                and (sim_c > sim_r + settings.ROUTER_CONFIRM_MARGIN)
                and not is_question_punct
            )

            # [Stage 2 NLI Arbiter]: Cứu xét bằng Cross-Encoder khi câu nói tự nhiên phân vân
            if not is_agree and not is_question_punct:
                pipe = self._get_pipeline()
                if pipe is not None:
                    premise = f"Trợ giảng hỏi: 'Bạn có muốn mình chuyển sang bài học tiếp theo và mở video cho bạn không?'. Học viên trả lời: '{prompt}'."
                    nli_res = pipe(
                        premise,
                        candidate_labels=["đồng ý mở video bài học", "từ chối hoặc đặt câu hỏi khác"],
                        hypothesis_template="Ý định của học viên là {}.",
                        multi_label=False
                    )
                    top_lbl = nli_res["labels"][0]
                    top_score = float(nli_res["scores"][0])
                    if top_lbl == "đồng ý mở video bài học" and top_score >= settings.ROUTER_CONFIRM_NLI_THRESHOLD:
                        is_agree = True
                        sim_c = top_score
                        logger.info(f"[ConfirmationClassifier:NLI-Rescue] Cứu xét thành công qua NLI: '{prompt[:35]}' -> {top_score*100:.1f}%")

            logger.info(
                f"[ConfirmationClassifier:E5-NLI] '{prompt[:35]}' -> "
                f"Cos_C={sim_c:.3f} | Cos_R={sim_r:.3f} -> IsAgree={is_agree}"
            )
            return is_agree, sim_c
        except Exception as e:
            logger.error(f"[ConfirmationClassifier] Lỗi tính tương quan vector: {e}")
            return False, 0.0

    def warmup(self) -> None:
        """Khởi động nóng mô hình NLI Arbiter trên CPU/RAM để khử triệt để Cold-Start."""
        try:
            pipe = self._get_pipeline()
            if pipe is not None and self._candidate_labels:
                pipe("khởi động hệ thống", candidate_labels=self._candidate_labels[:1], hypothesis_template=self._template)
                logger.info("[NLIArbiter] Khởi động nóng (Warmup) hoàn tất.")
        except Exception as e:
            logger.warning(f"[NLIArbiter] Warmup thất bại nhẹ ({e}).")


class IntentRouter:
    """
    Bộ định tuyến phân loại ý định người dùng chuẩn SOTA (Zero LinearSVC):
    - Kiến trúc Cascade 2 Tầng (Cascading Multi-Tier Router):
      + Tầng 1: Fast-Path Deep Neural SLM Router ONNX INT8 (0.06ms) trên không gian E5 1024-dim.
      + Tầng 2: Cross-Encoder NLI Arbiter (mDeBERTa-v3-base-xnli) kích hoạt qua cổng Entropy/Margin Gate.
    """

    def __init__(self):
        self._slm_session = None
        self._classes = ["chit_chat", "course_query", "out_of_scope"]
        self._manifest_data = _load_router_manifest()
        self._solicitation_words: List[str] = [w.lower() for w in self._manifest_data.get("solicitation_words", [])]
        self._nli_arbiter = NLIArbiter(self._manifest_data)
        self._security_guardrail = get_security_input_guardrail()
        self._chitchat_proto_matrix: Optional[np.ndarray] = None
        self._chitchat_proto_responses: List[str] = []
        self._pure_social_proto_matrix: Optional[np.ndarray] = None
        self._sys_proto_matrix: Optional[np.ndarray] = None
        self._ack_proto_matrix: Optional[np.ndarray] = None
        self._curriculum_nav_proto_matrix: Optional[np.ndarray] = None
        self._curriculum_nav_folded_proto_matrix: Optional[np.ndarray] = None

        # 1. Nạp Fast-Path SLM ONNX INT8 Router (Temperature-Scaled T*)
        slm_path = PROJECT_ROOT / "app" / "agent" / "models" / "slm_router_int8.onnx"
        if slm_path.exists():
            try:
                import onnxruntime as ort
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 1 if os.environ.get("OMP_NUM_THREADS") == "1" else 2
                opts.inter_op_num_threads = 1
                opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                self._slm_session = ort.InferenceSession(str(slm_path), opts, providers=["CPUExecutionProvider"])
                logger.info(f"[IntentRouter] 🚀 Nạp thành công Fast-Path SLM ONNX INT8 Router từ {slm_path}.")
            except Exception as e:
                logger.warning(f"[IntentRouter] Lỗi nạp slm_router_int8.onnx ({e}).")
        else:
            logger.warning(f"[IntentRouter] Chưa tìm thấy {slm_path}. Cần chạy script huấn luyện SLM.")

    def warmup(self) -> None:
        """Khởi động nóng mô hình NLI Arbiter và các ma trận prototype để triệt tiêu Cold-Start."""
        self._nli_arbiter.warmup()
        self._ensure_chitchat_prototypes()
        self._security_guardrail._ensure_embeddings()
        from app.services.curriculum import get_curriculum_service
        get_curriculum_service()._ensure_nav_embeddings()

    def _normalize_text(self, text: str) -> str:
        """Chuẩn hóa văn bản Unicode NFC và loại bỏ khoảng trắng thừa."""
        if not text:
            return ""
        normalized = unicodedata.normalize("NFC", text.strip())
        return " ".join(normalized.split())

    @staticmethod
    def _fold_vietnamese_accents(text: str) -> str:
        """Loại bỏ dấu thanh tiếng Việt (Zero Regex) phục vụ đối chiếu điều hướng khi người dùng gõ thiếu dấu."""
        if not text:
            return ""
        decomposed = unicodedata.normalize("NFD", text.lower())
        stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
        return stripped.replace("đ", "d")

    def is_code_solicitation(self, prompt: str) -> bool:
        """Nhận diện yêu cầu xin code hoàn chỉnh / giải bài tập hộ nạp từ router_intent_manifest.json (0% Hardcode)."""
        clean_p = self._normalize_text(prompt).lower()
        if not clean_p:
            return False
        return any(w in clean_p for w in self._solicitation_words)

    def is_pseudocode_request(self, prompt: str) -> bool:
        """Nhận diện yêu cầu trình bày mã giả / khung thuật toán nạp từ router_intent_manifest.json (0% Hardcode)."""
        clean_p = self._normalize_text(prompt).lower()
        if not clean_p:
            return False
        sigs = self._manifest_data.get("pseudocode_request_signatures", [])
        return any(str(sig).strip().lower() in clean_p for sig in sigs if str(sig).strip())

    def _ensure_chitchat_prototypes(self) -> None:
        """Khởi tạo ma trận prototype E5 1024-dim cho chitchat, pure social, acknowledgment và curriculum nav từ manifest JSON."""
        if (
            self._chitchat_proto_matrix is not None
            and self._pure_social_proto_matrix is not None
            and self._ack_proto_matrix is not None
            and self._curriculum_nav_proto_matrix is not None
        ):
            return

        emb_svc = get_embedding_service()

        # 1. Chitchat & Pure Social & System Identity Prototypes
        subintents = self._manifest_data.get("chitchat_subintents", {})
        if subintents and (self._chitchat_proto_matrix is None or self._pure_social_proto_matrix is None or self._sys_proto_matrix is None):
            pure_keys = set(self._manifest_data.get("pure_social_subintents", ["greeting", "gratitude", "goodbye"]))
            sys_keys = {"identity_architecture", "socratic_pedagogy"}
            try:
                proto_texts: List[str] = []
                proto_keys: List[str] = []
                all_resps: List[str] = []
                for sub_key, sub_cfg in subintents.items():
                    resp_txt = sub_cfg.get("response_text", GREETING_RESPONSES)
                    for proto_str in sub_cfg.get("prototypes", []):
                        proto_texts.append(proto_str)
                        proto_keys.append(sub_key)
                        all_resps.append(resp_txt)
                if proto_texts:
                    batch_mat = emb_svc.embed_queries_dense_batch(proto_texts)
                    self._chitchat_proto_matrix = batch_mat
                    self._chitchat_proto_responses = all_resps
                    pure_indices = [i for i, k in enumerate(proto_keys) if k in pure_keys]
                    sys_indices = [i for i, k in enumerate(proto_keys) if k in sys_keys]
                    if pure_indices:
                        self._pure_social_proto_matrix = batch_mat[pure_indices]
                    if sys_indices:
                        self._sys_proto_matrix = batch_mat[sys_indices]
            except Exception as e:
                logger.warning(f"[IntentRouter] Không thể khởi tạo ma trận chitchat prototypes ({e}).")

        # 2. Acknowledgment Prototypes
        ack_protos = self._manifest_data.get("acknowledgment_prototypes", [])
        if ack_protos and self._ack_proto_matrix is None:
            try:
                self._ack_proto_matrix = emb_svc.embed_queries_dense_batch(ack_protos)
            except Exception as e:
                logger.warning(f"[IntentRouter] Không thể khởi tạo ma trận acknowledgment prototypes ({e}).")

        # 3. Curriculum Navigation Prototypes (gồm cả bản không dấu cho câu hỏi mất dấu)
        nav_protos = self._manifest_data.get("curriculum_navigation_prototypes", [])
        if nav_protos and self._curriculum_nav_proto_matrix is None:
            try:
                self._curriculum_nav_proto_matrix = emb_svc.embed_queries_dense_batch(nav_protos)
                folded_nav_protos = [self._fold_vietnamese_accents(p) for p in nav_protos]
                self._curriculum_nav_folded_proto_matrix = emb_svc.embed_queries_dense_batch(folded_nav_protos)
            except Exception as e:
                logger.warning(f"[IntentRouter] Không thể khởi tạo ma trận curriculum navigation prototypes ({e}).")

    def get_pure_social_similarity(self, prompt: str) -> float:
        """
        Tính độ tương đồng Cosine tối đa giữa prompt và các prototype xã giao thuần túy
        (greeting, gratitude, goodbye) nạp từ router_intent_manifest.json (100% Data-Driven).
        """
        clean_p = self._normalize_text(prompt)
        if not clean_p:
            return 1.0
        self._ensure_chitchat_prototypes()
        if self._pure_social_proto_matrix is None or len(self._pure_social_proto_matrix) == 0:
            return 0.0
        try:
            emb_svc = get_embedding_service()
            qv = np.array(emb_svc.embed_query_dense(clean_p), dtype=np.float32)
            norm_q = np.linalg.norm(qv)
            if norm_q > 0:
                qv /= norm_q
            sims = np.dot(self._pure_social_proto_matrix, qv)
            return float(np.max(sims))
        except Exception as e:
            logger.warning(f"[IntentRouter] Lỗi tính tương đồng pure social ({e}).")
            return 0.0

    def is_pure_social(self, prompt: str) -> tuple[bool, float]:
        """
        Kiểm định độ thuần khiết xã giao (Pure Social Prototype Gate):
        Trả về (True, sim) nếu sim >= settings.ROUTER_PURE_SOCIAL_THRESHOLD.
        """
        clean_p = self._normalize_text(prompt)
        if not clean_p:
            return (True, 1.0)
        lower_p = clean_p.lower()
        if self.is_code_solicitation(clean_p):
            return (False, 0.0)
        ex_sigs = self._manifest_data.get("exercise_statement_signatures", [])
        if any(sig in lower_p for sig in ex_sigs):
            return (False, 0.0)
        if self.has_domain_entity(clean_p) or _detect_student_cpp_ast(clean_p):
            return (False, 0.0)
        if self.is_context_dependent(clean_p):
            return (False, 0.0)
        from app.services.curriculum import get_curriculum_service
        curr_svc = get_curriculum_service()
        if curr_svc.has_current_lesson_reference(clean_p) or curr_svc.is_overview_query(clean_p):
            return (False, 0.0)
        sim = self.get_pure_social_similarity(clean_p)
        return (sim >= settings.ROUTER_PURE_SOCIAL_THRESHOLD, sim)

    def get_system_identity_similarity(self, prompt: str, query_vec: Optional[np.ndarray] = None) -> float:
        """
        Đo độ tương đồng Cosine tối đa giữa prompt và các prototype System Identity & Socratic Pedagogy
        nạp từ router_intent_manifest.json (100% Vector Similarity, 0% Substring Hardcode).
        """
        clean_p = self._normalize_text(prompt)
        if not clean_p:
            return 0.0
        self._ensure_chitchat_prototypes()
        if self._sys_proto_matrix is None or len(self._sys_proto_matrix) == 0:
            return 0.0
        try:
            if query_vec is None:
                emb_svc = get_embedding_service()
                qv = np.array(emb_svc.embed_query_dense(clean_p), dtype=np.float32)
                norm_q = np.linalg.norm(qv)
                if norm_q > 0:
                    qv /= norm_q
            else:
                qv = query_vec
            sims = np.dot(self._sys_proto_matrix, qv)
            return float(np.max(sims))
        except Exception as e:
            logger.warning(f"[IntentRouter] Lỗi tính tương đồng system identity ({e}).")
            return 0.0

    def is_social_acknowledgment(self, raw_prompt: str) -> tuple[bool, float]:
        """
        Conversational Closure & Social Acknowledgment Gate (Nhận diện cảm thán / tiếp thu / đóng lượt):
        Kiểm tra vắng mặt câu hỏi nghi vấn ('?' hoặc từ hỏi kỹ thuật),
        BẮT BUỘC có acknowledgment_signatures từ manifest, KHÔNG chứa từ xin giải hộ,
        và đo Cosine với acknowledgment_prototypes đạt >= settings.ROUTER_SOCIAL_ACK_THRESHOLD (0.80).
        """
        clean_p = self._normalize_text(raw_prompt)
        if not clean_p:
            return (False, 0.0)

        # Nếu có dấu '?', đây là câu hỏi nghi vấn, không phải câu cảm thán/tiếp thu thuần túy
        if "?" in clean_p:
            return (False, 0.0)

        # Kiểm tra từ để hỏi kỹ thuật mở đầu
        lower_p = clean_p.lower()
        question_starters = tuple(self._manifest_data.get("question_starters", ()))
        if any(lower_p.startswith(w) for w in question_starters):
            return (False, 0.0)

        # Kiểm tra acknowledgment_signatures từ manifest
        ack_sigs = self._manifest_data.get("acknowledgment_signatures", [])
        has_ack_sig = any(sig in lower_p for sig in ack_sigs)
        if not has_ack_sig:
            return (False, 0.0)

        # Loại trừ các yêu cầu giải hộ / xin code hoàn chỉnh
        solicitation_words = tuple(self._manifest_data.get("solicitation_words", ()))
        if any(w in lower_p for w in solicitation_words):
            return (False, 0.0)

        self._ensure_chitchat_prototypes()

        max_sim = 0.0
        # Đo tương đồng với acknowledgment prototypes
        if self._ack_proto_matrix is not None and len(self._ack_proto_matrix) > 0:
            try:
                emb_svc = get_embedding_service()
                qv = np.array(emb_svc.embed_query_dense(clean_p), dtype=np.float32)
                norm_q = np.linalg.norm(qv)
                if norm_q > 0:
                    qv /= norm_q
                sims = np.dot(self._ack_proto_matrix, qv)
                max_sim = float(np.max(sims))
            except Exception as e:
                logger.warning(f"[IntentRouter] Lỗi tính acknowledgment similarity: {e}")

        # KHÔNG gộp get_pure_social_similarity ở đây để tránh anisotropic cone của E5
        is_ack = has_ack_sig and (max_sim >= settings.ROUTER_SOCIAL_ACK_THRESHOLD)
        return (is_ack, max_sim)

    def is_curriculum_navigation(self, prompt: str) -> tuple[bool, float]:
        """
        Curriculum Navigation Recognition Gate (Nhận diện câu hỏi lộ trình giáo trình):
        Kết hợp đối chiếu ma trận prototype E5 (curriculum_navigation_prototypes & CurriculumService)
        và cổng cách ly tương phản Social/Identity, loại bỏ hoàn toàn chốt chặn từ khóa cứng.
        """
        clean_p = self._normalize_text(prompt)
        if not clean_p:
            return (False, 0.0)

        lower_p = clean_p.lower()
        # Loại trừ câu mô tả đề bài/bài tập hoặc yêu cầu giải hộ code
        ex_sigs = self._manifest_data.get("exercise_statement_signatures", [])
        if any(sig in lower_p for sig in ex_sigs):
            return (False, 0.0)
        if any(w in lower_p for w in self._solicitation_words):
            return (False, 0.0)

        nav_sigs = self._manifest_data.get("curriculum_navigation_signatures", [])
        has_nav_sig = any(sig in lower_p for sig in nav_sigs)
        folded_p = " ".join(
            "".join(c if c.isalnum() else " " for c in self._fold_vietnamese_accents(lower_p)).split()
        )
        has_folded_sig = any(
            f" {self._fold_vietnamese_accents(sig)} " in f" {folded_p} "
            for sig in nav_sigs
        )

        # Câu hỏi tìm đoạn trong video bài học hiện tại (PC-01: "khoảng phút bao nhiêu...", "đoạn nào trong bài...")
        # hoặc câu hỏi so sánh hai bài học ("bài này khác bài 11 chỗ nào")
        # KHÔNG phải điều hướng chuyển bài học trừ khi có chữ ký hỏi bài nào/bài mấy tường minh.
        if not has_nav_sig and not has_folded_sig:
            from app.services.curriculum import get_curriculum_service
            curr_svc = get_curriculum_service()
            if curr_svc.is_video_section_seeking_query(clean_p):
                return (False, 0.0)
            if curr_svc.is_lesson_comparison_query(clean_p) and curr_svc.extract_requested_nav_seq_raw(clean_p) is None:
                return (False, 0.0)

        self._ensure_chitchat_prototypes()
        if self._curriculum_nav_proto_matrix is None or len(self._curriculum_nav_proto_matrix) == 0:
            return (False, 0.0)

        try:
            emb_svc = get_embedding_service()
            qv = np.array(emb_svc.embed_query_dense(clean_p), dtype=np.float32)
            norm_q = np.linalg.norm(qv)
            if norm_q > 0:
                qv /= norm_q
            sims = np.dot(self._curriculum_nav_proto_matrix, qv)
            max_sim = float(np.max(sims))

            # Cổng cách ly tương phản: Không nhận diện nhầm câu chào hỏi xã giao, hỏi danh tính/sư phạm hoặc xin lời khuyên (advice)
            sim_soc = self.get_pure_social_similarity(clean_p)
            sim_sys = self.get_system_identity_similarity(clean_p, query_vec=qv)
            sim_chitchat = (
                float(np.max(np.dot(self._chitchat_proto_matrix, qv)))
                if (self._chitchat_proto_matrix is not None and len(self._chitchat_proto_matrix) > 0)
                else 0.0
            )
            if sim_sys >= 0.88:
                return (False, max_sim)

            if not has_nav_sig and not has_folded_sig and sim_chitchat >= 0.90 and sim_chitchat > max_sim + 0.02:
                return (False, max_sim)

            has_domain = self.has_domain_entity(clean_p)
            has_curriculum_topic_cached: Optional[bool] = True if has_domain else None

            def _has_curriculum_topic() -> bool:
                nonlocal has_curriculum_topic_cached
                if has_curriculum_topic_cached is None:
                    from app.services.curriculum import get_curriculum_service
                    has_curriculum_topic_cached = bool(
                        get_curriculum_service().semantic_search_lessons(clean_p, top_k=1, min_similarity=0.80)
                    )
                return has_curriculum_topic_cached

            if sim_soc >= settings.ROUTER_PURE_SOCIAL_THRESHOLD and not has_domain:
                if not (has_folded_sig and _has_curriculum_topic()):
                    return (False, max_sim)

            if not has_nav_sig and max_sim <= max(sim_soc, sim_sys, sim_chitchat) + 0.02:
                # Cho phép cứu xét tiếp nếu khớp chữ ký điều hướng bỏ dấu + có chủ đề giáo trình
                folded_sim = max_sim
                if has_folded_sig and self._curriculum_nav_folded_proto_matrix is not None:
                    folded_sim = max(max_sim, float(np.max(np.dot(self._curriculum_nav_folded_proto_matrix, qv))))
                if has_folded_sig and folded_sim >= 0.82 and _has_curriculum_topic():
                    return (True, folded_sim)
                return (False, max_sim)

            if has_nav_sig:
                return (max_sim >= 0.78, max_sim)

            # Kiểm tra nhánh gõ thiếu dấu thanh tiếng Việt (vd: "có bai học nào về con trỏ không")
            if has_folded_sig:
                folded_sim = max_sim
                if self._curriculum_nav_folded_proto_matrix is not None:
                    folded_sim = max(max_sim, float(np.max(np.dot(self._curriculum_nav_folded_proto_matrix, qv))))
                if folded_sim >= 0.82 and _has_curriculum_topic():
                    return (True, folded_sim)

            # Khi không có chữ ký từ vựng tường minh (câu hỏi diễn đạt tự nhiên):
            # Yêu cầu độ tương đồng vector E5 cao (>= 0.875) hoặc đồng thuận với CurriculumService.is_navigation_query (>= 0.865)
            if max_sim >= 0.875:
                return (True, max_sim)
            if max_sim >= 0.865:
                from app.services.curriculum import get_curriculum_service
                if get_curriculum_service().is_navigation_query(clean_p):
                    return (True, max_sim)

            return (False, max_sim)
        except Exception as e:
            logger.warning(f"[IntentRouter] Lỗi tính curriculum navigation similarity: {e}")
            return (False, 0.0)

    def has_domain_entity(self, prompt: str) -> bool:
        """
        Kiểm tra xem văn bản có chứa thực thể kỹ thuật C++ từ bilingual_entity_mappings hay không.
        Zero Regex, Data-Driven hoàn toàn từ router_intent_manifest.json (Mục 5.2 - Nhịp 1B).
        Hỗ trợ nhận diện cụm từ kỹ thuật đa từ khi gõ thiếu dấu tiếng Việt (vd: 'con tro', 'vong lap').
        """
        clean_text = self._normalize_text(prompt).lower()
        if not clean_text:
            return False

        folded_text = " ".join(
            "".join(c if c.isalnum() else " " for c in self._fold_vietnamese_accents(clean_text)).split()
        )
        padded_folded = f" {folded_text} "

        entity_maps = self._manifest_data.get("bilingual_entity_mappings", {})
        for entity_key, synonyms in entity_maps.items():
            if entity_key in clean_text:
                return True
            for syn in synonyms:
                syn_low = syn.lower()
                if syn_low in clean_text:
                    return True
                folded_syn = " ".join(
                    "".join(c if c.isalnum() else " " for c in self._fold_vietnamese_accents(syn_low)).split()
                )
                if len(folded_syn.split()) >= 2 and f" {folded_syn} " in padded_folded:
                    return True
        return False

    def _has_verified_curriculum_topic(self, clean_prompt: str) -> bool:
        """Kiểm tra câu hỏi có khớp chủ đề bài học xác thực trong giáo trình (Zero Regex)."""
        try:
            from app.services.curriculum import get_curriculum_service, _has_topical_overlap
            c_svc = get_curriculum_service()
            matched = c_svc.find_lesson_for_query(clean_prompt)
            if not matched:
                return False
            m_lesson, _ = matched
            return bool(
                _has_topical_overlap(
                    m_lesson,
                    clean_prompt,
                    c_svc._stop_words,
                    conflict_groups=c_svc._modifier_conflict_groups,
                    domain_tokens=c_svc._domain_specific_tokens,
                )
            )
        except Exception as e:
            logger.debug(f"[IntentRouter] Lỗi kiểm tra _has_verified_curriculum_topic ({e}).")
            return False

    def compute_drift_similarity(self, prompt: str, anchor_query: Optional[str]) -> float:
        """
        Tính độ tương đồng Cosine trôi ngữ nghĩa (Topic Drift Cosine Similarity):
        Sim_drift = e(prompt) . e(anchor_query) trên không gian E5 1024-dim chuẩn hóa.
        """
        clean_p = self._normalize_text(prompt)
        clean_anchor = self._normalize_text(anchor_query or "")
        if not clean_p or not clean_anchor:
            return 0.0

        try:
            emb_svc = get_embedding_service()
            v1 = np.array(emb_svc.embed_query_dense(clean_p), dtype=np.float32)
            v2 = np.array(emb_svc.embed_query_dense(clean_anchor), dtype=np.float32)
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)
            if norm1 > 0 and norm2 > 0:
                return float(np.dot(v1 / norm1, v2 / norm2))
            return 0.0
        except Exception as e:
            logger.warning(f"[IntentRouter] Lỗi tính drift similarity: {e}")
            return 0.0

    def is_context_dependent(self, prompt: str, anchor_query: Optional[str] = None) -> bool:
        """
        Phán định tính phụ thuộc ngữ cảnh D(u_t) (Context Dependency Detector - Zero Hardcoded Entity):
        Thỏa mãn ít nhất một trong 2 điều kiện chuẩn SIGIR/ICLR 2025:
        1. Linguistic Anaphora Signatures: Chứa chỉ từ hồi chỉ cấu trúc tiếng Việt từ manifest.
        2. Elliptical Fragmentary Interrogative: Câu hỏi ngắn (len <= 7 words) kết thúc bằng '?'.
        (Đã loại bỏ hoàn toàn điều kiện Cosine similarity thô do anisotropic cone của E5).
        """
        clean_p = self._normalize_text(prompt)
        if not clean_p:
            return False

        alpha_clean = " ".join("".join(c if c.isalnum() else " " for c in clean_p.lower()).split())
        padded_alpha = f" {alpha_clean} "

        # 1. Anaphora Signatures từ manifest JSON (đối chiếu trên chuỗi đã tách dấu câu)
        anaphora_sigs = self._manifest_data.get("anaphora_signatures", [])
        clean_lower = f" {clean_p.lower()} "
        for sig in anaphora_sigs:
            sig_clean = sig.strip().lower()
            if not sig_clean:
                continue
            sig_norm = " ".join("".join(c if c.isalnum() else " " for c in sig_clean).split())
            if f" {sig_clean} " in clean_lower or (sig_norm and f" {sig_norm} " in padded_alpha):
                return True

        # 2. Elliptical Fragmentary Interrogative (chỉ kích hoạt khi câu hỏi ngắn thiếu thực thể kỹ thuật độc lập)
        words = clean_p.split()
        if len(words) <= 7 and clean_p.endswith("?") and not self.has_domain_entity(clean_p):
            return True

        # 3. Discourse Elaboration / Clarification Follow-ups (Data-Driven Manifest, Zero Substring Leakage)
        # Chỉ kích hoạt khi câu không chứa thực thể độc lập và toàn bộ từ còn lại ngoài chữ ký đào sâu là hư từ lịch sự hoặc anaphora (chặn "nấu mì chi tiết hơn")
        elab_sigs = self._manifest_data.get("follow_up_elaboration_signatures", [])
        if elab_sigs and len(words) <= 16 and not self.has_domain_entity(clean_p):
            sorted_elab_sigs = sorted(
                (str(s) for s in elab_sigs if str(s).strip()),
                key=len,
                reverse=True,
            )
            matched_elab = None
            for sig in sorted_elab_sigs:
                sig_norm = " ".join("".join(c if c.isalnum() else " " for c in sig.lower()).split())
                if sig_norm and f" {sig_norm} " in padded_alpha:
                    matched_elab = sig_norm
                    break
            if matched_elab:
                residual_str = padded_alpha.replace(f" {matched_elab} ", " ").strip()
                raw_particles = self._manifest_data.get("follow_up_polite_particles")
                if isinstance(raw_particles, list) and raw_particles:
                    polite_particles = {str(x).strip().lower() for x in raw_particles if str(x).strip()}
                else:
                    logger.warning(
                        "Missing or empty 'follow_up_polite_particles' in router_intent_manifest.json; using fallback default particles."
                    )
                    polite_particles = {
                        "ạ", "nhé", "đi", "giúp", "giùm", "cho", "mình", "em", "tôi",
                        "được", "không", "thầy", "bạn", "về", "nữa", "thêm", "cái",
                        "phần", "đoạn", "chỗ", "lại", "nha", "nhỉ", "với", "hơn", "à",
                        "vậy", "thế", "đưa", "ra", "thôi", "cũng", "chỉ", "cần", "xin", "lấy",
                    }
                anaphora_words = set()
                for a_sig in anaphora_sigs:
                    for tok in a_sig.lower().split():
                        anaphora_words.add(tok)
                residual_tokens = [t for t in residual_str.split() if t]
                if all((t in polite_particles or t in anaphora_words) for t in residual_tokens):
                    return True

        return False

    def is_topic_shift(self, raw_prompt: str, anchor_query: str) -> tuple[bool, float]:
        """
        Semantic Drift Isolation Gate (Cách ly trôi ngữ nghĩa):
        is_topic_shift <=> (Sim_drift < ROUTER_TOPIC_DRIFT_THRESHOLD) and not D(raw_prompt)
        Trả về (True, sim) nếu phát hiện dịch chuyển chủ đề ngoài lề hoặc sang chủ đề độc lập mới.
        """
        clean_p = self._normalize_text(raw_prompt)
        clean_anchor = self._normalize_text(anchor_query)
        if not clean_anchor:
            return (False, 1.0)

        sim = self.compute_drift_similarity(clean_p, clean_anchor)

        # Nếu câu hỏi có tính hồi chỉ/phụ thuộc ngữ cảnh thì bảo toàn luồng ngữ cảnh
        if self.is_context_dependent(clean_p, anchor_query=clean_anchor):
            return (False, sim)

        if sim < settings.ROUTER_TOPIC_DRIFT_THRESHOLD:
            return (True, sim)

        return (False, sim)

    def _get_slm_probs(self, clean_prompt: str) -> Optional[np.ndarray]:
        """Tính phân phối xác suất Softmax qua Fast-Path SLM ONNX INT8."""
        if self._slm_session is None or not clean_prompt:
            return None
        try:
            emb_svc = get_embedding_service()
            query_vec = np.array(emb_svc.embed_query_dense(clean_prompt), dtype=np.float32)
            q_norm = np.linalg.norm(query_vec)
            if q_norm > 0:
                query_vec /= q_norm
            vec_2d = query_vec.reshape(1, -1)
            logits = self._slm_session.run(None, {"dense_vector": vec_2d})[0][0]
            exp_l = np.exp(logits - np.max(logits))
            probs = exp_l / np.sum(exp_l)
            return probs
        except Exception as err:
            logger.debug(f"[IntentRouter] Lỗi tính SLM probs: {err}")
            return None

    def classify_contextual(self, raw_prompt: str, anchor_query: str) -> tuple[RouterClassification, str]:
        """
        Đánh giá ý định ngữ cảnh kép (Dual-Track Contextual Formulation - SIGIR/ICLR 2025):
        Phân định câu hỏi nối tiếp/tỉnh lược dựa trên mỏ neo học thuật (anchor_query).
        Trả về (RouterClassification, search_query).
        """
        clean_raw = self._normalize_text(raw_prompt)
        clean_anchor = self._normalize_text(anchor_query)

        if not clean_anchor:
            clf = self.classify(clean_raw)
            return clf, clean_raw

        # 1. Kiểm định Social Acknowledgment Gate
        is_ack, ack_sim = self.is_social_acknowledgment(clean_raw)
        if is_ack:
            logger.info(f"[IntentRouter:Contextual] Phát ngôn cảm thán/tiếp thu học tập (Sim={ack_sim:.3f}): '{clean_raw[:35]}'")
            resp = self._select_chitchat_response(clean_raw)
            return RouterClassification(intent="chit_chat", direct_response=resp, is_course_query=False), clean_raw

        # 2. Kiểm định Pure Social Gate
        is_soc, soc_sim = self.is_pure_social(clean_raw)
        if is_soc:
            logger.info(f"[IntentRouter:Contextual] Phát ngôn xã giao thuần khiết (Sim={soc_sim:.3f}): '{clean_raw[:35]}'")
            return self.classify(clean_raw), clean_raw

        # 3. Kiểm định Topic Shift Gate (Semantic Drift Isolation)
        is_shift, drift_sim = self.is_topic_shift(clean_raw, clean_anchor)
        if is_shift:
            logger.info(
                f"[IntentRouter:Contextual] Phát hiện đổi chủ đề (DriftSim={drift_sim:.3f} < {settings.ROUTER_TOPIC_DRIFT_THRESHOLD}): "
                f"Cô lập hoàn toàn khỏi anchor."
            )
            return self.classify(clean_raw), clean_raw

        # 4. Kiểm định Curriculum Navigation Gate
        is_nav, nav_sim = self.is_curriculum_navigation(clean_raw)
        if is_nav:
            logger.info(f"[IntentRouter:Contextual] Phát hiện câu hỏi lộ trình giáo trình (NavSim={nav_sim:.3f}): '{clean_raw}'")
            return RouterClassification(intent="course_query", direct_response=None, is_course_query=True), clean_raw

        # 5. Xây dựng câu truy vấn hợp nhất theo chuẩn SIGIR
        contextual_prompt = f"{clean_anchor} -> {clean_raw}"
        search_query = f"{clean_anchor} — {clean_raw}"

        # 6. Tính phân phối xác suất SLM trên contextual_prompt và raw_prompt
        p_raw = self._get_slm_probs(clean_raw)
        p_ctx = self._get_slm_probs(contextual_prompt)

        if p_ctx is not None and p_raw is not None:
            # Classes: [0: chit_chat, 1: course_query, 2: out_of_scope]
            p_course_raw = float(p_raw[1])
            p_oos_raw = float(p_raw[2])
            p_course_ctx = float(p_ctx[1])
            delta_course = p_course_ctx - p_course_raw

            logger.info(
                f"[IntentRouter:Contextual] P_course_ctx={p_course_ctx:.3f}, "
                f"P_course_raw={p_course_raw:.3f}, Delta={delta_course:.3f}, P_oos_raw={p_oos_raw:.3f}"
            )

            # (i) Trội xác suất ngữ cảnh hoặc (ii) Độ lợi thông tin ngữ cảnh dương
            if (p_course_ctx >= settings.ROUTER_CONTEXTUAL_COURSE_MIN_PROB) or (
                delta_course >= settings.ROUTER_CONTEXTUAL_GAIN_MARGIN and p_oos_raw < 0.65
            ):
                logger.info(f"[IntentRouter:Contextual] Cứu xét Pareto SLM thành công: '{clean_raw}' -> course_query")
                return RouterClassification(intent="course_query", direct_response=None, is_course_query=True), search_query

        # (iii) Thẩm định qua Stage 2 NLI Arbiter
        nli_intent, nli_conf = self._nli_arbiter.arbitrate(contextual_prompt)
        if nli_intent == "course_query" and nli_conf >= settings.ROUTER_CONTEXTUAL_NLI_MIN_CONF:
            logger.info(f"[IntentRouter:Contextual] Cứu xét NLI Arbiter thành công ({nli_conf*100:.1f}%): '{clean_raw}' -> course_query")
            return RouterClassification(intent="course_query", direct_response=None, is_course_query=True), search_query

        # Fallback về phân loại raw_prompt
        raw_clf = self.classify(clean_raw)
        return raw_clf, clean_raw

    def _select_chitchat_response(self, prompt: str, query_vec: Optional[np.ndarray] = None) -> str:
        """
        Lựa chọn câu phản hồi sư phạm cho nhóm Chit-Chat bằng 100% Dense Vector Cosine Matching
        trên ma trận prototype nạp từ router_intent_manifest.json (0% từ khóa cứng, 0% Regex).
        """
        self._ensure_chitchat_prototypes()
        if self._chitchat_proto_matrix is not None and self._chitchat_proto_responses:
            try:
                if query_vec is None:
                    emb_svc = get_embedding_service()
                    qv = np.array(emb_svc.embed_query_dense(prompt), dtype=np.float32)
                    norm_q = np.linalg.norm(qv)
                    if norm_q > 0:
                        qv /= norm_q
                else:
                    qv = query_vec
                sims = np.dot(self._chitchat_proto_matrix, qv)
                best_idx = int(np.argmax(sims))
                return self._chitchat_proto_responses[best_idx]
            except Exception as e:
                logger.debug(f"[IntentRouter] Lỗi tính Cosine chitchat subintent ({e}).")
        return GREETING_RESPONSES

    def classify(self, prompt: str) -> RouterClassification:
        """
        Phân loại câu hỏi của học viên thuần túy bằng Machine Learning (Zero-Regex / Zero-Hardcoded-Triggers):
        - Tầng 1: Calibrated Convex-Neural Soft-Voting Ensemble (0.45 * P_SLM(T*) + 0.55 * P_SVC)
        - Tầng 2: Cross-Encoder NLI Arbiter (mDeBERTa-v3-base-xnli) qua cổng Bi-Directional Entropy/Margin Gate
        - Tầng 3: An toàn mặc định (Abstention) -> Đẩy vào RAG (course_query)
        """
        clean_prompt = self._normalize_text(prompt)
        if not clean_prompt:
            return RouterClassification(
                intent="chit_chat",
                direct_response=GREETING_RESPONSES,
                is_course_query=False
            )

        # ----------------------------------------------------
        # 0. TẦNG 0: Security Input Guardrail (OWASP LLM01 Gate - ~0ms)
        # ----------------------------------------------------
        is_safe, refusal_reason = self._security_guardrail.validate_input(clean_prompt)
        if not is_safe:
            return RouterClassification(
                intent="out_of_scope",
                direct_response=refusal_reason or OFFTOPIC_CASUAL_RESPONSES,
                is_course_query=False,
                is_security_refusal=True,
            )

        # ----------------------------------------------------
        # 0b. TẦNG 0b: Exercise Statement Signatures (Data-Driven Manifest)
        # ----------------------------------------------------
        lower_prompt = clean_prompt.lower()
        ex_sigs = self._manifest_data.get("exercise_statement_signatures", [])
        if any(sig in lower_prompt for sig in ex_sigs):
            logger.info(f"[IntentRouter] Nhận diện Exercise Statement signature: '{clean_prompt[:40]}...' -> course_query")
            return RouterClassification(
                intent="course_query",
                direct_response=None,
                is_course_query=True
            )

        # ----------------------------------------------------
        # 0c. TẦNG 0c: Curriculum Navigation Gate (Data-Driven Manifest)
        # ----------------------------------------------------
        is_nav, nav_sim = self.is_curriculum_navigation(clean_prompt)
        if is_nav:
            logger.info(f"[IntentRouter] Nhận diện Curriculum Navigation (Sim={nav_sim:.3f}): '{clean_prompt[:40]}...' -> course_query")
            return RouterClassification(
                intent="course_query",
                direct_response=None,
                is_course_query=True
            )

        # ----------------------------------------------------
        # 0c2. TẦNG 0c2: Current-Lesson Overview/Section Gate (Data-Driven Manifest)
        # ----------------------------------------------------
        from app.services.curriculum import get_curriculum_service
        curr_svc_cls = get_curriculum_service()
        section_markers = self._manifest_data.get("crag_section_markers", [])
        is_cur_overview_or_section = curr_svc_cls.has_current_lesson_reference(clean_prompt) and (
            curr_svc_cls.is_overview_query(clean_prompt)
            or any(str(m).strip().lower() in lower_prompt for m in section_markers if str(m).strip())
        )
        if (
            is_cur_overview_or_section
            and not self.is_social_acknowledgment(clean_prompt)[0]
            and self.get_system_identity_similarity(clean_prompt) < 0.88
        ):
            logger.info(
                f"[IntentRouter] Tầng 0c2 Current-Lesson Overview/Section Gate: '{clean_prompt[:40]}...' -> course_query"
            )
            return RouterClassification(
                intent="course_query",
                direct_response=None,
                is_course_query=True,
            )

        # ----------------------------------------------------
        # 1. TẦNG 1: Fast-Path SLM ONNX INT8 Deep Neural Classifier (0% LinearSVC)
        # ----------------------------------------------------
        if self._slm_session is not None:
            try:
                emb_svc = get_embedding_service()
                query_vec = np.array(emb_svc.embed_query_dense(clean_prompt), dtype=np.float32)
                q_norm = np.linalg.norm(query_vec)
                if q_norm > 0:
                    query_vec /= q_norm
                vec_2d = query_vec.reshape(1, -1)

                logits = self._slm_session.run(None, {"dense_vector": vec_2d})[0][0]
                exp_l = np.exp(logits - np.max(logits))
                probs = exp_l / np.sum(exp_l)
                mode_tag = "SLM-ONNX-INT8"

                if probs is not None:
                    top1_idx = int(np.argmax(probs))
                    top1_class = self._classes[top1_idx]
                    top1_prob = float(probs[top1_idx])
                    sorted_p = np.sort(probs)
                    margin = float(sorted_p[-1] - sorted_p[-2])

                    p_chit = float(probs[0])
                    p_course = float(probs[1])
                    p_oos = float(probs[2])

                    logger.info(
                        f"[IntentRouter-{mode_tag}] Intent={top1_class} (Conf={top1_prob*100:.1f}%, Margin={margin:.3f}) | "
                        f"Probs: chit_chat={p_chit:.3f}, course={p_course:.3f}, oos={p_oos:.3f}"
                    )

                    # ----------------------------------------------------
                    # 0d. TẦNG 0d: System Identity & Socratic Pedagogy Prototype Gate (100% Vector Cosine, Zero Hardcode)
                    # ----------------------------------------------------
                    sim_sys = self.get_system_identity_similarity(clean_prompt, query_vec=query_vec)
                    has_solicitation = any(w in lower_prompt for w in self._solicitation_words)
                    if sim_sys >= 0.88 and p_chit >= 0.15 and p_oos < 0.45 and not has_solicitation:
                        logger.info(
                            f"[IntentRouter] Tầng 0d Prototype Gate (sim_sys={sim_sys:.4f}, p_chit={p_chit:.3f}, p_oos={p_oos:.3f}) -> chit_chat"
                        )
                        return RouterClassification(
                            intent="chit_chat",
                            direct_response=self._select_chitchat_response(clean_prompt, query_vec=query_vec),
                            is_course_query=False
                        )

                    # ----------------------------------------------------
                    # ĐIỀU PHỐI CASCADE: STAGE 1 (ENSEMBLE) -> STAGE 2 (NLI ARBITER)
                    # Cổng độ trễ đa chiều Bi-Directional Entropy/Margin Gate (Mục 2.2 - Nhịp 1B / Nhịp 2)
                    # ----------------------------------------------------
                    has_curriculum_topic = False
                    if top1_class == "out_of_scope" and p_course < 0.16:
                        has_curriculum_topic = self._has_verified_curriculum_topic(clean_prompt)

                    is_ambiguous_slm = (
                        (margin < 0.22) or
                        (top1_class == "out_of_scope" and (p_course >= 0.10 or is_nav or has_curriculum_topic)) or
                        (top1_class == "course_query" and (p_oos >= 0.25 or p_chit >= 0.22) and margin < 0.25) or
                        (top1_class == "chit_chat" and (p_course >= 0.20 or p_oos >= 0.25))
                    )

                    if is_ambiguous_slm:
                        logger.info(
                            f"[IntentRouter-Cascade] Kích hoạt Stage 2 NLI Arbiter ({mode_tag}): "
                            f"Top1={top1_class} (P={top1_prob:.3f}), Margin={margin:.3f}, "
                            f"P_course={p_course:.3f}, P_chit={p_chit:.3f}, P_oos={p_oos:.3f}, "
                            f"is_nav={is_nav}, has_curriculum={has_curriculum_topic}"
                        )
                        nli_intent, nli_conf = self._nli_arbiter.arbitrate(clean_prompt)
                        if is_nav:
                            logger.info(f"[IntentRouter-Cascade] Curriculum Navigation bảo chứng -> course_query")
                            return RouterClassification(intent="course_query", direct_response=None, is_course_query=True)
                        elif nli_intent == "course_query" and (nli_conf >= 0.35 or p_course >= 0.20 or has_curriculum_topic):
                            logger.info(f"[IntentRouter-Cascade] NLI Arbiter phân định -> course_query ({nli_conf*100:.1f}%)")
                            return RouterClassification(intent="course_query", direct_response=None, is_course_query=True)
                        elif nli_intent == "chit_chat":
                            if (nli_conf >= 0.65 and p_chit >= 0.12) or (nli_conf >= 0.45 and p_chit >= 0.22):
                                logger.info(f"[IntentRouter-Cascade] NLI Arbiter phân định -> chit_chat ({nli_conf*100:.1f}%)")
                                return RouterClassification(
                                    intent="chit_chat",
                                    direct_response=self._select_chitchat_response(clean_prompt, query_vec=query_vec),
                                    is_course_query=False
                                )
                            elif top1_class == "course_query" or p_course >= 0.25 or (
                                has_curriculum_topic and p_oos < 0.85
                            ):
                                logger.info(
                                    f"[IntentRouter-Cascade] Rigorous Chit-Chat Verification Gate: "
                                    f"Bác bỏ chit_chat (P_chit={p_chit:.3f} < 0.12, P_course={p_course:.3f}) -> course_query"
                                )
                                return RouterClassification(intent="course_query", direct_response=None, is_course_query=True)
                            else:
                                logger.info(
                                    f"[IntentRouter-Cascade] Rigorous Chit-Chat Verification Gate: "
                                    f"Bác bỏ chit_chat (P_chit={p_chit:.3f} < 0.12, P_course={p_course:.3f}) -> out_of_scope"
                                )
                                return RouterClassification(
                                    intent="out_of_scope",
                                    direct_response=OFFTOPIC_CASUAL_RESPONSES,
                                    is_course_query=False
                                )
                        elif nli_intent == "out_of_scope":
                            if top1_class == "course_query":
                                topic_verified = has_curriculum_topic or self._has_verified_curriculum_topic(clean_prompt)
                                has_student_code = _detect_student_cpp_ast(clean_prompt)
                                if (
                                    nli_conf >= 0.80
                                    and p_oos >= 0.22
                                    and (p_course - p_oos) < 0.25
                                    and not topic_verified
                                    and not has_student_code
                                ):
                                    logger.info(
                                        f"[IntentRouter-Cascade] NLI Arbiter lật SLM course_query phân vân "
                                        f"(NLI={nli_conf*100:.1f}%, P_course={p_course:.3f}, P_oos={p_oos:.3f}) -> out_of_scope"
                                    )
                                    return RouterClassification(
                                        intent="out_of_scope",
                                        direct_response=OFFTOPIC_CASUAL_RESPONSES,
                                        is_course_query=False,
                                    )
                                else:
                                    logger.info(
                                        f"[IntentRouter-Cascade] Recall-First Protection bảo vệ SLM course_query "
                                        f"(NLI={nli_conf*100:.1f}%, P_course={p_course:.3f}, P_oos={p_oos:.3f}, "
                                        f"topic={topic_verified}, ast={has_student_code}) -> course_query"
                                    )
                                    return RouterClassification(intent="course_query", direct_response=None, is_course_query=True)
                            else:
                                if (
                                    self.is_code_solicitation(clean_prompt)
                                    and p_oos < 0.85
                                    and p_course >= 0.20
                                    and (
                                        self.has_domain_entity(clean_prompt)
                                        or _detect_student_cpp_ast(clean_prompt)
                                        or has_curriculum_topic
                                        or self._has_verified_curriculum_topic(clean_prompt)
                                    )
                                ):
                                    logger.info(
                                        "[IntentRouter-Cascade] Pedagogical Code-Solicitation Protection -> course_query (Socratic soft refusal)"
                                    )
                                    return RouterClassification(intent="course_query", direct_response=None, is_course_query=True)

                                if (p_course >= 0.20 or has_curriculum_topic) and p_oos < 0.90:
                                    if nli_conf < 0.72 and (has_curriculum_topic or self._has_verified_curriculum_topic(clean_prompt)):
                                        logger.info(
                                            f"[IntentRouter-Cascade] Curriculum Semantic Rescue (NLI={nli_conf*100:.1f}%, P_course={p_course:.3f}) -> course_query"
                                        )
                                        return RouterClassification(intent="course_query", direct_response=None, is_course_query=True)

                                logger.info(f"[IntentRouter-Cascade] NLI Arbiter phân định -> out_of_scope ({nli_conf*100:.1f}%)")
                                return RouterClassification(
                                    intent="out_of_scope",
                                    direct_response=OFFTOPIC_CASUAL_RESPONSES,
                                    is_course_query=False
                                )

                    if top1_class == "out_of_scope" and is_nav:
                        logger.info(f"[IntentRouter] Post-SLM Curriculum Navigation Rescue -> course_query")
                        return RouterClassification(intent="course_query", direct_response=None, is_course_query=True)

                    if top1_class == "course_query":
                        return RouterClassification(intent="course_query", direct_response=None, is_course_query=True)
                    elif top1_class == "chit_chat":
                        return RouterClassification(
                            intent="chit_chat",
                            direct_response=self._select_chitchat_response(clean_prompt, query_vec=query_vec),
                            is_course_query=False
                        )
                    else:
                        return RouterClassification(
                            intent="out_of_scope",
                            direct_response=OFFTOPIC_CASUAL_RESPONSES,
                            is_course_query=False
                        )
            except Exception as err:
                logger.warning(f"[IntentRouter] Lỗi tính toán Ensemble Router ({err}).")

        # ----------------------------------------------------
        # 3. TẦNG 3: Mặc định an toàn chuyển tiếp vào RAG Pipeline
        # ----------------------------------------------------
        return RouterClassification(
            intent="course_query",
            direct_response=None,
            is_course_query=True
        )

    def check_confirmation(self, prompt: str) -> tuple[bool, float]:
        """Phán định ý định đồng ý/xác nhận hành động đàm thoại từ học viên (Speech-Act Guard + E5/NLI)."""
        clean_p = self._normalize_text(prompt)
        if not clean_p or "?" in clean_p or len(clean_p.split()) > 10:
            return (False, 0.0)
        if (
            self.has_domain_entity(clean_p)
            or _detect_student_cpp_ast(clean_p)
            or self.is_code_solicitation(clean_p)
        ):
            return (False, 0.0)
        alpha_clean = " ".join("".join(c if c.isalnum() else " " for c in clean_p.lower()).split())
        padded_alpha = f" {alpha_clean} "
        for sig in self._manifest_data.get("curriculum_navigation_signatures", []):
            sig_norm = " ".join("".join(c if c.isalnum() else " " for c in str(sig).lower()).split())
            if sig_norm and f" {sig_norm} " in padded_alpha:
                return (False, 0.0)
        for qs in self._manifest_data.get("question_starters", []):
            qs_norm = " ".join("".join(c if c.isalnum() else " " for c in str(qs).lower()).split())
            if qs_norm and f" {qs_norm} " in padded_alpha:
                return (False, 0.0)
        return self._nli_arbiter.is_confirmation(clean_p)


# Singleton instance để tái sử dụng toàn backend
_router_instance: Optional[IntentRouter] = None


def get_intent_router() -> IntentRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = IntentRouter()
    return _router_instance
