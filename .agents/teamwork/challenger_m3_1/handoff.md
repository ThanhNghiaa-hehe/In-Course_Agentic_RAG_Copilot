# BÁO CÁO KHẢO THÍ & ĐỐI CHỨNG ĐỊNH LƯỢNG (QA BENCHMARK VERIFICATION REPORT) — MILESTONE 3 (R3)

**Vai trò:** QA Benchmark Engineer / Empirical Challenger (`@qa-tester` / `challenger_m3_1`)  
**Mã tiến trình:** Milestone 3 (R3) — Khảo thí Định lượng Toàn diện & Đối chứng Chống Hồi quy  
**Người nhận báo cáo:** Parent Orchestrator (`@orchestrator` / `7a600b06-f7d6-4d38-9eff-05a718d15f68`), Core Retrieval Engineer (`@core-coder` / `worker_m2_1`), Academic Scribe (`@academic-scribe`)  
**Tập dữ liệu chuẩn:** `tests/data/benchmark_golden_dataset.json` (200 test cases qua 4 tầng)  
**Tệp kết quả phát sinh:**
- `docs/benchmarks/stage11_report_2026-10-03_22-14-15.md`
- `docs/benchmarks/stage11_results_2026-10-03_22-14-15.json`
- `docs/benchmarks/latest_benchmark_results.json`

**Phán quyết kiểm định (Explicit Verdict):** ⚠️ **REQUEST_CHANGES**

---

## 1. OBSERVATION (QUAN SÁT THỰC NGHIỆM TRỰC TIẾP)

Chúng tôi đã tự mình thực thi 3 kịch bản kiểm thử độc lập trên môi trường Python 3.11 `.venv` của dự án mà không tin cậy bất kỳ log trung gian nào. Các kết quả quan sát được ghi nhận nguyên văn:

### Quan sát 1. Kiểm thử 14 ca mục tiêu Tier 1 (`scratch/test_targeted_cases.py`)
- **Lệnh thực thi:** `.venv\Scripts\python scratch/test_targeted_cases.py`
- **Kết quả tổng quát:** **5/14 (35.7%) CA ĐẠT CHUẨN GROUNDED**, **9/14 (64.3%) CA THẤT BẠI**.
- **Chi tiết 5 ca phục hồi thành công (PASS):**
  1. `BENCH-022` (L4, If-else năm nhuận): `✓ PASS` | Latency: `3627.0ms` | Status: `grounded` | Chunk: `video_transcript` (Conf: `0.3078`, TS: `<timestamp sec="751">12:31</timestamp>`)
  2. `BENCH-035` (L11, Hàm hoán đổi swap): `✓ PASS` | Latency: `2995.7ms` | Status: `grounded` | Chunk: `video_transcript` (Conf: `0.3043`, TS: `<timestamp sec="2638">43:58</timestamp>`)
  3. `BENCH-041` (L53, Class và Object): `✓ PASS` | Latency: `4007.5ms` | Status: `grounded` | Chunk: `video_transcript` (Conf: `0.3796`, TS: `<timestamp sec="228">03:48</timestamp>`)
  4. `BENCH-045` (L53, Phạm vi private): `✓ PASS` | Latency: `5547.1ms` | Status: `grounded` | Chunks: 3 (Confs: `0.3921, 0.3044, 0.3744`, TS: `<timestamp sec="724">12:04</timestamp>`)
  5. `BENCH-049` (L53, Con trỏ this): `✓ PASS` | Latency: `6433.1ms` | Status: `grounded` | Chunk: `video_transcript` (Conf: `0.3254`, TS: `<timestamp sec="1584">26:24</timestamp>`)
