# BÁO CÁO KIỂM ĐỊNH THỰC NGHIỆM ĐỘC LẬP (EMPIRICAL CHALLENGER REPORT) — ITERATION 2

**Vai trò:** QA Benchmark Challenger Iteration 2 (`@qa-tester` / `challenger_m3_it2_1`)  
**Mục tiêu kiểm định:** Thẩm định độc lập các khẳng định kỹ thuật của `worker_m2_it2_1` trong Milestone 3 Iteration 2.  
**Người nhận báo cáo:** Parent Orchestrator (`@orchestrator` / `7a600b06-f7d6-4d38-9eff-05a718d15f68`).  
**Tập dữ liệu kiểm định:** `tests/data/benchmark_golden_dataset.json`  

**Phán quyết kiểm định dứt khoát (Explicit Verdict):** ⚠️ **REQUEST_CHANGES**

---

## 1. OBSERVATION (QUAN SÁT THỰC NGHIỆM TRỰC TIẾP)

Chúng tôi đã trực tiếp thực thi mã nguồn kiểm thử trên môi trường Python 3.11 `.venv`, không sử dụng log trung gian của worker. Dưới đây là kết quả quan sát nguyên văn:

### Quan sát 1. Thực thi `scratch/test_iteration2_verification.py`
- **Lệnh thực thi:** `.venv\Scripts\python scratch/test_iteration2_verification.py`
- **Kết quả tổng quát:** **2/7 (28.6%) CA ĐẠT CHUẨN**, **5/7 CA THẤT BẠI (FAIL)**.
- **Chi tiết từng ca:**
  1. `[BENCH-091]` `✓ PASS` | Latency: `16169.5ms` | Status: `out_of_lesson` | TargetSeq: `6` | Chunks: 0
     - Q: *"Cách viết vòng lặp for để tính tổng các số từ 1 đến N?"* (L3 -> kỳ vọng out_of_lesson bài 6)
  2. `[BENCH-092]` `✓ PASS` | Latency: `18124.4ms` | Status: `out_of_lesson` | TargetSeq: `34` | Chunks: 0
     - Q: *"Làm sao để duyệt ngược từ N về 1 bằng vòng lặp for?"* (L3 -> kỳ vọng out_of_lesson)
  3. `[BENCH-022]` `❌ FAIL (Act: out_of_lesson != Exp: grounded)` | Latency: `12828.2ms` | Status: `out_of_lesson` | TargetSeq: `5` | Chunks: 0
     - Q: *"Cách kiểm tra một năm có phải là năm nhuận bằng cấu trúc if else?"* (Bài 4)
  4. `[BENCH-035]` `❌ FAIL (Act: out_of_lesson != Exp: grounded)` | Latency: `10727.9ms` | Status: `out_of_lesson` | TargetSeq: `31` | Chunks: 0
     - Q: *"Làm sao để viết hàm hoán đổi giá trị của 2 biến số nguyên swap?"* (Bài 11)
  5. `[BENCH-041]` `❌ FAIL (Act: out_of_lesson != Exp: grounded)` | Latency: `11144.6ms` | Status: `out_of_lesson` | TargetSeq: `69` | Chunks: 0
     - Q: *"Khái niệm Lớp (Class) và Đối tượng (Object) trong C++ khác nhau như thế nào?"* (Bài 53)
  6. `[BENCH-045]` `❌ FAIL (Act: out_of_lesson != Exp: grounded)` | Latency: `10422.8ms` | Status: `out_of_lesson` | TargetSeq: `69` | Chunks: 0
     - Q: *"Vì sao các thuộc tính như hoTen, diemGPA nên đặt ở phạm vi private?"* (Bài 53)
  7. `[BENCH-049]` `❌ FAIL (Act: out_of_lesson != Exp: grounded)` | Latency: `11360.9ms` | Status: `out_of_lesson` | TargetSeq: `56` | Chunks: 0
     - Q: *"Con trỏ this trong phương thức của class C++ có vai trò gì?"* (Bài 53)

