"""
Verification tests for Unseen Vietnamese Numeric/Middle Temporal Queries,
Multimodal Code-AST Co-Retrieval, Stateful ChatGraph Temporal Anchor Tracking,
and AST-Guided Transcript Canonicalization + Integrity Guardrails.
"""

import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import canonicalize_transcripts_ast as canon
from app.agent.prompts import SOCRATIC_GROUNDED_PROMPT
from app.services.chat_graph import (
    commit_assistant_turn,
    get_chat_graph,
    reset_session_state,
)
from app.services.curriculum import get_curriculum_service
from app.services.retrieval import RetrievalResult, RetrievalService


def _make_video_hit(
    hit_id: str,
    score: float,
    lesson_seq: int,
    course_id: str,
    start_sec: int,
    end_sec: int,
    raw_text: str,
    video_title: str = "lesson_53_oop.mp4",
):
    return SimpleNamespace(
        id=hit_id,
        score=score,
        payload={
            "lesson_id": f"lesson-{lesson_seq:02d}",
            "lesson_seq": lesson_seq,
            "course_id": course_id,
            "content_type": "video_transcript",
            "raw_text": raw_text,
            "video_title": video_title,
            "start_sec": start_sec,
            "end_sec": end_sec,
            "start_label": f"{start_sec // 60:02d}:{start_sec % 60:02d}",
            "end_label": f"{end_sec // 60:02d}:{end_sec % 60:02d}",
        },
    )


def _make_code_ast_hit(
    hit_id: str,
    score: float,
    lesson_seq: int,
    course_id: str,
    approx_video_sec: int,
    code_scope: str,
    context_code: str,
    file_path: str = "data/sample_codes/lesson_53.cpp",
):
    return SimpleNamespace(
        id=hit_id,
        score=score,
        payload={
            "lesson_id": f"lesson-{lesson_seq:02d}",
            "lesson_seq": lesson_seq,
            "course_id": course_id,
            "content_type": "code_ast",
            "language": "cpp",
            "code_scope": code_scope,
            "file_path": file_path,
            "start_line": 10,
            "end_line": 22,
            "raw_text": context_code,
            "context_code": context_code,
            "approx_video_sec": approx_video_sec,
        },
    )


def _make_mock_embedding_service():
    emb = MagicMock()
    emb.embed_query_dense.return_value = [0.1] * 8
    emb.embed_query_sparse.return_value = ([1, 2], [0.5, 0.5])
    emb.rerank_documents_async = AsyncMock(side_effect=lambda query, documents: [0.5] * len(documents))
    return emb


def _extract_filter_conditions(q_filter):
    conds = {}
    for cond in getattr(q_filter, "must", None) or []:
        key = getattr(cond, "key", None)
        if not key:
            continue
        match = getattr(cond, "match", None)
        rng = getattr(cond, "range", None)
        if match is not None:
            conds[key] = ("match", getattr(match, "value", None))
        elif rng is not None:
            conds[key] = ("range", (getattr(rng, "gte", None), getattr(rng, "lte", None)))
    return conds


# ---------------------------------------------------------------------------
# 1. Vietnamese numeric words & relative_middle in CurriculumService
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("phút thứ năm", {"kind": "explicit_sec", "target_sec": 300}),
        ("phút thứ năm thầy nói gì", {"kind": "explicit_sec", "target_sec": 300}),
        ("hai mươi tư phút rưỡi", {"kind": "explicit_sec", "target_sec": 1470}),
        ("ba phút mười giây", {"kind": "explicit_sec", "target_sec": 190}),
        ("hai mươi lăm phút thầy viết code gì", {"kind": "explicit_sec", "target_sec": 1500}),
        ("mười hai phút rưỡi", {"kind": "explicit_sec", "target_sec": 750}),
        ("phút thứ nhất thầy giới thiệu gì", {"kind": "explicit_sec", "target_sec": 60}),
        ("đoạn giữa video", {"kind": "relative_middle", "target_sec": None}),
        ("đoạn giữa video giảng về gì", {"kind": "relative_middle", "target_sec": None}),
        ("phần giữa bài giảng thầy demo gì", {"kind": "relative_middle", "target_sec": None}),
        ("chạy mất năm giây", None),
        ("code chạy mất năm giây thì có chậm không", None),
    ],
)
def test_curriculum_vietnamese_numeric_time_and_relative_middle(prompt, expected):
    c_svc = get_curriculum_service()
    assert c_svc.extract_video_time_reference(prompt) == expected


def test_curriculum_middle_and_vn_numeric_do_not_trigger_navbypass():
    c_svc = get_curriculum_service()
    for query in ("đoạn giữa video giảng về gì", "phút thứ năm thầy nói gì", "hai mươi tư phút rưỡi"):
        assert c_svc.is_navigation_query(query, current_lesson_seq=53, preferred_course_id="cpp-oop") is False
        assert c_svc.has_current_lesson_reference(query, current_lesson_seq=53, preferred_course_id="cpp-oop") is True


