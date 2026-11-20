import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# Đảm bảo import trực tiếp từ thư mục gốc dự án
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agent.prompts import SOCRATIC_GROUNDED_PROMPT, get_academic_glossary_prompt_extension
from app.agent.router import get_intent_router
from app.schemas.chat import ChatRequest
from app.services.chat import (
    ChatService,
    StreamingOutputPipeline,
    StreamingSocraticFooterGuard,
    apply_streaming_sanitizers,
    has_trailing_socratic_question,
    is_echo_only_prose,
)
from app.services.chat_graph import (
    commit_assistant_turn,
    context_assembly_node,
    crag_grader_node,
    get_chat_graph,
    reset_session_state,
    retrieval_node,
    router_node,
)
from app.services.curriculum import get_curriculum_service
from app.services.retrieval import RetrievalService
from app.services.telemetry_critic import TelemetryCriticService


def _make_base_state(
    prompt: str,
    *,
    lesson_seq: int = 57,
    course_id: str | None = None,
    session_id: str = "test_e2e_conv_default",
    current_video_sec: int | None = None,
) -> dict:
    resolved_course_id = course_id
    if resolved_course_id is None:
        les = get_curriculum_service().get_lesson_by_seq(lesson_seq)
        resolved_course_id = (les or {}).get("course_id", "cpp-core")
    return {
        "session_id": session_id,
        "prompt": prompt,
        "course_id": resolved_course_id,
        "lesson_seq": lesson_seq,
        "current_video_sec": current_video_sec,
        "turn_count": 1,
        "messages": [],
    }


def _with_checkpoint(session_id: str, state: dict) -> dict:
    snap = get_chat_graph().get_state({"configurable": {"thread_id": session_id}})
    vals = dict(snap.values) if snap and snap.values else {}
    return {**vals, **state, "messages": vals.get("messages", state.get("messages", []))}


def _collect_sse_delta_text(events: list[dict]) -> str:
    parts = []
    for ev in events:
        if ev.get("event") == "delta":
            payload = json.loads(ev["data"])
            parts.append(payload.get("content", ""))
    return "".join(parts)


async def _make_fake_stream(chunks: list[str]):
    for text in chunks:
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=text))]
        )


# ==============================================================================
# PC-01: Video Section Seeking + Adversarial Non-Course Counter-Examples
# ==============================================================================
@pytest.mark.asyncio
async def test_pc01_video_section_seeking_and_adversarials():
    sid = "pc01_section_seeking"
    reset_session_state(sid)

    positive_queries = [
        "khoảng phút bao nhiêu thì nói về lý thuyết",
        "đến phút mấy giảng về code",
        "đoạn nào trong bài nói về ví dụ",
    ]
    for idx, q in enumerate(positive_queries):
        q_sid = f"{sid}_{idx}"
        reset_session_state(q_sid)
        routed = await router_node(_make_base_state(q, lesson_seq=57, session_id=q_sid))
        assert routed["intent"] == "course_query", f"PC-01 failed for '{q}': {routed}"
        assert routed["is_curriculum_navigation"] is False

    # Kiểm chứng trọn vẹn Retrieval + CRAG cho câu debug log PC-01 tại Bài 57
    reset_session_state(sid)
    s0 = _make_base_state(
        "khoảng phút bao nhiêu thì nói về lý thuyết",
        lesson_seq=57,
        session_id=sid,
    )
    s1 = {**s0, **(await router_node(s0))}
    s2 = {**s1, **(await retrieval_node(s1))}
    s3 = {**s2, **(await crag_grader_node(s2))}
    assert s3["retrieval_status"] == "grounded", f"Expected grounded L57, got {s3.get('retrieval_status')}"
    assert s3.get("suggested_timestamps"), "PC-01 must surface L57 chapter timestamps"

    # Đối chứng phản ví dụ: Tuyệt đối KHÔNG cứu nhầm identity hoặc bóng đá ngoài luồng
    r_id = await router_node(_make_base_state("bạn được tạo ra lúc nào", lesson_seq=57, session_id=f"{sid}_id"))
    assert r_id["intent"] == "chit_chat"

    r_oos = await router_node(
        _make_base_state(
            "phút thứ 6 trận bóng đá hôm qua thế nào",
            lesson_seq=57,
            session_id=f"{sid}_oos",
        )
    )
    assert r_oos["intent"] == "out_of_scope"


