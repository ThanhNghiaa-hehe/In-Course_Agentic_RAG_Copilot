"""
LangGraph StateGraph Orchestration Engine cho In-Course Agentic RAG Copilot.
Tác giả: Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Kiến trúc:
- State Schema chuẩn Pydantic / TypedDict với đầy đủ context slots.
- 3 Discrete Nodes chính:
  1. `router_node`: Multi-Class Semantic Router (Aurelio AI 2024).
  2. `retrieval_node`: True Hybrid Retrieval (Dense E5 + Sparse BM25 + In-HNSW Pre-filter).
  3. `crag_grader_node`: Thẩm định tương quan CRAG Meta AI 2024 & Đóng gói Socratic Prompt.
- Conditional Edges: Phân luồng rẽ nhánh linh hoạt giữa Fast-Path và Course Retrieval.
"""

import logging
from typing import TypedDict, List, Dict, Any, Optional
from markdown_it import MarkdownIt
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

_MD_PARSER = MarkdownIt()

_CPP_PARSER = None
try:
    import tree_sitter
    import tree_sitter_cpp as tscpp
    _CPP_LANG = tree_sitter.Language(tscpp.language())
    _CPP_PARSER = tree_sitter.Parser(_CPP_LANG)
except Exception:
    _CPP_PARSER = None

from app.agent.router import get_intent_router
from app.services.curriculum import get_curriculum_service
from app.services.retrieval import get_retrieval_service, RetrievalResult
from app.agent.guardrails import get_session_rate_limiter, normalize_user_input
from app.agent.prompts import (
    SOCRATIC_GROUNDED_PROMPT,
    OUT_OF_LESSON_PROMPT,
    CURRICULUM_OVERVIEW_PROMPT,
    COVERAGE_GAP_PROMPT,
    get_academic_glossary_prompt_extension,
)
from app.config import settings

logger = logging.getLogger("uvicorn.error")


class AgentState(TypedDict):
    """
    Trạng thái luồng xử lý Agentic RAG chuẩn hóa qua toàn bộ chu trình StateGraph.
    Hỗ trợ bộ nhớ phiên đa lượt (Multi-turn Memory), Cửa sổ trượt k turns và Checkpointer.
    """
    # 1. Quản lý phiên đa lượt & Checkpointer (LangGraph Thread State)
    session_id: str
    turn_count: int
    messages: List[Dict[str, str]]
    conversation_summary: Optional[str]

    # 2. Inputs từ học viên ở lượt hiện tại
    prompt: str
    course_id: str
    lesson_seq: int
    current_lesson_seq: Optional[int]
    current_video_sec: Optional[int]

    # 3. Định tuyến ý định (Intent Routing)
    intent: str
    direct_response: Optional[str]
    is_course_query: bool
    search_query: Optional[str]
    last_course_query: Optional[str]
    last_turn_intent: Optional[str]
    is_curriculum_navigation: bool
    is_overview_query: bool

    # 4. Kết quả truy xuất & Thẩm định CRAG
    retrieval_status: str
    retrieved_chunks: List[Dict[str, Any]]
    is_approximate: bool
    is_low_confidence: bool
    target_lesson_seq: Optional[int]
    future_best_chunk: Optional[Dict[str, Any]]
    suggested_timestamps: List[Dict[str, Any]]
    sources: List[Dict[str, Any]]

    # 4b. Điều hướng đàm thoại đa lượt (Conversational Navigation Agent)
    pending_navigation: Optional[Dict[str, Any]]
    last_offered_lessons: Optional[List[Dict[str, Any]]]
    action: Optional[Dict[str, Any]]

    # 4c. Neo thời gian video đa lượt (Stateful Temporal Anchor Tracking)
    last_video_sec: Optional[int]
    last_lesson_seq: Optional[int]
    prev_video_sec: Optional[int]
    prev_lesson_seq: Optional[int]
    inherited_video_sec: Optional[int]
    missing_deictic_sec: bool

    # 5. Đóng gói Prompt Socratic & Danh sách ChatML cho LLM Generation
    system_prompt: str
    user_message_content: str
    assembled_messages: List[Dict[str, str]]


def _sanitize_context_code_ast(code: str) -> str:
    """
    Bóc tách và tước bỏ khung vỏ #include và int main() bằng Tree-sitter C++ AST (Zero Regex).
    Chỉ giữ lại phần logic, giải thuật và các định nghĩa hàm/lớp trọng tâm.
    Tuân thủ nghiêm ngặt Invariant 2 (In-Context AST Sanitization & Imitation Firewall).
    """
    if not code:
        return ""
    if _CPP_PARSER is None:
        clean_lines = []
        for line in code.splitlines():
            s = line.strip()
            if s.startswith("#include") or s.startswith("using namespace"):
                continue
            clean_lines.append(line)
        return "\n".join(clean_lines).strip()

    try:
        tree = _CPP_PARSER.parse(code.encode("utf-8"))
        preserved_parts = []
        for child in tree.root_node.children:
            if child.type in ("preproc_include", "using_declaration"):
                continue
            if child.type == ";" and preserved_parts:
                preserved_parts[-1] += ";"
                continue
            if child.type == "function_definition":
                decl = child.child_by_field_name("declarator")
                if decl and b"main" in decl.text:
                    body = child.child_by_field_name("body")
                    if body:
                        stmts = [
                            c.text.decode("utf-8")
                            for c in body.children
                            if c.type not in ("{", "}") and not (c.type == "return_statement" and b"0" in c.text)
                        ]
                        if stmts:
                            preserved_parts.append("\n".join(stmts))
                        continue
            preserved_parts.append(child.text.decode("utf-8"))
        res = "\n\n".join(preserved_parts).strip()
        return res if res else code.strip()
    except Exception as e:
        logger.warning(f"[chat_graph] Lỗi Tree-sitter AST sanitize ({e}), giữ nguyên code.")
        return code.strip()


def _format_context_block(chunks: List[Dict[str, Any]], max_chars: int = settings.MAX_CONTEXT_CHARS) -> str:
    """
    Định dạng các chunks ngữ cảnh thành khối văn bản có cấu trúc súc tích (Context Distillation).
    Áp trần tối đa ~800 tokens (~1500 ký tự) để tối ưu thời gian Prefill Attention trên GPU (Mục 4.2 - Nhịp 1B).
    Áp dụng In-Context AST Sanitization để triệt tiêu 100% bẫy In-Context Imitation.
    Bảo toàn 100% thẻ <timestamp> và mã nguồn Code AST.
    """
    if not chunks:
        return "[LƯU Ý: Không tìm thấy tài liệu bài giảng nào vượt qua ngưỡng tin cậy cho câu hỏi này. Hãy hướng dẫn học viên dựa trên kiến thức chuẩn của C++]."

    MAX_CODE_CHUNK_CHARS = 550
    MAX_VIDEO_CHUNK_CHARS = 400

    blocks = ["[NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC]"]
    current_len = 0
    for idx, chunk in enumerate(chunks, 1):
        c_type = chunk.get("content_type", "unknown")
        lesson_seq = chunk.get("lesson_seq", "?")

        if c_type == "code_ast":
            scope = chunk.get("code_scope", "")
            code_content = (chunk.get("context_code") or chunk.get("raw_text", "")).strip()
            sanitized_code = _sanitize_context_code_ast(code_content)
            if len(sanitized_code) > MAX_CODE_CHUNK_CHARS:
                sanitized_code = sanitized_code[:MAX_CODE_CHUNK_CHARS].rstrip() + "\n// [...đoạn mã tiếp theo được rút gọn...]"
            item_text = (
                f"[MÃ NGUỒN BÀI GIẢNG THAM KHẢO - ĐÂY KHÔNG PHẢI CODE CỦA HỌC VIÊN]\n"
                f"// Trích đoạn logic Bài {lesson_seq} ({scope}):\n"
                f"```cpp\n{sanitized_code}\n```"
            )
        else:
            tag = chunk.get("timestamp_tag", "")
            raw_t = (chunk.get("raw_text", "")).strip()
            raw_t = " ".join(raw_t.split())
            if len(raw_t) > MAX_VIDEO_CHUNK_CHARS:
                raw_t = raw_t[:MAX_VIDEO_CHUNK_CHARS].rstrip() + "..."
            tag_info = f" (mốc {tag})" if tag else ""
            item_text = f"Nguồn Bài {lesson_seq}{tag_info}: {raw_t}"

        # Áp trần ngân sách ngữ cảnh (trừ item đầu tiên luôn giữ)
        if current_len + len(item_text) > max_chars and idx > 1:
            break

        blocks.append(item_text)
        current_len += len(item_text)

    return "\n\n".join(blocks)



