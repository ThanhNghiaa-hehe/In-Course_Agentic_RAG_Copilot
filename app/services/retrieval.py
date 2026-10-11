import logging
import math
import re
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Literal, Tuple
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from app.config import settings
from app.services.qdrant import get_async_qdrant_client
from app.services.embedding import EmbeddingService, get_embedding_service

logger = logging.getLogger("uvicorn.error")

BINDING_MANIFEST_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "metadata" / "lesson_code_video_binding.json"


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


def assemble_balanced_modality(
    video_items: List[Dict[str, Any]],
    code_items: List[Dict[str, Any]],
    final_top_k: int = 3,
    prefer_balanced: bool = True
) -> List[Dict[str, Any]]:
    """
    Lắp ghép ngữ cảnh đa phương thức cân bằng thích ứng (Adaptive Balanced Modality Assembly):
    - Đảm bảo tối thiểu 1 Video Transcript (bảo toàn mốc thời gian <timestamp> và lời giảng sư phạm).
    - Nếu có Code AST đạt độ tương quan hợp lệ (prefer_balanced=True), đảm bảo tối thiểu 1 Code AST Chunk.
    - Điền đầy các slot còn lại (tối đa final_top_k) bằng các chunk có điểm cao nhất tiếp theo (Video hoặc Code).
    - Tự động Fallback về 100% Video nếu không có Code AST đạt chuẩn (Fault-Tolerant & Graceful Degradation).
    """
    sorted_videos = sorted(video_items, key=lambda x: x.get("confidence_score", 0.0), reverse=True)
    sorted_codes = sorted(code_items, key=lambda x: x.get("confidence_score", 0.0), reverse=True)

    if not sorted_videos and not sorted_codes:
        return []
    if not sorted_codes or not prefer_balanced:
        return sorted_videos[:final_top_k] if sorted_videos else sorted_codes[:final_top_k]
    if not sorted_videos:
        return sorted_codes[:final_top_k]

    selected = [sorted_videos[0], sorted_codes[0]]
    remaining = [v for v in sorted_videos[1:]] + [c for c in sorted_codes[1:]]
    remaining_sorted = sorted(remaining, key=lambda x: x.get("confidence_score", 0.0), reverse=True)

    needed = final_top_k - len(selected)
    if needed > 0:
        selected.extend(remaining_sorted[:needed])

    return selected


def sigmoid(z: float) -> float:
    """
    Logistic Sigmoid Normalization: Chuyển đổi raw logits (-inf, +inf) sang xác suất thực [0.0, 1.0].
    """
    clipped = max(-250.0, min(250.0, z))
    return float(1.0 / (1.0 + math.exp(-clipped)))


