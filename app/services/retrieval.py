import logging
import math
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Literal, Tuple
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from app.config import settings
from app.services.qdrant import get_async_qdrant_client
from app.services.embedding import EmbeddingService, get_embedding_service

logger = logging.getLogger("uvicorn.error")


@dataclass
class RetrievalResult:
    """
    Kết quả truy xuất ngữ cảnh bài học chuẩn hóa:
    - chunks: Danh sách các đoạn trích dẫn (U-shaped assembly)
    - status: 'grounded' (có tài liệu), 'out_of_lesson' (bài học tương lai), 'coverage_gap' (ngoài giáo trình)
    - target_lesson_seq: Thứ tự bài học tương lai nếu bị chặn bởi In-HNSW Pre-filter
    - is_low_confidence: Cờ đánh dấu Graceful Degradation (0.20 <= score < 0.35)
    """
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    status: Literal["grounded", "out_of_lesson", "coverage_gap"] = "coverage_gap"
    target_lesson_seq: Optional[int] = None
    is_low_confidence: bool = False

    def __iter__(self):
        return iter(self.chunks)

    def __len__(self):
        return len(self.chunks)

    def __getitem__(self, item):
        return self.chunks[item]

    def __bool__(self):
        return bool(self.chunks)


def sanitize_text(text: str) -> str:
    """
    Chuẩn hóa văn bản trả về:
    - Loại bỏ ký tự carriage return và các ký tự điều khiển.
    - Lọc bỏ các ký tự ngoại ngữ lạ (Hangul, Hanja,...) do lỗi âm học mô hình sinh ra.
    """
    if not text:
        return ""
    text = text.replace("\r", " ").replace("\ufffd", "")
    text = re.sub(r"[\uac00-\ud7af\u1100-\u11ff\u4e00-\u9fff]", "", text)
    return " ".join(text.split())