# ==========================================
# NODE 1: INTENT ROUTER NODE
# ==========================================
async def router_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 1: Phân loại ý định người dùng qua Multi-Class Semantic Router (Aurelio AI).
    Áp dụng Context-Aware Query Formulation (SIGIR/Google Research):
    Khi có lịch sử hội thoại, ghép câu hỏi gần nhất của User làm tiền đề ngữ cảnh để Vector E5
    nhận diện chính xác ngữ nghĩa câu hỏi nối tiếp (Coreference & Ellipsis) thuần túy bằng toán học ML.
    """
    router = get_intent_router()
    curr_svc = get_curriculum_service()
    history = state.get("messages", [])
    raw_prompt = normalize_user_input(state.get("prompt", ""))
    pending_nav = state.get("pending_navigation")

    # 0. Nhận diện Mệnh Lệnh Chuyển Bài Trực Tiếp (Conversational UI Action Dispatcher - Mục 3.2 & 4.1)
    requested_nav_seq = curr_svc.extract_requested_nav_seq_raw(raw_prompt)
    if requested_nav_seq is not None:
        if curr_svc.get_lesson_by_seq(requested_nav_seq) is None:
            min_seq, max_seq = curr_svc.get_lesson_seq_bounds()
            logger.info(
                f"[LangGraph:router_node] Số bài {requested_nav_seq} nằm ngoài phạm vi manifest ({min_seq}..{max_seq})."
            )
            return {
                "prompt": raw_prompt,
                "intent": "out_of_scope",
                "direct_response": (
                    f"Giáo trình hiện tại chỉ gồm các bài học từ **Bài {min_seq}** đến **Bài {max_seq}**, "
                    f"không có **Bài {requested_nav_seq}**. Bạn muốn chuyển đến số bài nào trong phạm vi từ Bài {min_seq} đến Bài {max_seq}?"
                ),
                "is_course_query": False,
                "target_lesson_seq": None,
                "last_turn_intent": "out_of_scope",
                "action": None,
                "pending_navigation": None,
            }
        logger.info(
            f"[LangGraph:router_node] Nhận diện Mệnh Lệnh Chuyển Bài Trực Tiếp: "
            f"'{raw_prompt}' -> target_lesson_seq={requested_nav_seq}"
        )
        direct_resp = (
            f"Đã rõ! Mình đang chuyển bạn sang **Bài {requested_nav_seq}** "
            f"để bạn theo dõi video bài giảng ngay nhé! 🎬"
        )
        return {
            "prompt": raw_prompt,
            "intent": "confirm_navigation",
            "direct_response": direct_resp,
            "is_course_query": False,
            "target_lesson_seq": requested_nav_seq,
            "last_turn_intent": "confirm_navigation",
            "last_offered_lessons": [],
            "action": {
                "type": "navigate_and_seek",
                "action": "navigate_lesson",
                "target_lesson_seq": requested_nav_seq,
                "sec": 0,
                "label": "00:00"
            },
            "pending_navigation": None
        }

    # Kiểm tra xác nhận đàm thoại hoặc mệnh lệnh hồi chỉ ('chuyển cho tôi đến bài đó') từ trạng thái có cấu trúc
    is_anaphoric_nav = curr_svc.extract_anaphoric_navigation_command(raw_prompt)
    if pending_nav:
        is_confirmed, conf_score = router.check_confirmation(raw_prompt)
        if is_confirmed or is_anaphoric_nav:
            target_seq = pending_nav.get("lesson_seq")
            target_sec = pending_nav.get("sec", 0)
            target_lbl = pending_nav.get("label", "00:00")
            logger.info(
                f"[LangGraph:router_node] Xác nhận chuyển bài thành công (NLI={conf_score*100:.1f}%, ana={is_anaphoric_nav}): "
                f"Bài {target_seq} @ {target_lbl} ({target_sec}s)"
            )
            direct_resp = (
                f"Đã rõ! Mình đang chuyển bạn sang **Bài {target_seq}** tại mốc **{target_lbl}** "
                f"để bạn theo dõi video bài giảng ngay nhé! 🎬"
            )
            return {
                "prompt": raw_prompt,
                "intent": "confirm_navigation",
                "direct_response": direct_resp,
                "is_course_query": False,
                "target_lesson_seq": target_seq,
                "last_turn_intent": "confirm_navigation",
                "last_offered_lessons": [],
                "action": {
                    "type": "navigate_and_seek",
                    "action": "navigate_lesson",
                    "target_lesson_seq": target_seq,
                    "sec": target_sec,
                    "label": target_lbl
                },
                "pending_navigation": None
            }
        else:
            logger.info("[LangGraph:router_node] Học viên đặt câu hỏi khác, tự động xóa pending_navigation.")
    elif is_anaphoric_nav:
        offered_lessons = state.get("last_offered_lessons") or []
        if len(offered_lessons) == 1:
            only_les = offered_lessons[0]
            if isinstance(only_les, dict):
                target_seq = only_les.get("seq")
                target_sec = int(only_les.get("sec", 0) or 0)
                target_lbl = only_les.get("label") or f"{target_sec // 60:02d}:{target_sec % 60:02d}"
            else:
                target_seq = int(only_les) if str(only_les).isdigit() else None
                target_sec = 0
                target_lbl = "00:00"
            if target_seq is not None and curr_svc.get_lesson_by_seq(int(target_seq)) is not None:
                logger.info(
                    f"[LangGraph:router_node] Giải tham chiếu điều hướng hồi chỉ qua last_offered_lessons: Bài {target_seq}"
                )
                return {
                    "prompt": raw_prompt,
                    "intent": "confirm_navigation",
                    "direct_response": (
                        f"Đã rõ! Mình đang chuyển bạn sang **Bài {target_seq}** tại mốc **{target_lbl}** "
                        f"để bạn theo dõi video bài giảng ngay nhé! 🎬"
                    ),
                    "is_course_query": False,
                    "target_lesson_seq": int(target_seq),
                    "last_turn_intent": "confirm_navigation",
                    "last_offered_lessons": [],
                    "action": {
                        "type": "navigate_and_seek",
                        "action": "navigate_lesson",
                        "target_lesson_seq": int(target_seq),
                        "sec": target_sec,
                        "label": target_lbl,
                    },
                    "pending_navigation": None,
                }
        elif len(offered_lessons) > 1:
            choices_lines = []
            for item in offered_lessons:
                if isinstance(item, dict):
                    c_seq = item.get("seq")
                    c_course_hint = item.get("course_id")
                    c_title_hint = item.get("title")
                else:
                    c_seq = int(item) if str(item).isdigit() else None
                    c_course_hint = None
                    c_title_hint = None
                les_obj = curr_svc.get_lesson_by_seq(int(c_seq), course_id=c_course_hint) if c_seq is not None else None
                c_title = (les_obj or {}).get("title") or c_title_hint or f"Bài {c_seq}"
                c_course = (les_obj or {}).get("course_id") or c_course_hint or ""
                choices_lines.append(f"- **Bài {c_seq}** (khóa `{c_course}`): {c_title}")
            clarify_resp = (
                "Ở lượt trước có nhiều bài học liên quan được gợi ý trong giáo trình:\n\n"
                + "\n".join(choices_lines)
                + "\n\nBạn muốn mình chuyển thẳng đến số bài nào (ví dụ: *chuyển sang bài 57*)?"
            )
            return {
                "prompt": raw_prompt,
                "intent": "confirm_navigation",
                "direct_response": clarify_resp,
                "is_course_query": False,
                "target_lesson_seq": None,
                "last_turn_intent": "confirm_navigation",
                "last_offered_lessons": offered_lessons,
                "action": None,
                "pending_navigation": None,
            }

    # 1. Phân loại ý định thô qua Router Machine Learning
    raw_clf = router.classify(raw_prompt)
    prev_saved_lesson = state.get("last_lesson_seq")
    if prev_saved_lesson is None:
        prev_saved_lesson = state.get("current_lesson_seq")
    curr_lesson = state.get("lesson_seq")
    lesson_switched = (
        prev_saved_lesson is not None
        and isinstance(prev_saved_lesson, int)
        and not isinstance(prev_saved_lesson, bool)
        and curr_lesson is not None
        and int(prev_saved_lesson) != int(curr_lesson)
    )

    # Recency Gate: Chỉ giữ anchor_query khi lượt liền trước thực sự là course_query (tránh T1 -> T2 OOS -> T3 cứu nhầm)
    prev_turn_intent = state.get("last_turn_intent")
    recency_allows_anchor = True
    if prev_turn_intent is not None:
        recency_allows_anchor = (prev_turn_intent == "course_query")
    elif history:
        for m in reversed(history):
            if m.get("role") == "user":
                last_u = normalize_user_input(m.get("content", ""))
                is_soc_last, _ = router.is_pure_social(last_u)
                is_ack_last, _ = router.is_social_acknowledgment(last_u)
                if is_soc_last or is_ack_last or not router.classify(last_u).is_course_query:
                    recency_allows_anchor = False
                break

    anchor_query = None if (lesson_switched or not recency_allows_anchor) else state.get("last_course_query")
    if lesson_switched and state.get("last_course_query"):
        logger.info(
            f"[LangGraph:router_node] Phát hiện đổi bài học ({prev_saved_lesson} -> {curr_lesson}): "
            "đặt lại mỏ neo last_course_query cũ để chống rò rỉ chủ đề."
        )
    if not anchor_query and history and not lesson_switched and recency_allows_anchor:
        # Tìm câu hỏi user gần nhất trong history mà không phải là pure social greeting hay acknowledgment
        for m in reversed(history):
            if m.get("role") == "user":
                cand = normalize_user_input(m.get("content", ""))
                is_soc, _ = router.is_pure_social(cand)
                is_ack, _ = router.is_social_acknowledgment(cand)
                if not is_soc and not is_ack and router.classify(cand).is_course_query:
                    anchor_query = cand
                    break

    # -------------------------------------------------------------------------
    # BƯỚC 0: TERMINAL SECURITY INPUT GUARDRAIL VERDICT (OWASP LLM01)
    # -------------------------------------------------------------------------
    if getattr(raw_clf, "is_security_refusal", False):
        logger.warning(
            f"[LangGraph:router_node] SecurityInputGuardrail từ chối đầu vào: '{raw_prompt[:40]}...' -> out_of_scope"
        )
        return {
            "prompt": raw_prompt,
            "intent": "out_of_scope",
            "direct_response": raw_clf.direct_response,
            "is_course_query": False,
            "search_query": None,
            "last_course_query": anchor_query,
            "last_turn_intent": "out_of_scope",
            "is_curriculum_navigation": False,
            "pending_navigation": None,
            "action": None,
        }

    # -------------------------------------------------------------------------
    # BƯỚC 1: SOCIAL ACKNOWLEDGMENT & PURE SOCIAL CLOSURE GATE
    # -------------------------------------------------------------------------
    time_ref = curr_svc.extract_video_time_reference(raw_prompt)
    explicit_seq = curr_svc._extract_lesson_seq(raw_prompt.lower())
    is_in_video_time_ref = time_ref is not None and explicit_seq is None
    is_anchored_deictic_current = (
        is_in_video_time_ref
        and time_ref.get("kind") == "deictic_current"
        and state.get("current_video_sec") is not None
    )

    is_soc_ack, ack_sim = router.is_social_acknowledgment(raw_prompt)
    is_pure_soc, soc_sim = router.is_pure_social(raw_prompt)
    if is_soc_ack or ((not raw_clf.is_course_query) and is_pure_soc and not is_in_video_time_ref):
        max_social_sim = max(ack_sim, soc_sim)
        logger.info(
            f"[LangGraph:router_node] Bước 1 Social Acknowledgment Gate (Sim={max_social_sim:.3f}): "
            f"'{raw_prompt[:35]}...' -> chit_chat (skip RAG)"
        )
        return {
            "prompt": raw_prompt,
            "intent": "chit_chat",
            "direct_response": router._select_chitchat_response(raw_prompt),
            "is_course_query": False,
            "search_query": None,
            "last_course_query": anchor_query,  # Bảo toàn anchor cho các lượt học tập tiếp theo!
            "last_turn_intent": "chit_chat",
            "is_curriculum_navigation": False,
            "pending_navigation": None,
            "action": None
        }

    # -------------------------------------------------------------------------
    # BƯỚC 2: CURRICULUM NAVIGATION GATE
    # -------------------------------------------------------------------------
    is_curriculum_nav, nav_sim = router.is_curriculum_navigation(raw_prompt)
    if is_curriculum_nav:
        time_ref = curr_svc.extract_video_time_reference(raw_prompt)
        explicit_seq = curr_svc._extract_lesson_seq(raw_prompt.lower())
        is_temporal_current = (
            time_ref is not None
            and explicit_seq is None
            and not curr_svc._names_other_lesson_topic(
                raw_prompt,
                current_lesson_seq=state.get("lesson_seq"),
                preferred_course_id=state.get("course_id"),
            )
        )
        if is_temporal_current:
            logger.info(
                f"[LangGraph:router_node] Bước 2 Temporal Guard: '{raw_prompt[:40]}...' "
                "là truy vấn mốc video bài hiện tại -> không chuyển sang Curriculum Navigation."
            )
            is_curriculum_nav = False

    if is_curriculum_nav:
        logger.info(
            f"[LangGraph:router_node] Bước 2 Curriculum Navigation Gate (NavSim={nav_sim:.3f}): "
            f"'{raw_prompt[:40]}...' -> Tìm bài học mới trong playlist"
        )
        return {
            "prompt": raw_prompt,
            "intent": "course_query",
            "direct_response": None,
            "is_course_query": True,
            "search_query": raw_prompt,
            "last_course_query": anchor_query,
            "last_turn_intent": "course_query",
            "is_curriculum_navigation": True,
            "pending_navigation": None,
            "action": None
        }

    # -------------------------------------------------------------------------
    # BƯỚC 3: PHÂN NHÁNH THEO raw_clf VÀ anchor_query (CHỐNG Ô NHIỄM NGỮ CẢNH - MỤC 5.2)
    # -------------------------------------------------------------------------
    if raw_clf.is_course_query:
        # Kiểm tra Semantic Topic Shift Isolation Gate:
        # Chỉ thực hiện Context Fusion khi câu hỏi phụ thuộc ngữ cảnh VÀ không bị đổi chủ đề
        is_dep = router.is_context_dependent(raw_prompt, anchor_query=anchor_query) if anchor_query else False
        is_shift, drift_sim = router.is_topic_shift(raw_prompt, anchor_query) if anchor_query else (False, 1.0)

        if anchor_query and is_dep and not is_shift and not is_anchored_deictic_current:
            search_query = f"{anchor_query} — {raw_prompt}"
            new_last_course_query = f"{anchor_query} | {raw_prompt}" if len(anchor_query) < 220 else raw_prompt
            logger.info(f"[LangGraph:router_node] Bước 3 Context Fusion (Dependent & Coherent): '{search_query[:55]}...'")
        else:
            search_query = raw_prompt
            new_last_course_query = raw_prompt
            if anchor_query and is_shift:
                logger.info(f"[LangGraph:router_node] Bước 3 Topic Shift phát hiện (Sim={drift_sim:.3f}): Cô lập câu hỏi mới '{raw_prompt[:40]}...'")
            else:
                logger.info(f"[LangGraph:router_node] Bước 3 Course Query đơn lập: '{raw_prompt[:40]}...'")

        return {
            "prompt": raw_prompt,
            "intent": "course_query",
            "direct_response": None,
            "is_course_query": True,
            "search_query": search_query,
            "last_course_query": new_last_course_query,
            "last_turn_intent": "course_query",
            "is_curriculum_navigation": False,
            "pending_navigation": None,
            "action": None
        }
    else:
        # raw_clf.is_course_query == False
        # CHỈ gọi router.classify_contextual(raw_prompt, anchor_query) khi anchor_query tồn tại (đã qua Recency Gate) VÀ is_context_dependent là True!
        if (
            anchor_query
            and recency_allows_anchor
            and not is_anchored_deictic_current
            and router.is_context_dependent(raw_prompt, anchor_query=anchor_query)
        ):
            classification, formulated_q = router.classify_contextual(raw_prompt, anchor_query)
            if classification.is_course_query:
                search_query = formulated_q
                new_last_course_query = f"{anchor_query} | {raw_prompt}" if len(anchor_query) < 220 else raw_prompt
                logger.info(f"[LangGraph:router_node] Bước 3 Contextual Rescue thành công: '{raw_prompt}' -> SearchQuery: '{search_query[:55]}...'")
                return {
                    "prompt": raw_prompt,
                    "intent": "course_query",
                    "direct_response": None,
                    "is_course_query": True,
                    "search_query": search_query,
                    "last_course_query": new_last_course_query,
                    "last_turn_intent": "course_query",
                    "is_curriculum_navigation": False,
                    "pending_navigation": None,
                    "action": None
                }
            else:
                non_course_clf = classification
        else:
            non_course_clf = raw_clf

        # Bước 3b: In-Video Temporal & 2-Slot Section-Seeking NLI Gate
        # Cứu câu hỏi mốc/đoạn video thiếu từ khóa C++ ("phút thứ 6...", "khoảng phút bao nhiêu thì nói về lý thuyết")
        # đồng thời chặn câu thể thao/đời sống và bảo vệ danh tính/xã giao (sim_sys < 0.88, not is_soc_ack, not is_pure_soc).
        sim_sys = router.get_system_identity_similarity(raw_prompt)
        is_section_seeking = (
            curr_svc.is_video_section_seeking_query(raw_prompt)
            and not is_curriculum_nav
            and not is_soc_ack
            and not is_pure_soc
            and sim_sys < 0.88
            and not curr_svc._names_other_lesson_topic(
                raw_prompt,
                current_lesson_seq=state.get("lesson_seq"),
                preferred_course_id=state.get("course_id"),
            )
        )
        if (is_in_video_time_ref or is_section_seeking) and not is_pure_soc and not is_soc_ack and sim_sys < 0.88:
            slm_probs = router._get_slm_probs(raw_prompt)
            p_oos = float(slm_probs[2]) if slm_probs is not None else 0.0
            if p_oos < 0.75:
                is_in_video, offtopic_score = router._nli_arbiter.verify_in_video_temporal_query(raw_prompt)
                if is_in_video:
                    logger.info(
                        f"[LangGraph:router_node] Bước 3b In-Video Temporal/Section NLI Rescue: "
                        f"'{raw_prompt[:40]}...' (time_ref={is_in_video_time_ref}, section={is_section_seeking}, P_oos={p_oos:.3f}, NLI_offtopic={offtopic_score:.3f}) -> course_query"
                    )
                    return {
                        "prompt": raw_prompt,
                        "intent": "course_query",
                        "direct_response": None,
                        "is_course_query": True,
                        "search_query": raw_prompt,
                        "last_course_query": raw_prompt,
                        "last_turn_intent": "course_query",
                        "is_curriculum_navigation": False,
                        "pending_navigation": None,
                        "action": None
                    }

        logger.info(f"[LangGraph:router_node] Bước 3 Non-course classification ({non_course_clf.intent}): '{raw_prompt[:35]}...'")
        return {
            "prompt": raw_prompt,
            "intent": non_course_clf.intent,
            "direct_response": non_course_clf.direct_response,
            "is_course_query": False,
            "search_query": None,
            "last_course_query": anchor_query,  # Bảo toàn anchor nếu lượt sau cần kiểm tra
            "last_turn_intent": non_course_clf.intent,
            "is_curriculum_navigation": False,
            "pending_navigation": None,
            "action": None
        }


# ==========================================
# NODE 2: RETRIEVAL NODE
# ==========================================
async def retrieval_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 2: Thực hiện True Hybrid Retrieval (Dense E5 + Sparse BM25) có In-HNSW Pre-filter.
    Áp dụng Dual Retrieval with Confidence-Gated Selection (Invariant 1 - Zero Context Pollution):
    - Bước 1: Khi không phải hỏi lộ trình, ưu tiên truy xuất với raw_prompt để không làm biến dạng phân phối điểm Cross-Encoder.
    - Bước 2: Chỉ khi retrieval_res rơi vào coverage_gap hoặc is_low_confidence (dấu hiệu thiếu thực thể),
      hệ thống mới kích hoạt truy xuất dự phòng bằng search_query bổ sung mỏ neo.
    """
    retrieval_service = get_retrieval_service()
    c_svc = get_curriculum_service()
    raw_prompt = normalize_user_input(state.get("prompt", ""))
    search_query = normalize_user_input(state.get("search_query") or raw_prompt)
    anchor_query = state.get("last_course_query")
    current_video_sec = state.get("current_video_sec")
    is_curriculum_nav = bool(state.get("is_curriculum_navigation", False))
    is_cont_turn = bool(anchor_query and state.get("messages"))

    # Scoped Temporal Guard: Truy vấn mốc video bài hiện tại không được bị NavBypass/CURRICULUM_OVERVIEW chiếm quyền
    time_ref = c_svc.extract_video_time_reference(raw_prompt)
    explicit_seq = c_svc._extract_lesson_seq(raw_prompt.lower())
    if (
        time_ref is not None
        and explicit_seq is None
        and not c_svc._names_other_lesson_topic(
            raw_prompt,
            current_lesson_seq=state.get("lesson_seq"),
            preferred_course_id=state.get("course_id"),
        )
    ):
        is_curriculum_nav = False

    # Stateful Temporal Anchor Fallback cho truy vấn chỉ thị ("đoạn này", "chỗ này", ...)
    effective_video_sec = current_video_sec
    inherited_video_sec: Optional[int] = None
    missing_deictic_sec = False
    if (
        time_ref is not None
        and explicit_seq is None
        and time_ref.get("kind") == "deictic_current"
        and current_video_sec is None
    ):
        last_video_sec = state.get("last_video_sec")
        last_lesson_seq = state.get("last_lesson_seq")
        if (
            last_video_sec is not None
            and not isinstance(last_video_sec, bool)
            and last_lesson_seq == state.get("lesson_seq")
        ):
            effective_video_sec = int(last_video_sec)
            inherited_video_sec = effective_video_sec
            logger.info(
                f"[LangGraph:retrieval_node] Kế thừa neo thời gian đa lượt: "
                f"inherited_video_sec={inherited_video_sec}s (Bài {state.get('lesson_seq')})"
            )
        else:
            missing_deictic_sec = True
            logger.info(
                f"[LangGraph:retrieval_node] Thiếu current_video_sec và không có neo lượt trước "
                f"cho truy vấn deictic_current ở Bài {state.get('lesson_seq')} -> missing_deictic_sec=True"
            )

    if is_curriculum_nav:
        try:
            retrieval_res: RetrievalResult = await retrieval_service.hybrid_search(
                query_text=search_query,
                course_id=state["course_id"],
                current_lesson_seq=state["lesson_seq"],
                top_candidates=settings.DEFAULT_TOP_CANDIDATES,
                final_top_k=settings.DEFAULT_FINAL_TOP_K,
                is_curriculum_navigation=True,
                is_continuation_turn=False,
                current_video_sec=effective_video_sec,
            )
        except Exception as e:
            logger.error(f"[LangGraph:retrieval_node] Lỗi truy xuất Qdrant/RAG khi tìm lộ trình: {e}")
            retrieval_res = RetrievalResult(chunks=[], status="coverage_gap")
    else:
        router = get_intent_router()
        is_pure_followup = (
            bool(search_query and search_query != raw_prompt)
            and router.is_context_dependent(raw_prompt, anchor_query=anchor_query)
            and (not router.has_domain_entity(raw_prompt))
            and (time_ref is None)
        )
        if is_pure_followup:
            if effective_video_sec is None:
                s_time_ref = c_svc.extract_video_time_reference(search_query)
                if (
                    s_time_ref is not None
                    and s_time_ref.get("kind") == "deictic_current"
                    and state.get("last_video_sec") is not None
                    and not isinstance(state.get("last_video_sec"), bool)
                    and state.get("last_lesson_seq") == state.get("lesson_seq")
                ):
                    effective_video_sec = int(state["last_video_sec"])
                    inherited_video_sec = effective_video_sec
                    logger.info(
                        f"[LangGraph:retrieval_node] Follow-up kế thừa neo thời gian: "
                        f"inherited_video_sec={inherited_video_sec}s (Bài {state.get('lesson_seq')})"
                    )
            try:
                retrieval_res: RetrievalResult = await retrieval_service.hybrid_search(
                    query_text=search_query,
                    course_id=state["course_id"],
                    current_lesson_seq=state["lesson_seq"],
                    top_candidates=settings.DEFAULT_TOP_CANDIDATES,
                    final_top_k=settings.DEFAULT_FINAL_TOP_K,
                    is_curriculum_navigation=False,
                    is_continuation_turn=is_cont_turn,
                    current_video_sec=effective_video_sec,
                )
            except Exception as e:
                logger.error(f"[LangGraph:retrieval_node] Lỗi truy xuất Qdrant/RAG với pure follow-up: {e}")
                retrieval_res = RetrievalResult(chunks=[], status="coverage_gap")
        else:
            # Bước 1: Truy xuất với raw_prompt trước để bảo toàn phân phối Cross-Encoder
            try:
                retrieval_res: RetrievalResult = await retrieval_service.hybrid_search(
                    query_text=raw_prompt,
                    course_id=state["course_id"],
                    current_lesson_seq=state["lesson_seq"],
                    top_candidates=settings.DEFAULT_TOP_CANDIDATES,
                    final_top_k=settings.DEFAULT_FINAL_TOP_K,
                    is_curriculum_navigation=False,
                    is_continuation_turn=is_cont_turn,
                    current_video_sec=effective_video_sec,
                )
            except Exception as e:
                logger.error(f"[LangGraph:retrieval_node] Lỗi truy xuất Qdrant/RAG với raw_prompt: {e}")
                retrieval_res = RetrievalResult(chunks=[], status="coverage_gap")

            # Bước 2: Contextual Fallback nếu raw_prompt bị coverage_gap hoặc is_low_confidence và search_query != raw_prompt
            if (retrieval_res.status == "coverage_gap" or retrieval_res.is_low_confidence) and search_query != raw_prompt:
                logger.info(
                    f"[LangGraph:retrieval_node] raw_prompt thiếu thực thể ({retrieval_res.status}), "
                    f"kích hoạt Fallback với search_query: '{search_query[:45]}...'"
                )
                try:
                    fallback_res: RetrievalResult = await retrieval_service.hybrid_search(
                        query_text=search_query,
                        course_id=state["course_id"],
                        current_lesson_seq=state["lesson_seq"],
                        top_candidates=settings.DEFAULT_TOP_CANDIDATES,
                        final_top_k=settings.DEFAULT_FINAL_TOP_K,
                        is_curriculum_navigation=False,
                        is_continuation_turn=is_cont_turn,
                        current_video_sec=effective_video_sec,
                    )
                    if fallback_res.status in ("grounded", "out_of_lesson") and not fallback_res.is_low_confidence:
                        retrieval_res = fallback_res
                except Exception as fb_err:
                    logger.warning(f"[LangGraph:retrieval_node] Lỗi truy xuất Fallback Contextual: {fb_err}")

    return {
        "retrieved_chunks": retrieval_res.chunks,
        "retrieval_status": retrieval_res.status,
        "is_approximate": getattr(retrieval_res, "is_approximate", False),
        "is_low_confidence": retrieval_res.is_low_confidence,
        "target_lesson_seq": retrieval_res.target_lesson_seq,
        "future_best_chunk": getattr(retrieval_res, "future_best_chunk", None),
        "is_curriculum_navigation": is_curriculum_nav,
        "inherited_video_sec": inherited_video_sec,
        "missing_deictic_sec": missing_deictic_sec,
    }


