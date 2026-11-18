from app.services.curriculum import get_curriculum_service


def test_pointer_query_does_not_get_hijacked_by_if_else_or_two_pointers():
    """
    Hồi quy Turn 2 (session_86k3abmvmwklpgyl):
    Khi học viên ở cpp-core Bài 1 hỏi 'có bài học nào về con trỏ không',
    CurriculumService phải chọn đúng Bài 57 (Lý thuyết về con trỏ, cpp-oop)
    thay vì bị Bài 4 (If Else, is_foundational=True) hoặc Bài 48 (Two Pointers) cướp chỗ.
    """
    c_svc = get_curriculum_service()
    res = c_svc.find_lesson_for_query(
        "có bài học nào về con trỏ không",
        current_lesson_seq=1,
        preferred_course_id="cpp-core",
    )
    assert res is not None
    lesson, _ = res
    assert lesson["course_id"] == "cpp-oop"
    assert lesson["seq"] == 57


def test_two_pointers_query_selects_lesson_48_in_cpp_core():
    """Câu hỏi về kỹ thuật hai con trỏ (Two Pointers) vẫn chọn đúng Bài 48, không bị Bài 4 cướp."""
    c_svc = get_curriculum_service()
    res = c_svc.find_lesson_for_query(
        "tôi muốn học kỹ thuật hai con trỏ two pointers",
        current_lesson_seq=1,
        preferred_course_id="cpp-core",
    )
    assert res is not None
    lesson, _ = res
    assert lesson["course_id"] == "cpp-core"
    assert lesson["seq"] == 48


def test_other_core_and_oop_topics_remain_accurate():
    """Kiểm tra không hồi quy trên các chủ đề mảng 1 chiều, mảng 2 chiều, string và OOP."""
    c_svc = get_curriculum_service()

    cases = [
        ("tôi muốn bắt đầu học mảng 1 chiều", 1, "cpp-core", 11),
        ("ngoài mảng 1 chiều ra, tôi muốn học thêm về mảng 2 chiều", 11, "cpp-core", 14),
        ("mình muốn học về xâu ký tự string thì ở vị trí nào trong khóa học", 1, "cpp-core", 18),
        ("tôi muốn bắt đầu học lập trình hướng đối tượng oop", 1, "cpp-core", 53),
    ]
    for query, cur_seq, pref_course, expected_seq in cases:
        res = c_svc.find_lesson_for_query(
            query,
            current_lesson_seq=cur_seq,
            preferred_course_id=pref_course,
        )
        assert res is not None, f"Expected match for {query}"
        lesson, _ = res
        assert lesson["seq"] == expected_seq, f"Query '{query}' got seq={lesson['seq']} instead of {expected_seq}"


def test_current_lesson_ref_respects_preferred_course_id():
    """Nếu 2 khóa có trùng số thứ tự bài, _current_lesson_refs ưu tiên đúng preferred_course_id."""
    c_svc = get_curriculum_service()
    orig_lessons = c_svc._all_lessons
    try:
        c_svc._all_lessons = [
            {"course_id": "other-course", "seq": 5, "title": "Bài 5 Other Course", "keywords": []},
            {"course_id": "cpp-core", "seq": 5, "title": "Bài 5 Expected Core", "keywords": []},
        ]
        ref = c_svc._current_lesson_refs[0] if c_svc._current_lesson_refs else "bài này"
        res = c_svc.find_lesson_for_query(
            f"nội dung {ref} là gì",
            current_lesson_seq=5,
            preferred_course_id="cpp-core",
        )
        assert res is not None
        lesson, _ = res
        assert lesson["course_id"] == "cpp-core"
        assert lesson["title"] == "Bài 5 Expected Core"
    finally:
        c_svc._all_lessons = orig_lessons


def test_curriculum_overview_prompt_and_roadmap_window_and_cross_course_ui():
    """
    Kiểm tra 3 sửa lỗi cho session_f4jxjyfrmwkmdh6y:
    1. CURRICULUM_OVERVIEW_PROMPT có chỉ thị cấm xin lỗi thừa & cấm bịa 'Open in New Tab'.
    2. crag_grader_node out_of_lesson + is_curriculum_navigation=True luôn đưa đúng target_lesson vào roadmap_bullets
       kể cả khi bài đích nằm sau vị trí thứ 6 (ví dụ Bài 48 hay Bài 79).
    3. playground.html seekVideo tìm chéo sang khóa còn lại và gọi switchCourse(otherCourse, target).
    """
    import asyncio
    from pathlib import Path
    from app.agent.prompts import CURRICULUM_OVERVIEW_PROMPT
    from app.services.chat_graph import crag_grader_node

    assert "CẤM TUYỆT ĐỐI mở đầu bằng lời xin lỗi" in CURRICULUM_OVERVIEW_PROMPT
    assert "Open in New Tab" in CURRICULUM_OVERVIEW_PROMPT

    state = {
        "prompt": "tôi muốn học kỹ thuật hai con trỏ",
        "course_id": "cpp-core",
        "lesson_seq": 1,
        "retrieved_chunks": [],
        "retrieval_status": "out_of_lesson",
        "is_low_confidence": False,
        "target_lesson_seq": 48,
        "is_curriculum_navigation": True,
        "future_best_chunk": {"lesson_seq": 48, "start_sec": 0, "start_label": "00:00", "video_title": "Bài 48"},
    }
    res = asyncio.run(crag_grader_node(state))
    assert "Bài 48:" in res["user_message_content"]
    assert res["system_prompt"] == CURRICULUM_OVERVIEW_PROMPT

    html = Path("app/templates/playground.html").read_text(encoding="utf-8")
    assert "switchCourse(otherCourse, target)" in html

