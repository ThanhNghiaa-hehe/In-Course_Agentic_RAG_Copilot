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
    video_title: str = Field(..., description="Tên file hoặc tiêu đề bài giảng video")
    start_sec: int = Field(..., ge=0, description="Giây bắt đầu của đoạn phát biểu")
    end_sec: int = Field(..., ge=0, description="Giây kết thúc của đoạn phát biểu")
    start_label: Optional[str] = Field(default=None, description="Mốc thời gian mm:ss bắt đầu")
    end_label: Optional[str] = Field(default=None, description="Mốc thời gian mm:ss kết thúc")
    speaker_tag: Optional[str] = Field(default="instructor", description="Người nói")


class CodeChunkPayload(BaseChunkPayload):
    content_type: ContentType = ContentType.CODE_AST
    file_path: str = Field(..., description="Đường dẫn file (vd: src/lesson_01.cpp)")
    language: Optional[str] = Field(default="cpp", description="Ngôn ngữ lập trình")
    code_language: Optional[str] = Field(default="cpp", description="Mã định danh ngôn ngữ")
    code_scope: str = Field(..., description="Phạm vi code (vd: function_main)")
    start_line: int = Field(..., ge=1)
    end_line: int = Field(..., ge=1)
    context_code: Optional[str] = Field(default=None, description="Mã nguồn kèm Header Preamble chuẩn AST")


class DocChunkPayload(BaseChunkPayload):
    content_type: ContentType = ContentType.MARKDOWN_DOC
    section_title: str = Field(..., description="Tiêu đề đề mục tài liệu")
    file_name: str