_GLOSSARY_EXCLUDED_SECTION_HEADERS = (
    "[MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI]",
    "[DANH MỤC BÀI HỌC THẬT LIÊN QUAN TRONG GIÁO TRÌNH]",
    "[DANH MỤC LỘ TRÌNH BÀI HỌC BẢO CHỨNG TỪ GIÁO TRÌNH]",
    "[CÁC LỰA CHỌN BÀI HỌC PHÙ HỢP TRONG GIÁO TRÌNH]",
)


def _extract_glossary_lookup_text(user_message_content: str, raw_prompt: str) -> str:
    """
    Trích xuất văn bản phục vụ tra cứu từ điển học thuật (Academic Glossary):
    - Giữ nguyên câu hỏi của học viên (`raw_prompt`) và ngữ cảnh bài giảng thực tế
      (`[NGỮ CẢNH BÀI GIẢNG...]`, `[HỌC LIỆU BÀI GIẢNG...]`, `[MÃ NGUỒN BÀI GIẢNG...]`).
    - Loại trừ các khối mục lục phụ trợ / danh mục lộ trình (`[MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI]`,
      `[DANH MỤC BÀI HỌC...]`, `[CÁC LỰA CHỌN BÀI HỌC...]`) để tránh tiêm nhầm thuật ngữ của các mốc
      phân đoạn khác hoặc bài học khác vào prompt của mô hình 7B.
    """
    if not user_message_content:
        return raw_prompt or ""
    kept_lines: List[str] = []
    skipping_section = False
    for line in user_message_content.splitlines():
        stripped = line.strip()
        if any(stripped.startswith(hdr) for hdr in _GLOSSARY_EXCLUDED_SECTION_HEADERS):
            skipping_section = True
            continue
        if skipping_section:
            if stripped.startswith("[") and stripped.endswith(("]", "]:")):
                skipping_section = False
            else:
                continue
        kept_lines.append(line)
    cleaned_body = "\n".join(kept_lines).strip()
    if raw_prompt:
        return f"{cleaned_body} {raw_prompt}".strip()
    return cleaned_body


def _build_ambiguous_candidates_block(ambiguous_res: Dict[str, Any]) -> str:
    """Định dạng danh sách lựa chọn bài học thật từ giáo trình khi phát hiện truy vấn mơ hồ/đa chủ đề."""
    reason = ambiguous_res.get("reason", "")
    cands = [c for c in ambiguous_res.get("candidates", []) if c.get("seq") is not None]
    reason_note = (
        f"Học viên đang hỏi lựa chọn giữa {len(cands)} chủ đề khác nhau (BẮT BUỘC phải giới thiệu đầy đủ cả {len(cands)} bài học tương ứng bên dưới, tuyệt đối KHÔNG chỉ nêu 1 bài)."
        if reason == "multi_topic_disjunction"
        else "Chủ đề này xuất hiện ở nhiều bài học khác nhau trong giáo trình."
    )
    cand_lines: List[str] = []
    for idx, c in enumerate(cands, start=1):
        branch_q = str(c.get("branch_query", "") or "").strip()
        if reason == "multi_topic_disjunction" and branch_q:
            cand_lines.append(
                f'{idx}. Chủ đề "{branch_q}" -> Bài {c.get("seq")} (khóa {c.get("course_id")}): {c.get("title")}'
            )
        else:
            cand_lines.append(
                f"{idx}. Bài {c.get('seq')} (khóa {c.get('course_id')}): {c.get('title')}"
            )
    return (
        "\n[CÁC LỰA CHỌN BÀI HỌC PHÙ HỢP TRONG GIÁO TRÌNH]\n"
        f"- Ghi chú phân giải: {reason_note}\n"
        + "\n".join(cand_lines)
        + f"\n- CHỈ THỊ ĐỐI THOẠI: BẮT BUỘC phải liệt kê ĐẦY ĐỦ CẢ {len(cands)} bài học ở trên "
          "(đúng số Bài, khóa học và tiêu đề cho từng chủ đề; tuyệt đối KHÔNG chọn 1 bỏ 1, KHÔNG mở đầu bằng \"Chào bạn!\" hay \"Theo đoạn video...\") "
          "và kết thúc câu trả lời bằng đúng 1 câu hỏi định hướng có dấu `?` để học viên chọn muốn tập trung "
          "vào bài học hoặc chủ đề nào trước (KHÔNG viết nhãn `**Câu hỏi gợi mở:**` hay câu kết `nhé!`). "
          "KHÔNG tự đoán chọn một bài duy nhất và KHÔNG tự bịa thêm số bài học ngoài danh sách.\n"
    )