- **Chi tiết 9 ca chưa phục hồi (FAIL):**
  1. `BENCH-004` (L2, float vs double): `❌ FAIL (Act: out_of_lesson != Exp: grounded)` | Latency: `14962.9ms`
  2. `BENCH-007` (L2, unsigned int): `❌ FAIL (Act: coverage_gap != Exp: grounded)` | Latency: `16807.7ms`
  3. `BENCH-010` (L3, ++x vs x++): `❌ FAIL (Act: coverage_gap != Exp: grounded)` | Latency: `16704.1ms`
  4. `BENCH-011` (L3, toán tử logic &&, ||, !): `❌ FAIL (Act: out_of_lesson != Exp: grounded)` | Latency: `14000.5ms`
  5. `BENCH-014` (L3, kiểm tra chẵn lẻ %): `❌ FAIL (Act: out_of_lesson != Exp: grounded)` | Latency: `13647.6ms`
  6. `BENCH-016` (L3, ngắn mạch short-circuit): `❌ FAIL (Act: coverage_gap != Exp: grounded)` | Latency: `13235.4ms`
  7. `BENCH-037` (L11, tham số tham chiếu &x): `❌ FAIL (Act: coverage_gap != Exp: grounded)` | Latency: `9494.7ms`
  8. `BENCH-058` (L54, chuỗi string s[i]): `❌ FAIL (Act: out_of_lesson != Exp: grounded)` | Latency: `17737.1ms`
  9. `BENCH-064` (L56, mẫu số khác 0 PhanSo): `❌ FAIL (Act: coverage_gap != Exp: grounded)` | Latency: `22255.6ms`

---

### Quan sát 2. Đánh giá Router Accuracy & Rào chắn An ninh (`scratch/check_router_v21.py`)
- **Lệnh thực thi:** `.venv\Scripts\python scratch/check_router_v21.py`
- **Thời gian hoàn tất:** 436.6 giây
- **Số câu kiểm thử:** 200/200
- **Số câu phân luồng ĐÚNG:** **196/200** (**98.00%**)
- **Phân rã theo từng tầng (Tier):**
  + `Tier in_scope`: **80/80 (100.0%)** | Độ trễ TB: 4420.4 ms
  + `Tier out_of_lesson`: **40/40 (100.0%)** | Độ trễ TB: 229.0 ms
  + `Tier adversarial_hybrid`: **36/40 (90.0%)** | Độ trễ TB: 1732.2 ms (chỉ sai 4 ca ẩn dụ đời sống `BENCH-132, 139, 152, 158`)
  + `Tier chit_chat`: **40/40 (100.0%)** | Độ trễ TB: **109.1 ms** (Fast-Path)
- **Kiểm định Rào chắn An ninh (Security OWASP LLM01 - 10 kịch bản Jailbreak/Prompt Injection):**
  + Toàn bộ 10 ca `BENCH-191` đến `BENCH-200` (DAN Mode, System Prompt Exfiltration, Teacher Impersonation, Deadline Panic, Markdown Delimiter, Bash Terminal, English Bypass, Base64 Obfuscation, Reverse Psychology, Hypothetical Fiction) đều được phân luồng chuẩn xác 100% vào `out_of_scope` qua Fast-Path trong khoảng **4.3 ms – 234.1 ms**.
  + Không có bất kỳ ca hồi quy nào (0 regression).

---

### Quan sát 3. Khảo thí Toàn diện Toàn bộ 200 câu Golden Dataset (`scripts/run_rag_benchmark.py`)
- **Lệnh thực thi:** `.venv\Scripts\python scripts/run_rag_benchmark.py --dataset tests/data/benchmark_golden_dataset.json`
- **Thời gian bắt đầu:** 2026-10-03 22:14:15 | **Thời gian hoàn tất:** 2026-10-03 22:34:26 (Tổng thời gian: **1211.4 giây**, giảm **305.3s** so với Baseline cũ 1516.7s).
- **Báo cáo đã xuất bản:** `docs/benchmarks/stage11_report_2026-10-03_22-14-15.md` và `docs/benchmarks/stage11_results_2026-10-03_22-14-15.json`.
- **Bảng đối chiếu chỉ số kỹ thuật (So sánh Baseline vs Sau Tối Ưu M2):**

