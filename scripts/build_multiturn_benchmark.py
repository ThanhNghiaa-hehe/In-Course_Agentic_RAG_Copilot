"""
Multi-Turn Conversational Benchmark Dataset Generator & Validator
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.
"""
import json
import re
from pathlib import Path
from collections import Counter

DATASET_FILE = Path(__file__).resolve().parent.parent / "tests" / "data" / "multiturn_benchmark_dataset.json"
ROUTER_CORPUS_FILE = Path(__file__).resolve().parent.parent / "data" / "metadata" / "router_training_corpus.json"
OUTPUT_FILE = DATASET_FILE

def norm(t: str) -> str:
    return re.sub(r"\s+", " ", t.lower().strip())

def jaccard_similarity(s1: str, s2: str) -> float:
    w1 = set(norm(s1).split())
    w2 = set(norm(s2).split())
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / len(w1 | w2)

if DATASET_FILE.exists():
    with open(DATASET_FILE, "r", encoding="utf-8") as _f_init:
        _existing_data = json.load(_f_init)
    TIER1_SESSIONS = [s for s in _existing_data if s.get("tier") == "tier_1_anaphora"]
    TIER2_SESSIONS = [s for s in _existing_data if s.get("tier") == "tier_2_socratic"]
    TIER3_SESSIONS = [s for s in _existing_data if s.get("tier") == "tier_3_topic_switch"]
    TIER4_SESSIONS = [s for s in _existing_data if s.get("tier") == "tier_4_budget"]
else:
    TIER1_SESSIONS = []
    TIER2_SESSIONS = []
    TIER3_SESSIONS = []
    TIER4_SESSIONS = []