_RELATIVE_SEGMENT_CUES = (
    "đoạn đầu", "đoạn giữa", "đoạn cuối",
    "phần đầu", "phần giữa", "phần cuối",
    "khúc đầu", "khúc giữa", "khúc cuối",
)


def _build_lesson_chapters_block(
    c_svc: Any,
    lesson_seq: int,
    course_id: str,
    *,
    focus_sec: Optional[int] = None,
) -> str:
    """Nạp mục lục phân đoạn video bài học hiện tại từ CurriculumService."""
    chapters = c_svc.get_lesson_chapters(lesson_seq, course_id)
    if not chapters:
        return ""
    active_chapters = chapters
    if focus_sec is not None and not isinstance(focus_sec, bool):
        f_sec = int(focus_sec)
        nearby = [
            ch for ch in chapters
            if ch.get("sec") is not None and abs(int(ch["sec"]) - f_sec) <= 600
        ]
        if nearby:
            active_chapters = nearby
    chapter_lines = [
        f"- Mốc {ch.get('label', '00:00')}: {ch.get('summary', '')}"
        for ch in active_chapters
        if ch.get("summary")
    ]
    if not chapter_lines:
        return ""
    return (
        "\n\n[MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI]\n"
        + "\n".join(chapter_lines)
        + "\n(Lưu ý: Mục lục trên chỉ dùng để nắm bố cục toàn bài hoặc hỏi lại khi thiếu mốc giây; "
          "nếu học viên hỏi một mốc/đoạn cụ thể thì CHỈ giải thích nội dung trong [NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC], "
          "TUYỆT ĐỐI KHÔNG trộn nội dung từ các mốc khác trong mục lục và chỉ gắn thẻ <timestamp sec=\"...\"> của ngữ cảnh chính.)"
    )


# ==========================================
# NODE 3: CRAG GRADER & PROMPT PACKAGER NODE
# ==========================================
async def crag_grader_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 3: Trích xuất mốc thời gian video, nguồn trích dẫn và đóng gói Socratic Prompt.
    """
    chunks = state.get("retrieved_chunks", [])
    retrieval_status = state.get("retrieval_status", "coverage_gap")
    is_low_confidence = state.get("is_low_confidence", False)
    target_lesson_seq = state.get("target_lesson_seq")
    raw_prompt = normalize_user_input(state.get("prompt", ""))
    search_query = normalize_user_input(state["search_query"]) if state.get("search_query") else None

    c_svc = get_curriculum_service()
    time_ref_for_link = c_svc.extract_video_time_reference(raw_prompt)
    is_anchored_deictic_current = (
        time_ref_for_link is not None
        and time_ref_for_link.get("kind") == "deictic_current"
        and state.get("current_video_sec") is not None
    )

    # Xác định dòng liên kết ngữ cảnh hội thoại cho Anaphora Resolution
    is_code_solicitation = get_intent_router().is_code_solicitation(raw_prompt)

    context_linked_line = ""
    if (
        search_query
        and search_query != raw_prompt
        and not is_code_solicitation
        and not is_anchored_deictic_current
    ):
        context_linked_line = f"\n[NGỮ CẢNH HỘI THOẠI LIÊN KẾT]: {search_query}"

    suggested_timestamps: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []
    has_approximate = bool(state.get("is_approximate", False))
    new_pending_nav: Optional[Dict[str, Any]] = None

    is_curriculum_nav = bool(state.get("is_curriculum_navigation", False))
    is_overview_q = (time_ref_for_link is None) and c_svc.is_overview_query(raw_prompt)
    norm_for_split = normalize_user_input(raw_prompt, lowercase=True, preserve_newlines=False)
    has_disjunction = len(c_svc._split_disjunction_branches(norm_for_split)) >= 2

    ambiguous_res: Dict[str, Any] = {
        "is_ambiguous": False,
        "reason": "",
        "branches": [],
        "candidates": [],
    }
    if retrieval_status == "out_of_lesson" or is_curriculum_nav or is_overview_q or has_disjunction:
        try:
            ambiguous_res = c_svc.find_ambiguous_candidates(
                raw_prompt,
                current_lesson_seq=state.get("lesson_seq"),
                preferred_course_id=state.get("course_id"),
            )
        except Exception as amb_err:
            logger.debug(f"[LangGraph:crag_grader_node] Lỗi find_ambiguous_candidates: {amb_err}")

    is_ambiguous = bool(ambiguous_res.get("is_ambiguous") and ambiguous_res.get("candidates"))
    is_disjunction_ambiguous = is_ambiguous and ambiguous_res.get("reason") == "multi_topic_disjunction"
    is_ambiguous_grounded_nav = bool(
        retrieval_status == "grounded"
        and is_disjunction_ambiguous
    )
    missing_deictic_sec = bool(state.get("missing_deictic_sec", False))
    cur_seq_for_deictic = state.get("lesson_seq")
    deictic_chapters_block = (
        _build_lesson_chapters_block(c_svc, cur_seq_for_deictic, state.get("course_id"))
        if (missing_deictic_sec and cur_seq_for_deictic is not None)
        else ""
    )
    if missing_deictic_sec:
        has_approximate = False

    if retrieval_status == "grounded" and not is_ambiguous_grounded_nav and not missing_deictic_sec:
        for chunk in chunks:
            if chunk.get("is_approximate"):
                has_approximate = True

            if chunk.get("content_type") == "video_transcript" and chunk.get("start_sec") is not None:
                suggested_timestamps.append({
                    "sec": chunk["start_sec"],
                    "label": chunk.get("start_label", f"{chunk['start_sec']//60:02d}:{chunk['start_sec']%60:02d}"),
                    "title": chunk.get("video_title", "Đoạn video bài giảng liên quan"),
                    "lesson_seq": chunk.get("lesson_seq")
                })
            elif chunk.get("content_type") == "code_ast" and chunk.get("approx_video_sec") is not None:
                v_sec = int(chunk["approx_video_sec"])
                suggested_timestamps.append({
                    "sec": v_sec,
                    "label": f"{v_sec//60:02d}:{v_sec%60:02d}",
                    "title": f"Bài giảng giải thích cú pháp [{chunk.get('code_scope', 'Code AST')}]",
                    "lesson_seq": chunk.get("lesson_seq")
                })

            sources.append({
                "id": chunk.get("id"),
                "content_type": chunk.get("content_type"),
                "confidence_pct": chunk.get("confidence_pct", 0.0),
                "confidence_score": chunk.get("confidence_score", 0.0),
                "is_approximate": chunk.get("is_approximate", False),
                "lesson_id": chunk.get("lesson_id"),
                "lesson_seq": chunk.get("lesson_seq"),
                "start_sec": chunk.get("start_sec") if chunk.get("start_sec") is not None else chunk.get("approx_video_sec"),
                "start_label": chunk.get("start_label") or (
                    f"{int(chunk['approx_video_sec'])//60:02d}:{int(chunk['approx_video_sec'])%60:02d}"
                    if chunk.get("approx_video_sec") is not None else None
                ),
                "timestamp_tag": chunk.get("timestamp_tag"),
                "file_path": chunk.get("file_path"),
                "code_scope": chunk.get("code_scope"),
                "context_code": chunk.get("context_code"),
                "approx_video_sec": chunk.get("approx_video_sec")
            })

    # Đóng gói Prompt tương ứng theo 3 trạng thái sư phạm
    if retrieval_status == "grounded":
        if is_ambiguous_grounded_nav:
            active_system_prompt = CURRICULUM_OVERVIEW_PROMPT
            ambiguous_block = _build_ambiguous_candidates_block(ambiguous_res)
            user_message_content = f"""[CÂU HỎI CỦA HỌC VIÊN]
{raw_prompt}{context_linked_line}

[TIẾN ĐỘ BÀI HỌC]
- Khóa học hiện tại: {state['course_id']}
- Bài học hiện tại của học viên: Bài {state['lesson_seq']}
{ambiguous_block}"""
        elif missing_deictic_sec and deictic_chapters_block:
            active_system_prompt = SOCRATIC_GROUNDED_PROMPT
            user_message_content = f"""[CÂU HỎI THẮC MẮC CỦA HỌC VIÊN]
{raw_prompt}{context_linked_line}{deictic_chapters_block}

