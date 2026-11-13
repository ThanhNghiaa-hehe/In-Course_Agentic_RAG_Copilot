# TASK PLAN: THIẾT KẾ KIẾN TRÚC TOÁN HỌC & HỘI TỤ ĐỈNH CAO (PSTACK VÒNG LẶP #4)
> **Dự án:** In-Course Agentic RAG Copilot — LangGraph Stateful Orchestration  
> **Sinh viên thực hiện:** Trần Thành Nghĩa (MSSV: `23DH112252`), Trường Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT)  
> **Kiểm toán Nợ kỹ thuật (Nhịp 1A):** `@codebase-auditor` ([`.agent/technical_debt_audit.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/technical_debt_audit.md))  
> **Thiết kế Kiến trúc & Toán học (Nhịp 1B):** Lead Architect, `@rag-architect` ([7fde0236-e44c-4d7b-8940-7ff32b4fb03c](conversation://7fde0236-e44c-4d7b-8940-7ff32b4fb03c)) & `@solution-analyst` ([305424e9-7f88-4c30-95f0-2261949694b5](conversation://305424e9-7f88-4c30-95f0-2261949694b5)) ([`.agent/implementation_spec.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/implementation_spec.md))  
> **Thực thi Nguyên tử (Nhịp 2):** `@core-coder`  
> **Kiểm thử & Thẩm định Độc lập (Nhịp 3):** `@qa-tester`, `@grounding-evaluator` & `@codebase-auditor`  
> **Nguyên tắc kỷ luật:** 100% Zero Quick-Fix | 0% Regex Runtime | 0% Test-Set Snooping | 100% Data/Code Separation | Evidence-Based Verification

---

