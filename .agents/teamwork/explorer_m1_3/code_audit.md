# BÁO CÁO KIỂM TOÁN MÃ NGUỒN LÕI TRUY XUẤT & ĐẶC TẢ TRIỂN KHAI CHO CORE CODER (MILESTONE 2)

**Phụ trách:** Retrieval Code Inspector (`explorer_m1_3` / `@retrieval-inspector`)  
**Dự án:** In-Course Agentic RAG Copilot  
**Sinh viên thực hiện:** Trần Thành Nghĩa (MSSV: `23DH112252`), HUFLIT  
**Đối tượng bàn giao:** Core Retrieval Engineer (`@core-coder` - Milestone 2) & Orchestrator  
**Thời gian lập:** 2026-10-03  
**Tệp mục tiêu kiểm toán:**
- `app/services/retrieval.py`
- `app/config.py`
- `app/services/chat_graph.py`
- `app/schemas/search.py`, `app/schemas/chat.py`, `app/schemas/metadata.py`
- `data/metadata/lesson_code_video_binding.json`

---

## 1. TỔNG QUAN VÀ KẾT QUẢ KIỂM TOÁN (EXECUTIVE SUMMARY)

Đợt kiểm toán mã nguồn toàn diện đối với lõi truy xuất và các dịch vụ phụ thuộc đã xác nhận:
1. **Nguyên nhân cốt lõi gây ra 14 lỗi Tier 1:**
   - Trong `app/services/retrieval.py` (dòng 509), cổng thoát sớm video tại Tầng 1 đang sử dụng hằng số `settings.MODALITY_GATE_VIDEO_EARLY_EXIT = 0.50` thay vì `settings.MODALITY_GATE_VIDEO_THRESHOLD = 0.30`.
   - Do phân phối điểm thực tế của Video Transcript chỉ nằm trong dải $[0.30, 0.45]$, cổng Tầng 1 **bị khóa hoàn toàn** đối với các câu hỏi lý thuyết video bài hiện tại.
   - Luồng điều khiển rơi vào Tầng 2, hàm `_probe_future_lessons` bị gọi vô điều kiện. Do các bài học sau chứa mã nguồn và từ khóa lặp lại (`float/double`, `&&`, `%`, `swap`, `class`, `private`, `this`, `s[i]`), điểm bài tương lai dễ dàng vượt $0.40$ và biên độ $\Delta > 0.12$, khiến 9 câu hỏi hợp lệ bị nuốt oan thành `out_of_lesson`.
   - 5 câu hỏi còn lại rớt xuống Tầng 3 nhưng bị hàm `grade_document_relevance` (với ngưỡng ngầm $0.40$) loại bỏ, dẫn đến rớt oan xuống `coverage_gap`.
2. **Hiện trạng cổng độ trễ phẳng 0.22:**
   - Ngưỡng phẳng $0.22$ cũ đã từng được dùng để chặn `_probe_future_lessons` nhưng gây ra hiện tượng văn nói lướt ở bài cũ ($0.22 - 0.28$) nuốt bài mới (21 ca Tier 2).
   - Việc chuyển đổi sang Modality-Aware Gate đã được khởi tạo trong `retrieval.py` nhưng chưa hoàn thiện do mâu thuẫn giữa 2 hằng số `MODALITY_GATE_VIDEO_THRESHOLD = 0.30` và `MODALITY_GATE_VIDEO_EARLY_EXIT = 0.50`.
3. **Data/Code Separation Invariant:**
   - Hoàn toàn tuân thủ 100%: Mọi mốc liên kết Code-to-Video được nạp động từ file JSON `data/metadata/lesson_code_video_binding.json` qua `BINDING_MANIFEST_PATH`. Không có bất kỳ từ điển hay metadata nghiệp vụ nào bị hardcode trong mã nguồn Python (`.py`).
4. **Chuẩn Pydantic v2 & Typing:**
   - Toàn bộ các schemas trong `app/schemas/` (`SearchRequest`, `SearchChunkResult`, `SearchResponse`, `ChatRequest`, `StreamMetadataEvent`) đều tuân thủ nghiêm ngặt Pydantic v2 và typing type hints.

---

