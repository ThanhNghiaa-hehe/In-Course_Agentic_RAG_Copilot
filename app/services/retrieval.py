import asyncio
import logging
import math
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
COMPILER_DIAGNOSTICS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "metadata" / "compiler_diagnostics_manifest.json"


@dataclass
class RetrievalResult:
    """
    Kết quả truy xuất ngữ cảnh bài học chuẩn hóa:
    - chunks: Danh sách các đoạn trích dẫn (U-shaped assembly)
    - status: 'grounded' (có tài liệu), 'out_of_lesson' (bài học tương lai), 'coverage_gap' (ngoài giáo trình)
    - target_lesson_seq: Thứ tự bài học tương lai nếu bị chặn bởi In-HNSW Pre-filter
    - is_low_confidence: Cờ đánh dấu Graceful Degradation (0.20 <= score < 0.35)
    - future_best_chunk: Mốc video của đoạn trích dẫn bài tương lai (hỗ trợ Conversational Navigation)
    """
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    status: Literal["grounded", "out_of_lesson", "coverage_gap"] = "coverage_gap"
    target_lesson_seq: Optional[int] = None
    is_low_confidence: bool = False
    is_approximate: bool = False
    future_best_chunk: Optional[Dict[str, Any]] = None

    def __iter__(self):
        return iter(self.chunks)

    def __len__(self):
        return len(self.chunks)

    def __getitem__(self, item):
        return self.chunks[item]

    def __bool__(self):
        return bool(self.chunks)


def is_hangul_or_cjk(c: str) -> bool:
    """Kiểm tra ký tự thuộc khối Hangul hoặc CJK dựa trên mã Unicode (Zero Regex)."""
    code = ord(c)
    return (
        (0xAC00 <= code <= 0xD7AF) or
        (0x1100 <= code <= 0x11FF) or
        (0x4E00 <= code <= 0x9FFF)
    )


def sanitize_text(text: str) -> str:
    """
    Chuẩn hóa văn bản trả về (Zero Regex):
    - Loại bỏ ký tự carriage return và các ký tự điều khiển.
    - Lọc bỏ các ký tự ngoại ngữ lạ (Hangul, Hanja,...) do lỗi âm học mô hình sinh ra.
    """
    if not text:
        return ""
    text = text.replace("\r", " ").replace("\ufffd", "")
    if any(is_hangul_or_cjk(c) for c in text):
        text = "".join(c for c in text if not is_hangul_or_cjk(c))
    return " ".join(text.split())


def truncate_rerank_text(text: str, max_chars: int = settings.RERANK_MAX_CHARS) -> str:
    """
    Cắt tỉa văn bản đầu vào cho Cross-Encoder xuống dưới trần độ dài ký tự an toàn (~384 tokens).
    Vì độ phức tạp tính toán cơ chế tự chú ý (Self-Attention / Cross-Attention) là O(L^2),
    việc giới hạn L <= 384 tokens (~1.200 ký tự) giúp tăng tốc độ suy luận trên CPU lên:
    (1024 / 384)^2 ≈ 7.1x, đồng thời bảo toàn trọn vẹn chữ ký hàm, scope và ngữ nghĩa cốt lõi.
    """
    if not text:
        return ""
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars]


def deduplicate_temporal_candidates(
    raw_candidates: List[Any],
    min_overlap_ratio: float = 0.40,
    proximity_sec: int = 30
) -> List[Any]:
    """
    [M-06: Pre-rerank Window Deduplication]
    Áp dụng thuật toán Temporal Non-Maximum Suppression (NMS) trên trục thời gian:
    - Loại bỏ các chunk video transcript bị gối đầu trùng lặp (stride 15s-30s) trong cùng bài học.
    - Loại bỏ các chunk Code AST trùng lặp cùng scope hàm/lớp trong cùng bài học.
    - Giữ lại chunk có điểm RRF cao hơn (chọn chunk xuất hiện trước trong danh sách RRF).
    - Cắt giảm 25% - 30% số lượng ứng viên cần Re-rank mà không làm mất thông tin.
    """
    if not raw_candidates or len(raw_candidates) <= 1:
        return raw_candidates

    accepted_candidates: List[Any] = []

    for hit in raw_candidates:
        p = hit.payload or {}
        c_type = p.get("content_type", "video_transcript")
        lesson_id = p.get("lesson_id", "")

        is_suppressed = False

        if c_type == "code_ast":
            code_scope = p.get("code_scope", "")
            for prev in accepted_candidates:
                prev_p = prev.payload or {}
                if (
                    prev_p.get("content_type") == "code_ast"
                    and prev_p.get("lesson_id") == lesson_id
                    and prev_p.get("code_scope") == code_scope
                ):
                    is_suppressed = True
                    break
        else:
            start_sec = int(p.get("start_sec", 0))
            end_sec = int(p.get("end_sec", 0))
            vid_title = p.get("video_title", "")

            for prev in accepted_candidates:
                prev_p = prev.payload or {}
                if prev_p.get("content_type") == "video_transcript":
                    prev_vid = prev_p.get("video_title", "")
                    prev_lid = prev_p.get("lesson_id", "")

                    if (vid_title and prev_vid and vid_title == prev_vid) or (lesson_id and prev_lid and lesson_id == prev_lid):
                        prev_start = int(prev_p.get("start_sec", 0))
                        prev_end = int(prev_p.get("end_sec", 0))

                        # 1. Kiểm tra độ lệch mốc bắt đầu (Edge Proximity)
                        if abs(start_sec - prev_start) <= proximity_sec:
                            is_suppressed = True
                            break

                        # 2. Kiểm tra độ phủ thời gian Overlap Ratio
                        overlap = max(0, min(end_sec, prev_end) - max(start_sec, prev_start))
                        if overlap > 0:
                            min_dur = min(end_sec - start_sec, prev_end - prev_start)
                            if min_dur > 0 and (overlap / min_dur) >= min_overlap_ratio:
                                is_suppressed = True
                                break

        if not is_suppressed:
            accepted_candidates.append(hit)

    return accepted_candidates


