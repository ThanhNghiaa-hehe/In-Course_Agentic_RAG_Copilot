"""
End-to-End Anti-Parroting, Temporal Shift Context Hygiene & TelemetryCritic Regression Tests.

Covers:
1. context_assembly_node & _clean_assistant_history_text:
   - Overlong t-1 (>450 chars) and older t < k-1 (>200 chars) assistant turns are
     truncated cleanly at natural sentence boundaries WITHOUT '[đã rút gọn...]'
     or '[rút gọn...]' bracket tags that 7B models echo.
   - Trailing Socratic '?' question on overlong t-1 turn is preserved when present.
   - Opening greetings/boilerplate ('Chào bạn! Theo đoạn video,') and closing filler
     ('Nếu còn thắc mắc gì nữa hãy hỏi nhé!') are stripped from assistant history
     while preserving C++ code and keywords.
   - Temporal shift (06:13 -> 17:22 or 40:09, current_video_sec jump >= 45s,
     out_of_lesson, or lesson switch) prunes stale assistant history and injects
     the anti-parroting current-turn focus directive.
   - SOFT_NUDGE_TURN_TRIGGER (turn > 6) forbids writing sample C++ code blocks and
     enforces mandatory Socratic '?' ending (never generic 'nhé!').
2. StreamingInternalArtifactSanitizer & crag_grader_node deictic safety:
   - Strips echoed internal bracket tags and leading 'Chào bạn!' without harming C++ a[i].
   - missing_deictic_sec=True clears unanchored suggested_timestamps and last_video_sec.
3. TelemetryCriticService:
   - Valid in-video temporal queries ('còn phút thứ 6 thì sao', 'phút thứ 6 nói gì')
     routed to course_query have is_topic_intruded == False.
   - Genuine off-topic ('phút thứ 6 trận bóng đá tỷ số bao nhiêu') if routed to
     course_query STILL triggers is_topic_intruded == True (turn_score <= 25).
   - Genuine missing '?' (even when C++ ternary `a ? b : c` exists in inline/fenced code)
     and '#include' / 'int main()' in course_query response STILL trigger warning/violation.
   - Empty-whitelist hallucinated <timestamp> tags are penalized as unverified.
"""

import os

if os.environ.get("SAFE_CPU_MODE") == "1":
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_WAIT_POLICY"] = "PASSIVE"

import torch

torch.set_num_threads(1)
try:
    torch.set_num_interop_threads(1)
except RuntimeError:
    pass

import pytest

from app.agent.prompts import OUT_OF_LESSON_PROMPT, SOCRATIC_GROUNDED_PROMPT
from app.config import settings

settings.RERANK_CPU_THREADS = 1
from app.services.chat import StreamingInternalArtifactSanitizer
from app.services.chat_graph import (
    _clean_assistant_history_text,
    context_assembly_node,
    crag_grader_node,
)
from app.services.telemetry_critic import get_telemetry_critic_service


# ==============================================================================
# 1. CONTEXT ASSEMBLY & ASSISTANT HISTORY SANITIZATION
# ==============================================================================


