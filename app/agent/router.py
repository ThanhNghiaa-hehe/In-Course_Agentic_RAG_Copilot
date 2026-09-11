import re
import unicodedata
from typing import Optional, Tuple
from app.schemas.chat import RouterClassification

# ==========================================
# 1. Regex Fast-Path Patterns (Tier 1)
# ==========================================

# Mẫu câu chào hỏi
GREETING_PATTERNS = [
    r"^(xin\s+)?chào(\s+(bạn|thầy|cô|anh|em|ad|admin|bot|copilot|mọi\s+người|all))?[\s!.]*$",
    r"^(hi|hello|hey|alo|hế\s*lô|hé\s*lô|chao\s*ban)(\s+(bạn|thầy|cô|anh|em|ad|admin|bot|copilot|mọi\s+người|all))?[\s!.]*$",
    r"^(chúc\s+)?(buổi\s+)?(sáng|chiều|tối)(\s+vui\s+vẻ)?[\s!.]*$",
    r"^(bạn\s+khỏe\s+không|dạo\s+này\s+thế\s+nào|có\s+khỏe\s+không)[\s?!.]*$",
]

# Mẫu câu cảm ơn & xác nhận hoàn thành
GRATITUDE_PATTERNS = [
    r"^(cảm\s+ơn|cam\s+on|thank(s)?(\s+you)?|tks|tkss|ty)(\s+(bạn|thầy|ad|bot|copilot))?[\s!.]*$",
    r"^(ok|oke|okie|được\s+rồi|tuyệt\s+vời|hiểu\s+rồi|mình\s+hiểu\s+rồi|tuyệt)[\s!.]*$",
]

# Mẫu câu hỏi về danh tính trợ giảng AI (Tuân thủ Invariant Author)
IDENTITY_PATTERNS = [
    r"(bạn|em|mày|bot|copilot)\s+là\s+(ai|gì)",
    r"ai\s+(tạo|làm|viết|phát\s+triển|sinh)\s+ra\s+(bạn|em|bot|copilot)",
    r"(giới\s+thiệu\s+về\s+(bản\s+thân|bạn)|bạn\s+có\s+thể\s+làm\s+(được\s+)?gì)",
    r"(thông\s+tin\s+về\s+bạn|tác\s+giả\s+của\s+(bạn|em|bot|dự\s+án))",
]

# ==========================================
# 2. Regex Out-of-Scope Patterns (Tier 2)
# ==========================================
# Nhận diện các câu hỏi lệch phạm vi khóa học (nấu ăn, chiên cá, thời tiết, giải trí...)
OUT_OF_SCOPE_PATTERNS = [
    r"(chiên|rán|nướng|nấu|luộc|xào|kho)\s+(cá|thịt|gà|trứng|rau|canh|cơm|bò|heo)",
    r"(cách|làm\s+sao|bí\s+quyết)\s+(để\s+)?(chiên|rán|nướng|nấu|kho)",
    r"(thời\s+tiết|dự\s+báo\s+thời\s+tiết|nhiệt\s+độ\s+hôm\s+nay)",
    r"(giá\s+vàng|tỷ\s+giá|chứng\s+khoán|tiền\s+ảo|bitcoin)",
    r"(bóng\s+đá|kết\s+quả\s+xổ\s+số|soi\s+cầu|mua\s+vé)",
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

OUT_OF_SCOPE_RESPONSE = (
    "Xin lỗi bạn, tôi là **Trợ giảng Lập trình chuyên biệt** cho khóa học lập trình. "
    "Tôi chỉ có thể hỗ trợ các thắc mắc liên quan đến bài giảng, cú pháp mã nguồn, "
    "thuật toán và bài tập trong khóa học.\n\n"
    "Bạn hãy đặt câu hỏi liên quan đến kiến thức lập trình (ví dụ: biến, con trỏ, hàm, ép kiểu trong C++) để tôi hỗ trợ nhé!"
)


class IntentRouter:
    """
    Bộ định tuyến phân loại ý định người dùng (Multi-Tier Intent Classifier Router):
    - Tier 1: Fast-Path Regex Matcher (< 1ms, 0 API cost) cho chào hỏi, cảm ơn, danh tính.
    - Tier 2: Out-of-Scope Heuristic Filter cho các câu hỏi lạc đề (chiên cá, thời tiết...).
    - Tier 3: Course Query chuyển tiếp vào pipeline Advanced RAG (Qdrant + Jina Reranker).
    """

    def __init__(self):
        # Biên dịch trước các regex patterns để tối ưu hóa hiệu năng CPU micro-second
        self._greeting_res = [re.compile(p, re.IGNORECASE) for p in GREETING_PATTERNS]
        self._gratitude_res = [re.compile(p, re.IGNORECASE) for p in GRATITUDE_PATTERNS]
        self._identity_res = [re.compile(p, re.IGNORECASE) for p in IDENTITY_PATTERNS]
        self._out_of_scope_res = [re.compile(p, re.IGNORECASE) for p in OUT_OF_SCOPE_PATTERNS]

    def _normalize_text(self, text: str) -> str:
        """Chuẩn hóa văn bản Unicode NFC và loại bỏ khoảng trắng thừa."""
        if not text:
            return ""
        normalized = unicodedata.normalize("NFC", text.strip())
        return " ".join(normalized.split())

    def classify(self, prompt: str) -> RouterClassification:
        """
        Phân loại câu hỏi của học viên và xác định nhánh xử lý.
        
        Returns:
            RouterClassification với intent ('chit_chat', 'out_of_scope', 'course_query')
        """
        clean_prompt = self._normalize_text(prompt)
        if not clean_prompt:
            return RouterClassification(
                intent="chit_chat",
                direct_response=GREETING_RESPONSES,
                is_course_query=False
            )

        # 1. Tier 1: Fast-Path Identity (Ưu tiên cao nhất để bắt các câu hỏi danh tính kèm lời chào)
        for pattern in self._identity_res:
            if pattern.search(clean_prompt):
                return RouterClassification(
                    intent="chit_chat",
                    direct_response=IDENTITY_RESPONSES,
                    is_course_query=False
                )

        # 2. Tier 1: Fast-Path Greeting
        for pattern in self._greeting_res:
            if pattern.search(clean_prompt):
                return RouterClassification(
                    intent="chit_chat",
                    direct_response=GREETING_RESPONSES,
                    is_course_query=False
                )

        # 3. Tier 1: Fast-Path Gratitude
        for pattern in self._gratitude_res:
            if pattern.search(clean_prompt):
                return RouterClassification(
                    intent="chit_chat",
                    direct_response=GRATITUDE_RESPONSES,
                    is_course_query=False
                )

        # 4. Tier 2: Out-of-Scope Heuristic Guardrail
        for pattern in self._out_of_scope_res:
            if pattern.search(clean_prompt):
                return RouterClassification(
                    intent="out_of_scope",
                    direct_response=OUT_OF_SCOPE_RESPONSE,
                    is_course_query=False
                )

        # 5. Tier 3: In-Course Learning Query -> Tiến vào RAG Pipeline
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
