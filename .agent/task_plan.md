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
- [x] **Mục 16.3b (Re-clean toàn bộ 83 Transcripts + Hồi phục `Multi-Grounding TS` & Nghiệm thu Swarm Gemini 3.8 Flash — `23/11/2026`):**
  - Đã hoàn thiện Spec & Pipeline `specs/002-smart-reclean-pipeline/spec.md` (Smart 2-Pass + Layer A deterministic + `gemini-3.1-flash-lite` Layer B Cross-Model Auditor + chặn JSON leak / LaTeX / localized 3-segment hallucination + `QdrantSyncResources` singleton + checkpoint `PARTIAL_ERROR`).
  - **Nhịp 1 & Nhịp 2:** Hoàn tất 83/83 bài học (`6,387/6,387` chunks) với 0 JSON/LaTeX leaks, cập nhật `3,452` chunks so với bản sao lưu gốc.
  - **Nghiệm thu Swarm Verification (Gemini 3.8 Flash - `seanpaul1402`):**
    - Kiểm toán chuyên sâu toàn bộ 59 chunk tồn đọng trong `scratch/swarm_audit_targets.json`.
    - Phân định rạch ròi 36 ca False Alarms (từ ngữ chuẩn: phím tắt IDE `Ctrl+N`/`Ctrl space`, `trên mạng`/`mạng xã hội`, `sắp xếp nổi bọt` trong bài so sánh giải thuật, toán tử `*(a++)`) và 23 ca lỗi ngữ âm thực tế (`ngu nữ là chi chịu cộng -> ngôn ngữ lập trình C++`, `Tiết cây -> Test case`, `bán kính và diện tích -> chu vi và diện tích`, `ngăn sếp -> ngăn xếp`, `câu chúc giữa phật -> Cấu trúc dữ liệu và giải thuật`).
    - Áp dụng 30 bản vá (bao gồm loại bỏ triệt để rác âm học CJK) qua cổng kiểm duyệt `validate_canonical_chunk(targeted=True)` và `run_supervisor_layer_a` đạt 100% PASS, 0 metadata mutation.
    - Đồng bộ nguyên tử lên Qdrant Cloud cluster: `exact_count = 6,387 / 6,387`, `spot_payload_parity = True`.
    - Làm mới `video_chapters` trong `data/curriculum/lessons_manifest.json`.
  - **Khảo thí Đối chuẩn Sau Nghiệm thu:**
    - `pytest tests/test_unseen_edges_and_canonicalizer.py`: **`34/34 passed`** (`100%`).
    - `scripts/run_multiturn_benchmark.py --mode retrieval` (50 sessions / 222 turns): Intent **98.65%**, ARR **98.94%**, SRP **100.0%**, Budget **100.0%**, Retrieval Status **90.54%**, Multi-Grounding Safety **86.49%**.
    - Residual audit: chỉ còn đúng **39 chunks** (100% là False Alarms đã được thẩm định bảo toàn).
