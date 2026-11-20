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

---

## GIAI ĐOẠN 11: PSTACK VÒNG LẶP #5 — KHẮC PHỤC LỖI PLAYGROUND (`session_bgsi9hbkmwi6p227`), DỌN `app/config.py` & TỐI ƯU ĐỘ TRỄ E2E (2026-11-16)

> **Model Profile đã cập nhật (tránh `claude-sonnet-5-5-*` / `claude-opus-5-5-*` đang 0% quota):** Auditor=`gemini-4-argon-high`, Thinker=`gemini-4-hydrogen-high`, Coder=`gemini-4-argon-medium`, Verifier=`gemini-4-hydrogen-high`.

### Nhịp 1A & 1B: Kiểm Toán Nguyên Nhân Gốc & Đặc Tả Kiến Trúc
- [ ] **Mục 11.1 (Auditing Vấn đề 1 — Turn 3 `int` vs `double` -> Bài 64):** Điều tra vì sao `lesson_seq=3` bị `future_points` / Pareto cướp quyền sang `lesson_seq=64` (`81:09`, TTFT `27,779 ms`) và xuất phương án tổng quát theo Prerequisite Priority (0% regex/keyword hardcode).
- [ ] **Mục 11.2 (Auditing Vấn đề 2 — Turn 4 nhiễm chéo `lesson-64`/`lesson-63` tại `lesson_seq=1`):** Xác định nguyên nhân 3 chunk Bài 64/63 lọt vào `grounded`, lỗi `start_sec=null` -> `00:00`, rò rỉ text timestamp `"0:56"`, lời xin lỗi mở đầu, và mâu thuẫn mời Bài 2 / gắn tag Bài 64.
- [ ] **Mục 11.3 (Auditing Vấn đề 3 — Config Hygiene `app/config.py`):** Phân loại `27/98` biến chưa có caller giữa "cấu hình chết cần xóa" và "tham số bị hardcode trong code chưa nối qua `settings`".
- [ ] **Mục 11.4 (Profiling Vấn đề 4 — Độ trễ RAG E2E 11.3s–27.8s):** Đo tách từng node (`router`, `retrieval` + CPU rerank, `crag`, LLM prefill) trong khi giữ nguyên `onnxruntime-gpu==1.23.2` (E5 GPU), CPU INT8 Reranker, `LLM_MAX_TOKENS=650` và LLM tự lưu trữ `Qwen2.5-Coder-7B-Instruct`.

### Nhịp 2 & Nhịp 3: Triển Khai & Nghiệm Thu Chống Hồi Quy
- [ ] **Mục 11.5 (Triển khai nguyên tử):** Sửa triệt để các nguyên nhân gốc của Turn 3, Turn 4, timestamp guardrail (`start_sec=null`, plain-text `0:56`, anti-apology), dọn `app/config.py`, và tối ưu latency.
- [ ] **Mục 11.6 (Evidence Gates & Test tái lập):** Chạy `pytest tests/ -v`, benchmark đa lượt + Golden 200, và test hồi quy cho 2 ca Turn 3/Turn 4 trong `session_bgsi9hbkmwi6p227`.

---

## GIAI ĐOẠN 12: TỐI ƯU HÓA LATENCY TRÊN SERVER GPU REMOTE (ĐÃ HOÀN TẤT 17/11/2026)
> **Kết quả thực đo:** Tiny streaming TTFT giảm từ `4,083.8 ms` (Ngrok) xuống `1,640.2 ms` (cold) và **`649.2 ms`** (prefix-cache hit) qua Cloudflare + vLLM; TTFT trung bình phiên Playground giảm từ `11,280 ms` xuống **`4,696 ms`**.
- [x] **Mục 12.1 (vLLM KV-Cache & Chunked Prefill):** Bật `--enable-chunked-prefill`, `--max-num-batched-tokens 2048` và bỏ `--enforce-eager` trên Kaggle vLLM.
- [x] **Mục 12.2 (System Prompt Prefix Caching):** Bật `--enable-prefix-caching` và giữ tĩnh 100% `messages[0]` trong `chat_graph.py`.
- [x] **Mục 12.3 (Cloudflare Quick Tunnel):** Chuyển từ Ngrok sang `cloudflared` Quick Tunnel (`trycloudflare.com`).
- [x] **Mục 12.4 (Cache Embedding & Cắt Rerank Dư Thừa):** Thêm `@lru_cache(maxsize=512)` trên `embed_query_dense`, khử double `"query: query: "`, cắt `deduped_candidates[:top_candidates]` và bỏ rerank thừa cho câu điều hướng.

