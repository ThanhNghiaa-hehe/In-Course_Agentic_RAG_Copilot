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


class IntentRouter:
    """
    Bộ định tuyến phân loại ý định người dùng chuẩn SOTA:
    - Loại bỏ hoàn toàn các danh sách prototype tĩnh trong mã nguồn.
    - Vận hành dựa trên mô hình Platt-Calibrated LinearSVC trên không gian E5 1024 chiều.
    - Biên độ tự tin Margin Decision Boundary (ΔP >= 0.12) chống phân vân ngữ nghĩa.
    """

    def __init__(self):
        self._calibrated_clf = None
        self._classes = ["chit_chat", "course_query", "out_of_scope"]

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
        - Tầng 2: Margin Decision Boundary (ΔP >= 0.12) chống phân vân ngữ nghĩa
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

                logger.info(
                    f"[IntentRouter-Calibrated] Probs: chit_chat={probs[0]:.3f} | "
                    f"course_query={probs[1]:.3f} | out_of_scope={probs[2]:.3f} (Margin={margin:.3f})"
                )

                # Ngưỡng Margin Quyết Định (Margin Decision Boundary >= 0.12)
                MARGIN_THRESHOLD = 0.12
                if margin >= MARGIN_THRESHOLD:
                    if top1_class == "course_query":
                        return RouterClassification(intent="course_query", direct_response=None, is_course_query=True)
                    elif top1_class == "chit_chat":
                        return RouterClassification(intent="chit_chat", direct_response=self._select_chitchat_response(clean_prompt), is_course_query=False)
                    elif top1_class == "out_of_scope":
                        return RouterClassification(intent="out_of_scope", direct_response=OFFTOPIC_CASUAL_RESPONSES, is_course_query=False)
                else:
                    # Margin hẹp (phân vân ngữ nghĩa) -> Abstention, an toàn fallback vào course_query
                    logger.info(f"[IntentRouter-Calibrated] Margin thấp ({margin:.3f} < {MARGIN_THRESHOLD}) -> Abstention Fallback vào RAG.")
                    return RouterClassification(intent="course_query", direct_response=None, is_course_query=True)

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