# ---------------------------------------------------------------------------
# 2. _temporal_proximity_search: relative_middle (~T/2) & code_ast co-retrieval
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_temporal_proximity_relative_middle_and_code_ast_co_retrieval():
    all_hits = [
        _make_video_hit(
            "v-030",
            0.78,
            lesson_seq=53,
            course_id="cpp-oop",
            start_sec=30,
            end_sec=75,
            raw_text="Giới thiệu khái niệm lập trình hướng đối tượng.",
        ),
        _make_video_hit(
            "v-580",
            0.86,
            lesson_seq=53,
            course_id="cpp-oop",
            start_sec=580,
            end_sec=630,
            raw_text="Ở giữa bài học, thầy minh họa Access Modifier private và public cho lớp SinhVien.",
        ),
        _make_video_hit(
            "v-640",
            0.82,
            lesson_seq=53,
            course_id="cpp-oop",
            start_sec=640,
            end_sec=685,
            raw_text="Viết hàm getName và setName để đóng gói dữ liệu.",
        ),
        _make_video_hit(
            "v-1150",
            0.74,
            lesson_seq=53,
            course_id="cpp-oop",
            start_sec=1150,
            end_sec=1200,
            raw_text="Tổng kết cuối bài học về OOP.",
        ),
        _make_code_ast_hit(
            "c-100-far",
            0.90,
            lesson_seq=53,
            course_id="cpp-oop",
            approx_video_sec=100,
            code_scope="class:IntroStruct",
            context_code="struct IntroStruct { int x; };",
        ),
        _make_code_ast_hit(
            "c-590-near",
            0.89,
            lesson_seq=53,
            course_id="cpp-oop",
            approx_video_sec=590,
            code_scope="class:SinhVien",
            context_code="class SinhVien {\nprivate:\n    string ten;\npublic:\n    string getTen();\n};",
        ),
    ]

    captured_filters = []

    async def _fake_scroll(**kwargs):
        s_filter = kwargs.get("scroll_filter")
        captured_filters.append(s_filter)
        conds = _extract_filter_conditions(s_filter)
        c_val = conds.get("course_id", (None, None))[1]
        l_val = conds.get("lesson_seq", (None, None))[1]
        ct_val = conds.get("content_type", (None, None))[1]
        rng = conds.get("start_sec", (None, (None, None)))[1]

        matched = []
        for h in all_hits:
            p = h.payload
            if c_val and p.get("course_id") != c_val:
                continue
            if l_val is not None and p.get("lesson_seq") != l_val:
                continue
            if ct_val and p.get("content_type") != ct_val:
                continue
            if rng and rng[0] is not None and rng[1] is not None:
                if not (rng[0] <= int(p.get("start_sec", 0)) <= rng[1]):
                    continue
            matched.append(h)
        return (matched, None)

    fake_qdrant = MagicMock()
    fake_qdrant.scroll = AsyncMock(side_effect=_fake_scroll)
    fake_qdrant.query_points = AsyncMock(side_effect=AssertionError("Should not run vector fallback"))

    fake_c_svc = MagicMock()
    fake_c_svc.extract_video_time_reference.return_value = {"kind": "relative_middle", "target_sec": None}
    fake_c_svc.get_lesson_chapters.return_value = [{"sec": 1200, "label": "20:00", "summary": "Kết thúc"}]

    svc = RetrievalService(client=fake_qdrant, embedding_service=_make_mock_embedding_service())
    res = await svc._temporal_proximity_search(
        query_text="đoạn giữa video thầy giảng gì",
        course_id="cpp-oop",
        current_lesson_seq=53,
        time_ref={"kind": "relative_middle", "target_sec": None},
        current_video_sec=None,
        c_svc=fake_c_svc,
        final_top_k=3,
    )

    assert res.status == "grounded"
    assert res.is_approximate is False
    assert len(res.chunks) >= 2

    # Ensure both video_transcript near T/2=600s and code_ast near 590s (±120s) were co-retrieved
    video_chunks = [c for c in res.chunks if c.get("content_type") == "video_transcript"]
    code_chunks = [c for c in res.chunks if c.get("content_type") == "code_ast"]
    assert len(video_chunks) >= 1
    assert any(500 <= c["start_sec"] <= 700 for c in video_chunks)
    assert len(code_chunks) == 1
    assert code_chunks[0]["id"] == "c-590-near"
    assert code_chunks[0]["approx_video_sec"] == 590
    assert code_chunks[0]["start_sec"] == 590
    assert code_chunks[0]["timestamp_tag"] == '<timestamp sec="590">09:50</timestamp>'
    assert code_chunks[0]["is_approximate"] is False

    # Ensure filter requested code_ast explicitly
    assert any(
        _extract_filter_conditions(f).get("content_type") == ("match", "code_ast")
        for f in captured_filters
    )