---

## GIAI ĐOẠN 13: HOÀN THIỆN SINH VĂN 7B & KIỂM CHỨNG THỰC TẾ NGOÀI KỊCH BẢN (PHIÊN TIẾP THEO)
> **Nguồn phát sinh:** Log Playground `session_ta0ppev2mwjkyk7s` (`17/11/2026 01:13:54`) — Retrieval & Timestamp Guardrail đã chuẩn, cần dứt điểm hiện tượng LLM 7B lặp văn Turn 2 và vỏ `[Video Bài 12 - ]`.
- [x] **Mục 13.1 (Làm sạch `sliding_history` trong `app/services/chat_graph.py#L685-L778,L820-L821`):** Đã strip `<timestamp ...>...</timestamp>`, dòng `📍 **Mốc video bài giảng:** ...` và nhãn `[Video Bài ...]` khỏi các lượt `assistant` cũ trước khi nạp vào ngữ cảnh lượt mới (kể cả lượt `t-1`).
- [x] **Mục 13.2 (Đổi format `_format_context_block` trong `app/services/chat_graph.py#L168-L175`):** Đã chuyển từ `[Video Bài {seq} - {tag}]:` sang `Nguồn Bài {seq} (mốc {tag}):` để LLM 7B không bắt chước bọc ngoặc vuông quanh `<timestamp>`.
- [x] **Mục 13.3 (Neo lộ trình khi hỏi lùi bài `<= current_lesson_seq`):** Trong `crag_grader_node`, khi `is_curriculum_navigation=True` & `grounded`, đã chèn `[THÔNG TIN BÀI HỌC KHỚP GIÁO TRÌNH]` vào `user_message_content`.
- [ ] **Mục 13.4 (Kiểm chứng thực tế Out-of-Script + Dọn `config.py` & Benchmark cuối):** Test tự do trên Playground với chủ đề mới (Con trỏ / Struct / Xâu ký tự), dọn sạch cấu hình chết trong `app/config.py` & class `SocraticOutputGuardrail`, rồi chạy 1 lượt benchmark tổng thể (`pytest` + Multi-Turn + Golden 200) xác nhận 0% hồi quy.

---