## 2. KẾT QUẢ KIỂM TOÁN CHI TIẾT THEO 4 TRỌNG TÂM (DEEP CODE AUDIT)

### 2.1. Cổng độ trễ phẳng (0.22) & Cổng Early Exit hiện tại

#### Vị trí lịch sử & thực trạng mã nguồn:
- Trong `app/config.py` (dòng 47):
  ```python
  FUTURE_PROBE_ACTIVATION_GATE: float = 0.22
  ```
- Trong `app/services/retrieval.py` (dòng 434–436):
  ```python
  effective_video_threshold = video_score_threshold if video_score_threshold is not None else (
      min_score_threshold if min_score_threshold is not None else settings.VIDEO_SCORE_THRESHOLD
  ) # VIDEO_SCORE_THRESHOLD = 0.22
  ```
- **Tại sao cổng phẳng 0.22 thất bại trong lịch sử:**
  - Video transcript của giảng viên thường có thói quen nhắc lướt qua các chủ đề tương lai (ví dụ: ở Bài 2 nhắc lướt *"sau này các bạn sẽ học class ở bài OOP"*).
  - Cross-Encoder chấm điểm các câu nhắc lướt này đạt trong dải $0.22 \le S < 0.30$.
  - Nếu dùng cổng phẳng $0.22$ để Early Exit, hệ thống tưởng rằng bài cũ đã dạy kiến thức này và khóa `grounded` ngay lập tức, tước đoạt cơ hội thăm dò bài tương lai (bài thực sự giảng dạy chuyên sâu). Điều này vi phạm *Relevance vs. Context Sufficiency Invariant (ICLR 2025)* và gây ra 21 ca lỗi Tier 2.

#### Vấn đề nghiêm trọng trong cài đặt hiện tại:
- Tại dòng 489–524 của `app/services/retrieval.py`:
  ```python
  valid_ast_items = [
      it for it in candidate_items
      if it.get("content_type") == "code_ast" and it.get("confidence_score", 0.0) >= settings.MODALITY_GATE_AST_THRESHOLD
  ]
  if valid_ast_items:
      # Early Exit AST
      ...
  
  valid_video_early_exit = [
      it for it in candidate_items
      if it.get("content_type") == "video_transcript" and it.get("confidence_score", 0.0) >= settings.MODALITY_GATE_VIDEO_EARLY_EXIT
  ]
  if valid_video_early_exit:
      # Early Exit Video
      ...
  ```
- Tại `app/config.py`:
  - Dòng 45: `MODALITY_GATE_VIDEO_THRESHOLD: float = 0.30`
  - Dòng 46: `MODALITY_GATE_VIDEO_EARLY_EXIT: float = 0.50`
- **Khuyết tật chết người:**
  - `retrieval.py` dòng 509 sử dụng `MODALITY_GATE_VIDEO_EARLY_EXIT` ($0.50$) thay vì `MODALITY_GATE_VIDEO_THRESHOLD` ($0.30$).
  - Trong thực tế, các đoạn Video Transcript của bài giảng có âm học tự nhiên và ngữ cảnh rộng, điểm số sau Sigmoid và RRF Joint Fusion dao động từ $0.30$ đến $0.46$.
  - Mức ngưỡng $0.50$ khiến cho **không một video transcript nào của bài hiện tại** vượt qua được Tầng 1!
  - Cổng Early Exit hoàn toàn tê liệt đối với các câu hỏi lý thuyết, buộc 100% các câu hỏi này phải chạy vào `_probe_future_lessons` ở Tầng 2.

---

### 2.2. Cơ chế hoạt động & Điểm kích hoạt của `_probe_future_lessons`

#### Cấu trúc hàm `_probe_future_lessons`:
Được định nghĩa tại dòng 160–275 của `app/services/retrieval.py`:
- **Chữ ký hàm:**
  ```python
  async def _probe_future_lessons(
      self,
      query_dense: List[float],
      sparse_indices: List[int],
      sparse_values: List[float],
      query_text: str,
      course_id: str,
      current_lesson_seq: int
  ) -> Tuple[Optional[int], float]
  ```