@pytest.mark.asyncio
async def test_overlong_t_minus_1_and_older_turns_truncate_without_bracket_tags():
    """
    Overlong t-1 (>450 chars) and older t < k-1 (>200 chars) assistant turns must
    truncate cleanly at sentence boundaries without '[đã rút gọn...]' or '[rút gọn...]'
    bracket markers, while preserving a trailing Socratic '?' question on t-1.
    """
    older_verbose = (
        "Tính đóng gói (Encapsulation) giúp che giấu dữ liệu nội bộ của đối tượng bằng từ khóa private. "
        "Các thành phần bên ngoài lớp chỉ được phép tương tác thông qua hệ thống phương thức getter và setter hợp lệ. "
        "Nhờ cơ chế kiểm soát truy cập chặt chẽ này, dữ liệu của đối tượng luôn đảm bảo tính toàn vẹn và tránh bị "
        "gán các giá trị sai lệch từ bên ngoài hàm khác."
    )
    assert len(older_verbose) > 200

    t_minus_1_verbose = (
        "Hàm khởi tạo (Constructor) là phương thức đặc biệt có tên trùng hoàn toàn với tên lớp và không có kiểu trả về. "
        "Nó được trình biên dịch tự động kích hoạt ngay thời điểm đối tượng được cấp phát vùng nhớ để khởi gán giá trị ban đầu. "
        "Một lớp có thể nạp chồng nhiều hàm khởi tạo với danh sách tham số khác nhau nhằm linh hoạt cách tạo đối tượng. "
        "Nếu lập trình viên tự định nghĩa hàm khởi tạo có tham số thì trình biên dịch sẽ không tự sinh hàm khởi tạo mặc định nữa. "
        "Theo bạn, chuyện gì sẽ xảy ra nếu khai báo `SinhVien sv;` khi lớp chỉ có hàm tạo 4 tham số?"
    )
    assert len(t_minus_1_verbose) > 450

    state = {
        "prompt": "Giải thích thêm về hàm tạo mặc định ạ",
        "user_message_content": "[NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC]\nNguồn Bài 53: Constructor mặc định.",
        "system_prompt": SOCRATIC_GROUNDED_PROMPT,
        "lesson_seq": 53,
        "prev_lesson_seq": 53,
        "retrieval_status": "grounded",
        "messages": [
            {"role": "user", "content": "Đóng gói là gì?"},
            {"role": "assistant", "content": older_verbose},
            {"role": "user", "content": "Hàm khởi tạo hoạt động thế nào?"},
            {"role": "assistant", "content": t_minus_1_verbose},
        ],
        "conversation_summary": None,
    }

    res = await context_assembly_node(state)
    assistant_msgs = [m["content"] for m in res["assembled_messages"] if m["role"] == "assistant"]
    assert len(assistant_msgs) == 2

    older_cleaned, t1_cleaned = assistant_msgs[0], assistant_msgs[1]

    for msg_text in (older_cleaned, t1_cleaned):
        assert "[đã rút gọn" not in msg_text.lower()
        assert "[rút gọn" not in msg_text.lower()

    assert len(older_cleaned) <= 205
    assert older_cleaned.endswith("...")

    assert len(t1_cleaned) <= 420
    assert t1_cleaned.endswith("SinhVien sv;` khi lớp chỉ có hàm tạo 4 tham số?")


def test_clean_assistant_history_strips_greetings_video_boilerplate_and_closing_filler():
    """
    Opening 'Chào bạn! Theo đoạn video,' and closing 'Nếu còn thắc mắc gì nữa hãy hỏi nhé!'
    must be stripped from assistant history while preserving technical content and C++ code.
    """
    raw_assistant = (
        "Chào bạn! Theo đoạn video, thầy đang giải thích về khái niệm Encapsulation "
        "(tính đóng gói) thông qua việc đặt thuộc tính `string ma;` ở phạm vi `private` "
        "tại <timestamp sec=\"373\">06:13</timestamp>.\n"
        "Tại sao chúng ta không nên để mọi thuộc tính ở phạm vi `public`? "
        "Nếu còn thắc mắc gì nữa hãy hỏi nhé!\n\n"
        "📍 **Mốc video bài giảng:** <timestamp sec=\"373\">06:13</timestamp>"
    )

    cleaned = _clean_assistant_history_text(raw_assistant)

    assert not cleaned.lower().startswith("chào bạn")
    assert "theo đoạn video" not in cleaned.lower()
    assert "nếu còn thắc mắc" not in cleaned.lower()
    assert "hãy hỏi nhé" not in cleaned.lower()
    assert "<timestamp" not in cleaned.lower()
    assert "📍" not in cleaned

    # Core technical explanation and genuine Socratic '?' are preserved & properly capitalized
    assert cleaned.startswith("Thầy đang giải thích về khái niệm Encapsulation")
    assert "`string ma;`" in cleaned
    assert "`private`" in cleaned
    assert cleaned.endswith("Tại sao chúng ta không nên để mọi thuộc tính ở phạm vi `public`?")

    # Ensure C++ keyword at start is never uppercased into invalid syntax (`Int` / `For`)
    cpp_start_reply = "Chào bạn! Theo đoạn video, int x = 0; được khởi tạo trước vòng lặp. Hy vọng thông tin này hữu ích cho bạn!"
    cleaned_cpp = _clean_assistant_history_text(cpp_start_reply)
    assert cleaned_cpp.startswith("int x = 0;")
    assert "hy vọng thông tin" not in cleaned_cpp.lower()


