# NHIỆM VỤ SPEC 004 — SỬA ĐỒNG BỘ WORKFLOW RAG LIÊN TẦNG & LOGIC FALLBACK (PSTACK + CONFLICT MATRIX)
> **Dự án:** In-Course Agentic RAG Copilot — LangGraph Stateful Orchestration  
> **Tác giả:** Trần Thành Nghĩa (MSSV: `23DH112252`), Trường Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT)  
> **Ngày lập:** 2026-11-25  
> **Đặc tả đầu ra bắt buộc:** `specs/004-unified-rag-workflow-hardening/spec.md` (kèm Cross-Layer Conflict Matrix & Dependency-Ordered Changes)  
> **Nguyên tắc tối thượng:** Cross-Layer Unified Fix (Sửa theo toàn luồng, cấm vá cục bộ) | 0% Regex Runtime | 0% Quick-Fix | 0% Test-Set Snooping

---

## 0. BẤT BIẾN HẠ TẦNG & MỐC BASELINE KHÔNG ĐƯỢC HỒI QUY (DO NOT REGRESS)
1. **Phần cứng & ONNX (RTX 2050 4 GB VRAM):**
   - Giữ `onnxruntime-gpu==1.23.2`, Dense E5 (`intfloat/multilingual-e5-large`) trên GPU, `jina-reranker-v2-int8` trên CPU (`USE_CPU_RERANKER=True`, `USE_INT8_RERANKER=True`, `RERANK_CPU_THREADS=4`).
   - Mọi lệnh kiểm thử chạy **tuần tự từng tiến trình** với `HF_HUB_OFFLINE=1` và `TRANSFORMERS_OFFLINE=1`.