| Chỉ số khảo thí | Kết quả Baseline (20:52:50) | Kết quả Hiện tại (22:14:15) | Độ lệch (Delta) | Tiêu chuẩn Nghiệm thu (AC) | Trạng thái Đánh giá |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Router Accuracy** | 98.0% (196/200) | **98.0%** (196/200) | 0.0% | $\ge 98.0\%$ | ✅ **ĐẠT (PASS)** |
| **CRAG Grader Precision** | 80.0% (160/200) | **81.0%** (162/200) | **+1.0%** (+2 ca) | $\ge 85.0\%$ ($\ge 170/200$) | ❌ **CHƯA ĐẠT (FAIL)** |
| **Timestamp Safety & Accuracy** | 64.5% (129/200) | **64.5%** (129/200) | 0.0% | $\ge 75.0\%$ | ❌ **CHƯA ĐẠT (FAIL)** |
| **Độ trễ trung bình/câu** | 7463.1 ms | **6002.0 ms** | **-1461.1 ms** (-19.6%) | $\le 7500 \text{ ms}$ | ✅ **ĐẠT (Cải thiện rõ nét)** |
| **Tier 1 In-Scope CRAG** | 66/80 (82.5%) | **71/80** (88.75%) | **+5 ca** (+6.25%) | 80/80 (100%) | ⚠️ **Cải thiện 5 ca, còn 9 ca** |
| **Tier 2 Out-of-Lesson CRAG** | 27/40 (67.5%) | **23/40** (57.5%) | **-4 ca** (-10.0%) | $\ge 35/40$ | ❌ **Phát sinh 4 ca nuốt nhầm** |
| **Tier 3 Adversarial CRAG** | 27/40 (67.5%) | **28/40** (70.0%) | **+1 ca** (+2.5%) | $\ge 30/40$ | ⚠️ **Chưa đủ ngưỡng** |
| **Tier 4 Chit-chat / Security** | 40/40 (100%) | **40/40** (100%) | 0.0% | 40/40 (100%) | ✅ **ĐẠT TUYỆT ĐỐI (0 regression)** |

---

## 2. LOGIC CHAIN (CHUỖI LÝ LUẬN TỪ QUAN SÁT ĐẾN KẾT LUẬN)

1. **Hiệu lực xác thực của Modality-Aware Gate (Tầng 1):**
   - Từ Quan sát 1 và Quan sát 3, việc hạ ngưỡng Video Early Exit xuống `0.30` đã giải cứu thành công 5 ca In-Scope thuộc bài 4, 11, 53 (`BENCH-022`, `BENCH-035`, `BENCH-041`, `BENCH-045`, `BENCH-049`).
   - Tầng 1 đã triệt tiêu hoàn toàn Future Probing ở các ca này, giúp độ trễ giảm mạnh từ ~10.8s xuống 3.0s – 4.0s (giảm 63%), đưa tỷ lệ CRAG Tier 1 từ 66/80 lên 71/80.

2. **Căn nguyên 9 ca Tier 1 còn thất bại (Failure Patterns P03 & P09):**
   - Quan sát 1 cho thấy 9 ca (`BENCH-004, 007, 010, 011, 014, 016, 037, 058, 064`) không thể kích hoạt Tầng 1 vì điểm số bài hiện tại đều nằm dưới `0.30` (ví dụ: `BENCH-004` đạt 0.2241, `BENCH-007` đạt 0.1114, `BENCH-010` đạt 0.0744).
   - Kiểm tra nội dung text chunk trong Qdrant cho thấy các bài 2, 3 chứa chuỗi âm học Whisper bị méo dạng chưa qua chuẩn hóa lexicon regex (ví dụ: *"thẳng đáp bồ"* thay vì *"double"*, *"An Phai In"* thay vì *"unsigned int"*).
   - Vì bài hiện tại không có điểm tự tin ($\ge 0.30$), hệ thống buộc phải rơi vào Tầng 2 (bị bài sau chứa code AST nuốt nhầm sang `out_of_lesson` như `BENCH-004, 011, 014, 058`) hoặc rơi vào Tầng 4 (`coverage_gap` do điểm sàn $< 0.20$ như `BENCH-007, 010, 016, 037, 064`).

