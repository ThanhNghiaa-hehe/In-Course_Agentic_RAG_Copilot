"""
Regression tests for P0 fixes (Hydrogen Swarm Verification):
1. Curriculum navigation turn followed by "int và double khác nhau cái gì?" at lesson_seq=3
   does not pollute last_course_query, flip is_curriculum_navigation=True, or route to lesson 64.
2. crag_grader_node preserves start_sec=0 instead of turning falsy 0 into None.
3. StreamingTimestampSanitizer and sanitize_timestamp_tags suppress unverified timestamp bodies
   without leaking plain-text timestamps, and ChatService.stream_chat avoids duplicate footers
   while preserving lesson="..." on deterministic fallback tags.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import json
import pytest

from app.agent.router import get_intent_router
from app.schemas.chat import ChatRequest
from app.services.chat import (
    ChatService,
    StreamingTimestampSanitizer,
    sanitize_timestamp_tags,
)
from app.services.chat_graph import (
    commit_assistant_turn,
    crag_grader_node,
    get_chat_graph,
    reset_session_state,
    router_node,
)


def _base_state(session_id: str, prompt: str, course_id: str = "cpp-core", lesson_seq: int = 3):
    return {
        "session_id": session_id,
        "prompt": prompt,
        "course_id": course_id,
        "lesson_seq": lesson_seq,
        "intent": "unknown",
        "direct_response": None,
        "is_course_query": False,
        "retrieval_status": "coverage_gap",
        "retrieved_chunks": [],
        "is_approximate": False,
        "is_low_confidence": False,
        "target_lesson_seq": None,
        "suggested_timestamps": [],
        "sources": [],
        "system_prompt": "",
        "user_message_content": "",
        "assembled_messages": [],
    }


@pytest.mark.asyncio
async def test_p0_curriculum_nav_then_int_double_at_lesson_3():
    """
    Turn 1: "tôi muốn học về kiểu dữ liệu thì sẽ học bài mấy" (curriculum nav)
    Turn 2: "int và double khác nhau cái gì?" at lesson_seq=3
    Must NOT flip is_curriculum_navigation=True or route to lesson 64.
    """
    router = get_intent_router()
    assert router.is_context_dependent("int và double khác nhau cái gì?") is False

    sid = "test_p0_nav_then_int_double"
    reset_session_state(sid)

    # Check router_node directly with Turn 1 -> Turn 2 state progression
    state_t1 = {
        **_base_state(sid, "tôi muốn học về kiểu dữ liệu thì sẽ học bài mấy", lesson_seq=3),
        "messages": [],
        "last_course_query": None,
    }
    res_t1 = await router_node(state_t1)
    assert res_t1["is_curriculum_navigation"] is True
    assert res_t1["last_course_query"] is None

    # Full graph execution across Turn 1 and Turn 2
    graph = get_chat_graph()
    config = {"configurable": {"thread_id": sid}}

    out_t1 = await graph.ainvoke(
        _base_state(sid, "tôi muốn học về kiểu dữ liệu thì sẽ học bài mấy", lesson_seq=3),
        config=config,
    )
    assert out_t1.get("is_curriculum_navigation") is True
    assert out_t1.get("last_course_query") is None

    commit_assistant_turn(
        session_id=sid,
        user_prompt="tôi muốn học về kiểu dữ liệu thì sẽ học bài mấy",
        assistant_response="Bạn có thể tham khảo bài học về kiểu dữ liệu trong khóa học.",
        current_lesson_seq=3,
    )

    out_t2 = await graph.ainvoke(
        _base_state(sid, "int và double khác nhau cái gì?", lesson_seq=3),
        config=config,
    )
    assert out_t2.get("intent") == "course_query"
    assert out_t2.get("is_curriculum_navigation") is False
    assert out_t2.get("target_lesson_seq") != 64

    reset_session_state(sid)


@pytest.mark.asyncio
async def test_p0_crag_grader_preserves_start_sec_zero():
    """
    start_sec=0 (00:00) must be preserved as 0, never coerced to None.
    """
    state = {
        "prompt": "Kiểu dữ liệu int là gì?",
        "search_query": "Kiểu dữ liệu int là gì?",
        "retrieval_status": "grounded",
        "is_low_confidence": False,
        "target_lesson_seq": None,
        "retrieved_chunks": [
            {
                "id": "vid-0",
                "content_type": "video_transcript",
                "confidence_pct": 92.0,
                "confidence_score": 0.92,
                "is_approximate": False,
                "lesson_id": "lesson-3",
                "lesson_seq": 3,
                "start_sec": 0,
                "start_label": "00:00",
                "video_title": "Bài 3: Kiểu dữ liệu",
                "raw_text": "Giới thiệu kiểu int",
            },
            {
                "id": "code-0",
                "content_type": "code_ast",
                "confidence_pct": 88.0,
                "confidence_score": 0.88,
                "is_approximate": False,
                "lesson_id": "lesson-3",
                "lesson_seq": 3,
                "start_sec": None,
                "approx_video_sec": 0,
                "code_scope": "main",
                "context_code": "int x = 0;",
            },
        ],
    }

    result = await crag_grader_node(state)
    assert len(result["sources"]) == 2
    assert result["sources"][0]["start_sec"] == 0
    assert result["sources"][1]["start_sec"] == 0
    assert result["suggested_timestamps"][0]["sec"] == 0
    assert result["suggested_timestamps"][1]["sec"] == 0


def test_p0_streaming_timestamp_sanitizer_suppresses_unverified_bodies():
    """
    StreamingTimestampSanitizer and sanitize_timestamp_tags must NOT emit unverified
    timestamp body text (e.g. "0:56") or truncated unclosed body text.
    """
    sanitizer = StreamingTimestampSanitizer(valid_secs={120})
    tokens = [
        "Xem thêm tại ",
        "<time",
        'stamp sec="56"',
        ">0:56</time",
        "stamp> và ",
        '<timestamp sec="120" lesson="3">',
        "02:00</timestamp>.",
    ]
    emitted = []
    for tok in tokens:
        emitted.extend(sanitizer.process(tok))
    emitted.extend(sanitizer.flush())
    rendered = "".join(emitted)

    assert "0:56" not in rendered
    assert 'sec="56"' not in rendered
    assert '<timestamp sec="120" lesson="3">02:00</timestamp>' in rendered

    # Truncated unclosed tag at end of stream
    trunc_sanitizer = StreamingTimestampSanitizer(valid_secs={120})
    trunc_out = trunc_sanitizer.process('Kiểm tra <timestamp sec="56">0:5')
    trunc_out.extend(trunc_sanitizer.flush())
    trunc_rendered = "".join(trunc_out)
    assert "0:5" not in trunc_rendered
    assert "<timestamp" not in trunc_rendered

    # Non-streaming sanitizer parity check
    clean_full = sanitize_timestamp_tags(
        'Mốc <timestamp sec="56">0:56</timestamp> và <timestamp sec="120">02:00</timestamp>',
        {120},
    )
    assert "0:56" not in clean_full
    assert '<timestamp sec="120">02:00</timestamp>' in clean_full


@pytest.mark.asyncio
async def test_p0_stream_chat_no_duplicate_footer_and_preserves_lesson_attr():
    """
    When LLM outputs a footer header followed by an unverified timestamp tag,
    the sanitizer strips the unverified tag/body and the deterministic fallback
    appends the verified tag (with lesson attr and sec=0) without duplicating the header.
    """
    async def _fake_llm_stream():
        chunks = [
            "Giải thích ngắn gọn.\n\n📍 **Mốc video bài giảng:** ",
            '<timestamp sec="56">0:56</timestamp>',
        ]
        for text in chunks:
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=text))]
            )

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=_fake_llm_stream())

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
            "retrieved_chunks": [{"id": "c0"}],
            "suggested_timestamps": [
                {"sec": 0, "label": "00:00", "title": "Bài 3", "lesson_seq": 3}
            ],
            "sources": [],
            "assembled_messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "user"},
            ],
        }
    )

    service = ChatService()
    service.client = fake_client

    req = ChatRequest(
        prompt="int và double khác nhau cái gì?",
        course_id="cpp-core",
        lesson_seq=3,
        session_id="test_p0_stream_footer",
    )

    deltas = []
    with patch("app.services.chat.get_chat_graph", return_value=fake_graph), patch(
        "app.services.chat.commit_assistant_turn"
    ):
        async for ev in service.stream_chat(req):
            if ev.get("event") == "delta":
                deltas.append(json.loads(ev["data"])["content"])

    full_text = "".join(deltas)
    assert "0:56" not in full_text
    assert 'sec="56"' not in full_text
    assert full_text.count("Mốc video bài giảng:") == 1
    assert '<timestamp sec="0" lesson="3">00:00</timestamp>' in full_text
