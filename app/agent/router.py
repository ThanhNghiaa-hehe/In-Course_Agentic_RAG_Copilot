import logging
import re
import unicodedata
from typing import Optional, List
import numpy as np

from app.schemas.chat import RouterClassification
from app.services.embedding import get_embedding_service

logger = logging.getLogger("uvicorn.error")

# ==========================================
# 1. In-Scope Technical Safety-Net (Ưu tiên cao nhất chống False Negative)
# ==========================================
IN_SCOPE_SAFETY_NET_PATTERNS = [
    # Cú pháp code block và ký tự lập trình đặc thù
    r"```",
    r"[{};]",
    r"#include\s*<",
    r"\b(std::|cout|cin|printf|scanf|nullptr|NULL)\b",
    r"->",
    r"::",
    # Từ khóa lỗi và gỡ lỗi
    r"\b(segfault|segmentation\s*fault|core\s*dump|lỗi|error|bug|warning|undefined|stack\s*overflow)\b",
    # Từ khóa cốt lõi của môn học C++
    r"\b(c\+\+|cpp|c\s*\+\+|con\s*trỏ|pointer|biến|hàm|mảng|array|vòng\s*lặp|loop|for|while)\b",
    r"\b(struct|class|oop|đối\s*tượng|kế\s*thừa|đa\s*hình|constructor|destructor|override)\b",
    r"\b(int|float|char|double|string|bool|void|return|main|const|static|auto|vector)\b",
    r"\b(new|delete|malloc|free|reference|tham\s*chiếu|địa\s*chỉ|memory|bộ\s*nhớ|leak)\b",
    r"\b(thuật\s*toán|giải\s*thuật|đệ\s*quy|recursion|sắp\s*xếp|tìm\s*kiếm|bài\s*tập)\b",
]

# ==========================================
# 2. Fast-Path Greeting & Identity Patterns
# ==========================================
GREETING_PATTERNS = [
    r"^(xin\s+)?chào(\s+(bạn|thầy|cô|anh|em|ad|admin|bot|copilot|mọi\s+người|all))?[\s!.]*$",
    r"^(hi|hello|hey|alo|hế\s*lô|hé\s*lô|chao\s*ban)(\s+(bạn|thầy|cô|anh|em|ad|admin|bot|copilot|mọi\s+người|all))?[\s!.]*$",
    r"^(chúc\s+)?(buổi\s+)?(sáng|chiều|tối)(\s+vui\s+vẻ)?[\s!.]*$",
    r"^(bạn\s+khỏe\s+không|dạo\s+này\s+thế\s+nào|có\s+khỏe\s+không)[\s?!.]*$",
]

GRATITUDE_PATTERNS = [
    r"^(cảm\s+ơn|cam\s+on|thank(s)?(\s+you)?|tks|tkss|ty)(\s+(bạn|thầy|ad|bot|copilot))?[\s!.]*$",
    r"^(ok|oke|okie|được\s+rồi|tuyệt\s+vời|hiểu\s+rồi|mình\s+hiểu\s+rồi|tuyệt)[\s!.]*$",
]

IDENTITY_PATTERNS = [
    r"(bạn|em|mày|bot|copilot)\s+là\s+(ai|gì)",
    r"ai\s+(tạo|làm|viết|phát\s+triển|sinh)\s+ra\s+(bạn|em|bot|copilot)",
    r"(giới\s+thiệu\s+về\s+(bản\s+thân|bạn)|bạn\s+có\s+thể\s+làm\s+(được\s+)?gì)",
    r"(thông\s+tin\s+về\s+bạn|tác\s+giả\s+của\s+(bạn|em|bot|dự\s+án))",
]

# ==========================================
# 3. Phản hồi sư phạm chuẩn định hình
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

IDENTITY_RESPONSES = (
    "Tôi là **In-Course Agentic RAG Copilot** - Trợ giảng lập trình thông minh theo phương pháp Socratic, "
    "được phát triển bởi sinh viên **Trần Thành Nghĩa** (MSSV: `23DH112252`), "
    "Trường **Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT)**.\n\n"
    "Nhiệm vụ của tôi là gợi mở tư duy, phân tích nguyên nhân lỗi, "
    "và trích dẫn chính xác mốc thời gian video bài giảng kèm mã nguồn mẫu để giúp bạn tự tin làm chủ lập trình!"
)

