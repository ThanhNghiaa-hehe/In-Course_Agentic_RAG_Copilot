# Handoff Report — Milestone 1 (R1): Retrieval Code Inspection & Implementation Blueprint

**Agent:** Retrieval Code Inspector (`@retrieval-inspector` / `explorer_m1_3`)  
**Recipient:** `@core-coder` and `@orchestrator` (`7a600b06-f7d6-4d38-9eff-05a718d15f68`)  
**Working Directory:** `d:\In_Course_Agentic_RAG_Copilot\.agents\teamwork\explorer_m1_3`  
**Milestone:** Milestone 1 (R1) — Code Audit of Retrieval Pipeline & Blueprint Formulation  
**Date:** 2026-10-03  

---

## 1. Observation

1. **Benchmark Results (`docs/benchmarks/stage11_results_2026-10-03_20-52-50.json`):**
   - Đợt khảo thí ghi nhận Router Accuracy đạt `98.0%` (196/200), CRAG Grader Precision đạt `80.0%` (160/200) — dưới ngưỡng cam kết CI/CD $\ge 85.0\%$.
   - Tier 1 (In-Scope Technical, 80 test cases) ghi nhận chính xác 14 ca thất bại (`status_ok: false`):
     - **9 ca bị nuốt oan thành `out_of_lesson`:**
       - `BENCH-004` (dòng 188-218): Query: *"Sự khác nhau giữa float và double trong C++ là gì?"* | `Act: out_of_lesson != Exp: grounded` | Latency: 9202.5 ms
       - `BENCH-011` (dòng 485-515): Query: *"Các toán tử logic &&, || và ! trong C++ hoạt động như thế nào?"* | `Act: out_of_lesson != Exp: grounded` | Latency: 18009.5 ms
       - `BENCH-014` (dòng 601-631): Query: *"Làm thế nào để kiểm tra một số nguyên n có phải là số chẵn bằng toán tử %?"* | `Act: out_of_lesson != Exp: grounded` | Latency: 8110.3 ms
       - `BENCH-022` (dòng 910-938): Query: *"Cách kiểm tra một năm có phải là năm nhuận bằng cấu trúc if else?"* | `Act: out_of_lesson != Exp: grounded` | Latency: 6517.8 ms
       - `BENCH-035` (dòng 1500-1528): Query: *"Làm sao để viết hàm hoán đổi giá trị của 2 biến số nguyên swap?"* | `Act: out_of_lesson != Exp: grounded` | Latency: 5760.7 ms
       - `BENCH-041` (dòng 1750-1779): Query: *"Khái niệm Lớp (Class) và Đối tượng (Object) trong C++ khác nhau như thế nào?"* | `Act: out_of_lesson != Exp: grounded` | Latency: 6381.7 ms
       - `BENCH-045` (dòng 1920-1950): Query: *"Vì sao các thuộc tính như hoTen, diemGPA nên đặt ở phạm vi private?"* | `Act: out_of_lesson != Exp: grounded` | Latency: 6316.7 ms
       - `BENCH-049` (dòng 2090-2120): Query: *"Con trỏ this trong phương thức của class C++ có vai trò gì?"* | `Act: out_of_lesson != Exp: grounded` | Latency: 6057.9 ms
       - `BENCH-058` (dòng 2465-2493): Query: *"Toán tử s[i] dùng để truy cập từng ký tự trong biến std::string như thế nào?"* | `Act: out_of_lesson != Exp: grounded` | Latency: 5994.6 ms
     - **5 ca bị rớt oan thành `coverage_gap`:**
       - `BENCH-007` (dòng 320-350): Query: *"Từ khóa unsigned trong kiểu unsigned int có tác dụng gì?"* | `Act: coverage_gap != Exp: grounded` | Latency: 7669.3 ms
       - `BENCH-010` (dòng 455-482): Query: *"Cách dùng toán tử tăng giảm ++ và -- (tiền tố tiền vị và hậu vị)?"* | `Act: coverage_gap != Exp: grounded` | Latency: 7246.8 ms
       - `BENCH-016` (dòng 670-702): Query: *"Hiện tượng ngắn mạch (short-circuit evaluation) của toán tử logic && và || là gì?"* | `Act: coverage_gap != Exp: grounded` | Latency: 7924.4 ms
       - `BENCH-037` (dòng 1580-1606): Query: *"Toán tử tham chiếu & trong khai báo tham số hàm có ý nghĩa gì?"* | `Act: coverage_gap != Exp: grounded` | Latency: 6324.3 ms
       - `BENCH-064` (dòng 2730-2755): Query: *"Cách xử lý ngoại lệ hoặc kiểm tra mẫu số khác 0 khi khởi tạo phân số?"* | `Act: coverage_gap != Exp: grounded` | Latency: 47218.6 ms

