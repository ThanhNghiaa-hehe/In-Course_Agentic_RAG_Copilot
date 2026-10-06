"""
Bộ Định Tuyến Phân Loại Ý Định (Platt-Calibrated Intent Router)
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Kiến trúc phòng vệ 3 tầng sâu (Defense-in-Depth):
- Tầng 1: Explicit Code Syntax Gate (Bắt ký tự cú pháp lập trình #include, std::, ->, ::, cout, cin).
- Tầng 2: LinearSVC + Platt Scaling (Scikit-Learn CalibratedClassifierCV 3-fold) trên không gian E5 1024-dim.
- Tầng 3: Margin Decision Boundary (ΔP >= 0.12) kết hợp cơ chế Abstention Fallback vào RAG an toàn.
"""

import logging
import re
import unicodedata
from pathlib import Path
from typing import Optional, List, Dict, Any
import numpy as np
import joblib

from app.schemas.chat import RouterClassification
from app.services.embedding import get_embedding_service
from app.agent.guardrails import get_security_input_guardrail, SECURITY_REFUSAL_RESPONSE

logger = logging.getLogger("uvicorn.error")
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent



# ==========================================
# 2. Phản hồi Sư phạm Chuẩn (Pedagogical Responses)
# ==========================================
GREETING_RESPONSES = (
    "Chào bạn! Tôi là **In-Course AI Copilot** - Trợ giảng lập trình của khóa học. "
    "Hôm nay bạn đang học đến bài nào và gặp khó khăn gì với cú pháp hay thuật toán C++, "
    "hãy gửi cho tôi để chúng ta cùng giải quyết nhé!"
)

GRATITUDE_RESPONSES = (
    "Rất vui vì đã đồng hành và gợi mở được hướng đi cho bạn! "
    "Hãy tiếp tục thực hành viết code nhé, nếu gặp bất kỳ lỗi cú pháp hay logic nào khác, "
    "tôi luôn ở đây hỗ trợ bạn!"
)

GOODBYE_RESPONSES = (
    "Tạm biệt bạn nhé! Chúc bạn có một buổi học tập và thực hành hiệu quả. "
    "Khi nào cần hỗ trợ giải đáp về bài học hay sửa lỗi code C++, "
    "tôi luôn sẵn sàng đồng hành cùng bạn!"
)

IDENTITY_RESPONSES = (
    "Tôi là **In-Course Agentic RAG Copilot** - Trợ giảng lập trình thông minh theo phương pháp Socratic, "
    "được phát triển bởi sinh viên **Trần Thành Nghĩa** (MSSV: `23DH112252`), "
    "Trường **Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT)**.\n\n"
    "Hệ thống được xây dựng trên nền tảng **FastAPI**, **Python 3.11**, **Qdrant Vector DB** "
    "kết hợp mô hình embedding đa ngữ `multilingual-e5-large` và trích xuất mốc thời gian video chuẩn xác!"
)

ADVICE_RESPONSES = (
    "Học lập trình ban đầu có thể có nhiều bỡ ngỡ với các khái niệm như bộ nhớ, con trỏ hay cú pháp nghiêm ngặt của C++. "
    "Lời khuyên tốt nhất là hãy **kiên trì thực hành viết code mỗi ngày**, tự tay gõ từng dòng lệnh "
    "và học cách đọc hiểu các thông báo lỗi biên dịch. Tôi luôn ở đây đồng hành và hướng dẫn bạn từng bước!"
)

OFFTOPIC_CASUAL_RESPONSES = (
    "Chào bạn! Tôi là **In-Course AI Copilot** - Trợ giảng chuyên môn của khóa học lập trình C++. "
    "Tôi luôn sẵn sàng đồng hành hỗ trợ bạn giải đáp các thắc mắc về bài học, cú pháp code và bài tập lập trình "
    "thay vì các chủ đề ngoài lề đời sống. Hãy gửi cho tôi câu hỏi hoặc đoạn code C++ bạn đang gặp khó khăn nhé!"
)