2. **Mốc Chất lượng Bắt buộc Bảo toàn:**
   - **Sequential Pytest (`11` suites):** `100% PASSED` (96/96+ tests, 0 failed, 0 skipped) + bổ sung unit test mới cho toàn bộ ca trong Spec 004.
   - **E2E Matrix (`scripts/e2e_matrix_harness.py --suite all --routing-only`):** **`all_passed: true` (`9/9` suites: `M1..M3`, `S1`, `M4..M8`)**, Critic Health $\ge 90/100$, Socratic `100.0%`.
   - **Macro Benchmark (Chống Goodhart's Law):**
     - Multi-Turn (`50` sessions / `222` turns): Intent $\ge 94.0\%$, Retrieval Status $\ge 90.0\%$ (hiện tại `90.54%`), ARR $\ge 97.0\%$, SRP $= 100.0\%$.
     - Stage 11 Golden 200: Router $\ge 90.5\%$, CRAG Precision $\ge 86.0\%$, Timestamp Safety $\ge 86.5\%$.

---

## 1. HAI CỤM VẤN ĐỀ CẦN GIẢI QUYẾT ĐỒNG BỘ TOÀN LUỒNG (PROBLEM CLASSES)

### Cụm A — Hệ thống Fallback Liên Tầng (`IntentRouter -> ChatGraph -> RetrievalService -> ChatService`)
1. **`app/agent/router.py#L874-L878` & `#L161-L177` (Contextual NLI Fallback):**
   - `self._nli_arbiter.arbitrate(contextual_prompt)` trả về `(pred_intent, top_score)` trong đó `top_score` là điểm của nhãn thắng cuộc `pred_intent`.
   - Dòng 875 viết `if nli_intent == "course_query" or nli_conf >= settings.ROUTER_CONTEXTUAL_NLI_MIN_CONF:` (`or` thay vì `and`), làm các câu `out_of_scope` có `nli_conf >= 0.45` bị ép nhầm thành `course_query`.
   - Đồng thời kiểm tra `#L209-L211` (`verify_in_video_temporal_query` fail-open trả `(True, 0.0)` khi lỗi model NLI) để bảo đảm xử lý an toàn, không lọt câu ngoài lề.
2. **`app/services/chat_graph.py#L760-L779` (Contextual Retrieval Fallback trong `retrieval_node`):**
   - Khi `raw_prompt` ban đầu trả về `coverage_gap` (`0` chunks), nhánh dự phòng chạy lại bằng `search_query` (đã nối `anchor_query`), nhưng dòng 776 đòi `and not fallback_res.is_low_confidence`, vô tình vứt bỏ kết quả `grounded (is_low_confidence=True)` của Tầng 3 Graceful Degradation để giữ `coverage_gap`.
   - Cần phân biệt: khi kết quả gốc là `coverage_gap`, chấp nhận `fallback_res` nếu `status in ("grounded", "out_of_lesson")` (kể cả `is_low_confidence=True`); chỉ đòi `not fallback_res.is_low_confidence` khi kết quả gốc đã `grounded`.
3. **`app/services/retrieval.py#L700-L712` & `#L1770-L1785` (RRF Min-Max Division Collapse trên 1 candidate):**
   - Khi Cross-Encoder gặp lỗi (`is_fallback_rrf=True` hoặc exception trong `_score_future_points`), nếu chỉ có `1` candidate (hoặc các điểm RRF bằng nhau: `max_rrf == min_rrf`), `(rrf_raw - min_rrf) / (max_rrf - min_rrf + 1e-6)` cho `0.0` → `raw_prob = 0.20`, rớt dưới cả `VIDEO_SCORE_THRESHOLD (0.22)` và `CODE_SCORE_THRESHOLD (0.35)`.
   - Cần xử lý chuẩn toán học khi `max_rrf - min_rrf <= 1e-6` (neo đỉnh `1.0` nếu `rrf_raw > 0` hoặc tỷ lệ hợp lý) mà không phá phân phối khi `len >= 2`.
4. **`app/services/retrieval.py#L2241-L2256` & `#L591-L611` & `app/services/chat.py#L2276-L2293`:**
   - Tầng 3 Graceful Degradation (`#L2241-L2256`) gọi `grade_document_relevance(..., min_confidence=0.15/0.18)` mà không lọc `content_type == "video_transcript"`, khiến `code_ast` điểm `0.15..0.18` (dưới xa chuẩn `0.35`) lọt qua.
   - `_build_lightweight_future_chunk` (`#L591-L611`) khi thiếu cả Qdrant hit lẫn chapter gắn `is_approximate=False` cho mốc mặc định `00:00` → cần đánh dấu `is_approximate=True` (hoặc không gán nhãn chắc chắn cho mốc giả).
   - `ChatService` (`#L2276-L2293`) Deterministic Timestamp Fallback nếu LLM đã viết dòng `📍 **Mốc video bài giảng:**` kèm chữ mô tả ngoài thẻ `<timestamp>`, cần tránh nối trùng dòng `📍` thứ hai.

### Cụm B — Problem Class Điều Hướng Khái Niệm Tương Lai Có Kèm Bối Cảnh Hiện Tại (`M6-T03`, `M7-T02`, `M8-T03`)
- **Bằng chứng thực nghiệm từ `logs/playground_debug/e2e_matrix_latest_summary.json` (`--suite deep --routing-only`):**
  - `M6-T03` (ở Bài 37 `cpp-core`): *"Vậy muốn tự quản lý ngăn xếp không dùng đệ quy nữa thì học cấu trúc Stack ở bài nào và hai thao tác push pop tốn O(1) không?"* → `is_nav=True`, nhưng `find_lesson_for_query` trả **`L37`** (trong khi `find_ambiguous_candidates` ra `[43, 37, 68]`), dẫn tới `RetrievalService` khóa `focused_lesson_seq = 37` và `Pareto 3A` xóa `target_seq` → kẹt `grounded` L37 thay vì `out_of_lesson -> L43`.
  - `M7-T02` (ở Bài 53 `cpp-oop`): *"Nếu tạo 3 object SinhVien rồi muốn đếm tổng số sinh viên đã tạo bằng biến dùng chung cho cả class thì học ở bài nào và dùng từ khóa gì?"* → `is_nav=True`, `find_lesson_for_query` trả **`L53`** (`amb=[53, 41, 55, 69]`), kẹt `grounded` L53 thay vì `out_of_lesson -> L54`.
  - `M8-T03` (ở Bài 57 `cpp-oop`): *"Nếu dùng con trỏ next để nối các Node rời rạc trong bộ nhớ thay cho mảng cố định thì học ở bài nào?"* → `is_nav=True`, `find_lesson_for_query` trả **`L57`** (`amb=[57, 58, 79, 64]`), kẹt `grounded` L57 thay vì `out_of_lesson -> L58`.
- **Yêu cầu gốc rễ (0% Quick-Fix, 0% Snooping):**
  - Truy vết toàn bộ tương tác giữa `CurriculumService.find_lesson_for_query` (`#L1200-L1386`, đặc biệt bước `DAG Prerequisite Root Selection` chọn `min seq` trùng bài hiện tại), từ khóa học thuật chuẩn trong `lessons_manifest.json` (như Bài 54 `static` / biến tĩnh dùng chung, Bài 58 `Node` / `next`), và `RetrievalService.search` (`#L1483-L1488`, `#L1613-L1634`, `#L2010-L2030`) khi `curriculum_matched_seq == current_lesson_seq` nhưng câu hỏi là điều hướng lộ trình (`"...học ở bài nào..."`)!
  - Thiết kế cơ chế tổng quát (bảo vệ toàn vẹn các ca hỏi lại bài hiện tại/bài trước trong `M1..M5`, `S1`, `Golden 200`, `Multi-turn`) và khóa trong **Cross-Layer Conflict Matrix**.

---

## 2. YÊU CẦU KIỂM CHỨNG CUỐI CÙNG (HARNESS VERIFICATION GATE)
Sau khi hoàn tất sửa code theo Spec 004, bắt buộc chạy tuần tự qua Harness:
```powershell
.\.venv\Scripts\python.exe scripts\master_autonomous_harness.py --stage 1 --force-eval
```
Chỉ kết luận **PASS** khi AST + 11 Pytest Suites + E2E Matrix (`M1..M8` + `S1`, `all_passed: true`) + Macro Benchmarks đều xanh sạch và 0% quick-fix/regex trong `git diff app/`.