# ==============================================================================
# PC-02: Follow-up Elaboration + Recency Gate + OOS Turn Isolation
# ==============================================================================
@pytest.mark.asyncio
async def test_pc02_followup_elaboration_recency_gate_and_adversarials():
    sid = "pc02_followup_session"
    reset_session_state(sid)

    # Turn 1: Câu hỏi bài học có ngữ cảnh video cụ thể tại Bài 57
    t1_route = await router_node(
        _make_base_state(
            "đoạn này đang khai báo gì",
            lesson_seq=57,
            session_id=sid,
            current_video_sec=145,
        )
    )
    assert t1_route["intent"] == "course_query"
    commit_assistant_turn(
        sid,
        "đoạn này đang khai báo gì",
        "Đoạn này đang minh họa cách khai báo biến con trỏ trong C++. Bạn thử xem kiểu dữ liệu đứng trước dấu * là gì nhé?",
        current_lesson_seq=57,
        last_course_query="đoạn này đang khai báo gì",
    )
    get_chat_graph().update_state(
        {"configurable": {"thread_id": sid}},
        {"last_turn_intent": "course_query"},
    )

    # Turn 2: Câu nối ngắn 'chi tiết hơn' phải được cứu về course_query + kế thừa ngữ cảnh T1
    t2_base = _with_checkpoint(
        sid,
        _make_base_state(
            "chi tiết hơn",
            lesson_seq=57,
            session_id=sid,
            current_video_sec=145,
        ),
    )
    t2_route = {**t2_base, **(await router_node(t2_base))}
    assert t2_route["intent"] == "course_query"
    assert t2_route.get("search_query")
    assert "khai báo" in t2_route["search_query"].lower()
    t2_ret = await retrieval_node(t2_route)
    assert t2_ret.get("retrieved_chunks"), "Follow-up 'chi tiết hơn' must retrieve L57 chunks"

    # Phản ví dụ 1: Câu có 'cho mình ví dụ về vòng lặp for' là câu hỏi độc lập, không bị hiểu nhầm thành pure follow-up
    t_indep_in = _with_checkpoint(
        sid,
        _make_base_state(
            "cho mình ví dụ về vòng lặp for",
            lesson_seq=57,
            session_id=sid,
        ),
    )
    t_indep = await router_node(t_indep_in)
    assert t_indep["intent"] == "course_query"
    assert "vòng lặp for" in t_indep["search_query"].lower()

    # Phản ví dụ 2: Standalone ngoài luồng 'nấu mì chi tiết hơn' -> out_of_scope
    sid_oos = "pc02_standalone_oos"
    reset_session_state(sid_oos)
    r_noodle = await router_node(_make_base_state("nấu mì chi tiết hơn", lesson_seq=57, session_id=sid_oos))
    assert r_noodle["intent"] == "out_of_scope"

    # Phản ví dụ 3: T1(course) -> T2(out_of_scope) -> T3('chi tiết hơn') -> Recency Gate phải chặn cứu
    sid_gate = "pc02_recency_gate"
    reset_session_state(sid_gate)
    commit_assistant_turn(
        sid_gate,
        "con trỏ là gì",
        "Con trỏ là biến lưu địa chỉ bộ nhớ. Bạn thử đoán kiểu địa chỉ nhé?",
        current_lesson_seq=57,
        last_course_query="con trỏ là gì",
    )
    get_chat_graph().update_state(
        {"configurable": {"thread_id": sid_gate}},
        {"last_turn_intent": "course_query"},
    )
    t_weather = await router_node(
        _with_checkpoint(
            sid_gate,
            _make_base_state("thời tiết Hà Nội hôm nay sao", lesson_seq=57, session_id=sid_gate),
        )
    )
    assert t_weather["intent"] == "out_of_scope"
    commit_assistant_turn(
        sid_gate,
        "thời tiết Hà Nội hôm nay sao",
        "Mình chỉ hỗ trợ kiến thức lập trình trong khóa học thôi ạ.",
        current_lesson_seq=57,
    )
    get_chat_graph().update_state(
        {"configurable": {"thread_id": sid_gate}},
        {"last_turn_intent": "out_of_scope"},
    )
    t_after_oos = await router_node(
        _with_checkpoint(
            sid_gate,
            _make_base_state("chi tiết hơn", lesson_seq=57, session_id=sid_gate),
        )
    )
    assert t_after_oos["intent"] == "out_of_scope"