- **Logic truy vấn Qdrant:**
  - Tạo 2 bộ lọc In-HNSW:
    + `future_code_filter`: `course_id == course_id`, `lesson_seq > current_lesson_seq`, `content_type == "code_ast"`
    + `future_video_filter`: `course_id == course_id`, `lesson_seq > current_lesson_seq`, `content_type == "video_transcript"`
  - Thực hiện prefetch song song 4 luồng qua Qdrant Native RRF:
    + Dense Video (limit 12) + Sparse Video (limit 12)
    + Dense Code (limit 6) + Sparse Code (limit 6)
    + Fusion limit: `settings.FUTURE_PROBE_LIMIT` (hiện tại là 12).
  - Rerank các ứng viên thu được qua `self.embedding_service.rerank_documents` (Jina-v2 Cross-Encoder) và tính điểm Sigmoid + RRF Fusion:
    $$S_{\text{fused}} = 0.90 \cdot \sigma(z) + 0.10 \cdot \min\left(1.0, \frac{\text{RRF}}{0.8333}\right)$$
  - Trả về `(target_lesson_seq, max_score)` của chunk tương lai đạt điểm cao nhất.

#### Các điểm gọi (Invocation Points) trong `search()`:
Hàm `_probe_future_lessons` được gọi tại 2 vị trí trong `search()`:
1. **Vị trí 1 (Dòng 345–356):** Khi trong phạm vi bài hiện tại hoàn toàn không tìm thấy bất kỳ point nào (`if not raw_candidates:`).
   - Nếu tìm thấy bài tương lai có $S \ge \text{MIN\_SCORE\_THRESHOLD}$ ($0.25$): trả về `out_of_lesson`.
   - Nếu không: trả về `coverage_gap`.
   - *Đánh giá:* Vị trí này hoàn toàn đúng đắn.
2. **Vị trí 2 (Dòng 535–542):** Khi Tầng 1 không kích hoạt Early Exit:
   ```python
   target_seq, future_score = await self._probe_future_lessons(...)
   margin = future_score - max_current_score
   if target_seq and future_score >= settings.FUTURE_PROBE_MIN_CONFIDENCE and margin > settings.FUTURE_PROBE_MARGIN:
       return RetrievalResult(chunks=[], status="out_of_lesson", target_lesson_seq=target_seq)
   ```
   - *Đánh giá:* Do Tầng 1 bị hỏng ngưỡng video ($0.50$), hàm này bị gọi cho toàn bộ các câu hỏi lý thuyết in-scope.
   - **Hậu quả độ trễ:** Mỗi lần gọi `_probe_future_lessons` tốn thêm một vòng Round-trip Qdrant Cloud và một lượt suy luận Cross-Encoder trên 12–18 văn bản. Điều này làm độ trễ trung bình của Tier 1 tăng vọt lên **$10,874.6\text{ ms}$** ($\approx 10.9$ giây).

---

### 2.3. Cơ chế gắn nhãn phương thức (Modality Tagging) & Metadata Binding

Kiểm toán từ dòng 362–420 và 443–473 của `app/services/retrieval.py`:
1. **Phân biệt phương thức qua Point Payload:**
   - `content_type = p.get("content_type", "video_transcript")`
2. **Đối với `code_ast`:**
   - Trích xuất: `file_path`, `language`, `code_scope`, `start_line`, `end_line`, `context_code`.
   - **Ánh xạ mốc video Ground-Truth (Roadmap Phase 2):**
     ```python
     approx_vid_sec = p.get("approx_video_sec")
     if approx_vid_sec is None and self._code_video_bindings:
         lookup_key = f"{item['lesson_id']}:{code_scope}"
         approx_vid_sec = self._code_video_bindings.get(lookup_key)
         if approx_vid_sec is None:
             lesson_fallback = f"{item['lesson_id']}:function_main"
             approx_vid_sec = self._code_video_bindings.get(lesson_fallback)
     ```
   - Sinh thẻ timestamp video tự động:
     ```python
     if parsed_vid_sec is not None:
         lbl = f"{parsed_vid_sec//60:02d}:{parsed_vid_sec%60:02d}"
         item["timestamp_tag"] = f'<timestamp sec="{parsed_vid_sec}">{lbl}</timestamp>'
     ```
3. **Đối với `video_transcript`:**
   - Trích xuất: `video_title`, `start_sec`, `end_sec`, `start_label`, `end_label`.
   - Sinh thẻ timestamp: `<timestamp sec="{start_sec}">{start_lbl}</timestamp>`.