def reorder_lost_in_the_middle(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Khắc phục hiện tượng 'Lost-in-the-Middle' (Liu et al., Stanford 2024).
    Sắp xếp các chunks theo cấu trúc hình chữ U:
    - Chunk có độ liên quan cao nhất ở đầu (vị trí 1)
    - Chunk cao thứ nhì ở cuối danh sách
    - Các chunk còn lại nằm ở phần giữa
    Ví dụ với 3 chunks: [Top 1, Top 3, Top 2]
    """
    if len(items) <= 2:
        return items

    sorted_items = sorted(
        items,
        key=lambda x: x.get("confidence_score", x.get("rrf_score", 0.0)),
        reverse=True
    )
    reordered: List[Optional[Dict[str, Any]]] = [None] * len(sorted_items)
    left = 0
    right = len(sorted_items) - 1

    for i, item in enumerate(sorted_items):
        if i % 2 == 0:
            reordered[left] = item
            left += 1
        else:
            reordered[right] = item
            right -= 1

    return [item for item in reordered if item is not None]


def sigmoid(z: float) -> float:
    """
    Logistic Sigmoid Normalization: Chuyển đổi raw logits (-inf, +inf) sang xác suất thực [0.0, 1.0].
    """
    clipped = max(-250.0, min(250.0, z))
    return float(1.0 / (1.0 + math.exp(-clipped)))


def grade_document_relevance(query: str, item: Dict[str, Any]) -> str:
    """
    CRAG Document Relevance Grader (Yan et al., Meta AI 2024):
    Thẩm định độ tương quan thực tế giữa Query và Chunk trước khi cho phép nạp vào Prompt.
    Trả về 'CORRECT' nếu tài liệu thực sự liên quan, hoặc 'INCORRECT' nếu lạc đề.
    """
    prob = float(item.get("confidence_score", 0.0))
    text = (item.get("raw_text", "") + " " + item.get("context_code", "")).lower()
    query_lower = query.lower()

    # 1. Nếu điểm Cross-Encoder rất cao (>= 0.45), tin cậy vào mô hình
    if prob >= 0.45:
        return "CORRECT"

    # 2. Bóc tách các từ khóa thực thể ngoài lề đời sống
    casual_words = [
        "nhậu", "uống bia", "uống rượu", "thịt bò", "ăn lẩu", "đi chơi", "hát karaoke",
        "chơi game", "bóng đá", "tình cảm", "giải rượu", "nấu ăn", "thời tiết"
    ]
    has_casual_query = any(cw in query_lower for cw in casual_words)

    # Nếu câu hỏi chứa thực thể đời sống mà nội dung tài liệu hoàn toàn không có thực thể tương ứng -> INCORRECT
    if has_casual_query and not any(cw in text for cw in casual_words):
        logger.info(
            f"[CRAG Grader] Chunk {item.get('id')} bị đánh giá INCORRECT: Câu hỏi chứa từ đời sống ngoài lề không khớp tài liệu."
        )
        return "INCORRECT"

    # 3. Với video transcript điểm biên (0.22 <= prob < 0.30), kiểm tra có thuật ngữ kỹ thuật chung không
    stop_words = {
        "cho", "em", "hỏi", "với", "là", "gì", "thế", "nào", "trong", "bài", "thì",
        "có", "không", "nhé", "ạ", "ơi", "bạn", "thầy", "tôi", "mình", "làm", "sao",
        "được", "và", "ở", "này", "đó", "của", "để", "như", "một", "các", "hello", "hi"
    }
    raw_tokens = re.findall(r"\b[\w\+\#]+\b", query_lower)
    content_tokens = [t for t in raw_tokens if t not in stop_words and len(t) >= 2]

    # Nếu có từ khóa nội dung nhưng không có từ nào xuất hiện trong chunk và prob < 0.30 -> INCORRECT
    if content_tokens and not any(t in text for t in content_tokens) and prob < 0.30:
        logger.info(
            f"[CRAG Grader] Chunk {item.get('id')} bị đánh giá INCORRECT: Thiếu liên kết thực thể (Prob: {prob:.4f} < 0.30)."
        )
        return "INCORRECT"

    return "CORRECT"


class RetrievalService:
    """
    Lõi Dịch vụ Tìm kiếm Đa phương thức 11 Giai đoạn (Stage 6 -> 9) chuẩn Enterprise:
    - True Hybrid Retrieval (Parallel Prefetch: Dense E5 + Sparse BM25)
    - In-HNSW Dynamic Pre-filtering (course_id & lesson_seq <= current_seq)
    - Qdrant Native Reciprocal Rank Fusion (RRF)
    - Stage 8: Multilingual Cross-Encoder Reranker (Jina-v2) + Logistic Sigmoid
    - Corrective RAG (CRAG) Document Relevance Grader (Meta AI 2024)
    - Graceful Degradation (0.20 <= score < 0.35)
    - Future Lesson Probe: Phân biệt rõ ràng giữa Out-of-Lesson (bài tương lai) và Coverage-Gap (ngoài giáo trình)
    - Stage 9: U-shaped Context Assembly chống Lost-in-the-Middle
    """

    def __init__(
        self,
        client: Optional[AsyncQdrantClient] = None,
        embedding_service: Optional[EmbeddingService] = None
    ):
        self.client = client or get_async_qdrant_client()
        self.embedding_service = embedding_service or get_embedding_service()

    async def _probe_future_lessons(
        self,
        query_dense: List[float],
        sparse_indices: List[int],
        sparse_values: List[float],
        query_text: str,
        course_id: str,
        current_lesson_seq: int
    ) -> Tuple[Optional[int], float]:
        """
        Kiểm tra xem câu hỏi có thuộc về bài học tương lai (> current_lesson_seq) của khóa học hay không.
        Trả về (target_lesson_seq, max_confidence_score).
        """
        future_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="course_id",
                    match=models.MatchValue(value=course_id)
                ),
                models.FieldCondition(
                    key="lesson_seq",
                    range=models.Range(gt=current_lesson_seq)
                )
            ]
        )

        try:
            future_resp = await self.client.query_points(
                collection_name=settings.QDRANT_COLLECTION_NAME,
                prefetch=[
                    models.Prefetch(
                        query=query_dense,
                        using="dense",
                        filter=future_filter,
                        limit=5
                    ),
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=sparse_indices,
                            values=sparse_values
                        ),
                        using="sparse",
                        filter=future_filter,
                        limit=5
                    )
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=5
            )

            future_points = future_resp.points
            if not future_points:
                return None, 0.0

            future_texts: List[str] = []
            future_seqs: List[int] = []

            for hit in future_points:
                p = hit.payload or {}
                future_seqs.append(int(p.get("lesson_seq", 0)))
                c_type = p.get("content_type", "video_transcript")
                if c_type == "code_ast":
                    ctx_code = p.get("context_code") or p.get("raw_text", "")
                    code_lang = p.get("code_language") or p.get("language", "cpp")
                    future_texts.append(f"[Mã nguồn {code_lang.upper()} - {p.get('code_scope', '')}]\n{ctx_code}")
                else:
                    vid_title = p.get("video_title", "video_lecture.mp4")
                    start_lbl = p.get("start_label", "")
                    raw_txt = sanitize_text(p.get("raw_text", ""))
                    future_texts.append(f"[Bài giảng Video {vid_title} mốc {start_lbl}]\n{raw_txt}")

            try:
                raw_logits = self.embedding_service.rerank_documents(query=query_text, documents=future_texts)
                scores = [sigmoid(val) for val in raw_logits]
            except Exception as re_err:
                logger.warning(f"[RetrievalService] Lỗi rerank future probe ({re_err}), dùng RRF score.")
                scores = [float(hit.score) for hit in future_points]

            max_idx = 0
            max_score = 0.0
            for idx, sc in enumerate(scores):
                if sc > max_score:
                    max_score = sc
                    max_idx = idx

            target_seq = future_seqs[max_idx] if future_seqs else None
            return target_seq, max_score

        except Exception as probe_err:
            logger.warning(f"[RetrievalService] Lỗi khi probe future lessons ({probe_err}).")
            return None, 0.0

    async def search(
        self,
        query_text: str,
        course_id: str = "cpp-core",
        current_lesson_seq: int = 2,
        top_candidates: int = settings.DEFAULT_TOP_CANDIDATES,
        final_top_k: int = settings.DEFAULT_FINAL_TOP_K,
        min_score_threshold: Optional[float] = None,
        code_score_threshold: Optional[float] = None,
        video_score_threshold: Optional[float] = None,
    ) -> RetrievalResult:
        """
        Thực hiện tìm kiếm ngữ cảnh bài học bất đồng bộ (non-blocking).
        Trả về RetrievalResult gồm chunks và trạng thái phân loại 3 nhánh:
        - 'grounded': Tìm thấy ngữ cảnh bài học hợp lệ trong phạm vi cho phép.
        - 'out_of_lesson': Ngữ cảnh bị chặn bởi cửa sổ tiến độ bài học (thuộc bài tương lai).
        - 'coverage_gap': Chủ đề hoàn toàn ngoài phạm vi khóa học hoặc ngoài lề.
        """
        logger.info(
            f"[RetrievalService] Query: '{query_text}' | Course: {course_id} | Window: lesson_seq <= {current_lesson_seq}"
        )

        # 1. Sinh Dual Vectors bất đồng bộ / fast ONNX
        query_dense = self.embedding_service.embed_query_dense(query_text)
        sparse_indices, sparse_values = self.embedding_service.embed_query_sparse(query_text)

        # 2. Xây dựng In-HNSW Pre-filter động (Ngăn ngừa triệt để hiện tượng lộ bài học tương lai)
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="course_id",
                    match=models.MatchValue(value=course_id)
                ),
                models.FieldCondition(
                    key="lesson_seq",
                    range=models.Range(lte=current_lesson_seq)
                )
            ]
        )

        # 3. [STAGE 6 & 7] Song song hóa Prefetch: Dense + Sparse với Native RRF Fusion
        response = await self.client.query_points(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            prefetch=[
                models.Prefetch(
                    query=query_dense,
                    using="dense",
                    filter=query_filter,
                    limit=top_candidates
                ),
                models.Prefetch(
                    query=models.SparseVector(
                        indices=sparse_indices,
                        values=sparse_values
                    ),
                    using="sparse",
                    filter=query_filter,
                    limit=top_candidates
                )
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_candidates
        )

        raw_candidates = response.points
        logger.info(f"[RetrievalService] Lấy được {len(raw_candidates)} chunks ứng viên qua thuật toán RRF.")

        # Nếu hoàn toàn không có candidate nào trong phạm vi bài hiện tại
        if not raw_candidates:
            target_seq, future_score = await self._probe_future_lessons(
                query_dense=query_dense,
                sparse_indices=sparse_indices,
                sparse_values=sparse_values,
                query_text=query_text,
                course_id=course_id,
                current_lesson_seq=current_lesson_seq
            )
            if target_seq and future_score >= settings.VIDEO_SCORE_THRESHOLD:
                logger.info(f"[RetrievalService] Phát hiện chủ đề thuộc bài tương lai (Seq {target_seq}) với điểm {future_score:.4f}.")
                return RetrievalResult(chunks=[], status="out_of_lesson", target_lesson_seq=target_seq)
            return RetrievalResult(chunks=[], status="coverage_gap")

        # 4. [STAGE 8] Multilingual Cross-Encoder Re-ranking & Logistic Sigmoid Normalization
        candidate_items: List[Dict[str, Any]] = []
        texts_to_rerank: List[str] = []

        for hit in raw_candidates:
            raw_rrf = float(hit.score)
            p = hit.payload or {}
            content_type = p.get("content_type", "video_transcript")

            item: Dict[str, Any] = {
                "id": str(hit.id),
                "rrf_score": round(raw_rrf, 4),
                "content_type": content_type,
                "lesson_id": p.get("lesson_id", ""),
                "lesson_seq": p.get("lesson_seq", 0),
                "raw_text": sanitize_text(p.get("raw_text", "")),
            }

            if content_type == "code_ast":
                ctx_code = p.get("context_code") or p.get("raw_text", "")
                code_lang = p.get("code_language") or p.get("language", "cpp")
                item.update({
                    "file_path": p.get("file_path", ""),
                    "language": code_lang,
                    "code_scope": p.get("code_scope", ""),
                    "start_line": p.get("start_line", 0),
                    "end_line": p.get("end_line", 0),
                    "context_code": ctx_code
                })
                texts_to_rerank.append(f"[Mã nguồn {code_lang.upper()} - {p.get('code_scope', '')}]\n{ctx_code}")
            else:
                start_sec = int(p.get("start_sec", 0))
                end_sec = int(p.get("end_sec", 0))
                start_lbl = p.get("start_label") or f"{start_sec//60:02d}:{start_sec%60:02d}"
                end_lbl = p.get("end_label") or f"{end_sec//60:02d}:{end_sec%60:02d}"
                vid_title = p.get("video_title", "video_lecture.mp4")

                item.update({
                    "video_title": vid_title,
                    "start_sec": start_sec,
                    "end_sec": end_sec,
                    "start_label": start_lbl,
                    "end_label": end_lbl,
                    "timestamp_tag": f'<timestamp sec="{start_sec}">{start_lbl}</timestamp>'
                })
                texts_to_rerank.append(f"[Bài giảng Video {vid_title} mốc {start_lbl}]\n{item['raw_text']}")

            candidate_items.append(item)

        # Chấm điểm Cross-Encoder vi mô
        is_fallback_rrf = False
        try:
            raw_logits = self.embedding_service.rerank_documents(query=query_text, documents=texts_to_rerank)
        except Exception as rerank_err:
            logger.error(f"[RetrievalService] Lỗi Cross-Encoder ({rerank_err}), fallback sang RRF score.")
            raw_logits = [item["rrf_score"] for item in candidate_items]
            is_fallback_rrf = True

        # Xác định ngưỡng phân tầng đa phương thức
        effective_code_threshold = code_score_threshold if code_score_threshold is not None else (
            min_score_threshold if min_score_threshold is not None else settings.CODE_SCORE_THRESHOLD
        )
        effective_video_threshold = video_score_threshold if video_score_threshold is not None else (
            min_score_threshold if min_score_threshold is not None else settings.VIDEO_SCORE_THRESHOLD
        )

        # Áp dụng Logistic Sigmoid và Lọc theo ngưỡng phân tầng
        scored_items: List[Dict[str, Any]] = []
        discarded_videos: List[Dict[str, Any]] = []
        has_high_confidence_code = False

        for i, item in enumerate(candidate_items):
            score_val = raw_logits[i] if i < len(raw_logits) else 0.0
            prob = score_val if is_fallback_rrf else sigmoid(score_val)

            item["confidence_score"] = round(prob, 4)
            item["confidence_pct"] = round(prob * 100, 2)

            c_type = item.get("content_type", "video_transcript")
            threshold = effective_code_threshold if c_type == "code_ast" else effective_video_threshold

            if prob >= threshold:
                scored_items.append(item)
                if c_type == "code_ast" and prob >= 0.60:
                    has_high_confidence_code = True
            else:
                if c_type == "video_transcript":
                    discarded_videos.append(item)
                logger.debug(
                    f"[RetrievalService] Bỏ qua chunk {item['id']} ({c_type}) vì độ tin cậy {prob:.4f} < {threshold}"
                )

        # Best-Effort In-Course Video Fallback (Phase 1 Roadmap):
        has_video_in_scored = any(it.get("content_type") != "code_ast" for it in scored_items)
        if has_high_confidence_code and not has_video_in_scored and discarded_videos:
            eligible_fallback_videos = [
                v for v in discarded_videos
                if v.get("confidence_score", 0.0) >= settings.VIDEO_FALLBACK_MIN_THRESHOLD
            ]
            if eligible_fallback_videos:
                best_fallback_video = max(eligible_fallback_videos, key=lambda x: x.get("confidence_score", 0.0))
                best_fallback_video["is_approximate"] = True
                scored_items.append(best_fallback_video)
                logger.info(
                    f"[RetrievalService] Best-Effort Fallback kích hoạt: Chọn video mốc {best_fallback_video.get('start_label')} "
                    f"với độ tin cậy {best_fallback_video.get('confidence_score'):.4f} >= {settings.VIDEO_FALLBACK_MIN_THRESHOLD}."
                )

        # [CRAG Stage: Document Relevance Grading (Meta AI 2024)]
        # Thẩm định độ tương quan thực tế giữa câu hỏi và các tài liệu trước khi nạp vào Prompt
        crag_verified_items = [
            it for it in scored_items
            if grade_document_relevance(query_text, it) == "CORRECT"
        ]

        # TH1: Có tài liệu vượt qua thẩm định CRAG -> Trạng thái 'grounded'
        if crag_verified_items:
            top_reranked = sorted(
                crag_verified_items,
                key=lambda x: x["confidence_score"],
                reverse=True
            )[:final_top_k]
            final_assembled = reorder_lost_in_the_middle(top_reranked)
            logger.info(f"[RetrievalService] Hoàn tất CRAG Verification với {len(final_assembled)} chunks hợp lệ.")
            return RetrievalResult(
                chunks=final_assembled,
                status="grounded",
                is_low_confidence=False
            )

        # TH2: Không có tài liệu đạt ngưỡng chuẩn -> Thử Graceful Degradation có thẩm định CRAG
        low_confidence_items = [
            it for it in candidate_items
            if it.get("confidence_score", 0.0) >= 0.20 and grade_document_relevance(query_text, it) == "CORRECT"
        ]
        if low_confidence_items:
            logger.info(f"[RetrievalService] Kích hoạt Graceful Degradation: {len(low_confidence_items)} chunks đạt ngưỡng tham khảo >= 0.20.")
            top_low_conf = sorted(
                low_confidence_items,
                key=lambda x: x["confidence_score"],
                reverse=True
            )[:final_top_k]
            final_assembled = reorder_lost_in_the_middle(top_low_conf)
            return RetrievalResult(
                chunks=final_assembled,
                status="grounded",
                is_low_confidence=True
            )

        # TH3: Ngữ cảnh hoàn toàn không đạt ngưỡng sàn -> Probe bài học tương lai để phân định
        target_seq, future_score = await self._probe_future_lessons(
            query_dense=query_dense,
            sparse_indices=sparse_indices,
            sparse_values=sparse_values,
            query_text=query_text,
            course_id=course_id,
            current_lesson_seq=current_lesson_seq
        )
        if target_seq and future_score >= settings.VIDEO_SCORE_THRESHOLD:
            logger.info(
                f"[RetrievalService] Chủ đề thuộc bài học tương lai (Seq {target_seq}) với độ tin cậy {future_score:.4f}."
            )
            return RetrievalResult(chunks=[], status="out_of_lesson", target_lesson_seq=target_seq)

        logger.info("[RetrievalService] Không tìm thấy ngữ cảnh phù hợp cả hiện tại lẫn tương lai -> 'coverage_gap'.")
        return RetrievalResult(chunks=[], status="coverage_gap")


_retrieval_service: Optional[RetrievalService] = None


def get_retrieval_service() -> RetrievalService:
    """
    FastAPI Dependency Provider cho RetrievalService.
    """
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService()
    return _retrieval_service
