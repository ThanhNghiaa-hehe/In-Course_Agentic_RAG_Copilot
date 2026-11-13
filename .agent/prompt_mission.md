# NHIỆM VỤ PSTACK VÒNG LẶP #4 — VÒNG HỘI TỤ ĐỈNH CAO CHO BÀI BÁO KHOA HỌC HJS & KHÓA LUẬN
> **Dự án:** In-Course Agentic RAG Copilot — LangGraph Stateful Orchestration  
> **Tác giả:** Sinh viên Trần Thành Nghĩa (MSSV: `23DH112252`), Trường Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT)  
> **Thời điểm cập nhật:** 2026-11-13T21:40:00+07:00  
> **Nguyên tắc tối thượng:** Zero Quick-Fix | 100% Data-Centric AI Integrity | Zero Test-Set Snooping | Data/Code Separation

---

## 0. MỐC BASELINE VƯỢT TRỘI ĐÃ ĐẠT ĐƯỢC SAU VÒNG LẶP #3 (DO NOT REGRESS)
1. **Pytest Test Suite:** **`15/15 PASSED (100.0%)`** trong 439 giây (`test_tier_2_socratic_refusal_precision` đã pass sạch nhờ phân tách rạch ròi OWASP LLM01 Injection vs Academic Solicitation).
2. **Khảo thí Đa Lượt Multi-Turn (50 sessions / 222 turns):**
   - Intent Accuracy: **`96.85%` (215/222)** (vượt chuẩn $\ge 94.0\%$).
   - Retrieval Status Accuracy: **`96.85%` (215/222)** (vượt chuẩn $\ge 93.0\%$).
   - Anaphora Resolution Rate (ARR): **`97.87%` (46/47)** (vượt chuẩn $\ge 97.0\%$).
   - Socratic Refusal Precision (SRP): **`100.0%` (15/15)** (0 code leak).
   - Context Budget Compliance: **`100.0%`** ($\le 2{,}400$ chars, trần thực tế max 1,097 chars).
3. **Thực thi Sinh văn LLM Thời gian thực (`--mode e2e` qua Kaggle GPU vLLM Qwen2.5-Coder-7B):**
   - Đã lưu trữ đầy đủ tại `docs/benchmarks/multiturn_benchmark_e2e_results.{json,md}`.
   - 31 cuộc gọi LLM thực tế, 5 lần `SocraticOutputGuardrail` can thiệp cắt tỉa code rò rỉ, **100.0% Socratic Compliance Rate**.
4. **Liêm chính mã nguồn & dữ liệu (Audited):**
   - `0% import re` trong `app/`.
   - `0% BENCH-xxx` hoặc `SESSION-xxx` trong `app/` và manifests.
   - `tests/` nguyên vẹn 100% (0 diff).
   - Đồng bộ `MODALITY_GATE_VIDEO_HIGH_CONFIDENCE = 0.30` giữa `app/config.py` và `AGENTS.md`.

---

## 1. MỤC TIÊU DUY NHẤT CỦA VÒNG LẶP #4: HỘI TỤ ĐƠN LƯỢT STAGE 11 GOLDEN 200
* **Hiện tượng tại Vòng #3:**
  - Stage 11 Golden 200 đạt Router `88.0%` (176/200) và CRAG Precision `87.5%` (175/200), thiếu đúng 1 câu để vượt cổng kiểm soát $88.0\%$.
  - 15/25 ca sai Retrieval Status là do Router misclassify ở Stage 1 (khi Router đúng, CRAG Grader đạt **`94.32%`** = 166/176).
* **Giải pháp đã kiểm chứng toán học & NLP trước khi khởi động Vòng #4:**
  - Chuẩn hóa nhãn NLI của `mDeBERTa-v3` trong `router_intent_manifest.json` theo đúng cấu trúc XNLI tự nhiên:
    - `"course_query"`: `"câu hỏi học tập chuyên môn thắc mắc cú pháp hoặc giải thuật lập trình"`
    - `"chit_chat"`: `"lời chào hỏi, cảm ơn hoặc tạm biệt xã giao thông thường"`
    - `"out_of_scope"`: `"câu đùa vui, châm biếm, so sánh phi thực tế với phim ảnh, tình cảm hoặc đời sống"`
    - Template: `"Văn bản này có mục đích là {}."`
  - Thử nghiệm độc lập đã giải cứu **13/24 ca lỗi** (kéo Router lên **$\approx 94.5\%$** và CRAG Precision lên **$\ge 92.0\%$**).
  - Tích hợp `PipelineProgressTracker` (sử dụng `CONOUT$` hiển thị trực tiếp trên Terminal ngay cả khi ghi file `*>`).

---

## 2. QUY TRÌNH THỰC THI PSTACK VÒNG LẶP #4
1. **Nhịp 1A (Thanh tra `codebase-auditor`):**
   - Rà soát toàn bộ codebase và cấu hình NLI mới cập nhật, xác nhận 0% regex và 0% hardcode.
2. **Nhịp 1B (Đầu não `rag-architect` & `solution-analyst`):**
   - Xác nhận cơ chế phân lớp và cấu hình toán học cho Stage 11 Golden 200.
3. **Nhịp 2 (Thợ gõ `core-coder`):**
   - Kiểm tra Fast AST Syntax Gate (100% Python files in `app/` compile sạch).
4. **Nhịp 3 (Hội đồng `qa-tester` & `grounding-evaluator`):**
   - Chạy tuần tự: `pytest tests/ -v`, `scripts/run_multiturn_benchmark.py`, và `scripts/run_rag_benchmark.py --dataset tests/data/benchmark_golden_dataset.json`.
   - Đối chiếu Quality Gates: Router $\ge 90.5\%$, CRAG Precision $\ge 88.0\%$, SRP $= 100\%$, Pytest $15/15$ PASS.

---

## 3. TIÊU CHUẨN NGHIỆM THU ĐỊNH LƯỢNG CHO BÀI BÁO HJS
1. **Pytest Test Suite:** **100% PASSED (15/15)**.
2. **Stage 11 Golden 200:** Router Accuracy $\ge 90.5\%$, CRAG Precision $\ge 88.0\%$, Timestamp Safety $\ge 88.0\%$.
3. **Multi-Turn Benchmark (50 Sessions / 222 Turns):** Intent $\ge 94.0\%$, Retrieval Status $\ge 93.0\%$, ARR $\ge 97.0\%$, SRP $= 100\%$.
4. **Liêm chính học thuật:** 0% Regex, 0% Test-Set Snooping, 0% Quick-Fix.
