import logging
from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.search import SearchRequest, SearchResponse, SearchChunkResult
from app.services.retrieval import RetrievalService, get_retrieval_service

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/search", tags=["Multimodal Search"])


@router.post(
    "",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Tìm kiếm ngữ cảnh Đa phương thức (True Hybrid RRF: Video + Code AST)",
    description="""
    Thực hiện truy xuất ngữ cảnh bài học chuẩn Enterprise (Stage 6 -> 9):
    1. **Parallel Prefetch:** Bắn song song Dense Vector E5 (1024-dim) và Sparse BM25.
    2. **In-HNSW Dynamic Pre-filtering:** Giới hạn `course_id` và `lesson_seq <= current_seq` (ngăn chặn rò rỉ kiến thức tương lai).
    3. **Qdrant Native RRF Fusion:** Dung hợp thứ hạng nghịch đảo đa phương thức.
    4. **Confidence Thresholding:** Lọc theo ngưỡng tin cậy toán học (`min_score_threshold >= 0.35`).
    5. **Lost-in-the-Middle Mitigation:** Sắp xếp cấu trúc hình chữ U `[Top 1, Top 3, Top 2]`.
    """
)
async def search_course_context(
    request: SearchRequest,
    retrieval_service: RetrievalService = Depends(get_retrieval_service)
) -> SearchResponse:
    try:
        raw_chunks = await retrieval_service.search(
            query_text=request.query,
            course_id=request.course_id,
            current_lesson_seq=request.lesson_seq,
            top_candidates=request.top_candidates,
            final_top_k=request.final_top_k,
            min_score_threshold=request.min_score_threshold
        )

        results = [SearchChunkResult(**chunk) for chunk in raw_chunks]

        return SearchResponse(
            query=request.query,
            course_id=request.course_id,
            current_lesson_seq=request.lesson_seq,
            total_retrieved=len(results),
            results=results
        )
    except Exception as e:
        logger.error(f"[SearchAPI] Lỗi khi xử lý tìm kiếm ngữ cảnh: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi xử lý tìm kiếm đa phương thức: {str(e)}"
        )