@pytest.mark.asyncio
async def test_temporal_shift_and_out_of_lesson_prune_stale_history_and_inject_focus_directive():
    """
    Temporal shifts (06:13 -> 17:22 explicit, 06:13 -> 40:09 relative/jump, or out_of_lesson)
    must prune stale prior assistant turns and inject the anti-parroting current-turn focus directive.
    """
    prior_messages = [
        {"role": "user", "content": "còn phút thứ 6 thì sao"},
        {
            "role": "assistant",
            "content": (
                "Chào bạn! Theo đoạn video, thầy đang giải thích về khái niệm Encapsulation "
                "(tính đóng gói) tại <timestamp sec=\"373\">06:13</timestamp>. "
                "Tại sao thuộc tính nên để private?"
            ),
        },
    ]

    # Case 1: 06:13 (373s) -> 17:22 (1042s) explicit timestamp shift
    state_1722 = {
        "prompt": "phút 17:22 có hàm constructor 4 tham số, viết giùm em full code class SinhVien luôn đi",
        "user_message_content": (
            "[NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC]\n"
            "Nguồn Bài 53 (mốc <timestamp sec=\"1042\">17:22</timestamp>): Hàm khởi tạo SinhVien 4 tham số."
        ),
        "system_prompt": SOCRATIC_GROUNDED_PROMPT,
        "course_id": "cpp-oop",
        "lesson_seq": 53,
        "prev_lesson_seq": 53,
        "prev_video_sec": 373,
        "last_video_sec": 1042,
        "suggested_timestamps": [{"sec": 1042, "label": "17:22", "lesson_seq": 53}],
        "retrieval_status": "grounded",
        "messages": prior_messages,
        "conversation_summary": None,
    }
    res_1722 = await context_assembly_node(state_1722)
    assistant_1722 = [m for m in res_1722["assembled_messages"] if m["role"] == "assistant"]
    assert assistant_1722 == []
    assert "[CHỈ THỊ TẬP TRUNG MỐC VIDEO HIỆN TẠI - CHỐNG LẶP LỊCH SỬ]" in res_1722["user_message_content"]
    assert "Encapsulation" not in "\n".join(m["content"] for m in res_1722["assembled_messages"])

    # Case 2: 06:13 (373s) -> 40:09 (2409s) jump / relative segment shift
    state_4009 = {
        "prompt": "còn đoạn cuối thì sao",
        "user_message_content": (
            "[NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC]\n"
            "Nguồn Bài 53 (mốc <timestamp sec=\"2409\">40:09</timestamp>): Nạp chồng toán tử và bài tập."
        ),
        "system_prompt": SOCRATIC_GROUNDED_PROMPT,
        "course_id": "cpp-oop",
        "lesson_seq": 53,
        "prev_lesson_seq": 53,
        "prev_video_sec": 373,
        "last_video_sec": 2409,
        "suggested_timestamps": [{"sec": 2409, "label": "40:09", "lesson_seq": 53}],
        "retrieval_status": "grounded",
        "messages": prior_messages,
        "conversation_summary": None,
    }
    res_4009 = await context_assembly_node(state_4009)
    assistant_4009 = [m for m in res_4009["assembled_messages"] if m["role"] == "assistant"]
    assert assistant_4009 == []
    assert "[CHỈ THỊ TẬP TRUNG MỐC VIDEO HIỆN TẠI - CHỐNG LẶP LỊCH SỬ]" in res_4009["user_message_content"]

    # Case 3: out_of_lesson shift (e.g. asking about pointers while in Bài 53)
    state_ool = {
        "prompt": "tôi muốn học con trỏ thì học bài nào",
        "user_message_content": "[TIẾN ĐỘ BÀI HỌC]: Chủ đề Con trỏ được dạy tại Bài 42 (khóa cpp-core).",
        "system_prompt": OUT_OF_LESSON_PROMPT,
        "course_id": "cpp-oop",
        "lesson_seq": 53,
        "prev_lesson_seq": 53,
        "retrieval_status": "out_of_lesson",
        "messages": prior_messages,
        "conversation_summary": None,
    }
    res_ool = await context_assembly_node(state_ool)
    assistant_ool = [m for m in res_ool["assembled_messages"] if m["role"] == "assistant"]
    assert assistant_ool == []
    assert "[CHỈ THỊ TẬP TRUNG LƯỢT HIỆN TẠI - CHỐNG LẶP LỊCH SỬ]" in res_ool["user_message_content"]
    assert 'KHÔNG mở đầu bằng "Chào bạn!" hay "Theo đoạn video..."' in res_ool["user_message_content"]