@pytest.mark.asyncio
async def test_temporal_proximity_ignores_distant_code_ast_and_keeps_pure_transcript():
    hits = [
        _make_video_hit(
            "v-300",
            0.88,
            lesson_seq=53,
            course_id="cpp-oop",
            start_sec=285,
            end_sec=325,
            raw_text="Tại phút thứ năm thầy giải thích khái niệm đóng gói.",
        ),
        _make_code_ast_hit(
            "c-050-too-far",
            0.90,
            lesson_seq=53,
            course_id="cpp-oop",
            approx_video_sec=50,
            code_scope="class:TooFar",
            context_code="class TooFar {};",
        ),
    ]

    async def _fake_scroll(**kwargs):
        conds = _extract_filter_conditions(kwargs.get("scroll_filter"))
        ct_val = conds.get("content_type", (None, None))[1]
        rng = conds.get("start_sec", (None, (None, None)))[1]
        matched = []
        for h in hits:
            p = h.payload
            if ct_val and p.get("content_type") != ct_val:
                continue
            if rng and rng[0] is not None and rng[1] is not None:
                if not (rng[0] <= int(p.get("start_sec", 0)) <= rng[1]):
                    continue
            matched.append(h)
        return (matched, None)

    fake_qdrant = MagicMock()
    fake_qdrant.scroll = AsyncMock(side_effect=_fake_scroll)

    svc = RetrievalService(client=fake_qdrant, embedding_service=_make_mock_embedding_service())
    res = await svc.hybrid_search(
        query_text="phút thứ năm thầy nói gì",
        course_id="cpp-oop",
        current_lesson_seq=53,
    )

    assert res.status == "grounded"
    assert res.is_approximate is False
    assert len(res.chunks) == 1
    assert res.chunks[0]["content_type"] == "video_transcript"
    assert res.chunks[0]["start_sec"] == 285


# ---------------------------------------------------------------------------
# 3. chat_graph.py stateful temporal anchor (MemorySaver multi-turn)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_chat_graph_turn1_deictic_without_anchor_injects_chapters_clarification():
    session_id = f"test-deictic-turn1-{uuid.uuid4().hex[:8]}"
    reset_session_state(session_id)
    try:
        recorded_calls = []

        async def _fake_hybrid_search(**kwargs):
            recorded_calls.append(kwargs)
            return RetrievalResult(chunks=[], status="coverage_gap")

        fake_retrieval = MagicMock()
        fake_retrieval.hybrid_search = AsyncMock(side_effect=_fake_hybrid_search)

        graph = get_chat_graph()
        config = {"configurable": {"thread_id": session_id}}
        with patch("app.services.chat_graph.get_retrieval_service", return_value=fake_retrieval):
            out = await graph.ainvoke(
                {
                    "session_id": session_id,
                    "prompt": "đoạn này thầy nói gì",
                    "course_id": "cpp-oop",
                    "lesson_seq": 53,
                    "current_video_sec": None,
                },
                config=config,
            )

        assert len(recorded_calls) >= 1
        assert recorded_calls[0]["current_video_sec"] is None
        assert out["missing_deictic_sec"] is True
        assert out["inherited_video_sec"] is None
        assert out["last_video_sec"] is None
        assert out["system_prompt"] == SOCRATIC_GROUNDED_PROMPT
        assert "[MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI]" in out["user_message_content"]
        assert "[LƯU Ý LÀM RÕ MỐC THỜI GIAN VIDEO]" in out["user_message_content"]
    finally:
        reset_session_state(session_id)


