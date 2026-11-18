"""
Focused unit tests for Stage 13 Context Hygiene & Curriculum Navigation Anchor:
- 13.1: context_assembly_node cleans <timestamp ...>...</timestamp>,
        '📍 **Mốc video bài giảng:** ...', and '[Video Bài ...]' from
        assistant history (including turn t-1) while keeping C++ explanation
        text, C++ comparison/stream operators, and code fences intact.
- 13.2: _format_context_block no longer emits '[Video Bài {seq} - {tag}]:'
        bracketed pattern while still preserving <timestamp> info.
- 13.3: crag_grader_node injects '[THÔNG TIN BÀI HỌC KHỚP GIÁO TRÌNH]' when
        is_curriculum_navigation=True & grounded (e.g. backward query at
        lesson_seq=12 matching Bài 11), and does NOT inject it when
        is_curriculum_navigation=False.
"""

import pytest

from app.agent.prompts import SOCRATIC_GROUNDED_PROMPT
from app.services.chat_graph import (
    _format_context_block,
    context_assembly_node,
    crag_grader_node,
)


@pytest.mark.asyncio
async def test_13_1_context_assembly_cleans_assistant_history_including_t_minus_1():
    """
    13.1: context_assembly_node must strip <timestamp ...>...</timestamp>,
    '📍 **Mốc video bài giảng:** ...' footer lines, and '[Video Bài ...]'
    bracketed labels from ALL assistant turns (including t-1), while keeping
    substantive C++ explanation text and C++ < / > operators intact.
    """
    older_assistant = (
        "[Video Bài 10 - 01:10]: Độ phức tạp O(n) phụ thuộc vào số bước lặp i < n.\n"
        "Bạn hãy kiểm tra điều kiện i < n && j > 0 trong vòng lặp.\n\n"
        "📍 **Mốc video bài giảng:** <timestamp sec=\"70\">01:10</timestamp>"
    )
    t_minus_1_assistant = (
        "[Video Bài 11 - 02:25]: Khi khai báo `int a[100];` và `vector<int> v;`, "
        "chỉ số chạy từ `0` đến `n - 1` (tức `i < n`).\n"
        "Hãy thử in phần tử với `cout << a[0];` ở đoạn "
        "<timestamp sec=\"145\">02:25</timestamp> và xem thêm tại "
        "<timestamp sec=\"210\">03:30</timestamp>.\n\n"
        "```cpp\n"
        "for (int i = 0; i < n; ++i) {\n"
        "    cout << a[i] << \" \";\n"
        "}\n"
        "```\n\n"
        "📍 **Mốc video bài giảng:** <timestamp sec=\"145\">02:25</timestamp> | "
        "<timestamp sec=\"210\">03:30</timestamp>"
    )

    state = {
        "prompt": "Tại sao truy cập a[n] bị lỗi?",
        "user_message_content": "Câu hỏi: Tại sao truy cập a[n] bị lỗi?",
        "system_prompt": SOCRATIC_GROUNDED_PROMPT,
        "messages": [
            {"role": "user", "content": "Độ phức tạp vòng lặp là gì?"},
            {"role": "assistant", "content": older_assistant},
            {"role": "user", "content": "Mảng 1 chiều khai báo sao ạ?"},
            {"role": "assistant", "content": t_minus_1_assistant},
        ],
        "conversation_summary": None,
    }

    res = await context_assembly_node(state)
    assembled = res["assembled_messages"]

    assistant_msgs = [m["content"] for m in assembled if m["role"] == "assistant"]
    assert len(assistant_msgs) == 2

    older_cleaned, t1_cleaned = assistant_msgs[0], assistant_msgs[1]

    for cleaned in (older_cleaned, t1_cleaned):
        assert "<timestamp" not in cleaned.lower()
        assert "</timestamp>" not in cleaned.lower()
        assert "📍" not in cleaned
        assert "mốc video bài giảng" not in cleaned.lower()
        assert "[video bài" not in cleaned.lower()

    # Older turn keeps substantive C++ explanation & comparison operators
    assert "Độ phức tạp O(n)" in older_cleaned
    assert "i < n && j > 0" in older_cleaned

    # Turn t-1 keeps full C++ explanation and template/stream/comparison operators;
    # long code fences (>180 chars) are collapsed by the existing Markdown AST pruner.
    assert "int a[100];" in t1_cleaned
    assert "vector<int> v;" in t1_cleaned
    assert "i < n" in t1_cleaned
    assert "cout << a[0];" in t1_cleaned
    assert "[...khung code minh họa ở lượt trước...]" in t1_cleaned