@pytest.mark.asyncio
async def test_soft_nudge_turn_trigger_preserves_question_mark_and_forbids_sample_code():
    """
    When turn_count > settings.SOFT_NUDGE_TURN_TRIGGER (turn > 6), the pedagogical
    soft nudge must NEVER ask for sample code blocks and must explicitly require
    ending with 1 Socratic '?' question instead of 'nhé!'.
    """
    history_12_msgs = []
    for i in range(settings.SOFT_NUDGE_TURN_TRIGGER):
        history_12_msgs.append({"role": "user", "content": f"Câu hỏi lượt {i + 1} về hàm hủy?"})
        history_12_msgs.append(
            {
                "role": "assistant",
                "content": f"Ở lượt {i + 1}, hàm hủy `~SinhVien()` dọn dẹp tài nguyên. Khi nào nó được gọi?",
            }
        )

    state = {
        "prompt": "tóm lại hàm hủy ~SinhVien dùng làm gì và khi nào chạy",
        "user_message_content": "[NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC]\nNguồn Bài 53: Hàm hủy ~SinhVien.",
        "system_prompt": SOCRATIC_GROUNDED_PROMPT,
        "lesson_seq": 53,
        "prev_lesson_seq": 53,
        "retrieval_status": "grounded",
        "messages": history_12_msgs,
        "conversation_summary": None,
    }

    res = await context_assembly_node(state)
    assert res["turn_count"] == settings.SOFT_NUDGE_TURN_TRIGGER + 1

    final_user = res["user_message_content"]
    assert "[HƯỚNG DẪN SƯ PHẠM ĐA LƯỢT]" in final_user
    assert "TUYỆT ĐỐI KHÔNG tự viết thêm khối code C++ mẫu dài" in final_user
    assert "`?`" in final_user
    assert "KHÔNG kết thúc bằng câu xã giao cảm thán (`nhé!`)" in final_user
    assert "tự mở IDE gõ chạy thử mã nguồn" not in final_user