3. **Phát hiện lỗ hổng phản pháo: Hiện tượng "Văn nói bài cũ nuốt câu hỏi bài mới" tại Tầng 1 (Failure Patterns P14 & P16):**
   - Khi kiểm tra sâu 17 ca thất bại tại Tier 2 (`stage11_results_2026-10-03_22-14-15.json`), chúng tôi phát hiện một nghịch lý:
     Tại `BENCH-091` (Học bài 3 nhưng hỏi về vòng lặp `for` tính tổng - kiến thức Bài 6): Kỳ vọng phải là `out_of_lesson`. Nhưng thực tế hệ thống trả về `grounded` (TS: 2223s) với chunk video transcript bài 3 đạt điểm `0.3810 >= 0.30`!
     Tương tự, `BENCH-092` (vòng lặp `for` duyệt ngược) cũng bị video bài 3 nuốt với điểm `0.3538 >= 0.30`!
   - **Bản chất lỗi:** Lời thoại video bài 3 của giảng viên có nhắc thoáng qua các khái niệm tổng quát (*"nếu các bạn học một phần if-else... các bạn cứ thực hiện..."*). Mô hình Cross-Encoder Re-ranker cho điểm ngữ nghĩa tương quan (Semantic Relevance) cao đạt 0.381.
   - Do Tầng 1 quy định hễ Video Transcript $\ge 0.30$ là Early Exit ngay lập tức sang `grounded`, hệ thống đã **bị đánh lừa bởi Spurious Mention Leakage (P14)**, vi phạm trực tiếp nguyên lý **Relevance vs. Context Sufficiency Invariant (ICLR 2025)**: Đoạn văn đạt điểm tương quan nhưng hoàn toàn KHÔNG đủ thông tin để giảng dạy vòng lặp `for`.
   - Kết quả: Tier 2 giảm từ 27/40 xuống 23/40 đúng (bị 4 ca chuyển thành `grounded` giả mạo).

4. **Đối chiếu với Acceptance Criteria:**
   - [x] Router Accuracy $\ge 98.0\%$: ĐẠT (98.0%)
   - [x] Tier 4 Chit-chat (40/40) & Security (10/10): ĐẠT TUYỆT ĐỐI (100% không hồi quy)
   - [ ] CRAG Grader Precision $\ge 85.0\%$: **KHÔNG ĐẠT** (Chỉ đạt 81.0%, thiếu 9 ca nữa để đạt mốc 170/200)
   - [ ] Timestamp Safety & Accuracy $\ge 75.0\%$: **KHÔNG ĐẠT** (Chỉ đạt 64.5%)
   - [ ] Phục hồi 14 ca Tier 1: **KHÔNG ĐẠT** (Chỉ phục hồi được 5/14 ca)

---

## 3. CAVEATS (GIỚI HẠN VÀ KHUYẾN NGHỊ VÙNG BIÊN)

1. **Về Dữ liệu Âm học:**
   - Lõi phân tầng 4 cấp toán học của `worker_m2_1` hoạt động đúng logic thiết kế kỹ thuật, nhưng bị giới hạn bởi chất lượng dữ liệu text transcript hiện có trên Qdrant Cloud. Không thể nâng CRAG lên $\ge 85\%$ nếu các chunk bài 2 và 3 vẫn lưu các từ méo dạng *"thẳng đáp bồ"*, *"An Phai In"*.
2. **Về Ranh giới Early Exit của Video Transcript:**
   - Ngưỡng phẳng `0.30` cho video transcript tại Tầng 1 là con dao hai lưỡi: nó cứu được 5 ca In-Scope bài cũ, nhưng lại tạo kẽ hở cho văn nói lan man của bài cũ nuốt mất câu hỏi bài mới ở Tier 2 (như `BENCH-091`, `BENCH-092`).
   - Cần bổ sung thêm điều kiện Semantic Context Sufficiency hoặc nâng ngưỡng Early Exit của Video khi không có Code AST kèm theo.

---

## 4. CONCLUSION & VERDICT (KẾT LUẬN & PHÁN QUYẾT)

### Phán quyết: ⚠️ **REQUEST_CHANGES**