4. **Tính toán điểm số tin cậy (CRAG Joint Confidence Fusion):**
   - Áp dụng Logistic Sigmoid chuẩn hóa: $\sigma(z) = \frac{1}{1 + e^{-z}}$.
   - Hợp nhất với RRF qua tỷ lệ $\alpha = 0.90, \beta = 0.10$:
     ```python
     prob = alpha * raw_prob + settings.CRAG_RRF_WEIGHT * rrf_norm
     ```
   - Gắn nhãn `item["raw_semantic_score"]`, `item["confidence_score"]`, `item["confidence_pct"]`.

---

### 2.4. Khảo sát cấu hình & Nhập hằng số từ `app/config.py`

| Tên hằng số trong `Settings` | Giá trị hiện tại | Giá trị chuẩn hóa M2 | Tình trạng & Vai trò |
| :--- | :---: | :---: | :--- |
| `MODALITY_GATE_AST_THRESHOLD` | `0.35` | `0.35` | ✅ Đạt chuẩn — Ngưỡng nghiêm ngặt cho Code AST Anchor |
| `MODALITY_GATE_VIDEO_THRESHOLD` | `0.30` | `0.30` | ✅ Đạt chuẩn — Ngưỡng chuẩn hóa cho Video Early Exit |
| `MODALITY_GATE_VIDEO_EARLY_EXIT` | `0.50` | *(Xóa bỏ)* | 🚨 Lỗi thời — Gây vô hiệu hóa Tầng 1 Early Exit |
| `FUTURE_PROBE_ACTIVATION_GATE` | `0.22` | `0.22` | ✅ Đạt chuẩn — Ngưỡng sàn kích hoạt thăm dò |
| `FUTURE_PROBE_MARGIN` | `0.12` | `0.12` | ✅ Đạt chuẩn — Biên độ vượt trội tối thiểu ($\Delta \ge 0.12$) |
| `FUTURE_PROBE_MIN_CONFIDENCE` | `0.40` | `0.40` | ✅ Đạt chuẩn — Điểm sàn tự tin tối thiểu của bài tương lai |
| `FUTURE_PROBE_LIMIT` | `12` | `18` | ⚠️ Cần nâng lên 18 để phủ đủ số bài tương lai (OOP) |
| `DEFAULT_TOP_CANDIDATES` | `8` | `10` | ⚠️ Cần nâng lên 10 để tránh bão hòa candidate pool |
| `DEFAULT_FINAL_TOP_K` | `3` | `3` | ✅ Đạt chuẩn — U-shaped Context Assembly [Top 1, Top 3, Top 2] |
| `CRAG_RRF_WEIGHT` | `0.10` | `0.10` | ✅ Đạt chuẩn — Trọng số RRF trong CRAG Joint Fusion |
| `VIDEO_FALLBACK_MIN_THRESHOLD` | `0.15` | `0.15` | ✅ Đạt chuẩn — Ngưỡng sàn ngữ nghĩa sâu chống đối nghịch |

---

## 3. KIỂM TOÁN TÍNH TÁCH RỜI DỮ LIỆU & MÃ NGUỒN (DATA/CODE SEPARATION INVARIANT)

Quy chuẩn bất biến dự án yêu cầu:
> "Tuyệt đối KHÔNG hardcode các bảng tra cứu, từ điển ánh xạ metadata trực tiếp vào mã nguồn Python (.py). Mọi metadata nghiệp vụ bắt buộc phải được lưu trữ độc lập trong thư mục `data/metadata/*.json`."

### Kết quả kiểm toán:
1. **Đường dẫn tệp Manifest:**
   Trong `app/services/retrieval.py` dòng 17:
   ```python
   BINDING_MANIFEST_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "metadata" / "lesson_code_video_binding.json"
   ```
2. **Khởi tạo động trong Constructor:**
   Trong `RetrievalService.__init__` (dòng 150–159):
   ```python
   self._code_video_bindings: Dict[str, int] = {}
   if BINDING_MANIFEST_PATH.exists():
       try:
           with open(BINDING_MANIFEST_PATH, "r", encoding="utf-8") as bf:
               b_data = json.load(bf)
               self._code_video_bindings = b_data.get("bindings", {})
   ```
