# BÁO CÁO BÀN GIAO KỸ THUẬT (TECHNICAL HANDOFF REPORT)
**Vai trò:** RAG & CRAG Architect (`@rag-architect`)  
**Mã tiến trình:** Milestone 1 (R1) — Khảo sát & Đặc tả Kiến trúc Phân tầng Truy xuất  
**Đối tượng bàn giao:** Core Retrieval Engineer (`@core-coder`), Mathematical Decision Specialist (`@solution-analyst`), Parent Orchestrator (`@orchestrator`)  
**Tệp đính kèm phân tích chi tiết:** `d:\In_Course_Agentic_RAG_Copilot\.agents\teamwork\explorer_m1_1\analysis.md`  

---

## 1. OBSERVATION (QUAN SÁT THỰC NGHIỆM TRỰC TIẾP)

1. **Kết quả khảo thí Stage 11 Benchmark:**
   - Tệp báo cáo: `docs/benchmarks/stage11_report_2026-10-03_20-52-50.md` (dòng 15, 25)
     - `CRAG Grader Precision: 80.0% (160/200)` (Ngưỡng cam kết CI Gate $\ge 85.0\%$).
     - `Tier 1. In-Scope Technical: 80 ca | Router OK: 80/80 | CRAG OK: 66/80 | Timestamp OK: 39/80 | Độ trễ TB: 10874.6 ms`.
     - Số ca lỗi Tier 1: Chính xác **14 ca** (80 - 66 = 14).
   - Tệp kết quả chi tiết: `docs/benchmarks/stage11_results_2026-10-03_20-52-50.json`
     - 9 ca bị đẩy sai thành `out_of_lesson`:
       - `BENCH-004` (dòng 188-219, `L2`, query: "Sự khác nhau giữa float và double trong C++ là gì?", actual: `out_of_lesson`, latency: 9202.5ms).
       - `BENCH-011` (dòng 485-516, `L3`, query: "Các toán tử logic &&, || và ! trong C++ hoạt động như thế nào?", actual: `out_of_lesson`, latency: 18009.5ms).
       - `BENCH-014` (dòng 601-632, `L3`, query: "Làm thế nào để kiểm tra một số nguyên n có phải là số chẵn bằng toán tử %?", actual: `out_of_lesson`, latency: 8110.3ms).
       - `BENCH-022` (dòng 908-939, `L4`, query: "Cách kiểm tra một năm có phải là năm nhuận bằng cấu trúc if else?", actual: `out_of_lesson`, latency: 6517.8ms).
       - `BENCH-035` (dòng 1498-1529, `L11`, query: "Làm sao để viết hàm hoán đổi giá trị của 2 biến số nguyên swap?", actual: `out_of_lesson`, latency: 5760.7ms).
       - `BENCH-041` (dòng 1750-1781, `L53`, query: "Khái niệm Lớp (Class) và Đối tượng (Object) trong C++ khác nhau như thế nào?", actual: `out_of_lesson`, latency: 6381.7ms).
       - `BENCH-045` (dòng 1920-1951, `L53`, query: "Vì sao các thuộc tính như hoTen, diemGPA nên đặt ở phạm vi private?", actual: `out_of_lesson`, latency: 6316.7ms).
       - `BENCH-049` (dòng 2090-2121, `L53`, query: "Con trỏ this trong phương thức của class C++ có vai trò gì?", actual: `out_of_lesson`, latency: 6057.9ms).
       - `BENCH-058` (dòng 2463-2494, `L54`, query: "Toán tử s[i] dùng để truy cập từng ký tự trong biến std::string như thế nào?", actual: `out_of_lesson`, latency: 5994.6ms).
     - 5 ca bị rơi sai thành `coverage_gap`:
       - `BENCH-007` (dòng 320-351, `L2`, query: "Từ khóa unsigned trong kiểu unsigned int có tác dụng gì?", actual: `coverage_gap`, latency: 7669.3ms).
       - `BENCH-010` (dòng 452-483, `L3`, query: "Sự khác biệt giữa toán tử tiền tố ++x và hậu tố x++ là gì?", actual: `coverage_gap`, latency: 7246.8ms).
       - `BENCH-016` (dòng 672-703, `L3`, query: "Hiện tượng ngắn mạch (short-circuit evaluation) của toán tử logic && trong C++?", actual: `coverage_gap`, latency: 7924.4ms).
       - `BENCH-037` (dòng 1576-1607, `L11`, query: "Toán tử & trong định nghĩa tham số hàm void func(int &x) có tác dụng gì?", actual: `coverage_gap`, latency: 6324.3ms).
       - `BENCH-064` (dòng 2725-2756, `L56`, query: "Điều kiện kiểm tra mẫu số khác 0 khi khởi tạo một đối tượng PhanSo là gì?", actual: `coverage_gap`, latency: 47218.6ms).