## GIAI ĐOẠN 14: PLAYBACK TEMPORAL RETRIEVAL, 83-LESSON CHAPTERS, ANTI-PARROTING & LIVE E2E MATRIX (18/11/2026)
- [x] **Mục 14.1 (Playback-Aware Temporal & Video Chapters):** Nối `current_video_sec` từ Playground UI vào `RetrievalService`; xây dựng `scripts/build_video_chapters.py` tạo `video_chapters` cho **83/83 bài** trong `data/curriculum/lessons_manifest.json`; hỗ trợ phân rã mốc thời gian tương đối/tuyệt đối và câu hỏi đa chủ đề (`disjunction` như `"con trỏ hay vòng lặp"`).
- [x] **Mục 14.2 (In-Video Temporal NLI Rescue & Anti-Parroting 7B):** Bổ sung `Bước 3b` NLI cứu xét câu hỏi có yếu tố thời gian trong `app/agent/router.py` đồng bộ với `TelemetryCritic`; xóa tag ngoặc vuông trong lịch sử `context_assembly_node`, thêm `StreamingInternalArtifactSanitizer` + `25s` timeout & sửa `last_course_query` checkpointer trong `app/services/chat.py`.
- [x] **Mục 14.3 (AST Transcript Canonicalizer & Live E2E Matrix Harness):** Triển khai `scripts/canonicalize_transcripts_ast.py` (`--audit-hotwords`: 83/83 bài) và `scripts/e2e_matrix_harness.py` (mặc định GPU, có `--safe-cpu` và `--routing-only`).
- [x] **Mục 14.4 (Kết quả chạy Live E2E `--suite all` lúc `17:14–17:20`):**
  - `M1` (`cpp-oop` Bài 53): **10/10 PASS**, Health Score `93/100`, Socratic `100%`, avg TTFT `15,868ms` (lượt T3 cold load `96.5s`, T7 constructor từ chối giải full code đạt chuẩn).
  - `M2` (`cpp-core` Bài 11): **5/7 PASS** (Health Score `91/100`, Socratic `100%`, avg TTFT `3,884ms`). Hai lượt còn lại: T1 bị lệch chữ phiên âm `"mạng"` thay vì `"mảng"` + thiếu `?` cuối câu; T3 sửa đúng bug `i<=n` không lộ full solution nhưng thiếu `?` cuối câu.
  - `M3` (`cpp-oop` Bài 53 — Jailbreak & Edge): **5/5 PASS**, Health Score `96/100`, Socratic `100%`, avg TTFT `3,123ms`.
- [x] **Mục 14.5 (Việc tiếp theo cho phiên sau — Đã hoàn tất 19/11/2026):** Đã chạy live `scripts/canonicalize_transcripts_ast.py --gemini` cho 7 bài nhóm Mảng (`11, 12, 13, 14, 15, 64, 67`: `534/534` chunks processed/upserted, `0 errors`), hoàn thiện `StreamingSocraticFooterGuard` cho `?` Socratic và chạy lại `scripts/e2e_matrix_harness.py --suite all` xác nhận **`all_passed: true` (`22/22`)**.

---

## GIAI ĐOẠN 15: SWARM RUNTIME SMOOTHNESS, PSTACK RIGOR & ARRAY CANONICALIZATION (19/11/2026)
> **Cơ chế thực thi:** Swarm (`Orchestrator Neon` Coordinator, `auditor` `Gemini 4 Argon High` sau hot-swap từ `Opus 5.5 High`, `coder` `Gemini 4 Argon Medium`, `verifier` `Gemini 4 Hydrogen Medium`, `monitor`).
- [x] **Mục 15.1 (Nhịp 1–3 `[spec-1..4]` & Batch Prototype Warmup — `#5`, `#10`, `#19`, `#20`, `#25`):**
  - Cứng hóa `IntentRouter.is_pure_social()` + `is_code_solicitation()` từ `router_intent_manifest.json` + bảo toàn `is_security_refusal` tại `router_node`.
  - Hoàn thiện `StreamingSocraticFooterGuard` (vá edge cases `A, B, D, F, I`), tách `extract_prose_outside_code_and_footer` dùng chung với `TelemetryCritic`, hợp nhất `StreamingOutputPipeline` & `SocraticOutputGuardrail`, tách câu fallback khỏi lịch sử `commit_assistant_turn`.
  - Batch prototype warmup (`embed_queries_dense_batch`): giảm độ trễ `router_node` Q1 từ `2,446.4 ms` → **`28.5 ms`** (`85.8x`, zero LRU cache pollution); dọn 21 dead config fields trong `app/config.py` và nối `settings.PARETO_DOMINANCE_CODE_FUTURE_MIN` trong `app/services/retrieval.py`; tinh chỉnh Rule 3 canonicalizer 1-đối-1.
  - Bằng chứng PASS (`#25`): `test_p0_regression.py` (`4/4`), `test_unseen_edges_and_canonicalizer.py` (`24/24`), `test_tier_2_socratic_refusal_precision` (`1/1`), `test_e2e_anti_parroting_and_critic.py -k "not telemetry_critic"` (`9/9`).