[LƯU Ý LÀM RÕ MỐC THỜI GIAN VIDEO]: Trình phát hiện chưa cung cấp mốc giây đang xem và chưa có neo thời gian từ lượt trước. Hãy dựa vào [MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI] ở trên để hỏi lại học viên đang theo dõi mốc thời gian hoặc phân đoạn nào (kết thúc bằng dấu `?`), tuyệt đối KHÔNG tự đoán mốc 00:00 và KHÔNG tự giải thích một đoạn bất kỳ."""
        else:
            active_system_prompt = SOCRATIC_GROUNDED_PROMPT
            context_block = _format_context_block(chunks)
            caution_notice = "\n[LƯU Ý: Một số tài liệu có độ tin cậy tham khảo, hãy định hướng học viên thận trọng.]\n" if is_low_confidence else ""
            inherited_video_sec = state.get("inherited_video_sec")
            inherited_notice = ""
            if inherited_video_sec is not None and not isinstance(inherited_video_sec, bool):
                inh_sec = int(inherited_video_sec)
                inh_lbl = f"{inh_sec // 60:02d}:{inh_sec % 60:02d}"
                inherited_notice = (
                    f"\n[NEO THỜI GIAN ĐA LƯỢT]: Học viên không gửi mốc phát hiện tại; hệ thống "
                    f"đang bám theo mốc video vừa thảo luận ở lượt trước ({inh_lbl}, giây {inh_sec}).\n"
                )
            curriculum_nav_anchor = ""
            if is_curriculum_nav:
                match_res = c_svc.find_lesson_for_query(
                    raw_prompt,
                    current_lesson_seq=state.get("lesson_seq"),
                    preferred_course_id=state.get("course_id")
                )
                if match_res:
                    matched_lesson, matched_title = match_res
                    m_seq = matched_lesson.get("seq")
                    m_title = matched_lesson.get("title") or matched_title
                    if m_seq is not None and m_title:
                        curriculum_nav_anchor = f"[THÔNG TIN BÀI HỌC KHỚP GIÁO TRÌNH]: Bài {m_seq} - {m_title}\n\n"
            user_message_content = f"""{curriculum_nav_anchor}[CÂU HỎI THẮC MẮC CỦA HỌC VIÊN]
{raw_prompt}{context_linked_line}{inherited_notice}
{caution_notice}
{context_block}"""

            # Video Chapters Injection (khi grounded & hỏi vị trí/phân đoạn/tổng quan video bài hiện tại)
            lower_prompt = raw_prompt.lower()
            section_markers = tuple(getattr(c_svc, "_crag_section_markers", None) or (
                "mục lục", "phân đoạn", "các phần", "mấy phần", "chia thành",
                "phút bao nhiêu", "phút mấy", "giây bao nhiêu", "giây mấy",
                "đoạn nào", "phần nào", "khúc nào",
                "tóm tắt bài", "tóm tắt video", "nội dung video", "cấu trúc bài",
                "timeline", "chapter",
            ))
            has_section_marker = any(m in lower_prompt for m in section_markers) or c_svc.is_video_section_seeking_query(raw_prompt)
            has_relative_segment_cue = any(cue in lower_prompt for cue in _RELATIVE_SEGMENT_CUES)
            time_ref = c_svc.extract_video_time_reference(raw_prompt)
            is_curr_lesson_chunks = (
                not chunks
                or all(ch.get("lesson_seq") == state.get("lesson_seq") for ch in chunks)
            )
            if (
                is_overview_q
                or (is_curriculum_nav and is_curr_lesson_chunks)
                or has_section_marker
                or has_relative_segment_cue
                or (time_ref is not None and not chunks)
            ):
                cur_seq = state.get("lesson_seq")
                focus_sec_val: Optional[int] = None
                if (
                    not is_overview_q
                    and not missing_deictic_sec
                    and not has_section_marker
                    and not (is_curriculum_nav and is_curr_lesson_chunks)
                ):
                    if chunks and chunks[0].get("start_sec") is not None:
                        focus_sec_val = int(chunks[0]["start_sec"])
                    elif time_ref and time_ref.get("target_sec") is not None:
                        focus_sec_val = int(time_ref["target_sec"])
                chapters_block = (
                    _build_lesson_chapters_block(
                        c_svc,
                        cur_seq,
                        state.get("course_id"),
                        focus_sec=focus_sec_val,
                    )
                    if cur_seq is not None
                    else ""
                )
                if chapters_block:
                    user_message_content += chapters_block

            if is_curriculum_nav:
                nav_related_entries: List[str] = []
                nav_seen = set()
                try:
                    sem_hits = c_svc.semantic_search_lessons(raw_prompt, top_k=6, min_similarity=0.78)
                    for _sc, les in sem_hits:
                        l_course = les.get("course_id", state.get("course_id"))
                        l_seq = les.get("seq")
                        if l_seq is None or (l_course, l_seq) in nav_seen:
                            continue
                        nav_seen.add((l_course, l_seq))
                        nav_related_entries.append(
                            f"- Bài {l_seq} (khóa {l_course}): {les.get('title', '')}".rstrip()
                        )
                        if len(nav_related_entries) >= 6:
                            break
                except Exception:
                    pass
                if nav_related_entries:
                    user_message_content += (
                        "\n\n[DANH MỤC BÀI HỌC THẬT LIÊN QUAN TRONG GIÁO TRÌNH]\n"
                        + "\n".join(nav_related_entries)
                        + "\n(Lưu ý: Chỉ giới thiệu các Bài học có tên trong danh mục thật ở trên, tuyệt đối không tự bịa số bài học.)"
                    )

            if is_ambiguous and (is_curriculum_nav or is_overview_q):
                user_message_content += "\n" + _build_ambiguous_candidates_block(ambiguous_res)

    elif retrieval_status == "out_of_lesson":
        f_chunk = state.get("future_best_chunk")
        future_ts_info = ""
        future_learning_text = ""
        new_pending_nav = None

        target_course = (f_chunk or {}).get("course_id") or state["course_id"]

        if is_ambiguous:
            active_system_prompt = CURRICULUM_OVERVIEW_PROMPT if is_curriculum_nav else OUT_OF_LESSON_PROMPT
            cands_list = [c for c in ambiguous_res.get("candidates", []) if c.get("seq") is not None]
            target_desc = (
                f"Gồm đủ {len(cands_list)} lựa chọn bài học bên dưới (BẮT BUỘC phải nêu đầy đủ tất cả {len(cands_list)} bài học, không bỏ sót bài nào)"
            )
            future_learning_text = _build_ambiguous_candidates_block(ambiguous_res)

        elif is_curriculum_nav:
            # Hạng mục A & B (Mục 2.2 - Nhịp 1B): Chặn bơm raw future chunk khi điều hướng lộ trình
            active_system_prompt = CURRICULUM_OVERVIEW_PROMPT
            target_desc = f"Bài {target_lesson_seq} (khóa {target_course})" if target_lesson_seq else "các bài học sau"
            match_res = c_svc.find_lesson_for_query(
                raw_prompt,
                current_lesson_seq=state["lesson_seq"],
                preferred_course_id=state["course_id"]
            )
            target_lesson_dict = match_res[0] if match_res else None
            roadmap_bullets = []
            if target_lesson_dict:
                t_course = target_lesson_dict.get("course_id", target_course)
                target_course = t_course
                t_seq = target_lesson_dict.get("seq", target_lesson_seq)
                target_desc = f"Bài {t_seq} (khóa {t_course}): {target_lesson_dict.get('title')}"
                course_lessons = [
                    les for les in c_svc._all_lessons
                    if les.get("course_id") == t_course
                ]
                t_idx = next(
                    (idx for idx, les in enumerate(course_lessons) if les.get("seq") == t_seq),
                    0,
                )
                win_start = max(0, t_idx - 2)
                win_end = min(len(course_lessons), win_start + 6)
                win_start = max(0, win_end - 6)
                roadmap_bullets = [
                    f"- Bài {les.get('seq')} (khóa {t_course}): {les.get('title')}"
                    for les in course_lessons[win_start:win_end]
                ]

            roadmap_str = "\n".join(roadmap_bullets) if roadmap_bullets else f"- {target_desc}"
            future_learning_text = f"\n[DANH MỤC LỘ TRÌNH BÀI HỌC BẢO CHỨNG TỪ GIÁO TRÌNH]\n{roadmap_str}\n"

        else:
            active_system_prompt = OUT_OF_LESSON_PROMPT
            target_les = None
            if target_lesson_seq is not None:
                chunk_course = (f_chunk or {}).get("course_id")
                if chunk_course:
                    target_les = next(
                        (
                            les for les in c_svc._all_lessons
                            if les.get("seq") == target_lesson_seq and les.get("course_id") == chunk_course
                        ),
                        None,
                    )
                if not target_les:
                    target_les = c_svc.get_lesson_by_seq(target_lesson_seq)

            if target_les:
                target_course = target_les.get("course_id", target_course)
                t_title = target_les.get("title", "")
                target_desc = (
                    f"Bài {target_lesson_seq} (khóa {target_course}): {t_title}"
                    if t_title
                    else f"Bài {target_lesson_seq} (khóa {target_course})"
                )
            else:
                target_desc = (
                    f"Bài {target_lesson_seq} (khóa {target_course})"
                    if target_lesson_seq
                    else "các bài học sau"
                )

            if f_chunk:
                c_type = f_chunk.get("content_type", "video_transcript")
                if c_type == "code_ast":
                    scope = f_chunk.get("code_scope", "Mã nguồn")
                    code_raw = (f_chunk.get("context_code") or f_chunk.get("raw_text", "")).strip()
                    sanitized_c = _sanitize_context_code_ast(code_raw)
                    # Chỉ trích xuất chữ ký hàm / khai báo cấu trúc tối đa <= 5 dòng (loại bỏ chi tiết cài đặt và main)
                    c_lines = [l for l in sanitized_c.splitlines() if l.strip()]
                    short_c = "\n".join(c_lines[:5])
                    if short_c:
                        future_learning_text = f"\n[HỌC LIỆU BÀI GIẢNG TƯƠNG LAI ĐỂ GIẢI THÍCH BẢN CHẤT]\n// Trích đoạn khai báo logic Bài {target_lesson_seq} ({scope}):\n```cpp\n{short_c}\n```\n"
                else:
                    raw_t = (f_chunk.get("raw_text", "")).strip()
                    raw_t = " ".join(raw_t.split())
                    tag = f_chunk.get("timestamp_tag") or (f"mốc {f_chunk.get('start_label')}" if f_chunk.get("start_label") else "")
                    tag_part = f" ({tag})" if tag else ""
                    if len(raw_t) > 400:
                        raw_t = raw_t[:400].rstrip() + "..."
                    if raw_t:
                        future_learning_text = f"\n[HỌC LIỆU BÀI GIẢNG TƯƠNG LAI ĐỂ GIẢI THÍCH BẢN CHẤT]\nTrích đoạn Bài {target_lesson_seq}{tag_part}: {raw_t}\n"

            # Bơm danh sách các bài học THẬT liên quan nhất từ giáo trình để chặn LLM 7B tự bịa số bài mới
            related_entries: List[str] = []
            seen_keys = set()
            if target_les:
                les_course = target_les.get("course_id", target_course)
                les_seq = target_les.get("seq", target_lesson_seq)
                seen_keys.add((les_course, les_seq))
                related_entries.append(
                    f"- Bài {les_seq} (khóa {les_course}): {target_les.get('title', '')}".rstrip()
                )
            try:
                sem_hits = c_svc.semantic_search_lessons(raw_prompt, top_k=5, min_similarity=0.78)
                for _score, les in sem_hits:
                    les_course = les.get("course_id", state["course_id"])
                    les_seq = les.get("seq")
                    if (les_course, les_seq) in seen_keys:
                        continue
                    seen_keys.add((les_course, les_seq))
                    related_entries.append(
                        f"- Bài {les_seq} (khóa {les_course}): {les.get('title', '')}".rstrip()
                    )
                    if len(related_entries) >= 5:
                        break
            except Exception:
                pass

            if related_entries:
                future_learning_text += (
                    "\n[DANH MỤC BÀI HỌC THẬT LIÊN QUAN TRONG GIÁO TRÌNH]\n"
                    + "\n".join(related_entries)
                    + "\n"
                )

        new_offered_lessons: List[Dict[str, Any]] = []
        if is_ambiguous and ambiguous_res.get("candidates"):
            for cand in ambiguous_res.get("candidates", []):
                c_seq = cand.get("seq")
                if c_seq is None:
                    continue
                c_ts = c_svc.get_lesson_timestamps(int(c_seq))
                c_sec = int(c_ts[0]["sec"]) if c_ts else 0
                c_lbl = c_ts[0]["label"] if c_ts else "00:00"
                new_offered_lessons.append({
                    "course_id": cand.get("course_id", target_course),
                    "seq": int(c_seq),
                    "title": cand.get("title", f"Bài {c_seq}"),
                    "sec": c_sec,
                    "label": c_lbl,
                })
        elif not is_ambiguous and target_lesson_seq is not None:
            if f_chunk and f_chunk.get("start_sec") is not None:
                f_sec = int(f_chunk["start_sec"])
                f_lbl = f_chunk.get("start_label", f"{f_sec//60:02d}:{f_sec%60:02d}")
            else:
                ts_fallback = c_svc.get_lesson_timestamps(int(target_lesson_seq))
                f_sec = int(ts_fallback[0]["sec"]) if ts_fallback else 0
                f_lbl = ts_fallback[0]["label"] if ts_fallback else "00:00"
            t_les_obj = c_svc.get_lesson_by_seq(int(target_lesson_seq))
            t_title_nav = (t_les_obj or {}).get("title") or (f_chunk or {}).get("video_title", f"Bài {target_lesson_seq}")
            t_course_nav = (t_les_obj or {}).get("course_id") or target_course
            if f_chunk and f_chunk.get("start_sec") is not None:
                suggested_timestamps.append({
                    "sec": f_sec,
                    "label": f_lbl,
                    "title": f_chunk.get("video_title", f"Bài {target_lesson_seq}"),
                    "lesson_seq": target_lesson_seq
                })
                future_ts_info = (
                    f"\n\n[MỐC VIDEO BÀI GIẢNG TƯƠNG LAI]\n"
                    f"- Bài học giảng dạy: Bài {target_lesson_seq} (khóa {t_course_nav})\n"
                    f"- Mốc thời gian: {f_lbl} (giây {f_sec})\n"
                    f"- Thẻ click-to-seek bắt buộc chèn: <timestamp sec=\"{f_sec}\" lesson=\"{target_lesson_seq}\">{f_lbl}</timestamp>\n"
                    f"- CHỈ THỊ ĐÀM THOẠI: Kết thúc câu trả lời bằng câu hỏi gợi mở: "
                    f"\"Bạn có muốn mình chuyển sang Bài {target_lesson_seq} và mở ngay đoạn video này cho bạn không?\""
                )
            new_pending_nav = {
                "lesson_seq": int(target_lesson_seq),
                "sec": f_sec,
                "label": f_lbl,
                "title": t_title_nav,
            }
            new_offered_lessons = [{
                "course_id": t_course_nav,
                "seq": int(target_lesson_seq),
                "title": t_title_nav,
                "sec": f_sec,
                "label": f_lbl,
            }]

        user_message_content = f"""[CÂU HỎI CỦA HỌC VIÊN]
{raw_prompt}{context_linked_line}

[TIẾN ĐỘ BÀI HỌC]
- Khóa học hiện tại: {state['course_id']}
- Bài học hiện tại của học viên: Bài {state['lesson_seq']}
- Bài học giảng dạy nội dung này: {target_desc}{future_ts_info}
{future_learning_text}"""

    else:  # coverage_gap
        missing_deictic_sec = bool(state.get("missing_deictic_sec", False))
        cur_seq = state.get("lesson_seq")
        chapters_block = (
            _build_lesson_chapters_block(c_svc, cur_seq, state.get("course_id"))
            if missing_deictic_sec and cur_seq is not None
            else ""
        )
        if is_ambiguous and (is_curriculum_nav or ambiguous_res.get("reason") == "multi_topic_disjunction"):
            active_system_prompt = CURRICULUM_OVERVIEW_PROMPT
            ambiguous_block = _build_ambiguous_candidates_block(ambiguous_res)
            user_message_content = f"""[CÂU HỎI CỦA HỌC VIÊN]
{raw_prompt}{context_linked_line}

[TIẾN ĐỘ BÀI HỌC]
- Khóa học hiện tại: {state['course_id']}
- Bài học hiện tại của học viên: Bài {state['lesson_seq']}
{ambiguous_block}"""
        elif missing_deictic_sec and chapters_block:
            active_system_prompt = SOCRATIC_GROUNDED_PROMPT
            user_message_content = f"""[CÂU HỎI THẮC MẮC CỦA HỌC VIÊN]
{raw_prompt}{context_linked_line}{chapters_block}

[LƯU Ý LÀM RÕ MỐC THỜI GIAN VIDEO]: Trình phát hiện chưa cung cấp mốc giây đang xem và chưa có neo thời gian từ lượt trước. Hãy dựa vào [MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI] ở trên để hỏi lại học viên đang hỏi mốc thời gian hoặc phân đoạn nào, tuyệt đối KHÔNG tự đoán mốc 00:00."""
        else:
            active_system_prompt = COVERAGE_GAP_PROMPT
            user_message_content = f"""[CÂU HỎI CỦA HỌC VIÊN]
{raw_prompt}{context_linked_line}