@pytest.mark.asyncio
async def test_chat_graph_stateful_temporal_anchor_inherits_same_lesson_and_resets_on_lesson_change():
    session_id = f"test-deictic-multiturn-{uuid.uuid4().hex[:8]}"
    reset_session_state(session_id)
    try:
        recorded_calls = []

        async def _fake_hybrid_search(**kwargs):
            recorded_calls.append(kwargs)
            l_seq = kwargs.get("current_lesson_seq")
            v_sec = kwargs.get("current_video_sec")
            if l_seq == 53 and (v_sec == 228 or "phút 4" in kwargs.get("query_text", "").lower()):
                return RetrievalResult(
                    chunks=[
                        {
                            "id": "hit-53-228",
                            "content_type": "video_transcript",
                            "lesson_id": "lesson-53",
                            "lesson_seq": 53,
                            "course_id": "cpp-oop",
                            "raw_text": "Thầy giảng về Class và Access Modifier private/public.",
                            "video_title": "lesson-53_oop_intro.mp4",
                            "start_sec": 228,
                            "end_sec": 275,
                            "start_label": "03:48",
                            "end_label": "04:35",
                            "timestamp_tag": '<timestamp sec="228">03:48</timestamp>',
                            "confidence_score": 0.92,
                            "confidence_pct": 92.0,
                            "is_approximate": False,
                        }
                    ],
                    status="grounded",
                    is_approximate=False,
                    is_low_confidence=False,
                )
            return RetrievalResult(chunks=[], status="coverage_gap")

        fake_retrieval = MagicMock()
        fake_retrieval.hybrid_search = AsyncMock(side_effect=_fake_hybrid_search)

        graph = get_chat_graph()
        config = {"configurable": {"thread_id": session_id}}

        with patch("app.services.chat_graph.get_retrieval_service", return_value=fake_retrieval):
            # Turn 1: Explicit minute 4 at Bài 53 -> establishes last_video_sec=228, last_lesson_seq=53
            out1 = await graph.ainvoke(
                {
                    "session_id": session_id,
                    "prompt": "đoạn đầu khoảng phút 4 thầy giảng gì",
                    "course_id": "cpp-oop",
                    "lesson_seq": 53,
                    "current_video_sec": None,
                },
                config=config,
            )
            assert out1["retrieval_status"] == "grounded"
            assert out1["suggested_timestamps"][0]["sec"] == 228
            assert out1["last_video_sec"] == 228
            assert out1["last_lesson_seq"] == 53

            commit_assistant_turn(
                session_id=session_id,
                user_prompt="đoạn đầu khoảng phút 4 thầy giảng gì",
                assistant_response='Ở phút 03:48 <timestamp sec="228">03:48</timestamp> thầy giảng về Class.',
                current_lesson_seq=53,
                last_course_query=out1.get("last_course_query"),
            )

            # Turn 2: Deictic "đoạn này" with current_video_sec=None in SAME lesson 53 -> inherits 228
            recorded_calls.clear()
            out2 = await graph.ainvoke(
                {
                    "session_id": session_id,
                    "prompt": "đoạn này thầy giải thích cụ thể hơn được không",
                    "course_id": "cpp-oop",
                    "lesson_seq": 53,
                    "current_video_sec": None,
                },
                config=config,
            )
            assert len(recorded_calls) >= 1
            assert recorded_calls[0]["current_video_sec"] == 228
            assert out2["inherited_video_sec"] == 228
            assert out2["missing_deictic_sec"] is False
            assert out2["last_video_sec"] == 228
            assert out2["last_lesson_seq"] == 53
            assert "[NEO THỜI GIAN ĐA LƯỢT]" in out2["user_message_content"]

            commit_assistant_turn(
                session_id=session_id,
                user_prompt="đoạn này thầy giải thích cụ thể hơn được không",
                assistant_response="Thầy ví dụ thuộc tính private không thể truy cập trực tiếp từ ngoài class.",
                current_lesson_seq=53,
                last_course_query=out2.get("last_course_query"),
            )

            # Turn 3: Switch to lesson_seq=54 with deictic query & current_video_sec=None -> resets anchor!
            recorded_calls.clear()
            out3 = await graph.ainvoke(
                {
                    "session_id": session_id,
                    "prompt": "đoạn này giảng gì vậy ạ",
                    "course_id": "cpp-oop",
                    "lesson_seq": 54,
                    "current_video_sec": None,
                },
                config=config,
            )
            assert len(recorded_calls) >= 1
            assert recorded_calls[0]["current_video_sec"] is None
            assert out3["inherited_video_sec"] is None
            assert out3["missing_deictic_sec"] is True
            assert out3["last_video_sec"] is None
            assert out3["last_lesson_seq"] == 54
            assert out3["system_prompt"] == SOCRATIC_GROUNDED_PROMPT
            assert "[MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI]" in out3["user_message_content"]
    finally:
        reset_session_state(session_id)


# ---------------------------------------------------------------------------
# 4. scripts/canonicalize_transcripts_ast.py
# ---------------------------------------------------------------------------
def test_canonicalizer_ast_lexicon_extraction_all_83_lessons():
    manifest = canon.load_manifest()
    all_lessons = canon.iter_manifest_lessons(manifest)
    assert len(all_lessons) == 83

    for course_id, lesson in all_lessons:
        seq = int(lesson["seq"])
        lexicon = canon.extract_lesson_lexicon(course_id, seq)
        assert lexicon["course_id"] == course_id
        assert lexicon["lesson_seq"] == seq
        assert isinstance(lexicon["hotwords_list"], list) and len(lexicon["hotwords_list"]) >= 5
        assert isinstance(lexicon["hotwords_str"], str) and len(lexicon["hotwords_str"].strip()) > 0
        assert isinstance(lexicon["lexicon_prompt"], str) and lesson["title"] in lexicon["lexicon_prompt"]

        hw = canon.extract_lesson_hotwords(course_id, seq, max_hotwords=25)
        assert isinstance(hw, str) and len(hw.strip()) > 0


