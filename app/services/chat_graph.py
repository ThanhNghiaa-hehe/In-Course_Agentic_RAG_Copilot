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

import re
import logging
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.agent.router import get_intent_router
from app.services.retrieval import get_retrieval_service, RetrievalResult
from app.agent.guardrails import get_session_rate_limiter
from app.agent.prompts import (
    SOCRATIC_GROUNDED_PROMPT,
    OUT_OF_LESSON_PROMPT,
    COVERAGE_GAP_PROMPT,
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

    # 4. Kết quả truy xuất & Thẩm định CRAG
    retrieval_status: str
    retrieved_chunks: List[Dict[str, Any]]
    is_approximate: bool
    is_low_confidence: bool
    target_lesson_seq: Optional[int]
    suggested_timestamps: List[Dict[str, Any]]
    sources: List[Dict[str, Any]]

    # 5. Đóng gói Prompt Socratic & Danh sách ChatML cho LLM Generation
    system_prompt: str
    user_message_content: str
    assembled_messages: List[Dict[str, str]]


def _format_context_block(chunks: List[Dict[str, Any]], max_chars: int = 2400) -> str:
    """
    Định dạng các chunks ngữ cảnh thành khối văn bản có cấu trúc súc tích (Context Distillation).
    Áp trần tối đa ~800 tokens (~2400 ký tự) để tối ưu thời gian Prefill Attention trên GPU.
    Bảo toàn 100% thẻ <timestamp> và mã nguồn Code AST.
    """
    if not chunks:
        return "[LƯU Ý: Không tìm thấy tài liệu bài giảng nào vượt qua ngưỡng tin cậy cho câu hỏi này. Hãy hướng dẫn học viên dựa trên kiến thức chuẩn của C++]."

    blocks = ["[NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC]"]
    current_len = 0
    for idx, chunk in enumerate(chunks, 1):
        c_type = chunk.get("content_type", "unknown")
        lesson_seq = chunk.get("lesson_seq", "?")

        if c_type == "code_ast":
            scope = chunk.get("code_scope", "")
            code_content = (chunk.get("context_code") or chunk.get("raw_text", "")).strip()
            item_text = f"[Mã nguồn Bài {lesson_seq} - {scope}]:\n```cpp\n{code_content}\n```"
        else:
            tag = chunk.get("timestamp_tag", "")
            raw_t = (chunk.get("raw_text", "")).strip()
            raw_t = " ".join(raw_t.split())
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
    history = state.get("messages", [])
    raw_prompt = state["prompt"]

    # Nếu đang trong luồng hội thoại, kết hợp câu hỏi gần nhất của User làm ngữ cảnh toán học
    if history:
        last_user_query = next((m["content"] for m in reversed(history) if m.get("role") == "user"), "")
        if last_user_query:
            contextual_prompt = f"{last_user_query} -> {raw_prompt}"
        else:
            contextual_prompt = raw_prompt
    else:
        contextual_prompt = raw_prompt

    classification = router.classify(contextual_prompt)
    logger.info(
        f"[LangGraph:router_node] Query: '{raw_prompt[:35]}...' "
        f"(Contextual: '{contextual_prompt[:45]}...') -> Intent: {classification.intent}"
    )

    return {
        "intent": classification.intent,
        "direct_response": classification.direct_response,
        "is_course_query": classification.is_course_query
    }


# ==========================================
# NODE 2: RETRIEVAL NODE
# ==========================================
async def retrieval_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 2: Thực hiện True Hybrid Retrieval (Dense E5 + Sparse BM25) có In-HNSW Pre-filter.
    Áp dụng Conversational Query Reformulation để tăng cường độ hội tụ của vector tìm kiếm.
    """
    retrieval_service = get_retrieval_service()
    history = state.get("messages", [])
    raw_prompt = state["prompt"]

    if history:
        last_user_query = next((m["content"] for m in reversed(history) if m.get("role") == "user"), "")
        search_query = f"{last_user_query} {raw_prompt}" if last_user_query else raw_prompt
    else:
        search_query = raw_prompt

    try:
        retrieval_res: RetrievalResult = await retrieval_service.search(
            query_text=search_query,
            course_id=state["course_id"],
            current_lesson_seq=state["lesson_seq"],
            top_candidates=settings.DEFAULT_TOP_CANDIDATES,
            final_top_k=settings.DEFAULT_FINAL_TOP_K
        )
    except Exception as e:
        logger.error(f"[LangGraph:retrieval_node] Lỗi truy xuất Qdrant/RAG: {e}")
        retrieval_res = RetrievalResult(chunks=[], status="coverage_gap")

    return {
        "retrieved_chunks": retrieval_res.chunks,
        "retrieval_status": retrieval_res.status,
        "is_low_confidence": retrieval_res.is_low_confidence,
        "target_lesson_seq": retrieval_res.target_lesson_seq
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

    suggested_timestamps: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []
    has_approximate = False

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
{state['prompt']}
{caution_notice}
{context_block}"""

    elif retrieval_status == "out_of_lesson":
        active_system_prompt = OUT_OF_LESSON_PROMPT
        target_desc = f"Bài {target_lesson_seq}" if target_lesson_seq else "các bài học sau"
        user_message_content = f"""[CÂU HỎI CỦA HỌC VIÊN]
{state['prompt']}

[TIẾN ĐỘ BÀI HỌC]
- Khóa học: {state['course_id']}
- Bài học hiện tại của học viên: Bài {state['lesson_seq']}
- Bài học giảng dạy nội dung này: {target_desc}"""

    else:  # coverage_gap
        active_system_prompt = COVERAGE_GAP_PROMPT
        user_message_content = f"""[CÂU HỎI CỦA HỌC VIÊN]
{state['prompt']}

[THÔNG TIN PHẠM VI KHÓA HỌC]
- Khóa học: Lập trình C++ ({state['course_id']}), đang ở Bài {state['lesson_seq']}.
- Câu hỏi của học viên không nằm trong giáo trình bài giảng hoặc là chủ đề ngoài lề."""


    return {
        "is_approximate": has_approximate,
        "suggested_timestamps": suggested_timestamps,
        "sources": sources,
        "system_prompt": active_system_prompt,
        "user_message_content": user_message_content
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

    # 1. Thuật toán Sliding Window: Giữ lại tối đa 5 turns gần nhất (10 tin nhắn)
    SLIDING_WINDOW_TURNS = 5
    max_history_count = SLIDING_WINDOW_TURNS * 2
    raw_sliding_history = (
        history_messages[-max_history_count:]
        if len(history_messages) > max_history_count
        else list(history_messages)
    )

    # 2. Token Budget Pruning: Khống chế độ dài lịch sử <= 2,400 ký tự (~800 tokens)
    # Cắt tỉa các khối code dài ở các lượt cũ để bảo vệ KV Cache Prefill
    MAX_HISTORY_CHARS = 2400
    sliding_history: List[Dict[str, str]] = []
    accumulated_chars = 0

    # Duyệt ngược từ tin nhắn mới nhất về cũ nhất trong cửa sổ trượt
    for msg in reversed(raw_sliding_history):
        content = msg.get("content", "")
        role = msg.get("role", "user")

        # Rút gọn code block dài trong các câu trả lời cũ của assistant
        if role == "assistant" and "```" in content and len(content) > 350:
            content = re.sub(
                r"```(?:cpp|c\+\+|c)?\n.*?```",
                "[...khung code minh họa ở lượt trước...]",
                content,
                flags=re.DOTALL
            )

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

    # Pedagogical Soft Nudge: Khích lệ tự thực hành khi phiên kéo dài liên tục
    if turn_count > 6:
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


def commit_assistant_turn(session_id: str, user_prompt: str, assistant_response: str) -> None:
    """
    Lưu vết cặp tin nhắn (User + Assistant) vào StateGraph Checkpointer theo thread_id.
    Tự động kích hoạt thuật toán nén Conversation Summarizer khi số lượt > 6.
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

    # Nén tóm tắt nếu vượt quá 6 lượt đối thoại (> 10 tin nhắn lịch sử)
    summary = current_values.get("conversation_summary")
    if current_turn > 6 and len(history) > 10:
        overflow_msgs = history[:-10]
        topics = [
            f"Lượt {idx//2 + 1}: {m['content'][:60]}"
            for idx, m in enumerate(overflow_msgs) if m["role"] == "user"
        ]
        summary = f"Học viên đã thảo luận về: {'; '.join(topics)}."

    graph.update_state(config, {
        "messages": history,
        "turn_count": current_turn,
        "conversation_summary": summary
    })
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
        "assembled_messages": []
    })
    # Đồng bộ đặt lại lịch sử tần suất trong Rate Limiter
    get_session_rate_limiter().reset_session(session_id)
    logger.info(f"[LangGraph:Checkpointer] Đã reset trạng thái và rate limiter cho Session '{session_id}'.")
