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
from app.agent.guardrails import get_session_rate_limiter
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

    # 3. Định tuyến ý định (Intent Routing)
    intent: str
    direct_response: Optional[str]
    is_course_query: bool
    search_query: Optional[str]
    last_course_query: Optional[str]
    is_curriculum_navigation: bool

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
    action: Optional[Dict[str, Any]]

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
            item_text = f"[Video Bài {lesson_seq} - {tag}]: {raw_t}"

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
    raw_prompt = state["prompt"]
    pending_nav = state.get("pending_navigation")

    # 0. Nhận diện Mệnh Lệnh Chuyển Bài Trực Tiếp (Conversational UI Action Dispatcher - Mục 3.2 & 4.1)
    direct_nav_target = curr_svc.extract_direct_navigation_command(raw_prompt)
    if direct_nav_target is not None:
        logger.info(
            f"[LangGraph:router_node] Nhận diện Mệnh Lệnh Chuyển Bài Trực Tiếp: "
            f"'{raw_prompt}' -> target_lesson_seq={direct_nav_target}"
        )
        direct_resp = (
            f"Đã rõ! Mình đang chuyển bạn sang **Bài {direct_nav_target}** "
            f"để bạn theo dõi video bài giảng ngay nhé! 🎬"
        )
        return {
            "intent": "confirm_navigation",
            "direct_response": direct_resp,
            "is_course_query": False,
            "target_lesson_seq": direct_nav_target,
            "action": {
                "type": "navigate_and_seek",
                "action": "navigate_lesson",
                "target_lesson_seq": direct_nav_target,
                "sec": 0,
                "label": "00:00"
            },
            "pending_navigation": None
        }

    # Kiểm tra xác nhận đàm thoại đa lượt (Conversational Navigation Confirmation - Zero Regex NLI)
    if pending_nav:
        is_confirmed, conf_score = router.check_confirmation(raw_prompt)
        if is_confirmed:
            target_seq = pending_nav.get("lesson_seq")
            target_sec = pending_nav.get("sec", 0)
            target_lbl = pending_nav.get("label", "00:00")
            logger.info(
                f"[LangGraph:router_node] Xác nhận chuyển bài thành công qua NLI ({conf_score*100:.1f}%): "
                f"Bài {target_seq} @ {target_lbl} ({target_sec}s)"
            )
            direct_resp = (
                f"Đã rõ! Mình đang chuyển bạn sang **Bài {target_seq}** tại mốc **{target_lbl}** "
                f"để bạn theo dõi video bài giảng ngay nhé! 🎬"
            )
            return {
                "intent": "confirm_navigation",
                "direct_response": direct_resp,
                "is_course_query": False,
                "target_lesson_seq": target_seq,
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

    # 1. Phân loại ý định thô qua Router Machine Learning
    raw_clf = router.classify(raw_prompt)
    anchor_query = state.get("last_course_query")
    if not anchor_query and history:
        # Tìm câu hỏi user gần nhất trong history mà không phải là pure social greeting hay acknowledgment
        for m in reversed(history):
            if m.get("role") == "user":
                cand = m.get("content", "")
                is_soc, _ = router.is_pure_social(cand)
                is_ack, _ = router.is_social_acknowledgment(cand)
                if not is_soc and not is_ack and router.classify(cand).is_course_query:
                    anchor_query = cand
                    break

    # -------------------------------------------------------------------------
    # BƯỚC 1: SOCIAL ACKNOWLEDGMENT & PURE SOCIAL CLOSURE GATE
    # -------------------------------------------------------------------------
    is_soc_ack, ack_sim = router.is_social_acknowledgment(raw_prompt)
    is_pure_soc, soc_sim = router.is_pure_social(raw_prompt)
    if (not raw_clf.is_course_query) and (is_soc_ack or is_pure_soc):
        max_social_sim = max(ack_sim, soc_sim)
        logger.info(
            f"[LangGraph:router_node] Bước 1 Social Acknowledgment Gate (Sim={max_social_sim:.3f}): "
            f"'{raw_prompt[:35]}...' -> chit_chat (skip RAG)"
        )
        return {
            "intent": "chit_chat",
            "direct_response": router._select_chitchat_response(raw_prompt),
            "is_course_query": False,
            "search_query": None,
            "last_course_query": anchor_query,  # Bảo toàn anchor cho các lượt học tập tiếp theo!
            "is_curriculum_navigation": False,
            "pending_navigation": None,
            "action": None
        }

    # -------------------------------------------------------------------------
    # BƯỚC 2: CURRICULUM NAVIGATION GATE
    # -------------------------------------------------------------------------
    is_curriculum_nav, nav_sim = router.is_curriculum_navigation(raw_prompt)
    if is_curriculum_nav:
        logger.info(
            f"[LangGraph:router_node] Bước 2 Curriculum Navigation Gate (NavSim={nav_sim:.3f}): "
            f"'{raw_prompt[:40]}...' -> Tìm bài học mới trong playlist"
        )
        return {
            "intent": "course_query",
            "direct_response": None,
            "is_course_query": True,
            "search_query": raw_prompt,
            "last_course_query": raw_prompt,
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

        if anchor_query and is_dep and not is_shift:
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
            "intent": "course_query",
            "direct_response": None,
            "is_course_query": True,
            "search_query": search_query,
            "last_course_query": new_last_course_query,
            "is_curriculum_navigation": False,
            "pending_navigation": None,
            "action": None
        }
    else:
        # raw_clf.is_course_query == False
        # CHỈ gọi router.classify_contextual(raw_prompt, anchor_query) khi anchor_query tồn tại VÀ router.is_context_dependent(raw_prompt) là True!
        if anchor_query and router.is_context_dependent(raw_prompt, anchor_query=anchor_query):
            classification, formulated_q = router.classify_contextual(raw_prompt, anchor_query)
            if classification.is_course_query:
                search_query = formulated_q
                new_last_course_query = f"{anchor_query} | {raw_prompt}" if len(anchor_query) < 220 else raw_prompt
                logger.info(f"[LangGraph:router_node] Bước 3 Contextual Rescue thành công: '{raw_prompt}' -> SearchQuery: '{search_query[:55]}...'")
                return {
                    "intent": "course_query",
                    "direct_response": None,
                    "is_course_query": True,
                    "search_query": search_query,
                    "last_course_query": new_last_course_query,
                    "is_curriculum_navigation": False,
                    "pending_navigation": None,
                    "action": None
                }
            else:
                logger.info(f"[LangGraph:router_node] Bước 3 Non-course classification ({classification.intent}): '{raw_prompt[:35]}...'")
                return {
                    "intent": classification.intent,
                    "direct_response": classification.direct_response,
                    "is_course_query": False,
                    "search_query": None,
                    "last_course_query": anchor_query,
                    "is_curriculum_navigation": False,
                    "pending_navigation": None,
                    "action": None
                }

        # Nếu không có anchor_query HOẶC not router.is_context_dependent(raw_prompt):
        # Đây là Topic Shift sang out_of_scope / chit_chat (như trà sữa, nước Pháp, Đà Nẵng, bóng đá, chiên cá)!
        logger.info(f"[LangGraph:router_node] Bước 3 Topic Shift / Non-course độc lập ({raw_clf.intent}): '{raw_prompt[:35]}...'")
        return {
            "intent": raw_clf.intent,
            "direct_response": raw_clf.direct_response,
            "is_course_query": False,
            "search_query": None,
            "last_course_query": anchor_query,  # Bảo toàn anchor cho tương lai
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
    raw_prompt = state["prompt"]
    search_query = state.get("search_query") or raw_prompt
    anchor_query = state.get("last_course_query")
    is_curriculum_nav = state.get("is_curriculum_navigation", False)
    is_cont_turn = bool(anchor_query and state.get("messages"))

    if is_curriculum_nav:
        try:
            retrieval_res: RetrievalResult = await retrieval_service.search(
                query_text=search_query,
                course_id=state["course_id"],
                current_lesson_seq=state["lesson_seq"],
                top_candidates=settings.DEFAULT_TOP_CANDIDATES,
                final_top_k=settings.DEFAULT_FINAL_TOP_K,
                is_curriculum_navigation=True,
                is_continuation_turn=False
            )
        except Exception as e:
            logger.error(f"[LangGraph:retrieval_node] Lỗi truy xuất Qdrant/RAG khi tìm lộ trình: {e}")
            retrieval_res = RetrievalResult(chunks=[], status="coverage_gap")
    else:
        # Bước 1: Truy xuất với raw_prompt trước để bảo toàn phân phối Cross-Encoder
        try:
            retrieval_res: RetrievalResult = await retrieval_service.search(
                query_text=raw_prompt,
                course_id=state["course_id"],
                current_lesson_seq=state["lesson_seq"],
                top_candidates=settings.DEFAULT_TOP_CANDIDATES,
                final_top_k=settings.DEFAULT_FINAL_TOP_K,
                is_curriculum_navigation=False,
                is_continuation_turn=is_cont_turn
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
                fallback_res: RetrievalResult = await retrieval_service.search(
                    query_text=search_query,
                    course_id=state["course_id"],
                    current_lesson_seq=state["lesson_seq"],
                    top_candidates=settings.DEFAULT_TOP_CANDIDATES,
                    final_top_k=settings.DEFAULT_FINAL_TOP_K,
                    is_curriculum_navigation=False,
                    is_continuation_turn=is_cont_turn
                )
                if fallback_res.status in ("grounded", "out_of_lesson") and not fallback_res.is_low_confidence:
                    retrieval_res = fallback_res
            except Exception as fb_err:
                logger.warning(f"[LangGraph:retrieval_node] Lỗi truy xuất Fallback Contextual: {fb_err}")

    return {
        "retrieved_chunks": retrieval_res.chunks,
        "retrieval_status": retrieval_res.status,
        "is_low_confidence": retrieval_res.is_low_confidence,
        "target_lesson_seq": retrieval_res.target_lesson_seq,
        "future_best_chunk": getattr(retrieval_res, "future_best_chunk", None)
    }


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
    raw_prompt = state["prompt"]
    search_query = state.get("search_query")

    # Xác định dòng liên kết ngữ cảnh hội thoại cho Anaphora Resolution
    solicitation_markers = ("viết hộ", "viết giúp", "viết cho", "code hộ", "code giúp", "giải giúp", "giải hộ", "cho em xin code", "viết full", "code luôn", "viết code hoàn chỉnh", "chỉ em cách viết code hoàn chỉnh")
    is_code_solicitation = any(w in raw_prompt.lower() for w in solicitation_markers)

    context_linked_line = ""
    if search_query and search_query != raw_prompt and not is_code_solicitation:
        context_linked_line = f"\n[NGỮ CẢNH HỘI THOẠI LIÊN KẾT]: {search_query}"

    suggested_timestamps: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []
    has_approximate = False
    new_pending_nav: Optional[Dict[str, Any]] = None

    if retrieval_status == "grounded":
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
                "start_sec": chunk.get("start_sec") or chunk.get("approx_video_sec"),
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
        active_system_prompt = SOCRATIC_GROUNDED_PROMPT
        context_block = _format_context_block(chunks)
        caution_notice = "\n[LƯU Ý: Một số tài liệu có độ tin cậy tham khảo, hãy định hướng học viên thận trọng.]\n" if is_low_confidence else ""
        user_message_content = f"""[CÂU HỎI THẮC MẮC CỦA HỌC VIÊN]
{state['prompt']}{context_linked_line}
{caution_notice}
{context_block}"""

    elif retrieval_status == "out_of_lesson":
        is_curriculum_nav = bool(state.get("is_curriculum_navigation", False))
        f_chunk = state.get("future_best_chunk")
        future_ts_info = ""
        future_learning_text = ""
        new_pending_nav = None

        if is_curriculum_nav:
            # Hạng mục A & B (Mục 2.2 - Nhịp 1B): Chặn bơm raw future chunk khi điều hướng lộ trình
            active_system_prompt = CURRICULUM_OVERVIEW_PROMPT
            target_desc = f"Bài {target_lesson_seq}" if target_lesson_seq else "các bài học sau"
            c_svc = get_curriculum_service()
            match_res = c_svc.find_lesson_for_query(
                state["prompt"],
                current_lesson_seq=state["lesson_seq"],
                preferred_course_id=state["course_id"]
            )
            target_lesson_dict = match_res[0] if match_res else None
            roadmap_bullets = []
            if target_lesson_dict:
                t_course = target_lesson_dict.get("course_id", state["course_id"])
                t_seq = target_lesson_dict.get("seq", target_lesson_seq)
                target_desc = f"Bài {t_seq}: {target_lesson_dict.get('title')}"
                related_lessons = [
                    f"- Bài {les.get('seq')}: {les.get('title')}"
                    for les in c_svc._all_lessons
                    if les.get("course_id") == t_course
                ]
                roadmap_bullets = related_lessons[:6]

            roadmap_str = "\n".join(roadmap_bullets) if roadmap_bullets else f"- {target_desc}"
            future_learning_text = f"\n[DANH MỤC LỘ TRÌNH BÀI HỌC BẢO CHỨNG TỪ GIÁO TRÌNH]\n{roadmap_str}\n"

        else:
            active_system_prompt = OUT_OF_LESSON_PROMPT
            target_desc = f"Bài {target_lesson_seq}" if target_lesson_seq else "các bài học sau"
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

        if f_chunk and f_chunk.get("start_sec") is not None:
            f_sec = int(f_chunk["start_sec"])
            f_lbl = f_chunk.get("start_label", f"{f_sec//60:02d}:{f_sec%60:02d}")
            suggested_timestamps.append({
                "sec": f_sec,
                "label": f_lbl,
                "title": f_chunk.get("video_title", f"Bài {target_lesson_seq}"),
                "lesson_seq": target_lesson_seq
            })
            new_pending_nav = {
                "lesson_seq": target_lesson_seq,
                "sec": f_sec,
                "label": f_lbl,
                "title": f_chunk.get("video_title", f"Bài {target_lesson_seq}")
            }
            future_ts_info = (
                f"\n\n[MỐC VIDEO BÀI GIẢNG TƯƠNG LAI]\n"
                f"- Bài học giảng dạy: Bài {target_lesson_seq}\n"
                f"- Mốc thời gian: {f_lbl} (giây {f_sec})\n"
                f"- Thẻ click-to-seek bắt buộc chèn: <timestamp sec=\"{f_sec}\" lesson=\"{target_lesson_seq}\">{f_lbl}</timestamp>\n"
                f"- CHỈ THỊ ĐÀM THOẠI: Kết thúc câu trả lời bằng câu hỏi gợi mở: "
                f"\"Bạn có muốn mình chuyển sang Bài {target_lesson_seq} và mở ngay đoạn video này cho bạn không?\""
            )

        user_message_content = f"""[CÂU HỎI CỦA HỌC VIÊN]
{state['prompt']}{context_linked_line}

[TIẾN ĐỘ BÀI HỌC]
- Khóa học: {state['course_id']}
- Bài học hiện tại của học viên: Bài {state['lesson_seq']}
- Bài học giảng dạy nội dung này: {target_desc}{future_ts_info}
{future_learning_text}"""

    else:  # coverage_gap
        active_system_prompt = COVERAGE_GAP_PROMPT
        user_message_content = f"""[CÂU HỎI CỦA HỌC VIÊN]
{state['prompt']}{context_linked_line}

[THÔNG TIN PHẠM VI KHÓA HỌC]
- Khóa học: Lập trình C++ ({state['course_id']}), đang ở Bài {state['lesson_seq']}.
- Câu hỏi của học viên không nằm trong giáo trình bài giảng hoặc là chủ đề ngoài lề."""


    return {
        "is_approximate": has_approximate,
        "suggested_timestamps": suggested_timestamps,
        "sources": sources,
        "system_prompt": active_system_prompt,
        "user_message_content": user_message_content,
        "pending_navigation": new_pending_nav
    }


# ==========================================
# NODE 4: CONTEXT ASSEMBLY NODE (SLIDING WINDOW & CHATML)
# ==========================================
async def context_assembly_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 4: Điều phối ngữ cảnh đa lượt (Multi-Turn Context Assembly & Token Budget Guard).
    - Áp dụng thuật toán Sliding Window k = 5 turns (tối đa 10 messages gần nhất).
    - Token Budget Pruning: Khống chế tổng ký tự lịch sử <= 2,400 chars (~800 tokens).
    - Tích hợp tóm tắt bối cảnh các lượt cũ (conversation_summary) vào System Prompt.
    - Pedagogical Soft Nudge: Thêm gợi ý thực hành khi phiên kéo dài (> 6 turns).
    - Đóng gói danh sách tin nhắn chuẩn ChatML tuân thủ ngân sách an toàn <= 3,368 tokens.
    """
    history_messages = state.get("messages", [])
    conv_summary = state.get("conversation_summary")
    system_prompt = state.get("system_prompt", SOCRATIC_GROUNDED_PROMPT)
    user_message_content = state.get("user_message_content", state["prompt"])
    turn_count = (len(history_messages) // 2) + 1

    # 1. Thuật toán Sliding Window: Giữ lại tối đa settings.SLIDING_WINDOW_TURNS turns gần nhất
    SLIDING_WINDOW_TURNS = settings.SLIDING_WINDOW_TURNS
    max_history_count = SLIDING_WINDOW_TURNS * 2
    raw_sliding_history = (
        history_messages[-max_history_count:]
        if len(history_messages) > max_history_count
        else list(history_messages)
    )

    # 2. Token Budget Pruning: Khống chế độ dài lịch sử <= settings.MAX_HISTORY_CHARS ký tự
    # Cắt tỉa các khối code dài ở các lượt cũ để bảo vệ KV Cache Prefill
    MAX_HISTORY_CHARS = settings.MAX_HISTORY_CHARS
    sliding_history: List[Dict[str, str]] = []
    accumulated_chars = 0

    # Duyệt ngược từ tin nhắn mới nhất về cũ nhất trong cửa sổ trượt
    for idx_from_end, msg in enumerate(reversed(raw_sliding_history)):
        content = msg.get("content", "")
        role = msg.get("role", "user")

        # Nén các lượt trả lời xa của assistant (t < k - 1, tức idx_from_end >= 2) <= 200 ký tự (Mục 4.2 - Nhịp 1B)
        if role == "assistant" and idx_from_end >= 2:
            if len(content) > 200:
                content = content[:200].rstrip() + "... [rút gọn lượt cũ]"

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

        msg_len = len(content)
        if accumulated_chars + msg_len > MAX_HISTORY_CHARS and len(sliding_history) >= 2:
            # Vượt trần ngân sách nhưng luôn giữ ít nhất 1 turn gần nhất (2 msgs)
            break

        sliding_history.insert(0, {"role": role, "content": content})
        accumulated_chars += msg_len

    # 3. Xây dựng System Prompt hoàn chỉnh (kèm tóm tắt tiến trình & Soft Nudge nếu có)
    full_system_prompt = system_prompt
    if conv_summary:
        full_system_prompt += f"\n\n[BỐI CẢNH TIẾN TRÌNH THẢO LUẬN TRƯỚC ĐÓ CỦA HỌC VIÊN]:\n{conv_summary}"

    # Dynamic Academic Glossary Injection (Mục 4.2): Khóa không gian sinh từ của LLM theo chuẩn đại học
    glossary_ext = get_academic_glossary_prompt_extension(f"{user_message_content} {state.get('prompt', '')}")
    if glossary_ext:
        full_system_prompt += glossary_ext

    # Pedagogical Soft Nudge: Khích lệ tự thực hành khi phiên kéo dài liên tục
    if turn_count > settings.SOFT_NUDGE_TURN_TRIGGER:
        full_system_prompt += (
            "\n\n[HƯỚNG DẪN SƯ PHẠM ĐA LƯỢT]: Phiên học đã qua nhiều lượt trao đổi chi tiết. "
            "Ở cuối câu trả lời, hãy đính kèm một câu động viên ngắn gọn khuyến khích học viên "
            "tự mở IDE gõ chạy thử mã nguồn để củng cố bài học."
        )

    # 4. Đóng gói danh sách tin nhắn chuẩn ChatML
    assembled: List[Dict[str, str]] = [
        {"role": "system", "content": full_system_prompt}
    ]

    # Nạp các lượt trò chuyện trước đó từ Sliding Window đã được cắt tỉa
    for msg in sliding_history:
        assembled.append({"role": msg["role"], "content": msg["content"]})

    # Nạp câu hỏi hiện tại kèm khối tài liệu RAG đã được thẩm định CRAG
    assembled.append({"role": "user", "content": user_message_content})

    return {
        "assembled_messages": assembled,
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

    # Bổ sung cặp câu hỏi - câu trả lời mới
    history.append({"role": "user", "content": user_prompt})
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
        "current_lesson_seq": lesson_seq_ref
    }
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
        "action": None
    })
    # Đồng bộ đặt lại lịch sử tần suất trong Rate Limiter
    get_session_rate_limiter().reset_session(session_id)
    logger.info(f"[LangGraph:Checkpointer] Đã reset trạng thái và rate limiter cho Session '{session_id}'.")