def test_streaming_internal_artifact_sanitizer_strips_echoed_tags_and_preserves_cpp_arrays():
    """
    StreamingInternalArtifactSanitizer must strip echoed internal truncation/code tags
    and leading 'Chào bạn!' / 'Theo đoạn video,' (when forbid_video_opening=True)
    while preserving C++ array indexing a[i] and int arr[100].
    """
    sanitizer = StreamingInternalArtifactSanitizer(forbid_video_opening=False)
    chunks = [
        "Chào ",
        "bạn! ",
        "mảng ",
        "`int arr[100];` ",
        "truy cập `arr[i]`... ",
        "[đã rút gọn ",
        "phản hồi dài ở lượt trước]",
        " rất nhanh. Bạn thấy chỉ số tối đa là gì?",
    ]
    emitted = []
    for ch in chunks:
        emitted.extend(sanitizer.process(ch))
    emitted.extend(sanitizer.flush())
    result = "".join(emitted)

    assert not result.lower().startswith("chào bạn")
    assert result.startswith("Mảng `int arr[100];`")
    assert "`arr[i]`" in result
    assert "[đã rút gọn" not in result
    assert result.endswith("Bạn thấy chỉ số tối đa là gì?")

    ool_sanitizer = StreamingInternalArtifactSanitizer(forbid_video_opening=True)
    ool_tokens = ["Chào bạn! ", "Theo đoạn video, ", "chủ đề con trỏ nằm ở Bài 42. Bạn muốn xem Bài 42 không?"]
    ool_out = "".join([p for tok in ool_tokens for p in ool_sanitizer.process(tok)] + ool_sanitizer.flush())
    assert ool_out.startswith("Chủ đề con trỏ nằm ở Bài 42.")


@pytest.mark.asyncio
async def test_crag_grader_missing_deictic_sec_clears_unanchored_timestamps():
    """
    When missing_deictic_sec=True ('đoạn này là sao' with current_video_sec=None),
    crag_grader_node must clear unanchored suggested_timestamps and last_video_sec.
    """
    state = {
        "prompt": "đoạn này là sao",
        "search_query": "đoạn này là sao",
        "course_id": "cpp-oop",
        "lesson_seq": 53,
        "retrieved_chunks": [
            {
                "id": "random-chunk",
                "content_type": "video_transcript",
                "lesson_seq": 53,
                "start_sec": 920,
                "start_label": "15:20",
                "timestamp_tag": '<timestamp sec="920">15:20</timestamp>',
                "raw_text": "Ở đoạn này chúng ta xét tiếp ví dụ...",
                "confidence_score": 0.42,
                "is_approximate": False,
            }
        ],
        "retrieval_status": "grounded",
        "is_low_confidence": False,
        "target_lesson_seq": None,
        "is_curriculum_navigation": False,
        "missing_deictic_sec": True,
        "last_video_sec": None,
        "last_lesson_seq": 53,
    }
    res = await crag_grader_node(state)
    assert res["suggested_timestamps"] == []
    assert res["sources"] == []
    assert res["last_video_sec"] is None
    assert "[LƯU Ý LÀM RÕ MỐC THỜI GIAN VIDEO]" in res["user_message_content"]


# ==============================================================================
# 2. TELEMETRY CRITIC ALIGNMENT & STRICT GUARDRAILS
# ==============================================================================


@pytest.mark.parametrize(
    "valid_temporal_prompt",
    [
        "còn phút thứ 6 thì sao",
        "phút thứ 6 nói gì",
        "đoạn này là sao",
        "tôi muốn học con trỏ hay vòng lặp thì xem bài nào",
    ],
)
def test_telemetry_critic_accepts_valid_in_video_temporal_and_ambiguous_queries(valid_temporal_prompt: str):
    """
    Valid in-video temporal/deictic queries ('còn phút thứ 6 thì sao', 'phút thứ 6 nói gì',
    'đoạn này là sao') and ambiguous curriculum disjunction queries routed to course_query
    must have is_topic_intruded == False and multi_turn_intent_fidelity == 1.0.
    """
    critic = get_telemetry_critic_service()
    entry = {
        "turn": 3,
        "course_id": "cpp-oop",
        "lesson_seq": 53,
        "prompt": valid_temporal_prompt,
        "response_text": (
            "Tại mốc <timestamp sec=\"373\">06:13</timestamp>, bài giảng phân tích tính đóng gói "
            "khi đặt thuộc tính ở phạm vi `private`. Theo bạn, vì sao không nên để thuộc tính `public`?\n\n"
            "📍 **Mốc video bài giảng:** <timestamp sec=\"373\">06:13</timestamp>"
        ),
        "router": {"intent": "course_query", "used_fast_path": False},
        "crag": {"retrieval_status": "grounded", "target_lesson_seq": None},
        "timestamps": [{"sec": 373, "label": "06:13", "lesson_seq": 53}],
        "latency": {"ttft_ms": 950, "total_ms": 1800, "tokens_per_sec": 42.0},
    }

    res = critic.analyze_turn(entry, had_prior_course_query=True)
    assert res["is_topic_intruded"] is False
    assert res["is_intent_hijacked"] is False
    assert res["multi_turn_intent_fidelity"] == 1.0
    assert res["turn_score"] >= 90


