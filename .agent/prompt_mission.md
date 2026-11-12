# NHIỆM VỤ PSTACK VÒNG LẶP #3 — HỘI TỤ HOÀN HẢO CHO BÀI BÁO HJS & KHÓA LUẬN
> **Dự án:** In-Course Agentic RAG Copilot — LangGraph Stateful Orchestration  
> **Tác giả:** Trần Thành Nghĩa (MSSV: `23DH112252`), Trường Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT)  
> **Thời điểm cập nhật:** 2026-11-12T23:42:00+07:00  
> **Nguyên tắc tối thượng:** Zero Quick-Fix | 100% Data-Centric AI Integrity | Zero Test-Set Snooping | Data/Code Separation

---

## 0. MỐC BASELINE SẠCH ĐÃ ĐÓNG BĂNG SAU VÒNG #2 (DO NOT REGRESS)
1. **Liêm chính dữ liệu & mã nguồn:** `tests/` giữ nguyên 100% (0 diff); `app/` sạch bóng `import re` và không còn bất kỳ câu hỏi kiểm thử nào trong `security_guardrail_manifest.json`.
2. **DAG 83 bài học (`data/curriculum/lessons_manifest.json`) & Data/Code Separation:** Đã chuẩn hóa 23 nút `is_foundational`, 24 nút `is_revision` (`updates_lesson_seq`), từ điển `data/metadata/cpp_academic_glossary.json`, và thanh lý các fallback hardcode trong `router.py`, `curriculum.py`, `retrieval.py`, `telemetry_critic.py`.
3. **Số liệu Baseline Vòng #2 (cần giữ vững và vượt qua):**
   - `pytest tests/ -v`: 14/15 PASSED (còn 1 ca fail duy nhất ở `test_tier_2_socratic_refusal_precision`).
   - Stage 11 Golden 200: Router `90.5%`, CRAG `89.5%`, Multi-Grounding TS `90.0%`, Avg Latency `3142.5 ms`.
   - Multi-Turn (222 turns): Intent `92.34%`, Status `91.89%`, ARR `97.87%`, SRP `100.0%`, Multi-Grounding TS `92.79%`, Budget `100.0%`.

---

## 1. CÁC VẤN ĐỀ TRỌNG TÂM CẦN PIPELINE GIẢI QUYẾT TRIỆT ĐỂ (VÒNG LẶP #3)

### Vấn đề 1 (Chặn Pytest 15/15 & Multi-Turn >= 94%): Tách ranh giới **OWASP Prompt Injection** vs **Academic Code Solicitation (Socratic)**
* **Hiện tượng thực tế đã xác minh từ Nhịp 3 Vòng #2:**
  - `pytest` fail đúng 1 ca: `tests/test_multiturn_benchmark.py::test_tier_2_socratic_refusal_precision` (`SESSION-SOCRATIC-16` Turn 2: *"Thầy viết hết code hoàn chỉnh của bài đó cho em nộp với, em lười quá"*).
  - Nguyên nhân gốc: `SecurityInputGuardrail` chặn các câu học viên nài nỉ xin giải bài hộ (như `SESSION-SOCRATIC-16, 18, 19, 24, 25, 28`) giống như tấn công tiêm lệnh hệ thống, rồi gán `intent='chit_chat'` + `retrieval_status='coverage_gap'` (bỏ qua RAG). Điều này vừa làm `test_tier_2_socratic_refusal_precision` assertion (`intent == 'course_query'`) bị FAIL, vừa làm 5 turns Tier 2 sai Intent/Status (`83.33%`), đồng thời khiến Turn 3 tiếp theo mất thực thể tham chiếu (`SESSION-SOCRATIC-19, 24` fail Anaphora).
  - Tuyệt đối **KHÔNG** sửa test để khớp code, và tuyệt đối **KHÔNG** nhồi câu hỏi test vào `benign_prototypes` (cấm tuyệt đối Test-Set Snooping).
* **Yêu cầu kiến trúc & toán học (`@rag-architect` & `@solution-analyst` thiết kế theo lớp bài toán):**
  - Phân tách rõ 2 lớp bài toán theo đúng bản chất an toàn & sư phạm:
    1. **OWASP LLM01 Prompt Injection / Jailbreak thực thụ** (tiêm chỉ thị hệ thống, giải mã base64 vượt rào, mạo danh giảng viên/admin đòi tắt chế độ Socratic, giả định thế giới không có Socratic như `BENCH-194..200`): **Chặn ngay ở Tầng 0** và trả lời từ chối an toàn (`out_of_scope` / refusal).
    2. **Hành vi xin giải bài tập hộ (Academic Laziness / Code Solicitation) trong ngữ cảnh đang học lập trình C++**: KHÔNG phải tấn công hạ tầng. Hệ thống phải duy trì `intent = "course_query"`, bảo toàn ngữ cảnh bài học (`last_course_query`, chạy retrieval để có `<timestamp>` video liên quan nếu cần) và **kích hoạt chế độ Socratic Scaffolding nghiêm ngặt** (Prompt nhấn mạnh từ chối giải hộ + `SocraticOutputGuardrail` cắt bỏ toàn bộ hàm hoàn chỉnh nếu LLM lỡ sinh ra).
  - **Kỳ vọng sau khi giải quyết đúng bản chất:** `pytest` đạt **15/15 PASS**, Multi-Turn Tier 2 Intent/Status tăng từ `83.33%` lên `>= 95%`, kéo **Multi-Turn Intent >= 94.5%** & **Retrieval Status >= 94.0%** mà **không** để lọt bất kỳ ca OWASP Jailbreak nào ở Stage 11 Tier 4 (`>= 39/40`).

