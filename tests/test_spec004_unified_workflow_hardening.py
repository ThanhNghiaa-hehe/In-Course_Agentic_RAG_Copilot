"""
Unit & Integration Tests for Unified E2E Spec 004 (`004-unified-rag-workflow-hardening` v2.0).
Locks Problem Classes PC-01..PC-07 and Cross-Layer Conflict Matrix C1..C13 invariants.
Zero benchmark IDs and zero verbatim E2E test prompts.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.prompts import CURRICULUM_OVERVIEW_PROMPT, OUT_OF_LESSON_PROMPT
from app.agent.router import IntentRouter, NLIArbiter, _load_router_manifest
from app.schemas.chat import ChatRequest, RouterClassification, StreamMetadataEvent
from app.services.chat import ChatService
from app.services.chat_graph import crag_grader_node, retrieval_node
from app.services.curriculum import get_curriculum_service
from app.services.retrieval import (
    RetrievalResult,
    RetrievalService,
    grade_document_relevance,
)
from app.services.telemetry_critic import get_telemetry_critic_service


def _make_hit(
    hit_id: str,
    score: float,
    lesson_seq: int,
    course_id: str = "cpp-core",
    content_type: str = "video_transcript",
    raw_text: str = "Nội dung bài giảng C++ chi tiết.",
    video_title: str = "",
    start_sec: int = 120,
    end_sec: int = 180,
    code_scope: str = "helper_fn",
    approx_video_sec=None,
):
    payload = {
        "course_id": course_id,
        "lesson_id": f"lesson-{lesson_seq:02d}",
        "lesson_seq": lesson_seq,
        "content_type": content_type,
        "raw_text": raw_text,
    }
    if content_type == "code_ast":
        payload.update(
            {
                "file_path": f"lesson_{lesson_seq:02d}/sample.cpp",
                "language": "cpp",
                "code_scope": code_scope,
                "start_line": 1,
                "end_line": 12,
                "context_code": raw_text,
                "approx_video_sec": approx_video_sec,
            }
        )
    else:
        payload.update(
            {
                "video_title": video_title or f"lesson-{lesson_seq:02d}_lecture.mp4",
                "start_sec": start_sec,
                "end_sec": end_sec,
                "start_label": f"{start_sec // 60:02d}:{start_sec % 60:02d}",
                "end_label": f"{end_sec // 60:02d}:{end_sec % 60:02d}",
            }
        )
    return SimpleNamespace(id=hit_id, score=score, payload=payload)


def _make_mock_embedding(rerank_fn):
    emb = MagicMock()
    emb.embed_query_dense.return_value = [0.1] * 8
    emb.embed_query_sparse.return_value = ([1, 2], [0.5, 0.5])
    emb.rerank_documents_async = AsyncMock(side_effect=rerank_fn)
    return emb


def _is_future_qdrant_filter(q_filter) -> bool:
    for cond in getattr(q_filter, "must", None) or []:
        if getattr(cond, "key", None) == "lesson_seq":
            rng = getattr(cond, "range", None)
            if rng is not None and getattr(rng, "gt", None) is not None:
                return True
    return False


# ==============================================================================
# PC-01: Unresolved Self-Match Nav, Counterexamples & Downstream CRAG Sync
# ==============================================================================


@pytest.mark.asyncio
async def test_pc01_unresolved_self_match_nav_runs_ce_and_routes_to_future_lesson():
    """
    REQ-01: When is_curriculum_navigation=True and CurriculumService matches
    current_lesson_seq without explicit_seq/curr_ref/overview, RetrievalService
    must run Cross-Encoder on both current and future candidates and route to
    out_of_lesson when S_future >= 0.40 and margin >= -0.12 (not a revision).
    """
    c_svc = get_curriculum_service()
    l53 = c_svc.get_lesson_by_seq(53, course_id="cpp-oop")
    assert l53 is not None

    curr_hits = [
        _make_hit(
            "cur-53",
            0.85,
            lesson_seq=53,
            course_id="cpp-oop",
            raw_text="Khái niệm class và thuộc tính đối tượng trong bài nhập môn OOP.",
            start_sec=300,
        )
    ]
    fut_hits = [
        _make_hit(
            "fut-54",
            0.70,
            lesson_seq=54,
            course_id="cpp-oop",
            content_type="code_ast",
            code_scope="class_Counter_static",
            raw_text="class Counter { public: static int total; };",
            approx_video_sec=245,
        )
    ]

    async def _fake_query_points(**kwargs):
        prefetch = kwargs.get("prefetch") or []
        f = prefetch[0].filter if prefetch else None
        return SimpleNamespace(points=fut_hits if _is_future_qdrant_filter(f) else curr_hits)

    rerank_calls = []

    async def _fake_rerank(*, query: str, documents: list[str]):
        rerank_calls.append(len(documents))
        # Current gets slightly higher raw logit than future (~0.53 vs ~0.46) -> margin ~ -0.07 >= -0.12
        return [0.15 if "class Counter" not in d else -0.25 for d in documents]

    fake_qdrant = MagicMock()
    fake_qdrant.query_points = AsyncMock(side_effect=_fake_query_points)
    fake_emb = _make_mock_embedding(_fake_rerank)
    svc = RetrievalService(client=fake_qdrant, embedding_service=fake_emb)

    with patch.object(c_svc, "find_lesson_for_query", return_value=(l53, l53["title"])):
        res = await svc.search(
            query_text="muốn đếm tổng số đối tượng dùng chung biến cho cả lớp thì xem bài nào",
            course_id="cpp-oop",
            current_lesson_seq=53,
            is_curriculum_navigation=True,
        )

    assert len(rerank_calls) == 2
    assert res.status == "out_of_lesson"
    assert res.target_lesson_seq == 54
    assert res.skip_nav_rerank is False
    assert res.scoring_source == "cross_encoder"
    assert res.curriculum_matched_seq == 53
    assert res.future_best_chunk is not None
    assert res.future_best_chunk["scoring_source"] == "cross_encoder"
    assert res.future_best_chunk["confidence_score"] >= 0.40


@pytest.mark.asyncio
async def test_pc01_unresolved_self_match_stays_grounded_for_current_core_or_revision():
    """
    REQ-02: Under unresolved self-match nav, if future_score < 0.40 or
    margin < -0.12 or target is a revision of current lesson, stay grounded.
    """
    c_svc = get_curriculum_service()
    l53 = c_svc.get_lesson_by_seq(53, course_id="cpp-oop")
    l11 = c_svc.get_lesson_by_seq(11, course_id="cpp-core")
    assert l53 is not None and l11 is not None
    assert c_svc.is_revision_of(12, 11) is True

    # Case A: current core question -> future score < 0.40 -> stays grounded
    curr_53 = [_make_hit("c53", 0.88, 53, "cpp-oop", raw_text="Đóng gói private và hàm khởi tạo.")]
    fut_54 = [_make_hit("f54", 0.45, 54, "cpp-oop", raw_text="Từ khóa friend và static.")]

    async def _qp_a(**kwargs):
        f = (kwargs.get("prefetch") or [None])[0].filter
        return SimpleNamespace(points=fut_54 if _is_future_qdrant_filter(f) else curr_53)

    async def _rr_a(*, query: str, documents: list[str]):
        return [1.2 if "Đóng gói" in d else -1.5 for d in documents]

    fake_qdrant_a = MagicMock()
    fake_qdrant_a.query_points = AsyncMock(side_effect=_qp_a)
    svc_a = RetrievalService(client=fake_qdrant_a, embedding_service=_make_mock_embedding(_rr_a))

    with patch.object(c_svc, "find_lesson_for_query", return_value=(l53, l53["title"])):
        res_a = await svc_a.search(
            query_text="tính đóng gói và hàm tạo học ở bài nào",
            course_id="cpp-oop",
            current_lesson_seq=53,
            is_curriculum_navigation=True,
        )

    assert res_a.status == "grounded"
    assert res_a.target_lesson_seq is None
    assert res_a.skip_nav_rerank is False
    assert res_a.scoring_source == "cross_encoder"

    # Case B: target lesson 12 is_revision_of(12, 11) even with high CE -> Revision Non-Dominance Shield keeps grounded
    curr_11 = [_make_hit("c11", 0.80, 11, "cpp-core", raw_text="Mảng một chiều cơ bản trong C++.")]
    fut_12 = [_make_hit("f12", 0.85, 12, "cpp-core", raw_text="Luyện tập thêm về mảng một chiều.")]

    async def _qp_b(**kwargs):
        f = (kwargs.get("prefetch") or [None])[0].filter
        return SimpleNamespace(points=fut_12 if _is_future_qdrant_filter(f) else curr_11)

    async def _rr_b(*, query: str, documents: list[str]):
        return [0.4 if "Mảng một chiều" in d else 1.2 for d in documents]

    fake_qdrant_b = MagicMock()
    fake_qdrant_b.query_points = AsyncMock(side_effect=_qp_b)
    svc_b = RetrievalService(client=fake_qdrant_b, embedding_service=_make_mock_embedding(_rr_b))

    with patch.object(c_svc, "find_lesson_for_query", return_value=(l11, l11["title"])):
        res_b = await svc_b.search(
            query_text="phần tử mảng một chiều xem ở bài nào",
            course_id="cpp-core",
            current_lesson_seq=11,
            is_curriculum_navigation=True,
        )

    assert res_b.status == "grounded"
    assert res_b.target_lesson_seq is None


@pytest.mark.asyncio
async def test_pc01_verified_in_window_nav_preserves_focus_for_earlier_or_explicit_or_curr_ref():
    """
    REQ-02 / C2: nav_label_verified_in_window=True when matched < current,
    explicit_seq <= current, has_curr_ref, or is_overview -> skip_nav_rerank=True,
    scoring_source='nav_verified_rrf', stays grounded inside window.
    """
    c_svc = get_curriculum_service()
    l6 = c_svc.get_lesson_by_seq(6, course_id="cpp-core")
    l53 = c_svc.get_lesson_by_seq(53, course_id="cpp-oop")
    assert l6 is not None and l53 is not None

    hits_6 = [_make_hit("h6", 0.85, 6, "cpp-core", raw_text="Vòng lặp for và while trong C++.")]
    hits_53 = [_make_hit("h53", 0.85, 53, "cpp-oop", raw_text="Hàm hủy và hàm khởi tạo lớp SinhVien.")]

    async def _qp_6(**kwargs):
        f = (kwargs.get("prefetch") or [None])[0].filter
        return SimpleNamespace(points=[] if _is_future_qdrant_filter(f) else hits_6)

    async def _qp_53(**kwargs):
        f = (kwargs.get("prefetch") or [None])[0].filter
        return SimpleNamespace(points=[] if _is_future_qdrant_filter(f) else hits_53)

    mock_emb = _make_mock_embedding(
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("Cross-Encoder must be skipped when nav_label_verified_in_window=True"))
    )

    # (a) matched < current
    svc1 = RetrievalService(client=MagicMock(query_points=AsyncMock(side_effect=_qp_6)), embedding_service=mock_emb)
    with patch.object(c_svc, "find_lesson_for_query", return_value=(l6, l6["title"])):
        r_earlier = await svc1.search(
            query_text="vòng lặp for học ở bài nào",
            course_id="cpp-core",
            current_lesson_seq=11,
            is_curriculum_navigation=True,
        )
    assert r_earlier.status == "grounded"
    assert r_earlier.skip_nav_rerank is True
    assert r_earlier.scoring_source == "nav_verified_rrf"

    # (b) explicit_seq <= current
    svc2 = RetrievalService(client=MagicMock(query_points=AsyncMock(side_effect=_qp_53)), embedding_service=mock_emb)
    with patch.object(c_svc, "find_lesson_for_query", return_value=(l53, l53["title"])):
        r_explicit = await svc2.search(
            query_text="quay lại bài 53 xem phần hàm hủy ở đâu",
            course_id="cpp-oop",
            current_lesson_seq=53,
            is_curriculum_navigation=True,
        )
        # (c) has_curr_ref=True
        r_curr_ref = await svc2.search(
            query_text="trong bài này có nội dung gì quan trọng",
            course_id="cpp-oop",
            current_lesson_seq=53,
            is_curriculum_navigation=True,
        )
        # (d) is_overview=True
        r_overview = await svc2.search(
            query_text="bài này học về cái gì",
            course_id="cpp-oop",
            current_lesson_seq=53,
            is_curriculum_navigation=True,
        )

    for res in (r_explicit, r_curr_ref, r_overview):
        assert res.status == "grounded"
        assert res.skip_nav_rerank is True
        assert res.scoring_source == "nav_verified_rrf"


@pytest.mark.asyncio
async def test_pc01_crag_grader_preserves_ce_resolved_future_target_over_syllabus_and_competing_lessons():
    """
    REQ-01 / C3: When retrieval_status='out_of_lesson' has Cross-Encoder f_chunk >= 0.40,
    crag_grader_node does NOT let find_lesson_for_query overwrite target or let
    competing_lessons drop sources/timestamps, while multi_topic_disjunction still stays ambiguous.
    """
    c_svc = get_curriculum_service()
    l53 = c_svc.get_lesson_by_seq(53, course_id="cpp-oop")
    l54 = c_svc.get_lesson_by_seq(54, course_id="cpp-oop")
    assert l53 is not None and l54 is not None

    ce_f_chunk = {
        "id": "fut_54_ce",
        "lesson_id": "lesson-54",
        "course_id": "cpp-oop",
        "lesson_seq": 54,
        "content_type": "video_transcript",
        "score": 0.48,
        "confidence_score": 0.48,
        "confidence_pct": 48.0,
        "is_approximate": False,
        "start_sec": 310,
        "start_label": "05:10",
        "video_title": l54["title"],
        "timestamp_tag": '<timestamp sec="310">05:10</timestamp>',
        "raw_text": "Biến tĩnh static thuộc về cả lớp, dùng chung cho mọi đối tượng.",
        "scoring_source": "cross_encoder",
    }

    base_state = {
        "prompt": "muốn dùng biến dùng chung cho cả class học bài nào",
        "search_query": "muốn dùng biến dùng chung cho cả class học bài nào",
        "course_id": "cpp-oop",
        "lesson_seq": 53,
        "retrieval_status": "out_of_lesson",
        "target_lesson_seq": 54,
        "future_best_chunk": ce_f_chunk,
        "retrieved_chunks": [],
        "is_curriculum_navigation": True,
        "is_low_confidence": False,
        "is_approximate": False,
    }

    competing_amb = {
        "is_ambiguous": True,
        "reason": "competing_lessons",
        "branches": [],
        "candidates": [
            {"seq": 53, "course_id": "cpp-oop", "title": l53["title"]},
            {"seq": 54, "course_id": "cpp-oop", "title": l54["title"]},
        ],
    }
    with patch.object(c_svc, "find_lesson_for_query", return_value=(l53, l53["title"])), patch.object(
        c_svc, "find_ambiguous_candidates", return_value=competing_amb
    ):
        res_resolved = await crag_grader_node(base_state)

    assert res_resolved["system_prompt"] == OUT_OF_LESSON_PROMPT
    assert len(res_resolved["sources"]) == 1
    assert res_resolved["sources"][0]["lesson_seq"] == 54
    assert len(res_resolved["suggested_timestamps"]) == 1
    assert res_resolved["suggested_timestamps"][0]["sec"] == 310
    assert "[HỌC LIỆU BÀI GIẢNG TƯƠNG LAI ĐỂ GIẢI THÍCH BẢN CHẤT]" in res_resolved["user_message_content"]

    # multi_topic_disjunction must remain ambiguous
    disj_amb = {
        "is_ambiguous": True,
        "reason": "multi_topic_disjunction",
        "branches": ["con trỏ", "vòng lặp"],
        "candidates": [
            {"seq": 57, "course_id": "cpp-oop", "title": "Con trỏ"},
            {"seq": 6, "course_id": "cpp-core", "title": "Vòng lặp"},
        ],
    }
    with patch.object(c_svc, "find_ambiguous_candidates", return_value=disj_amb):
        res_disj = await crag_grader_node({
            **base_state,
            "prompt": "muốn học con trỏ hay vòng lặp thì xem bài nào",
        })
    assert res_disj["system_prompt"] == CURRICULUM_OVERVIEW_PROMPT
    assert res_disj["sources"] == []


# ==============================================================================
# PC-02: Contextual NLI `and` Guard & Temporal NLI Fail-Closed
# ==============================================================================


def test_pc02_contextual_nli_requires_and_not_or():
    """
    REQ-03: classify_contextual must require BOTH nli_intent == 'course_query'
    AND nli_conf >= ROUTER_CONTEXTUAL_NLI_MIN_CONF.
    """
    router = IntentRouter.__new__(IntentRouter)
    router._manifest_data = _load_router_manifest()
    router._solicitation_words = []
    router._slm_session = None
    router._nli_arbiter = MagicMock()
    router.is_pure_social = MagicMock(return_value=(False, 0.0))
    router.is_social_acknowledgment = MagicMock(return_value=(False, 0.0))
    router.is_topic_shift = MagicMock(return_value=(False, 0.90))
    router.is_curriculum_navigation = MagicMock(return_value=(False, 0.10))
    router._get_slm_probs = MagicMock(return_value=[0.10, 0.20, 0.70])  # skips SLM rescue
    oos_clf = RouterClassification(intent="out_of_scope", direct_response="Ngoài lề", is_course_query=False)
    router.classify = MagicMock(return_value=oos_clf)

    # 1. High conf out_of_scope must NOT rescue to course_query
    router._nli_arbiter.arbitrate.return_value = ("out_of_scope", 0.88)
    clf1, q1 = router.classify_contextual("vậy tỷ số bao nhiêu", anchor_query="biến trong C++")
    assert clf1.intent == "out_of_scope"
    assert q1 == "vậy tỷ số bao nhiêu"

    # 2. Low conf course_query (< 0.45) must NOT rescue
    router._nli_arbiter.arbitrate.return_value = ("course_query", 0.40)
    clf2, q2 = router.classify_contextual("ý đó sao", anchor_query="biến trong C++")
    assert clf2.intent == "out_of_scope"
    assert q2 == "ý đó sao"

    # 3. course_query AND >= 0.45 DOES rescue
    router._nli_arbiter.arbitrate.return_value = ("course_query", 0.55)
    clf3, q3 = router.classify_contextual("ý đó dùng sao", anchor_query="biến trong C++")
    assert clf3.intent == "course_query"
    assert "biến trong C++" in q3


def test_pc02_temporal_nli_fail_closed_on_pipeline_unavailable_or_error():
    """
    REQ-03 / C5: NLIArbiter loads temporal_nli_* from router_intent_manifest.json
    and fails closed (False, 1.0) when pipeline is None or raises an exception.
    """
    manifest = _load_router_manifest()
    assert "temporal_nli_template" in manifest
    assert "temporal_nli_labels" in manifest
    assert "temporal_nli_offtopic_threshold" in manifest

    arbiter = NLIArbiter(manifest)
    assert arbiter._temporal_template == manifest["temporal_nli_template"]
    assert arbiter._temporal_offtopic_threshold == pytest.approx(float(manifest["temporal_nli_offtopic_threshold"]))

    # Pipeline unavailable -> fail-closed
    arbiter._get_pipeline = MagicMock(return_value=None)
    assert arbiter.verify_in_video_temporal_query("phút thứ 6 nói gì") == (False, 1.0)

    # Pipeline raises -> fail-closed
    arbiter._get_pipeline = MagicMock(return_value=MagicMock(side_effect=RuntimeError("boom")))
    assert arbiter.verify_in_video_temporal_query("phút thứ 6 nói gì") == (False, 1.0)

    # Pipeline works -> threshold comparison
    in_vid_lbl, off_lbl = arbiter._temporal_labels
    arbiter._get_pipeline = MagicMock(
        return_value=lambda *a, **kw: {"labels": [in_vid_lbl, off_lbl], "scores": [0.85, 0.15]}
    )
    ok_res, off_sc = arbiter.verify_in_video_temporal_query("phút thứ 6 giảng gì")
    assert ok_res is True and off_sc == pytest.approx(0.15)


# ==============================================================================
# PC-03: Monotonic Contextual Retrieval Fallback in retrieval_node
# ==============================================================================


@pytest.mark.asyncio
async def test_pc03_retrieval_node_monotonic_contextual_fallback():
    """
    REQ-04: coverage_gap -> accepts Tier-3 grounded(is_low_confidence=True, is_approximate=True);
    grounded(is_low_confidence=True) -> rejects another low_conf fallback, only accepts high_conf.
    """
    low_fb = RetrievalResult(
        chunks=[{"id": "fb-low", "lesson_seq": 3, "content_type": "video_transcript"}],
        status="grounded",
        is_low_confidence=True,
        is_approximate=True,
        scoring_source="cross_encoder",
    )
    high_fb = RetrievalResult(
        chunks=[{"id": "fb-high", "lesson_seq": 3, "content_type": "video_transcript"}],
        status="grounded",
        is_low_confidence=False,
        is_approximate=False,
        scoring_source="cross_encoder",
    )
    base_state = {
        "prompt": "cơ chế đó hoạt động sao",
        "search_query": "biến con trỏ -> cơ chế đó hoạt động sao",
        "last_course_query": "biến con trỏ",
        "course_id": "cpp-core",
        "lesson_seq": 3,
        "messages": [{"role": "user", "content": "biến con trỏ"}],
        "is_curriculum_navigation": False,
        "current_video_sec": None,
    }

    fake_router = MagicMock()
    fake_router.is_context_dependent.return_value = False
    fake_router.has_domain_entity.return_value = True

    # 1. coverage_gap -> accepts low_conf Tier-3 fallback and preserves is_approximate=True
    cov_gap = RetrievalResult(chunks=[], status="coverage_gap")
    fake_ret = MagicMock()
    fake_ret.hybrid_search = AsyncMock(side_effect=[cov_gap, low_fb])
    with patch("app.services.chat_graph.get_retrieval_service", return_value=fake_ret), patch(
        "app.services.chat_graph.get_intent_router", return_value=fake_router
    ):
        out1 = await retrieval_node(base_state)
    assert out1["retrieval_status"] == "grounded"
    assert out1["is_low_confidence"] is True
    assert out1["is_approximate"] is True
    assert out1["retrieved_chunks"][0]["id"] == "fb-low"

    # 2. low_conf -> rejects low_conf fallback
    orig_low = RetrievalResult(
        chunks=[{"id": "orig-low", "lesson_seq": 3, "content_type": "video_transcript"}],
        status="grounded",
        is_low_confidence=True,
        is_approximate=True,
    )
    fake_ret2 = MagicMock()
    fake_ret2.hybrid_search = AsyncMock(side_effect=[orig_low, low_fb])
    with patch("app.services.chat_graph.get_retrieval_service", return_value=fake_ret2), patch(
        "app.services.chat_graph.get_intent_router", return_value=fake_router
    ):
        out2 = await retrieval_node(base_state)
    assert out2["retrieved_chunks"][0]["id"] == "orig-low"

    # 3. low_conf -> accepts high_conf fallback
    fake_ret3 = MagicMock()
    fake_ret3.hybrid_search = AsyncMock(side_effect=[orig_low, high_fb])
    with patch("app.services.chat_graph.get_retrieval_service", return_value=fake_ret3), patch(
        "app.services.chat_graph.get_intent_router", return_value=fake_router
    ):
        out3 = await retrieval_node(base_state)
    assert out3["retrieved_chunks"][0]["id"] == "fb-high"
    assert out3["is_low_confidence"] is False


# ==============================================================================
# PC-04: Calibrated RRF Fallback [0.15, 0.29] on Single Candidate & CE Crash
# ==============================================================================


@pytest.mark.asyncio
async def test_pc04_rrf_fallback_single_candidate_degraded_cap_no_phantom_grounded():
    """
    REQ-05: When Cross-Encoder crashes on a single candidate:
    - strong RRF (0.75) -> prob in [0.22, 0.29], grounded, is_low_confidence=True,
      is_approximate=True, scoring_source='rrf_fallback_degraded'
    - max RRF (1.00) -> prob <= 0.29 (never >= 0.30 or 0.505)
    - weak RRF (0.14) -> prob < 0.22 (not grounded)
    """
    c_svc = get_curriculum_service()
    l3 = c_svc.get_lesson_by_seq(3, course_id="cpp-core")
    assert l3 is not None

    async def _run_with_rrf(rrf_score: float) -> RetrievalResult:
        hit = _make_hit("single-hit", rrf_score, 3, "cpp-core", raw_text="Giải thích toán tử chia nguyên trong C++.")

        async def _qp(**kwargs):
            f = (kwargs.get("prefetch") or [None])[0].filter
            return SimpleNamespace(points=[] if _is_future_qdrant_filter(f) else [hit])

        emb = _make_mock_embedding(lambda **kwargs: (_ for _ in ()).throw(RuntimeError("CE crashed")))
        svc = RetrievalService(client=MagicMock(query_points=AsyncMock(side_effect=_qp)), embedding_service=emb)
        with patch.object(c_svc, "find_lesson_for_query", return_value=(l3, l3["title"])):
            return await svc.search(
                query_text="toán tử chia lấy dư hoạt động thế nào",
                course_id="cpp-core",
                current_lesson_seq=3,
            )

    res_strong = await _run_with_rrf(0.75)
    assert res_strong.status == "grounded"
    assert res_strong.is_low_confidence is True
    assert res_strong.is_approximate is True
    assert res_strong.scoring_source == "rrf_fallback_degraded"
    assert 0.22 <= res_strong.chunks[0]["confidence_score"] <= 0.29

    res_max = await _run_with_rrf(1.00)
    assert res_max.status == "grounded"
    assert res_max.chunks[0]["confidence_score"] <= 0.29
    assert res_max.chunks[0]["confidence_score"] < 0.30

    res_weak = await _run_with_rrf(0.14)
    assert res_weak.status == "coverage_gap"
    assert res_weak.scoring_source == "rrf_fallback_degraded"


# ==============================================================================
# PC-05: Tier-3 Video-Only Gate, Lightweight Approximate Flags, No Double Footer
# ==============================================================================


@pytest.mark.asyncio
async def test_pc05_tier3_video_only_lightweight_chunk_approximate_and_no_double_footer():
    """
    REQ-06, REQ-07, REQ-08:
    (a) code_ast with score 0.18 is rejected by grade_document_relevance and Tier 3.
    (b) _build_lightweight_future_chunk marks chapter & default 00:00 as is_approximate=True.
    (c) ChatService deterministic fallback appends (<timestamp ...>) on the same line
        without duplicating '📍' when LLM already wrote '📍 **Mốc video bài giảng:** phút 02:25'.
    """
    # (a) grade_document_relevance enforces CODE_SCORE_THRESHOLD (0.35) for code_ast
    low_code = {
        "id": "code-low",
        "content_type": "code_ast",
        "confidence_score": 0.18,
        "raw_text": "int helper() { return 0; }",
        "context_code": "int helper() { return 0; }",
    }
    assert grade_document_relevance("hàm helper", low_code, min_confidence=0.15) == "INCORRECT"

    # Tier 3 end-to-end check: only code_ast at 0.27 (below 0.35), no valid video -> coverage_gap
    c_svc = get_curriculum_service()
    l3 = c_svc.get_lesson_by_seq(3, course_id="cpp-core")
    code_hit = _make_hit(
        "code-27",
        0.90,
        3,
        "cpp-core",
        content_type="code_ast",
        code_scope="helper_fn",
        raw_text="int helper_fn() { return 42; }",
    )

    async def _qp_code(**kwargs):
        f = (kwargs.get("prefetch") or [None])[0].filter
        return SimpleNamespace(points=[] if _is_future_qdrant_filter(f) else [code_hit])

    # logit ~ -1.35 gives sigmoid ~ 0.20 < 0.35, raw_prob >= 0.19 -> Tier 3 must reject code_ast
    emb_code = _make_mock_embedding(lambda **kwargs: [-1.35 for _ in kwargs["documents"]])
    svc_code = RetrievalService(client=MagicMock(query_points=AsyncMock(side_effect=_qp_code)), embedding_service=emb_code)
    with patch.object(c_svc, "find_lesson_for_query", return_value=(l3, l3["title"])):
        res_code_only = await svc_code.search(
            query_text="ví dụ cú pháp khai báo biến kiểu số nguyên",
            course_id="cpp-core",
            current_lesson_seq=3,
            is_continuation_turn=True,
        )
    assert res_code_only.status == "coverage_gap"

    # (b) _build_lightweight_future_chunk sets is_approximate=True on chapter & 00:00 default
    with patch.object(c_svc, "get_lesson_timestamps", return_value=[{"sec": 125, "label": "02:05"}]):
        ch_chapter = RetrievalService._build_lightweight_future_chunk(
            future_points=[], target_seq=14, c_svc=c_svc, matched_lesson=c_svc.get_lesson_by_seq(14)
        )
    assert ch_chapter["is_approximate"] is True
    assert ch_chapter["scoring_source"] == "lightweight_nav_chapter"

    with patch.object(c_svc, "get_lesson_timestamps", return_value=[]):
        ch_zero = RetrievalService._build_lightweight_future_chunk(
            future_points=[], target_seq=14, c_svc=c_svc, matched_lesson=c_svc.get_lesson_by_seq(14)
        )
    assert ch_zero["is_approximate"] is True
    assert ch_zero["approx_video_sec"] is None
    assert ch_zero["scoring_source"] == "lightweight_nav_default_zero"

    # (c) ChatService avoids double 📍 line when LLM writes plain-text footer without <timestamp> tag
    async def _run_stream_with_llm_text(llm_text: str):
        async def _fake_stream():
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=llm_text))])

        fake_client = MagicMock()
        fake_client.chat.completions.create = AsyncMock(return_value=_fake_stream())
        fake_graph = MagicMock()
        fake_graph.ainvoke = AsyncMock(
            return_value={
                "intent": "course_query",
                "is_course_query": True,
                "direct_response": None,
                "retrieval_status": "grounded",
                "is_approximate": False,
                "is_low_confidence": False,
                "target_lesson_seq": None,
                "action": None,
                "is_curriculum_navigation": False,
                "curriculum_matched_seq": 3,
                "scoring_source": "cross_encoder",
                "skip_nav_rerank": False,
                "retrieved_chunks": [{"id": "c1"}],
                "suggested_timestamps": [{"sec": 145, "label": "02:25", "title": "Bài 3", "lesson_seq": 3}],
                "sources": [],
                "assembled_messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": "u"}],
            }
        )

        chat_svc = ChatService()
        chat_svc.client = fake_client
        req = ChatRequest(prompt="kiểm tra điều kiện thế nào?", course_id="cpp-core", lesson_seq=3, session_id="spec004_footer")
        deltas = []
        meta_payload = None
        with patch("app.services.chat.get_chat_graph", return_value=fake_graph), patch(
            "app.services.chat.commit_assistant_turn"
        ):
            async for ev in chat_svc.stream_chat(req):
                if ev.get("event") == "metadata":
                    meta_payload = json.loads(ev["data"])
                elif ev.get("event") == "delta":
                    deltas.append(json.loads(ev["data"])["content"])
        return "".join(deltas), meta_payload

    rendered1, meta_payload = await _run_stream_with_llm_text(
        "Hãy kiểm tra lại điều kiện biên.\n\n📍 **Mốc video bài giảng:** phút 02:25"
    )
    assert rendered1.count("📍") == 1
    assert rendered1.count("Mốc video bài giảng:") == 1
    assert '<timestamp sec="145" lesson="3">02:25</timestamp>' in rendered1
    assert meta_payload is not None and meta_payload["scoring_source"] == "cross_encoder"

    # Also verify direct elif has_trailing_ts_label branch when pipeline passes trailing label through
    fake_pipe = MagicMock()
    fake_pipe.process.side_effect = lambda tok: [tok]
    fake_pipe.flush_before_footer.return_value = []
    fake_pipe.flush_held_footer.return_value = []
    fake_pipe.is_echo_only_prose.return_value = False
    fake_pipe.inserted_fallback_question = False
    with patch("app.services.chat.StreamingOutputPipeline", return_value=fake_pipe):
        rendered2, _ = await _run_stream_with_llm_text(
            "Bạn thấy điều kiện biên ra sao?\n\n📍 **Mốc video bài giảng:** phút 02:25"
        )
    assert rendered2.count("📍") == 1
    assert rendered2.count("Mốc video bài giảng:") == 1
    assert '(<timestamp sec="145" lesson="3">02:25</timestamp>)' in rendered2

    # Backward-compatible default checks on StreamMetadataEvent
    compat_meta = StreamMetadataEvent()
    assert compat_meta.is_curriculum_navigation is False
    assert compat_meta.curriculum_matched_seq is None
    assert compat_meta.scoring_source is None
    assert compat_meta.skip_nav_rerank is False


# ==============================================================================
# PC-06: TelemetryCritic Flags Unresolved Curriculum Nav & Degraded RRF
# ==============================================================================


def test_pc06_telemetry_critic_flags_unresolved_nav_and_degraded_rrf():
    """
    REQ-08: TelemetryCriticService penalizes -15 for Unresolved Curriculum Navigation
    (RRF shortcut locked to current lesson without explicit/curr_ref/overview) and
    -5 for rrf_fallback_degraded, while NOT penalizing CE-verified grounded nav.
    """
    critic = get_telemetry_critic_service()

    unresolved_entry = {
        "turn": 3,
        "course_id": "cpp-oop",
        "lesson_seq": 53,
        "prompt": "muốn tạo biến dùng chung cho cả lớp thì học ở bài nào?",
        "response_text": (
            "Trong bài học này có giới thiệu lớp đối tượng. "
            "Bạn muốn biết phần nào tiếp theo? "
            '📍 **Mốc video bài giảng:** <timestamp sec="549" lesson="53">09:09</timestamp>'
        ),
        "latency": {"ttft_ms": 220, "total_ms": 250, "tokens_per_sec": 45.0},
        "router": {"intent": "course_query", "used_fast_path": False, "is_curriculum_navigation": True},
        "crag": {
            "retrieval_status": "grounded",
            "target_lesson_seq": None,
            "skip_nav_rerank": True,
            "scoring_source": "nav_verified_rrf",
        },
        "timestamps": [{"sec": 549, "label": "09:09", "lesson_seq": 53}],
        "sources": [{"lesson_seq": 53, "start_sec": 549}],
    }
    audit_unresolved = critic.analyze_turn(unresolved_entry)
    assert any("Unresolved Curriculum Navigation" in w for w in audit_unresolved["warnings"])
    assert audit_unresolved["turn_score"] <= 85

    degraded_entry = {
        **unresolved_entry,
        "prompt": "tính đóng gói private dùng để làm gì?",
        "router": {"intent": "course_query", "used_fast_path": False, "is_curriculum_navigation": False},
        "crag": {
            "retrieval_status": "grounded",
            "target_lesson_seq": None,
            "skip_nav_rerank": False,
            "scoring_source": "rrf_fallback_degraded",
        },
    }
    audit_degraded = critic.analyze_turn(degraded_entry)
    assert any("Degraded RRF Fallback" in w for w in audit_degraded["warnings"])
    assert audit_degraded["turn_score"] == 95

    ce_verified_entry = {
        **unresolved_entry,
        "crag": {
            "retrieval_status": "grounded",
            "target_lesson_seq": None,
            "skip_nav_rerank": False,
            "scoring_source": "cross_encoder",
        },
    }
    audit_clean = critic.analyze_turn(ce_verified_entry)
    assert not any("Unresolved Curriculum Navigation" in w for w in audit_clean["warnings"])
    assert not any("Degraded RRF Fallback" in w for w in audit_clean["warnings"])
    assert audit_clean["turn_score"] == 100


# ==============================================================================
# V2 DELTA TESTS (C8-v2, PC-07a/C11a, PC-07b/C11b, PC-07c/C12)
# ==============================================================================


@pytest.mark.asyncio
async def test_pc05a_tier3_preserves_phase2_bound_code_ast_while_blocking_low_code():
    """
    REQ-06v2 / C8-v2:
    When Tier 3 has Ambiguous video_transcript (~0.19) + current-lesson non-boilerplate
    Phase-2 bound code_ast (~0.33, approx_video_sec=5750) + noisy code_ast (~0.16)
    + function_main (~0.34), Tier 3 keeps video_transcript-only Decision Gate,
    retains the 0.33 bound code_ast with approx_video_sec=5750, drops noisy & main,
    and crag_grader_node exports 5750s into suggested_timestamps.
    """
    c_svc = get_curriculum_service()
    l7 = c_svc.get_lesson_by_seq(7, course_id="cpp-core")
    assert l7 is not None

    query_text = "hàm tham chiếu truyền giá trị vào biến thì hoạt động thế nào"
    hits = [
        _make_hit(
            "code-main",
            0.95,
            7,
            "cpp-core",
            content_type="code_ast",
            code_scope="function_main",
            raw_text="int main() { return 0; }",
            approx_video_sec=50,
        ),
        _make_hit(
            "code-bound",
            0.85,
            7,
            "cpp-core",
            content_type="code_ast",
            code_scope="function_thamChieu",
            raw_text="void thamChieu(int &x) { x += 1; }",
            approx_video_sec=5750,
        ),
        _make_hit(
            "vid-amb",
            0.50,
            7,
            "cpp-core",
            content_type="video_transcript",
            raw_text="Trong bài giảng này thầy giải thích hàm tham chiếu truyền giá trị vào biến.",
            start_sec=600,
            end_sec=650,
        ),
        _make_hit(
            "code-noise",
            0.40,
            7,
            "cpp-core",
            content_type="code_ast",
            code_scope="helper_noise",
            raw_text="void helperNoise() {}",
            approx_video_sec=100,
        ),
    ]

    async def _qp(**kwargs):
        f = (kwargs.get("prefetch") or [None])[0].filter
        return SimpleNamespace(points=[] if _is_future_qdrant_filter(f) else hits)

    async def _rr(*, query: str, documents: list[str]):
        scores = []
        for d in documents:
            if "int main" in d:
                scores.append(-1.40)
            elif "void thamChieu" in d:
                scores.append(-1.35)
            elif "thầy giải thích" in d:
                scores.append(-1.95)
            else:
                scores.append(-2.30)
        return scores

    svc = RetrievalService(
        client=MagicMock(query_points=AsyncMock(side_effect=_qp)),
        embedding_service=_make_mock_embedding(_rr),
    )
    with patch.object(c_svc, "find_lesson_for_query", return_value=(l7, l7["title"])):
        res = await svc.search(
            query_text=query_text,
            course_id="cpp-core",
            current_lesson_seq=7,
            is_continuation_turn=True,
        )

    assert res.status == "grounded"
    assert res.is_low_confidence is True
    assert res.is_approximate is True
    returned_ids = {c["id"] for c in res.chunks}
    assert "code-bound" in returned_ids
    assert "vid-amb" in returned_ids
    assert "code-noise" not in returned_ids
    assert "code-main" not in returned_ids
    assert res.chunks[0]["id"] == "code-bound"
    assert res.chunks[0]["approx_video_sec"] == 5750

    crag_out = await crag_grader_node(
        {
            "prompt": query_text,
            "search_query": query_text,
            "course_id": "cpp-core",
            "lesson_seq": 7,
            "retrieval_status": res.status,
            "target_lesson_seq": res.target_lesson_seq,
            "future_best_chunk": res.future_best_chunk,
            "retrieved_chunks": res.chunks,
            "is_curriculum_navigation": False,
            "is_low_confidence": res.is_low_confidence,
            "is_approximate": res.is_approximate,
        }
    )
    assert any(ts["sec"] == 5750 for ts in crag_out["suggested_timestamps"])


@pytest.mark.asyncio
async def test_pc07a_deterministic_rrf_tie_break_and_pre_nms_future_limit():
    """
    REQ-09 / C11a:
    (a) _sort_rrf_points_deterministically returns identical ordering regardless of
        input permutation on tied RRF scores (prefer_earlier_seq=True -> min seq,
        prefer_earlier_seq=False -> max seq, same seq -> str(id)).
    (b) _fetch_future_points queries Qdrant with limit >= 20 before NMS, and
        _score_future_points caps documents passed to rerank_documents_async at <= FUTURE_PROBE_LIMIT.
    """
    from app.config import settings
    from app.services.retrieval import _sort_rrf_points_deterministically

    tied_hits = [
        _make_hit("id-b", 0.5000001, 37, "cpp-core", start_sec=200, end_sec=260),
        _make_hit("id-a", 0.5000002, 28, "cpp-core", start_sec=100, end_sec=160),
        _make_hit("id-c", 0.5000003, 28, "cpp-core", start_sec=300, end_sec=360),
    ]
    fwd_fut = [h.id for h in _sort_rrf_points_deterministically(tied_hits, prefer_earlier_seq=True)]
    rev_fut = [h.id for h in _sort_rrf_points_deterministically(list(reversed(tied_hits)), prefer_earlier_seq=True)]
    assert fwd_fut == rev_fut == ["id-a", "id-c", "id-b"]

    fwd_cur = [h.id for h in _sort_rrf_points_deterministically(tied_hits, prefer_earlier_seq=False)]
    rev_cur = [h.id for h in _sort_rrf_points_deterministically(list(reversed(tied_hits)), prefer_earlier_seq=False)]
    assert fwd_cur == rev_cur == ["id-b", "id-a", "id-c"]

    many_future_hits = [
        _make_hit(
            f"fut-{i:02d}",
            0.50,
            28 if i < 2 else 37,
            "cpp-core",
            raw_text=f"Đoạn giảng tương lai số {i}",
            start_sec=i * 120,
            end_sec=i * 120 + 50,
        )
        for i in range(15)
    ]

    captured_limits = []

    async def _qp(**kwargs):
        captured_limits.append(kwargs.get("limit"))
        return SimpleNamespace(points=list(reversed(many_future_hits)))

    reranked_counts = []

    async def _rr(*, query: str, documents: list[str]):
        reranked_counts.append(len(documents))
        return [0.2 for _ in documents]

    svc = RetrievalService(
        client=MagicMock(query_points=AsyncMock(side_effect=_qp)),
        embedding_service=_make_mock_embedding(_rr),
    )
    fetched = await svc._fetch_future_points(
        query_dense=[0.1] * 8,
        sparse_indices=[1],
        sparse_values=[0.5],
        course_id="cpp-core",
        current_lesson_seq=7,
    )
    assert captured_limits and captured_limits[0] >= 20
    assert fetched[0].payload["lesson_seq"] == 28

    await svc._score_future_points(
        future_points=fetched,
        query_text="kiến thức bài tương lai",
        course_id="cpp-core",
    )
    assert reranked_counts and reranked_counts[0] <= settings.FUTURE_PROBE_LIMIT


@pytest.mark.asyncio
async def test_pc07b_monotonic_future_target_and_continuation_consensus():
    """
    REQ-10 / C11b:
    (a) Student in cpp-oop (L53) with CurriculumService matching past cpp-core (L18)
        must have is_future_curriculum_target=False (Tier-1 Early Exit preserved).
    (b) Continuation turn at L7 (S_curr ~ 0.29 >= 0.22) where CurriculumService guesses L43
        but Qdrant returns non-topical L37 -> has_future_topic_signal=False ->
        active_continuation_shield=True -> grounded L7.
    (c) Counterexample: continuation turn with consensus (matched=8, target=8) -> out_of_lesson L8.
    """
    c_svc = get_curriculum_service()
    l53 = c_svc.get_lesson_by_seq(53, course_id="cpp-oop")
    l18 = c_svc.get_lesson_by_seq(18, course_id="cpp-core")
    l43 = c_svc.get_lesson_by_seq(43, course_id="cpp-core")
    l8 = c_svc.get_lesson_by_seq(8, course_id="cpp-core")
    assert all(x is not None for x in (l53, l18, l43, l8))

    # (a) cpp-oop L53 + matched cpp-core L18 -> not future target -> Tier-1 Early Exit
    hits_53 = [
        _make_hit(
            "c53-v",
            0.85,
            53,
            "cpp-oop",
            raw_text="Khái niệm lớp và đối tượng trong bài nhập môn lập trình hướng đối tượng.",
            start_sec=200,
            end_sec=260,
        )
    ]
    fut_54 = [
        _make_hit(
            "f54-v",
            0.60,
            54,
            "cpp-oop",
            raw_text="Từ khóa static trong lớp.",
            start_sec=100,
            end_sec=160,
        )
    ]

    async def _qp_a(**kwargs):
        f = (kwargs.get("prefetch") or [None])[0].filter
        return SimpleNamespace(points=fut_54 if _is_future_qdrant_filter(f) else hits_53)

    ce_calls_a = []

    async def _rr_a(*, query: str, documents: list[str]):
        ce_calls_a.append(len(documents))
        return [0.2 for _ in documents]

    svc_a = RetrievalService(
        client=MagicMock(query_points=AsyncMock(side_effect=_qp_a)),
        embedding_service=_make_mock_embedding(_rr_a),
    )
    with patch.object(c_svc, "find_lesson_for_query", return_value=(l18, l18["title"])):
        res_a = await svc_a.search(
            query_text="khái niệm đóng gói dữ liệu trong lớp là gì",
            course_id="cpp-oop",
            current_lesson_seq=53,
            is_curriculum_navigation=False,
        )
    assert res_a.status == "grounded"
    assert len(ce_calls_a) == 1  # Tier-1 Early Exit succeeded without future probe CE

    # (b) Continuation turn L7, S_curr ~ 0.29 >= 0.22, matched=43 != target=37 (non-topical) -> grounded
    hits_7 = [
        _make_hit(
            "c7-v",
            0.80,
            7,
            "cpp-core",
            raw_text="Lưu ý về phạm vi hoạt động của tham số trong hàm C++.",
            start_sec=400,
            end_sec=460,
        )
    ]
    fut_37 = [
        _make_hit(
            "f37-v",
            0.80,
            37,
            "cpp-core",
            raw_text="Đoạn giảng ví dụ thao tác bộ nhớ chuyên sâu.",
            start_sec=120,
            end_sec=180,
        )
    ]

    async def _qp_b(**kwargs):
        f = (kwargs.get("prefetch") or [None])[0].filter
        return SimpleNamespace(points=fut_37 if _is_future_qdrant_filter(f) else hits_7)

    async def _rr_b(*, query: str, documents: list[str]):
        return [-1.10 if "tham số" in d else 0.50 for d in documents]

    svc_b = RetrievalService(
        client=MagicMock(query_points=AsyncMock(side_effect=_qp_b)),
        embedding_service=_make_mock_embedding(_rr_b),
    )
    with patch.object(c_svc, "find_lesson_for_query", return_value=(l43, l43["title"])):
        res_b = await svc_b.search(
            query_text="còn trường hợp kia thì xử lý ra sao",
            course_id="cpp-core",
            current_lesson_seq=7,
            is_continuation_turn=True,
        )
    assert res_b.status == "grounded"
    assert res_b.target_lesson_seq is None

    # (c) Consensus on continuation turn: matched=8 == target=8 -> out_of_lesson -> L8
    fut_8 = [
        _make_hit(
            "f8-v",
            0.85,
            8,
            "cpp-core",
            raw_text="Giới thiệu khái niệm hàm đệ quy cơ bản.",
            start_sec=90,
            end_sec=150,
        )
    ]

    async def _qp_c(**kwargs):
        f = (kwargs.get("prefetch") or [None])[0].filter
        return SimpleNamespace(points=fut_8 if _is_future_qdrant_filter(f) else hits_7)

    async def _rr_c(*, query: str, documents: list[str]):
        return [-1.10 if "tham số" in d else 0.80 for d in documents]

    svc_c = RetrievalService(
        client=MagicMock(query_points=AsyncMock(side_effect=_qp_c)),
        embedding_service=_make_mock_embedding(_rr_c),
    )
    with patch.object(c_svc, "find_lesson_for_query", return_value=(l8, l8["title"])):
        res_c = await svc_c.search(
            query_text="còn trường hợp kia thì xử lý ra sao",
            course_id="cpp-core",
            current_lesson_seq=7,
            is_continuation_turn=True,
        )
    assert res_c.status == "out_of_lesson"
    assert res_c.target_lesson_seq == 8


@pytest.mark.asyncio
async def test_pc07c_retrieval_node_anaphoric_unverified_ool_rescue_and_consensus_guard():
    """
    REQ-11 / C12:
    (a) raw_prompt returns out_of_lesson (target=46, matched=27) + search_query != raw_prompt
        + fallback_res returns high-conf grounded (>= 0.30, not is_low_confidence) -> rescues to grounded.
    (b) Same unverified OOL, but fallback_res returns grounded with score 0.26 < 0.30 -> stays out_of_lesson.
    (c) Consensus OOL (target=8, matched=8) -> does NOT call fallback_res, stays out_of_lesson -> 8.
    """
    base_state = {
        "prompt": "thoát khỏi nó thì sao",
        "search_query": "vòng lặp lồng nhau -> thoát khỏi nó thì sao",
        "last_course_query": "vòng lặp lồng nhau",
        "course_id": "cpp-core",
        "lesson_seq": 6,
        "messages": [{"role": "user", "content": "vòng lặp lồng nhau"}],
        "is_curriculum_navigation": False,
        "current_video_sec": None,
    }
    fake_router = MagicMock()
    fake_router.is_context_dependent.return_value = False
    fake_router.has_domain_entity.return_value = False

    unverified_ool = RetrievalResult(
        chunks=[],
        status="out_of_lesson",
        target_lesson_seq=46,
        curriculum_matched_seq=27,
        curriculum_matched_course="cpp-core",
    )
    high_grounded = RetrievalResult(
        chunks=[{"id": "fb-high", "lesson_seq": 6, "content_type": "video_transcript", "confidence_score": 0.52}],
        status="grounded",
        is_low_confidence=False,
        is_approximate=False,
        scoring_source="cross_encoder",
    )
    weak_grounded = RetrievalResult(
        chunks=[{"id": "fb-weak", "lesson_seq": 6, "content_type": "video_transcript", "confidence_score": 0.26}],
        status="grounded",
        is_low_confidence=False,
        is_approximate=False,
        scoring_source="cross_encoder",
    )
    verified_ool = RetrievalResult(
        chunks=[],
        status="out_of_lesson",
        target_lesson_seq=8,
        curriculum_matched_seq=8,
        curriculum_matched_course="cpp-core",
    )

    # (a) Rescue accepted
    ret_a = MagicMock(hybrid_search=AsyncMock(side_effect=[unverified_ool, high_grounded]))
    with patch("app.services.chat_graph.get_retrieval_service", return_value=ret_a), patch(
        "app.services.chat_graph.get_intent_router", return_value=fake_router
    ):
        out_a = await retrieval_node(base_state)
    assert out_a["retrieval_status"] == "grounded"
    assert out_a["retrieved_chunks"][0]["id"] == "fb-high"
    assert ret_a.hybrid_search.await_count == 2

    # (b) Weak fallback (< 0.30) rejected
    ret_b = MagicMock(hybrid_search=AsyncMock(side_effect=[unverified_ool, weak_grounded]))
    with patch("app.services.chat_graph.get_retrieval_service", return_value=ret_b), patch(
        "app.services.chat_graph.get_intent_router", return_value=fake_router
    ):
        out_b = await retrieval_node(base_state)
    assert out_b["retrieval_status"] == "out_of_lesson"
    assert out_b["target_lesson_seq"] == 46
    assert ret_b.hybrid_search.await_count == 2

    # (c) Consensus OOL skips fallback entirely
    ret_c = MagicMock(hybrid_search=AsyncMock(side_effect=[verified_ool]))
    with patch("app.services.chat_graph.get_retrieval_service", return_value=ret_c), patch(
        "app.services.chat_graph.get_intent_router", return_value=fake_router
    ):
        out_c = await retrieval_node(base_state)
    assert out_c["retrieval_status"] == "out_of_lesson"
    assert out_c["target_lesson_seq"] == 8
    assert ret_c.hybrid_search.await_count == 1