def test_telemetry_critic_flags_genuine_off_topic_sports_minute_query():
    """
    Genuine off-topic 'phút thứ 6 trận bóng đá tỷ số bao nhiêu' if misrouted to
    course_query MUST still trigger is_topic_intruded == True and cap turn_score <= 25.
    """
    critic = get_telemetry_critic_service()
    entry = {
        "turn": 10,
        "course_id": "cpp-oop",
        "lesson_seq": 53,
        "prompt": "phút thứ 6 trận bóng đá tỷ số bao nhiêu",
        "response_text": "Mình chỉ hỗ trợ kiến thức lập trình C++. Bạn muốn xem lại phần nào của Bài 53?",
        "router": {"intent": "course_query", "used_fast_path": False},
        "crag": {"retrieval_status": "coverage_gap", "target_lesson_seq": None},
        "timestamps": [],
        "latency": {"ttft_ms": 800, "total_ms": 1500, "tokens_per_sec": 38.0},
    }

    res = critic.analyze_turn(entry, had_prior_course_query=True)
    assert res["is_topic_intruded"] is True
    assert res["multi_turn_intent_fidelity"] == 0.0
    assert res["turn_score"] <= 25
    assert any("Topic Intrusion Hijacking" in v for v in res["socratic_violations"])


def test_telemetry_critic_strictly_flags_missing_question_include_main_and_unverified_ts():
    """
    1. Missing '?' in prose (even when C++ ternary `a ? b : c` appears in inline/fenced code)
       must trigger the missing-question warning in course_query.
    2. '#include <iostream>' (even in short code blocks) and 'int main()' must trigger
       socratic_compliance == False with explicit violations.
    3. <timestamp> emitted when suggested_ts == [] must be flagged as unverified.
    """
    critic = get_telemetry_critic_service()

    # 1. Missing Socratic '?' in prose (with inline C++ ternary trying to spoof '?') + unverified timestamp
    no_q_entry = {
        "turn": 5,
        "course_id": "cpp-core",
        "lesson_seq": 11,
        "prompt": "toán tử điều kiện hoạt động thế nào",
        "response_text": (
            "Biểu thức điều kiện viết dạng `int res = (a > b) ? a : b;` giúp chọn giá trị ngắn gọn "
            "tại <timestamp sec=\"999\">16:39</timestamp>. Nếu còn thắc mắc gì nữa hãy hỏi nhé!\n\n"
            "📍 **Mốc video bài giảng:** <timestamp sec=\"999\">16:39</timestamp>"
        ),
        "router": {"intent": "course_query", "used_fast_path": False},
        "crag": {"retrieval_status": "grounded", "target_lesson_seq": None},
        "timestamps": [],
        "latency": {"ttft_ms": 700, "total_ms": 1400, "tokens_per_sec": 45.0},
    }
    no_q_res = critic.analyze_turn(no_q_entry)
    assert any("Thiếu câu hỏi gợi mở" in w for w in no_q_res["warnings"])
    assert any("Whitelist" in w for w in no_q_res["warnings"])
    assert no_q_res["turn_score"] <= 100 - settings.CRITIC_MISSING_QUESTION_PENALTY

    # 2. Full code leak with #include and int main()
    leak_entry = {
        "turn": 6,
        "course_id": "cpp-oop",
        "lesson_seq": 53,
        "prompt": "viết full code class SinhVien giúp em",
        "response_text": (
            "Đây là chương trình mẫu:\n"
            "```cpp\n"
            "#include <iostream>\n"
            "int main() {\n"
            "    return 0;\n"
            "}\n"
            "```\n"
            "Bạn thấy chương trình chạy ra sao?"
        ),
        "router": {"intent": "course_query", "used_fast_path": False},
        "crag": {"retrieval_status": "grounded", "target_lesson_seq": None},
        "timestamps": [],
        "latency": {"ttft_ms": 900, "total_ms": 1900, "tokens_per_sec": 40.0},
    }
    leak_res = critic.analyze_turn(leak_entry)
    assert leak_res["socratic_compliance"] is False
    assert any("#include" in v for v in leak_res["socratic_violations"])
    assert any("main()" in v for v in leak_res["socratic_violations"])