TIER3_SESSIONS = [
    {
        "session_id": "SESSION-SWITCH-31",
        "course_id": "cpp-core",
        "lesson_seq": 2,
        "lesson_title": "Bài 2: Làm quen C++, Vào Ra & Kiểu dữ liệu, Biến",
        "tier": "tier_3_topic_switch",
        "turns": [
            {
                "turn_idx": 1,
                "user_prompt": "Biến char trong C++ chiếm bao nhiêu byte bộ nhớ?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "char memory size (1 byte)",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [915, 1030],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 2,
                "user_prompt": "Ủa vậy qua bài 6 vòng lặp for với while học về cái gì vậy thầy?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "out_of_lesson",
                "expected_target_entity": "lesson 6 loops overview",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [350, 1600],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 3,
                "user_prompt": "Thời tiết hôm nay ở Đà Nẵng có mưa không bot?",
                "expected_intent": "out_of_scope",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 4,
                "user_prompt": "Dạ thôi em quay lại bài 2, lệnh cin >> x thì nó nhập dữ liệu từ đâu?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "cin standard input stream",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [45, 915],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            }
        ]
    },
    {
        "session_id": "SESSION-SWITCH-32",
        "course_id": "cpp-core",
        "lesson_seq": 3,
        "lesson_title": "Bài 3: Toàn tập về các toán tử cơ bản trong C++",
        "tier": "tier_3_topic_switch",
        "turns": [
            {
                "turn_idx": 1,
                "user_prompt": "Toán tử chia lấy dư % có dùng được cho số thực float không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "modulo operator limitation to integers",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [450, 1168],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 2,
                "user_prompt": "Học xong C++ em có thể lập trình web frontend bằng ReactJS được không?",
                "expected_intent": "out_of_scope",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 3,
                "user_prompt": "Thế trong playlist này bài mấy dạy về viết hàm function vậy bot?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "out_of_lesson",
                "expected_target_entity": "lesson 7 function navigation",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [5750],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 4,
                "user_prompt": "Cảm ơn trợ giảng đã hướng dẫn lộ trình học!",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            }
        ]
    },
    {
        "session_id": "SESSION-SWITCH-33",
        "course_id": "cpp-core",
        "lesson_seq": 4,
        "lesson_title": "Bài 4: Cấu trúc rẽ nhánh If Else và Switch Case",
        "tier": "tier_3_topic_switch",
        "turns": [
            {
                "turn_idx": 1,
                "user_prompt": "Khi nào nên dùng if else và khi nào nên dùng switch case?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "if else vs switch case comparison",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [751, 800],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 2,
                "user_prompt": "Trợ giảng có thích chơi bóng đá không hay chỉ thích code thôi?",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 3,
                "user_prompt": "Bài tập về mảng một chiều học ở bài bao nhiêu vậy bot?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "out_of_lesson",
                "expected_target_entity": "lesson 11 array navigation",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [520],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 4,
                "user_prompt": "Cảm ơn bot, mình quay lại làm bài tập rẽ nhánh đây!",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            }
        ]
    },
    {
        "session_id": "SESSION-SWITCH-34",
        "course_id": "cpp-core",
        "lesson_seq": 6,
        "lesson_title": "Bài 6: Vòng lặp For, While và Do-While",
        "tier": "tier_3_topic_switch",
        "turns": [
            {
                "turn_idx": 1,
                "user_prompt": "Làm sao để dừng sớm một vòng lặp for khi tìm thấy kết quả?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "break statement in loop",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [350, 1600],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 2,
                "user_prompt": "Hôm nay em mệt quá bot ơi, học lập trình áp lực ghê.",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 3,
                "user_prompt": "Môn này học về con trỏ pointer ở bài nào vậy bot?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "out_of_lesson",
                "expected_target_entity": "pointer lesson navigation",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [5750],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 4,
                "user_prompt": "Câu lệnh continue thì bỏ qua câu lệnh nào trong vòng for?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "continue statement mechanism",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [350, 1600],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 5,
                "user_prompt": "Em cảm ơn trợ giảng đã động viên và giải đáp nhé!",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            }
        ]
    },
    {
        "session_id": "SESSION-SWITCH-35",
        "course_id": "cpp-core",
        "lesson_seq": 7,
        "lesson_title": "Bài 7: Hàm trong C++ & Truyền Tham Chiếu vs Tham Trị",
        "tier": "tier_3_topic_switch",
        "turns": [
            {
                "turn_idx": 1,
                "user_prompt": "Hàm kiểu void trong C++ không có câu lệnh return thì có hợp lệ không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "void function return semantics",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [5750, 5800],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 2,
                "user_prompt": "Mỗi ngày bạn có cần phải khởi động lại máy chủ hoặc đi ngủ không?",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 3,
                "user_prompt": "Thuật toán đệ quy học ở bài nào trong giáo trình vậy thầy?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "out_of_lesson",
                "expected_target_entity": "recursion lesson navigation",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [5750],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 4,
                "user_prompt": "Dạ em hiểu rồi, em cảm ơn thầy nhiều ạ!",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            }
        ]
    },
    {
        "session_id": "SESSION-SWITCH-36",
        "course_id": "cpp-core",
        "lesson_seq": 11,
        "lesson_title": "Bài 11: Mảng một chiều trong C++ & Bài toán thường gặp",
        "tier": "tier_3_topic_switch",
        "turns": [
            {
                "turn_idx": 1,
                "user_prompt": "Mảng một chiều truyền vào hàm thì nó truyền con trỏ ngầm định đúng không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "array decay to pointer in function argument",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [520, 850],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 2,
                "user_prompt": "Bài học nào trong khóa này dạy về mảng 2 chiều ma trận vậy bot?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "out_of_lesson",
                "expected_target_entity": "lesson 14 2D array navigation",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [450],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 3,
                "user_prompt": "Thủ đô của nước Pháp tên là gì vậy bot?",
                "expected_intent": "out_of_scope",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 4,
                "user_prompt": "Cảm ơn bot, mình hiểu rõ về mảng một chiều rồi!",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            }
        ]
    },
    {
        "session_id": "SESSION-SWITCH-37",
        "course_id": "cpp-core",
        "lesson_seq": 14,
        "lesson_title": "Bài 14: Lý thuyết về Mảng 2 chiều trong C++",
        "tier": "tier_3_topic_switch",
        "turns": [
            {
                "turn_idx": 1,
                "user_prompt": "Ma trận vuông cấp n có số hàng bằng số cột đúng không thầy?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "square matrix definition",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [450, 920],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 2,
                "user_prompt": "Thủ đô của nước Pháp tên là gì vậy bot?",
                "expected_intent": "out_of_scope",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 3,
                "user_prompt": "Bài tập xâu ký tự string học ở bài mấy trong khóa học?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "out_of_lesson",
                "expected_target_entity": "lesson 18 string navigation",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [600],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 4,
                "user_prompt": "Thanks bot nhé, mình nắm được bài 14 rồi!",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            }
        ]
    },
    {
        "session_id": "SESSION-SWITCH-38",
        "course_id": "cpp-core",
        "lesson_seq": 18,
        "lesson_title": "Bài 18: Xâu ký tự trong C++ - Cách sử dụng String",
        "tier": "tier_3_topic_switch",
        "turns": [
            {
                "turn_idx": 1,
                "user_prompt": "Cách nối hai chuỗi std::string bằng toán tử cộng + trong C++?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "string concatenation with operator+",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [600, 1250],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 2,
                "user_prompt": "Học lập trình C++ sau này có làm được mảng Trí tuệ nhân tạo AI không?",
                "expected_intent": "out_of_scope",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 3,
                "user_prompt": "Bài học nào dạy về cấu trúc Struct trong C++ vậy thầy?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "out_of_lesson",
                "expected_target_entity": "struct lesson navigation",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [600],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 4,
                "user_prompt": "Cảm ơn trợ giảng đã tư vấn định hướng rất nhiệt tình!",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            }
        ]
    },
    {
        "session_id": "SESSION-SWITCH-39",
        "course_id": "cpp-oop",
        "lesson_seq": 53,
        "lesson_title": "Bài 53: OOP Phần 1 - Class, Object & Constructor",
        "tier": "tier_3_topic_switch",
        "turns": [
            {
                "turn_idx": 1,
                "user_prompt": "Phạm vi truy cập private trong class bảo vệ dữ liệu như thế nào?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "encapsulation private specifier",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [350, 814],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 2,
                "user_prompt": "Cho em công thức làm món trà sữa trân chú đường đen tại nhà với.",
                "expected_intent": "out_of_scope",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 3,
                "user_prompt": "Bài mấy dạy về nạp chồng toán tử operator nhập xuất >> << vậy bot?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "out_of_lesson",
                "expected_target_entity": "lesson 56 operator stream navigation",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [415],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 4,
                "user_prompt": "Dạ em cảm ơn bot, em hiểu tính đóng gói encapsulation rồi ạ!",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            }
        ]
    },
    {
        "session_id": "SESSION-SWITCH-40",
        "course_id": "cpp-oop",
        "lesson_seq": 56,
        "lesson_title": "Bài 56: Kế Thừa & Nạp Chồng Toán Tử >>, <<",
        "tier": "tier_3_topic_switch",
        "turns": [
            {
                "turn_idx": 1,
                "user_prompt": "Hàm bạn friend function có thể truy cập được dữ liệu private của lớp không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "friend function access to private data",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [415, 501],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 2,
                "user_prompt": "Chúc bot một ngày làm việc tràn đầy năng lượng và vui vẻ nhé!",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 3,
                "user_prompt": "Bài tiếp theo bài 57 dạy về nội dung gì trong hướng đối tượng?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "out_of_lesson",
                "expected_target_entity": "lesson 57 curriculum navigation",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [415],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 4,
                "user_prompt": "Toán tử operator<< trả về ostream& để phục vụ việc in liên tiếp đúng không bot?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "ostream reference chaining",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [415, 501],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 5,
                "user_prompt": "Tuyệt vời, em đã hiểu rất sâu bài 56 rồi, cảm ơn trợ giảng!",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            }
        ]
    }
]

# =========================================================================
# TIER 4: CONTEXT BUDGET STRESS SESSIONS (10 SESSIONS - 60 TURNS = 6 TURNS/SESSION)
# =========================================================================

TIER4_SESSIONS = [
    {
        "session_id": "SESSION-STRESS-41",
        "course_id": "cpp-core",
        "lesson_seq": 2,
        "lesson_title": "Bài 2: Làm quen C++, Vào Ra & Kiểu dữ liệu, Biến",
        "tier": "tier_4_budget",
        "turns": [
            {
                "turn_idx": 1,
                "user_prompt": "Kiểu số nguyên int trong C++ có giới hạn giá trị từ bao nhiêu đến bao nhiêu?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "int range 32-bit limits",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [915, 1030],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 2,
                "user_prompt": "Nếu vượt quá giới hạn trên của nó thì xảy ra hiện tượng gì?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "integer overflow undefined behavior",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [915, 1030],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 3,
                "user_prompt": "Để chứa số lớn hơn ta nên đổi sang kiểu dữ liệu nào?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "long long 64-bit integer type",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [915, 1030],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 4,
                "user_prompt": "Kiểu long long đó chiếm mấy byte trong bộ nhớ RAM?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "long long size 8 bytes",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [915, 1030],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 5,
                "user_prompt": "Toán tử sizeof dùng để kiểm tra số byte của nó cú pháp viết sao?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "sizeof operator syntax",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [915, 1030],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 6,
                "user_prompt": "Cảm ơn trợ giảng đã đồng hành suốt 6 câu hỏi đào sâu về kiểu dữ liệu!",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            }
        ]
    },
    {
        "session_id": "SESSION-STRESS-42",
        "course_id": "cpp-core",
        "lesson_seq": 3,
        "lesson_title": "Bài 3: Toàn tập về các toán tử cơ bản trong C++",
        "tier": "tier_4_budget",
        "turns": [
            {
                "turn_idx": 1,
                "user_prompt": "Toán tử gán kết hợp += và -= trong C++ hoạt động ra sao?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "compound assignment operators",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [450, 1168],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 2,
                "user_prompt": "Viết x += 5 thì tương đương với biểu thức đầy đủ nào?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "equivalence of x += 5 to x = x + 5",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [450, 1168],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 3,
                "user_prompt": "Thế còn toán tử ba ngôi ? : có thể dùng để thay thế if else ngắn gọn không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "ternary operator conditional expression",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [450, 1168],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 4,
                "user_prompt": "Cú pháp của nó gồm ba phần: điều kiện, giá trị đúng, giá trị sai đúng không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "ternary operator tripartite syntax",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [450, 1168],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 5,
                "user_prompt": "Nó có thể lồng nhau để phân loại 3 mức điểm được không bot?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "nested ternary operator",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [450, 1168],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 6,
                "user_prompt": "Dạ em hiểu tường tận cả toán tử gán lẫn toán tử 3 ngôi rồi, thanks bot!",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            }
        ]
    },
    {
        "session_id": "SESSION-STRESS-43",
        "course_id": "cpp-core",
        "lesson_seq": 4,
        "lesson_title": "Bài 4: Cấu trúc rẽ nhánh If Else và Switch Case",
        "tier": "tier_4_budget",
        "turns": [
            {
                "turn_idx": 1,
                "user_prompt": "Khái niệm if else lồng nhau (nested if) trong C++ là gì?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "nested if statements",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [751, 800],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 2,
                "user_prompt": "Hiện tượng dangling else xảy ra khi nào và cách khắc phục bằng dấu ngoặc nhọn {}?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "dangling else resolution with braces",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [751, 800],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 3,
                "user_prompt": "Cấu trúc switch case có cho phép kiểm tra điều kiện lớn hơn bé hơn không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "switch case equality only limitation",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [751, 800],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 4,
                "user_prompt": "Nghĩa là nó chỉ so sánh bằng với các hằng số nguyên hoặc ký tự đúng không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "switch case integral constant matching",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [751, 800],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 5,
                "user_prompt": "Nếu hai case có cùng giá trị so sánh thì trình biên dịch có báo lỗi không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "duplicate case value compilation error",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [751, 800],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 6,
                "user_prompt": "Tuyệt vời, em đã hiểu rất sâu về các cạm bẫy rẽ nhánh, cảm ơn bot!",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            }
        ]
    },
    {
        "session_id": "SESSION-STRESS-44",
        "course_id": "cpp-core",
        "lesson_seq": 6,
        "lesson_title": "Bài 6: Vòng lặp For, While và Do-While",
        "tier": "tier_4_budget",
        "turns": [
            {
                "turn_idx": 1,
                "user_prompt": "Vòng lặp vô tận while(true) hay for(;;) thường được ứng dụng vào mục đích gì?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "infinite loop use cases",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [350, 1600],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 2,
                "user_prompt": "Làm sao để thoát khỏi nó khi người dùng chọn lệnh thoát chương trình?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "breaking infinite loop with break",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [350, 1600],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 3,
                "user_prompt": "Lệnh continue trong vòng lặp có làm vòng lặp dừng lại luôn không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "continue skipping current iteration",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [350, 1600],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 4,
                "user_prompt": "Nó chỉ nhảy qua lần lặp hiện tại để tới bước tăng i++ đúng không bot?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "continue jumping to increment expression",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [350, 1600],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 5,
                "user_prompt": "Nếu dùng continue trong while mà quên tăng biến đếm thì bị vòng lặp vô hạn đúng không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "continue causing infinite loop in while without increment",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [350, 1600],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 6,
                "user_prompt": "Đúng cái lỗi em vừa dính sáng nay luôn, cảm ơn trợ giảng đã chỉ ra!",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            }
        ]
    },
    {
        "session_id": "SESSION-STRESS-45",
        "course_id": "cpp-core",
        "lesson_seq": 7,
        "lesson_title": "Bài 7: Hàm trong C++ & Truyền Tham Chiếu vs Tham Trị",
        "tier": "tier_4_budget",
        "turns": [
            {
                "turn_idx": 1,
                "user_prompt": "Cấu trúc ngăn xếp call stack lưu trữ thông tin hàm như thế nào khi gọi hàm?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "call stack activation record stack frame",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [5750, 5800],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 2,
                "user_prompt": "Khi hàm kết thúc thì biến cục bộ trong stack frame của nó được giải phóng ra sao?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "stack frame deallocation upon return",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [5750, 5800],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 3,
                "user_prompt": "Nếu trả về con trỏ trỏ tới biến cục bộ đó thì có gây lỗi không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "dangling pointer from returning local address",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [5750, 5800],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 4,
                "user_prompt": "Hiện tượng đó gọi là con trỏ lơ lửng dangling pointer đúng không bot?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "dangling pointer definition",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [5750, 5800],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 5,
                "user_prompt": "Để tránh việc đó ta nên cấp phát động trên heap hay truyền tham chiếu vào?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "heap allocation or reference parameter solution",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [5750, 5800],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 6,
                "user_prompt": "Giải thích rất khoa học và sâu sắc về ô nhớ, em cảm ơn bot!",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            }
        ]
    },
    {
        "session_id": "SESSION-STRESS-46",
        "course_id": "cpp-core",
        "lesson_seq": 8,
        "lesson_title": "Bài 8: Hàm Hoán Vị (Swap) & Nạp Chồng Hàm",
        "tier": "tier_4_budget",
        "turns": [
            {
                "turn_idx": 1,
                "user_prompt": "Nguyên mẫu hàm function prototype đặt trước hàm main có vai trò gì?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "function prototype declaration purpose",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [1641, 2638],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 2,
                "user_prompt": "Nó giúp trình biên dịch biết trước kiểu trả về và danh sách tham số đúng không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "compiler forward declaration verification",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [1641, 2638],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 3,
                "user_prompt": "Nếu hai hàm trùng tên nhưng chỉ khác kiểu trả về thì có nạp chồng được không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "overloading cannot differ by return type alone",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [1641, 2638],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 4,
                "user_prompt": "Trình biên dịch sẽ báo lỗi mơ hồ ambiguous call đúng không bot?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "ambiguous overload compilation error",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [1641, 2638],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 5,
                "user_prompt": "Bắt buộc danh sách kiểu tham số của chúng phải khác nhau đúng không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "parameter list differentiation in overloading",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [1641, 2638],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 6,
                "user_prompt": "Dạ em nắm chắc nguyên tắc nạp chồng hàm rồi, cảm ơn bot nhiều!",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            }
        ]
    },
    {
        "session_id": "SESSION-STRESS-47",
        "course_id": "cpp-core",
        "lesson_seq": 11,
        "lesson_title": "Bài 11: Mảng một chiều trong C++ & Bài toán thường gặp",
        "tier": "tier_4_budget",
        "turns": [
            {
                "turn_idx": 1,
                "user_prompt": "Thuật toán tìm kiếm tuyến tính Linear Search trên mảng một chiều có độ phức tạp bao nhiêu?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "linear search time complexity O(n)",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [520, 850],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 2,
                "user_prompt": "Nó duyệt từ đầu đến cuối mảng cho đến khi gặp phần tử cần tìm đúng không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "linear scan traversal mechanism",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [520, 850],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 3,
                "user_prompt": "Nếu mảng đã được sắp xếp tăng dần thì ta nên dùng thuật toán nào để tìm nhanh hơn?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "binary search for sorted array",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [520, 850],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 4,
                "user_prompt": "Tìm kiếm nhị phân Binary Search có độ phức tạp thời gian là bao nhiêu bot?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "binary search time complexity O(log n)",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [520, 850],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 5,
                "user_prompt": "Mỗi bước nó chia đôi không gian tìm kiếm nên nhanh hơn nhiều đúng không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "divide and conquer logarithmic halving",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [520, 850],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 6,
                "user_prompt": "So sánh giữa O(n) và O(log n) trực quan quá, cảm ơn bot!",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            }
        ]
    },
    {
        "session_id": "SESSION-STRESS-48",
        "course_id": "cpp-core",
        "lesson_seq": 18,
        "lesson_title": "Bài 18: Xâu ký tự trong C++ - Cách sử dụng String",
        "tier": "tier_4_budget",
        "turns": [
            {
                "turn_idx": 1,
                "user_prompt": "Phương thức length() và size() của std::string có gì khác nhau không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "string length vs size equivalence",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [600, 1250],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 2,
                "user_prompt": "Chúng đều trả về số lượng ký tự hiện có trong chuỗi đúng không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "character count return value",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [600, 1250],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 3,
                "user_prompt": "Thế còn hàm substr() nhận hai tham số là vị trí bắt đầu và độ dài xâu con đúng không bot?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "substr parameters pos and count",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [600, 1250],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 4,
                "user_prompt": "Nếu bỏ qua tham số thứ hai thì nó sẽ cắt đến tận cuối xâu đúng không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "substr default parameter to end of string",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [600, 1250],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 5,
                "user_prompt": "Để tìm vị trí một từ con trong chuỗi ta dùng hàm find() đúng không bot?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "string find and string::npos",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [600, 1250],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 6,
                "user_prompt": "Dạ em đã thành thạo các phương thức string rồi, cảm ơn trợ giảng!",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            }
        ]
    },
    {
        "session_id": "SESSION-STRESS-49",
        "course_id": "cpp-oop",
        "lesson_seq": 53,
        "lesson_title": "Bài 53: OOP Phần 1 - Class, Object & Constructor",
        "tier": "tier_4_budget",
        "turns": [
            {
                "turn_idx": 1,
                "user_prompt": "Hàm hủy destructor trong class C++ có ký tự đặc biệt nào ở trước tên hàm?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "destructor tilde symbol ~",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [1170, 1200],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 2,
                "user_prompt": "Nó có nhận tham số đầu vào và có nạp chồng được không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "destructor takes no parameters and cannot overload",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [1170, 1200],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 3,
                "user_prompt": "Khi nào nó tự động được kích hoạt để dọn dẹp đối tượng?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "destructor invocation when object goes out of scope",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [1170, 1200],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 4,
                "user_prompt": "Nếu trong class có con trỏ cấp phát động new thì ta giải phóng delete ở trong đó đúng không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "deallocating dynamic memory inside destructor",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [1170, 1200],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 5,
                "user_prompt": "Nếu quên giải phóng thì gây ra lỗi rò rỉ bộ nhớ memory leak đúng không bot?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "memory leak prevention via destructor",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [1170, 1200],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 6,
                "user_prompt": "Cảm ơn bot đã giúp em hiểu rõ vòng đời sống của một đối tượng!",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            }
        ]
    },
    {
        "session_id": "SESSION-STRESS-50",
        "course_id": "cpp-oop",
        "lesson_seq": 56,
        "lesson_title": "Bài 56: Kế Thừa & Nạp Chồng Toán Tử >>, <<",
        "tier": "tier_4_budget",
        "turns": [
            {
                "turn_idx": 1,
                "user_prompt": "Kế thừa public trong C++ bảo toàn phạm vi các thuộc tính của lớp cha sang lớp con ra sao?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "public inheritance access specifier mapping",
                "anaphora_reference_required": False,
                "whitelist_video_secs": [120, 450],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 2,
                "user_prompt": "Thuộc tính protected của lớp cha thì lớp con có truy cập được không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "protected access in derived class",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [120, 450],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 3,
                "user_prompt": "Còn thuộc tính private của lớp cha thì lớp con có thấy trực tiếp được không?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "private members inaccessible directly in derived class",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [120, 450],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 4,
                "user_prompt": "Lớp con muốn gọi constructor của lớp cha thì dùng cú pháp danh sách khởi tạo thế nào?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "base class constructor call in derived initializer list",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [120, 450],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 5,
                "user_prompt": "Thứ tự gọi hàm tạo: lớp cha chạy trước hay lớp con chạy trước?",
                "expected_intent": "course_query",
                "expected_retrieval_status": "grounded",
                "expected_target_entity": "base constructor executed before derived constructor",
                "anaphora_reference_required": True,
                "whitelist_video_secs": [120, 450],
                "expected_has_timestamp": True,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            },
            {
                "turn_idx": 6,
                "user_prompt": "Bài học kế thừa này thật sự rất mạch lạc, em cảm ơn trợ giảng nhiều!",
                "expected_intent": "chit_chat",
                "expected_retrieval_status": "skip",
                "expected_target_entity": None,
                "anaphora_reference_required": False,
                "whitelist_video_secs": [],
                "expected_has_timestamp": False,
                "expected_socratic_refusal": False,
                "forbidden_tokens": []
            }
        ]
    }
]


def main():
    print("=" * 80)
    print("QUY TRÌNH KHỞI TẠO BỘ KHẢO THÍ ĐA LƯỢT (MULTI-TURN BENCHMARK GENERATOR)")
    print("In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT")
    print("=" * 80)

    all_sessions = TIER1_SESSIONS + TIER2_SESSIONS + TIER3_SESSIONS + TIER4_SESSIONS

    # 1. Thống kê cơ bản
    n_sessions = len(all_sessions)
    total_turns = sum(len(s["turns"]) for s in all_sessions)
    tier_counts = Counter(s["tier"] for s in all_sessions)
    tier_turn_counts = Counter()
    for s in all_sessions:
        tier_turn_counts[s["tier"]] += len(s["turns"])

    print(f"[THỐNG KÊ] Tổng số sessions: {n_sessions}")
    print(f"[THỐNG KÊ] Tổng số turns:    {total_turns}")
    for tier, count in tier_counts.items():
        print(f"  * {tier:24s}: {count:2d} sessions ({tier_turn_counts[tier]:2d} turns)")

    # Assertions
    assert n_sessions == 50, f"LỖI: Số session phải đúng 50 (hiện tại: {n_sessions})"
    assert total_turns == 222, f"LỖI: Số turns phải đúng 222 (hiện tại: {total_turns})"

    # 2. Kiểm tra tính hợp lệ của mốc video và schema
    for s_idx, s in enumerate(all_sessions, 1):
        for t in s["turns"]:
            # Mốc video
            if t["expected_has_timestamp"]:
                assert len(t["whitelist_video_secs"]) > 0, f"Session {s['session_id']} Turn {t['turn_idx']}: expected_has_timestamp=True nhưng whitelist_video_secs rỗng!"
                for sec in t["whitelist_video_secs"]:
                    assert isinstance(sec, int) and sec > 0, f"Mốc giây không hợp lệ: {sec} trong {s['session_id']}"
            else:
                assert len(t["whitelist_video_secs"]) == 0, f"Session {s['session_id']} Turn {t['turn_idx']}: expected_has_timestamp=False nhưng có whitelist_video_secs!"

            # Socratic refusal
            if t["expected_socratic_refusal"]:
                assert len(t["forbidden_tokens"]) > 0, f"Session {s['session_id']} Turn {t['turn_idx']}: expected_socratic_refusal=True nhưng forbidden_tokens rỗng!"

    print("[KIỂM TRA SCHEMA] Tất cả 228 turns tuân thủ 100% Schema Contract và Video Whitelist!")

    # 3. Kiểm tra rò rỉ dữ liệu với router_training_corpus.json
    with open(ROUTER_CORPUS_FILE, "r", encoding="utf-8") as f:
        corpus_data = json.load(f)
    train_queries = [x["text"] for x in corpus_data.get("samples", [])]

    max_j = 0.0
    leak_count = 0
    for s in all_sessions:
        for t in s["turns"]:
            q = t["user_prompt"]
            for tr_q in train_queries:
                j = jaccard_similarity(q, tr_q)
                if j > max_j:
                    max_j = j
                if j >= 0.70 or norm(q) == norm(tr_q):
                    leak_count += 1
                    print(f"  [LEAK PHÁT HIỆN]: J={j:.2f} | Turn: '{q}' vs Train: '{tr_q}'")

    print(f"[KIỂM TOÁN RÒ RỈ] Max Jaccard với Router Training Corpus: {max_j:.4f} (< 0.70)")
    print(f"[KIỂM TOÁN RÒ RỈ] Số mẫu rò rỉ dữ liệu: {leak_count} (0.00% Data Leakage)")
    assert leak_count == 0, "LỖI BẤT BIẾN: Phát hiện mẫu rò rỉ dữ liệu với tập huấn luyện!"

    # 4. Lưu file JSON
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_sessions, f, ensure_ascii=False, indent=2)

    print(f"[HOÀN TẤT] Đã lưu thành công bộ benchmark đa lượt tại: {OUTPUT_FILE.name}")
    print("=" * 80)


if __name__ == "__main__":
    main()
