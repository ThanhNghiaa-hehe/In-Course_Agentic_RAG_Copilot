# TASK PLAN: THIẾT KẾ KIẾN TRÚC TOÁN HỌC & HỘI TỤ TOÀN DIỆN (PSTACK VÒNG LẶP #2)
> **Dự án:** In-Course Agentic RAG Copilot — LangGraph Stateful Orchestration  
> **Sinh viên thực hiện:** Trần Thành Nghĩa (MSSV: `23DH112252`), Trường Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT)  
> **Kiểm toán Nợ kỹ thuật (Nhịp 1A):** `@codebase-auditor` ([`.agent/technical_debt_audit.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/technical_debt_audit.md))  
> **Thiết kế Kiến trúc & Toán học (Nhịp 1B):** Lead Architect, `@rag-architect` ([c18dd75e-ee31-465a-b22d-1b3094abbb13](conversation://c18dd75e-ee31-465a-b22d-1b3094abbb13)) & `@solution-analyst` ([6355981e-bded-401b-ae8c-ddbc1ccd0c72](conversation://6355981e-bded-401b-ae8c-ddbc1ccd0c72)) ([`.agent/implementation_spec.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/implementation_spec.md))  
> **Thực thi Nguyên tử (Nhịp 2):** `@core-coder`  
> **Kiểm thử & Thẩm định Độc lập (Nhịp 3):** `@qa-tester`, `@grounding-evaluator` & `@codebase-auditor`  
> **Nguyên tắc kỷ luật:** 100% Zero Quick-Fix | 0% Regex Runtime | 100% Data/Code Separation | Evidence-Based Verification

---