@pytest.mark.asyncio
async def test_13_1_context_assembly_preserves_short_cpp_code_and_strips_inline_footer():
    """
    13.1: Short C++ code blocks (<=180 chars) and inline C++ comparison/stream
    operators are preserved in turn t-1 while inline '📍' / 'Mốc video bài giảng'
    artifacts and '<timestamp>' tags are stripped.
    """
    t1_reply = (
        "Dùng `if (a < b && b > 0)` và `cin >> x; cout << x;` "
        "<timestamp sec=\"95\">01:35</timestamp>\n"
        "Mốc video bài giảng: <timestamp sec=\"95\">01:35</timestamp>"
    )
    state = {
        "prompt": "Tiếp theo làm gì?",
        "user_message_content": "Câu hỏi: Tiếp theo làm gì?",
        "system_prompt": SOCRATIC_GROUNDED_PROMPT,
        "messages": [
            {"role": "user", "content": "Kiểm tra điều kiện thế nào?"},
            {"role": "assistant", "content": t1_reply},
        ],
        "conversation_summary": None,
    }
    res = await context_assembly_node(state)
    assistant_msgs = [m["content"] for m in res["assembled_messages"] if m["role"] == "assistant"]
    assert len(assistant_msgs) == 1
    cleaned = assistant_msgs[0]
    assert "<timestamp" not in cleaned.lower()
    assert "mốc video bài giảng" not in cleaned.lower()
    assert "if (a < b && b > 0)" in cleaned
    assert "cin >> x; cout << x;" in cleaned


def test_13_2_format_context_block_no_bracketed_video_tag_preserves_timestamp():
    """
    13.2: _format_context_block must NOT emit '[Video Bài {seq} - {tag}]:'
    bracketed pattern while still preserving <timestamp ...>...</timestamp> info.
    """
    chunks = [
        {
            "content_type": "video_transcript",
            "lesson_seq": 11,
            "timestamp_tag": '<timestamp sec="145">02:25</timestamp>',
            "raw_text": "Trong C++, mảng một chiều lưu các phần tử liên tiếp nhau trong bộ nhớ.",
        },
        {
            "content_type": "video_transcript",
            "lesson_seq": 11,
            "timestamp_tag": "",
            "raw_text": "Chỉ số mảng bắt đầu từ 0 đến n - 1.",
        },
    ]

    formatted = _format_context_block(chunks)

    assert "[Video Bài" not in formatted
    assert "Nguồn Bài 11 (mốc <timestamp sec=\"145\">02:25</timestamp>):" in formatted
    assert '<timestamp sec="145">02:25</timestamp>' in formatted
    assert "Trong C++, mảng một chiều lưu các phần tử liên tiếp nhau trong bộ nhớ." in formatted
    assert "Nguồn Bài 11: Chỉ số mảng bắt đầu từ 0 đến n - 1." in formatted


@pytest.mark.asyncio
async def test_13_3_crag_grader_injects_curriculum_anchor_only_for_nav_grounded():
    """
    13.3: crag_grader_node injects '[THÔNG TIN BÀI HỌC KHỚP GIÁO TRÌNH]' when
    is_curriculum_navigation=True and retrieval_status='grounded' (backward
    query at lesson_seq=12 matching Bài 11), and does NOT inject it when
    is_curriculum_navigation=False.
    """
    grounded_chunks = [
        {
            "id": "chunk-11-vid",
            "content_type": "video_transcript",
            "lesson_id": "lesson-11",
            "lesson_seq": 11,
            "start_sec": 145,
            "start_label": "02:25",
            "timestamp_tag": '<timestamp sec="145">02:25</timestamp>',
            "video_title": "Bài 11: Mảng một chiều trong C++",
            "raw_text": "Bài 11 giới thiệu khái niệm và cách khai báo mảng một chiều trong C++.",
            "confidence_pct": 88.0,
            "confidence_score": 0.88,
            "is_approximate": False,
        }
    ]

    nav_state = {
        "prompt": "mảng một chiều học ở bài nào?",
        "search_query": "mảng một chiều học ở bài nào?",
        "course_id": "cpp-core",
        "lesson_seq": 12,
        "retrieved_chunks": grounded_chunks,
        "retrieval_status": "grounded",
        "is_low_confidence": False,
        "target_lesson_seq": None,
        "is_curriculum_navigation": True,
    }
    nav_res = await crag_grader_node(nav_state)
    nav_user_content = nav_res["user_message_content"]

    assert "[THÔNG TIN BÀI HỌC KHỚP GIÁO TRÌNH]: Bài 11 -" in nav_user_content
    assert "Mảng một chiều" in nav_user_content
    assert nav_user_content.startswith("[THÔNG TIN BÀI HỌC KHỚP GIÁO TRÌNH]: Bài 11 -")

    # Normal Socratic technical query (is_curriculum_navigation=False) must NOT inject anchor
    tech_state = {
        "prompt": "Làm sao truyền mảng một chiều vào hàm?",
        "search_query": "Làm sao truyền mảng một chiều vào hàm?",
        "course_id": "cpp-core",
        "lesson_seq": 12,
        "retrieved_chunks": grounded_chunks,
        "retrieval_status": "grounded",
        "is_low_confidence": False,
        "target_lesson_seq": None,
        "is_curriculum_navigation": False,
    }
    tech_res = await crag_grader_node(tech_state)
    tech_user_content = tech_res["user_message_content"]

    assert "[THÔNG TIN BÀI HỌC KHỚP GIÁO TRÌNH]" not in tech_user_content
    assert tech_user_content.startswith("[CÂU HỎI THẮC MẮC CỦA HỌC VIÊN]")