def test_canonicalizer_lesson_53_ast_lexicon_and_mocked_llm_repair():
    lexicon_53 = canon.extract_lesson_lexicon("cpp-oop", 53)
    assert lexicon_53["has_ast"] is True
    assert len(lexicon_53["ast_files"]) >= 1

    ast_syms = lexicon_53["ast_symbols"]
    assert any(spec in ast_syms["access_specifiers"] for spec in ("private", "public"))
    hotwords_lower = {h.lower() for h in lexicon_53["hotwords_list"]}
    assert "access modifier" in hotwords_lower
    assert "private" in hotwords_lower
    assert "public" in hotwords_lower

    sample_chunks = [
        {
            "chunk_id": "lesson53_chunk_001",
            "start_sec": 228,
            "end_sec": 275,
            "start_label": "03:48",
            "end_label": "04:35",
            "raw_text": "Trong bài học OOP hôm nay chúng ta tìm hiểu về Assets Modifier như private và public trong class.",
        },
        {
            "chunk_id": "lesson53_chunk_002",
            "start_sec": 275,
            "end_sec": 310,
            "start_label": "04:35",
            "end_label": "05:10",
            "raw_text": "Khi khai báo class SinhVien thì các thuộc tính nên đặt trong vùng private để bảo vệ dữ liệu.",
        },
    ]

    captured_user_prompts = []

    def _mock_llm(sys_prompt: str, usr_prompt: str) -> str:
        captured_user_prompts.append(usr_prompt)
        return json.dumps(
            {
                "lesson53_chunk_001": "Trong bài học OOP hôm nay chúng ta tìm hiểu về Access Modifier như private và public trong class.",
                "lesson53_chunk_002": "Khi khai báo class SinhVien thì các thuộc tính nên đặt trong vùng private để bảo vệ dữ liệu.",
            },
            ensure_ascii=False,
        )

    updated_chunks, stats = canon.canonicalize_lesson_chunks(
        sample_chunks,
        lexicon_53,
        llm_fn=_mock_llm,
        batch_size=5,
    )

    assert len(captured_user_prompts) == 1
    assert "access modifier" in captured_user_prompts[0].lower()
    assert "private" in captured_user_prompts[0]
    assert stats["updated"] == 1
    assert stats["unchanged"] == 1
    assert stats["rejected"] == 0
    assert stats["errors"] == 0

    c1, c2 = updated_chunks
    assert c1["chunk_id"] == "lesson53_chunk_001"
    assert c1["start_sec"] == 228
    assert c1["end_sec"] == 275
    assert c1["start_label"] == "03:48"
    assert c1["end_label"] == "04:35"
    assert "Access Modifier" in c1["raw_text"]
    assert "Assets Modifier" not in c1["raw_text"]
    assert c2["raw_text"] == sample_chunks[1]["raw_text"]


def test_validate_canonical_chunk_rejects_summaries_explosions_and_cjk_leakage():
    orig = (
        "Trong lập trình hướng đối tượng C++, Access Modifier gồm private, public và protected "
        "dùng để kiểm soát phạm vi truy cập của thuộc tính và phương thức trong class."
    )

    # Valid phonetic repair passes
    ok, reason = canon.validate_canonical_chunk(
        orig.replace("Access Modifier", "Assets Modifier"),
        orig,
    )
    assert ok is True and reason == "ok"

    # 1. Empty output
    ok, reason = canon.validate_canonical_chunk(orig, "   ")
    assert ok is False and reason == "empty_output"

    # 2. Hallucinated summary (severe shrinkage + rewrite)
    ok, reason = canon.validate_canonical_chunk(
        orig,
        "Tóm tắt: bài giảng nói về phạm vi truy cập OOP.",
    )
    assert ok is False and (
        reason.startswith("length_ratio_out_of_bounds")
        or reason.startswith("word_count_ratio_out_of_bounds")
        or reason.startswith("low_context_retention")
    )

    # 3. Length explosion
    ok, reason = canon.validate_canonical_chunk(
        orig,
        orig + " Ngoài ra giảng viên còn giải thích rất nhiều ví dụ mở rộng chi tiết khác nữa trong video này.",
    )
    assert ok is False and reason.startswith("length_ratio_out_of_bounds")

    # 4. CJK / Hangul leakage
    ok, reason = canon.validate_canonical_chunk(
        orig,
        orig.replace("phạm vi truy cập", "访问控制 phạm vi"),
    )
    assert ok is False and reason == "cjk_or_hangul_hallucination"

    ok, reason = canon.validate_canonical_chunk(
        orig,
        orig.replace("class", "클래스"),
    )
    assert ok is False and reason == "cjk_or_hangul_hallucination"

    # 5. Same-length & same-word-count rewrite (fails token retention >= 0.55)
    same_len_rewrite = (
        "Hôm nay thời tiết rất đẹp nên chúng tôi rủ nhau đi dạo quanh công viên xanh mát, "
        "uống cà phê sữa đá rồi cùng nhau trò chuyện vui vẻ suốt buổi sáng cuối tuần."
    )
    ok, reason = canon.validate_canonical_chunk(orig, same_len_rewrite)
    assert ok is False and reason.startswith("low_context_retention")


