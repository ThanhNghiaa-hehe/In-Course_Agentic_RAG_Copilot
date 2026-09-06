from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ContentType(str, Enum):
    VIDEO_TRANSCRIPT = "video_transcript"
    CODE_AST = "code_ast"
    MARKDOWN_DOC = "markdown_doc"


class BaseChunkPayload(BaseModel):
    course_id: str = Field(..., description="ID khóa học (vd: backend-java)")
    lesson_id: str = Field(..., description="ID bài học cụ thể (vd: lesson-05)")
    lesson_seq: int = Field(..., description="Thứ tự bài học trong curriculum để phục vụ pre-filter")
    content_type: ContentType
    raw_text: str = Field(..., description="Văn bản sạch dùng cho LLM context")


class VideoChunkPayload(BaseChunkPayload):
    content_type: ContentType = ContentType.VIDEO_TRANSCRIPT
    video_id: str = Field(..., description="ID hoặc link bài giảng video")
    start_sec: int = Field(..., ge=0, description="Giây bắt đầu của đoạn phát biểu")
    end_sec: int = Field(..., ge=0, description="Giây kết thúc của đoạn phát biểu")
    speaker_tag: Optional[str] = Field(default="instructor", description="Người nói")


class CodeChunkPayload(BaseChunkPayload):
    content_type: ContentType = ContentType.CODE_AST
    file_path: str = Field(..., description="Đường dẫn file (vd: src/UserService.java)")
    language: str = Field(..., description="Ngôn ngữ lập trình (java, python, javascript)")
    code_scope: str = Field(..., description="Phạm vi code (vd: UserService.findById)")
    start_line: int = Field(..., ge=1)
    end_line: int = Field(..., ge=1)


class DocChunkPayload(BaseChunkPayload):
    content_type: ContentType = ContentType.MARKDOWN_DOC
    section_title: str = Field(..., description="Tiêu đề đề mục tài liệu")
    file_name: str