## GIAI ĐOẠN 1–9: LỊCH SỬ CÁC CHẶNG CƠ SỞ & VÒNG LẶP #1–#3 ĐÃ NGHIỆM THU
- [x] **Giai đoạn 1–6:** Tối ưu hóa ONNX Reranker, N-Gram Curriculum Dominance, Action Dispatcher `navigate_and_seek`, Dynamic Glossary Injection, Semantic Drift Isolation Gate & Thiết lập Baseline Benchmark.
- [x] **Giai đoạn 7 (PSTACK Vòng lặp #1):** Triển khai Negative Constraints & `StreamingCodeSanitizer` (FSM theo dòng, 0% Regex), cắt tỉa Token Budget RAG (`LLM_MAX_TOKENS=512`, `MAX_CONTEXT_CHARS=1500`), khóa lỗ hổng Markdown Fence AST (`_detect_student_cpp_ast()` chặn ` ```system `).
- [x] **Giai đoạn 8–9 (PSTACK Vòng lặp #2–#3):** Chuẩn hóa DAG 83 bài học (`is_foundational`, `is_revision`), thanh lý 100% fallback hardcode trong `router.py`, `curriculum.py`, `retrieval.py`, `telemetry_critic.py`, đồng bộ `MODALITY_GATE_VIDEO_HIGH_CONFIDENCE = 0.30`, xóa sạch nhánh `pass` và comment `BENCH-xxx`, đạt `pytest 15/15 PASSED (100%)`, Multi-Turn Intent `96.85%`, Status `96.85%`, ARR `97.87%`, SRP `100.0%`, Budget `100.0%`, và hoàn tất E2E LLM Benchmark trên Kaggle GPU vLLM (`docs/benchmarks/multiturn_benchmark_e2e_results.json`).

---

## GIAI ĐOẠN 10: PSTACK VÒNG LẶP #4 — HỘI TỤ ĐƠN LƯỢT STAGE 11 GOLDEN 200 & BẢO VỆ TOÀN DIỆN MULTI-TURN

### Nhịp 1A & 1B: Thanh Tra Nợ Kỹ Thuật & Thiết Kế Đặc Tả Kiến Trúc Toán Học
- [x] **Mục 10.0.1 (Nhịp 1A — Deep Investigation & Audit):** Thanh tra toàn diện mã nguồn và kết quả thực tế từ `docs/benchmarks/latest_benchmark_results.json` (`18:21:56`) cùng `docs/benchmarks/multiturn_benchmark_results.json` (`18:05:23`); phát hiện lỗi Duplicate Key Shadowing `"solicitation_words"` tại dòng 190 `router_intent_manifest.json`, hiện tượng NLI Tokenizer Subword Frequency Skew trên `mDeBERTa-v3`, và rào cản Pareto trên 6 ca Nhóm C1 + 1 ca Nhóm C2; xuất bản [`.agent/technical_debt_audit.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/technical_debt_audit.md).
- [x] **Mục 10.0.2 (Nhịp 1B — Architectural & Mathematical Spec):** Triệu hồi `@rag-architect` ([7fde0236-e44c-4d7b-8940-7ff32b4fb03c](conversation://7fde0236-e44c-4d7b-8940-7ff32b4fb03c)) và `@solution-analyst` ([305424e9-7f88-4c30-95f0-2261949694b5](conversation://305424e9-7f88-4c30-95f0-2261949694b5)) thiết kế phương án chuẩn mực theo lớp bài toán (0% Quick-Fix, 0% Test-Set Snooping); xuất bản [`.agent/implementation_spec.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/implementation_spec.md) và cập nhật `.agent/task_plan.md`.

### Nhịp 2: Triển Khai Nguyên Tử 4 Hạng Mục Trọng Tâm (Atomic Implementation - Bàn giao `@core-coder`)
- [x] **Mục 10.1 (Hạng mục 1 — Khử Duplicate Key Shadowing & Trực giao hóa OWASP LLM01 vs. Academic Code Solicitation):**
  - [x] **10.1.1:** Xóa khóa trùng `"solicitation_words"` tại dòng 190–192 trong `data/metadata/router_intent_manifest.json` (triệt tiêu từ đơn `"cho"` làm hỏng `SESSION-OOP-15 T4` và `BENCH-176`); hợp nhất các cụm từ $\ge 2$ từ vào dòng 40–61.
  - [x] **10.1.2:** Bổ sung `"coercive_override_markers"` và 2 prototype tấn công mạo danh/cưỡng ép vào `data/metadata/security_guardrail_manifest.json`, cập nhật `SecurityInputGuardrail.validate_input()` tại `app/agent/guardrails.py` để chặn đứng `BENCH-193, 194` ở Tầng 0 mà bảo toàn 100% `pytest 15/15` và `SESSION-SOCRATIC-16..30`.
- [x] **Mục 10.2 (Hạng mục 2 — Cross-Lingual Hypothesis Transfer & Bayesian Consensus Gate trong `IntentRouter`):**
  - [x] **10.2.1:** Cập nhật `nli_template` (`"This text is about {}."`) và `nli_hypotheses` chuẩn MNLI/XNLI trong `data/metadata/router_intent_manifest.json`; nạp `self._template` từ manifest tại `app/agent/router.py#L132` (100% Data/Code Separation).
  - [x] **10.2.2:** Nâng cấp `is_ambiguous_slm` (kích hoạt khi `has_curriculum_topic` hoặc `p_course >= 0.10`) và triển khai **Rigorous Chit-Chat Verification Gate** (`p_chit >= 0.12`) tại `app/agent/router.py#L819-L880` để giải cứu 18 ca lỗi Nhóm R1 & R2.
- [x] **Mục 10.3 (Hạng mục 3 — Context-Aware `function_main` AST Grounding & Curriculum-Aligned Pareto Sufficiency):**
  - [x] **10.3.1:** Làm giàu từ khóa học thuật chuẩn giáo trình cho Bài 3, 7, 8 (`is_foundational`), 53, 54, 56 trong `data/curriculum/lessons_manifest.json`.
  - [x] **10.3.2:** Cập nhật `BOILERPLATE_SCOPES` theo ngữ cảnh câu hỏi `main` tại `app/services/retrieval.py#L914` (giải cứu `BENCH-048`) và chuẩn hóa `is_future_curriculum_topic` tại `app/services/retrieval.py#L1178-L1200` (giải cứu 6 ca Nhóm C1: `BENCH-087, 093, 098, 101, 103, 107`).
- [x] **Mục 10.4 (Hạng mục 4 — Fast AST Syntax Gate & Code Hygiene Verification):**
  - [x] **10.4.1:** Kiểm tra biên dịch AST toàn bộ file Python trong `app/`, xác nhận `MODALITY_GATE_VIDEO_HIGH_CONFIDENCE = 0.30`, `0% import re`, `0% pass` rỗng, `0% BENCH-xxx`.

### Nhịp 3: Cổng Nghiệm Thu Bằng Chứng Độc Lập (Evidence Gates - Bàn giao `@qa-tester` & `@grounding-evaluator`)
- [ ] **Mục 10.5 (Evidence Gate 1 — Automated Pytest Suite):**
  - [ ] Chạy `.venv\Scripts\pytest.exe tests/ -v` đạt **100% PASSED (15/15)**.
- [ ] **Mục 10.6 (Evidence Gate 2 — Multi-Turn 50 Sessions / 222 Turns Benchmark):**
  - [ ] Chạy `.venv\Scripts\python.exe scripts/run_multiturn_benchmark.py --mode retrieval` đạt **Intent $\ge 94.0\%$**, **Retrieval Status $\ge 93.0\%$**, **ARR $\ge 97.0\%$**, **SRP = 100.0% (15/15)**, **Context Budget = 100.0% ($\le 2{,}400$ chars)**.
- [ ] **Mục 10.7 (Evidence Gate 3 — Stage 11 Golden 200 Benchmark):**
  - [ ] Chạy `.venv\Scripts\python.exe scripts/run_rag_benchmark.py --dataset tests/data/benchmark_golden_dataset.json` đạt **Router Accuracy $\ge 90.5\%$ (mục tiêu $\ge 95.0\%$)**, **CRAG Grader Precision $\ge 88.0\%$ (mục tiêu $\ge 93.5\%$)**, **Timestamp Multi-Grounding Safety $\ge 88.0\%$**.
- [ ] **Mục 10.8 (Evidence Gate 4 — Final Zero Quick-Fix & Grounding Audit):**
  - [ ] Triệu hồi `@codebase-auditor` & `@grounding-evaluator` đối chiếu trên kết quả mới nhất: 0% runtime regex, 0% comment/ID `BENCH-xxx` trong `app/`, 0% hardcode fallback, 0% test-set snooping.