@pytest.mark.asyncio
async def test_canonicalizer_async_guardrail_fallback_preserves_original_on_rejection():
    lexicon_53 = canon.extract_lesson_lexicon("cpp-oop", 53)
    orig_text = "Trong bài giảng này thầy giới thiệu về Assets Modifier gồm private và public trong class SinhVien."
    chunks = [
        {
            "chunk_id": "c_guard_01",
            "start_sec": 100,
            "end_sec": 140,
            "start_label": "01:40",
            "end_label": "02:20",
            "raw_text": orig_text,
        }
    ]

    async def _bad_async_llm(sys_prompt: str, usr_prompt: str) -> str:
        return json.dumps(
            {"c_guard_01": "Tóm tắt ngắn: 面向对象 Access Modifier."},
            ensure_ascii=False,
        )

    out_chunks, stats = await canon.canonicalize_lesson_chunks_async(
        chunks,
        lexicon_53,
        llm_fn=_bad_async_llm,
        batch_size=5,
    )

    assert stats["updated"] == 0
    assert stats["rejected"] == 1
    assert out_chunks[0]["raw_text"] == orig_text
    assert out_chunks[0]["start_sec"] == 100
    assert out_chunks[0]["end_sec"] == 140


@pytest.mark.asyncio
async def test_real_router_node_rescues_in_video_temporal_and_deictic_queries():
    """
    End-to-end test through REAL router_node (real SLM-ONNX-INT8 + real mDeBERTa-v3
    NLIArbiter + real CurriculumService, zero router mocks) verifying:
    - Natural video timestamp & deictic queries without C++/thầy keywords are
      rescued cleanly to `course_query` (and NOT misrouted to NavBypass/out_of_scope/chit_chat).
    - Adversarial off-topic time/place queries ("bóng đá", "nấu mì mất 5 phút",
      "quán ăn ngon") and social gratitude remain blocked as out_of_scope / chit_chat.
    """
    from app.services.chat_graph import router_node

    hist = [{"role": "user", "content": "đoạn đầu khoảng 4 phút thầy về vấn đề gì"}]
    anchor = "đoạn đầu khoảng 4 phút thầy về vấn đề gì"

    cases = [
        ("phút thứ 6 nói về vấn đề gì", [], None, "course_query", False),
        ("còn phút thứ 6 thì sao", hist, anchor, "course_query", False),
        ("còn phút thứ 6 thì nói về gì", hist, anchor, "course_query", False),
        ("phút thứ 12 là phần nào vậy", [], None, "course_query", False),
        ("đoạn này là sao", [], None, "course_query", False),
        ("chỗ này chưa hiểu lắm", [], None, "course_query", False),
        ("đoạn đang xem nói về cái gì", [], None, "course_query", False),
        ("phút thứ 6 trận bóng đá hôm nay tỷ số mấy", [], None, "out_of_scope", False),
        ("nấu mì mất 5 phút rồi vớt ra nhé", [], None, "out_of_scope", False),
        ("chỗ này quán ăn nào ngon", [], None, "out_of_scope", False),
        ("cảm ơn bạn nhé", hist, anchor, "chit_chat", False),
    ]

    for prompt, msgs, last_q, exp_intent, exp_nav in cases:
        res = await router_node(
            {
                "prompt": prompt,
                "course_id": "cpp-oop",
                "lesson_seq": 53,
                "messages": msgs,
                "last_course_query": last_q,
                "pending_navigation": None,
            }
        )
        assert res["intent"] == exp_intent, f"Prompt {prompt!r}: expected {exp_intent}, got {res['intent']}"
        assert bool(res.get("is_curriculum_navigation", False)) is exp_nav


def test_curriculum_time_parser_excludes_cooking_minutes_duration():
    svc = get_curriculum_service()
    assert svc.extract_video_time_reference("nấu mì mất 5 phút rồi vớt ra nhé") is None
    assert svc.extract_video_time_reference("phút thứ 6 nói về vấn đề gì") == {
        "kind": "explicit_sec",
        "target_sec": 360,
    }


def test_lesson_11_ast_lexicon_extracts_array_declarator_and_forbidden_mang():
    lex = canon.extract_lesson_lexicon("cpp-core", 11)
    assert lex["has_ast"] is True
    hints_low = [h.lower() for h in lex["ast_symbols"]["concept_hints"]]
    assert "mảng" in hints_low
    assert "mảng một chiều" in hints_low
    assert "Array = Mảng" in lex["lexicon_prompt"]
    assert "mạng" in lex["lexicon_prompt"]


