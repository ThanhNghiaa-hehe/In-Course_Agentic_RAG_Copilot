"""
Comprehensive verification tests for In-Course Playback Temporal Retrieval,
Video Chapters, Current-Video Deictic Grounding, and Multi-Topic Disambiguation.
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.prompts import (
    CURRICULUM_OVERVIEW_PROMPT,
    OUT_OF_LESSON_PROMPT,
    SOCRATIC_GROUNDED_PROMPT,
)
from app.schemas.chat import ChatRequest
from app.services.chat import ChatService
from app.services.chat_graph import (
    crag_grader_node,
    retrieval_node,
    router_node,
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
# 1. Temporal Explicit Query (~phút 4) in cpp-oop Bài 53 stays grounded
# ---------------------------------------------------------------------------
def test_curriculum_explicit_minute_4_stays_current_lesson_no_navbypass():
    c_svc = get_curriculum_service()
    query = "đoạn đầu khoảng phút 4 thầy giảng gì"

    time_ref = c_svc.extract_video_time_reference(query)
    assert time_ref is not None
    assert time_ref["kind"] == "explicit_sec"
    assert time_ref["target_sec"] == 240

    assert c_svc.is_navigation_query(query, current_lesson_seq=53, preferred_course_id="cpp-oop") is False
    assert c_svc.has_current_lesson_reference(query, current_lesson_seq=53, preferred_course_id="cpp-oop") is True

    matched = c_svc.find_lesson_for_query(query, current_lesson_seq=53, preferred_course_id="cpp-oop")
    assert matched is not None
    lesson, _ = matched
    assert lesson["course_id"] == "cpp-oop"
    assert lesson["seq"] == 53


@pytest.mark.asyncio
async def test_retrieval_minute_4_in_lesson_53_returns_240s_segment_no_navbypass():
    hits_53 = [
        _make_video_hit(
            "hit-53-start",
            0.80,
            lesson_seq=53,
            course_id="cpp-oop",
            start_sec=0,
            end_sec=45,
            raw_text="Mở đầu bài học OOP giới thiệu tổng quan.",
            video_title="lesson-53_oop_intro.mp4",
        ),
        _make_video_hit(
            "hit-53-228",
            0.88,
            lesson_seq=53,
            course_id="cpp-oop",
            start_sec=228,
            end_sec=275,
            raw_text="Ở phút thứ 4 thầy giải thích khái niệm Class, thuộc tính private và phương thức public.",
            video_title="lesson-53_oop_intro.mp4",
        ),
        _make_video_hit(
            "hit-53-280",
            0.85,
            lesson_seq=53,
            course_id="cpp-oop",
            start_sec=280,
            end_sec=320,
            raw_text="Ví dụ tạo đối tượng SinhVien từ class vừa khai báo.",
            video_title="lesson-53_oop_intro.mp4",
        ),
        _make_video_hit(
            "hit-53-600",
            0.75,
            lesson_seq=53,
            course_id="cpp-oop",
            start_sec=600,
            end_sec=645,
            raw_text="Phần sau nói về Constructor và Destructor.",
            video_title="lesson-53_oop_intro.mp4",
        ),
        _make_video_hit(
            "hit-01-distractor",
            0.95,
            lesson_seq=1,
            course_id="cpp-core",
            start_sec=240,
            end_sec=280,
            raw_text="Bài 1 giới thiệu khóa học C++.",
            video_title="lesson-01_intro.mp4",
        ),
    ]

    captured_filters = []

    async def _fake_scroll(**kwargs):
        s_filter = kwargs.get("scroll_filter")
        captured_filters.append(s_filter)
        conds = _extract_filter_conditions(s_filter)
        c_val = conds.get("course_id", (None, None))[1]
        l_val = conds.get("lesson_seq", (None, None))[1]
        rng = conds.get("start_sec", (None, (None, None)))[1]
        matched = []
        for h in hits_53:
            p = h.payload
            if c_val and p["course_id"] != c_val:
                continue
            if l_val is not None and p["lesson_seq"] != l_val:
                continue
            if rng and rng[0] is not None and rng[1] is not None:
                if not (rng[0] <= p["start_sec"] <= rng[1]):
                    continue
            matched.append(h)
        return (matched, None)

    fake_qdrant = MagicMock()
    fake_qdrant.scroll = AsyncMock(side_effect=_fake_scroll)
    fake_qdrant.query_points = AsyncMock(side_effect=AssertionError("NavBypass/future probe must not run"))

    svc = RetrievalService(client=fake_qdrant, embedding_service=_make_mock_embedding_service())
    res = await svc.hybrid_search(
        query_text="đoạn đầu khoảng phút 4 thầy giảng gì",
        course_id="cpp-oop",
        current_lesson_seq=53,
    )

    assert captured_filters, "Expected temporal scroll filter to be constructed"
    conds = _extract_filter_conditions(captured_filters[0])
    assert conds["course_id"] == ("match", "cpp-oop")
    assert conds["lesson_seq"] == ("match", 53)
    assert conds["content_type"] == ("match", "video_transcript")
    assert conds["start_sec"] == ("range", (150, 330))

    assert res.status == "grounded"
    assert res.target_lesson_seq is None
    assert res.is_low_confidence is False
    assert len(res.chunks) >= 1
    assert all(ch["lesson_seq"] == 53 for ch in res.chunks)
    assert any(210 <= ch["start_sec"] <= 285 for ch in res.chunks)
    assert res.chunks[0]["start_sec"] == 228


@pytest.mark.asyncio
async def test_graph_pipeline_minute_4_in_lesson_53_stays_socratic_grounded():
    query = "đoạn đầu khoảng phút 4 thầy giảng gì"
    fake_retrieval = MagicMock()
    fake_retrieval.hybrid_search = AsyncMock(
        return_value=RetrievalResult(
            chunks=[
                {
                    "id": "hit-53-228",
                    "content_type": "video_transcript",
                    "lesson_id": "lesson-53",
                    "lesson_seq": 53,
                    "course_id": "cpp-oop",
                    "raw_text": "Thầy giảng về Class, Object và phạm vi truy cập private/public.",
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
    )

    base_state = {
        "session_id": "test-temporal-53",
        "turn_count": 1,
        "messages": [],
        "conversation_summary": None,
        "prompt": query,
        "course_id": "cpp-oop",
        "lesson_seq": 53,
        "current_video_sec": None,
        "intent": "course_query",
        "direct_response": None,
        "is_course_query": True,
        "search_query": None,
        "last_course_query": None,
        "is_curriculum_navigation": False,
        "retrieval_status": "coverage_gap",
        "retrieved_chunks": [],
        "is_approximate": False,
        "is_low_confidence": False,
        "target_lesson_seq": None,
        "future_best_chunk": None,
        "suggested_timestamps": [],
        "sources": [],
        "pending_navigation": None,
        "action": None,
        "system_prompt": "",
        "user_message_content": "",
        "assembled_messages": [],
    }

    r_out = await router_node(base_state)
    assert r_out["is_course_query"] is True
    assert r_out["is_curriculum_navigation"] is False
    base_state.update(r_out)

    with patch("app.services.chat_graph.get_retrieval_service", return_value=fake_retrieval):
        ret_out = await retrieval_node(base_state)

    assert ret_out["retrieval_status"] == "grounded"
    assert ret_out["is_curriculum_navigation"] is False
    assert ret_out["target_lesson_seq"] is None
    base_state.update(ret_out)

    grader_out = await crag_grader_node(base_state)
    assert grader_out["system_prompt"] == SOCRATIC_GROUNDED_PROMPT
    assert grader_out["system_prompt"] != CURRICULUM_OVERVIEW_PROMPT
    assert any(ts["sec"] == 228 and ts["lesson_seq"] == 53 for ts in grader_out["suggested_timestamps"])
    assert "[MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI]" in grader_out["user_message_content"]


# ---------------------------------------------------------------------------
# 2. Deictic Query ("đoạn này thầy nói gì") with current_video_sec=462
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_deictic_current_video_sec_462_retrieves_matching_lesson_53_segment():
    c_svc = get_curriculum_service()
    query = "đoạn này thầy nói gì"
    time_ref = c_svc.extract_video_time_reference(query)
    assert time_ref == {"kind": "deictic_current", "target_sec": None}

    hits_53 = [
        _make_video_hit(
            "hit-53-060",
            0.75,
            lesson_seq=53,
            course_id="cpp-oop",
            start_sec=60,
            end_sec=110,
            raw_text="Giới thiệu khái niệm OOP.",
        ),
        _make_video_hit(
            "hit-53-440",
            0.84,
            lesson_seq=53,
            course_id="cpp-oop",
            start_sec=440,
            end_sec=485,
            raw_text="Tại phút 7:20-8:05 thầy hướng dẫn viết constructor mặc định và constructor có tham số.",
        ),
        _make_video_hit(
            "hit-53-800",
            0.72,
            lesson_seq=53,
            course_id="cpp-oop",
            start_sec=800,
            end_sec=850,
            raw_text="Giải thích hàm hủy Destructor và từ khóa this.",
        ),
    ]

    captured_filters = []

    async def _fake_scroll(**kwargs):
        s_filter = kwargs.get("scroll_filter")
        captured_filters.append(s_filter)
        conds = _extract_filter_conditions(s_filter)
        rng = conds.get("start_sec", (None, (None, None)))[1]
        matched = [
            h for h in hits_53
            if h.payload["course_id"] == conds["course_id"][1]
            and h.payload["lesson_seq"] == conds["lesson_seq"][1]
            and (rng[0] is None or rng[0] <= h.payload["start_sec"] <= rng[1])
        ]
        return (matched, None)

    fake_qdrant = MagicMock()
    fake_qdrant.scroll = AsyncMock(side_effect=_fake_scroll)
    fake_qdrant.query_points = AsyncMock(side_effect=AssertionError("Should not fall back to future probe"))

    svc = RetrievalService(client=fake_qdrant, embedding_service=_make_mock_embedding_service())
    res = await svc.hybrid_search(
        query_text=query,
        course_id="cpp-oop",
        current_lesson_seq=53,
        current_video_sec=462,
    )

    assert captured_filters
    conds = _extract_filter_conditions(captured_filters[0])
    assert conds["course_id"] == ("match", "cpp-oop")
    assert conds["lesson_seq"] == ("match", 53)
    assert conds["start_sec"] == ("range", (372, 552))

    assert res.status == "grounded"
    assert len(res.chunks) == 1
    assert res.chunks[0]["lesson_seq"] == 53
    assert res.chunks[0]["start_sec"] == 440
    assert res.chunks[0]["end_sec"] == 485


@pytest.mark.asyncio
async def test_chat_stream_passes_current_video_sec_462_into_hybrid_search():
    recorded_calls = []

    async def _spy_hybrid_search(**kwargs):
        recorded_calls.append(kwargs)
        sec = kwargs.get("current_video_sec") or 0
        return RetrievalResult(
            chunks=[
                {
                    "id": "hit-53-440",
                    "content_type": "video_transcript",
                    "lesson_id": "lesson-53",
                    "lesson_seq": 53,
                    "course_id": "cpp-oop",
                    "raw_text": f"Đoạn video quanh giây {sec} giảng về constructor.",
                    "video_title": "lesson-53_oop_intro.mp4",
                    "start_sec": 440,
                    "end_sec": 485,
                    "start_label": "07:20",
                    "end_label": "08:05",
                    "timestamp_tag": '<timestamp sec="440">07:20</timestamp>',
                    "confidence_score": 0.94,
                    "confidence_pct": 94.0,
                    "is_approximate": False,
                }
            ],
            status="grounded",
            is_approximate=False,
            is_low_confidence=False,
        )

    fake_retrieval = MagicMock()
    fake_retrieval.hybrid_search = AsyncMock(side_effect=_spy_hybrid_search)

    async def _fake_stream_chunks():
        yield SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content='Ở đoạn này thầy giải thích constructor. Bạn thử đoán khi nào constructor được gọi? <timestamp sec="440">07:20</timestamp>'
                    )
                )
            ]
        )

    fake_openai = MagicMock()
    fake_openai.chat.completions.create = AsyncMock(return_value=_fake_stream_chunks())

    req = ChatRequest(
        prompt="đoạn này thầy nói gì",
        course_id="cpp-oop",
        lesson_seq=53,
        current_video_sec=462,
        session_id="test-stream-462",
    )

    chat_svc = ChatService(openai_client=fake_openai)
    events = []
    with patch("app.services.chat_graph.get_retrieval_service", return_value=fake_retrieval):
        async for ev in chat_svc.stream_chat(req):
            events.append(ev)

    assert len(recorded_calls) >= 1
    assert recorded_calls[0]["current_video_sec"] == 462
    assert recorded_calls[0]["course_id"] == "cpp-oop"
    assert recorded_calls[0]["current_lesson_seq"] == 53

    meta_events = [json.loads(e["data"]) for e in events if e["event"] == "metadata"]
    assert len(meta_events) == 1
    meta = meta_events[0]
    assert meta["retrieval_status"] == "grounded"
    assert meta["target_lesson_seq"] is None
    assert any(ts["sec"] == 440 for ts in meta["suggested_timestamps"])


# ---------------------------------------------------------------------------
# 3. Disambiguation query: "tôi muốn con trỏ hay vòng lặp"
# ---------------------------------------------------------------------------
def test_disambiguation_pointer_or_loop_detects_ambiguity_and_real_candidates():
    c_svc = get_curriculum_service()
    res = c_svc.find_ambiguous_candidates(
        "tôi muốn con trỏ hay vòng lặp",
        current_lesson_seq=1,
        preferred_course_id="cpp-core",
    )

    assert res["is_ambiguous"] is True
    assert res["reason"] == "multi_topic_disjunction"
    assert len(res["branches"]) >= 2
    assert len(res["candidates"]) >= 2

    manifest = json.loads(Path("data/curriculum/lessons_manifest.json").read_text(encoding="utf-8"))
    manifest_map = {
        (cid, int(les["seq"])): les["title"]
        for cid, cdata in manifest["courses"].items()
        for les in cdata["lessons"]
    }

    cand_seqs = set()
    for cand in res["candidates"]:
        key = (cand["course_id"], int(cand["seq"]))
        assert key in manifest_map, f"Candidate {key} is not a real manifest lesson"
        assert cand["title"] == manifest_map[key]
        assert isinstance(cand["score"], float) and cand["score"] > 0
        cand_seqs.add(int(cand["seq"]))

    # Must represent both pointer and loop concepts across real lessons
    assert any(seq in (57, 48, 64) for seq in cand_seqs), f"Expected pointer lesson in {cand_seqs}"
    assert any(seq in (6, 67) for seq in cand_seqs), f"Expected loop lesson in {cand_seqs}"

    # Yes/no tail ("hay không") must NOT be misdetected as multi_topic_disjunction
    yes_no_res = c_svc.find_ambiguous_candidates(
        "có bài học nào về con trỏ không",
        current_lesson_seq=1,
        preferred_course_id="cpp-core",
    )
    assert yes_no_res["reason"] != "multi_topic_disjunction"


@pytest.mark.asyncio
async def test_crag_grader_injects_disambiguation_options_without_guessing():
    state = {
        "prompt": "tôi muốn con trỏ hay vòng lặp",
        "search_query": "tôi muốn con trỏ hay vòng lặp",
        "course_id": "cpp-core",
        "lesson_seq": 1,
        "retrieved_chunks": [],
        "retrieval_status": "out_of_lesson",
        "is_low_confidence": False,
        "target_lesson_seq": 57,
        "is_curriculum_navigation": True,
        "future_best_chunk": {"lesson_seq": 57, "course_id": "cpp-oop", "start_sec": 0},
    }
    res = await crag_grader_node(state)
    assert res["system_prompt"] in (CURRICULUM_OVERVIEW_PROMPT, OUT_OF_LESSON_PROMPT)
    assert "[CÁC LỰA CHỌN BÀI HỌC PHÙ HỢP TRONG GIÁO TRÌNH]" in res["user_message_content"]
    assert "Bài 57" in res["user_message_content"] or "Bài 48" in res["user_message_content"]
    assert "Bài 6" in res["user_message_content"]
    assert res["pending_navigation"] is None
    assert res["suggested_timestamps"] == []


# ---------------------------------------------------------------------------
# 4. playground.html wires current_video_sec safely into /api/v1/chat/stream
# ---------------------------------------------------------------------------
def test_playground_html_wires_current_video_sec_safely():
    html = Path("app/templates/playground.html").read_text(encoding="utf-8")

    assert "function getSafeCurrentVideoSec()" in html
    assert "ytPlayer.getCurrentTime" in html
    assert "Math.floor" in html
    assert "Number.isFinite" in html
    assert "current_video_sec:" in html
    assert "fetch('/api/v1/chat/stream'" in html

    # Extract inline script block and validate JS syntax with node --check when available
    script_start = html.rfind("<script>")
    script_end = html.rfind("</script>")
    assert script_start != -1 and script_end > script_start
    js_code = html[script_start + len("<script>") : script_end]

    # Verify getSafeCurrentVideoSec and stream payload appear inside the active script
    assert "current_video_sec: reqVideoSec" in js_code or "current_video_sec:" in js_code

    node_bin = shutil.which("node")
    if node_bin:
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as tmp:
            tmp.write(js_code)
            tmp_path = Path(tmp.name)
        try:
            proc = subprocess.run([node_bin, "--check", str(tmp_path)], capture_output=True, text=True)
            assert proc.returncode == 0, f"JS syntax error: {proc.stderr}"
        finally:
            tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 5. lessons_manifest.json video_chapters across all 83 lessons + legacy fields
# ---------------------------------------------------------------------------
def _has_cjk(text: str) -> bool:
    return any(
        (0x4E00 <= ord(c) <= 0x9FFF)
        or (0x3400 <= ord(c) <= 0x4DBF)
        or (0xF900 <= ord(c) <= 0xFAFF)
        or (0x3000 <= ord(c) <= 0x303F)
        for c in text
    )


def test_lessons_manifest_has_valid_video_chapters_across_all_83_lessons():
    manifest = json.loads(Path("data/curriculum/lessons_manifest.json").read_text(encoding="utf-8"))
    courses = manifest["courses"]
    assert set(courses.keys()) >= {"cpp-core", "cpp-oop"}

    core_lessons = courses["cpp-core"]["lessons"]
    oop_lessons = courses["cpp-oop"]["lessons"]
    assert len(core_lessons) == 52
    assert len(oop_lessons) == 31

    all_lessons = core_lessons + oop_lessons
    assert len(all_lessons) == 83

    c_svc = get_curriculum_service()

    by_seq = {}
    for course_id, cdata in courses.items():
        for les in cdata["lessons"]:
            seq = les["seq"]
            by_seq[(course_id, seq)] = les
            assert isinstance(seq, int) and seq >= 1
            assert isinstance(les.get("title"), str) and les["title"].strip()
            assert isinstance(les.get("keywords"), list) and len(les["keywords"]) >= 1

            chapters = les.get("video_chapters")
            assert isinstance(chapters, list) and 5 <= len(chapters) <= 8, (
                f"{course_id} Bài {seq} invalid chapter count: {len(chapters) if isinstance(chapters, list) else None}"
            )
            prev_sec = -1
            for ch in chapters:
                assert isinstance(ch.get("sec"), int) and ch["sec"] >= 0
                assert ch["sec"] >= prev_sec, f"{course_id} Bài {seq} chapters not sorted"
                prev_sec = ch["sec"]

                lbl = ch.get("label", "")
                assert isinstance(lbl, str) and ":" in lbl
                parts = lbl.split(":")
                assert len(parts) == 2 and all(p.isdigit() for p in parts)

                summary = ch.get("summary", "")
                assert isinstance(summary, str) and len(summary.strip()) >= 5
                assert not _has_cjk(summary), f"CJK leak in {course_id} Bài {seq} chapter summary: {summary}"

            svc_chapters = c_svc.get_lesson_chapters(seq, course_id=course_id)
            assert svc_chapters == chapters

    # Spot-check preserved legacy flags & fields
    assert by_seq[("cpp-core", 4)].get("is_foundational") is True
    assert "description" in by_seq[("cpp-core", 4)]
    assert by_seq[("cpp-core", 12)].get("is_revision") is True
    assert by_seq[("cpp-core", 12)].get("updates_lesson_seq") == 11
    assert by_seq[("cpp-oop", 53)].get("is_foundational") is True