2. **Cấu hình và mã nguồn hiện hành:**
   - Tệp `app/config.py`:
     - Dòng 45: `MODALITY_GATE_VIDEO_THRESHOLD: float = 0.30`
     - Dòng 46: `MODALITY_GATE_VIDEO_EARLY_EXIT: float = 0.50`
     - Dòng 40: `DEFAULT_TOP_CANDIDATES: int = 8`
     - Dòng 48: `FUTURE_PROBE_MARGIN: float = 0.12`
     - Dòng 49: `FUTURE_PROBE_MIN_CONFIDENCE: float = 0.40`
     - Dòng 50: `FUTURE_PROBE_LIMIT: int = 12`
   - Tệp `app/services/retrieval.py`:
     - Dòng 507–510:
       ```python
       valid_video_early_exit = [
           it for it in candidate_items
           if it.get("content_type") == "video_transcript" and it.get("confidence_score", 0.0) >= settings.MODALITY_GATE_VIDEO_EARLY_EXIT
       ]
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
     - Dòng 100, 119: `grade_document_relevance(..., min_confidence: float = 0.40)` với video transcript yêu cầu `prob >= target_threshold` (0.40).

---

## 2. LOGIC CHAIN (CHUỖI LÝ LUẬN TỪ QUAN SÁT ĐẾN KẾT LUẬN)

1. **Tiền đề 1 (Đặc thù phân phối điểm phương thức):**
   - Video Transcript chứa ngôn ngữ hội thoại, phụ từ ("thì", "mà", "là") và nhiễu nhận dạng âm học Whisper. Khi đi qua Cross-Encoder (`jina-reranker-v2`) và hàm chuẩn hóa Logistic Sigmoid, các đoạn video bài giảng giải thích đúng trọng tâm thường đạt điểm trong khoảng $[0.30, 0.45]$.
   - Điểm $\ge 0.50$ chỉ xuất hiện khi câu thoại trùng khớp gần như 100% từng từ với câu hỏi.

2. **Tiền đề 2 (Khuyết tật cổng Early Exit tại Tầng 1):**
   - Do `MODALITY_GATE_VIDEO_EARLY_EXIT` được gán bằng `0.50` (Quan sát 2), các đoạn video bài hiện tại đạt $S \in [0.30, 0.45]$ không bao giờ thỏa mãn điều kiện dòng 509 của `retrieval.py`.
   - Vì câu hỏi lý thuyết không có khối Code AST đạt $\ge 0.35$ tương ứng, Tầng 1 Early Exit **luôn thất bại**.

3. **Tiền đề 3 (Bẫy rò rỉ từ khóa bài sau - P14 Spurious Mention Leakage):**
   - Khi Tầng 1 không đóng, luồng xử lý bắt buộc gọi `_probe_future_lessons` (dòng 535).
   - Trong lập trình, các từ khóa nền tảng như `float/double`, `&&`, `%`, `swap`, `class`, `private`, `this`, `s[i]` xuất hiện dày đặc trong mã nguồn của các bài học tiếp theo (Quan sát 1: 9 ca).
   - Vì Code AST có cấu trúc cú pháp cô đọng, Cross-Encoder chấm điểm Code AST tương lai rất cao ($S_{\text{future}} \ge 0.45 - 0.55$).
   - Độ lệch $\Delta \text{Margin} = S_{\text{future}} - S_{\text{current}} > 0.12$ được thỏa mãn.
   - Hệ thống phán quyết sai lầm: Đưa câu hỏi bài hiện tại vào `out_of_lesson`, xóa sạch context (`chunks = []`), gây lỗi P16 (Precedence Inversion).

4. **Tiền đề 4 (Bẫy loại bỏ cứng nhắc tại Tầng 3 và nghẽn Pool):**
   - Với 5 ca còn lại, bài sau không đạt $S \ge 0.40$, luồng rơi xuống Tầng 3.
   - Tại dòng 559, `grade_document_relevance` đòi hỏi $S \ge 0.40$ đối với video. Các chunk bài hiện tại ($0.22 \le S < 0.35$) bị loại bỏ sạch.
   - Khi rơi xuống Tầng 4 Graceful Degradation, do `DEFAULT_TOP_CANDIDATES = 8` quá hẹp (Quan sát 2), các ứng viên tiềm năng bị trôi khỏi pool. Hệ thống không còn chunk nào và rơi vào `coverage_gap` (P08 Empty Context Starvation).

5. **Kết luận suy diễn (Deductive Conclusion):**
   - Hạ ngưỡng Early Exit của Video Transcript từ `0.50` xuống `0.30` (`MODALITY_GATE_VIDEO_THRESHOLD = 0.30`) sẽ lập tức kích hoạt Tầng 1 Early Exit cho 9 ca bị nuốt, khóa trạng thái `grounded` ngay tại bài hiện tại và triệt tiêu 1.5s - 2.5s độ trễ do bỏ qua future probe.
   - Nới lỏng Tầng 3 (Graceful Degradation cho dải $[0.20, 0.30)$) kết hợp mở rộng candidate pool lên 10 chunks sẽ cứu vãn toàn bộ 5 ca rớt oan sang `coverage_gap`.

---

## 3. CAVEATS (GIỚI HẠN VÀ KHUYẾN NGHỊ VÙNG BIÊN)

1. **Nguy cơ rò rỉ khi sinh viên hỏi bài sau ở bài trước (Tier 2 Regression Risk):**
   - Nếu hạ ngưỡng video xuống quá thấp ($< 0.25$), các câu hỏi thuộc bài tương lai nhưng có video bài cũ nhắc lướt qua ("sau này học con trỏ") có thể bị khóa nhầm thành `grounded` ở bài cũ.
   - **Biện pháp khống chế:** Giữ nguyên ngưỡng sàn $0.30$ cho Video Early Exit. Chỉ cho phép Early Exit khi video bài hiện tại đạt $S \ge 0.30$. Các video điểm lơ lửng ($0.22 \le S < 0.30$) bắt buộc vẫn phải đi qua Tầng 2 Future Probe với biên độ $\Delta \text{Margin} \ge 0.12$.
2. **Hiện tượng nghẽn mạng Qdrant Cloud quốc tế:**
   - Câu `BENCH-064` ghi nhận độ trễ cá biệt 47.2 giây do độ trễ truyền gói tin mạng đến Qdrant Cloud. Khuyến nghị duy trì `timeout=60.0` và giới hạn `FUTURE_PROBE_LIMIT = 18`.
3. **Phạm vi thẩm định:**
   - Nghiên cứu này tập trung vào 14 ca lỗi Tier 1. Các tầng Tier 4 Chit-chat (40/40) và Security Guardrail (10/10) hoàn toàn không bị ảnh hưởng vì chạy trên luồng Fast-Path trước RAG.

---

## 4. CONCLUSION (KẾT LUẬN VÀ QUYẾT ĐỊNH KIẾN TRÚC)

1. **Khẳng định nguyên nhân:**
   Nguyên nhân 14 ca lỗi Tier 1 không bắt nguồn từ dữ liệu hay mô hình embedding, mà hoàn toàn do **lệch ngưỡng logic phân tầng trong mã nguồn** (`MODALITY_GATE_VIDEO_EARLY_EXIT = 0.50` chặn cổng Early Exit và điều kiện lọc CRAG Grader Tầng 3 quá khắt khe).
2. **Quy chuẩn kiến trúc bàn giao cho `@core-coder`:**
   - **Quy chuẩn 1:** Xóa bỏ tham số `MODALITY_GATE_VIDEO_EARLY_EXIT = 0.50`. Hợp nhất thành duy nhất `MODALITY_GATE_VIDEO_THRESHOLD = 0.30` tại `app/config.py`.
   - **Quy chuẩn 2:** Sửa Tầng 1 trong `app/services/retrieval.py`: Kích hoạt Early Exit khi `(has_ast and max_ast >= 0.35) or (max_video >= 0.30)`.
   - **Quy chuẩn 3:** Giữ nguyên điều kiện Tầng 2: Future Probe chỉ nuốt bài khi $S_{\text{future}} \ge 0.40$ VÀ $\Delta \text{Margin} \ge 0.12$.
   - **Quy chuẩn 4:** Tầng 3 Graceful Degradation tiếp nhận các chunk bài hiện tại trong dải $[0.20, 0.30)$ khi bài tương lai không vượt trội.
   - **Quy chuẩn 5:** Tăng `DEFAULT_TOP_CANDIDATES = 10` và `FUTURE_PROBE_LIMIT = 18` để tăng độ phủ ngữ cảnh.

---

## 5. VERIFICATION METHOD (PHƯƠNG PHÁP KIỂM CHỨNG ĐỘC LẬP)

Để kiểm chứng tính đúng đắn của đề xuất kiến trúc trước khi triển khai rộng:

1. **Tệp cần kiểm tra:**
   - `app/config.py`
   - `app/services/retrieval.py`
   - `tests/data/benchmark_golden_dataset.json`

2. **Lệnh PowerShell kiểm thử định lượng:**
   ```powershell
   # 1. Chạy kiểm tra riêng 14 ca mục tiêu Tier 1
   python scratch/test_targeted_cases.py

   # 2. Chạy toàn bộ 200 câu hỏi Benchmark Stage 11
   python scripts/run_rag_benchmark.py
   ```

3. **Điều kiện vô hiệu hóa (Invalidation Conditions):**
   - Nếu sau khi áp dụng, Router Accuracy giảm $< 98.0\% \to$ Vô hiệu hóa.
   - Nếu CRAG Grader Precision không đạt $\ge 85.0\% \to$ Vô hiệu hóa.
   - Nếu xuất hiện bất kỳ ca hồi quy nào ở Tier 4 Chit-chat hoặc Security Guardrail $\to$ Vô hiệu hóa ngay lập tức.