3. **Nội dung tệp JSON (`data/metadata/lesson_code_video_binding.json`):**
   - Đã được định nghĩa độc lập với 41 bindings (các bài 02, 03, 04, 06, 11, 53, 54, 56, 69).
   - Phiên bản: `2.1.0`.
4. **Kiểm tra cấm Hardcode:**
   - `grep_search` kiểm tra toàn bộ thư mục `app/` xác nhận: **0 dòng hardcode dictionary**, **0 dòng regex bắt riêng câu hỏi benchmark**.
   - Nguyên tắc **Zero Quick-Fix** được bảo toàn tuyệt đối 100%.

---

## 4. KIỂM TOÁN CHUẨN SCHEMA & TYPE ANNOTATIONS (PYDANTIC V2)

Kiểm toán các tệp schema tại `app/schemas/`:
1. `app/schemas/search.py`:
   - `SearchRequest`: Pydantic BaseModel, `ConfigDict(example=...)`, `min_length=2`, `max_length=500`, `lesson_seq >= 1`.
   - `SearchChunkResult`: Đầy đủ các trường phương thức kép (`video_transcript`, `code_ast`, `markdown_doc`), `confidence_pct`, `confidence_score`, `approx_video_sec`, `timestamp_tag`.
   - `SearchResponse`: Phân loại 3 trạng thái hợp lệ `Literal["grounded", "out_of_lesson", "coverage_gap"]`, cờ `is_low_confidence: bool`, `target_lesson_seq: Optional[int]`.
2. `app/schemas/chat.py`:
   - `StreamMetadataEvent`: Chứa đầy đủ `retrieval_status: Literal["grounded", "out_of_lesson", "coverage_gap", "fast_path"]`, `is_low_confidence: bool`, `target_lesson_seq: Optional[int]`.
3. `app/schemas/metadata.py`:
   - `ContentType(str, Enum)`, `BaseChunkPayload`, `VideoChunkPayload`, `CodeChunkPayload`.
4. `app/services/chat_graph.py`:
   - `AgentState(TypedDict)`: Đồng bộ đầy đủ các trường `retrieval_status`, `is_low_confidence`, `target_lesson_seq`, `suggested_timestamps`.
   - `retrieval_node`: Nhận `RetrievalResult` và cập nhật trọn vẹn vào `state`.
   - `crag_grader_node`: Xử lý mượt mà khi `retrieval_status == "grounded"` và `is_low_confidence == True` (tự động đính kèm `caution_notice`).
   - Không cần bất kỳ chỉnh sửa nào trong `chat_graph.py`.

---

## 5. BẢN ĐẶC TẢ TRIỂN KHAI CHO CORE CODER TRONG MILESTONE 2 (IMPLEMENTATION BLUEPRINT)

Kỹ sư `@core-coder` chỉ cần thực hiện chính xác các chỉnh sửa nguyên tử sau:

### 5.1. Chỉnh sửa tệp `app/config.py`

**Vị trí:** Dòng 40–52 của `app/config.py`.

#### Code Hiện Tại (Before):
```python
    DEFAULT_TOP_CANDIDATES: int = 8
    DEFAULT_FINAL_TOP_K: int = 3

    # Stage 6-9 Retrieval & CRAG Optimization (Chặng 2)
    MODALITY_GATE_AST_THRESHOLD: float = 0.35
    MODALITY_GATE_VIDEO_THRESHOLD: float = 0.30
    MODALITY_GATE_VIDEO_EARLY_EXIT: float = 0.50
    FUTURE_PROBE_ACTIVATION_GATE: float = 0.22
    FUTURE_PROBE_MARGIN: float = 0.12
    FUTURE_PROBE_MIN_CONFIDENCE: float = 0.40
    FUTURE_PROBE_LIMIT: int = 12
    CRAG_RRF_WEIGHT: float = 0.10
```

