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
from langgraph.graph import StateGraph, END

from app.agent.router import get_intent_router
from app.services.retrieval import get_retrieval_service, RetrievalResult
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
    """
    # 1. Inputs từ học viên
    prompt: str
    course_id: str
    lesson_seq: int

    # 2. Định tuyến ý định (Intent Routing)
    intent: str
    direct_response: Optional[str]
    is_course_query: bool

    # 3. Kết quả truy xuất & Thẩm định CRAG
    retrieval_status: str
    retrieved_chunks: List[Dict[str, Any]]
    is_approximate: bool
    is_low_confidence: bool
    target_lesson_seq: Optional[int]
    suggested_timestamps: List[Dict[str, Any]]
    sources: List[Dict[str, Any]]

    # 4. Đóng gói Prompt Socratic cho LLM Generation
    system_prompt: str
    user_message_content: str


def _format_context_block(chunks: List[Dict[str, Any]]) -> str:
    """
    Định dạng các chunks ngữ cảnh thành khối văn bản có cấu trúc rõ ràng cho LLM.
    """
    if not chunks:
        return "[LƯU Ý: Không tìm thấy tài liệu bài giảng nào vượt qua ngưỡng tin cậy cho câu hỏi này. Hãy hướng dẫn học viên dựa trên kiến thức chuẩn của C++]."

    blocks = ["[NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC]"]
    for idx, chunk in enumerate(chunks, 1):
        c_type = chunk.get("content_type", "unknown")
        lesson_id = chunk.get("lesson_id", "unknown")
        lesson_seq = chunk.get("lesson_seq", "?")
        conf_pct = chunk.get("confidence_pct", 0.0)
        is_approx = chunk.get("is_approximate", False)

        header = f"--- Tài liệu {idx} (Loại: {c_type} | Bài: {lesson_id} (Seq: {lesson_seq}) | Độ tin cậy: {conf_pct:.1f}%"
        if is_approx:
            header += " [Mốc tham khảo gần nhất]"
        header += ") ---"

        blocks.append(header)

        if c_type == "code_ast":
            file_p = chunk.get("file_path", "")
            scope = chunk.get("code_scope", "")
            code_content = chunk.get("context_code") or chunk.get("raw_text", "")
            blocks.append(f"Mã nguồn ({file_p} - Phạm vi: {scope}):\n```cpp\n{code_content}\n```")
        else:
            tag = chunk.get("timestamp_tag", "")
            sec = chunk.get("start_sec")
            label = chunk.get("start_label", "")
            raw_t = chunk.get("raw_text", "")
            blocks.append(f"Video Timestamp: {tag} (Bắt đầu tại {label} - {sec}s)\nNội dung giảng viên: {raw_t}")

    return "\n".join(blocks)


# ==========================================
# NODE 1: INTENT ROUTER NODE
# ==========================================
async def router_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 1: Phân loại ý định người dùng qua Multi-Class Semantic Router (Aurelio AI).
    """
    router = get_intent_router()
    classification = router.classify(state["prompt"])
    logger.info(f"[LangGraph:router_node] Prompt: '{state['prompt'][:35]}...' -> Intent: {classification.intent}")

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
    """
    retrieval_service = get_retrieval_service()
    try:
        retrieval_res: RetrievalResult = await retrieval_service.search(
            query_text=state["prompt"],
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
                    "title": chunk.get("video_title", "Đoạn video bài giảng liên quan")
                })
            elif chunk.get("content_type") == "code_ast" and chunk.get("approx_video_sec") is not None:
                v_sec = int(chunk["approx_video_sec"])
                suggested_timestamps.append({
                    "sec": v_sec,
                    "label": f"{v_sec//60:02d}:{v_sec%60:02d}",
                    "title": f"Bài giảng giải thích cú pháp [{chunk.get('code_scope', 'Code AST')}]"
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
{context_block}

HƯỚNG DẪN BẮT BUỘC:
- Hãy giải thích bản chất vấn đề và đặt câu hỏi gợi mở theo phương pháp Socratic.
- TUYỆT ĐỐI KHÔNG viết code giải hoàn chỉnh hộ học viên.
- Trích dẫn mốc thời gian từ tài liệu video trong phần ngữ cảnh trên dưới dạng thẻ bắt buộc:
  <timestamp sec="xxx">mm:ss</timestamp>
  để học viên có thể click tua nhanh video."""

    elif retrieval_status == "out_of_lesson":
        active_system_prompt = OUT_OF_LESSON_PROMPT
        target_desc = f"Bài {target_lesson_seq}" if target_lesson_seq else "các bài học sau"
        user_message_content = f"""[CÂU HỎI CỦA HỌC VIÊN]
{state['prompt']}

[THÔNG TIN TIẾN ĐỘ BÀI HỌC]
- Khóa học: {state['course_id']}
- Bài học hiện tại của học viên: Bài {state['lesson_seq']}
- Bài học giảng dạy nội dung này: {target_desc}

HƯỚNG DẪN TRẢ LỜI:
1. Nhẹ nhàng thông báo cho học viên biết chủ đề này sẽ được học ở {target_desc}, hiện tại ở Bài {state['lesson_seq']} bạn hãy nắm chắc kiến thức nền tảng trước nhé.
2. Nêu ngắn gọn 1-2 câu trực quan về khái niệm này.
3. Đặt 1 câu hỏi gợi mở Socratic liên hệ lại bài học hiện tại.
4. TUYỆT ĐỐI CẤM sinh bất kỳ thẻ <timestamp> nào."""

    else:  # coverage_gap
        active_system_prompt = COVERAGE_GAP_PROMPT
        user_message_content = f"""[CÂU HỎI CỦA HỌC VIÊN]
{state['prompt']}

[THÔNG TIN PHẠM VI KHÓA HỌC]
- Khóa học: Lập trình C++ ({state['course_id']}), đang ở Bài {state['lesson_seq']}.
- Câu hỏi của học viên không nằm trong giáo trình bài giảng hoặc là chủ đề ngoài lề.

HƯỚNG DẪN TRẢ LỜI:
- Nếu là câu hỏi ngoài lề đời sống (ăn uống, thời tiết, giải trí,...): Phản hồi thân thiện, hài hước và nhắc học viên quay lại hỏi về bài học C++.
- Nếu là câu hỏi công nghệ/ngôn ngữ khác: Nêu ngắn gọn 1 câu khách quan và mời học viên đặt các câu hỏi liên quan đến C++.
- TUYỆT ĐỐI CẤM sinh bất kỳ thẻ <timestamp> nào."""

    return {
        "is_approximate": has_approximate,
        "suggested_timestamps": suggested_timestamps,
        "sources": sources,
        "system_prompt": active_system_prompt,
        "user_message_content": user_message_content
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
def build_chat_graph():
    """
    Khởi tạo và biên dịch StateGraph cho Agentic RAG Copilot.
    """
    workflow = StateGraph(AgentState)

    # Đăng ký các Nodes
    workflow.add_node("router", router_node)
    workflow.add_node("retrieval", retrieval_node)
    workflow.add_node("crag_grader", crag_grader_node)

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
    workflow.add_edge("crag_grader", END)

    # Biên dịch đồ thị trạng thái
    compiled_graph = workflow.compile()
    logger.info("[LangGraph] Đã biên dịch thành công Chat StateGraph (3 Discrete Nodes & Conditional Routing).")
    return compiled_graph


# Singleton ChatGraph instance
_compiled_chat_graph = None


def get_chat_graph():
    global _compiled_chat_graph
    if _compiled_chat_graph is None:
        _compiled_chat_graph = build_chat_graph()
    return _compiled_chat_graph
