import logging
import re
import unicodedata
from typing import Optional, List, Dict, Any
import numpy as np

from app.schemas.chat import RouterClassification
from app.services.embedding import get_embedding_service

logger = logging.getLogger("uvicorn.error")

# ==========================================
# 1. Explicit Code Syntax & Compiler Error Gate
# (Phát hiện cú pháp mã nguồn thực tế và thông báo lỗi trình biên dịch)
# ==========================================
EXPLICIT_SYNTAX_PATTERNS = [
    # Cú pháp khối mã Markdown
    r"```",
    # Thư viện và chỉ thị tiền xử lý
    r"#include\s*<",
    # Namespace, toán tử phạm vi và truy cập thành viên C++
    r"\b(std::|cout|cin|printf|scanf|nullptr|NULL)\b",
    r"->",
    r"::",
]

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

# ==========================================
# 3. Multi-Class Semantic Router Anchors (Chuẩn Aurelio AI Standard 2024)
# ==========================================

# Cụm 1: Giao tiếp Xã giao, Lời chào, Cảm ơn, Tạm biệt, Danh tính & Lời khuyên
CHIT_CHAT_PROTOTYPES: List[Dict[str, str]] = [
    # Chào hỏi (Greetings - Tiếng Việt & Tiếng Anh)
    {"text": "xin chào bạn, chúc bạn một ngày tốt lành", "subtype": "greeting"},
    {"text": "chào bạn, chúc bạn một ngày làm việc vui vẻ", "subtype": "greeting"},
    {"text": "hello ai copilot, how are you today", "subtype": "greeting"},
    {"text": "hi bot, chào bạn nhé", "subtype": "greeting"},
    {"text": "chào buổi sáng, chúc một ngày tràn đầy năng lượng", "subtype": "greeting"},
    {"text": "bạn khỏe không, dạo này thế nào", "subtype": "greeting"},
    {"text": "xin chào thầy trợ giảng AI", "subtype": "greeting"},
    # Cảm ơn (Gratitude)
    {"text": "cảm ơn bạn nhiều nhé, giải thích rất dễ hiểu", "subtype": "gratitude"},
    {"text": "thank you very much, cảm ơn trợ giảng", "subtype": "gratitude"},
    {"text": "mình hiểu rồi, cảm ơn bạn rất nhiều", "subtype": "gratitude"},
    {"text": "tuyệt vời, cảm ơn sự hỗ trợ nhiệt tình của bạn", "subtype": "gratitude"},
    # Tạm biệt (Goodbye)
    {"text": "tạm biệt bot nhé, hẹn gặp lại vào ngày mai", "subtype": "goodbye"},
    {"text": "bye bot, chúc bạn ngủ ngon nhé", "subtype": "goodbye"},
    {"text": "hẹn gặp lại bạn sau nhé, tạm biệt", "subtype": "goodbye"},
    # Danh tính & Quyền sở hữu đồ án (Identity & Project Invariant)
    {"text": "bạn là ai và ai là người đã phát triển ra bạn", "subtype": "identity"},
    {"text": "đồ án này là của ai làm vậy bot, ai phát triển dự án này", "subtype": "identity"},
    {"text": "bạn được viết bằng ngôn ngữ lập trình gì thế, công nghệ kiến trúc gì", "subtype": "identity"},
    {"text": "giới thiệu về bản thân bạn và tác giả của đồ án này", "subtype": "identity"},
    {"text": "ai là tác giả của bạn", "subtype": "identity"},
    # Lời khuyên học tập (Pedagogical Advice)
    {"text": "học lập trình có khó không bạn, cho mình lời khuyên với", "subtype": "advice"},
    {"text": "người mới bắt đầu học lập trình C++ nên học như thế nào cho hiệu quả", "subtype": "advice"},
    {"text": "làm sao để học giỏi lập trình, xin kinh nghiệm học tốt", "subtype": "advice"},
]

# Cụm 2: Chủ đề Ngoài lề Đời sống (Off-Topic Casual Queries)
OFFTOPIC_PROTOTYPES: List[str] = [
    "thời tiết hôm nay ở Sài Gòn thế nào bạn ơi, trời mưa hay nắng",
    "dự báo thời tiết ngày mai có mưa bão lạnh không",
    "bạn có thể kể một câu chuyện cười được không, kể chuyện hài vui vẻ",
    "hát cho mình nghe một bài hát, mở nhạc giải trí đi",
    "hôm nay ăn gì, ăn thịt bò ăn lẩu uống trà sữa không",
    "đi nhậu không bạn, rủ đi uống bia uống rượu xem bóng đá",
    "bạn có người yêu chưa, tâm sự chuyện tình cảm cuộc sống gia đình",
    "dự đoán cung hoàng đạo, bói toán xem tử vi vận mệnh tương lai",
    "tôi muốn mua vé máy bay đi du lịch, giá phòng khách sạn",
    "làm sao để chữa bệnh cảm cúm, hạ sốt uống thuốc gì",
    "bí quyết giảm cân nhanh trong một tuần không cần tập thể dục",
    "chỉ cách trúng số độc đắc vietlott ngày hôm nay",
    "tán gẫu chém gió chuyện showbiz đời sống xã hội",
]