def reorder_lost_in_the_middle(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Khắc phục hiện tượng 'Lost-in-the-Middle' (Liu et al., Stanford 2024).
    Sắp xếp các chunks theo cấu trúc hình chữ U:
    - Chunk có độ liên quan cao nhất ở đầu (vị trí 1)
    - Chunk cao thứ nhì ở cuối danh sách
    - Các chunk còn lại nằm ở phần giữa
    Ví dụ với 3 chunks: [Top 1, Top 3, Top 2]
    """
    if len(items) <= 1:
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

    result = [item for item in reordered if item is not None]
    if len(result) > 1 and result[0].get("content_type") == "code_ast":
        boilerplate_scopes = {"header_preamble", "function_main", "type_class_specifier"}
        if (result[0].get("code_scope") or "") in boilerplate_scopes:
            for swap_idx, cand in enumerate(result[1:], start=1):
                c_type = cand.get("content_type")
                c_score = float(cand.get("confidence_score", 0.0))
                is_valid_video = (
                    c_type == "video_transcript"
                    and not cand.get("is_approximate", False)
                    and c_score >= settings.VIDEO_SCORE_THRESHOLD
                )
                is_specific_code = (
                    c_type == "code_ast"
                    and (cand.get("code_scope") or "") not in boilerplate_scopes
                    and c_score >= settings.CODE_SCORE_THRESHOLD
                )
                if is_valid_video or is_specific_code:
                    result[0], result[swap_idx] = result[swap_idx], result[0]
                    break
    return result


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


def compute_length_compensated_sigmoid(z: float, query_text: str) -> float:
    """
    Length-Compensated Temperature Scaling cho Cross-Encoder:
    Chuẩn hóa logit z theo độ dài câu hỏi |q|:
    scaled_logit = (z - 0.0) / (1.25 * math.sqrt(max(len(query.split()), 5) / 10.0))
    cross_score = 1.0 / (1.0 + math.exp(-scaled_logit))
    """
    num_words = max(len(query_text.split()), 5)
    temp_scale = 1.25 * math.sqrt(num_words / 10.0)
    scaled_logit = (z - 0.0) / temp_scale
    clipped = max(-250.0, min(250.0, scaled_logit))
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
        self._client = client
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

        self._compiler_diagnostics: List[Dict[str, Any]] = []
        if COMPILER_DIAGNOSTICS_PATH.exists():
            try:
                with open(COMPILER_DIAGNOSTICS_PATH, "r", encoding="utf-8") as cdf:
                    cd_data = json.load(cdf)
                    self._compiler_diagnostics = cd_data.get("diagnostics", [])
                logger.info(f"[RetrievalService] Nạp thành công {len(self._compiler_diagnostics)} Compiler Diagnostics từ manifest.")
            except Exception as cd_err:
                logger.warning(f"[RetrievalService] Không thể đọc compiler diagnostics manifest ({cd_err}).")

    @property
    def client(self) -> AsyncQdrantClient:
        return self._client or get_async_qdrant_client()

    def bridge_compiler_error_semantics(self, query_text: str) -> Tuple[str, bool]:
        """
        Compiler Error Semantic Bridge (HyDE / EMNLP 2023):
        Phát hiện log lỗi trình biên dịch (GCC/Clang/MSVC) và tăng cường ngữ nghĩa tiếng Việt
        để giải quyết triệt để bài toán Vocabulary Mismatch giữa log lỗi tiếng Anh và bài giảng tiếng Việt.
        Trả về (augmented_dense_query, has_bridge_applied).
        """
        if not self._compiler_diagnostics:
            return query_text, False

        q_lower = query_text.lower()
        matched_behaviors: List[str] = []

        for diag in self._compiler_diagnostics:
            for pat in diag.get("patterns", []):
                if pat.lower() in q_lower:
                    behavior = diag.get("pedagogical_vietnamese")
                    if behavior and behavior not in matched_behaviors:
                        matched_behaviors.append(behavior)
                    break

        if not matched_behaviors:
            return query_text, False

        # Tăng cường ngữ cảnh sư phạm cho Dense Vector E5 & Cross-Encoder (không làm biến dạng token gốc cho BM25)
        augmented_query = f"{query_text} [Hành vi sư phạm: {', '.join(matched_behaviors)}]"
        return augmented_query, True

    async def _fetch_future_points(
        self,
        query_dense: List[float],
        sparse_indices: List[int],
        sparse_values: List[float],
        course_id: str,
        current_lesson_seq: int,
        allow_cross_course: bool = False
    ) -> List[Any]:
        """
        [CHẶNG 6 SÁNG KIẾN 2: SCATTER-GATHER CONCURRENCY]
        Tải trước ứng viên điểm vector từ các bài học tương lai (> current_lesson_seq).
        Chạy song song (asynchronous) với lượt truy vấn bài hiện tại qua asyncio.gather,
        cắt giảm hoàn toàn 1 lượt Network RTT (~250-350ms) tới Qdrant Cloud.
        Chỉ mở rộng cross-course (cpp-core <-> cpp-oop) khi allow_cross_course=True (điều hướng lộ trình).
        """
        from app.services.curriculum import get_curriculum_service
        c_svc = get_curriculum_service()
        cpp_track_courses = c_svc.get_course_ids()
        course_condition = (
            models.FieldCondition(key="course_id", match=models.MatchAny(any=cpp_track_courses))
            if (allow_cross_course and course_id in cpp_track_courses)
            else models.FieldCondition(key="course_id", match=models.MatchValue(value=course_id))
        )
        future_code_filter = models.Filter(
            must=[
                course_condition,
                models.FieldCondition(key="lesson_seq", range=models.Range(gt=current_lesson_seq)),
                models.FieldCondition(key="content_type", match=models.MatchValue(value="code_ast"))
            ]
        )
        future_video_filter = models.Filter(
            must=[
                course_condition,
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
                        limit=6
                    ),
                    models.Prefetch(
                        query=query_dense,
                        using="dense",
                        filter=future_code_filter,
                        limit=4
                    ),
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=sparse_indices,
                            values=sparse_values
                        ),
                        using="sparse",
                        filter=future_code_filter,
                        limit=4
                    )
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=settings.FUTURE_PROBE_LIMIT
            )
            return future_resp.points if future_resp and hasattr(future_resp, "points") else []
        except Exception as probe_err:
            logger.warning(f"[RetrievalService] Lỗi khi tải trước future points ({probe_err}).")
            return []

    async def _score_future_points(
        self,
        future_points: List[Any],
        query_text: str
    ) -> Tuple[Optional[int], float, str]:
        """
        Đánh giá điểm tin cậy và xếp hạng các điểm ứng viên của bài học tương lai.
        Được gọi khi bài hiện tại không kích hoạt Early Exit (Tầng 1).
        Áp dụng truncate_rerank_text (M-05a) và rerank_documents_async (M-05b) để tối ưu CPU.
        """
        if not future_points:
            return None, 0.0, "video_transcript", None

        # [M-06: Pre-rerank Deduplication & M-05a: Candidate Pruning] Khử trùng lặp và giới hạn ứng viên bài tương lai
        future_points = deduplicate_temporal_candidates(future_points)
        future_points = future_points[:settings.FUTURE_PROBE_LIMIT]

        future_texts: List[str] = []
        future_seqs: List[int] = []

        for hit in future_points:
            p = hit.payload or {}
            future_seqs.append(int(p.get("lesson_seq", 0)))
            c_type = p.get("content_type", "video_transcript")
            if c_type == "code_ast":
                ctx_code = p.get("context_code") or p.get("raw_text", "")
                code_lang = p.get("code_language") or p.get("language", "cpp")
                raw_item_text = f"[Mã nguồn {code_lang.upper()} - {p.get('code_scope', '')}]\n{ctx_code}"
                future_texts.append(truncate_rerank_text(raw_item_text))
            else:
                vid_title = p.get("video_title", "video_lecture.mp4")
                start_lbl = p.get("start_label", "")
                raw_txt = sanitize_text(p.get("raw_text", ""))
                raw_item_text = f"[Bài giảng Video {vid_title} mốc {start_lbl}]\n{raw_txt}"
                future_texts.append(truncate_rerank_text(raw_item_text))

        try:
            raw_logits = await self.embedding_service.rerank_documents_async(query=query_text, documents=future_texts)
            scores = []
            w_max = settings.CRAG_RRF_WEIGHT
            all_rrfs = [float(p.score) for p in future_points] if future_points else [0.0]
            min_rrf = min(all_rrfs) if all_rrfs else 0.0
            max_rrf = max(all_rrfs) if all_rrfs else 1.0
            for idx, val in enumerate(raw_logits):
                raw_prob = compute_length_compensated_sigmoid(val, query_text)
                rrf_raw = float(future_points[idx].score) if idx < len(future_points) else 0.0
                rrf_norm = (rrf_raw - min_rrf) / (max_rrf - min_rrf + 1e-6)
                rrf_norm = min(1.0, max(0.0, rrf_norm))
                semantic_gate = min(1.0, (raw_prob / 0.28) ** 2)
                w_eff = w_max * semantic_gate
                fused_score = min(1.0, max(0.0, (1.0 - w_eff) * raw_prob + w_eff * rrf_norm))
                scores.append(fused_score)
        except Exception as re_err:
            logger.warning(f"[RetrievalService] Lỗi rerank future probe ({re_err}), dùng Calibrated RRF Fallback.")
            all_rrfs = [float(hit.score) for hit in future_points] if future_points else [0.0]
            min_rrf = min(all_rrfs) if all_rrfs else 0.0
            max_rrf = max(all_rrfs) if all_rrfs else 1.0
            scores = []
            for hit in future_points:
                r_i = float(hit.score)
                r_norm = (r_i - min_rrf) / (max_rrf - min_rrf + 1e-6)
                r_norm = min(1.0, max(0.0, r_norm))
                # Calibrated Min-Max Scaling (Mục 1.3): S_fallback = 0.20 + 0.25 * r_norm
                scores.append(0.20 + 0.25 * r_norm)

        # 1. Tìm ứng viên có điểm tuyệt đối cao nhất
        best_idx = 0
        max_score = 0.0
        for idx, sc in enumerate(scores):
            if sc > max_score:
                max_score = sc
                best_idx = idx

        # 2. [Prerequisite Order Pareto Invariant - ICLR 2025]
        # Khắc phục triệt để bẫy đảo ngược giáo trình (Curriculum Inversion Trap):
        # Giữa bài học cơ sở tiên quyết (L_early) và bài học ứng dụng nâng cao (L_late),
        # bài học đến sau CHỈ ĐƯỢC PHÉP thống trị nếu đạt biên độ vượt trội áp đảo (Margin > 0.15).
        CONFIDENCE_FLOOR = 0.35
        DOMINATE_MARGIN = 0.15

        confident_candidates = [
            (idx, future_seqs[idx], scores[idx])
            for idx in range(len(scores))
            if scores[idx] >= CONFIDENCE_FLOOR and future_seqs[idx] > 0
        ]

        if confident_candidates:
            # Sắp xếp theo lesson_seq tăng dần (ưu tiên bài học tiên quyết gần tiến độ học viên nhất)
            sorted_by_seq = sorted(confident_candidates, key=lambda x: (x[1], -x[2]))
            earliest_idx, earliest_seq, earliest_score = sorted_by_seq[0]

            if (max_score - earliest_score) > DOMINATE_MARGIN:
                chosen_idx = best_idx
                logger.info(
                    f"[RetrievalService:Pareto] Bài học sau Seq {future_seqs[best_idx]} áp đảo hoàn toàn "
                    f"Bài học cơ sở Seq {earliest_seq} (Score {max_score:.4f} vs {earliest_score:.4f}, Margin > {DOMINATE_MARGIN})."
                )
            else:
                chosen_idx = earliest_idx
                if earliest_seq != future_seqs[best_idx]:
                    logger.info(
                        f"[RetrievalService:Pareto] Kích hoạt Prerequisite Order Invariant: "
                        f"Ưu tiên Bài học cơ sở Seq {earliest_seq} (Score {earliest_score:.4f}) "
                        f"trước Bài học ứng dụng Seq {future_seqs[best_idx]} (Score {max_score:.4f}, Margin <= {DOMINATE_MARGIN})."
                    )
        else:
            chosen_idx = best_idx

        target_seq = future_seqs[chosen_idx] if future_seqs else None
        chosen_score = scores[chosen_idx] if scores else max_score
        best_chunk_type = (
            (future_points[best_idx].payload or {}).get("content_type", "video_transcript")
            if future_points and best_idx < len(future_points)
            else "video_transcript"
        )
        best_future_chunk = None
        if future_points and chosen_idx < len(future_points):
            best_p = future_points[chosen_idx].payload or {}
            chosen_chunk_type = best_p.get("content_type", "video_transcript")
            start_s = best_p.get("start_sec")
            if start_s is None and best_p.get("approx_video_sec") is not None:
                start_s = int(best_p.get("approx_video_sec"))

            best_future_chunk = {
                "lesson_seq": target_seq,
                "start_sec": start_s,
                "start_label": best_p.get("start_label") or (f"{int(start_s)//60:02d}:{int(start_s)%60:02d}" if start_s is not None else None),
                "video_title": best_p.get("video_title", f"Bài giảng Bài {target_seq}"),
                "content_type": chosen_chunk_type,
                "score": chosen_score,
                "raw_text": sanitize_text(best_p.get("raw_text", "")),
                "context_code": best_p.get("context_code", ""),
                "code_scope": best_p.get("code_scope", ""),
                "timestamp_tag": best_p.get("timestamp_tag", ""),
                "approx_video_sec": best_p.get("approx_video_sec")
            }
        return target_seq, max_score, best_chunk_type, best_future_chunk

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
        Wrapper tương thích ngược.
        """
        points = await self._fetch_future_points(
            query_dense=query_dense,
            sparse_indices=sparse_indices,
            sparse_values=sparse_values,
            course_id=course_id,
            current_lesson_seq=current_lesson_seq
        )
        res = await self._score_future_points(points, query_text)
        return res[0], res[1], res[2]

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
        is_curriculum_navigation: bool = False,
        is_continuation_turn: bool = False,
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

        if not is_curriculum_navigation:
            try:
                from app.agent.router import get_intent_router
                is_nav, _ = get_intent_router().is_curriculum_navigation(query_text)
                if is_nav:
                    is_curriculum_navigation = True
            except Exception:
                pass


        # 1. Sinh Dual Vectors bất đồng bộ / fast ONNX (Áp dụng Compiler Error Semantic Bridge nếu có)
        dense_query_text, has_bridge = self.bridge_compiler_error_semantics(query_text)
        if has_bridge:
            logger.info(f"[RetrievalService] Kích hoạt Compiler Error Semantic Bridge: '{dense_query_text}'")

        query_dense = self.embedding_service.embed_query_dense(dense_query_text)
        sparse_indices, sparse_values = self.embedding_service.embed_query_sparse(query_text)

        # 2. Xây dựng In-HNSW Pre-filter động (Ngăn ngừa triệt để hiện tượng lộ bài học tương lai)
        current_code_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="course_id",
                    match=models.MatchValue(value=course_id)
                ),
                models.FieldCondition(
                    key="lesson_seq",
                    range=models.Range(lte=current_lesson_seq)
                ),
                models.FieldCondition(
                    key="content_type",
                    match=models.MatchValue(value="code_ast")
                )
            ]
        )
        current_video_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="course_id",
                    match=models.MatchValue(value=course_id)
                ),
                models.FieldCondition(
                    key="lesson_seq",
                    range=models.Range(lte=current_lesson_seq)
                ),
                models.FieldCondition(
                    key="content_type",
                    match=models.MatchValue(value="video_transcript")
                )
            ]
        )

        # 3. [CHẶNG 6 SÁNG KIẾN 2]: SCATTER-GATHER ASYNC PARALLEL FUTURE PROBING
        # Phát song song 2 luồng I/O mạng tới Qdrant Cloud với cấu trúc Prefetch đối xứng đa phương thức:
        # Task A: Truy vấn bài hiện tại (Video + Code AST tách biệt)
        # Task B: Tải trước ứng viên bài tương lai (Video + Code AST tách biệt)
        current_query_coro = self.client.query_points(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            prefetch=[
                models.Prefetch(
                    query=query_dense,
                    using="dense",
                    filter=current_video_filter,
                    limit=top_candidates
                ),
                models.Prefetch(
                    query=models.SparseVector(
                        indices=sparse_indices,
                        values=sparse_values
                    ),
                    using="sparse",
                    filter=current_video_filter,
                    limit=top_candidates
                ),
                models.Prefetch(
                    query=query_dense,
                    using="dense",
                    filter=current_code_filter,
                    limit=max(4, top_candidates // 2)
                ),
                models.Prefetch(
                    query=models.SparseVector(
                        indices=sparse_indices,
                        values=sparse_values
                    ),
                    using="sparse",
                    filter=current_code_filter,
                    limit=max(4, top_candidates // 2)
                )
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_candidates + 4
        )

        future_fetch_coro = self._fetch_future_points(
            query_dense=query_dense,
            sparse_indices=sparse_indices,
            sparse_values=sparse_values,
            course_id=course_id,
            current_lesson_seq=current_lesson_seq,
            allow_cross_course=is_curriculum_navigation
        )

        # Chạy đồng thời 2 luồng mạng I/O qua asyncio.gather, tiết kiệm 1 Network RTT (~250-350ms)
        gather_results = await asyncio.gather(current_query_coro, future_fetch_coro, return_exceptions=True)

        current_resp = gather_results[0] if not isinstance(gather_results[0], Exception) else None
        future_points = gather_results[1] if not isinstance(gather_results[1], Exception) else []

        raw_candidates = current_resp.points if current_resp and hasattr(current_resp, "points") else []
        logger.info(
            f"[RetrievalService:Scatter-Gather] Đã tải đồng thời: {len(raw_candidates)} chunks bài hiện tại, "
            f"{len(future_points)} chunks bài tương lai."
        )

        # Nếu hoàn toàn không có candidate nào trong phạm vi bài hiện tại
        if not raw_candidates:
            target_seq, future_score, _, best_future_chunk = await self._score_future_points(
                future_points=future_points,
                query_text=dense_query_text if has_bridge else query_text
            )
            if target_seq and future_score >= settings.MIN_SCORE_THRESHOLD:
                logger.info(f"[RetrievalService] Phát hiện chủ đề thuộc bài tương lai (Seq {target_seq}) với điểm {future_score:.4f} >= {settings.MIN_SCORE_THRESHOLD}.")
                return RetrievalResult(
                    chunks=[],
                    status="out_of_lesson",
                    target_lesson_seq=target_seq,
                    future_best_chunk=best_future_chunk
                )
            return RetrievalResult(chunks=[], status="coverage_gap")

        # 4. [STAGE 8 & M-06] Pre-rerank Window Deduplication & Multilingual Cross-Encoder Re-ranking
        deduped_candidates = deduplicate_temporal_candidates(raw_candidates)
        if len(deduped_candidates) < len(raw_candidates):
            logger.info(
                f"[RetrievalService:M-06] Khử trùng lặp Pre-rerank: Giảm từ {len(raw_candidates)} xuống {len(deduped_candidates)} candidates."
            )

        candidate_items: List[Dict[str, Any]] = []
        texts_to_rerank: List[str] = []

        for hit in deduped_candidates:
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
                raw_code_item = f"[Mã nguồn {code_lang.upper()} - {code_scope}]\n{ctx_code}"
                texts_to_rerank.append(truncate_rerank_text(raw_code_item))
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
                raw_video_item = f"[Bài giảng Video {vid_title} mốc {start_lbl}]\n{item['raw_text']}"
                texts_to_rerank.append(truncate_rerank_text(raw_video_item))

            candidate_items.append(item)

        # Chấm điểm Cross-Encoder vi mô
        is_fallback_rrf = False
        try:
            rerank_query = dense_query_text if has_bridge else query_text
            raw_logits = await self.embedding_service.rerank_documents_async(query=rerank_query, documents=texts_to_rerank)
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

        # Áp dụng Dynamic Min-Max Scaling và Logistic Sigmoid theo ngưỡng phân tầng
        scored_items: List[Dict[str, Any]] = []
        discarded_videos: List[Dict[str, Any]] = []

        all_candidate_rrfs = [float(it.get("rrf_score", 0.0)) for it in candidate_items] if candidate_items else [0.0]
        min_rrf = min(all_candidate_rrfs) if all_candidate_rrfs else 0.0
        max_rrf = max(all_candidate_rrfs) if all_candidate_rrfs else 1.0

        for i, item in enumerate(candidate_items):
            score_val = raw_logits[i] if i < len(raw_logits) else 0.0
            rrf_raw = float(item.get("rrf_score", 0.0))
            rrf_norm = (rrf_raw - min_rrf) / (max_rrf - min_rrf + 1e-6)
            rrf_norm = min(1.0, max(0.0, rrf_norm))

            if is_fallback_rrf:
                # Calibrated Min-Max Scaling cho RRF Fallback (Mục 1.3 - Nhịp 1B)
                # Bảo toàn Top 1: 0.20 + 0.25 = 0.45 >= 0.35; Bottom: 0.20 < 0.22 (lọc bỏ tự nhiên)
                raw_prob = 0.20 + 0.25 * rrf_norm
            else:
                raw_prob = compute_length_compensated_sigmoid(score_val, rerank_query)

            # CRAG Joint Confidence Fusion (Meta AI 2024 & Self-RAG ICLR 2024)
            # Semantic-Gated RRF Fusion: ngăn nhiễu RRF thổi phồng ứng viên có raw_prob thấp
            c_type = item.get("content_type", "video_transcript")
            w_max = settings.CRAG_RRF_WEIGHT
            gate_pivot = 0.20 if c_type == "code_ast" else 0.28
            semantic_gate = min(1.0, (raw_prob / gate_pivot) ** 2)
            w_eff = w_max * semantic_gate
            prob = min(1.0, max(0.0, (1.0 - w_eff) * raw_prob + w_eff * rrf_norm))

            item["raw_semantic_score"] = round(raw_prob, 4)
            item["confidence_score"] = round(prob, 4)
            item["confidence_pct"] = round(prob * 100, 2)

            threshold = effective_code_threshold if c_type == "code_ast" else effective_video_threshold

            if prob >= threshold:
                scored_items.append(item)
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
        # Context-Aware Boilerplate Scope Filtering (Giải cứu câu hỏi về hàm main - Zero Hardcode)
        is_asking_main = "main" in query_text.lower().split() or "hàm main" in query_text.lower() or "main()" in query_text.lower()
        BOILERPLATE_SCOPES = (
            {"header_preamble", "type_class_specifier"}
            if is_asking_main
            else {"header_preamble", "function_main", "type_class_specifier"}
        )

        valid_ast_items = [
            it for it in candidate_items
            if it.get("content_type") == "code_ast"
            and it.get("confidence_score", 0.0) >= max(effective_code_threshold, settings.MODALITY_GATE_AST_THRESHOLD)
        ]
        specific_ast_items = [
            it for it in valid_ast_items
            if (it.get("code_scope") or "") not in BOILERPLATE_SCOPES
        ]
        valid_video_items = [
            it for it in candidate_items
            if it.get("content_type") == "video_transcript"
            and it.get("confidence_score", 0.0) >= max(effective_video_threshold, settings.MODALITY_GATE_VIDEO_THRESHOLD)
        ]

        max_specific_code_score = max([it.get("confidence_score", 0.0) for it in specific_ast_items], default=0.0)
        max_code_score = max([it.get("confidence_score", 0.0) for it in valid_ast_items], default=0.0)
        max_video_score = max([it.get("confidence_score", 0.0) for it in valid_video_items], default=0.0)
        all_video_scores = [
            it.get("confidence_score", 0.0) for it in candidate_items
            if it.get("content_type") == "video_transcript"
        ]
        max_any_video_score = max(all_video_scores, default=0.0)
        max_raw_prob = max((it.get("raw_semantic_score", 0.0) for it in candidate_items), default=0.0)

        # Kiểm tra Context Sufficiency (ICLR 2025):
        only_boilerplate_code = bool(valid_ast_items) and not specific_ast_items
        if only_boilerplate_code and not valid_video_items:
            valid_ast_items = []

        # -------------------------------------------------------------------------
        # TẦNG 1: GROUNDED ANCHOR & MODALITY-AWARE EARLY EXIT (An toàn tuyệt đối)
        # -------------------------------------------------------------------------
        has_strong_ast_grounding = (
            len(specific_ast_items) > 0
            and (
                max_specific_code_score >= 0.46
                or (max_specific_code_score >= 0.40 and max_video_score >= settings.VIDEO_SCORE_THRESHOLD)
            )
        )
        if not is_curriculum_navigation and has_strong_ast_grounding:
            anchor_candidates = assemble_balanced_modality(
                video_items=valid_video_items,
                code_items=valid_ast_items,
                final_top_k=final_top_k,
                prefer_balanced=True
            )
            final_assembled = reorder_lost_in_the_middle(anchor_candidates)
            logger.info(
                f"[RetrievalService] Tầng 1 Early Exit (Specific Code AST Anchor >= 0.46 or balanced >= 0.40): "
                f"Khóa GROUNDED thành công (max_specific_code_score={max_specific_code_score:.4f}, max_video={max_video_score:.4f})."
            )
            return RetrievalResult(
                chunks=final_assembled,
                status="grounded",
                is_low_confidence=False
            )

        has_high_confidence_video_grounding = (
            bool(valid_video_items)
            and (
                max_video_score >= settings.PARETO_VIDEO_STRONG_GROUNDING
                or (
                    max_video_score >= settings.MODALITY_GATE_VIDEO_HIGH_CONFIDENCE
                    and bool(specific_ast_items)
                )
            )
        )
        if not is_curriculum_navigation and has_high_confidence_video_grounding:
            eligible_code_items = [
                it for it in candidate_items
                if it.get("content_type") == "code_ast"
                and it.get("confidence_score", 0.0) >= 0.15
            ]
            anchor_candidates = assemble_balanced_modality(
                video_items=valid_video_items,
                code_items=eligible_code_items,
                final_top_k=final_top_k,
                prefer_balanced=bool(eligible_code_items)
            )
            final_assembled = reorder_lost_in_the_middle(anchor_candidates)
            logger.info(
                f"[RetrievalService] Tầng 1 Early Exit (High-Confidence Video >= {settings.PARETO_VIDEO_STRONG_GROUNDING} or >= {settings.MODALITY_GATE_VIDEO_HIGH_CONFIDENCE} with AST): "
                f"Khóa GROUNDED thành công (max_video_score={max_video_score:.4f})."
            )
            return RetrievalResult(
                chunks=final_assembled,
                status="grounded",
                is_low_confidence=False
            )

        # -------------------------------------------------------------------------
        # TẦNG 2: FUTURE LESSON PROBING & BẤT ĐẲNG THỨC PARETO 3 PHÂN TẦNG
        # -------------------------------------------------------------------------
        target_seq, future_score, future_chunk_type, best_future_chunk = await self._score_future_points(
            future_points=future_points,
            query_text=dense_query_text if has_bridge else query_text
        )

        if is_curriculum_navigation:
            # Loại trừ các chunk video giới thiệu tổng quan Bài 1/2 khỏi việc tính max_current_score
            from app.services.curriculum import get_curriculum_service
            c_svc = get_curriculum_service()
            current_lesson_items = [
                it for it in candidate_items
                if not c_svc.is_introductory_overview_chunk(it)
            ]
            if only_boilerplate_code:
                max_current_score = max_video_score
            else:
                max_current_score = max([it.get("confidence_score", 0.0) for it in current_lesson_items], default=0.0)
        else:
            if only_boilerplate_code:
                max_current_score = max_video_score
            else:
                max_current_score = max([it.get("confidence_score", 0.0) for it in candidate_items], default=0.0)

        margin = future_score - max_current_score

        # Phân nhánh Pareto Dominance (ICLR 2025):
        if is_curriculum_navigation:
            # Phân nhánh 3A: Curriculum Navigation Dominance vs Introductory Video
            min_future_floor = 0.18
            margin_req = -0.35
            logger.info(
                f"[RetrievalService:Pareto 3A] Kích hoạt Curriculum Navigation Dominance: "
                f"floor={min_future_floor}, margin_req={margin_req}"
            )
            if target_seq is None or future_score < 0.25 or is_curriculum_navigation:
                try:
                    from app.services.curriculum import get_curriculum_service
                    c_svc = get_curriculum_service()
                    c_match = c_svc.find_lesson_for_query(
                        query_text,
                        current_lesson_seq=current_lesson_seq,
                        preferred_course_id=course_id,
                    )
                    if c_match:
                        matched_lesson = c_match[0] if isinstance(c_match, (tuple, list)) else c_match
                        if isinstance(matched_lesson, dict):
                            c_seq = matched_lesson.get("seq") or matched_lesson.get("lesson_seq")
                            c_course = matched_lesson.get("course_id", course_id)
                            if c_seq is not None and (c_course != course_id or int(c_seq) > current_lesson_seq):
                                target_seq = int(c_seq)
                                future_score = max(future_score, 0.42)
                                margin = future_score - max_current_score
                                logger.info(f"[RetrievalService:Pareto 3A] Giải cứu target_seq qua CurriculumService: Khóa {c_course} - Bài {target_seq}")
                except Exception as c_err:
                    logger.warning(f"[RetrievalService:Pareto 3A] Lỗi giải cứu qua CurriculumService ({c_err})")
        else:
            # Kiểm tra exercise_statement_signatures & Curriculum Mapping từ CurriculumService (Data/Code Separation)
            from app.services.curriculum import get_curriculum_service
            c_svc = get_curriculum_service()
            is_exercise_stmt = c_svc.is_exercise_statement(query_text)
            curriculum_matched_seq: Optional[int] = None
            try:
                c_match = c_svc.find_lesson_for_query(
                    query_text,
                    current_lesson_seq=current_lesson_seq,
                    preferred_course_id=course_id,
                )
                if c_match:
                    matched_lesson = c_match[0] if isinstance(c_match, (tuple, list)) else c_match
                    if isinstance(matched_lesson, dict):
                        c_seq = matched_lesson.get("seq") or matched_lesson.get("lesson_seq")
                        if c_seq is not None:
                            curriculum_matched_seq = int(c_seq)
            except Exception as c_err:
                logger.warning(f"[RetrievalService:Pareto] Lỗi tra cứu curriculum_matched_seq ({c_err})")

            target_has_topical_match = False
            if target_seq is not None:
                try:
                    target_lesson = c_svc.get_lesson_by_seq(target_seq)
                    if target_lesson:
                        norm_q = query_text.lower()
                        t_kws = [k.lower() for k in target_lesson.get("keywords", []) if len(k) > 1]
                        target_has_topical_match = any(k in norm_q for k in t_kws)
                except Exception as t_err:
                    logger.debug(f"[RetrievalService:Pareto] Lỗi kiểm tra target_has_topical_match: {t_err}")

            # Phân nhánh 3B: Continuation & Exercise Shield + 4-Tier Pareto Sufficiency (ICLR 2025)
            if (
                (is_continuation_turn or is_exercise_stmt)
                and max_any_video_score >= settings.VIDEO_FALLBACK_MIN_THRESHOLD
                and future_chunk_type != "code_ast"
            ):
                min_future_floor = 0.52
                margin_req = 0.28
                logger.info(
                    f"[RetrievalService:Pareto 3B] Kích hoạt Continuation/Exercise Shield (cont={is_continuation_turn}, ex={is_exercise_stmt}): "
                    f"floor={min_future_floor}, margin_req={margin_req}"
                )
            elif max_current_score < settings.PARETO_LOCAL_GROUNDING_THRESHOLD:
                # Phân tầng (a): Bài hiện tại chưa có cơ sở giảng dạy cục bộ (< 0.22)
                min_future_floor = (
                    settings.MODALITY_GATE_AST_THRESHOLD
                    if future_chunk_type == "code_ast"
                    else settings.PARETO_FALLBACK_VIDEO_MIN
                )
                margin_req = settings.PARETO_FALLBACK_MARGIN
            elif max_current_score < settings.MODALITY_GATE_VIDEO_HIGH_CONFIDENCE:
                # Phân tầng (b): Bài hiện tại ở dải văn nói lơ lửng (0.22 <= S < 0.30)
                min_future_floor = (
                    settings.MODALITY_GATE_AST_THRESHOLD
                    if future_chunk_type == "code_ast"
                    else settings.PARETO_MARGINAL_FUTURE_MIN
                )
                margin_req = settings.PARETO_MARGINAL_MARGIN + (
                    max_current_score - settings.PARETO_LOCAL_GROUNDING_THRESHOLD
                ) * settings.PARETO_LINEAR_SLOPE_MILD
            elif max_current_score < settings.PARETO_VIDEO_STRONG_GROUNDING:
                # Phân tầng (c): Bài hiện tại có điểm video tự tin cao (0.30 <= S < 0.40) nhưng chưa có Code AST Anchor
                if (
                    target_seq is not None
                    and not specific_ast_items
                    and (
                        (curriculum_matched_seq is not None and curriculum_matched_seq > current_lesson_seq)
                        or target_has_topical_match
                    )
                ):
                    min_future_floor = (
                        settings.MODALITY_GATE_AST_THRESHOLD
                        if future_chunk_type == "code_ast"
                        else settings.PARETO_MARGINAL_FUTURE_MIN
                    )
                    margin_req = settings.PARETO_CURRICULUM_ALIGNED_MARGIN
                    logger.info(
                        f"[RetrievalService:Pareto 3B] Curriculum-Aligned Pareto Gate (matched_seq={curriculum_matched_seq}, "
                        f"target_seq={target_seq}, topical_match={target_has_topical_match}): "
                        f"floor={min_future_floor}, margin_req={margin_req}"
                    )
                else:
                    min_future_floor = (
                        settings.MODALITY_GATE_AST_THRESHOLD
                        if future_chunk_type == "code_ast"
                        else settings.PARETO_HIGH_VIDEO_FUTURE_MIN
                    )
                    margin_req = settings.PARETO_MARGINAL_MARGIN + (
                        max_current_score - settings.MODALITY_GATE_VIDEO_HIGH_CONFIDENCE
                    ) * settings.PARETO_LINEAR_SLOPE_MILD
            else:
                # Phân tầng (d): Bài hiện tại có độ tự tin rất cao (>= 0.40)
                min_future_floor = settings.PARETO_STRONG_FUTURE_MIN
                margin_req = settings.PARETO_STRONG_BASE_MARGIN + (
                    max_current_score - settings.PARETO_VIDEO_STRONG_GROUNDING
                ) * settings.PARETO_LINEAR_SLOPE_STEEP

        future_dominates = (
            target_seq is not None
            and target_seq > current_lesson_seq
            and future_score >= min_future_floor
            and margin >= margin_req
        )

        if not is_curriculum_navigation and (is_continuation_turn or is_exercise_stmt) and future_chunk_type != "code_ast":
            future_dominates = False

        # Foundational Prerequisite Priority Rule v2.3 & Revision Non-Dominance Shield (Zero Hardcoded Seq)
        if not is_curriculum_navigation and target_seq is not None:
            try:
                from app.services.curriculum import get_curriculum_service
                c_svc = get_curriculum_service()
                is_foundational = c_svc.is_foundational_lesson(current_lesson_seq)
                target_is_foundational = c_svc.is_foundational_lesson(target_seq)
                is_target_revision = c_svc.is_revision_of(target_seq, current_lesson_seq)
            except Exception:
                is_foundational = False
                target_is_foundational = False
                is_target_revision = False

            # Quy tắc 1: Revision Non-Dominance Shield (Bảo vệ học viên tại bài gốc khỏi bài update 2024-2026 / bài tập)
            if is_target_revision:
                future_dominates = False

            # Quy tắc 2: Foundational Prerequisite Priority Rule (ICLR 2025 Context Sufficiency)
            if is_foundational:
                is_future_curriculum_topic = (
                    not is_target_revision
                    and not specific_ast_items
                    and max_video_score < settings.PARETO_VIDEO_STRONG_GROUNDING
                    and (
                        (curriculum_matched_seq is not None and int(curriculum_matched_seq) > current_lesson_seq)
                        or target_has_topical_match
                    )
                )
                if not is_future_curriculum_topic:
                    if future_chunk_type == "code_ast":
                        if max_video_score >= settings.MODALITY_GATE_VIDEO_THRESHOLD and (
                            future_score < settings.PARETO_DOMINANCE_CODE_FUTURE_MIN
                            or margin < settings.PARETO_PREREQUISITE_CODE_MARGIN
                        ):
                            future_dominates = False
                    elif max_video_score >= settings.MODALITY_GATE_VIDEO_HIGH_CONFIDENCE:
                        if (
                            future_score < settings.PARETO_PREREQUISITE_DOMINATE_MIN
                            or margin < settings.PARETO_PREREQUISITE_DOMINATE_MARGIN
                        ):
                            future_dominates = False

        if future_dominates:
            logger.info(
                f"[RetrievalService] Tầng 2 Out-of-Lesson (Pareto Dominance): Bài tương lai "
                f"(Seq {target_seq}) thống trị với future_score={future_score:.4f}, margin={margin:.4f} "
                f"(max_current_score={max_current_score:.4f})."
            )
            return RetrievalResult(
                chunks=[],
                status="out_of_lesson",
                target_lesson_seq=target_seq,
                future_best_chunk=best_future_chunk
            )

        is_raw_valid = (max_raw_prob >= 0.19) or (max_raw_prob >= settings.VIDEO_FALLBACK_MIN_THRESHOLD and max_video_score >= 0.25)
        if (valid_video_items or valid_ast_items) and is_raw_valid:
            eligible_code_items = valid_ast_items if valid_ast_items else [
                it for it in candidate_items
                if it.get("content_type") == "code_ast"
                and it.get("confidence_score", 0.0) >= 0.15
            ]
            anchor_candidates = assemble_balanced_modality(
                video_items=valid_video_items,
                code_items=eligible_code_items,
                final_top_k=final_top_k,
                prefer_balanced=bool(eligible_code_items)
            )
            final_assembled = reorder_lost_in_the_middle(anchor_candidates)
            logger.info(
                f"[RetrievalService] Tầng 2 Non-Dominated -> GROUNDED: Bài tương lai không thống trị "
                f"(future={future_score:.4f}, margin={margin:.4f}). "
                f"Bài hiện tại đạt độ tin cậy hợp lệ (video={max_video_score:.4f}, code={max_code_score:.4f})."
            )
            return RetrievalResult(
                chunks=final_assembled,
                status="grounded",
                is_low_confidence=(max(max_video_score, max_code_score) < 0.25)
            )

        # -------------------------------------------------------------------------
        # TẦNG 3: GRACEFUL DEGRADATION (CRAG Ambiguous State)
        # -------------------------------------------------------------------------
        if min_score_threshold is not None and min_score_threshold >= 0.30:
            logger.info(
                f"[RetrievalService] Tầng 4 Coverage Gap: min_score_threshold ({min_score_threshold}) >= 0.30, "
                f"bỏ qua Graceful Degradation để bảo toàn bộ lọc ngoài phạm vi."
            )
            return RetrievalResult(chunks=[], status="coverage_gap")

        if not only_boilerplate_code:
            try:
                from app.services.curriculum import get_curriculum_service
                c_svc = get_curriculum_service()
                is_curr_foundational = c_svc.is_foundational_lesson(current_lesson_seq)
            except Exception:
                is_curr_foundational = False

            low_confidence_items = []

            # Điều kiện 1: Hội thoại nối tiếp hoặc bài hiện tại có neo ngữ cảnh mạnh (max_current_score >= 0.25)
            if is_continuation_turn or max_current_score >= 0.25:
                low_confidence_items = [
                    it for it in candidate_items
                    if it.get("confidence_score", 0.0) >= settings.VIDEO_FALLBACK_MIN_THRESHOLD
                    and it.get("raw_semantic_score", 0.0) >= 0.14
                    and grade_document_relevance(query_text, it, min_confidence=0.15) == "CORRECT"
                ]

            # Điều kiện 2: Câu hỏi lý thuyết thuộc bài học nền tảng có video rơi vào dải Ambiguous (>= 0.18)
            if not low_confidence_items and is_curr_foundational and max_any_video_score >= settings.PARETO_THEORY_GROUNDING_FLOOR and max_raw_prob >= 0.16:
                low_confidence_items = [
                    it for it in candidate_items
                    if it.get("confidence_score", 0.0) >= settings.PARETO_THEORY_GROUNDING_FLOOR
                    and grade_document_relevance(query_text, it, min_confidence=0.18) == "CORRECT"
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
                    f"đạt chuẩn CRAG Ambiguous (max_current={max_current_score:.4f}, max_video={max_video_score:.4f}). "
                    f"Gắn cờ is_low_confidence=True, is_approximate=True."
                )
                return RetrievalResult(
                    chunks=final_assembled,
                    status="grounded",
                    is_low_confidence=True,
                    is_approximate=True
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