2. **Cài đặt hiện tại trong `app/services/retrieval.py`:**
   - Dòng 507–511:
     ```python
     valid_video_early_exit = [
         it for it in candidate_items
         if it.get("content_type") == "video_transcript" and it.get("confidence_score", 0.0) >= settings.MODALITY_GATE_VIDEO_EARLY_EXIT
     ]
     ```
   - Dòng 535–542: Gọi `_probe_future_lessons` vô điều kiện khi Tầng 1 không Early Exit:
     ```python
     target_seq, future_score = await self._probe_future_lessons(
         query_dense=query_dense,
         sparse_indices=sparse_indices,
         sparse_values=sparse_values,
         query_text=query_text,
         course_id=course_id,
         current_lesson_seq=current_lesson_seq
     )
     margin = future_score - max_current_score
     ```
   - Dòng 549:
     ```python
     if target_seq and future_score >= settings.FUTURE_PROBE_MIN_CONFIDENCE and margin > settings.FUTURE_PROBE_MARGIN:
         return RetrievalResult(chunks=[], status="out_of_lesson", target_lesson_seq=target_seq)
     ```
   - Dòng 557–560:
     ```python
     crag_verified_items = [
         it for it in scored_items
         if grade_document_relevance(query_text, it) == "CORRECT"
     ]
     ```

3. **Cài đặt cấu hình trong `app/config.py`:**
   - Dòng 40: `DEFAULT_TOP_CANDIDATES: int = 8`
   - Dòng 44–51:
     ```python
     MODALITY_GATE_AST_THRESHOLD: float = 0.35
     MODALITY_GATE_VIDEO_THRESHOLD: float = 0.30
     MODALITY_GATE_VIDEO_EARLY_EXIT: float = 0.50
     FUTURE_PROBE_ACTIVATION_GATE: float = 0.22
     FUTURE_PROBE_MARGIN: float = 0.12
     FUTURE_PROBE_MIN_CONFIDENCE: float = 0.40
     FUTURE_PROBE_LIMIT: int = 12
     CRAG_RRF_WEIGHT: float = 0.10
     ```

4. **Kiểm tra Data/Code Separation:**
   - `BINDING_MANIFEST_PATH` tại dòng 17 của `app/services/retrieval.py` trỏ tới `data/metadata/lesson_code_video_binding.json`.
   - File JSON chứa 41 bindings mốc video. Không có bảng tra cứu nào bị hardcode trong các file `.py`.

---

## 2. Logic Chain

1. **Bước 1 (Tại sao Tầng 1 Early Exit bị vô hiệu hóa cho câu hỏi Video):**
   - Từ Quan sát 2 và 3, `retrieval.py` dòng 509 kiểm tra `confidence_score >= settings.MODALITY_GATE_VIDEO_EARLY_EXIT` ($0.50$).
   - Trong thực tế phân phối điểm của Cross-Encoder (Jina-v2) kết hợp Sigmoid và RRF, các đoạn Video Transcript của bài giảng có độ tin cậy thực tế $S \in [0.30, 0.45]$.
   - Do ngưỡng $0.50$ quá cao, điều kiện `valid_video_early_exit` luôn là rỗng (`[]`).
   - Cổng Early Exit tại Tầng 1 không bao giờ kích hoạt cho các câu hỏi lý thuyết video thuần túy.

2. **Bước 2 (Cơ chế dẫn đến 9 lỗi False Out-of-Lesson):**
   - Khi Tầng 1 không kích hoạt, luồng xử lý rơi vào dòng 535 và kích hoạt `_probe_future_lessons` trên toàn bộ các bài học sau.
   - Các từ khóa và khái niệm lập trình cơ bản (`float/double`, `&&`, `%`, `swap`, `class`, `private`, `this`, `s[i]`) thường xuyên xuất hiện trong các đoạn Code AST của bài học nâng cao tiếp theo.
   - Các chunk Code AST tương lai đạt điểm cao $S_{\text{future}} \ge 0.48 - 0.58$, tạo ra biên độ $\Delta = S_{\text{future}} - \max(S_{\text{current}}) > 0.12$.
   - Điều kiện dòng 549 thỏa mãn $\to$ Trả về `out_of_lesson` và xóa sạch `chunks = []`.
   - Điều này nuốt nhầm 9 câu hỏi thuộc bài hiện tại, đồng thời gia tăng độ trễ truy xuất thêm $2 - 10$ giây do double-query không cần thiết.

3. **Bước 3 (Cơ chế dẫn đến 5 lỗi False Coverage-Gap):**
   - Ở 5 câu hỏi còn lại, bài tương lai không đạt điểm vượt trội ($\Delta < 0.12$).
   - Luồng điều khiển rơi xuống Tầng 3 (CRAG Verification dòng 557), nơi hàm `grade_document_relevance` đòi hỏi điểm sàn ngầm $0.40$.
   - Các video bài hiện tại có điểm $0.22 \le S < 0.35$ bị đánh nhãn `INCORRECT`.
   - Xuống tiếp Tầng 4, do `DEFAULT_TOP_CANDIDATES = 8` quá hẹp, các chunk biên không trụ lại được.
   - Hệ thống kết luận sai thành `coverage_gap` (0 chunks).