OFFTOPIC_CASUAL_RESPONSES = (
    "Chào bạn! Tôi là **In-Course AI Copilot** - Trợ giảng chuyên môn của khóa học lập trình C++. "
    "Tôi luôn sẵn sàng đồng hành hỗ trợ bạn giải đáp các thắc mắc về bài học, cú pháp code và bài tập lập trình "
    "thay vì các chủ đề ngoài lề đời sống. Hãy gửi cho tôi câu hỏi hoặc đoạn code C++ bạn đang gặp khó khăn nhé!"
)

# ==========================================
# 4. Semantic Router Prototype Anchors (Chuẩn Aurelio AI)
# ==========================================
OFFTOPIC_ANCHORS: List[str] = [
    "nhậu không bạn, đi uống bia không",
    "hôm nay ăn gì, ăn thịt bò ăn lẩu không",
    "thời tiết hôm nay thế nào, trời mưa hay nắng",
    "đi chơi đi cà phê dạo phố xem phim với mình không",
    "bạn có người yêu chưa, tâm sự tình cảm cuộc sống đi",
    "bạn có biết hát hay chơi game bóng đá liên quân không",
    "buồn ngủ quá mệt mỏi quá, chúc ngủ ngon nhé",
    "chào buổi sáng, một ngày mới vui vẻ",
    "tán gẫu chém gió chuyện đời sống xã hội"
]

TECH_ANCHORS: List[str] = [
    "hỏi về bài học lập trình C++ và cấu trúc hàm main",
    "giải thích cú pháp biến con trỏ mảng vòng lặp for while",
    "lỗi biên dịch segfault segmentation fault core dump",
    "xem video bài giảng phút nào mốc thời gian bài học",
    "thư viện iostream lệnh cout cin namespace std",
    "khai báo hằng số const và ép kiểu thăng cấp dữ liệu",
    "thuật toán đệ quy sắp xếp tìm kiếm bài tập C++"
]