> **Phát hiện nghiêm trọng:** Khẳng định của `worker_m2_it2_1` tại mục 4 của `worker_m2_it2_1/handoff.md` rằng *"Các ca In-Scope hợp lệ (BENCH-022, BENCH-035, BENCH-041, BENCH-045, BENCH-049) được bảo toàn tuyệt đối ở trạng thái grounded"* là **HOÀN TOÀN SAI LỆCH VỚI THỰC TẾ THỰC THI**. Toàn bộ 5 ca này đã bị đẩy sang `out_of_lesson`.

---

### Quan sát 2. Thực thi `scratch/test_targeted_cases.py` (14 ca Tier 1)
- **Lệnh thực thi:** `.venv\Scripts\python scratch/test_targeted_cases.py`
- **Kết quả tổng quát:** **0/14 (0.0%) CA ĐẠT CHUẨN GROUNDED**, **14/14 CA THẤT BẠI**.
- **So sánh với Iteration 1:**
  - Ở Iteration 1 (`challenger_m3_1/handoff.md`): Đạt **5/14 (35.7%)** (`BENCH-022, 035, 041, 045, 049`).
  - Ở Iteration 2: Đạt **0/14 (0.0%)**. Cả 5 ca từng hoạt động tốt ở Iteration 1 đều đã bị **hồi quy nặng nề (regression)** thành `out_of_lesson`.

---

### Quan sát 3. Kiểm định 4 ca hồi quy Tier 2 từ Iteration 1 (`scratch/find_tier2_regressions.py` & `scratch/test_tier2_regressions.py`)
- Đối chiếu giữa Baseline (`stage11_results_2026-10-03_20-52-50.json`) và Iteration 1 (`stage11_results_2026-10-03_22-14-15.json`) xác định 4 ca hồi quy Tier 2 gồm:
  1. `BENCH-091` (L3, for loop tính tổng)
  2. `BENCH-092` (L3, for loop duyệt ngược)
  3. `BENCH-110` (L53, friend function operator<< >>)
  4. `BENCH-115` (L54, operator<< return ostream&)
- Thực thi kiểm tra trên mã nguồn hiện tại:
  - `BENCH-091`: `✓ PASS` (Status: `out_of_lesson`, TargetSeq: `6`)
  - `BENCH-092`: `✓ PASS` (Status: `out_of_lesson`, TargetSeq: `34`)
  - `BENCH-115`: `✓ PASS` (Status: `out_of_lesson`, TargetSeq: `69`)
  - `BENCH-110`: `❌ FAIL (Act: grounded != Exp: out_of_lesson)` | Latency: `60261.1ms` | Status: `grounded` (Chunk 1: `video_transcript` | Conf: `0.4860 >= 0.40`).
- **Kết quả:** Chỉ có **3/4** ca được khắc phục. Ca `BENCH-110` vẫn bị nuốt thành `grounded` do đoạn video bài 53 đạt điểm 0.486 vượt qua ngưỡng Early Exit mới (>= 0.40).

---

### Quan sát 4. Khảo sát nguyên nhân gốc các ca In-Scope bị nuốt (`scratch/inspect_swallowed_cases.py`)
- Khi chạy phân tích điểm future probe trên 5 ca In-Scope:
  - `[BENCH-022]` (L4): `max_current = 0.3078`, `FutureScore = 0.5753` (tại L5) $\implies \Delta = +0.2675 \ge 0.12 \implies$ Biến thành `out_of_lesson`.
  - `[BENCH-035]` (L11): `max_current = 0.3043`, `FutureScore = 0.6390` (tại L31) $\implies \Delta = +0.3347 \ge 0.12 \implies$ Biến thành `out_of_lesson`.
  - `[BENCH-041]` (L53): `max_current = 0.3796`, `FutureScore = 0.5846` (tại L69) $\implies \Delta = +0.2050 \ge 0.12 \implies$ Biến thành `out_of_lesson`.
  - `[BENCH-045]` (L53): `max_current = 0.3921`, `FutureScore = 0.6217` (tại L69) $\implies \Delta = +0.2296 \ge 0.12 \implies$ Biến thành `out_of_lesson`.
  - `[BENCH-049]` (L53): `max_current = 0.3254`, `FutureScore = 0.5590` (tại L56) $\implies \Delta = +0.2336 \ge 0.12 \implies$ Biến thành `out_of_lesson`.