class NLIArbiter:
    """
    Stage 2 Cross-Encoder NLI Arbiter:
    Sử dụng mô hình MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7 (chạy CPU, 0 MB VRAM).
    Nhiệm vụ: Phán xử logic ngữ nghĩa (Entailment / Contradiction) cho các câu hỏi
    rơi vào vùng phân vân (Margin < 0.12 hoặc P_course >= 0.20 khi bị Stage 1 kéo về out_of_scope).
    Tuyệt đối Zero-Regex, 100% Machine Learning.
    """

    def __init__(self):
        self._pipeline = None
        self._candidate_labels = [
            "câu hỏi học tập chuyên môn thắc mắc cú pháp hoặc giải thuật lập trình",
            "câu đùa vui, châm biếm, so sánh phi thực tế với phim ảnh, tình cảm hoặc đời sống"
        ]
        self._label_map = {
            "câu hỏi học tập chuyên môn thắc mắc cú pháp hoặc giải thuật lập trình": "course_query",
            "câu đùa vui, châm biếm, so sánh phi thực tế với phim ảnh, tình cảm hoặc đời sống": "out_of_scope"
        }
        self._template = "Văn bản này có mục đích là {}."

    def _get_pipeline(self):
        """Khởi tạo trễ (Lazy Loading) để không làm chậm thời gian khởi động server."""
        if self._pipeline is None:
            try:
                from transformers import pipeline
                logger.info("[NLIArbiter] Đang nạp mô hình mDeBERTa-v3-base-xnli trên CPU...")
                self._pipeline = pipeline(
                    "zero-shot-classification",
                    model="MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7",
                    device=-1
                )
                logger.info("[NLIArbiter] Nạp thành công mô hình NLI Arbiter trên CPU.")
            except Exception as e:
                logger.error(f"[NLIArbiter] Không thể nạp pipeline transformers NLI: {e}")
                self._pipeline = None
        return self._pipeline

    def arbitrate(self, prompt: str) -> tuple[str, float]:
        """Phán định ý định bằng suy luận logic Zero-Shot NLI."""
        pipe = self._get_pipeline()
        if pipe is None:
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

    def warmup(self) -> None:
        """Khởi động nóng mô hình NLI Arbiter trên CPU/RAM để khử triệt để Cold-Start."""
        try:
            pipe = self._get_pipeline()
            if pipe is not None:
                pipe("khởi động hệ thống", candidate_labels=self._candidate_labels[:1], hypothesis_template=self._template)
                logger.info("[NLIArbiter] Khởi động nóng (Warmup) hoàn tất.")
        except Exception as e:
            logger.warning(f"[NLIArbiter] Warmup thất bại nhẹ ({e}).")