@pytest.mark.asyncio
async def test_spec5_temporal_shift_excludes_chapter_toc_glossary_and_stale_summary():
    """
    [spec-5] M1-T07 regression:
    - crag_grader_node keeps [MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI] in user_message_content.
    - _extract_glossary_lookup_text excludes [MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI] so Mốc 09:09
      ('encapsulation') does not trigger the Encapsulation glossary entry on a 17:22 Constructor turn.
    - context_assembly_node suppresses stale conversation_summary on temporal shift.
    """
    from app.services.chat_graph import (
        _extract_glossary_lookup_text,
        context_assembly_node,
        crag_grader_node,
    )

    prompt = "phút 17:22 có hàm constructor 4 tham số, viết giùm em full code class SinhVien luôn đi"
    state = {
        "prompt": prompt,
        "search_query": prompt,
        "course_id": "cpp-oop",
        "lesson_seq": 53,
        "prev_lesson_seq": 53,
        "prev_video_sec": 373,
        "last_video_sec": 373,
        "last_lesson_seq": 53,
        "retrieval_status": "grounded",
        "is_low_confidence": False,
        "is_curriculum_navigation": False,
        "target_lesson_seq": None,
        "retrieved_chunks": [
            {
                "id": "hit-53-1042",
                "content_type": "video_transcript",
                "lesson_id": "lesson-53",
                "lesson_seq": 53,
                "course_id": "cpp-oop",
                "raw_text": "Ở phút 17:22 thầy viết hàm khởi tạo SinhVien có 4 tham số ma, ten, ns, gpa.",
                "video_title": "lesson-53_oop.mp4",
                "start_sec": 1042,
                "end_sec": 1090,
                "start_label": "17:22",
                "end_label": "18:10",
                "timestamp_tag": '<timestamp sec="1042">17:22</timestamp>',
                "confidence_score": 0.91,
                "is_approximate": False,
            }
        ],
        "messages": [
            {"role": "user", "content": "phút thứ 6 nói về gì"},
            {"role": "assistant", "content": "Ở phút 06:13 thầy giảng về tính đóng gói (Encapsulation)."},
        ],
        "conversation_summary": "Học viên đang theo học Bài 53. Tiến trình thảo luận trước đó: encapsulation và private.",
    }

    grader_out = await crag_grader_node(state)
    assert "[MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI]" not in grader_out["user_message_content"]

    sample_with_toc = (
        grader_out["user_message_content"]
        + "\n\n[MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI]\n- Mốc 09:09: Tính đóng gói (encapsulation)"
    )
    lookup_txt = _extract_glossary_lookup_text(sample_with_toc, prompt)
    assert "[MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI]" not in lookup_txt
    assert "encapsulation" not in lookup_txt.lower()

    merged_state = {**state, **grader_out}
    ctx_out = await context_assembly_node(merged_state)
    final_user_msg = ctx_out["user_message_content"]

    assert "Constructor ->" in final_user_msg
    assert 'Encapsulation -> "Tính đóng gói"' not in final_user_msg
    assert "[BỐI CẢNH TIẾN TRÌNH THẢO LUẬN TRƯỚC ĐÓ CỦA HỌC VIÊN]" not in final_user_msg


@pytest.mark.asyncio
async def test_spec5_multi_topic_disjunction_formats_numbered_branches_and_skips_nav_glossary():
    """
    [spec-5] M2-T05 regression:
    - Multi-topic disjunction ('tôi muốn học con trỏ hay vòng lặp thì xem bài nào') formats
      numbered branch-paired options for both Bài 57 and Bài 6 with explicit list-all cardinality.
    - context_assembly_node skips academic glossary injection and stale conversation_summary on
      out_of_lesson curriculum navigation turns.
    """
    from app.services.chat_graph import context_assembly_node, crag_grader_node

    prompt = "tôi muốn học con trỏ hay vòng lặp thì xem bài nào"
    state = {
        "prompt": prompt,
        "search_query": prompt,
        "course_id": "cpp-core",
        "lesson_seq": 11,
        "prev_lesson_seq": 11,
        "retrieval_status": "out_of_lesson",
        "is_low_confidence": False,
        "is_curriculum_navigation": True,
        "target_lesson_seq": 57,
        "future_best_chunk": {"lesson_seq": 57, "course_id": "cpp-core", "start_sec": 0},
        "retrieved_chunks": [],
        "messages": [
            {"role": "user", "content": "bài này học về cái gì"},
            {"role": "assistant", "content": "Bài 11 giới thiệu mảng một chiều. Bạn muốn xem phần nào trước?"},
        ],
        "conversation_summary": "Học viên đang theo học Bài 11 về mảng một chiều.",
    }

    grader_out = await crag_grader_node(state)
    user_content = grader_out["user_message_content"]
    assert "[CÁC LỰA CHỌN BÀI HỌC PHÙ HỢP TRONG GIÁO TRÌNH]" in user_content
    assert "1. Chủ đề" in user_content
    assert "2. Chủ đề" in user_content
    assert "Bài 57" in user_content
    assert "Bài 6" in user_content
    assert "BẮT BUỘC phải liệt kê ĐẦY ĐỦ CẢ 2 bài học" in user_content

    merged_state = {**state, **grader_out}
    ctx_out = await context_assembly_node(merged_state)
    final_user_msg = ctx_out["user_message_content"]
    assert "[TỪ ĐIỂN THUẬT NGỮ CHUẨN ĐẠI HỌC" not in final_user_msg
    assert "[BỐI CẢNH TIẾN TRÌNH THẢO LUẬN TRƯỚC ĐÓ CỦA HỌC VIÊN]" not in final_user_msg