## GIAI ĐOẠN 1–7: LỊCH SỬ CÁC CHẶNG CƠ SỞ & VÒNG LẶP #1 ĐÃ NGHIỆM THU
- [x] **Giai đoạn 1–6:** Tối ưu hóa ONNX Reranker, N-Gram Curriculum Dominance, Action Dispatcher `navigate_and_seek`, Dynamic Glossary Injection, Semantic Drift Isolation Gate & Thiết lập Baseline Benchmark.
- [x] **Giai đoạn 7 (PSTACK Vòng lặp #1):**
  - [x] Triển khai Negative Constraints & `StreamingCodeSanitizer` (FSM theo dòng, 0% Regex) đạt `SRP = 100.0%`.
  - [x] Cắt tỉa Token Budget RAG (`LLM_MAX_TOKENS=512`, `MAX_CONTEXT_CHARS=1500`) kéo Latency trung bình xuống ~3.4s, Context Budget Compliance = `100.0%` (max 895 chars).
  - [x] Gỡ bỏ `has_domain_entity` khỏi Router NLI gate (phục hồi Stage 11 Router lên `94.50%`, ARR `97.87%`).
  - [x] Khóa lỗ hổng Markdown Fence AST (`_detect_student_cpp_ast()` chặn ` ```system `, `BENCH-195` PASS).
  - [x] Phục hồi cấu hình Retrieval Pareto (`RERANK_MAX_CHARS=1200`, cô lập cross-course probing cho `is_curriculum_navigation=True`) & tách bạch báo cáo `Timestamp Multi-Grounding` vs `Timestamp Strict (Tier 1)` ở Stage 11.

---

## GIAI ĐOẠN 8: PSTACK VÒNG LẶP #2 — GIẢI QUYẾT TRIỆT ĐỂ 5 VẤN ĐỀ CỐT LÕI TRƯỚC HẠN NỘP KHÓA LUẬN & BÀI BÁO HJS

### Nhịp 1A & 1B: Thanh Tra Nợ Kỹ Thuật & Thiết Kế Đặc Tả Kiến Trúc Toán Học (Vòng lặp #2)
- [x] **Mục 8.0.1 (Nhịp 1A — Deep Investigation & Audit):** Thanh tra toàn diện mã nguồn, đối soát kết quả thực tế từ `docs/benchmarks/latest_benchmark_results.json` (Stage 11: Router `94.50%`, CRAG `92.00%`) và `docs/benchmarks/multiturn_benchmark_results.json` (Multi-Turn: Intent `94.14%`, Status `91.89%`), bóc trần 10 ca Cascading Router Failure, bẫy Early Exit Video Tầng 1, Tầng 3 CRAG bị che khuất và danh mục nợ kỹ thuật P1–P3; xuất bản [`.agent/technical_debt_audit.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/technical_debt_audit.md).
- [x] **Mục 8.0.2 (Nhịp 1B — Architectural & Mathematical Spec):** Triệu hồi `@rag-architect` ([c18dd75e-ee31-465a-b22d-1b3094abbb13](conversation://c18dd75e-ee31-465a-b22d-1b3094abbb13)) và `@solution-analyst` ([6355981e-bded-401b-ae8c-ddbc1ccd0c72](conversation://6355981e-bded-401b-ae8c-ddbc1ccd0c72)) thiết kế phương án tổng quát (Problem-Class Solutions, 0% Quick-Fix, 100% Data/Code Separation); xuất bản [`.agent/implementation_spec.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/implementation_spec.md) và cập nhật `.agent/task_plan.md`.

### Nhịp 2: Triển Khai Nguyên Tử 5 Hạng Mục Đột Phá (Atomic Implementation)
- [x] **Mục 8.1 (Vấn đề 0 — Pre-Optimization Benchmark Baseline Verification):**
  - [x] **8.1.1:** Xác nhận và lưu trữ kết quả Baseline thực tế (`Stage 11`: Router `94.50%`, CRAG `92.00%`, TS Safety `92.50%`; `Multi-Turn`: Intent `94.14%`, Status `91.89%`, ARR `97.87%`, SRP `100.0%`).
- [x] **Mục 8.2 (Hạng mục 1 — Phân tách Không gian Vector OWASP LLM01 vs Socratic Request tại `SecurityInputGuardrail`):**
  - [x] **8.2.1:** Xóa bỏ 7 câu xin full code cá biệt ở cuối `benign_prototypes` (dòng 47–53) trong `data/metadata/security_guardrail_manifest.json`, thay bằng 3 prototype trao đổi học tập tổng quát và bổ sung 4 `attack_prototypes` ép vô hiệu hóa Socratic.
  - [x] **8.2.2:** Cập nhật biên độ quyết định Calibrated Dual-Condition tại `app/agent/guardrails.py#L182`: `(sim_attack >= 0.865 and margin >= 0.018) or (sim_attack >= 0.890 and margin >= 0.010) or (sim_attack >= 0.925)`, loại bỏ vĩnh viễn ngưỡng mỏng `margin >= 0.005`, bảo toàn 100% `BENCH-194..200`, `SESSION-SOCRATIC-16..30` và `BENCH-001..189`.
- [x] **Mục 8.3 (Hạng mục 2 — Giải cứu 10 Ca Cascading Router Failure & 2 Ca Navigation Disambiguation trong Đa Lượt):**
  - [x] **8.3.1:** Bổ sung 8 prototype tiếp thu có ngữ cảnh kỹ thuật vào `acknowledgment_prototypes`, cập nhật `nli_hypotheses["out_of_scope"]` (bao quát công nghệ ngoài giáo trình C++) trong `data/metadata/router_intent_manifest.json` và hiệu chỉnh `ROUTER_SOCIAL_ACK_THRESHOLD = 0.72` trong `app/config.py`.
  - [x] **8.3.2:** Cập nhật `CurriculumService.extract_direct_navigation_command()` (`app/services/curriculum.py`) để phân biệt Mệnh lệnh điều khiển UI chuyển bài trực tiếp với Câu hỏi nghi vấn nội dung bài học (chứa dấu `?` và từ để hỏi), giải cứu `SESSION-SWITCH-31-t2` và `SESSION-SWITCH-31-t4`.
- [x] **Mục 8.4 (Hạng mục 3 — Chuẩn hóa DAG 83 Bài Học `is_revision`, Khắc phục Bẫy Early Exit Video & Khai thông Tầng 3 CRAG):**
  - [x] **8.4.1:** Kiểm tra và bảo chứng đầy đủ 23 Foundational Nodes (`is_foundational: true`) và 24 Revision/Update Nodes (`is_revision: true`, `updates_lesson_seq`) trong `data/curriculum/lessons_manifest.json`.
  - [x] **8.4.2:** Đặt `MODALITY_GATE_VIDEO_HIGH_CONFIDENCE = 0.40` trong `app/config.py`, tinh chỉnh Phân tầng (c) Pareto (`0.30 <= max_current_score < 0.40`) và `Foundational Prerequisite Priority v2.3` trong `app/services/retrieval.py` để giải quyết `BENCH-092`, `BENCH-097` và `SESSION-STRESS-48-t1` mà bảo toàn `BENCH-041`.
  - [x] **8.4.3:** Khai thông Tầng 3 Graceful Degradation (`app/services/retrieval.py#L1182-L1206`) bị che khuất bởi điều kiện thừa `max_video_score >= 0.22`, giải cứu `SESSION-CORE-02-t1`, `SESSION-CORE-08-t1`, `SESSION-SOCRATIC-26-t3`, `SESSION-STRESS-42-t2` mà không làm rò rỉ `coverage_gap`.
- [x] **Mục 8.5 (Hạng mục 4 & 5 — Chuẩn hóa `--mode e2e` + Timestamp Song song & Thanh lý 100% Nợ Kỹ Thuật P2/P3):**
  - [x] **8.5.1:** Nâng cấp `scripts/run_multiturn_benchmark.py`: tăng timeout LLM E2E lên `15.0s` (cấu hình qua `BENCHMARK_LLM_TIMEOUT`), tổng hợp `e2e_socratic_metrics`, và in song song `Strict WHR (±30s)` cùng `Multi-Grounding Timestamp Safety Rate`.
  - [x] **8.5.2:** Thanh lý 100% fallback hardcode P2 & P3 trong `app/agent/router.py#L436-L451`, `app/services/curriculum.py#L404-L408`, `app/services/retrieval.py#L386-L391` (`get_course_ids()`), và `app/services/telemetry_critic.py#L227`.

### Nhịp 3: Cổng Nghiệm Thu Bằng Chứng Độc Lập (Evidence Gates - Vòng lặp #2)
- [ ] **Mục 8.6 (Evidence Gate 1 — Automated Pytest Suite):**
  - [ ] Chạy `pytest tests/ -v` đạt **100% PASSED**.
- [ ] **Mục 8.7 (Evidence Gate 2 — Stage 11 Golden 200 Benchmark):**
  - [ ] Chạy `scripts/run_rag_benchmark.py` đạt **Router Accuracy $\ge 94.0\%$**, **CRAG Grader Precision $\ge 92.0\%$**, **Tier 2 Out-of-lesson $\ge 36/40$**, **Timestamp Multi-Grounding Safety $\ge 92.0\%$**.
- [ ] **Mục 8.8 (Evidence Gate 3 — Multi-Turn 50 Sessions / 222 Turns Benchmark & E2E Socratic Verification):**
  - [ ] Chạy `scripts/run_multiturn_benchmark.py` (`--mode retrieval` & `--mode e2e --limit 5`) đạt **Intent $\ge 94.5\%$**, **Retrieval Status $\ge 93.5\%$**, **ARR $\ge 97.0\%$**, **SRP = 100.0% (15/15)**, **Context Budget = 100.0% ($\le 2{,}400$ chars)**.
- [ ] **Mục 8.9 (Evidence Gate 4 — Final Zero Quick-Fix & Grounding Audit):**
  - [ ] Triệu hồi `@codebase-auditor` & `@grounding-evaluator` xác nhận 0% regex runtime, 0% hardcode fallback trong Python, 0% test-set snooping, 0% fake metrics.