[THÔNG TIN PHẠM VI KHÓA HỌC]
- Khóa học: Lập trình C++ ({state['course_id']}), đang ở Bài {state['lesson_seq']}.
- Câu hỏi của học viên không nằm trong giáo trình bài giảng hoặc là chủ đề ngoài lề."""

    current_lesson_seq = state.get("lesson_seq")
    prev_last_video_sec = state.get("last_video_sec")
    prev_last_lesson_seq = state.get("last_lesson_seq")

    new_last_video_sec = prev_last_video_sec
    new_last_lesson_seq = prev_last_lesson_seq

    extracted_sec: Optional[int] = None
    if retrieval_status == "grounded" and suggested_timestamps and not missing_deictic_sec:
        raw_sec = suggested_timestamps[0].get("sec")
        if isinstance(raw_sec, (int, float)) and not isinstance(raw_sec, bool):
            extracted_sec = int(raw_sec)

    if missing_deictic_sec:
        new_last_video_sec = None
        new_last_lesson_seq = current_lesson_seq
    elif extracted_sec is not None:
        new_last_video_sec = extracted_sec
        new_last_lesson_seq = current_lesson_seq
    elif current_lesson_seq != prev_last_lesson_seq:
        new_last_video_sec = None
        new_last_lesson_seq = current_lesson_seq

    return {
        "prompt": raw_prompt,
        "is_overview_query": is_overview_q,
        "is_approximate": has_approximate,
        "suggested_timestamps": suggested_timestamps,
        "sources": sources,
        "system_prompt": active_system_prompt,
        "user_message_content": user_message_content,
        "pending_navigation": new_pending_nav,
        "last_offered_lessons": new_offered_lessons if retrieval_status == "out_of_lesson" else (
            [
                {
                    "course_id": cand.get("course_id", state.get("course_id")),
                    "seq": int(cand.get("seq")),
                    "title": cand.get("title", ""),
                    "sec": 0,
                    "label": "00:00",
                }
                for cand in ambiguous_res.get("candidates", [])
                if cand.get("seq") is not None
            ]
            if (is_ambiguous and ambiguous_res.get("candidates"))
            else []
        ),
        "last_video_sec": new_last_video_sec,
        "last_lesson_seq": new_last_lesson_seq,
        "prev_video_sec": prev_last_video_sec,
        "prev_lesson_seq": prev_last_lesson_seq,
    }


def _extract_first_timestamp_sec(text: str) -> Optional[int]:
    """Trích xuất giá trị số giây đầu tiên từ thẻ <timestamp sec=\"...\"> (Zero Regex)."""
    if not text or "<timestamp" not in text.lower():
        return None
    low = text.lower()
    pos = 0
    while True:
        t_idx = low.find("<timestamp", pos)
        if t_idx == -1:
            return None
        gt_idx = low.find(">", t_idx)
        if gt_idx == -1:
            return None
        open_tag = text[t_idx:gt_idx + 1]
        sec_idx = open_tag.lower().find("sec=")
        if sec_idx != -1:
            val_part = open_tag[sec_idx + 4:].lstrip(" \"'")
            digits: List[str] = []
            for ch in val_part:
                if ch.isdigit():
                    digits.append(ch)
                else:
                    break
            if digits:
                return int("".join(digits))
        pos = gt_idx + 1


def _strip_timestamp_tags_plain(text: str) -> str:
    """Loại bỏ hoàn toàn các phần tử <timestamp ...>...</timestamp> bằng quét chuỗi thuần túy (Zero Regex), bảo toàn 100% toán tử < > của C++."""
    if not text or "<timestamp" not in text.lower():
        return text
    work = text
    while True:
        low = work.lower()
        start_idx = low.find("<timestamp")
        if start_idx == -1:
            break
        close_idx = low.find("</timestamp>", start_idx)
        if close_idx != -1:
            work = work[:start_idx] + work[close_idx + len("</timestamp>"):]
        else:
            gt_idx = work.find(">", start_idx)
            if gt_idx != -1:
                work = work[:start_idx] + work[gt_idx + 1:]
            else:
                work = work[:start_idx]
                break
    return work


def _strip_leaked_video_source_brackets(line: str) -> str:
    """Loại bỏ nhãn nguồn dạng ngoặc vuông '[Video Bài ...]' bị rò rỉ trong câu trả lời cũ (Zero Regex)."""
    if "[video bài" not in line.lower():
        return line
    work = line
    while True:
        low = work.lower()
        b_start = low.find("[video bài")
        if b_start == -1:
            break
        b_end = work.find("]", b_start)
        if b_end == -1:
            break
        cut_end = b_end + 1
        if cut_end < len(work) and work[cut_end] == ":":
            cut_end += 1
        while cut_end < len(work) and work[cut_end] == " ":
            cut_end += 1
        work = work[:b_start] + work[cut_end:]
    return work


_OPENING_GREETING_PREFIXES = (
    "xin chào các bạn",
    "xin chào bạn",
    "xin chào em",
    "xin chào",
    "chào các bạn",
    "chào bạn",
    "chào em",
    "hello bạn",
    "hi bạn",
)

_OPENING_VIDEO_BOILERPLATE_PREFIXES = (
    "theo đoạn video bài giảng này",
    "theo đoạn video bài giảng",
    "theo đoạn video này",
    "theo đoạn video trên",
    "theo đoạn video",
    "theo video bài giảng này",
    "theo video bài giảng",
    "theo nội dung đoạn video",
    "theo nội dung video",
    "theo như đoạn video",
    "theo như trong video",
    "theo trong đoạn video",
    "theo trong video",
    "trong đoạn video bài giảng này",
    "trong đoạn video này",
    "trong đoạn video trên",
    "trong đoạn video",
    "dựa trên đoạn video",
    "dựa theo đoạn video",
    "dựa vào đoạn video",
)

_DEFAULT_CLOSING_FILLER_PREFIXES = (
    "hy vọng thông tin",
    "hy vọng giải thích",
    "hy vọng câu trả lời",
    "hy vọng những thông tin",
    "hy vọng điều này",
    "hy vọng phần giải thích",
    "hy vọng gợi ý",
    "hi vọng thông tin",
    "hi vọng giải thích",
    "nếu còn thắc mắc",
    "nếu bạn còn thắc mắc",
    "nếu em còn thắc mắc",
    "nếu có thắc mắc",
    "nếu bạn có thắc mắc",
    "nếu em có thắc mắc",
    "nếu còn câu hỏi",
    "nếu bạn còn câu hỏi",
    "nếu có câu hỏi",
    "nếu bạn có câu hỏi",
    "nếu cần giải thích thêm",
    "nếu bạn cần giải thích thêm",
    "bạn có câu hỏi gì",
    "bạn có thêm câu hỏi",
    "bạn còn câu hỏi",
    "bạn còn thắc mắc gì",
    "bạn đã hiểu",
    "bạn hiểu được",
    "chúc bạn học tốt",
    "chúc em học tốt",
    "chúc bạn thực hành tốt",
    "chúc bạn thành công",
    "hãy thử áp dụng những kiến thức này",
    "học viên hãy chọn bài học phù hợp nhất với nhu cầu",
    "hãy hỏi nhé",
    "cứ hỏi nhé",
    "hãy cho tôi biết nhé",
    "hãy gửi cho tôi nhé",
)


def _get_closing_filler_prefixes() -> tuple:
    try:
        manifest_closers = get_intent_router()._manifest_data.get("forbidden_closing_prefixes")
        if isinstance(manifest_closers, list) and manifest_closers:
            return tuple(str(x).strip().lower() for x in manifest_closers if str(x).strip())
    except Exception:
        pass
    return _DEFAULT_CLOSING_FILLER_PREFIXES


_CLOSING_FILLER_PREFIXES = _get_closing_filler_prefixes()


def _is_analogy_verification_query(prompt: str) -> bool:
    """
    Kiểm định 2 khe (Comparison Marker + Verification Tail) trên ranh giới token (Zero Regex)
    để nhận diện câu hỏi học viên mượn ẩn dụ đời sống / xác nhận đúng-sai.
    """
    if not prompt:
        return False
    try:
        slot_cfg = get_intent_router()._manifest_data.get("analogy_verification_2slot", {})
    except Exception:
        slot_cfg = {}
    comp_markers = slot_cfg.get("comparison_markers") or ("giống như", "như là", "tức là", "hiểu là", "ví von")
    tail_markers = slot_cfg.get("verification_tail_markers") or ("có đúng không", "có đúng k", "đúng không", "đúng k", "phải không", "phải k")
    alpha_clean = " ".join("".join(c if c.isalnum() else " " for c in prompt.lower()).split())
    padded = f" {alpha_clean} "
    has_comp = any(
        f" {m_clean} " in padded
        for m in comp_markers
        for m_clean in [" ".join("".join(c if c.isalnum() else " " for c in str(m).lower()).split())]
        if m_clean
    )
    if not has_comp:
        return False
    return any(
        f" {t_clean} " in padded
        for t in tail_markers
        for t_clean in [" ".join("".join(c if c.isalnum() else " " for c in str(t).lower()).split())]
        if t_clean
    )

_CPP_LOWER_START_KEYWORDS = (
    "int ", "void ", "double ", "float ", "char ", "bool ", "long ", "short ",
    "unsigned ", "signed ", "string ", "class ", "struct ", "const ", "static ",
    "virtual ", "for ", "while ", "if ", "else ", "return ", "vector", "std::", "`",
)


def _capitalize_cleaned_sentence_start(text: str) -> str:
    """Viết hoa chữ cái đầu tiên của câu sau khi tước bỏ tiền tố chào hỏi/khuôn sáo mà không chạm vào từ khóa C++."""
    if not text:
        return text
    if any(text.startswith(kw) for kw in _CPP_LOWER_START_KEYWORDS):
        return text
    first = text[0]
    if first.isalpha() and first.islower():
        return first.upper() + text[1:]
    return text


def _strip_opening_greetings_and_boilerplate(text: str) -> str:
    """
    Loại bỏ lời chào lặp ('Chào bạn!', 'Xin chào!') và cụm mở đầu rập khuôn ('Theo đoạn video,')
    ở đầu tin nhắn Assistant cũ để cắt đứt vòng lặp nhại few-shot trên mô hình 7B (Zero Regex).
    """
    if not text:
        return text
    work = text.lstrip()
    if work.startswith("```"):
        return text

    changed = True
    while changed and work:
        changed = False
        low = work.lower()

        for g_pref in _OPENING_GREETING_PREFIXES:
            if low.startswith(g_pref):
                after_idx = len(g_pref)
                if after_idx == len(work) or work[after_idx] in ("!", ",", ".", ":", "-", "—", " ", "\t", "\n"):
                    cur = after_idx
                    while cur < len(work) and work[cur] in ("!", ",", ".", ":", "-", "—", " ", "\t", "\n"):
                        cur += 1
                    work = _capitalize_cleaned_sentence_start(work[cur:])
                    changed = True
                    break

        if changed or not work:
            continue

        low = work.lower()
        for v_pref in _OPENING_VIDEO_BOILERPLATE_PREFIXES:
            if low.startswith(v_pref):
                after_idx = len(v_pref)
                if after_idx < len(work) and work[after_idx] in (",", ":"):
                    cur = after_idx + 1
                    while cur < len(work) and work[cur] in (" ", "\t"):
                        cur += 1
                    work = _capitalize_cleaned_sentence_start(work[cur:])
                    changed = True
                    break

    return work


def _split_line_sentences_plain(line: str) -> List[str]:
    """Tách các câu trên một dòng văn bản ngoài cặp dấu backtick `...` (Zero Regex)."""
    sentences: List[str] = []
    in_backtick = False
    start = 0
    n = len(line)
    i = 0
    while i < n:
        ch = line[i]
        if ch == "`":
            in_backtick = not in_backtick
        elif not in_backtick and ch in (".", "!", "?"):
            end = i + 1
            while end < n and line[end] in (".", "!", "?", "\"", "'", ")"):
                end += 1
            seg = line[start:end].strip()
            if seg:
                sentences.append(seg)
            start = end
            while start < n and line[start] == " ":
                start += 1
            i = start
            continue
        i += 1
    if start < n:
        tail = line[start:].strip()
        if tail:
            sentences.append(tail)
    return sentences


def _is_closing_filler_sentence(sentence: str) -> bool:
    """Kiểm tra xem một câu cuối có phải là lời chúc / xã giao đóng lượt thừa thãi hay không."""
    probe = sentence.strip().lstrip("*-_• \t").rstrip(".!? \t\"')").lower()
    if not probe:
        return False
    return any(probe.startswith(pref) for pref in _CLOSING_FILLER_PREFIXES)


def _strip_closing_filler(text: str) -> str:
    """Loại bỏ các câu kết xã giao sáo rỗng ('Hy vọng...', 'Nếu còn thắc mắc...') ở cuối lịch sử Assistant (Zero Regex)."""
    if not text:
        return text
    lines = text.splitlines()
    if any(l.strip().startswith("```") for l in lines[-2:] if l.strip()):
        return text

    # Kiểm tra xem dòng cuối có nằm ngoài code fence không
    fence_toggle = False
    for l in lines:
        if l.strip().startswith("```"):
            fence_toggle = not fence_toggle
    if fence_toggle:
        return text

    while lines:
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            break
        last_line = lines[-1]
        if last_line.strip().startswith("```"):
            break

        # Gỡ nhãn '**Câu hỏi gợi mở:**' nếu có để giữ lại câu hỏi tự nhiên
        for label_pat in ("**Câu hỏi gợi mở:**", "**Câu hỏi gợi mở**:", "Câu hỏi gợi mở:"):
            if last_line.strip().startswith(label_pat):
                idx = last_line.find(label_pat)
                last_line = last_line[idx + len(label_pat):].lstrip()
                lines[-1] = last_line
                break

        sents = _split_line_sentences_plain(last_line)
        if not sents:
            break
        changed_line = False
        while sents and _is_closing_filler_sentence(sents[-1]):
            sents.pop()
            changed_line = True
        if not changed_line:
            break
        if sents:
            lines[-1] = " ".join(sents)
            break
        else:
            lines.pop()

    return "\n".join(lines).strip()