@pytest.mark.asyncio
async def test_spec6_specific_timestamp_with_grounded_chunks_suppresses_toc_while_relative_filters_by_focus_sec():
    """
    [spec-6] #1:
    - Focused timestamp/player queries with grounded chunks (M1-T05 at 680s, M1-T07 at 1042s)
      suppress [MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI] completely.
    - Relative segment queries ('còn đoạn giữa thì sao' at 2409s) keep [MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI]
      filtered to chapters within ±600s of focus_sec=2409s (excluding Mốc 09:09 encapsulation).
    """
    from app.services.chat_graph import crag_grader_node

    # 1. M1-T05: deictic with grounded chunk at 638s -> no TOC injected
    state_t05 = {
        "prompt": "chỗ này đang dạy gì",
        "search_query": "chỗ này đang dạy gì",
        "course_id": "cpp-oop",
        "lesson_seq": 53,
        "current_video_sec": 680,
        "retrieval_status": "grounded",
        "is_low_confidence": False,
        "is_curriculum_navigation": False,
        "target_lesson_seq": None,
        "retrieved_chunks": [
            {
                "id": "hit-53-638",
                "content_type": "video_transcript",
                "lesson_id": "lesson-53",
                "lesson_seq": 53,
                "course_id": "cpp-oop",
                "raw_text": "Ở đoạn này thầy hướng dẫn khai báo thuộc tính và phương thức.",
                "video_title": "lesson-53_oop.mp4",
                "start_sec": 638,
                "end_sec": 685,
                "start_label": "10:38",
                "end_label": "11:25",
                "timestamp_tag": '<timestamp sec="638">10:38</timestamp>',
                "confidence_score": 0.90,
                "is_approximate": False,
            }
        ],
    }
    out_t05 = await crag_grader_node(state_t05)
    assert "[MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI]" not in out_t05["user_message_content"]
    assert "encapsulation" not in out_t05["user_message_content"].lower()

    # 2. M1-T06: relative segment query ("còn đoạn giữa thì sao") at 2409s -> TOC present but 09:09 excluded
    state_t06 = {
        "prompt": "còn đoạn giữa thì sao",
        "search_query": "còn đoạn giữa thì sao",
        "course_id": "cpp-oop",
        "lesson_seq": 53,
        "current_video_sec": None,
        "retrieval_status": "grounded",
        "is_low_confidence": False,
        "is_curriculum_navigation": False,
        "target_lesson_seq": None,
        "retrieved_chunks": [
            {
                "id": "hit-53-2409",
                "content_type": "video_transcript",
                "lesson_id": "lesson-53",
                "lesson_seq": 53,
                "course_id": "cpp-oop",
                "raw_text": "Ở đoạn giữa video thầy minh họa bài tập sắp xếp danh sách sinh viên.",
                "video_title": "lesson-53_oop.mp4",
                "start_sec": 2409,
                "end_sec": 2460,
                "start_label": "40:09",
                "end_label": "41:00",
                "timestamp_tag": '<timestamp sec="2409">40:09</timestamp>',
                "confidence_score": 0.89,
                "is_approximate": False,
            }
        ],
    }
    out_t06 = await crag_grader_node(state_t06)
    assert "[MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI]" in out_t06["user_message_content"]
    assert "09:09" not in out_t06["user_message_content"]
    assert "encapsulation" not in out_t06["user_message_content"].lower()


@pytest.mark.asyncio
async def test_spec6_anchored_deictic_current_with_player_sec_omits_prior_turn_context_linking():
    """
    [spec-6] #2:
    When a deictic_current query ('chỗ này đang dạy gì') has an active player current_video_sec (e.g. 680s),
    router_node and crag_grader_node must NOT link it back to the prior turn's last_course_query ('phút thứ 6 nói gì').
    """
    from app.services.chat_graph import crag_grader_node, router_node

    r_out = await router_node(
        {
            "prompt": "chỗ này đang dạy gì",
            "course_id": "cpp-oop",
            "lesson_seq": 53,
            "current_video_sec": 680,
            "messages": [
                {"role": "user", "content": "phút thứ 6 nói gì"},
                {"role": "assistant", "content": "Phút thứ 6 nói về tính đóng gói."},
            ],
            "last_course_query": "phút thứ 6 nói gì",
            "pending_navigation": None,
        }
    )
    assert r_out["intent"] == "course_query"
    assert r_out["search_query"] == "chỗ này đang dạy gì"
    assert "phút thứ 6" not in (r_out["search_query"] or "")

    g_out = await crag_grader_node(
        {
            "prompt": "chỗ này đang dạy gì",
            "search_query": "phút thứ 6 nói gì — chỗ này đang dạy gì",
            "course_id": "cpp-oop",
            "lesson_seq": 53,
            "current_video_sec": 680,
            "retrieval_status": "grounded",
            "is_low_confidence": False,
            "is_curriculum_navigation": False,
            "target_lesson_seq": None,
            "retrieved_chunks": [],
        }
    )
    assert "[NGỮ CẢNH HỘI THOẠI LIÊN KẾT]" not in g_out["user_message_content"]