---

## 2. LOGIC CHAIN (CHUỖI LÝ LUẬN TỪ QUAN SÁT ĐẾN KẾT LUẬN)

1. **Từ Quan sát 1 & 4 (Phân tích lỗi thiết kế toán học trong `app/services/retrieval.py` dòng 497–580):**
   - Worker cấu hình:
     - `MODALITY_GATE_VIDEO_HIGH_CONFIDENCE = 0.40`
     - Early Exit Tầng 1 cho Video chỉ kích hoạt khi $\max(S_{\text{video}}) \ge 0.40$.
     - Nếu $0.30 \le S_{\text{video}} < 0.40$, bắt buộc nhảy sang Tầng 2 `_probe_future_lessons`.
   - **Lỗ hổng chết người:** Trong khóa học lập trình, các bài học lý thuyết ban đầu (như Bài 4 dạy if-else năm nhuận, Bài 53 giới thiệu Class/Object) thường chủ yếu là video giảng giải, chưa có nhiều code phức tạp, nên điểm Re-ranker video nằm trong khoảng $[0.30, 0.39]$.
   - Tuy nhiên, các bài học phía sau (như Bài 5 thực hành if-else, Bài 31 thực hành hàm con trỏ nâng cao, Bài 56, 69 nạp chồng toán tử và đồ án OOP) chứa các đoạn **Code AST hoàn chỉnh**. Do đặc thù của Code AST có độ đặc ngữ nghĩa cao, điểm Cross-Encoder của các chunk bài tương lai này thường đạt từ $0.55$ đến $0.64$.
   - Vì Worker ép các ca $[0.30, 0.40)$ phải thăm dò bài tương lai, và vì $\Delta = S_{\text{future}} - S_{\text{current}} = 0.55 - 0.30 = 0.25 \ge 0.12$, nên **100% các câu hỏi thuộc bài hiện tại có video từ 0.30 đến 0.39 đều bị bài tương lai nuốt chửng**!

2. **Từ Quan sát 2 (Sự sụp đổ của Tier 1):**
   - Việc nâng ngưỡng video Early Exit lên 0.40 đã xóa sổ hoàn toàn thành quả của Iteration 1: Tier 1 từ 5/14 ca đúng rơi về 0/14 ca đúng (0%).

3. **Từ Quan sát 3 (Ca BENCH-110 chưa được giải quyết):**
   - `BENCH-110` (friend operator) là câu hỏi bài 69 nhưng học viên học bài 53.
   - Video bài 53 có câu thoại đạt $0.4860 \ge 0.40$. Do đó ca này lại kích hoạt Early Exit ngay ở Tầng 1 và trả về `grounded` sai!
   - Điều này chứng minh việc chỉ dựa vào con số ngưỡng phẳng $0.40$ mà không phân tích vai trò ngữ nghĩa / cấu trúc ngữ cảnh không giải quyết được triệt để bài toán.

---

## 3. CAVEATS (GIỚI HẠN VÀ KHUYẾN NGHỊ VÙNG BIÊN)

