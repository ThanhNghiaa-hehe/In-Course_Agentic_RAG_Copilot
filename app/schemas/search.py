from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


class SearchRequest(BaseModel):
    """
    Schema xác thực dữ liệu đầu vào cho API tìm kiếm bài học.
    Đảm bảo an toàn dữ liệu và tuân thủ nguyên tắc In-HNSW Pre-filtering.
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "Cách khai báo hằng số const và ép kiểu trong C++",
                "course_id": "cpp-core",
                "lesson_seq": 2,
                "top_candidates": 10,
                "final_top_k": 3,
                "min_score_threshold": 0.35
            }
        }
    )

    query: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Câu hỏi thắc mắc về bài học hoặc mã nguồn của học viên"
    )
    course_id: str = Field(
        default="cpp-core",
        description="Mã định danh khóa học hiện tại"
    )
    lesson_seq: int = Field(
        default=2,
        ge=1,
        description="Thứ tự bài học hiện tại (chống lộ bài tương lai: lesson_seq <= current_seq)"
    )
    top_candidates: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Số lượng chunks ứng viên ban đầu lấy qua True Hybrid RRF"
    )
    final_top_k: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Số lượng chunks tối ưu sau khi xếp hạng và U-shaped assembly"
    )
    min_score_threshold: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        description="Ngưỡng lọc điểm tin cậy RRF tối thiểu"
    )


class SearchChunkResult(BaseModel):
    """
    Schema chi tiết cho một chunk ngữ cảnh đa phương thức (Video Transcript hoặc Code AST).
    """
    id: str = Field(..., description="UUID định danh duy nhất của Point trên Qdrant Cloud")
    content_type: Literal["video_transcript", "code_ast", "markdown_doc"] = Field(
        ...,
        description="Phân loại dữ liệu đa phương thức"
    )
    rrf_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Điểm số dung hợp thứ hạng nghịch đảo Reciprocal Rank Fusion (RRF)"
    )
    confidence_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Độ tin cậy được quy đổi theo tỷ lệ phần trăm trực quan"
    )
    lesson_id: str = Field(..., description="ID bài học (vd: lesson-01, lesson-02)")
    lesson_seq: int = Field(..., description="Thứ tự bài học trong giáo trình")
    raw_text: str = Field(..., description="Nội dung văn bản sạch phục vụ LLM Context")

    # Thuộc tính đặc thù cho Video Transcript (Multimodal Video Sync)
    video_title: Optional[str] = Field(default=None, description="Tên file bài giảng video")
    start_sec: Optional[int] = Field(default=None, ge=0, description="Mốc giây bắt đầu trong video")
    end_sec: Optional[int] = Field(default=None, ge=0, description="Mốc giây kết thúc trong video")
    start_label: Optional[str] = Field(default=None, description="Nhãn thời gian hiển thị (định dạng mm:ss)")
    end_label: Optional[str] = Field(default=None, description="Nhãn thời gian kết thúc (định dạng mm:ss)")
    timestamp_tag: Optional[str] = Field(
        default=None,
        description="Thẻ tua video chuẩn: <timestamp sec=\"xxx\">mm:ss</timestamp>"
    )

    # Thuộc tính đặc thù cho Code AST (Tree-sitter Source Chunk)
    file_path: Optional[str] = Field(default=None, description="Đường dẫn file mã nguồn mẫu")
    language: Optional[str] = Field(default=None, description="Ngôn ngữ lập trình (cpp, java, python)")
    code_scope: Optional[str] = Field(default=None, description="Phạm vi cú pháp AST (tên hàm, class)")
    start_line: Optional[int] = Field(default=None, ge=1, description="Dòng code bắt đầu trong file")
    end_line: Optional[int] = Field(default=None, ge=1, description="Dòng code kết thúc trong file")


class SearchResponse(BaseModel):
    """
    Schema kết quả trả về toàn diện của API tìm kiếm ngữ cảnh bài học.
    """
    query: str = Field(..., description="Câu hỏi gốc của học viên")
    course_id: str = Field(..., description="Khóa học tìm kiếm")
    current_lesson_seq: int = Field(..., description="Cửa sổ bài học tối đa được phép truy cập")
    total_retrieved: int = Field(..., description="Tổng số chunks vượt qua ngưỡng lọc tin cậy")
    results: List[SearchChunkResult] = Field(
        default_factory=list,
        description="Danh sách các chunks đã được sắp xếp hình chữ U chống Lost-in-the-Middle"
    )