class IntentRouter:
    """
    Bộ định tuyến phân loại ý định người dùng kết hợp Semantic Vector Router (Aurelio AI Standard):
    - Tier 1: In-Scope Safety-Net (phát hiện code, lỗi, keyword C++) -> Ép route vào RAG (chống False Negative).
    - Tier 2: Pure Fast-Path Regex (chào hỏi đơn giản, danh tính tác giả).
    - Tier 3: Semantic Router (Cosine Similarity với Prototype Vector Centroids):
      + Nếu similarity(query, OFFTOPIC) >= 0.70 và > similarity(query, TECH) -> Chặn ngay ở cửa vào (< 3ms).
    - Tier 4: Default Route -> Chuyển tiếp vào RAG Pipeline để Cross-Encoder chấm điểm.
    """

    def __init__(self):
        self._safety_net_res = [re.compile(p, re.IGNORECASE) for p in IN_SCOPE_SAFETY_NET_PATTERNS]
        self._identity_res = [re.compile(p, re.IGNORECASE) for p in IDENTITY_PATTERNS]
        self._greeting_res = [re.compile(p, re.IGNORECASE) for p in GREETING_PATTERNS]
        self._gratitude_res = [re.compile(p, re.IGNORECASE) for p in GRATITUDE_PATTERNS]

        # Khởi tạo ma trận Prototype Embeddings cho Semantic Router
        try:
            emb_svc = get_embedding_service()
            offtopic_list = [emb_svc.embed_query_dense(a) for a in OFFTOPIC_ANCHORS]
            tech_list = [emb_svc.embed_query_dense(a) for a in TECH_ANCHORS]
            self._offtopic_mat = np.array(offtopic_list, dtype=np.float32)
            self._tech_mat = np.array(tech_list, dtype=np.float32)
            # Chuẩn hóa L2 norm
            self._offtopic_mat /= np.maximum(np.linalg.norm(self._offtopic_mat, axis=1, keepdims=True), 1e-9)
            self._tech_mat /= np.maximum(np.linalg.norm(self._tech_mat, axis=1, keepdims=True), 1e-9)
            self._semantic_ready = True
            logger.info("[IntentRouter] Nạp thành công Semantic Router Anchors (Aurelio AI Standard).")
        except Exception as e:
            logger.warning(f"[IntentRouter] Không thể khởi tạo Semantic Router ({e}), fallback sang Regex.")
            self._semantic_ready = False

    def _normalize_text(self, text: str) -> str:
        """Chuẩn hóa văn bản Unicode NFC và loại bỏ khoảng trắng thừa."""
        if not text:
            return ""
        normalized = unicodedata.normalize("NFC", text.strip())
        return " ".join(normalized.split())

    def _compute_semantic_intent(self, clean_prompt: str) -> Optional[RouterClassification]:
        """
        Tính toán khoảng cách Cosine vi mô với các cụm chủ đề để nhận diện câu hỏi ngoài lề đời sống.
        """
        if not self._semantic_ready:
            return None

        try:
            emb_svc = get_embedding_service()
            query_vec = np.array(emb_svc.embed_query_dense(clean_prompt), dtype=np.float32)
            q_norm = np.linalg.norm(query_vec)
            if q_norm == 0:
                return None
            query_vec /= q_norm

            sim_offtopic = float(np.max(np.dot(self._offtopic_mat, query_vec)))
            sim_tech = float(np.max(np.dot(self._tech_mat, query_vec)))

            logger.info(f"[IntentRouter] Semantic Scores: OffTopic={sim_offtopic:.3f} | Tech={sim_tech:.3f}")

            # Nếu độ tương đồng với cụm OffTopic vượt trội (>= 0.70 và cao hơn Tech)
            if sim_offtopic >= 0.70 and sim_offtopic > sim_tech:
                return RouterClassification(
                    intent="out_of_scope",
                    direct_response=OFFTOPIC_CASUAL_RESPONSES,
                    is_course_query=False
                )
        except Exception as err:
            logger.warning(f"[IntentRouter] Lỗi tính semantic similarity ({err}).")

        return None

    def classify(self, prompt: str) -> RouterClassification:
        """
        Phân loại câu hỏi của học viên theo mô hình phòng thủ 4 tầng.
        """
        clean_prompt = self._normalize_text(prompt)
        if not clean_prompt:
            return RouterClassification(
                intent="chit_chat",
                direct_response=GREETING_RESPONSES,
                is_course_query=False
            )

        # 1. TIER 1: In-Scope Safety-Net (Ưu tiên cao nhất chống False Negative)
        # Nếu câu hỏi có chứa code block, cú pháp C++, hoặc lỗi biên dịch -> Ép ngay vào RAG
        has_technical_signal = any(p.search(clean_prompt) for p in self._safety_net_res)
        if has_technical_signal:
            return RouterClassification(
                intent="course_query",
                direct_response=None,
                is_course_query=True
            )

        # 2. TIER 2: Pure Fast-Path Regex (Chào hỏi, Cảm ơn, Danh tính tác giả)
        for pattern in self._identity_res:
            if pattern.search(clean_prompt):
                return RouterClassification(
                    intent="chit_chat",
                    direct_response=IDENTITY_RESPONSES,
                    is_course_query=False
                )

        for pattern in self._greeting_res:
            if pattern.search(clean_prompt):
                return RouterClassification(
                    intent="chit_chat",
                    direct_response=GREETING_RESPONSES,
                    is_course_query=False
                )

        for pattern in self._gratitude_res:
            if pattern.search(clean_prompt):
                return RouterClassification(
                    intent="chit_chat",
                    direct_response=GRATITUDE_RESPONSES,
                    is_course_query=False
                )

        # 3. TIER 3: Semantic Router (Aurelio AI Vector Routing)
        # Nhận diện các câu rủ rê, từ lóng, ăn nhậu, tâm sự đời sống mà Regex không thể bao quát
        semantic_result = self._compute_semantic_intent(clean_prompt)
        if semantic_result is not None:
            return semantic_result

        # 4. TIER 4: Mặc định chuyển tiếp vào RAG Pipeline
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