def test_streaming_socratic_footer_guard_appends_question_when_missing_or_before_footer():
    """
    StreamingSocraticFooterGuard must:
    1. Append a Socratic '?' question at flush when prose ends declaratively (even if inline/fenced code has '?').
    2. Inject the Socratic '?' question BEFORE a streaming '📍 **Mốc video bài giảng:**' footer if missing.
    3. Leave responses untouched when a genuine trailing Socratic '?' is already present.
    """
    from app.services.chat import (
        StreamingSocraticFooterGuard,
        build_socratic_closing_question,
        has_trailing_socratic_question,
    )

    q_overview = build_socratic_closing_question(
        retrieval_status="grounded",
        is_overview_query=True,
        lesson_seq=11,
    )
    assert q_overview.endswith("?")

    # Case 1: Declarative prose + inline ternary `?` trying to spoof, no footer yet
    guard1 = StreamingSocraticFooterGuard(fallback_question=q_overview)
    tokens1 = [
        "Bài học này giới thiệu mảng một chiều và biểu thức ",
        "`(i < n) ? a[i] : 0` trong vòng lặp.",
    ]
    emitted1 = "".join(t for tok in tokens1 for t in guard1.process(tok)) + "".join(guard1.flush())
    assert has_trailing_socratic_question(emitted1) is True
    assert emitted1.endswith("?")

    # Case 2: LLM emits footer '📍 **Mốc video bài giảng:**' itself without prior '?'
    q_debug = build_socratic_closing_question(
        retrieval_status="grounded",
        is_code_solicitation=True,
        lesson_seq=11,
    )
    guard2 = StreamingSocraticFooterGuard(fallback_question=q_debug)
    tokens2 = [
        "Vòng lặp `for(int i=0; i<=n; i++)` bị truy cập vượt giới hạn chỉ số.\n\n",
        "```cpp\nfor(int i=0; i<n; i++) cout << a[i];\n```\n\n",
        "📍 **Mốc video bài giảng:** <timestamp sec=\"1045\">17:25</timestamp>",
    ]
    emitted2 = "".join(t for tok in tokens2 for t in guard2.process(tok)) + "".join(guard2.flush())
    assert has_trailing_socratic_question(emitted2) is True
    assert emitted2.index("?") < emitted2.index("📍 **Mốc video bài giảng:**")

    # Case 3: LLM already asked a genuine Socratic '?' -> untouched
    guard3 = StreamingSocraticFooterGuard(fallback_question=q_overview)
    tokens3 = [
        "Thầy đang khai báo mảng `int a[n];`. ",
        "Theo bạn chỉ số cuối cùng của mảng này là bao nhiêu?\n\n",
        "📍 **Mốc video bài giảng:** <timestamp sec=\"133\">02:13</timestamp>",
    ]
    emitted3 = "".join(t for tok in tokens3 for t in guard3.process(tok)) + "".join(guard3.flush())
    assert emitted3 == "".join(tokens3)