# Cụm 3: Chuyên môn Lập trình C++ (Course Technical Queries)
TECH_PROTOTYPES: List[str] = [
    "hỏi về bài học lập trình C++ và cấu trúc hàm main chuẩn",
    "giải thích cú pháp biến hằng số const và ép kiểu dữ liệu type casting",
    "con trỏ pointer địa chỉ ô nhớ và toán tử giải tham chiếu trong C++",
    "lỗi biên dịch compilation error syntax error linker error undefined reference",
    "lỗi runtime segfault segmentation fault core dump tràn bộ nhớ stack overflow",
    "thư viện iostream lệnh cout cin và namespace std",
    "vòng lặp for while câu lệnh điều kiện if else mảng array tĩnh",
    "thuật toán đệ quy recursion sắp xếp tìm kiếm bài tập C++",
    "cách định nghĩa class struct đối tượng oop kế thừa đa hình",
    "template trong C++ và con trỏ thông minh unique_ptr shared_ptr",
    "đọc ghi file văn bản fstream và xử lý ngoại lệ try catch",
    "xem video bài giảng phút nào mốc thời gian bài học C++",
]


class IntentRouter:
    """
    Bộ định tuyến phân loại ý định người dùng chuẩn SOTA Multi-Class Semantic Router (Aurelio AI Standard):
    - Tầng 1: Explicit Code Syntax & Compiler Error Gate (Nhận diện cú pháp code block, #include, std::, lỗi segfault) -> Ép ngay vào RAG.
    - Tầng 2: Multi-Class Semantic Vector Router (Tính toán Cosine vi mô với 3 cụm Prototypes trên không gian E5):
      + CHIT_CHAT_PROTOTYPES -> Route 'chit_chat' (Fast-Path < 50ms kèm câu trả lời sư phạm tương ứng).
      + OFFTOPIC_PROTOTYPES -> Route 'out_of_scope' (Từ chối lịch sự < 50ms, tiết kiệm tài nguyên).
      + TECH_PROTOTYPES -> Route 'course_query' (Đẩy vào True Hybrid Retrieval & CRAG Grader).
    - Tầng 3: Default Route -> Mặc định 'course_query' để bảo toàn tính an toàn cho câu hỏi lập trình.
    """

    def __init__(self):
        self._syntax_gate_res = [re.compile(p, re.IGNORECASE) for p in EXPLICIT_SYNTAX_PATTERNS]
        self._semantic_ready = False

        # Khởi tạo ma trận Prototype Embeddings cho Multi-Class Semantic Router
        try:
            emb_svc = get_embedding_service()

            chitchat_texts = [p["text"] for p in CHIT_CHAT_PROTOTYPES]
            self._chitchat_subtypes = [p["subtype"] for p in CHIT_CHAT_PROTOTYPES]

            chitchat_vecs = [emb_svc.embed_query_dense(t) for t in chitchat_texts]
            offtopic_vecs = [emb_svc.embed_query_dense(t) for t in OFFTOPIC_PROTOTYPES]
            tech_vecs = [emb_svc.embed_query_dense(t) for t in TECH_PROTOTYPES]

            self._chitchat_mat = np.array(chitchat_vecs, dtype=np.float32)
            self._offtopic_mat = np.array(offtopic_vecs, dtype=np.float32)
            self._tech_mat = np.array(tech_vecs, dtype=np.float32)

            # Chuẩn hóa L2 norm ma trận
            self._chitchat_mat /= np.maximum(np.linalg.norm(self._chitchat_mat, axis=1, keepdims=True), 1e-9)
            self._offtopic_mat /= np.maximum(np.linalg.norm(self._offtopic_mat, axis=1, keepdims=True), 1e-9)
            self._tech_mat /= np.maximum(np.linalg.norm(self._tech_mat, axis=1, keepdims=True), 1e-9)

            self._semantic_ready = True
            logger.info("[IntentRouter] Nạp thành công Multi-Class Semantic Router (Aurelio AI Standard - 3 Intent Spaces).")
        except Exception as e:
            logger.warning(f"[IntentRouter] Không thể khởi tạo Semantic Router ({e}), fallback sang cấu hình cơ bản.")
            self._semantic_ready = False

    def _normalize_text(self, text: str) -> str:
        """Chuẩn hóa văn bản Unicode NFC và loại bỏ khoảng trắng thừa."""
        if not text:
            return ""
        normalized = unicodedata.normalize("NFC", text.strip())
        return " ".join(normalized.split())

    def _get_chitchat_response(self, subtype: str) -> str:
        """Lấy câu phản hồi sư phạm phù hợp theo phân loại chi tiết của Chit-Chat."""
        if subtype == "greeting":
            return GREETING_RESPONSES
        elif subtype == "gratitude":
            return GRATITUDE_RESPONSES
        elif subtype == "goodbye":
            return GOODBYE_RESPONSES
        elif subtype == "identity":
            return IDENTITY_RESPONSES
        elif subtype == "advice":
            return ADVICE_RESPONSES
        return GREETING_RESPONSES

    def classify(self, prompt: str) -> RouterClassification:
        """
        Phân loại câu hỏi của học viên theo mô hình phòng thủ 3 tầng khoa học.
        """
        clean_prompt = self._normalize_text(prompt)
        if not clean_prompt:
            return RouterClassification(
                intent="chit_chat",
                direct_response=GREETING_RESPONSES,
                is_course_query=False
            )

        # ----------------------------------------------------
        # 1. TẦNG 1: Explicit Code Syntax & Compiler Error Gate
        # ----------------------------------------------------
        # Nếu câu hỏi chứa ký hiệu code cụ thể (#include, std::, ->, segfault) -> Ép ngay vào RAG
        has_syntax_signal = any(p.search(clean_prompt) for p in self._syntax_gate_res)
        if has_syntax_signal:
            return RouterClassification(
                intent="course_query",
                direct_response=None,
                is_course_query=True
            )

        # ----------------------------------------------------
        # 2. TẦNG 2: Multi-Class Semantic Vector Router (Aurelio AI)
        # ----------------------------------------------------
        if self._semantic_ready:
            try:
                emb_svc = get_embedding_service()
                query_vec = np.array(emb_svc.embed_query_dense(clean_prompt), dtype=np.float32)
                q_norm = np.linalg.norm(query_vec)
                if q_norm > 0:
                    query_vec /= q_norm

                    # Tính độ tương đồng cực đại với 3 cụm ý định
                    chitchat_sims = np.dot(self._chitchat_mat, query_vec)
                    sim_chitchat = float(np.max(chitchat_sims))
                    best_chitchat_idx = int(np.argmax(chitchat_sims))

                    sim_offtopic = float(np.max(np.dot(self._offtopic_mat, query_vec)))
                    sim_tech = float(np.max(np.dot(self._tech_mat, query_vec)))

                    logger.info(
                        f"[IntentRouter] Semantic Scores: ChitChat={sim_chitchat:.3f} | "
                        f"OffTopic={sim_offtopic:.3f} | Tech={sim_tech:.3f}"
                    )

                    # Quyết định phân luồng (Argmax with Confidence Threshold)
                    # Ngưỡng tin cậy chuẩn Aurelio AI: >= 0.65
                    CONFIDENCE_THRESHOLD = 0.65

                    # TH1: Ý định Chit-Chat vượt trội
                    if sim_chitchat >= CONFIDENCE_THRESHOLD and sim_chitchat >= sim_tech and sim_chitchat >= sim_offtopic:
                        subtype = self._chitchat_subtypes[best_chitchat_idx]
                        return RouterClassification(
                            intent="chit_chat",
                            direct_response=self._get_chitchat_response(subtype),
                            is_course_query=False
                        )

                    # TH2: Ý định Ngoài lề Đời sống (Off-Topic) vượt trội
                    if sim_offtopic >= CONFIDENCE_THRESHOLD and sim_offtopic > sim_tech and sim_offtopic > sim_chitchat:
                        return RouterClassification(
                            intent="out_of_scope",
                            direct_response=OFFTOPIC_CASUAL_RESPONSES,
                            is_course_query=False
                        )

                    # TH3: Ý định Chuyên môn (Tech) vượt trội -> Vào RAG
                    if sim_tech >= CONFIDENCE_THRESHOLD and sim_tech > sim_chitchat and sim_tech > sim_offtopic:
                        return RouterClassification(
                            intent="course_query",
                            direct_response=None,
                            is_course_query=True
                        )
            except Exception as err:
                logger.warning(f"[IntentRouter] Lỗi tính toán Semantic Router ({err}).")

        # ----------------------------------------------------
        # 3. TẦNG 3: Mặc định chuyển tiếp vào RAG Pipeline
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


