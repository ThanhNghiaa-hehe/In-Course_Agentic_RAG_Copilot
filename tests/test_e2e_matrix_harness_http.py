import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.e2e_matrix_harness import (  # noqa: E402
    TurnSpec,
    build_suites,
    detect_foreign_language_leak,
    evaluate_turn_assertions,
    parse_sse_events_from_lines,
)


def _load_manifest_lesson_map() -> dict[int, str]:
    manifest_path = ROOT_DIR / "data" / "curriculum" / "lessons_manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    mapping: dict[int, str] = {}
    for cid, cval in data["courses"].items():
        lessons = cval.get("lessons", cval) if isinstance(cval, dict) else cval
        for item in lessons:
            seq = item.get("seq") or item.get("lesson_seq")
            if seq is not None:
                mapping[int(seq)] = cid
    return mapping


def test_all_13_suites_align_with_lessons_manifest() -> None:
    suites = build_suites()
    expected_ids = {
        "M1",
        "M2",
        "M3",
        "S1",
        "M4",
        "M5",
        "M6",
        "M7",
        "M8",
        "M9",
        "M10",
        "M11",
        "M12",
    }
    assert set(suites.keys()) == expected_ids

    lesson_course_map = _load_manifest_lesson_map()
    pro_turns = 0
    for sid, suite in suites.items():
        assert suite.default_lesson_seq in lesson_course_map
        assert lesson_course_map[suite.default_lesson_seq] == suite.default_course_id
        assert len(suite.turns) >= 3
        for idx, turn in enumerate(suite.turns, start=1):
            assert turn.turn_idx == idx, f"{sid} turn numbering mismatch"
            assert turn.lesson_seq in lesson_course_map
            assert lesson_course_map[turn.lesson_seq] == turn.course_id, (
                f"{sid} T{idx}: lesson {turn.lesson_seq} belongs to "
                f"{lesson_course_map[turn.lesson_seq]}, got {turn.course_id}"
            )
            if sid in {"M9", "M10", "M11", "M12"}:
                pro_turns += 1

    assert pro_turns == 22


def test_detect_foreign_language_leak_catches_cjk_and_spanish() -> None:
    assert detect_foreign_language_leak("Trong C++, biến int lưu số nguyên có dấu?") is None
    assert "CJK" in (detect_foreign_language_leak("Trong C++, 这是一个测试 đúng không?") or "")
    assert "Spanish" in (detect_foreign_language_leak("¿Estás seguro với kết quả này?") or "")
    assert "Spanish" in (detect_foreign_language_leak("¡Tuyệt vời! Bạn hiểu chưa?") or "")


def test_parse_sse_events_from_lines_parses_metadata_delta_done() -> None:
    raw_lines = [
        ": keep-alive ping",
        "event: metadata",
        'data: {"intent": "course_query", "retrieval_status": "grounded"}',
        "",
        "event: delta",
        'data: {"content": "Xin "}',
        "",
        "event: delta",
        'data: {"content": "chào?"}',
        "",
        "event: done",
        'data: {"status": "completed"}',
        "",
    ]
    events = parse_sse_events_from_lines(raw_lines)
    assert events == [
        ("metadata", '{"intent": "course_query", "retrieval_status": "grounded"}'),
        ("delta", '{"content": "Xin "}'),
        ("delta", '{"content": "chào?"}'),
        ("done", '{"status": "completed"}'),
    ]


def test_evaluate_turn_assertions_flags_leaks_and_missing_question() -> None:
    spec = TurnSpec(
        turn_idx=1,
        course_id="cpp-core",
        lesson_seq=26,
        current_video_sec=None,
        prompt="Viết full code std::sort giúp tôi",
        expected_intents=("course_query",),
        expected_statuses=("grounded",),
        expect_fast_path=False,
        expect_socratic_question=True,
    )
    bad_entry = {
        "router": {"intent": "course_query", "used_fast_path": False},
        "crag": {"retrieval_status": "grounded", "target_lesson_seq": None},
        "response_text": "#include <iostream>\n¡Cuidado! Đây là lời giải đầy đủ.",
    }
    failures, _ = evaluate_turn_assertions(spec, bad_entry, prev_rag_prose=None, routing_only=False)
    joined = " | ".join(failures)
    assert "#include" in joined
    assert "Spanish" in joined
    assert "Missing Socratic" in joined