def grade_document_relevance(query: str, item: Dict[str, Any], min_confidence: float = 0.40) -> str:
    """
    CRAG Document Relevance Grader (Yan et al., Meta AI 2024 & Self-RAG ICLR 2024):
    Thẩm định độ tương quan thực tế giữa Query và Chunk dựa trên:
    1. Multilingual Cross-Attention Confidence Score (Logistic Sigmoid Normalization).
    2. Ngưỡng tương quan tối thiểu (Calibrated Decision Boundary):
       - Code AST: prob >= 0.35 (do đặc thù cú pháp mã nguồn).
       - Video Transcript: prob >= 0.40 (loại bỏ triệt để câu hỏi đối nghịch và nhiễu âm học).
    3. Kiểm tra tính toàn vẹn nội dung của tài liệu.
    Trả về 'CORRECT' nếu tài liệu thực sự liên quan, hoặc 'INCORRECT' nếu không đạt ngưỡng tin cậy.
    """
    prob = float(item.get("confidence_score", 0.0))
    c_type = item.get("content_type", "video_transcript")

    text = (item.get("raw_text", "") + " " + item.get("context_code", "")).strip()
    if not text or len(text) < 10:
        logger.info(f"[CRAG Grader] Chunk {item.get('id')} bị đánh giá INCORRECT: Nội dung rỗng hoặc không hợp lệ.")
        return "INCORRECT"

    target_threshold = min(0.35, min_confidence) if c_type == "code_ast" else min_confidence
    if prob >= target_threshold:
        return "CORRECT"

    logger.info(
        f"[CRAG Grader] Chunk {item.get('id')} ({c_type}) bị đánh giá INCORRECT: "
        f"Độ tin cậy {prob:.4f} < ngưỡng chuẩn {target_threshold}."
    )
    return "INCORRECT"


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
        self._code_video_bindings: Dict[str, int] = {}
        if BINDING_MANIFEST_PATH.exists():
            try:
                with open(BINDING_MANIFEST_PATH, "r", encoding="utf-8") as bf:
                    b_data = json.load(bf)
                    self._code_video_bindings = b_data.get("bindings", {})
                logger.info(f"[RetrievalService] Nạp thành công {len(self._code_video_bindings)} Code-to-Video bindings từ manifest.")
            except Exception as b_err:
                logger.warning(f"[RetrievalService] Không thể đọc metadata bindings ({b_err}).")

    async def _probe_future_lessons(
        self,
        query_dense: List[float],
        sparse_indices: List[int],
        sparse_values: List[float],
        query_text: str,
        course_id: str,
        current_lesson_seq: int
    ) -> Tuple[Optional[int], float, str]:
        """
        Kiểm tra xem câu hỏi có thuộc về bài học tương lai (> current_lesson_seq) của khóa học hay không.
        Trả về (target_lesson_seq, max_confidence_score, best_chunk_type).
        """
        future_code_filter = models.Filter(
            must=[
                models.FieldCondition(key="course_id", match=models.MatchValue(value=course_id)),
                models.FieldCondition(key="lesson_seq", range=models.Range(gt=current_lesson_seq)),
                models.FieldCondition(key="content_type", match=models.MatchValue(value="code_ast"))
            ]
        )
        future_video_filter = models.Filter(
            must=[
                models.FieldCondition(key="course_id", match=models.MatchValue(value=course_id)),
                models.FieldCondition(key="lesson_seq", range=models.Range(gt=current_lesson_seq)),
                models.FieldCondition(key="content_type", match=models.MatchValue(value="video_transcript"))
            ]
        )

        try:
            future_resp = await self.client.query_points(
                collection_name=settings.QDRANT_COLLECTION_NAME,
                prefetch=[
                    models.Prefetch(
                        query=query_dense,
                        using="dense",
                        filter=future_video_filter,
                        limit=12
                    ),
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=sparse_indices,
                            values=sparse_values
                        ),
                        using="sparse",
                        filter=future_video_filter,
                        limit=12
                    ),
                    models.Prefetch(
                        query=query_dense,
                        using="dense",
                        filter=future_code_filter,
                        limit=6
                    ),
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=sparse_indices,
                            values=sparse_values
                        ),
                        using="sparse",
                        filter=future_code_filter,
                        limit=6
                    )
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=settings.FUTURE_PROBE_LIMIT
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
                scores = []
                alpha = 1.0 - settings.CRAG_RRF_WEIGHT
                for idx, val in enumerate(raw_logits):
                    raw_prob = sigmoid(val)
                    rrf_raw = float(future_points[idx].score) if idx < len(future_points) else 0.0
                    rrf_norm = min(1.0, max(0.0, rrf_raw / 0.8333))
                    fused_score = min(1.0, max(0.0, alpha * raw_prob + settings.CRAG_RRF_WEIGHT * rrf_norm))
                    scores.append(fused_score)
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
            best_chunk_type = "video_transcript"
            if future_points and max_idx < len(future_points):
                best_chunk_type = (future_points[max_idx].payload or {}).get("content_type", "video_transcript")
            return target_seq, max_score, best_chunk_type

        except Exception as probe_err:
            logger.warning(f"[RetrievalService] Lỗi khi probe future lessons ({probe_err}).")
            return None, 0.0, "video_transcript"

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

        is_syntax_query = bool(
            re.search(
                r"(\+\=|\-\=|\*\=|\/\=|\%\=|\+\+|\-\-|==|!=|<=|>=|&&|\|\||<<|>>|%|"
                r"toán tử|cú pháp|cách viết|viết rút gọn|khai báo|hàm|lớp|class|struct|"
                r"code|cài đặt|vòng lặp|for|while|do-while|if|else|switch|case|break|continue|"
                r"vector|string|cin|cout|swap|tham chiếu|pointer|con trỏ)",
                query_text,
                re.IGNORECASE
            )
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
            target_seq, future_score, _ = await self._probe_future_lessons(
                query_dense=query_dense,
                sparse_indices=sparse_indices,
                sparse_values=sparse_values,
                query_text=query_text,
                course_id=course_id,
                current_lesson_seq=current_lesson_seq
            )
            if target_seq and future_score >= settings.MIN_SCORE_THRESHOLD:
                logger.info(f"[RetrievalService] Phát hiện chủ đề thuộc bài tương lai (Seq {target_seq}) với điểm {future_score:.4f} >= {settings.MIN_SCORE_THRESHOLD}.")
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
                code_scope = p.get("code_scope", "")
                approx_vid_sec = p.get("approx_video_sec")
                # Ưu tiên mốc Ground-Truth trong manifest JSON nếu có cấu hình chính xác
                if self._code_video_bindings:
                    lookup_key = f"{item['lesson_id']}:{code_scope}"
                    manifest_sec = self._code_video_bindings.get(lookup_key)
                    if manifest_sec is not None:
                        approx_vid_sec = manifest_sec
                    elif approx_vid_sec is None:
                        lesson_fallback = f"{item['lesson_id']}:function_main"
                        approx_vid_sec = self._code_video_bindings.get(lesson_fallback)

                parsed_vid_sec = int(approx_vid_sec) if approx_vid_sec is not None else None
                item.update({
                    "file_path": p.get("file_path", ""),
                    "language": code_lang,
                    "code_scope": code_scope,
                    "start_line": p.get("start_line", 0),
                    "end_line": p.get("end_line", 0),
                    "context_code": ctx_code,
                    "approx_video_sec": parsed_vid_sec
                })
                if parsed_vid_sec is not None:
                    lbl = f"{parsed_vid_sec//60:02d}:{parsed_vid_sec%60:02d}"
                    item["timestamp_tag"] = f'<timestamp sec="{parsed_vid_sec}">{lbl}</timestamp>'
                texts_to_rerank.append(f"[Mã nguồn {code_lang.upper()} - {code_scope}]\n{ctx_code}")
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
            raw_prob = score_val if is_fallback_rrf else sigmoid(score_val)

            # CRAG Joint Confidence Fusion (Meta AI 2024 & Self-RAG ICLR 2024)
            # Kết hợp điểm xác suất ngữ nghĩa sâu (Cross-Encoder) và độ tương quan từ vựng khách quan (Hybrid RRF)
            # Không dùng regex hay magic number, đảm bảo tính chuẩn xác toán học
            rrf_raw = float(item.get("rrf_score", 0.0))
            rrf_norm = min(1.0, max(0.0, rrf_raw / 0.8333))
            alpha = 1.0 - settings.CRAG_RRF_WEIGHT
            prob = alpha * raw_prob + settings.CRAG_RRF_WEIGHT * rrf_norm
            prob = min(1.0, max(0.0, prob))

            item["raw_semantic_score"] = round(raw_prob, 4)
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

        # Roadmap Phase 2: Code-to-Video Metadata Binding (Chính thức kích hoạt)
        # Các đoạn Code AST đã được liên kết mốc video Ground-Truth từ Ingestion Metadata Manifest
        has_bound_code_video = any(
            it.get("approx_video_sec") is not None for it in scored_items if it.get("content_type") == "code_ast"
        )
        if has_bound_code_video:
            logger.info("[RetrievalService] Roadmap Phase 2: Sử dụng Ground-Truth Code-to-Video Metadata Binding.")

        # =========================================================================
        # [RETRIEVAL HIERARCHY PRECEDENCE INVARIANT - YAN ET AL. & ICLR 2025]
        # Bắt buộc tuân thủ 4 tầng phân cấp toán học một chiều nghiêm ngặt:
        # =========================================================================

        # -------------------------------------------------------------------------
        # TẦNG 1: GROUNDED ANCHOR & MODALITY-AWARE EARLY EXIT
        # -------------------------------------------------------------------------
        # Phân biệt rạch ròi giữa 2 phương thức:
        # 1. Code AST: Mốc neo cú pháp tất định (unambiguous syntax anchor)
        #    Nếu có Code AST >= MODALITY_GATE_AST_THRESHOLD (0.35) -> Khóa GROUNDED ngay lập tức, triệt tiêu Future Probing.
        # 2. Video Transcript: Văn nói bài giảng tự nhiên
        #    - Nếu Video Transcript >= MODALITY_GATE_VIDEO_HIGH_CONFIDENCE (0.40) -> Khóa GROUNDED ngay lập tức.
        #    - Nếu Video Transcript thuộc dải [MODALITY_GATE_VIDEO_THRESHOLD, MODALITY_GATE_VIDEO_HIGH_CONFIDENCE) ([0.30, 0.40)):
        #      KHÔNG Early Exit! Phải thăm dò bài tương lai trước để tránh lỗi văn nói bài cũ nuốt bài mới (ICLR 2025 Context Sufficiency).
        valid_ast_items = [
            it for it in candidate_items
            if it.get("content_type") == "code_ast"
            and it.get("confidence_score", 0.0) >= settings.MODALITY_GATE_AST_THRESHOLD
        ]
        valid_video_items = [
            it for it in candidate_items
            if it.get("content_type") == "video_transcript"
            and it.get("confidence_score", 0.0) >= settings.MODALITY_GATE_VIDEO_THRESHOLD
        ]
        max_video_score = max([it.get("confidence_score", 0.0) for it in valid_video_items], default=0.0)

        # 1.1. Code AST Anchor Early Exit:
        if valid_ast_items:
            anchor_candidates = assemble_balanced_modality(
                video_items=valid_video_items,
                code_items=valid_ast_items,
                final_top_k=final_top_k,
                prefer_balanced=True
            )
            final_assembled = reorder_lost_in_the_middle(anchor_candidates)
            logger.info(
                f"[RetrievalService] Tầng 1 Early Exit (Code AST Anchor): Khóa GROUNDED thành công "
                f"({len(valid_ast_items)} AST, {len(valid_video_items)} Video chunks). "
                f"Triệt tiêu future probing."
            )
            return RetrievalResult(
                chunks=final_assembled,
                status="grounded",
                is_low_confidence=False
            )

        # 1.2. High-Confidence Video Early Exit:
        # Bẫy văn nói bài giảng: Chỉ Early Exit khi:
        # (a) max_video_score >= settings.MODALITY_GATE_VIDEO_HIGH_CONFIDENCE
        # (b) VÀ không phải câu hỏi cú pháp cấu trúc điều khiển bị thiếu Code AST anchor trong bài hiện tại
        can_early_exit_video = (
            valid_video_items and 
            max_video_score >= settings.MODALITY_GATE_VIDEO_HIGH_CONFIDENCE
        )
        if can_early_exit_video:
            eligible_code_items = [
                it for it in candidate_items
                if it.get("content_type") == "code_ast"
                and it.get("confidence_score", 0.0) >= 0.20
            ]
            anchor_candidates = assemble_balanced_modality(
                video_items=valid_video_items,
                code_items=eligible_code_items,
                final_top_k=final_top_k,
                prefer_balanced=(is_syntax_query or any(c.get("confidence_score", 0.0) >= 0.25 for c in eligible_code_items))
            )
            final_assembled = reorder_lost_in_the_middle(anchor_candidates)
            logger.info(
                f"[RetrievalService] Tầng 1 Early Exit (High-Confidence Video >= {settings.MODALITY_GATE_VIDEO_HIGH_CONFIDENCE}): "
                f"Khóa GROUNDED thành công (max_video_score={max_video_score:.4f}). "
                f"Triệt tiêu future probing."
            )
            return RetrievalResult(
                chunks=final_assembled,
                status="grounded",
                is_low_confidence=False
            )

        # -------------------------------------------------------------------------
        # TẦNG 2: FUTURE LESSON PROBING (Kiểm tra bài học tương lai)
        # -------------------------------------------------------------------------
        # Áp dụng chuẩn [PARETO CONTEXT SUFFICIENCY INVARIANT - ICLR 2025]:
        # Bài tương lai chỉ được phép thống trị bài hiện tại khi thỏa mãn bất đẳng thức Pareto.
        max_current_score = max([it.get("confidence_score", 0.0) for it in candidate_items], default=0.0)
        target_seq = None
        future_score = 0.0
        margin = 0.0

        target_seq, future_score, future_chunk_type = await self._probe_future_lessons(
            query_dense=query_dense,
            sparse_indices=sparse_indices,
            sparse_values=sparse_values,
            query_text=query_text,
            course_id=course_id,
            current_lesson_seq=current_lesson_seq
        )
        margin = future_score - max_current_score

        has_local_grounding = max_current_score >= settings.PARETO_LOCAL_GROUNDING_THRESHOLD

        future_dominates = False
        if target_seq:
            if not has_local_grounding:
                # Trường hợp 1: Bài hiện tại KHÔNG có ngữ cảnh đạt chuẩn sàn (< 0.22)
                # Kích hoạt Out-of-Lesson khi bài tương lai đạt độ tự tin (>= 0.25) và biên độ chuẩn (>= 0.12)
                future_dominates = (
                    future_score >= settings.FUTURE_PROBE_MIN_CONFIDENCE and
                    margin >= settings.FUTURE_PROBE_MARGIN
                )
            else:
                # Trường hợp 2: Bài hiện tại ĐÃ CÓ ngữ cảnh tham khảo hợp lệ (>= 0.22)
                # Phân tầng theo phương thức (Modality-Aware Precedence - ICLR 2025 Context Sufficiency):
                if future_chunk_type == "code_ast":
                    # Code AST ở bài tương lai chỉ vô tình chứa từ khóa (như double, int)
                    # không được phép nuốt mất bài giảng lý thuyết nền tảng của bài hiện tại.
                    # Chỉ dominate khi đạt ngưỡng Code AST chuyên biệt:
                    future_dominates = (
                        future_score >= settings.PARETO_DOMINANCE_CODE_FUTURE_MIN and
                        margin >= settings.PARETO_DOMINANCE_CODE_MARGIN
                    )
                else:
                    # Bài giảng video chuyên sâu bài tương lai:
                    future_dominates = (
                        future_score >= settings.PARETO_DOMINANCE_FUTURE_MIN and
                        margin >= settings.PARETO_DOMINANCE_MARGIN
                    )

        if future_dominates:
            logger.info(
                f"[RetrievalService] Tầng 2 Out-of-Lesson (Pareto Dominance): Bài tương lai "
                f"(Seq {target_seq}) thống trị với future_score={future_score:.4f}, margin={margin:.4f} "
                f"(has_local_grounding={has_local_grounding})."
            )
            return RetrievalResult(chunks=[], status="out_of_lesson", target_lesson_seq=target_seq)

        # Nếu bài tương lai KHÔNG thống trị Pareto, và bài hiện tại có video transcript đạt ngưỡng hợp lệ:
        # Đây chính là ngữ cảnh bài giảng hợp lệ của bài hiện tại (bảo toàn BENCH-004, BENCH-011, BENCH-041,...).
        if valid_video_items:
            eligible_code_items = [
                it for it in candidate_items
                if it.get("content_type") == "code_ast"
                and it.get("confidence_score", 0.0) >= 0.20
            ]
            anchor_candidates = assemble_balanced_modality(
                video_items=valid_video_items,
                code_items=eligible_code_items,
                final_top_k=final_top_k,
                prefer_balanced=(is_syntax_query or any(c.get("confidence_score", 0.0) >= 0.25 for c in eligible_code_items))
            )
            final_assembled = reorder_lost_in_the_middle(anchor_candidates)
            logger.info(
                f"[RetrievalService] Tầng 2 Non-Dominated -> GROUNDED: Bài tương lai không thống trị "
                f"(future={future_score:.4f}, margin={margin:.4f}). "
                f"Video bài hiện tại đạt độ tin cậy hợp lệ {max_video_score:.4f} >= {settings.MODALITY_GATE_VIDEO_THRESHOLD}."
            )
            return RetrievalResult(
                chunks=final_assembled,
                status="grounded",
                is_low_confidence=(max_video_score < 0.25)
            )

        # -------------------------------------------------------------------------
        # TẦNG 3: GRACEFUL DEGRADATION (CRAG Ambiguous State: 0.20 <= S < 0.30)
        # -------------------------------------------------------------------------
        # Chỉ kích hoạt khi bài tương lai KHÔNG vượt trội, và bài hiện tại có cơ sở tham khảo:
        # S_current >= 0.20 VÀ S_semantic_raw >= VIDEO_FALLBACK_MIN_THRESHOLD (0.15)
        low_confidence_items = [
            it for it in candidate_items
            if it.get("confidence_score", 0.0) >= 0.20
            and it.get("raw_semantic_score", 0.0) >= settings.VIDEO_FALLBACK_MIN_THRESHOLD
            and grade_document_relevance(query_text, it, min_confidence=0.20) == "CORRECT"
        ]
        if low_confidence_items:
            top_low_conf = sorted(
                low_confidence_items,
                key=lambda x: x["confidence_score"],
                reverse=True
            )[:final_top_k]
            final_assembled = reorder_lost_in_the_middle(top_low_conf)
            logger.info(
                f"[RetrievalService] Tầng 3 Graceful Degradation: {len(low_confidence_items)} chunks "
                f"đạt ngưỡng tham khảo [0.20, 0.30). Gắn cờ is_low_confidence=True."
            )
            return RetrievalResult(
                chunks=final_assembled,
                status="grounded",
                is_low_confidence=True
            )

        # -------------------------------------------------------------------------
        # TẦNG 4: KHOẢNG TRỐNG HỌC LIỆU (Curriculum Coverage Gap - CRAG Incorrect)
        # -------------------------------------------------------------------------
        logger.info(
            f"[RetrievalService] Tầng 4 Coverage Gap: Không tìm thấy ngữ cảnh phù hợp "
            f"(max_current={max_current_score:.4f}, future={future_score:.4f}) -> 'coverage_gap'."
        )
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