#### Code Cần Thay Thế (After):
```python
    DEFAULT_TOP_CANDIDATES: int = 10
    DEFAULT_FINAL_TOP_K: int = 3

    # Stage 6-9 Retrieval & CRAG Optimization (Chặng 2 - Modality-Aware Precision)
    MODALITY_GATE_AST_THRESHOLD: float = 0.35
    MODALITY_GATE_VIDEO_THRESHOLD: float = 0.30
    FUTURE_PROBE_ACTIVATION_GATE: float = 0.22
    FUTURE_PROBE_MARGIN: float = 0.12
    FUTURE_PROBE_MIN_CONFIDENCE: float = 0.40
    FUTURE_PROBE_LIMIT: int = 18
    CRAG_RRF_WEIGHT: float = 0.10
```

*Ghi chú thay đổi:*
- Xóa bỏ `MODALITY_GATE_VIDEO_EARLY_EXIT: float = 0.50`.
- Nâng `DEFAULT_TOP_CANDIDATES` từ `8` lên `10` để tránh nghẽn candidate pool.
- Nâng `FUTURE_PROBE_LIMIT` từ `12` lên `18` để tăng diện tích phủ bài học tương lai.

---

### 5.2. Chỉnh sửa tệp `app/services/retrieval.py`

**Vị trí:** Dòng 482–600 của `app/services/retrieval.py`.