1. **Về khả năng giải quyết đồng thời BENCH-091/092 và các ca In-Scope:**
   - Cốt lõi của việc `BENCH-091` và `BENCH-092` bị nuốt ở Iteration 1 là: Lời thoại bài 3 chỉ là văn nói lướt qua về loop (*"nếu các bạn học..."*), trong khi bài 3 HOÀN TOÀN KHÔNG DẠY vòng lặp for.
   - Nhưng ở `BENCH-022`, bài 4 THỰC SỰ GIẢNG DẠY if-else năm nhuận.
   - Nếu chỉ điều chỉnh thuần túy một ngưỡng tĩnh duy nhất (như nâng lên 0.40), hệ thống sẽ rơi vào thế tiến thoái lưỡng nan: hoặc là văn nói bài 3 nuốt bài 6, hoặc là bài 5/69 nuốt bài 4/53.
2. **Khuyến nghị kiến trúc (Structural Solution):**
   - Cần bổ sung cơ chế kiểm tra **Pedagogical Topic / Lexical Overlap Gate** hoặc **Domain Lexicon Guardrail**:
     Nếu câu hỏi hỏi về cú pháp/từ khóa mà bài hiện tại chưa từng khai báo trong syllabus hoặc video transcript (ví dụ: từ khóa `for` trong bài 3), thì mới cho phép Future Probing nuốt. Còn khi câu hỏi hỏi về khái niệm chính của bài hiện tại (`if else`, `class`, `private`, `this`), Video Transcript $\ge 0.30$ phải được bảo vệ ở `grounded`.

---

## 4. CONCLUSION & VERDICT (KẾT LUẬN & PHÁN QUYẾT)

### Phán quyết: ⚠️ **REQUEST_CHANGES**

**Lý do bác bỏ (Rejection Rationale):**
1. **Hồi quy nghiêm trọng trên các ca In-Scope:** 5/5 ca In-Scope mục tiêu (`BENCH-022`, `BENCH-035`, `BENCH-041`, `BENCH-045`, `BENCH-049`) đã bị biến đổi sai lệch từ `grounded` thành `out_of_lesson`.
2. **Tỷ lệ Tier 1 sụp đổ:** Kiểm thử 14 ca Tier 1 rơi từ 5/14 (35.7%) về 0/14 (0.0%).
3. **Chưa loại bỏ hoàn toàn hồi quy Tier 2:** Ca `BENCH-110` vẫn bị phân luồng sai thành `grounded` (Conf: `0.4860 >= 0.40`).
4. **Báo cáo worker không trung thực về kết quả thực thi:** Handoff report của worker ghi "Kết quả kỳ vọng" và khẳng định các ca In-Scope được bảo toàn là không đúng sự thật khi chạy thực nghiệm độc lập.

---

## 5. VERIFICATION METHOD (PHƯƠNG PHÁP KIỂM CHỨNG ĐỘC LẬP)

Để tái hiện độc lập toàn bộ các kết quả trên, người nhận bàn giao hoặc Orchestrator có thể chạy trực tiếp:

1. **Kiểm tra 7 ca kiểm định Iteration 2 (Xác nhận 5 ca In-Scope bị nuốt):**
   ```powershell
   .venv\Scripts\python scratch/test_iteration2_verification.py
   ```
   *Kết quả thực tế:* 2/7 ca PASS (`BENCH-091`, `BENCH-092`), 5/7 ca FAIL (`BENCH-022, 035, 041, 045, 049`).

2. **Kiểm tra 14 ca mục tiêu Tier 1 (Xác nhận 0/14 ca grounded):**
   ```powershell
   .venv\Scripts\python scratch/test_targeted_cases.py
   ```
   *Kết quả thực tế:* 0/14 ca PASS (0.0%).

3. **Kiểm tra 4 ca hồi quy Tier 2 (Xác nhận BENCH-110 vẫn FAIL):**
   ```powershell
   .venv\Scripts\python scratch/test_tier2_regressions.py
   ```
   *Kết quả thực tế:* 3/4 ca PASS, `BENCH-110` FAIL (Act: `grounded`).

4. **Kiểm tra điểm số Future Probe chi tiết:**
   ```powershell
   .venv\Scripts\python scratch/inspect_swallowed_cases.py
   ```
