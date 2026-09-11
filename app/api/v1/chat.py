from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.schemas.chat import ChatRequest
from app.services.chat import ChatService, get_chat_service

router = APIRouter(prefix="/chat", tags=["Socratic Chat"])


@router.post(
    "/stream",
    summary="Phát luồng hội thoại Socratic thời gian thực (SSE Stream)",
    description="""
    Nhận câu hỏi của học viên, phân loại ý định (Chit-chat / Out-of-Scope / Course Query),
    truy xuất tài liệu đa phương thức (AST Code + Video Transcript),
    và phát luồng sự kiện SSE:
    - Event 1: `metadata` (chứa danh sách sources, mốc timestamp video, cờ approximate fallback)
    - Event 2..N: `delta` (chứa từng token văn bản Socratic từ LLM)
    - Event N+1: `done` (kết thúc truyền phát)
    """,
    response_class=EventSourceResponse
)
async def stream_socratic_chat(
    request: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service)
):
    """
    Endpoint phát luồng Server-Sent Events (SSE) theo chuẩn W3C EventSource.
    """
    event_generator = chat_service.stream_chat(request)
    return EventSourceResponse(
        event_generator,
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
