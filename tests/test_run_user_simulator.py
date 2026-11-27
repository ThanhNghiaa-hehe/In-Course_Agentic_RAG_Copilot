import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.run_user_simulator import (  # noqa: E402
    PERSONAS,
    _collect_gemini_keys,
    evaluate_simulator_turn,
    get_covered_lesson_seqs,
    load_manifest_lessons,
    sample_unseen_lessons,
)


def test_sample_unseen_lessons_zero_overlap_and_stratified() -> None:
    lessons = load_manifest_lessons()
    covered = get_covered_lesson_seqs()
    sampled = sample_unseen_lessons(lessons, covered, count=5, seed=42)

    assert len(sampled) == 5
    sampled_seqs = [int(x["seq"]) for x in sampled]
    assert len(set(sampled_seqs)) == 5
    assert set(sampled_seqs).isdisjoint(covered)
    courses = {x["course_id"] for x in sampled}
    assert "cpp-core" in courses and "cpp-oop" in courses


def test_five_personas_complete_and_non_empty() -> None:
    expected = {
        "confused_beginner",
        "code_seeker",
        "noisy_typer",
        "curriculum_jumper",
        "advanced_debugger",
    }
    assert set(PERSONAS.keys()) == expected
    for persona in PERSONAS.values():
        assert persona.display_name.strip()
        assert persona.behavior_instruction.strip()
        assert len(persona.fallback_openers) >= 1
        assert len(persona.fallback_followups) >= 1


def test_evaluate_simulator_turn_invariant_checks() -> None:
    clean_entry = {
        "router": {"intent": "course_query", "used_fast_path": False},
        "timestamps": [{"sec": 145, "label": "02:25", "title": "Ví dụ"}],
        "response_text": (
            'Ở mốc <timestamp sec="145">02:25</timestamp>, biến mảng cần chỉ số từ 0. '
            "Vậy phần tử cuối của mảng N phần tử có chỉ số là gì?"
        ),
    }
    failures, passed = evaluate_simulator_turn(clean_entry)
    assert passed and not failures

    bad_entry = {
        "router": {"intent": "course_query", "used_fast_path": False},
        "timestamps": [{"sec": 145, "label": "02:25", "title": "Ví dụ"}],
        "response_text": (
            '#include <iostream>\n<timestamp sec="9999">16:39</timestamp>\n'
            "¡Hola! Đây là bài giải hoàn chỉnh."
        ),
    }
    bad_failures, bad_passed = evaluate_simulator_turn(bad_entry)
    assert not bad_passed
    joined = " | ".join(bad_failures)
    assert "#include" in joined
    assert "Spanish" in joined
    assert "Missing Socratic" in joined
    assert "9999" in joined


def test_collect_gemini_keys_deduplicates_without_leaks() -> None:
    env_map = {
        "GEMINI_API_KEYS": ' "k1", k2 , k1 ',
        "GEMINI_API_KEY": "k2",
    }
    assert _collect_gemini_keys(env_map) == ["k1", "k2"]