def _clean_assistant_history_text(text: str) -> str:
    """
    Làm sạch lịch sử phản hồi của Assistant trước khi đưa vào sliding_history (kể cả lượt t-1):
    (a) Loại bỏ thẻ <timestamp ...>...</timestamp>.
    (b) Loại bỏ dòng footer bắt đầu bằng '📍' hoặc 'Mốc video bài giảng:'.
    (c) Loại bỏ nhãn '[Video Bài ...]' và các thẻ rút gọn nội bộ cũ nếu có.
    (d) Loại bỏ lời chào mở đầu lặp ('Chào bạn!') & khuôn sáo ('Theo đoạn video,') và câu kết xã giao ('Nếu còn thắc mắc...').
    Bảo toàn 100% nội dung giải thích C++ và khối code.
    """
    if not text:
        return ""
    work = _strip_timestamp_tags_plain(text)
    for internal_marker in (
        "... [đã rút gọn phản hồi dài ở lượt trước]",
        "[đã rút gọn phản hồi dài ở lượt trước]",
        "... [rút gọn lượt cũ]",
        "[rút gọn lượt cũ]",
    ):
        if internal_marker in work:
            work = work.replace(internal_marker, "...")

    cleaned_lines: List[str] = []
    in_code_fence = False

    for line in work.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            cleaned_lines.append(line)
            continue

        if in_code_fence:
            cleaned_lines.append(line)
            continue

        header_probe = stripped.lstrip("*-• \t")
        if header_probe.startswith("📍") or header_probe.lower().startswith("mốc video bài giảng"):
            continue

        if "📍" in line:
            pin_idx = line.find("📍")
            line = line[:pin_idx].rstrip()
        if "mốc video bài giảng" in line.lower():
            low_line = line.lower()
            m_idx = low_line.find("mốc video bài giảng")
            cut_idx = m_idx
            while cut_idx > 0 and line[cut_idx - 1] in ("*", " ", "\t", "-"):
                cut_idx -= 1
            line = line[:cut_idx].rstrip()

        line = _strip_leaked_video_source_brackets(line)
        if not line.strip() and stripped:
            continue
        cleaned_lines.append(line)

    res = "\n".join(cleaned_lines)
    while "\n\n\n" in res:
        res = res.replace("\n\n\n", "\n\n")
    res = res.strip()
    res = _strip_opening_greetings_and_boilerplate(res)
    res = _strip_closing_filler(res)
    while "\n\n\n" in res:
        res = res.replace("\n\n\n", "\n\n")
    return res.strip()


def _truncate_assistant_history_cleanly(
    text: str,
    max_chars: int,
    preserve_trailing_question: bool = False,
) -> str:
    """
    Rút gọn phản hồi dài của Assistant tại ranh giới câu tự nhiên ('.', '?', '!', '\\n') kèm '...',
    TUYỆT ĐỐI KHÔNG chèn nhãn ngoặc vuông '[đã rút gọn...]' / '[rút gọn...]' tránh mô hình 7B nhại lại.
    Nếu preserve_trailing_question=True và lượt t-1 kết thúc bằng câu hỏi Socratic ('?'),
    bảo toàn câu hỏi cuối để duy trì mẫu chuẩn Socratic trong cửa sổ trượt.
    """
    if len(text) <= max_chars:
        return text

    trailing_q = ""
    if preserve_trailing_question and text.rstrip().endswith("?"):
        non_empty_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if non_empty_lines:
            last_ln = non_empty_lines[-1]
            sents = _split_line_sentences_plain(last_ln)
            cand_q = sents[-1] if sents else last_ln
            if cand_q.endswith("?") and 12 <= len(cand_q) <= 140 and not _is_closing_filler_sentence(cand_q):
                trailing_q = cand_q

    body_budget = (max_chars - len(trailing_q) - 4) if trailing_q else (max_chars - 3)
    body_budget = max(80, body_budget)
    window = text[:body_budget].rstrip()

    min_cut = body_budget // 2
    best_sent_idx = -1
    for sep in (".", "?", "!", "\n"):
        idx = window.rfind(sep)
        if idx >= min_cut and idx > best_sent_idx:
            best_sent_idx = idx

    if best_sent_idx != -1:
        ch_end = window[best_sent_idx]
        cut = window[:best_sent_idx + 1].rstrip()
        if ch_end in (".", "\n"):
            if cut.endswith(("?", "!")):
                pass
            else:
                cut = cut.rstrip(" ,;:-(.\t") + "..."
        elif not cut.endswith(("?", "!", "...")):
            cut = cut + "..."
    else:
        sp_idx = window.rfind(" ")
        if sp_idx >= min_cut:
            cut = window[:sp_idx]
        else:
            cut = window
        cut = cut.rstrip(" ,;:-(\t.") + "..."

    if trailing_q and trailing_q not in cut:
        return f"{cut}\n{trailing_q}"
    return cut


def _is_fast_path_boilerplate_assistant(content: str) -> bool:
    """Nhận diện tin nhắn trả lời mẫu của Fast-Path (chào hỏi / từ chối ngoài lề) để tránh nhiễm 'Chào bạn! ... nhé!' vào LLM."""
    if not content or "In-Course AI Copilot" not in content:
        return False
    return (
        "Trợ giảng lập trình của khóa học" in content
        or "Trợ giảng chuyên môn của khóa học" in content
    )