#### Code Hiện Tại (Before - Dòng 482–600):
```python
        # [Retrieval Hierarchy Precedence Invariant - Chuẩn Yan et al. & ICLR 2025]
        # Bắt buộc tuân thủ 4 tầng phân cấp toán học nghiêm ngặt:
        #
        # Tầng 1: Grounded cấp cao qua AST Grounding Anchor hoặc Video High-Confidence (Early Exit)
        # 1. Nếu bài hiện tại có khối Code AST đạt confidence >= MODALITY_GATE_AST_THRESHOLD (0.35) -> Early Exit.
        # 2. Hoặc nếu Video Transcript bài hiện tại đạt confidence >= MODALITY_GATE_VIDEO_EARLY_EXIT (0.50)
        #    (Context Sufficiency tuyệt đối cho câu hỏi lý thuyết bài hiện tại) -> Early Exit.
        valid_ast_items = [
            it for it in candidate_items
            if it.get("content_type") == "code_ast" and it.get("confidence_score", 0.0) >= settings.MODALITY_GATE_AST_THRESHOLD
        ]
        if valid_ast_items:
            logger.info(f"[RetrievalService] Tầng 1: Khóa grounded qua AST Grounding Anchor ({len(valid_ast_items)} chunks) -> Early Exit.")
            top_ast = sorted(
                valid_ast_items,
                key=lambda x: x["confidence_score"],
                reverse=True
            )[:final_top_k]
            final_assembled = reorder_lost_in_the_middle(top_ast)
            return RetrievalResult(
                chunks=final_assembled,
                status="grounded",
                is_low_confidence=False
            )

        valid_video_early_exit = [
            it for it in candidate_items
            if it.get("content_type") == "video_transcript" and it.get("confidence_score", 0.0) >= settings.MODALITY_GATE_VIDEO_EARLY_EXIT
        ]
        if valid_video_early_exit:
            logger.info(f"[RetrievalService] Tầng 1: Khóa grounded qua Video Early Exit Gate ({len(valid_video_early_exit)} chunks) -> Early Exit.")
            top_vid = sorted(
                valid_video_early_exit,
                key=lambda x: x["confidence_score"],
                reverse=True
            )[:final_top_k]
            final_assembled = reorder_lost_in_the_middle(top_vid)
            return RetrievalResult(
                chunks=final_assembled,
                status="grounded",
                is_low_confidence=False
            )

        # Tầng 2: Thăm dò bài tương lai (Future Lesson Probing - Giải pháp A)
        # BẮT BUỘC thực hiện khi bài hiện tại KHÔNG có Code AST Grounding Anchor hoặc Video Early Exit.
        # Khắc phục triệt để hiện tượng "bài cũ nuốt bài mới":
        # - Nhóm 1 (11 ca): Video bài cũ đạt 0.22 <= S < 0.36 khiến Flat Gate cũ đóng sớm.
        # - Nhóm 2 (10 ca): Video bài cũ nói lướt đạt S >= 0.40 nhưng vi phạm Context Sufficiency (ICLR 2025).
        max_current_score = max([it.get("confidence_score", 0.0) for it in candidate_items], default=0.0)
        target_seq = None
        future_score = 0.0
        margin = 0.0

        target_seq, future_score = await self._probe_future_lessons(
            query_dense=query_dense,
            sparse_indices=sparse_indices,
            sparse_values=sparse_values,
            query_text=query_text,
            course_id=course_id,
            current_lesson_seq=current_lesson_seq
        )
        margin = future_score - max_current_score

        # Future Context Sufficiency Gate (Pareto-Optimal Boundary - Yan et al. & ICLR 2025):
        # Bài tương lai CHỈ ĐƯỢC PHÉP nuốt bài hiện tại khi bản thân nó là một ngữ cảnh hoàn chỉnh:
        # 1. Đạt chuẩn CRAG Context Sufficiency: future_score >= FUTURE_PROBE_MIN_CONFIDENCE (0.40)
        # 2. VƯỢT TRỘI bài hiện tại với biên độ rõ ràng: margin > FUTURE_PROBE_MARGIN (0.12)
        if target_seq and future_score >= settings.FUTURE_PROBE_MIN_CONFIDENCE and margin > settings.FUTURE_PROBE_MARGIN:
            logger.info(
                f"[RetrievalService] Tầng 2: Phát hiện chủ đề bài tương lai (Seq {target_seq}) vượt trội với score={future_score:.4f} (Margin Δ={margin:.4f} > {settings.FUTURE_PROBE_MARGIN})."
            )
            return RetrievalResult(chunks=[], status="out_of_lesson", target_lesson_seq=target_seq)

        # Tầng 3: Thẩm định CRAG chuẩn (ngưỡng cao >= 0.40) cho Video Transcript bài hiện tại
        # Chỉ áp dụng khi bài tương lai KHÔNG vượt trội, và video bài hiện tại thực sự giảng giải chi tiết
        crag_verified_items = [
            it for it in scored_items
            if grade_document_relevance(query_text, it) == "CORRECT"
        ]
        if crag_verified_items:
            top_reranked = sorted(
                crag_verified_items,
                key=lambda x: x["confidence_score"],
                reverse=True
            )[:final_top_k]
            final_assembled = reorder_lost_in_the_middle(top_reranked)
            logger.info(f"[RetrievalService] Tầng 3: Hoàn tất CRAG Verification với {len(final_assembled)} chunks hợp lệ.")
            return RetrievalResult(
                chunks=final_assembled,
                status="grounded",
                is_low_confidence=False
            )

        # Tầng 4: Hạ chuẩn có kiểm soát (Graceful Degradation) nếu bài hiện tại đạt ngưỡng sàn >= 0.20
        # Và yêu cầu độ tương quan ngữ nghĩa sâu >= VIDEO_FALLBACK_MIN_THRESHOLD để ngăn chặn hoàn toàn câu hỏi đối nghịch
        low_confidence_items = [
            it for it in candidate_items
            if it.get("confidence_score", 0.0) >= 0.20
            and it.get("raw_semantic_score", 0.0) >= settings.VIDEO_FALLBACK_MIN_THRESHOLD
            and grade_document_relevance(query_text, it, min_confidence=0.20) == "CORRECT"
        ]
        if low_confidence_items:
            logger.info(f"[RetrievalService] Tầng 4: Kích hoạt Graceful Degradation: {len(low_confidence_items)} chunks đạt ngưỡng tham khảo >= 0.20.")
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

        # Tầng 5: Khoảng trống học liệu (Coverage Gap) khi cả bài hiện tại và bài tương lai đều không đạt
        logger.info(f"[RetrievalService] Tầng 5: Không tìm thấy ngữ cảnh phù hợp (max_current={max_current_score:.4f}, future={future_score:.4f}) -> 'coverage_gap'.")
        return RetrievalResult(chunks=[], status="coverage_gap")
```