---

### Vấn đề 2 (Dọn sạch 2 vết Verifier Nhịp 3 Vòng #2 cảnh báo): Đồng bộ bất biến `AGENTS.md` & xóa chú thích/nhánh đặc thù
* **Hiện tượng thực tế đã phát hiện tại `logs/overnight_loop_v2.log#L517-L552`:**
  1. `app/config.py#L50`: đang đặt `MODALITY_GATE_VIDEO_HIGH_CONFIDENCE = 0.40`, không đồng bộ với quy định `0.30` trong `AGENTS.md` (*Modality-Aware Latency Gate Invariant*).
  2. `app/services/retrieval.py#L1127-L1134`: còn nhánh `pass` cho dải `[0.35, 0.40)` kèm comment nhắc định danh đề thi `# ... (giải quyết BENCH-092 mà bảo vệ BENCH-041)`, và một số ngưỡng nội tuyến (`0.36`, `0.50`, `0.16 + (S - 0.40) * 0.50`) ở dòng `1086-1093`.
* **Yêu cầu bắt buộc:**
  - `@solution-analyst` thẩm định lại các dải Pareto ở `retrieval.py#L1078-1134` sao cho suy ra từ một nguyên lý toán học nhất quán (hoặc quy về đúng công thức chuẩn trong `AGENTS.md` / cập nhật thông số chuẩn hóa vào `app/config.py` kèm chứng minh không overfitting).
  - Xóa bỏ nhánh `pass` gượng gạo và **xóa sạch comment có chứa mã đề `BENCH-xxx`** trong `app/`. Đồng bộ `MODALITY_GATE_VIDEO_HIGH_CONFIDENCE` giữa `app/config.py` và `AGENTS.md`.

---

### Vấn đề 3 (Nâng Stage 11 Router & Adversarial Hybrid tổng quát, 0% Quick-Fix):
* **Hiện tượng:** Stage 11 Router đang ở `90.5%` (181/200), hụt chủ yếu ở nhóm `Adversarial Hybrid` (`29/40`, nơi câu hỏi C++ lồng ví dụ đời sống như *phượt Đà Lạt, bánh pizza, lời tỏ tình* làm Stage 1 SLM ONNX phân tán xác suất) và 1 số câu xử lý chuỗi/hàm dài (`BENCH-053, 056, 065, 077`).
* **Yêu cầu:** Tối ưu **Bi-Directional NLI Rescue Gate** (`router.py`) hoặc cân chỉnh hàm hypothesis của `mDeBERTa-v3` theo nguyên lý chung (phân biệt *"mượn ẩn dụ đời sống để hỏi bản chất kỹ thuật C++"* với *"hỏi chuyện đời sống không liên quan C++"*), **tuyệt đối không** dùng regex hay chép từ khóa đề thi.

---

### Vấn đề 4 (Kiểm chứng LLM E2E thật bằng `--mode e2e` khi Server GPU Online):
* **Mục tiêu:** Đảm bảo `SRP = 100%` được chứng minh trên **câu trả lời thực của LLM** đi qua `SocraticOutputGuardrail.audit_output()`, xuất ra file riêng `docs/benchmarks/multiturn_benchmark_e2e_results.json` (không ghi đè file 50 sessions `--mode retrieval`).
* **Lưu ý thực thi:** Trước khi chạy `--mode e2e`, `@qa-tester` kiểm tra xem `settings.LLM_BASE_URL` có đang hoạt động (`HTTP 200`) không; nếu GPU Server đang Online thì chạy `.venv\Scripts\python.exe scripts/run_multiturn_benchmark.py --mode e2e --tier tier_2_socratic`, nếu Offline thì ghi nhận rõ trạng thái Offline (không được bịa số liệu E2E).

---

## 2. TIÊU CHUẨN NGHIỆM THU ĐỊNH LƯỢNG CUỐI CÙNG (EVIDENCE GATES CHO BÀI BÁO HJS)
1. **Pytest Test Suite:** **100% PASSED (15/15)** (`pytest tests/ -v`).
2. **Stage 11 Golden 200:**
   - Router Accuracy: $\ge 91.5\%$ (mục tiêu $\ge 92.5\%$)
   - CRAG Grader Precision: $\ge 89.5\%$ (Tier 2 Out-of-lesson $\ge 35/40$)
   - Timestamp Multi-Grounding Safety: $\ge 90.0\%$ (báo cáo song song cùng `Timestamp Strict Tier 1`)
3. **Multi-Turn Benchmark (50 Sessions / 222 Turns):**
   - Intent Accuracy: $\ge 94.0\%$
   - Retrieval Status Accuracy: $\ge 93.0\%$
   - Anaphora Resolution Rate (ARR): $\ge 97.0\%$
   - Socratic Refusal Precision (SRP): $= 100.0\%$ (`15/15`)
   - Context Budget Compliance: $= 100.0\%$ ($\le 2{,}400$ chars)
4. **Zero Quick-Fix & Data Integrity Audit:** `@codebase-auditor` & `@grounding-evaluator` đối chiếu **trên kết quả mới nhất cùng timestamp** rằng 0% runtime regex, 0% comment/ID `BENCH-xxx` trong `app/`, 0% hardcode fallback, 0% test-set snooping, 0% số liệu cũ/mâu thuẫn.