- [x] **Mục 17 (`Spec 003` — Đồng bộ 7 tầng sửa 5 Problem Classes Playground Kịch bản 1 — `23/11/2026`):**
  - Chẩn đoán phiên `logs/playground_debug/session_session_ro5jsf0kmwt30fh6_20261123_165346.json`: `PC-01` (`L19` cướp quyền `L43` + thiếu `sources` khi `out_of_lesson` + spoil 3 bước), `PC-02` (đứt `anchor_query` Lượt 5 + ảo giác *"Đúng vậy, bạn đã mô tả..."* + điểm mù `TelemetryCritic`), `PC-03` (`SecurityInputGuardrail` chặn nhầm Lượt 4/6 thành OWASP LLM01), `PC-04` (câu hỏi kép Lượt 2 kéo 4 bài nhiễu + mất giải thích `++x`/`x++` & timestamp), `PC-05` (lọt câu kết *"Bạn muốn biết thêm thông tin..."*).
  - **Swarm 5 Agents (`pstack` 4 chặng):** `@solution-analyst` & `@rag-architect` (`gemini-4-argon-high`) thiết kế `specs/003-playground-scenario1-fixes/spec.md` (`v2.1`) $\rightarrow$ `@codebase-auditor` (`claude-sonnet-5-5-high` Cổng 1 `#137`, chuyển dự phòng `gemini-4-argon-high` ở Cổng 2 `#145`) $\rightarrow$ `@core-coder` (`gemini-4-hydrogen-high`) triển khai đồng bộ 7 tầng (`#144`) $\rightarrow$ `@grounding-evaluator` (`gemini-4-hydrogen-high`) nghiệm thu tuần tự (`#147`).
  - **Kết quả Nghiệm thu (`#147`, `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`):**
    - **12/12 `pytest` suites tuần tự (`97 passed, 0 failed, 0 skipped`, 4 deselected ở `-k test_tier_2_socratic_refusal_precision`):** gồm `tests/test_playground_scenario1_fixes.py` (`5/5`), `test_p0_regression.py` (`4/4`), `test_playground_e2e_convergence.py` (`5/5`), `test_playback_temporal_and_disambiguation.py` (`9/9`), `test_session_7aky9_debug_fixes.py` (`4/4`), `test_stage13_context_hygiene.py` (`6/6`), `test_group1_2_optimizations.py` (`4/4`), `test_e2e_anti_parroting_and_critic.py` (`15/15`), `test_chat_stream.py` (`6/6`), `test_search_api.py` (`4/4`), `test_unseen_edges_and_canonicalizer.py` (`34/34`), `test_multiturn_benchmark.py` (`1/1`).
    - **Replay 7 lượt Kịch bản 1 (Real ONNX + Qdrant + LangGraph, LLM Kaggle đang offline):** `T2 -> Bài 3 (is_ambiguous=False, ts=[1275s], len(sources)==1)`, `T4 & T6 -> course_query (SOFT REFUSAL / PSEUDOCODE GUIDANCE)`, `T5 -> grounded Bài 3 (AST 450s)`, `T7 -> out_of_lesson Bài 43 (ts=[204s], len(sources)==1)`; `TelemetryCriticService` bắt `3/3` lỗi giả lập; `BENCH-041/049/091/092` 0% hồi quy; `BENCH-191..200 + M3-T4` `11/11` blocked; `20-query Held-out` `10/10 + 10/10`.
    - **`run_multiturn_benchmark.py --mode retrieval` (`50 sessions / 222 turns`):** Intent `98.65%`, Retrieval Status `90.09%` (`1` timeout Qdrant ở `STRESS-49 T5`), ARR `98.94%`, SRP `100.00%`, Budget `100.00%`.
    - **Dữ liệu nguồn & Metadata sạch sẽ:** 5/5 manifest JSON UTF-8 NFC hợp lệ, `83` bài học khớp `syllabus_embeddings.npz` `(83, 1024)`, Qdrant Cloud `video_transcript = 6,387` & `code_ast = 64` (100% parity).

---

