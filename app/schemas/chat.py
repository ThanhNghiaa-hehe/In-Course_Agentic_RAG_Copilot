from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    prompt: str = Field(..., description="Câu hỏi hoặc thắc mắc về bài học/code của học viên")
    course_id: str = Field(..., description="Mã khóa học hiện tại")
    lesson_seq: int = Field(..., ge=1, description="Thứ tự bài học hiện tại (dùng để pre-filter)")
    current_video_sec: Optional[int] = Field(default=None, ge=0, description="Mốc thời gian hiện tại của video trên player")
    session_id: Optional[str] = Field(default=None, description="Mã phiên hội thoại đa lượt của học viên (LangGraph thread_id)")


class SuggestedTimestamp(BaseModel):
    sec: int = Field(..., ge=0)
    label: str = Field(..., description="Định dạng mm:ss")
    title: str = Field(..., description="Mô tả ngắn gọn nội dung giảng viên nói")
    lesson_seq: Optional[int] = Field(default=None, description="Bài học sở hữu mốc video này (hỗ trợ Cross-Lesson Video Alignment)")


class RouterClassification(BaseModel):
    intent: Literal["chit_chat", "out_of_scope", "course_query", "confirm_navigation"] = Field(
        ...,
        description="Ý định người dùng: chào hỏi xã giao, ngoài lề, câu hỏi bài học, hoặc xác nhận hành động đàm thoại"
    )
    direct_response: Optional[str] = Field(
        default=None,
        description="Câu trả lời phản hồi trực tiếp nếu là chit_chat hoặc out_of_scope"
    )
    is_course_query: bool = Field(
        default=True,
        description="True nếu cần đi tiếp vào pipeline RAG"
    )


class StreamMetadataEvent(BaseModel):
    session_id: Optional[str] = Field(default=None, description="Mã phiên hội thoại được đồng bộ với LangGraph Checkpointer")
    turn_count: int = Field(default=1, description="Thứ tự lượt đối thoại trong phiên hiện tại")
    intent: Literal["chit_chat", "out_of_scope", "course_query", "confirm_navigation", "rate_limited"] = "course_query"
    suggested_timestamps: List[SuggestedTimestamp] = Field(default_factory=list)
    retrieved_chunk_count: int = 0
    used_fast_path: bool = False
    is_approximate: bool = False
    retrieval_status: Literal["grounded", "out_of_lesson", "coverage_gap", "fast_path"] = "grounded"
    is_low_confidence: bool = False
    target_lesson_seq: Optional[int] = None
    auto_seek_sec: Optional[int] = Field(
        default=None,
        description="Mốc giây video để Frontend tự động nhảy (seekTo) ngay lập tức tại miligiây thứ 350 (Ưu tiên 2: Fast-Path Progressive Streaming)"
    )
    action: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Lệnh điều khiển tương tác (ví dụ: navigate_and_seek) do Agent kích hoạt khi học viên xác nhận đàm thoại"
    )
    sources: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Danh sách nguồn trích dẫn phục vụ hiển thị source cards trên UI"
    )