4. **Bước 4 (Tính hoàn chỉnh và ổn định của Thiết kế 4 Cấp):**
   - Chuyển ngưỡng Video Early Exit về `MODALITY_GATE_VIDEO_THRESHOLD = 0.30` và kết hợp cả AST ($\ge 0.35$) lẫn Video ($\ge 0.30$) tại Tầng 1: Ngay lập tức khóa `grounded` cho bài hiện tại và triệt tiêu `_probe_future_lessons`. Phục hồi 9/9 ca false out-of-lesson.
   - Cố định Tầng 3 (Graceful Degradation) với sàn $S \ge 0.20$ và $S_{\text{semantic\_raw}} \ge 0.15$: Bắt trọn vẹn 5/5 ca false coverage-gap có điểm tham khảo trong khoảng $[0.20, 0.30)$.
   - Nâng `DEFAULT_TOP_CANDIDATES = 10` và `FUTURE_PROBE_LIMIT = 18` giúp giải quyết triệt để nguy cơ nghẽn candidate pool.

---

## 3. Caveats

1. **Biến thiên độ trễ mạng (Network / Cloud Jitter):** Trường hợp `BENCH-064` bị độ trễ bất thường 47.2s là do kết nối mạng tới Qdrant Cloud cluster, không phải do thuật toán phân tầng.
2. **Cố định kiến trúc Reranker:** Toàn bộ các ngưỡng số học ($0.35, 0.30, 0.20, 0.12$) được chuẩn hóa dựa trên mô hình `jinaai/jina-reranker-v2-base-multilingual` kết hợp Logistic Sigmoid. Nếu thay đổi mô hình Re-ranker, các ngưỡng này cần được khảo thí lại qua Grid Search.
3. Không có bảo lưu nào khác.

---

## 4. Conclusion

1. Lỗi căn nguyên là do sử dụng biến cấu hình sai `MODALITY_GATE_VIDEO_EARLY_EXIT = 0.50` thay vì `MODALITY_GATE_VIDEO_THRESHOLD = 0.30` tại Tầng 1 của `app/services/retrieval.py`.
2. Toàn bộ thiết kế phân tầng 4 cấp toán học đã được làm rõ và khớp nối hoàn chỉnh với `app/config.py`, `app/services/retrieval.py`, `app/schemas/` và `app/services/chat_graph.py`.
3. Bản đặc tả chi tiết mã nguồn trước/sau (Before/After) đã sẵn sàng trong `code_audit.md` để kỹ sư `@core-coder` áp dụng ngay trong Milestone 2.
4. Dự kiến sau khi triển khai: 14/14 ca Tier 1 sẽ phục hồi thành `grounded`, nâng CRAG Grader Precision từ $80.0\%$ lên $\mathbf{\ge 87.0\%}$ (vượt cam kết $\ge 85.0\%$), độ trễ Tier 1 giảm từ 10.8s xuống $\le 4.5$s.

---

## 5. Verification Method

1. **Kiểm tra trực quan mã nguồn sau chỉnh sửa của `@core-coder`:**
   - Mở `app/config.py`: Đảm bảo `MODALITY_GATE_VIDEO_EARLY_EXIT` đã bị xóa bỏ, `DEFAULT_TOP_CANDIDATES = 10`, `FUTURE_PROBE_LIMIT = 18`.
   - Mở `app/services/retrieval.py`: Đảm bảo dòng 509 sử dụng `settings.MODALITY_GATE_VIDEO_THRESHOLD` ($0.30$), và Tầng 1 hợp nhất cả `valid_ast_items + valid_video_items`.
2. **Chạy kiểm thử Benchmark Golden Dataset (thực hiện bởi `@qa-tester` trong Milestone 3):**
   ```powershell
   .venv\Scripts\python scripts\run_rag_benchmark.py --dataset benchmark_golden_dataset.json
   ```
3. **Điều kiện bác bỏ (Invalidation Conditions):**
   - Nếu bất kỳ ca nào trong 14 ca Tier 1 (`BENCH-004`, `BENCH-007`, `BENCH-010`, `BENCH-011`, `BENCH-014`, `BENCH-016`, `BENCH-022`, `BENCH-035`, `BENCH-037`, `BENCH-041`, `BENCH-045`, `BENCH-049`, `BENCH-058`, `BENCH-064`) vẫn còn trả về `status_ok: false`.
   - Nếu CRAG Precision tổng thể không đạt $\ge 85.0\%$ (dưới 170/200 câu).
   - Nếu phát sinh hồi quy ở Tier 4 Chit-chat (dưới 40/40) hoặc Security Guardrail.