## GIAI ĐOẠN 18: PSTACK SPEC 004 — SỬA ĐỒNG BỘ WORKFLOW RAG LIÊN TẦNG & LOGIC FALLBACK (`2026-11-25`)
> **Đặc tả Unified E2E Spec:** [`specs/004-unified-rag-workflow-hardening/spec.md`](file:///D:/In_Course_Agentic_RAG_Copilot/specs/004-unified-rag-workflow-hardening/spec.md)  
> **Đặc tả Triển khai & Toán học:** [`.agent/implementation_spec.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/implementation_spec.md)  
> **Kiểm toán Nhịp 1A:** [`.agent/technical_debt_audit.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/technical_debt_audit.md)  
> **Nguyên tắc:** Cross-Layer Unified Fix | 0% Regex Runtime | 0% Quick-Fix | 0% Test-Set Snooping | Pre/Post Benchmark Cycle

### Nhịp 1A & 1B: Kiểm Toán Liên Tầng & Thiết Kế Unified E2E Spec + Conflict Matrix
- [x] **Mục 18.0.1 (Nhịp 1A — Deep E2E Audit):** `@codebase-auditor` truy vết toàn luồng `IntentRouter → CurriculumService → RetrievalService → ChatGraph → ChatService → TelemetryCritic` tại `HEAD 5986d5d`, tái hiện sống `M6-T03`, `M7-T02`, `M8-T03`, bóc trần 3 lối tắt `<=`, điểm ảo `0.505`, rủi ro "neo `1.0`" ở RRF-fallback, và độ trễ freshness của Baseline JSON; xuất bản [`.agent/technical_debt_audit.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/technical_debt_audit.md).
- [x] **Mục 18.0.2 (Nhịp 1B — Unified E2E Spec & Cross-Layer Conflict Matrix):** `rag-architect` & `solution-analyst` thiết kế giải pháp toàn luồng cho 6 Problem Classes (`PC-01..PC-06`), phát hiện thêm 2 điểm gãy hạ nguồn ở `crag_grader_node` (`find_lesson_for_query` ghi đè ngược & `competing_lessons` xóa `f_chunk`), chứng minh toán học vị từ `nav_label_verified_in_window` + Biên Pareto Unresolved-Nav `(0.40, -0.12)` + trần lý thuyết Qdrant RRF ($R_{\max}^{\star}=1.0$) & dải suy giảm `[0.15, 0.29]`, khóa Ma trận Xung đột Chéo `C1..C10`; xuất bản [`specs/004-unified-rag-workflow-hardening/spec.md`](file:///D:/In_Course_Agentic_RAG_Copilot/specs/004-unified-rag-workflow-hardening/spec.md) và đồng bộ [`.agent/implementation_spec.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/implementation_spec.md).

### Bước 0 & Nhịp 2: Chụp Baseline Mới & Triển Khai Nguyên Tử 6 Lớp Phụ Thuộc (`@core-coder`)
- [x] **Mục 18.1 (Bước 0 — Fresh Pre-Optimization Baseline tại `HEAD 5986d5d`):** Chạy tuần tự (`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`) 11 Pytest suites + `e2e_matrix_harness.py --suite all --routing-only` + `run_multiturn_benchmark.py --mode retrieval` + `run_rag_benchmark.py`; lưu bản chụp đối chứng vào `scratch/spec004_baseline/`.
- [x] **Mục 18.2 (Lớp 0 & Lớp 1 — Config, Manifest & `IntentRouter`):** Thêm `PARETO_UNRESOLVED_NAV_FUTURE_MIN=0.40`, `PARETO_UNRESOLVED_NAV_MARGIN=-0.12` vào `app/config.py`; tách `temporal_nli_*` ra `data/metadata/router_intent_manifest.json`; sửa `or → and` tại `app/agent/router.py#L875` và chuyển `verify_in_video_temporal_query` sang fail-closed `(False, 1.0)` khi lỗi NLI.
- [x] **Mục 18.3 (Lớp 2 — `RetrievalService`):** Mở rộng 4 trường quan sát trên `RetrievalResult`; triển khai `_compute_calibrated_rrf_norm(..., theoretical_max=1.0)` & chế độ suy giảm `[0.15, 0.29]` khi `reranker_failed=True`; hợp nhất vị từ `nav_label_verified_in_window` + `nav_unresolved_self_match` + Pareto Unresolved-Nav `(0.40, -0.12)` + Revision Non-Dominance Shield; siết modality Tầng 3 (`video_transcript` only) & `grade_document_relevance` (`code_ast >= 0.35`); gắn `is_approximate=True` cho chapter & default `00:00` trong `_build_lightweight_future_chunk`; đính chính 3 docstring CRAG Yan et al. (`arXiv:2401.15884`).
- [x] **Mục 18.4 (Lớp 3 — `ChatGraph / CRAG`):** Cập nhật `AgentState` & `retrieval_node` (4 trường quan sát + điều kiện nâng cấp đơn điệu $\prec$ cho Contextual Fallback); đồng bộ `crag_grader_node` ưu tiên `target_lesson_seq` đã giải, tắt `competing_lessons` override khi `f_chunk` đến từ Cross-Encoder $\ge 0.40$ (bảo toàn `multi_topic_disjunction` & `NavBypass`), đồng bộ `has_approximate`, và sửa docstring CRAG dòng 10.
- [x] **Mục 18.5 (Lớp 4 & Lớp 5 — `Schemas`, `ChatService`, `TelemetryCritic` & `Harness`):** Thêm 4 trường optional có default vào `StreamMetadataEvent` & `chat.py`; vá chống lặp dòng `📍` tại `app/services/chat.py#L2275-L2293` (0% regex); ghi đủ nav/scoring telemetry vào `scripts/e2e_matrix_harness.py`; thêm kiểm tra `Unresolved Curriculum Navigation (-15)` & `Degraded RRF Fallback (-5)` vào `app/services/telemetry_critic.py`.
- [x] **Mục 18.6 (Bộ Test Spec 004):** Viết mới 10 unit/integration test khóa `PC-01..PC-06` và các ca đối chứng tại `tests/test_spec004_unified_workflow_hardening.py` (0% ID benchmark, 0% sao chép nguyên văn đề thi).

### Nhịp 3 (Vòng #1 — Đã Hậu kiểm & Chuyển tiếp sang Vòng #2)
- [x] **Mục 18.7 (Stage 1 Verification Gate — Vòng #1):** Đã chạy `master_autonomous_harness.py --stage 1 --force-eval`: Gate 1 PASS, Gate 2 (`11/11` suites + `10/10` Spec 004 riêng) PASS, Gate 3 **`E2E Matrix 9/9 PASS (all_passed: true, Health 99..100)`**; trượt 2 cổng sát biên `1` ca: Multi-Turn Status `89.64% < 90.0%` (`STRESS-45 T2`) và Golden 200 TS Safety `86.0% < 86.5%` (`BENCH-037`), kèm `except Exception: pass` (`retrieval.py#L2199-L2200`) và thiếu đăng ký suite Spec 004 vào `SEQUENTIAL_PYTEST_SUITES` (`VERDICT: REJECTED` tại [`.agent/verification_verdict.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/verification_verdict.md)).

### Vòng Lặp #2 (Hậu Kiểm Hồi Quy & Khóa Đồng Bộ Liên Tầng — Spec 004 v2.0)
- [x] **Mục 18.8.1 (Nhịp 1A Vòng #2 — Deep Regression Audit):** `@codebase-auditor` truy vết sống và chứng minh 4 nguyên nhân gốc (`RC-L2-01` bất đối xứng Tầng 3 `PC-05a`; `RC-L2-02` tổ hợp RRF tie-break bất định + lỗi ngược chiều `cpp-core`/`cpp-oop` + tín hiệu tương lai không đồng thuận + điểm mù đại từ hồi chỉ `out_of_lesson` ở `retrieval_node`; `RC-L2-03` `except: pass`; `RC-L2-04` thiếu đăng ký Harness Gate 2); xuất bản [`.agent/technical_debt_audit.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/technical_debt_audit.md).
- [x] **Mục 18.8.2 (Nhịp 1B Vòng #2 — Unified E2E Spec v2.0 & Conflict Matrix `C1..C13`):** `rag-architect` & `solution-analyst` thiết kế đồng bộ `C8-v2` (tách cổng quyết định `video_transcript`-only với đóng gói `tier3_bound_code_items` ngưỡng chặt `>= 0.22`), `PC-07` (`C11` khóa RRF tất định đối xứng + `limit >= 20` trước NMS + `is_future_curriculum_target` đơn điệu + Đồng thuận Tương lai Liên tầng cho `is_continuation_turn=True`; `C12` cứu xét anaphoric `out_of_lesson` không đồng thuận với rào chắn 3 lớp `>= 0.30`), và `C13`; nâng cấp [`specs/004-unified-rag-workflow-hardening/spec.md`](file:///D:/In_Course_Agentic_RAG_Copilot/specs/004-unified-rag-workflow-hardening/spec.md) lên **v2.0** và đồng bộ [`.agent/implementation_spec.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/implementation_spec.md).
- [x] **Mục 18.9 (Bước V2-1 — `RetrievalService` Delta):** Thêm `_sort_rrf_points_deterministically` (`prefer_earlier_seq=True/False`) + nâng `_fetch_future_points` RRF `limit=max(FUTURE_PROBE_LIMIT*2, 20)` trước NMS; sửa `is_future_curriculum_target` (`seq > current_lesson_seq`); nâng cấp `has_future_topic_signal` theo Đồng thuận Liên tầng cho lượt nối tiếp; đổi `except Exception: pass` (`#L2199-L2200`) thành `logger.debug`; đồng bộ `assemble_balanced_modality` cho `tier3_bound_code_items` (`seq==current`, non-boilerplate, `approx_video_sec!=None`, `score >= 0.22`) trong Tầng 3. *(KHÔNG ghi đè `scratch/spec004_baseline/`.)*
- [x] **Mục 18.10 (Bước V2-2 — `ChatGraph.retrieval_node` Delta):** Bổ sung nhánh `is_unverified_anaphoric_ool` (`status=="out_of_lesson"` & `curriculum_matched_seq != target_lesson_seq`) khi `search_query != raw_prompt`, chỉ chấp nhận `fallback_res` khi `status=="grounded" and not is_low_confidence and max_score >= 0.30`.
- [x] **Mục 18.11 (Bước V2-3 — Harness Gate 2 & Test Suite Spec 004):** Đăng ký `"tests/test_spec004_unified_workflow_hardening.py"` vào `MasterAutonomousHarness.SEQUENTIAL_PYTEST_SUITES` (`12` suites) và bổ sung 4 unit tests khóa `C8-v2`, `C11a`, `C11b`, `C12` (`14/14` tests, `0%` ID benchmark).
- [ ] **Mục 18.12 (Bước V2-4 — Nhịp 3 Vòng #2 Master Verification Gate):** Chạy `.\.venv\Scripts\python.exe scripts\master_autonomous_harness.py --stage 1 --force-eval` (`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`): xác nhận `exit_code = 0`, Gate 1 (`0` lỗi), Gate 2 (`12/12` suites `110/110` PASS), Gate 3 (`E2E Matrix 9/9 PASS`, Health $\ge 90$), Gate 4a (Multi-Turn Status $\ge 90.0\%$, Intent $\ge 94.0\%$, ARR $\ge 97.0\%$, SRP $= 100\%$), Gate 4b (Golden 200 Router $\ge 90.5\%$, CRAG $\ge 86.0\%$, TS Safety $\ge 86.5\%$), xuất `VERDICT: APPROVED`.