# ==============================================================================
# PC-03: Unaccented/Typo Navigation + Multi-Turn Disambiguation + Bounds + L1 ASR
# ==============================================================================
@pytest.mark.asyncio
async def test_pc03_unaccented_nav_pending_disambiguation_bounds_and_l1_asr():
    router = get_intent_router()
    curriculum = get_curriculum_service()

    # 12 positive navigation queries (gồm cả mất dấu và sai chính tả 'bai')
    pos_nav = [
        "có bai học nào về con trỏ không",
        "co bai hoc nao ve con tro khong",
        "tim bai ve mang 2 chieu",
        "bai nao day ve struct",
        "hoc ve con tro o bai nao",
        "chuyen den bai con tro",
        "co bai nao noi ve ham khong",
        "muon hoc ve vong lap thi xem bai may",
        "xem bai giang ve de quy",
        "lop va doi tuong nam o bai nao",
        "bai may day ve vector",
        "co bai hoc nao ve sap xep khong",
    ]
    for q in pos_nav:
        is_nav, matched = router.is_curriculum_navigation(q)
        assert is_nav is True, f"Expected True for nav query '{q}', got False ({matched})"

    # Negative non-navigation queries (gồm cả phản ví dụ folding collision)
    neg_nav = [
        "con trỏ là gì",
        "tại sao dùng con trỏ",
        "giải thích đoạn code con trỏ này",
        "xin chào bạn",
        "thời tiết hôm nay thế nào",
        "cách nấu phở bò",
        "bài tập này làm sao",
        "phút thứ 5 nói gì",
        "vòng lặp for chạy bao nhiêu lần",
        "con trỏ null có nguy hiểm không",
        "bạn tên là gì",
        "cảm ơn thầy ạ",
        "bãi biển nào đẹp",
        "bai bien nao dep",
        "bai toan nay kho qua",
    ]
    for q in neg_nav:
        is_nav, matched = router.is_curriculum_navigation(q)
        assert is_nav is False, f"Expected False for non-nav query '{q}', matched={matched}"

    # Bounds check cho lệnh chuyển bài trực tiếp ngoài phạm vi [1..83]
    lo, hi = curriculum.get_lesson_seq_bounds()
    assert lo == 1 and hi >= 83
    for bad_cmd in ("chuyển đến bài 999", "chuyển đến bài 0"):
        sid_bad = f"pc03_bounds_{bad_cmd}"
        reset_session_state(sid_bad)
        r_bad = await router_node(_make_base_state(bad_cmd, lesson_seq=1, session_id=sid_bad))
        assert r_bad["intent"] == "out_of_scope"
        assert r_bad.get("action") is None
        assert str(lo) in (r_bad.get("direct_response") or "")
        assert str(hi) in (r_bad.get("direct_response") or "")

    # Disambiguation đa bài được gợi ý ('chuyển cho tôi đến bài đó' khi offered > 1 vs == 1)
    sid_multi = "pc03_multi_offered"
    reset_session_state(sid_multi)
    commit_assistant_turn(
        sid_multi,
        "có bai học nào về con trỏ không",
        "Trong khóa học có Bài 57 (Con trỏ) và Bài 58 (Thực hành Con trỏ) đề cập nội dung này.",
        current_lesson_seq=1,
    )
    get_chat_graph().update_state(
        {"configurable": {"thread_id": sid_multi}},
        {
            "last_turn_intent": "course_query",
            "last_offered_lessons": [
                {"course_id": "cpp-oop", "seq": 57, "title": "Bài 57: Lý thuyết về con trỏ trong C++", "sec": 0, "label": "00:00"},
                {"course_id": "cpp-oop", "seq": 58, "title": "Bài 58: Con trỏ nâng cao", "sec": 0, "label": "00:00"},
            ],
        },
    )
    r_ambig = await router_node(
        _with_checkpoint(
            sid_multi,
            _make_base_state("chuyển cho tôi đến bài đó", lesson_seq=1, session_id=sid_multi),
        )
    )
    assert r_ambig["intent"] == "confirm_navigation"
    assert r_ambig.get("action") is None, "Multiple offered lessons must clarify instead of guessing"
    assert "57" in (r_ambig.get("direct_response") or "")
    assert "58" in (r_ambig.get("direct_response") or "")

    sid_single = "pc03_single_offered"
    reset_session_state(sid_single)
    commit_assistant_turn(
        sid_single,
        "có bai học nào về con trỏ không",
        "Chủ đề con trỏ được giảng chi tiết tại Bài 57.",
        current_lesson_seq=1,
    )
    get_chat_graph().update_state(
        {"configurable": {"thread_id": sid_single}},
        {
            "last_turn_intent": "course_query",
            "last_offered_lessons": [
                {"course_id": "cpp-oop", "seq": 57, "title": "Bài 57: Lý thuyết về con trỏ trong C++", "sec": 0, "label": "00:00"}
            ],
        },
    )
    r_single = await router_node(
        _with_checkpoint(
            sid_single,
            _make_base_state("chuyển cho tôi đến bài đó", lesson_seq=1, session_id=sid_single),
        )
    )
    assert r_single["intent"] == "confirm_navigation"
    assert r_single.get("action") is not None
    assert r_single["action"]["target_lesson_seq"] == 57

    # E2E Retrieval: "có bai học nào về con trỏ không" từ Bài 1 phải tìm đúng nhóm bài con trỏ (không kẹt Bài 38/50)
    sid_e2e = "pc03_real_nav"
    reset_session_state(sid_e2e)
    s0 = _make_base_state("có bai học nào về con trỏ không", lesson_seq=1, session_id=sid_e2e)
    s1 = {**s0, **(await router_node(s0))}
    assert s1["is_curriculum_navigation"] is True
    s2 = {**s1, **(await retrieval_node(s1))}
    s3 = {**s2, **(await crag_grader_node(s2))}
    offered = s3.get("last_offered_lessons") or []
    offered_seqs = [item["seq"] if isinstance(item, dict) else int(item) for item in offered]
    assert any(seq >= 57 for seq in offered_seqs), f"Expected pointer lessons (>=57) offered, got {offered}"

    # Kiểm chứng dữ liệu L1 transcript & manifest chapters đã sạch lỗi ASR mục tiêu
    l1_chunks_path = (
        ROOT_DIR
        / "data"
        / "transcripts"
        / "cpp-core"
        / "lesson-01_01_-_Cách_Tự_Học_Lập_Trình_Cho_Người_Mới"
        / "lesson-01_chunks.json"
    )
    l1_text = l1_chunks_path.read_text(encoding="utf-8").lower()
    for bad_tok in ("câu chúc", "lý thiết số", "mạng trai", "màng cha", "mạng một chiều", "mạng 2 chiều"):
        assert bad_tok not in l1_text, f"Found uncleaned ASR artifact '{bad_tok}' in lesson-01_chunks.json"

    ext_glossary = get_academic_glossary_prompt_extension("tìm hiểu câu chúc trong struct")
    assert "câu chúc" in ext_glossary.lower()