- [x] **Mục 15.2 (Xử lý OpenMP / CPU Thread Contention — `#21`, `#26`, `#27`, `#29` `[approved]`):** Pin `cpu_threads=1` & `reranker_threads=1` khi `device=="cpu"` hoặc `OMP_NUM_THREADS=="1"`, bật `batch_size=32` cho CPU `embed_queries_dense_batch` (`app/services/embedding.py`), pin `torch.set_num_threads(1)` cho `NLIArbiter` CPU & `opts.intra_op_num_threads` (`app/agent/router.py`), đồng bộ `SAFE_CPU_MODE` trong `tests/test_e2e_anti_parroting_and_critic.py`; bằng chứng PASS: `test_e2e_anti_parroting_and_critic.py` **15/15 PASSED** trong `36.56s`.
- [x] **Mục 15.3 (Canonicalize Live Nhóm Bài Mảng — `#43`, `#45`, `#54`):** Bổ sung `--gemini` (`gemini-3.5-flash-lite`) + xoay vòng đa key `GEMINI_API_KEYS` vào `scripts/canonicalize_transcripts_ast.py` (`tests/test_unseen_edges_and_canonicalizer.py`: 24/24 PASSED), chạy tuần tự 7 bài (`11, 12, 13, 14, 15, 64, 67`) với `--apply --sync-qdrant --refresh-chapters --async-mode --max-concurrency 5`: **534/534 processed, 307 updated, 212 unchanged, 15 guardrail-rejected, 0 errors, 534 Qdrant points upserted**. Kiểm chứng trực tiếp `lesson-11_chunks.json` tại `chunk_1228_1291` (`1228s`) & `chunk_1276_1324` (`1276s`) đã chuẩn hóa `"mảng"` (video_chapters L11/12/13/14/64/67 sạch `mạng/màng`; riêng L15 còn 1 chapter `14:41` chưa đổi do chunk bị guardrail-rejected hoặc unchanged).
- [x] **Mục 15.4 (Cổng Nghiệm Thu Cuối `[spec-5]`, `[spec-6]` & Pytest Hậu Kiểm Toàn Phần — `#67`, `#69`, `#75`, `#77`, `#81`, `#87`):**
  - `[spec-5]`: Tách phạm vi `_extract_glossary_lookup_text()` (không quét TOC/danh mục lộ trình), chặn stale `conv_summary` khi chuyển mốc/lộ trình, đánh số cặp nhánh `multi_topic_disjunction` (`M2-T05` đủ Bài 57 & Bài 6).
  - `[spec-6]`: Cắt `[MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI]` khỏi các câu hỏi mốc video/vị trí cụ thể đã có chunks (`M1-T05`, `M1-T07`), lọc TOC theo `focus_sec ± 600s` cho phân đoạn tương đối, và không nối `last_course_query` khi `deictic_current` có `current_video_sec` tường minh.
  - **Live E2E (`scripts/e2e_matrix_harness.py --suite all`, GPU + Kaggle `Qwen/Qwen2.5-Coder-7B-Instruct`):** **`all_passed: true` (`22/22 turns PASS`)** — `M1`: **10/10** (Health `93/100`, Socratic `100.0%`), `M2`: **7/7** (Health `99/100`, Socratic `100.0%`), `M3`: **5/5** (Health `96/100`, Socratic `100.0%`).
  - **Hậu kiểm `pytest` sau bản sửa cuối (`[spec-6]`, `71 passed, 0 failed, 0 skipped`):** `test_playback_temporal_and_disambiguation.py` (`9/9`), `test_unseen_edges_and_canonicalizer.py` (`28/28`), `test_group1_2_optimizations.py` (`4/4`), `test_p0_regression.py` (`4/4`), `test_e2e_anti_parroting_and_critic.py` (`15/15`), `test_chat_stream.py` (`6/6`), `test_search_api.py` (`4/4`), `test_multiturn_benchmark.py -k "test_tier_2_socratic_refusal_precision"` (`1/1`, 4 deselected).
  - *(Lưu ý Mục 13.4 giữ `[ ]` riêng cho phần test UI Playground tự do trực tiếp với người dùng & benchmark Golden 200 ngoài phạm vi offline/matrix phiên này).*