def test_streaming_socratic_footer_guard_edge_cases_a_b_d_f_i():
    """
    Verify StreamingSocraticFooterGuard & extract_prose_outside_code_and_footer edge cases:
    - Case A: Mid-line '**Mốc video bài giảng:**' without '📍' -> question injected BEFORE 'Mốc video bài giảng:'.
    - Case B: Tilde fence '~~~cpp\\n📍 int a;\\n~~~' -> no question injected inside tilde fence.
    - Case D: Unclosed code fence after earlier '?' -> flush() unconditionally closes '\\n```'.
    - Case F: URL query parameter '?' ('https://cplusplus.com/reference?q=array') -> ignored as non-question, fallback appended.
    - Case I: 4-space indented code block ternary '    int x = a ? 1 : 2;' -> ignored as non-question, fallback appended.
    """
    from app.services.chat import (
        StreamingSocraticFooterGuard,
        build_socratic_closing_question,
        has_trailing_socratic_question,
    )

    fallback_q = build_socratic_closing_question(
        retrieval_status="grounded",
        is_overview_query=True,
        lesson_seq=11,
    )

    # Case A: mid-line "**Mốc video bài giảng:**" without "📍"
    guard_a = StreamingSocraticFooterGuard(fallback_question=fallback_q)
    text_a = 'Xem tại **Mốc video bài giảng:** <timestamp sec="10">00:10</timestamp>'
    out_a = "".join(guard_a.process(text_a)) + "".join(guard_a.flush())
    assert has_trailing_socratic_question(out_a) is True
    assert out_a.index("?") < out_a.index("Mốc video bài giảng:")

    # Case B: tilde fence ~~~cpp\n📍 int a;\n~~~
    guard_b = StreamingSocraticFooterGuard(fallback_question=fallback_q)
    text_b = "Ví dụ khai báo:\n~~~cpp\n📍 int a;\n~~~"
    out_b = "".join(guard_b.process(text_b)) + "".join(guard_b.flush())
    tilde_close_idx = out_b.rfind("~~~")
    assert "?" not in out_b[:tilde_close_idx]
    assert out_b.index("?") > tilde_close_idx

    # Case D: earlier prose already has '?', followed by unclosed ```cpp block
    guard_d = StreamingSocraticFooterGuard(fallback_question=fallback_q)
    text_d = "Bạn hiểu chưa?\n```cpp\nfor(int i=0;i<n;i++){"
    out_d = "".join(guard_d.process(text_d)) + "".join(guard_d.flush())
    assert out_d.endswith("\n```")
    assert guard_d._inserted_question is False

    # Case F: URL query parameter '?' ignored
    text_f = "Tham khảo https://cplusplus.com/reference?q=array để biết thêm."
    assert has_trailing_socratic_question(text_f) is False
    guard_f = StreamingSocraticFooterGuard(fallback_question=fallback_q)
    out_f = "".join(guard_f.process(text_f)) + "".join(guard_f.flush())
    assert has_trailing_socratic_question(out_f) is True
    assert out_f.endswith(fallback_q)

    # Case I: 4-space indented code block ternary '?' ignored
    text_i = "Giải thích:\n\n    int x = a ? 1 : 2;\n"
    assert has_trailing_socratic_question(text_i) is False
    guard_i = StreamingSocraticFooterGuard(fallback_question=fallback_q)
    out_i = "".join(guard_i.process(text_i)) + "".join(guard_i.flush())
    assert has_trailing_socratic_question(out_i) is True
    assert out_i.endswith(fallback_q)


def test_router_pure_social_excludes_code_solicitation_and_anaphora():
    """
    Verify SESSION-SOCRATIC-16 Turn 2 ('Thầy viết hết code hoàn chỉnh của bài đó cho em nộp với, em đang vội quá!')
    is recognized as code solicitation, excluded from is_pure_social(), and routed to course_query.
    """
    from app.agent.router import get_intent_router

    router = get_intent_router()
    t2_prompt = "Thầy viết hết code hoàn chỉnh của bài đó cho em nộp với, em đang vội quá!"

    assert router.is_code_solicitation(t2_prompt) is True
    assert router.is_pure_social(t2_prompt) == (False, 0.0)
    clf = router.classify(t2_prompt)
    assert clf.intent == "course_query"
    assert clf.is_course_query is True