# ==========================================
# NODE 4: CONTEXT ASSEMBLY NODE (SLIDING WINDOW & CHATML)
# ==========================================
async def context_assembly_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 4: Điều phối ngữ cảnh đa lượt (Multi-Turn Context Assembly & Token Budget Guard).
    - Áp dụng thuật toán Sliding Window k turns và khống chế ngân sách ký tự lịch sử.
    - Cắt tỉa sạch theo ranh giới câu (Zero Bracket Tag Leak) & khử lời chào/câu kết sáo rỗng.
    - Temporal / Topic Shift History Pruning: Khi học viên nhảy sang mốc thời gian video mới
      (>= 45s hoặc explicit/relative segment) hoặc chuyển sang out_of_lesson / đổi bài học,
      cắt bỏ lịch sử giải thích cũ và bơm chỉ thị neo ngữ cảnh lượt hiện tại.
    - Bảo toàn 100% System Prompt tĩnh cho vLLM KV Prefix Caching.
    """
    history_messages = state.get("messages", [])
    conv_summary = state.get("conversation_summary")
    system_prompt = state.get("system_prompt", SOCRATIC_GROUNDED_PROMPT)
    raw_prompt = normalize_user_input(state.get("prompt", ""))
    user_message_content = state.get("user_message_content") or raw_prompt
    turn_count = (len(history_messages) // 2) + 1

    # Phát hiện chuyển dịch mốc thời gian video (Temporal Shift) hoặc chuyển bài / ngoài bài học (Topic/Lesson Shift)
    c_svc = get_curriculum_service()
    time_ref = c_svc.extract_video_time_reference(raw_prompt) if raw_prompt else None
    explicit_seq = c_svc._extract_lesson_seq(raw_prompt.lower()) if raw_prompt else None
    time_kind = time_ref.get("kind") if (time_ref and explicit_seq is None) else None

    current_target_sec: Optional[int] = None
    raw_cur_vsec = state.get("current_video_sec")
    if isinstance(raw_cur_vsec, (int, float)) and not isinstance(raw_cur_vsec, bool):
        current_target_sec = int(raw_cur_vsec)
    if time_ref and explicit_seq is None and time_ref.get("target_sec") is not None:
        current_target_sec = int(time_ref["target_sec"])
    elif state.get("suggested_timestamps"):
        first_ts_sec = state["suggested_timestamps"][0].get("sec")
        if isinstance(first_ts_sec, (int, float)) and not isinstance(first_ts_sec, bool):
            current_target_sec = int(first_ts_sec)
    elif "<timestamp" in user_message_content.lower():
        parsed_umc_sec = _extract_first_timestamp_sec(user_message_content)
        if parsed_umc_sec is not None:
            current_target_sec = parsed_umc_sec

    prior_video_sec: Optional[int] = None
    raw_prev_vsec = state.get("prev_video_sec")
    if isinstance(raw_prev_vsec, (int, float)) and not isinstance(raw_prev_vsec, bool):
        prior_video_sec = int(raw_prev_vsec)
    else:
        for m in reversed(history_messages):
            if m.get("role") == "assistant":
                ts_sec = _extract_first_timestamp_sec(m.get("content", ""))
                if ts_sec is not None:
                    prior_video_sec = ts_sec
                    break
        if prior_video_sec is None:
            raw_last_vsec = state.get("last_video_sec")
            if (
                isinstance(raw_last_vsec, (int, float))
                and not isinstance(raw_last_vsec, bool)
                and current_target_sec is not None
                and int(raw_last_vsec) != current_target_sec
            ):
                prior_video_sec = int(raw_last_vsec)

    has_video_sec_jump = (
        current_target_sec is not None
        and prior_video_sec is not None
        and abs(current_target_sec - prior_video_sec) >= 45
    )
    is_explicit_or_relative_segment = time_kind in (
        "explicit_sec",
        "relative_start",
        "relative_middle",
        "relative_end",
    )
    is_temporal_shift = bool(is_explicit_or_relative_segment or has_video_sec_jump)

    retrieval_status = state.get("retrieval_status")
    is_curriculum_nav = bool(state.get("is_curriculum_navigation", False))
    curr_lesson_seq = state.get("lesson_seq")
    prev_lesson_seq = state.get("prev_lesson_seq")
    if prev_lesson_seq is None:
        prev_lesson_seq = state.get("current_lesson_seq")
    is_lesson_switch = (
        curr_lesson_seq is not None
        and prev_lesson_seq is not None
        and isinstance(prev_lesson_seq, int)
        and not isinstance(prev_lesson_seq, bool)
        and int(curr_lesson_seq) != int(prev_lesson_seq)
    )
    is_out_of_lesson_or_nav = bool(
        retrieval_status == "out_of_lesson"
        or is_curriculum_nav
        or is_lesson_switch
    )

    # 1. Thuật toán Sliding Window: Lọc bỏ các cặp Fast-Path chào hỏi/ngoài lề khỏi few-shot context
    filtered_history: List[Dict[str, str]] = []
    idx_h = 0
    total_h = len(history_messages)
    while idx_h < total_h:
        cur_m = history_messages[idx_h]
        if (
            cur_m.get("role") == "user"
            and idx_h + 1 < total_h
            and history_messages[idx_h + 1].get("role") == "assistant"
            and _is_fast_path_boilerplate_assistant(history_messages[idx_h + 1].get("content", ""))
        ):
            idx_h += 2
            continue
        if cur_m.get("role") == "assistant" and _is_fast_path_boilerplate_assistant(cur_m.get("content", "")):
            idx_h += 1
            continue
        filtered_history.append(cur_m)
        idx_h += 1

    SLIDING_WINDOW_TURNS = settings.SLIDING_WINDOW_TURNS
    max_history_count = SLIDING_WINDOW_TURNS * 2
    raw_sliding_history = (
        filtered_history[-max_history_count:]
        if len(filtered_history) > max_history_count
        else list(filtered_history)
    )

    # 2. Token Budget & Temporal/Topic Shift Pruning
    MAX_HISTORY_CHARS = settings.MAX_HISTORY_CHARS
    sliding_history: List[Dict[str, str]] = []
    accumulated_chars = 0

    if not (is_temporal_shift or is_out_of_lesson_or_nav):
        # Duyệt ngược từ tin nhắn mới nhất về cũ nhất trong cửa sổ trượt
        for idx_from_end, msg in enumerate(reversed(raw_sliding_history)):
            content = msg.get("content", "")
            role = msg.get("role", "user")

            if role == "assistant":
                content = _clean_assistant_history_text(content)

            # Rút gọn code block dài trong các câu trả lời cũ của assistant bằng Markdown AST (Zero Regex)
            if role == "assistant" and "```" in content and len(content) > 180:
                try:
                    tokens = _MD_PARSER.parse(content)
                    ranges = [t.map for t in tokens if t.type in ("fence", "code_block") and t.map]
                    if ranges:
                        lines = content.splitlines()
                        new_lines = []
                        skip_until = -1
                        for i, l in enumerate(lines):
                            in_range = False
                            for start, end in ranges:
                                if i == start:
                                    new_lines.append("[...khung code minh họa ở lượt trước...]")
                                    skip_until = end
                                    in_range = True
                                    break
                                elif start < i < end:
                                    in_range = True
                                    break
                            if not in_range and i >= skip_until:
                                new_lines.append(l)
                        content = "\n".join(new_lines)
                except Exception:
                    pass

            # Nén các lượt trả lời xa của assistant (t < k - 1, tức idx_from_end >= 2) <= 200 ký tự không dùng thẻ ngoặc vuông
            if role == "assistant" and idx_from_end >= 2 and len(content) > 200:
                content = _truncate_assistant_history_cleanly(content, max_chars=200, preserve_trailing_question=False)

            # Nén lượt t-1 của assistant nếu quá dài (> 450 ký tự) tại ranh giới câu tự nhiên, bảo toàn câu hỏi '?' cuối nếu có
            if role == "assistant" and idx_from_end < 2 and len(content) > 450:
                content = _truncate_assistant_history_cleanly(content, max_chars=360, preserve_trailing_question=True)

            msg_len = len(content)
            if accumulated_chars + msg_len > MAX_HISTORY_CHARS and len(sliding_history) >= 2:
                # Vượt trần ngân sách nhưng luôn giữ ít nhất 1 turn gần nhất (2 msgs)
                break

            sliding_history.insert(0, {"role": role, "content": content})
            accumulated_chars += msg_len

    # 3. Bảo toàn System Prompt tĩnh 100% cho vLLM KV Prefix Caching; đẩy phần động vào user_message_content
    full_system_prompt = system_prompt
    dynamic_user_extensions: List[str] = []
    if conv_summary and not is_lesson_switch and not is_temporal_shift and not is_out_of_lesson_or_nav:
        dynamic_user_extensions.append(
            f"[BỐI CẢNH TIẾN TRÌNH THẢO LUẬN TRƯỚC ĐÓ CỦA HỌC VIÊN]:\n{conv_summary}"
        )

    # Dynamic Academic Glossary Injection (Mục 4.2): Khóa không gian sinh từ của LLM theo chuẩn đại học
    # Loại trừ các khối mục lục phụ trợ / danh mục lộ trình để không tiêm nhầm thuật ngữ của mốc/bài khác
    is_nav_only_turn = bool(state.get("is_curriculum_navigation", False)) and state.get("retrieval_status") == "out_of_lesson"
    glossary_lookup_text = "" if is_nav_only_turn else _extract_glossary_lookup_text(user_message_content, raw_prompt)
    glossary_ext = get_academic_glossary_prompt_extension(glossary_lookup_text) if glossary_lookup_text else ""
    if glossary_ext:
        dynamic_user_extensions.append(glossary_ext.strip())

    missing_deictic_sec = bool(state.get("missing_deictic_sec", False))
    if is_out_of_lesson_or_nav:
        dynamic_user_extensions.append(
            "[CHỈ THỊ TẬP TRUNG LƯỢT HIỆN TẠI - CHỐNG LẶP LỊCH SỬ]: "
            "Học viên vừa chuyển sang hỏi lộ trình hoặc bài học khác (chưa mở video bài học đó). "
            "CHỈ trả lời trực diện dựa trên [TIẾN ĐỘ BÀI HỌC] / danh mục giáo trình của lượt này; "
            "TUYỆT ĐỐI KHÔNG mở đầu bằng \"Chào bạn!\" hay \"Theo đoạn video...\", KHÔNG lặp lại chủ đề "
            "của các lượt trước, và BẮT BUỘC kết thúc câu trả lời (ngay trước thẻ `<timestamp>` nếu có) "
            "bằng đúng 1 câu hỏi định hướng cụ thể có dấu `?`."
        )
    elif is_temporal_shift and not missing_deictic_sec:
        dynamic_user_extensions.append(
            "[CHỈ THỊ TẬP TRUNG MỐC VIDEO HIỆN TẠI - CHỐNG LẶP LỊCH SỬ]: "
            "Học viên đang hỏi về một mốc/phân đoạn video cụ thể mới ở lượt này. "
            "CHỈ giải thích đúng kiến thức nằm trong [NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC] của lượt này; "
            "TUYỆT ĐỐI KHÔNG lặp lại chủ đề của các mốc video ở lượt trước hay các phân đoạn khác trong mục lục, "
            "KHÔNG mở đầu bằng \"Chào bạn!\", từ chối viết code giải hoàn chỉnh nếu học viên xin full code, "
            "và BẮT BUỘC kết thúc phần giải thích (ngay trước thẻ `<timestamp>`) bằng đúng 1 câu hỏi Socratic kiểm tra tư duy có dấu `?`."
        )

    # Pedagogical Analogy / Verification Directive (tiêm vào user_message_content, giữ messages[0] tĩnh 100%)
    if not is_out_of_lesson_or_nav and _is_analogy_verification_query(raw_prompt):
        dynamic_user_extensions.append(
            "[CHỈ THỊ ĐÁNH GIÁ MỆNH ĐỀ / ẨN DỤ]: Học viên đang kiểm chứng một ví dụ ẩn dụ hoặc nhận định đúng/sai. "
            "Bắt buộc thực hiện đủ 3 bước: (1) Đánh giá rõ ví dụ/nhận định đó đúng hay chưa chính xác ở điểm nào, "
            "(2) Giải thích bản chất kỹ thuật C++ tương ứng trong 2–3 câu ngắn gọn bám sát [NGỮ CẢNH BÀI GIẢNG], "
            "(3) Kết thúc bằng ĐÚNG 1 câu hỏi Socratic MỚI có dấu `?` (TUYỆT ĐỐI CẤM chỉ lặp lại câu hỏi của học viên)."
        )

    # Pedagogical Soft Nudge: Khích lệ tự suy luận ngắn gọn khi phiên kéo dài liên tục (CẤM tự sinh code mẫu dài & giữ bắt buộc dấu '?')
    if turn_count > settings.SOFT_NUDGE_TURN_TRIGGER:
        dynamic_user_extensions.append(
            "[HƯỚNG DẪN SƯ PHẠM ĐA LƯỢT]: Phiên học đã qua nhiều lượt trao đổi. "
            "Hãy trả lời trực diện bằng 2–4 câu giải thích bản chất (TUYỆT ĐỐI KHÔNG chỉ lặp lại câu hỏi của học viên, "
            "TUYỆT ĐỐI KHÔNG tự viết thêm khối code C++ mẫu dài hay chương trình chạy thử); sau đó kết thúc bằng "
            "ĐÚNG 1 câu hỏi Socratic MỚI kiểm tra tư duy kết thúc bằng dấu `?` (ngay trước thẻ `<timestamp>`), "
            "KHÔNG kết thúc bằng câu xã giao cảm thán (`nhé!`)."
        )
    elif (
        not is_out_of_lesson_or_nav
        and not is_temporal_shift
        and any(
            tag in user_message_content
            for tag in (
                "[NGỮ CẢNH BÀI GIẢNG",
                "[TIẾN ĐỘ BÀI HỌC]",
                "[THÔNG TIN PHẠM VI KHÓA HỌC]",
                "[MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI]",
            )
        )
    ):
        dynamic_user_extensions.append(
            "[QUY TẮC ĐỊNH DẠNG ĐẦU RA BẮT BUỘC]: Đi thẳng vào nội dung chuyên môn (KHÔNG mở đầu bằng \"Chào bạn!\"), "
            "giải thích/đánh giá trực diện câu hỏi trong 2–4 câu (TUYỆT ĐỐI CẤM chỉ lặp lại câu hỏi của học viên), "
            "và câu văn cuối cùng trước thẻ `<timestamp>` BẮT BUỘC là đúng 1 câu hỏi Socratic MỚI cụ thể kết thúc bằng dấu `?` "
            "(KHÔNG kết thúc bằng câu xã giao `nhé!`)."
        )

    final_user_content = user_message_content
    if dynamic_user_extensions:
        final_user_content = f"{user_message_content}\n\n" + "\n\n".join(dynamic_user_extensions)

    # 4. Đóng gói danh sách tin nhắn chuẩn ChatML
    assembled: List[Dict[str, str]] = [
        {"role": "system", "content": full_system_prompt}
    ]

    # Nạp các lượt trò chuyện trước đó từ Sliding Window đã được cắt tỉa
    for msg in sliding_history:
        assembled.append({"role": msg["role"], "content": msg["content"]})

    # Nạp câu hỏi hiện tại kèm khối tài liệu RAG đã được thẩm định CRAG và các phần mở rộng động
    assembled.append({"role": "user", "content": final_user_content})

    return {
        "assembled_messages": assembled,
        "user_message_content": final_user_content,
        "turn_count": turn_count
    }


# ==========================================
# CONDITIONAL ROUTING FUNCTION
# ==========================================
def should_retrieve(state: AgentState) -> str:
    """
    Rẽ nhánh điều kiện:
    - Nếu là câu hỏi chuyên môn lập trình (course_query) -> Chuyển sang Node Retrieval.
    - Nếu là chào hỏi, cảm ơn, danh tính, ngoài lề (chit_chat / out_of_scope) -> Kết thúc sớm (Fast-Path).
    """
    if state.get("is_course_query", False):
        return "retrieval"
    return "fast_path"


# ==========================================
# XÂY DỰNG & BIÊN DỊCH LANGGRAPH STATEGRAPH
# ==========================================
_checkpointer = MemorySaver()
_compiled_chat_graph = None


def build_chat_graph():
    """
    Khởi tạo và biên dịch StateGraph cho Agentic RAG Copilot với MemorySaver Checkpointer.
    """
    global _checkpointer
    workflow = StateGraph(AgentState)

    # Đăng ký 4 Discrete Nodes
    workflow.add_node("router", router_node)
    workflow.add_node("retrieval", retrieval_node)
    workflow.add_node("crag_grader", crag_grader_node)
    workflow.add_node("context_assembly", context_assembly_node)

    # Thiết lập Điểm khởi đầu (Entry Point)
    workflow.set_entry_point("router")

    # Thiết lập Cạnh điều kiện (Conditional Edges)
    workflow.add_conditional_edges(
        "router",
        should_retrieve,
        {
            "fast_path": END,
            "retrieval": "retrieval"
        }
    )

    # Thiết lập Cạnh tuần tự (Linear Edges)
    workflow.add_edge("retrieval", "crag_grader")
    workflow.add_edge("crag_grader", "context_assembly")
    workflow.add_edge("context_assembly", END)

    # Biên dịch đồ thị trạng thái có kết nối Checkpointer
    compiled_graph = workflow.compile(checkpointer=_checkpointer)
    logger.info("[LangGraph] Đã biên dịch thành công Chat StateGraph (4 Discrete Nodes & MemorySaver Checkpointer).")
    return compiled_graph


def get_chat_graph():
    global _compiled_chat_graph
    if _compiled_chat_graph is None:
        _compiled_chat_graph = build_chat_graph()
    return _compiled_chat_graph


def commit_assistant_turn(
    session_id: str,
    user_prompt: str,
    assistant_response: str,
    current_lesson_seq: Optional[int] = None,
    last_course_query: Optional[str] = None
) -> None:
    """
    Lưu vết cặp tin nhắn (User + Assistant) vào StateGraph Checkpointer theo thread_id.
    Tự động kích hoạt thuật toán nén Conversation Summarizer khi số lượt > SUMMARIZER_TURN_TRIGGER,
    bảo toàn tuyệt đối thông tin bài học hiện tại (current_lesson_seq) và mỏ neo (last_course_query).
    """
    graph = get_chat_graph()
    config = {"configurable": {"thread_id": session_id}}
    state_snapshot = graph.get_state(config)

    current_values = state_snapshot.values if state_snapshot else {}
    history = list(current_values.get("messages", []))

    clean_user_prompt = normalize_user_input(user_prompt)

    # Bổ sung cặp câu hỏi - câu trả lời mới
    history.append({"role": "user", "content": clean_user_prompt})
    history.append({"role": "assistant", "content": assistant_response})

    current_turn = len(history) // 2

    lesson_seq_ref = current_lesson_seq or current_values.get("current_lesson_seq", "hiện tại")

    # Nén tóm tắt nếu vượt quá SUMMARIZER_TURN_TRIGGER lượt đối thoại
    summary = current_values.get("conversation_summary")
    max_history_before_summary = settings.SLIDING_WINDOW_TURNS * 2
    if current_turn > settings.SUMMARIZER_TURN_TRIGGER and len(history) > max_history_before_summary:
        overflow_msgs = history[:-max_history_before_summary]
        topics = [
            f"Lượt {idx//2 + 1}: {m['content'][:60]}"
            for idx, m in enumerate(overflow_msgs) if m["role"] == "user"
        ]
        summary = f"Học viên đang theo học Bài {lesson_seq_ref}. Tiến trình thảo luận trước đó: {'; '.join(topics)}."

    update_payload: Dict[str, Any] = {
        "messages": history,
        "turn_count": current_turn,
        "conversation_summary": summary,
        "current_lesson_seq": current_lesson_seq if current_lesson_seq is not None else current_values.get("current_lesson_seq"),
    }
    if current_lesson_seq is not None and current_values.get("last_lesson_seq") is None:
        update_payload["last_lesson_seq"] = current_lesson_seq
    if last_course_query is not None:
        update_payload["last_course_query"] = last_course_query
    elif "last_course_query" in current_values and current_values["last_course_query"] is not None:
        update_payload["last_course_query"] = current_values["last_course_query"]

    graph.update_state(config, update_payload)
    logger.info(f"[LangGraph:Checkpointer] Đã lưu snapshot Turn {current_turn} cho Session '{session_id}' ({len(history)} messages).")


def reset_session_state(session_id: str) -> None:
    """
    Đặt lại trạng thái phiên trong Checkpointer và Rate Limiter khi học viên bấm nút Làm mới.
    """
    graph = get_chat_graph()
    config = {"configurable": {"thread_id": session_id}}
    graph.update_state(config, {
        "messages": [],
        "turn_count": 0,
        "conversation_summary": None,
        "search_query": None,
        "last_course_query": None,
        "assembled_messages": [],
        "pending_navigation": None,
        "last_offered_lessons": [],
        "last_turn_intent": None,
        "action": None,
        "current_lesson_seq": None,
        "last_video_sec": None,
        "last_lesson_seq": None,
        "prev_video_sec": None,
        "prev_lesson_seq": None,
        "inherited_video_sec": None,
        "missing_deictic_sec": False,
        "is_overview_query": False,
    })
    # Đồng bộ đặt lại lịch sử tần suất trong Rate Limiter
    get_session_rate_limiter().reset_session(session_id)
    logger.info(f"[LangGraph:Checkpointer] Đã reset trạng thái và rate limiter cho Session '{session_id}'.")