# ==============================================================================
# PC-04: Metaphor Prompting (Static messages[0]) + Echo Continuation + Timeout Fallback
# ==============================================================================
@pytest.mark.asyncio
async def test_pc04_analogy_prompt_echo_continuation_and_timeout_fallback():
    # 1. Static messages[0] + token-boundary analogy directive
    analogy_state = {
        **_make_base_state(
            "ví dụ con trỏ giống như tờ giấy ghi địa chỉ nhà có đúng k",
            lesson_seq=57,
            session_id="pc04_ctx",
        ),
        "intent": "course_query",
        "search_query": "con trỏ địa chỉ bộ nhớ",
        "retrieval_status": "grounded",
        "retrieved_chunks": [
            {
                "text": "Biến con trỏ dùng để lưu trữ địa chỉ vùng nhớ của một biến khác.",
                "lesson_seq": 57,
                "start_sec": 120,
                "end_sec": 180,
                "score": 0.62,
                "chunk_type": "video_transcript",
            }
        ],
        "suggested_timestamps": [{"sec": 120, "label": "02:00", "title": "Khái niệm con trỏ", "lesson_seq": 57}],
        "is_curriculum_navigation": False,
        "is_overview_query": False,
    }
    ctx_out = await context_assembly_node(analogy_state)
    msgs = ctx_out["assembled_messages"]
    assert msgs[0]["content"] == SOCRATIC_GROUNDED_PROMPT, "messages[0] must stay 100% static"
    assert "[CHỈ THỊ ĐÁNH GIÁ MỆNH ĐỀ / ẨN DỤ]" in msgs[-1]["content"]

    # Phản ví dụ boundary: 'đúng kiểu' & 'cho mình ví dụ về vòng lặp for' -> KHÔNG kích hoạt analogy directive
    for neg_prompt in (
        "khai báo int* p thế này có đúng kiểu dữ liệu không",
        "cho mình ví dụ về vòng lặp for",
    ):
        non_analogy_state = {
            **analogy_state,
            "prompt": neg_prompt,
        }
        non_ctx_out = await context_assembly_node(non_analogy_state)
        assert non_ctx_out["assembled_messages"][0]["content"] == SOCRATIC_GROUNDED_PROMPT
        assert "[CHỈ THỊ ĐÁNH GIÁ MỆNH ĐỀ / ẨN DỤ]" not in non_ctx_out["assembled_messages"][-1]["content"]

    # 2. Helper is_echo_only_prose & has_trailing_socratic_question
    q_analogy = "ví dụ con trỏ giống như tờ giấy ghi địa chỉ nhà có đúng k"
    echo_resp = "Ví dụ về con trỏ giống như tờ giấy ghi địa chỉ nhà có đúng không?"
    assert is_echo_only_prose(echo_resp, q_analogy) is True
    assert has_trailing_socratic_question(echo_resp, user_prompt=q_analogy) is False

    real_resp = (
        "Ví dụ về con trỏ giống như tờ giấy ghi địa chỉ nhà là rất chính xác! "
        "Con trỏ chỉ lưu địa chỉ vùng nhớ của biến khác chứ không chứa giá trị dữ liệu trực tiếp bên trong. "
        "Vậy nếu giá trị trong ngôi nhà đó thay đổi thì tờ giấy ghi địa chỉ có thay đổi theo không?"
    )
    assert is_echo_only_prose(real_resp, q_analogy) is False
    assert has_trailing_socratic_question(real_resp, user_prompt=q_analogy) is True

    # 3. ChatService.stream_chat: Echo continuation qua CÙNG pipeline
    service = ChatService()
    create_mock = AsyncMock(
        side_effect=[
            _make_fake_stream(
                [
                    "Ví dụ về con trỏ giống như tờ giấy ghi địa chỉ nhà có đúng không?",
                    "\n\n📍 **Mốc video bài giảng:** <timestamp sec=\"120\">02:00</timestamp>",
                ]
            ),
            _make_fake_stream(
                [
                    "Đúng rồi! Con trỏ là biến lưu địa chỉ vùng nhớ của biến khác, chứ không lưu bản sao giá trị bên trong. ",
                    "Theo bạn, nếu giá trị tại địa chỉ đó thay đổi thì giá trị đọc qua con trỏ có đổi theo không?",
                ]
            ),
        ]
    )
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock)))

    # Khởi chạy stream_chat thật với mock graph invoke tối thiểu? Không, mock graph invoke trả về grounded state chuẩn để kiểm tra stream_chat orchestration thật!
    fake_final_state = {
        "intent": "course_query",
        "is_course_query": True,
        "used_fast_path": False,
        "retrieved_chunks": analogy_state["retrieved_chunks"],
        "is_approximate": False,
        "retrieval_status": "grounded",
        "is_low_confidence": False,
        "target_lesson_seq": None,
        "action": None,
        "suggested_timestamps": analogy_state["suggested_timestamps"],
        "sources": [],
        "assembled_messages": msgs,
        "system_prompt": SOCRATIC_GROUNDED_PROMPT,
        "user_message_content": ctx_out["user_message_content"],
        "last_course_query": q_analogy,
    }
    mock_graph = MagicMock()
    mock_graph.aget_state = AsyncMock(return_value=SimpleNamespace(values={}))
    mock_graph.ainvoke = AsyncMock(return_value=fake_final_state)

    import app.services.chat as chat_mod

    orig_get_graph = chat_mod.get_chat_graph
    orig_commit = chat_mod.commit_assistant_turn
    commit_sessions: list[str] = []

    def _spy_commit(session_id_arg, *args, **kwargs):
        commit_sessions.append(session_id_arg)
        return orig_commit(session_id_arg, *args, **kwargs)

    chat_mod.get_chat_graph = lambda: mock_graph
    chat_mod.commit_assistant_turn = _spy_commit
    try:
        sid_ok = "pc04_stream_ok"
        reset_session_state(sid_ok)
        req = ChatRequest(prompt=q_analogy, course_id="cpp-core", lesson_seq=57, session_id=sid_ok)
        events = [ev async for ev in service.stream_chat(req)]
        full_text = _collect_sse_delta_text(events)
        assert create_mock.await_count == 2, "Expected 1 echo corrective continuation call"
        assert "địa chỉ vùng nhớ" in full_text
        assert '<timestamp sec="120"' in full_text
        assert full_text.count("Mốc video bài giảng:") == 1
        assert sid_ok in commit_sessions

        critic = TelemetryCriticService()
        audit_ok = critic.analyze_turn(
            {
                "turn": 1,
                "prompt": q_analogy,
                "response_text": full_text,
                "router": {"intent": "course_query", "used_fast_path": False},
                "crag": {"retrieval_status": "grounded"},
                "timestamps": [{"sec": 120}],
            }
        )
        assert audit_ok["is_echo_only"] is False

        # 4. Timeout/Error trên corrective continuation: Zero Fake Fallback + không commit turn lỗi + critic flags echo
        create_timeout = AsyncMock(
            side_effect=[
                _make_fake_stream(["Ví dụ về con trỏ giống như tờ giấy ghi địa chỉ nhà có đúng không?"]),
                TimeoutError("LLM continuation timed out"),
            ]
        )
        service.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create_timeout))
        )
        sid_to = "pc04_stream_timeout"
        reset_session_state(sid_to)
        req_to = ChatRequest(prompt=q_analogy, course_id="cpp-core", lesson_seq=57, session_id=sid_to)
        events_to = [ev async for ev in service.stream_chat(req_to)]
        text_to = _collect_sse_delta_text(events_to)
        assert create_timeout.await_count == 2
        assert "chạy thử" not in text_to and "dữ liệu đầu vào" not in text_to  # Zero Fake Fallback: không bơm fallback canned
        assert '<timestamp sec="120"' in text_to  # deterministic timestamp fallback preserved
        assert sid_to not in commit_sessions  # Không commit turn echo-only lỗi vào Checkpointer

        # Critic nhận diện đúng ca echo-only thô
        audit_echo = critic.analyze_turn(
            {
                "turn": 1,
                "prompt": q_analogy,
                "response_text": echo_resp,
                "router": {"intent": "course_query", "used_fast_path": False},
                "crag": {"retrieval_status": "grounded"},
                "timestamps": [{"sec": 120}],
            }
        )
        assert audit_echo["is_echo_only"] is True
    finally:
        chat_mod.get_chat_graph = orig_get_graph
        chat_mod.commit_assistant_turn = orig_commit