---

## GIAI ĐOẠN 16: KIỂM TOÁN LOG PLAYGROUND DEMO THỰC TẾ & SPEC-DRIVEN HỘI TỤ (20/11/2026)
- [x] **Mục 16.1 (Kiểm toán 2 debug Playground gần nhất — 20/11/2026):** Đã đọc toàn bộ 2 log:
  1. `logs/playground_debug/session_session_le0ib7e9mwn86374_20261119_142753.json` (`9 turns`, Health **`35/100`**, Socratic `66.7%`): phát hiện `T6/T7/T9` (`"khoảng phút bao nhiêu thì nói về lý thuyết"`) trôi vào `chit_chat` identity; `T3->T4` (`"chuyển cho tôi đến bài đó"`) mất neo Bài 57 rơi về Bài 2; `T2` Bài 1 còn từ `"mạng"`.
  2. `logs/playground_debug/session_session_7ztumoqfmwn8a8no_20261119_143313.json` (`10 turns`, Health **`91/100`**, Socratic `100.0%`): phát hiện `T4` (`"chi tiết hơn"`) bị chặn `out_of_scope`; `T7/T8` ẩn dụ `"ví dụ con trỏ giống như tờ giấy ghi địa chỉ nhà..."` bị co thành 1 câu nhại lại; `T10` (`"ngoài bài 57 thì muốn học về vector với iterator hoặc tìm kiếm nhị phân..."`) kẹt `grounded` Bài 57; `T9` kéo `Bài 54` vào timestamp; `T5/T9` thiếu nhãn `📍 **Mốc video bài giảng:**` / còn câu kết cấm.
- [x] **Mục 16.2 (Chế độ B — Swarm Spec-Driven Convergence `PC-01..PC-05` — ĐÃ HOÀN TẤT `20/11/2026`):**
  - **Nhịp 1 (`#94..#99`):** Trace gốc 5 lỗi Playground, hoàn thành 1 vòng Adversarial Red-Team Debate (`coder-2` `Gemini 4 Hydrogen High` vs `auditor-2` `Claude Opus 5.5 High` -> hot-swap `Gemini 4 Neon High` sau `429`), chốt `specs/001-playground-e2e-convergence/spec.md` v2 (`[approved-spec]`).
  - **Nhịp 2 (`#105..#117`):** Triển khai tuần tự 5 lớp (`router_intent_manifest.json`, `cpp_academic_glossary.json`, `lesson-01_chunks.json` + Qdrant L1 upsert/refresh, `app/agent/router.py`, `app/agent/prompts.py`, `app/services/curriculum.py`, `app/services/retrieval.py`, `app/services/chat_graph.py`, `app/services/chat.py`, `app/services/telemetry_critic.py`), thêm `tests/test_playground_e2e_convergence.py`, sửa triệt để 5 điểm audit (`#107`) & 2 hồi quy Phase 3A (`#113` -> `#115`), đạt `[approved]` (`#117`).
  - **Nhịp 3 (`#123`, `#125` — sau bản sửa cuối `#115`):**
    - **LIVE E2E Matrix (`scripts/e2e_matrix_harness.py --suite all`, `Qwen/Qwen2.5-Coder-7B-Instruct` Kaggle):** **`all_passed: true` (`22/22 PASS`)** — `M1`: **10/10** (Health **97/100**, Avg TTFT `4894ms`), `M2`: **7/7** (Health **99/100**, Avg TTFT `2791ms`), `M3`: **5/5** (Health **98/100**, Avg TTFT `2044ms`), Socratic `100.0%`.
    - **LIVE 5-PC Playground Replay (`ChatService.stream_chat` + `TelemetryCriticService`):** `PC-01` (90/100, không dính identity), `PC-02` (`"chi tiết hơn"` `course_query` 90/100), `PC-03` (Bài 57/48/79/64 clarification, không rơi L2; `Bài 999` từ chối động `Bài 1..Bài 83`, 97/100; L1 grep 0 lỗi `"mạng"`/`"câu chúc"`), `PC-04` (giải thích 3 đoạn thực chất + `<timestamp>`, 90/100), `PC-05` (`suggested_timestamps=[]`, đủ Vector Bài 20 & Tìm kiếm nhị phân Bài 25; lượt quay lại 0 dính L54, 90/100).
    - **11 bộ `pytest` chạy tuần tự sau bản sửa cuối (`86 passed, 0 failed, 0 skipped`, 4 deselected ở `-k test_tier_2_socratic_refusal_precision`):** `test_stage13_context_hygiene.py` (`6/6`), `test_search_api.py` (`4/4`), `test_playground_e2e_convergence.py` (`5/5`), `test_playback_temporal_and_disambiguation.py` (`9/9`), `test_unseen_edges_and_canonicalizer.py` (`28/28`), `test_session_7aky9_debug_fixes.py` (`4/4`), `test_group1_2_optimizations.py` (`4/4`), `test_p0_regression.py` (`4/4`), `test_e2e_anti_parroting_and_critic.py` (`15/15`), `test_chat_stream.py` (`6/6`), `test_multiturn_benchmark.py -k "test_tier_2_socratic_refusal_precision"` (`1/1`).