class IntentRouter:
    """
    Bộ định tuyến phân loại ý định người dùng chuẩn SOTA:
    - Loại bỏ hoàn toàn các danh sách prototype tĩnh trong mã nguồn.
    - Kiến trúc Cascade 2 Tầng (Cascading Multi-Tier Router):
      + Tầng 1: Platt-Calibrated LinearSVC trên không gian E5 1024-dim (Fast-Path ~2 ms).
      + Tầng 2: Cross-Encoder NLI Arbiter (mDeBERTa-v3-base-xnli trên CPU khi phân vân).
    - Biên độ tự tin Margin Decision Boundary (ΔP >= 0.12) chống phân vân ngữ nghĩa.
    """

    def __init__(self):
        self._calibrated_clf = None
        self._classes = ["chit_chat", "course_query", "out_of_scope"]
        self._nli_arbiter = NLIArbiter()
        self._security_guardrail = get_security_input_guardrail()

        # Nạp mô hình đã hiệu chuẩn Platt Scaling (Scikit-Learn CalibratedClassifierCV)
        model_path = PROJECT_ROOT / "app" / "agent" / "models" / "calibrated_router.joblib"
        if model_path.exists():
            try:
                self._calibrated_clf = joblib.load(model_path)
                logger.info(f"[IntentRouter] Nạp thành công mô hình Platt-Calibrated Router từ {model_path}.")
            except Exception as e:
                logger.error(f"[IntentRouter] Lỗi khi nạp calibrated_router.joblib ({e}).")
        else:
            logger.warning(f"[IntentRouter] Chưa tìm thấy {model_path}. Cần chạy script huấn luyện.")

    def warmup(self) -> None:
        """Khởi động nóng mô hình NLI Arbiter để triệt tiêu Cold-Start."""
        self._nli_arbiter.warmup()

    def _normalize_text(self, text: str) -> str:
        """Chuẩn hóa văn bản Unicode NFC và loại bỏ khoảng trắng thừa."""
        if not text:
            return ""
        normalized = unicodedata.normalize("NFC", text.strip())
        return " ".join(normalized.split())

    def _select_chitchat_response(self, prompt: str) -> str:
        """Lựa chọn câu phản hồi sư phạm phù hợp cho nhóm Chit-Chat."""
        lower_p = prompt.lower()
        if any(w in lower_p for w in ["cảm ơn", "thank", "tuyệt", "hiểu rồi"]):
            return GRATITUDE_RESPONSES
        elif any(w in lower_p for w in ["tạm biệt", "bye", "hẹn gặp", "ngủ ngon"]):
            return GOODBYE_RESPONSES
        elif any(w in lower_p for w in ["tác giả", "là ai", "nghĩa", "huflit", "đồ án", "mã số"]):
            return IDENTITY_RESPONSES
        elif any(w in lower_p for w in ["khuyên", "kinh nghiệm", "khó không", "nản", "bắt đầu"]):
            return ADVICE_RESPONSES
        return GREETING_RESPONSES

    def classify(self, prompt: str) -> RouterClassification:
        """
        Phân loại câu hỏi của học viên thuần túy bằng Machine Learning (Zero-Regex):
        - Tầng 1: Platt-Calibrated Classifier (Scikit-Learn LinearSVC + CalibratedClassifierCV)
        - Tầng 2: Cross-Encoder NLI Arbiter (mDeBERTa-v3-base-xnli trên CPU) khi phân vân
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
                is_course_query=False
            )

        # ----------------------------------------------------
        # 1. TẦNG 1: Platt-Calibrated Classifier Gate (Scikit-Learn)
        # ----------------------------------------------------
        if self._calibrated_clf is not None:
            try:
                emb_svc = get_embedding_service()
                query_vec = np.array(emb_svc.embed_query_dense(clean_prompt), dtype=np.float32)
                q_norm = np.linalg.norm(query_vec)
                if q_norm > 0:
                    query_vec /= q_norm

                # Dự đoán phân phối xác suất đã hiệu chuẩn P(y=c|x)
                probs = self._calibrated_clf.predict_proba(query_vec.reshape(1, -1))[0]
                sorted_indices = np.argsort(probs)[::-1]
                top1_idx = sorted_indices[0]
                top2_idx = sorted_indices[1]

                top1_class = self._classes[top1_idx]
                top1_prob = float(probs[top1_idx])
                top2_prob = float(probs[top2_idx])
                margin = top1_prob - top2_prob

                p_chit = float(probs[0])
                p_course = float(probs[1])
                p_oos = float(probs[2])

                logger.info(
                    f"[IntentRouter-Calibrated] Probs: chit_chat={p_chit:.3f} | "
                    f"course_query={p_course:.3f} | out_of_scope={p_oos:.3f} (Margin={margin:.3f})"
                )

                # ----------------------------------------------------
                # ĐIỀU PHỐI CASCADE: STAGE 1 (LinearSVC) -> STAGE 2 (NLI ARBITER)
                # ----------------------------------------------------
                MARGIN_THRESHOLD = 0.12

                # Điều kiện kích hoạt Stage 2 NLI Arbiter:
                # 1. Rơi vào vùng phân vân ngữ nghĩa (margin < 0.12)
                # 2. Hoặc Stage 1 chọn out_of_scope nhưng chưa đủ tự tin (p_oos < 0.72) và vẫn có tín hiệu kỹ thuật đáng kể (p_course >= 0.25 và p_chit < 0.35)
                #    (Dấu hiệu của câu ẩn dụ sư phạm / chuỗi kỹ thuật bị từ vựng đời sống kéo lệch)
                is_ambiguous = (margin < MARGIN_THRESHOLD)
                is_potential_metaphor = (top1_class == "out_of_scope" and p_oos < 0.72 and p_course >= 0.25 and p_chit < 0.35)

                if is_ambiguous or is_potential_metaphor:
                    logger.info(
                        f"[IntentRouter-Cascade] Kích hoạt Stage 2 NLI Arbiter: "
                        f"Top1={top1_class} (P={top1_prob:.3f}), Margin={margin:.3f}, P_course={p_course:.3f}"
                    )
                    nli_intent, nli_conf = self._nli_arbiter.arbitrate(clean_prompt)

                    # Nếu NLI khẳng định đây là câu hỏi học tập (Entailment >= 0.50): Cứu về course_query
                    if nli_intent == "course_query" and nli_conf >= 0.50:
                        logger.info(f"[IntentRouter-Cascade] NLI Arbiter giải cứu thành công -> course_query ({nli_conf*100:.1f}%)")
                        return RouterClassification(intent="course_query", direct_response=None, is_course_query=True)

                    # Nếu NLI khẳng định out_of_scope và tự tin cao (>= 0.65)
                    elif nli_intent == "out_of_scope" and nli_conf >= 0.65 and top1_class != "chit_chat":
                        return RouterClassification(intent="out_of_scope", direct_response=OFFTOPIC_CASUAL_RESPONSES, is_course_query=False)

                # Trường hợp thông thường: Tuân thủ phán quyết Stage 1 LinearSVC
                if top1_class == "course_query":
                    return RouterClassification(intent="course_query", direct_response=None, is_course_query=True)
                elif top1_class == "chit_chat":
                    return RouterClassification(intent="chit_chat", direct_response=self._select_chitchat_response(clean_prompt), is_course_query=False)
                elif top1_class == "out_of_scope":
                    return RouterClassification(intent="out_of_scope", direct_response=OFFTOPIC_CASUAL_RESPONSES, is_course_query=False)

            except Exception as err:
                logger.warning(f"[IntentRouter] Lỗi tính toán Calibrated Router ({err}).")

        # ----------------------------------------------------
        # 3. TẦNG 3: Mặc định an toàn chuyển tiếp vào RAG Pipeline
        # ----------------------------------------------------
        return RouterClassification(
            intent="course_query",
            direct_response=None,
            is_course_query=True
        )


# Singleton instance để tái sử dụng toàn backend
_router_instance: Optional[IntentRouter] = None


def get_intent_router() -> IntentRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = IntentRouter()
    return _router_instance
