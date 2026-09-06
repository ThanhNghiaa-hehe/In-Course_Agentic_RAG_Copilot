from typing import List, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    prompt: str = Field(..., description="Câu hỏi hoặc thắc mắc về bài học/code của học viên")
    course_id: str = Field(..., description="Mã khóa học hiện tại")
    lesson_seq: int = Field(..., ge=1, description="Thứ tự bài học hiện tại (dùng để pre-filter)")
    current_video_sec: Optional[int] = Field(default=None, ge=0, description="Mốc thời gian hiện tại của video trên player")


class SuggestedTimestamp(BaseModel):
    sec: int = Field(..., ge=0)
    label: str = Field(..., description="Định dạng mm:ss")
    title: str = Field(..., description="Mô tả ngắn gọn nội dung giảng viên nói")


class StreamMetadataEvent(BaseModel):
    suggested_timestamps: List[SuggestedTimestamp] = Field(default_factory=list)
    retrieved_chunk_count: int = 0
    used_fast_path: bool = False