- [x] **Mục 16.3a (Khảo thí Macro Benchmark không LLM — `20/11/2026`):**
  - `scripts/run_full_evaluation.py --suite all` (`300` câu trong `625.17s`): Router **91.00%** (`273/300` — In-Domain `90.0%`, OOD `93.0%`; 0% lệch trên `In-Scope`/`Out-of-Lesson`), CRAG **83.67%** (`251/300` — In-Domain `86.0%`), Latency Mean **1,938.2ms** trên Golden 200 (giảm từ `4,896.0ms`).
  - `scripts/run_multiturn_benchmark.py --mode retrieval` (`50 sessions / 222 turns` trong `446.49s`): Intent **98.65%** (`219/222`), ARR **97.87%** (`92/94`), SRP **100.0%** (`15/15`), Budget **100.0%** (`Max: 894/2400`), Latency Mean **2,010.00ms** (giảm từ `7,531.85ms`). Ghi nhận **19/222** ca lệch status (Pareto L2->L5, `L3 ++x/x++` `coverage_gap` tại `max_current=0.2302`, NLI `SWITCH-32/38`) làm `Retrieval Status` ở `91.44%` và `Multi-Grounding TS` ở `86.94%` (< 90%).
- [ ] **Mục 16.3b (Re-clean toàn bộ 83 Transcripts + Hồi phục `Multi-Grounding TS >= 90%` & Đồng bộ Overnight Harness):**
  - Chạy `scripts/canonicalize_transcripts_ast.py --gemini --apply --sync-qdrant --refresh-chapters --async-mode` (xoay đa key `GEMINI_API_KEYS`) làm sạch toàn bộ 83 bài học (khử lỗi đồng âm Whisper như `"kính UV"`, `"phát bại trị"`, `"petero"`, `"++x/x++"`).
  - Rà ngưỡng `is_raw_valid` (`L3 ++x/x++` `0.2302`) / Pareto & chạy lại `run_multiturn_benchmark.py --mode retrieval` khôi phục `Multi-Grounding TS >= 90%`.
  - Cập nhật `"thanhnghiaa1402@gmail.com"` và bảng profile tránh `Argon 21%` trong `scripts/thinker_doer_pipeline.py` / `scripts/master_autonomous_harness.py`.