# ==============================================================================
# PC-05: Exclusion + Multi-Topic Nav + T9 Code AST Hygiene + Closers & Footer
# ==============================================================================
@pytest.mark.asyncio
async def test_pc05_exclusion_multitopic_codeast_closers_and_footer_hygiene():
    curriculum = get_curriculum_service()

    # 1. Exclusion: 'ngoài bài 57 ...' không được trả về Bài 57, phải giữ nguyên đa nhánh Vector & Tìm kiếm nhị phân
    q_excl = "ngoài bài 57 thì muốn học về vector với iterator hoặc tìm kiếm nhị phân thì xem những bài nào"
    excluded = curriculum.extract_excluded_lesson_seqs(q_excl)
    assert 57 in excluded
    cand = curriculum.find_lesson_for_query(q_excl, preferred_course_id="cpp-core")
    if cand is not None:
        cand_lesson = cand[0] if isinstance(cand, (tuple, list)) else cand
        assert cand_lesson.get("seq", cand_lesson.get("lesson_seq")) != 57
    ambig_cands = curriculum.find_ambiguous_candidates(q_excl, preferred_course_id="cpp-core")
    cands_list = (ambig_cands or {}).get("candidates", [])
    assert (ambig_cands or {}).get("is_ambiguous") is True
    assert (ambig_cands or {}).get("reason") == "multi_topic_disjunction"
    assert all(c.get("seq", c.get("lesson_seq")) != 57 for c in cands_list)
    cand_titles_low = " ".join((c.get("title") or "").lower() for c in cands_list)
    assert "vector" in cand_titles_low and "nhị phân" in cand_titles_low, f"Missing multi-topic candidates: {cands_list}"

    sid_nav = "pc05_excl_nav"
    reset_session_state(sid_nav)
    s0 = _make_base_state(q_excl, lesson_seq=57, session_id=sid_nav)
    s1 = {**s0, **(await router_node(s0))}
    assert s1["intent"] == "course_query"
    assert s1["is_curriculum_navigation"] is True
    s2 = {**s1, **(await retrieval_node(s1))}
    s3 = {**s2, **(await crag_grader_node(s2))}
    assert s3.get("target_lesson_seq") != 57
    assert s3.get("suggested_timestamps") == []
    offered_57_check = [
        item["seq"] if isinstance(item, dict) else int(item)
        for item in (s3.get("last_offered_lessons") or [])
    ]
    assert 57 not in offered_57_check
    assert len(offered_57_check) >= 2

    # REQ-07: 'sau bài 20 thì học gì' KHÔNG đưa 'sau bài' vào exclusion -> giữ nguyên Bài 20 trong included_seqs
    q_after_20 = "sau bài 20 thì học gì"
    assert 20 not in curriculum.extract_excluded_lesson_seqs(q_after_20)
    assert curriculum._extract_lesson_seq(q_after_20) == 20

    # 'bài này khác bài 11 chỗ nào' -> là câu hỏi so sánh/học tập, không bị hiểu nhầm nav thuần
    sid_cmp = "pc05_cmp_11"
    reset_session_state(sid_cmp)
    r_cmp = await router_node(_make_base_state("bài này khác bài 11 chỗ nào", lesson_seq=57, session_id=sid_cmp))
    assert r_cmp["intent"] == "course_query"
    assert r_cmp["is_curriculum_navigation"] is False

    # 2. T9 Cross-lesson code_ast filtering qua RetrievalService.search thật
    ret_svc = RetrievalService()
    fake_points = [
        SimpleNamespace(
            id="l57_vid",
            score=0.95,
            payload={
                "course_id": "cpp-core",
                "content_type": "video_transcript",
                "lesson_id": "lesson-57",
                "lesson_seq": 57,
                "raw_text": "Trong bài con trỏ này, chúng ta dùng toán tử & để lấy địa chỉ của biến.",
                "video_title": "Bai 57 Con tro",
                "start_sec": 120,
                "end_sec": 180,
            },
        ),
        SimpleNamespace(
            id="l54_main",
            score=0.40,
            payload={
                "course_id": "cpp-core",
                "content_type": "code_ast",
                "lesson_id": "lesson-54",
                "lesson_seq": 54,
                "code_scope": "function_main",
                "context_code": "int main() { return 0; }",
                "raw_text": "int main() { return 0; }",
            },
        ),
        SimpleNamespace(
            id="l50_struct",
            score=0.80,
            payload={
                "course_id": "cpp-core",
                "content_type": "code_ast",
                "lesson_id": "lesson-50",
                "lesson_seq": 50,
                "code_scope": "struct_definition",
                "context_code": "struct SinhVien { string ten; };",
                "raw_text": "struct SinhVien { string ten; };",
            },
        ),
        SimpleNamespace(
            id="l57_ptr",
            score=0.55,
            payload={
                "course_id": "cpp-core",
                "content_type": "code_ast",
                "lesson_id": "lesson-57",
                "lesson_seq": 57,
                "code_scope": "variable_declaration",
                "context_code": "int *p = &a;",
                "raw_text": "int *p = &a;",
            },
        ),
    ]

    async def _fake_query_points(*args, **kwargs):
        return SimpleNamespace(points=fake_points)

    async def _fake_future_points(*args, **kwargs):
        return []

    async def _fake_rerank_async(*, query: str, documents: list[str]):
        logits = []
        for doc in documents:
            if "toán tử &" in doc:
                logits.append(2.5)  # video high confidence (>= 0.45)
            elif "const int x = 5" in doc:
                logits.append(-0.9)  # same-lesson function_main 0.15..0.35
            elif "int main()" in doc:
                logits.append(-2.0)  # low score < 0.35 (cross-lesson boilerplate leak)
            elif "struct SinhVien" in doc:
                logits.append(1.5)  # prior-lesson high confidence (>= 0.35)
            else:
                logits.append(-0.9)  # same-lesson 0.15..0.35
        return logits

    qdrant_client = ret_svc.client
    orig_qp = qdrant_client.query_points
    orig_future = ret_svc._fetch_future_points
    orig_rerank_async = ret_svc.embedding_service.rerank_documents_async

    # Sub-case A: Prior-lesson >= 0.35 (L50 struct) được giữ; Cross-lesson < 0.35 boilerplate (L54 main) bị chặn
    active_points = [fake_points[0], fake_points[1], fake_points[2]]

    async def _fake_qp_a(*args, **kwargs):
        return SimpleNamespace(points=active_points)

    qdrant_client.query_points = _fake_qp_a
    ret_svc._fetch_future_points = _fake_future_points
    ret_svc.embedding_service.rerank_documents_async = _fake_rerank_async
    try:
        res_a = await ret_svc.search(
            query_text="con trỏ dùng toán tử nào",
            course_id="cpp-core",
            current_lesson_seq=57,
            final_top_k=5,
        )
        ids_a = {str(c.get("id")) for c in res_a.chunks}
        assert res_a.status == "grounded"
        assert "l54_main" not in ids_a, f"L54 low-score function_main leaked into L57: {ids_a}"
        assert "l50_struct" in ids_a, f"Prior-lesson >= 0.35 struct must be preserved: {ids_a}"

        # Sub-case B: Same-lesson 0.15..0.35 AST (gồm cả function_main cùng bài ở bài nhập môn như L2) được giữ; L54 leak khác bài vẫn bị chặn
        active_points = [fake_points[0], fake_points[1], fake_points[3]]
        res_b = await ret_svc.search(
            query_text="con trỏ dùng toán tử nào",
            course_id="cpp-core",
            current_lesson_seq=57,
            final_top_k=5,
        )
        ids_b = {str(c.get("id")) for c in res_b.chunks}
        assert res_b.status == "grounded"
        assert "l54_main" not in ids_b, f"L54 low-score function_main leaked into L57: {ids_b}"
        assert "l57_ptr" in ids_b, f"Same-lesson 0.15..0.35 AST must be preserved: {ids_b}"

        # Sub-case C: Same-lesson function_main >= 0.15 (vd: bài 54 hoặc bài 2 nhập môn) vẫn được đồng truy xuất
        same_lesson_main_point = SimpleNamespace(
            id="l57_main",
            score=0.55,
            payload={
                "course_id": "cpp-core",
                "content_type": "code_ast",
                "lesson_id": "lesson-57",
                "lesson_seq": 57,
                "code_scope": "function_main",
                "context_code": "int main() { const int x = 5; return 0; }",
                "raw_text": "int main() { const int x = 5; return 0; }",
            },
        )
        active_points = [fake_points[0], fake_points[1], same_lesson_main_point]
        res_c = await ret_svc.search(
            query_text="con trỏ dùng toán tử nào",
            course_id="cpp-core",
            current_lesson_seq=57,
            final_top_k=5,
        )
        ids_c = {str(c.get("id")) for c in res_c.chunks}
        assert res_c.status == "grounded"
        assert "l54_main" not in ids_c, f"Cross-lesson L54 leaked into L57: {ids_c}"
        assert "l57_main" in ids_c, f"Same-lesson >= 0.15 function_main must be preserved: {ids_c}"
    finally:
        qdrant_client.query_points = orig_qp
        ret_svc._fetch_future_points = orig_future
        ret_svc.embedding_service.rerank_documents_async = orig_rerank_async

    # 3. Forbidden closers + Footer '📍' lifecycle
    closer_cases = [
        "Con trỏ là biến lưu địa chỉ bộ nhớ.\n\nBạn đã hiểu đúng không?",
        "Con trỏ giúp truy cập vùng nhớ gián tiếp. Bạn hiểu được điều này chưa?",
        "Biến con trỏ khai báo với dấu sao. Bạn có câu hỏi gì không?",
        "Địa chỉ biến lấy qua toán tử &. Chúc bạn học tốt!",
    ]
    for txt in closer_cases:
        assert has_trailing_socratic_question(txt) is False, f"Forbidden closer must not satisfy '?': {txt}"
        cleaned, inserted = apply_streaming_sanitizers(
            txt,
            valid_secs=set(),
            fallback_question="Theo bạn toán tử nào dùng để lấy địa chỉ của một biến?",
        )
        assert inserted is True
        assert "Bạn đã hiểu đúng không?" not in cleaned
        assert "Bạn hiểu được điều này chưa?" not in cleaned
        assert "Bạn có câu hỏi gì không?" not in cleaned
        assert "Chúc bạn học tốt!" not in cleaned
        assert "Theo bạn toán tử nào dùng để lấy địa chỉ của một biến?" in cleaned

    # Không chặn nhầm câu hỏi có nội dung thật hoặc góp ý sửa sai
    kept_1, _ = apply_streaming_sanitizers(
        "Con trỏ lưu địa chỉ bộ nhớ. Bạn có muốn xem ví dụ về con trỏ không?",
        valid_secs=set(),
        fallback_question="FALLBACK?",
    )
    assert "Bạn có muốn xem ví dụ về con trỏ không?" in kept_1
    assert "FALLBACK?" not in kept_1

    kept_2, _ = apply_streaming_sanitizers(
        "Bạn đã hiểu nhầm chỗ khai báo rồi. Vậy kiểu dữ liệu của con trỏ là gì?",
        valid_secs=set(),
        fallback_question="FALLBACK?",
    )
    assert "Bạn đã hiểu nhầm chỗ khai báo rồi." in kept_2

    # Bare <timestamp> trên dòng riêng -> tự động gắn nhãn 📍 **Mốc video bài giảng:**
    bare_out, _ = apply_streaming_sanitizers(
        'Con trỏ lưu địa chỉ. Theo bạn toán tử & trả về gì?\n\n<timestamp sec="145">02:25</timestamp>\n',
        valid_secs={145},
        fallback_question="FALLBACK?",
    )
    assert "📍 **Mốc video bài giảng:** <timestamp sec=\"145\">02:25</timestamp>" in bare_out

    # Inline <timestamp> giữa câu KHÔNG bị chèn 📍 ở giữa câu
    inline_out, _ = apply_streaming_sanitizers(
        'Trong bài giảng, <timestamp sec="145">02:25</timestamp> là chỗ thầy giải thích con trỏ. Theo bạn biến con trỏ chứa gì?',
        valid_secs={145},
        fallback_question="FALLBACK?",
    )
    assert "📍 **Mốc video bài giảng:**" not in inline_out

    # hold_footer_until_flush=True: Nếu mọi timestamp đều bị strip -> KHÔNG lọt dangling 📍
    pipe = StreamingOutputPipeline(
        valid_secs={10},
        fallback_question="Theo bạn biến con trỏ lưu gì?",
        hold_footer_until_flush=True,
    )
    chunks = pipe.process(
        'Con trỏ là biến lưu địa chỉ.\n\n📍 **Mốc video bài giảng:** <timestamp sec="999">16:39</timestamp>'
    )
    chunks.extend(pipe.flush())
    held_res = "".join(chunks)
    assert "📍" not in held_res
    assert "Mốc video bài giảng:" not in held_res
    assert "Theo bạn biến con trỏ lưu gì?" in held_res