**Lý do:**
1. CRAG Grader Precision chỉ đạt **81.0%** (162/200), chưa đạt ngưỡng bắt buộc của Acceptance Criteria ($\ge 85.0\%$, tối thiểu 170/200).
2. Tỷ lệ mốc video Timestamp Safety chỉ đạt **64.5%**, chưa đạt ngưỡng cam kết ($\ge 75.0\%$).
3. 9/14 ca lỗi Tier 1 vẫn chưa được phục hồi do lỗi âm học Whisper và hiện tượng Future Probe nuốt nhầm.
4. Phát sinh 4 ca hồi quy tại Tier 2 (bị văn nói điểm cao nuốt thành `grounded` giả mạo).

### Đề xuất hành động khắc phục cụ thể (Actionable Remedies for Next Iteration):
1. **Khắc phục Dữ liệu Âm học (Whisper Canonicalization):**
   Chạy pipeline `scripts/reclean_transcripts.py` để chuẩn hóa các cụm từ kỹ thuật C++ trong transcript Bài 2 & Bài 3 (`float`, `double`, `unsigned int`, `++x`, `&&`, `||`, `%`) và re-index lên Qdrant Cloud (sử dụng kỹ năng `whisper-canonicalizer-tester`).
2. **Siết chặt điều kiện Tầng 1 Early Exit (Context Sufficiency Guardrail):**
   Tại Tầng 1 của `app/services/retrieval.py`: Chỉ cho phép Early Exit trực tiếp khi:
   - Có Code AST $\ge 0.35$ (có mã nguồn thực thi bảo chứng), HOẶC
   - Video transcript đạt ngưỡng tự tin rất cao $\ge 0.40$, HOẶC video transcript $\ge 0.30$ kết hợp chứa ít nhất 1 từ khóa cốt lõi của câu hỏi (loại bỏ trường hợp văn nói generic đạt 0.38 nuốt câu hỏi `for` loop như `BENCH-091`).
3. **Mở rộng Phase 2 Metadata Binding:**
   Tiếp tục đồng bộ file `data/metadata/lesson_code_video_binding.json` cho các bài 2, 3, 11 để nâng Timestamp Safety từ 64.5% lên $\ge 75.0\%$.

---

## 5. VERIFICATION METHOD (PHƯƠNG PHÁP KIỂM CHỨNG ĐỘC LẬP)

Bất kỳ thành viên nào trong nhóm hoặc Giảng viên hướng dẫn đều có thể độc lập tái hiện và kiểm chứng toàn bộ kết quả trên bằng các lệnh PowerShell:

1. **Tái hiện kiểm thử 14 ca Tier 1:**
   ```powershell
   .venv\Scripts\python scratch/test_targeted_cases.py
   ```
   *Kết quả kỳ thị thực tế:* 5 ca PASS (`BENCH-022, 035, 041, 045, 049`), 9 ca FAIL.

2. **Tái hiện kiểm thử Router & An ninh (200 câu):**
   ```powershell
   .venv\Scripts\python scratch/check_router_v21.py
   ```
   *Kết quả kỳ thị thực tế:* Router Accuracy 98.00% (196/200), Tier Chit-chat 40/40, Security 10/10.

3. **Tái hiện toàn bộ bài thi Stage 11 Benchmark (200 câu):**
   ```powershell
   .venv\Scripts\python scripts/run_rag_benchmark.py --dataset tests/data/benchmark_golden_dataset.json
   ```
   *Kết quả kỳ thị thực tế:* CRAG 81.0% (162/200), Timestamps 64.5% (129/200), Latency 6002.0ms.

4. **Điều kiện vô hiệu hóa (Invalidation Conditions):**
   - Nếu chạy lại `scripts/run_rag_benchmark.py` mà CRAG Grader Precision đạt $\ge 85.0\%$ (170/200) $\to$ Phán quyết REQUEST_CHANGES được tự động nâng cấp thành APPROVE.
   - Nếu phát hiện bất kỳ ca nào trong Tier 4 Chit-chat hoặc Security Guardrail bị phân luồng sai $\to$ Báo động đỏ toàn hệ thống.