#### Code Cần Thay Thế (After):
```python
        # =========================================================================
        # [RETRIEVAL HIERARCHY PRECEDENCE INVARIANT - YAN ET AL. & ICLR 2025]
        # Bắt buộc tuân thủ 4 tầng phân cấp toán học một chiều nghiêm ngặt:
        # =========================================================================

        # -------------------------------------------------------------------------
        # TẦNG 1: GROUNDED ANCHOR & MODALITY-AWARE EARLY EXIT
        # -------------------------------------------------------------------------
        # Điều kiện:
        # 1. Có khối Code AST đạt ngưỡng cú pháp >= MODALITY_GATE_AST_THRESHOLD (0.35), HOẶC
        # 2. Có Video Transcript đạt ngưỡng hội thoại >= MODALITY_GATE_VIDEO_THRESHOLD (0.30).
        # Hành vi: Khóa ngay GROUNDED, triệt tiêu hoàn toàn Future Probing (tiết kiệm 1.5s - 2.5s).
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

        if valid_ast_items or valid_video_items:
            anchor_candidates = sorted(
                valid_ast_items + valid_video_items,
                key=lambda x: x["confidence_score"],
                reverse=True
            )[:final_top_k]
            final_assembled = reorder_lost_in_the_middle(anchor_candidates)
            logger.info(
                f"[RetrievalService] Tầng 1 Early Exit: Khóa GROUNDED thành công "
                f"({len(valid_ast_items)} AST, {len(valid_video_items)} Video chunks). "
                f"Triệt tiêu future probing."
            )
            return RetrievalResult(
                chunks=final_assembled,
                status="grounded",
                is_low_confidence=False
            )

        # -------------------------------------------------------------------------
        # TẦNG 2: FUTURE LESSON PROBING (Chỉ chạy khi bài hiện tại thực sự thiếu thông tin)
        # -------------------------------------------------------------------------
        # Khắc phục hiện tượng bài cũ nuốt bài mới (ICLR 2025 Context Sufficiency):
        # Bài tương lai chỉ được phép nuốt bài hiện tại khi:
        # (a) future_score >= FUTURE_PROBE_MIN_CONFIDENCE (0.40)
        # (b) margin = future_score - max_current_score >= FUTURE_PROBE_MARGIN (0.12)
        max_current_score = max([it.get("confidence_score", 0.0) for it in candidate_items], default=0.0)
        target_seq = None
        future_score = 0.0
        margin = 0.0

        target_seq, future_score = await self._probe_future_lessons(
            query_dense=query_dense,
            sparse_indices=sparse_indices,
            sparse_values=sparse_values,
            query_text=query_text,
            course_id=course_id,
            current_lesson_seq=current_lesson_seq
        )
        margin = future_score - max_current_score

        if target_seq and future_score >= settings.FUTURE_PROBE_MIN_CONFIDENCE and margin >= settings.FUTURE_PROBE_MARGIN:
            logger.info(
                f"[RetrievalService] Tầng 2 Out-of-Lesson: Phát hiện chủ đề bài tương lai "
                f"(Seq {target_seq}) vượt trội với score={future_score:.4f} (Margin Δ={margin:.4f} >= {settings.FUTURE_PROBE_MARGIN})."
            )
            return RetrievalResult(chunks=[], status="out_of_lesson", target_lesson_seq=target_seq)

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
```

---

## 6. DANH MỤC KIỂM TRA CHO MILESTONE 2 (@core-coder CHECKLIST)

Sau khi `@core-coder` áp dụng mã nguồn trên, cần kiểm tra các điểm sau:
- [ ] Không còn sự hiện diện của `MODALITY_GATE_VIDEO_EARLY_EXIT` trong cả `app/config.py` và `app/services/retrieval.py`.
- [ ] `valid_video_items` trong Tầng 1 sử dụng đúng `settings.MODALITY_GATE_VIDEO_THRESHOLD` ($0.30$).
- [ ] Tầng 1 kết hợp cả `valid_ast_items + valid_video_items` để lấy top chunks có điểm cao nhất qua `reorder_lost_in_the_middle`.
- [ ] Tầng 2 chỉ kích hoạt khi Tầng 1 không thỏa mãn, và kiểm tra điều kiện `future_score >= 0.40` cùng `margin >= 0.12`.
- [ ] Tầng 3 (Graceful Degradation) thẩm định với sàn $0.20$ và `raw_semantic_score >= 0.15`.
- [ ] `DEFAULT_TOP_CANDIDATES = 10` và `FUTURE_PROBE_LIMIT = 18` được nạp đúng từ `app/config.py`.
- [ ] Toàn bộ lệnh import và Pydantic schema không phát sinh cảnh báo lỗi linter.