@pytest.mark.asyncio
async def test_13_4_context_assembly_compresses_overlong_t_minus_1_assistant():
    """
    13.4: Verbose multi-bullet assistant response at turn t-1 (>450 chars) must
    be truncated cleanly so 7B models do not autoregressively copy its bullet
    structure into the next turn.
    """
    verbose_t1 = (
        "Dưới đây là giải thích chi tiết về kế thừa trong OOP:\n"
        "- Ý 1: Lớp con kế thừa thuộc tính và phương thức public/protected của lớp cha.\n"
        "- Ý 2: Không kế thừa hàm tạo và hàm hủy một cách mặc định.\n"
        "- Ý 3: Có thể ghi đè phương thức bằng từ khóa virtual và override.\n"
        "- Ý 4: Đóng gói và tính đa hình giúp mở rộng mã nguồn an toàn hơn.\n"
        "- Ý 5: Luôn kiểm tra phạm vi truy cập khi thiết kế hệ thống hướng đối tượng lớn trong C++ hiện đại "
        "nhằm tránh rò rỉ bộ nhớ và xung đột tên hàm giữa các lớp cơ sở."
    )
    assert len(verbose_t1) > 450

    state = {
        "prompt": "Giải thích thêm về đa hình?",
        "user_message_content": "Câu hỏi: Giải thích thêm về đa hình?",
        "system_prompt": SOCRATIC_GROUNDED_PROMPT,
        "messages": [
            {"role": "user", "content": "Kế thừa là gì?"},
            {"role": "assistant", "content": verbose_t1},
        ],
        "conversation_summary": None,
    }
    res = await context_assembly_node(state)
    assistant_msgs = [m["content"] for m in res["assembled_messages"] if m["role"] == "assistant"]
    assert len(assistant_msgs) == 1
    cleaned = assistant_msgs[0]
    assert len(cleaned) < 420
    assert cleaned.endswith("...")
    assert "[đã rút gọn" not in cleaned
    assert "[rút gọn" not in cleaned


@pytest.mark.asyncio
async def test_13_5_out_of_lesson_injects_exact_target_course_and_real_related_lessons():
    """
    13.5: Cross-course or non-nav out_of_lesson must record the exact target
    lesson's course_id (e.g. Bài 11 in cpp-core when user is in cpp-oop) and
    inject [DANH MỤC BÀI HỌC THẬT LIÊN QUAN TRONG GIÁO TRÌNH] from syllabus_manifest.
    """
    from app.agent.prompts import OUT_OF_LESSON_PROMPT

    future_chunks = [
        {
            "id": "chunk-11-core",
            "content_type": "video_transcript",
            "course_id": "cpp-core",
            "lesson_id": "lesson-11",
            "lesson_seq": 11,
            "start_sec": 120,
            "start_label": "02:00",
            "timestamp_tag": '<timestamp sec="120">02:00</timestamp>',
            "video_title": "Bài 11: Mảng 1 chiều cơ bản",
            "raw_text": "Trong C++, mảng một chiều lưu các phần tử cùng kiểu nằm liên tiếp.",
            "confidence_pct": 85.0,
            "confidence_score": 0.85,
            "is_approximate": False,
        }
    ]

    state = {
        "prompt": "ngoài bài 64 ra còn những bài nào dạy về mảng 1 chiều nữa không",
        "search_query": "mảng 1 chiều bài nào trong giáo trình",
        "course_id": "cpp-oop",
        "lesson_seq": 57,
        "retrieved_chunks": [],
        "future_chunks": future_chunks,
        "retrieval_status": "out_of_lesson",
        "is_low_confidence": False,
        "target_lesson_seq": 11,
        "is_curriculum_navigation": False,
    }
    res = await crag_grader_node(state)
    user_content = res["user_message_content"]

    assert res["system_prompt"] == OUT_OF_LESSON_PROMPT
    assert "- Khóa học hiện tại: cpp-oop" in user_content
    assert "Bài 11 (khóa cpp-core)" in user_content
    assert "[DANH MỤC BÀI HỌC THẬT LIÊN QUAN TRONG GIÁO TRÌNH]" in user_content
    assert "CẤM tự suy đoán hay bịa thêm" in OUT_OF_LESSON_PROMPT
