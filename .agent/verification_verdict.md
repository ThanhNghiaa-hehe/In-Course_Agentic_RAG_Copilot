# Báo Cáo Kiểm Toán Độc Lập PSTACK - Nhịp 3 (Vòng Lặp #1)

- **Vai trò thực hiện:** `grounding-evaluator` (Kiểm toán viên độc lập)
- **Tác giả Đồ án:** Trần Thành Nghĩa (MSSV: `23DH112252`) — HUFLIT
- **Đối tượng kiểm toán:** Spec `005-unified-dataset-workflow-repair` (`specs/005-unified-dataset-workflow-repair/spec.md`) & kết quả chạy Harness Stage 1 (`.agent/harness_stage1_latest.log`)
- **Trạng thái Harness Stage 1:** **`exit_code = 1` (THẤT BẠI tại Gate 4b)**

---

## 1. Tóm Tắt Bằng Chứng Thực Đo Từ Harness & Báo Cáo Benchmark

| Cổng Kiểm Chứng (Stage 1) | Trạng thái | Bằng chứng trực tiếp | Ghi chú kiểm toán |
|---|:---:|---|---|
| **Gate 1: AST & Anti-Bypass Diff** | **PASS** | `.agent/harness_stage1_latest.log#L5` (`0.6s`) | `0` lỗi cú pháp, `0` vi phạm Anti-Bypass |
| **Gate 2: Sequential Pytest (13 suites)** | **PASS** | `.agent/harness_stage1_latest.log#L6-L153` (`337.9s`) | Đủ `13/13` suites PASS (gồm `test_spec005_unified_dataset_workflow.py`: `8 passed`) |
| **Gate 3: E2E Matrix (`--suite all --routing-only`)** | **PASS** | `logs/playground_debug/e2e_matrix_latest_summary.json` (`2026-11-26T13:17:48`) | `all_passed: true` (`9/9` suites: `M1=99`, `M2=100`, `M3=100`, `S1=99`, `M4..M7=100`, `M8=95`; Socratic `100.0%`) |
| **Gate 4a: Multi-Turn Benchmark (50/222)** | **PASS (CI Gate) / WARN (TS)** | `docs/benchmarks/multiturn_benchmark_results.json` (`2026-11-26T13:18:16` → `13:24:18`) | Intent `98.65%` (`219/222`), Status `93.24%` (`207/222`), ARR `98.94%` (`93/94`), SRP `100.0%` (`15/15`), Budget `100.0%` (`894/2400`), Mean `1631.22ms`. **Lưu ý:** `Multi-Grounding Timestamp Safety = 88.74% (197/222) < 90.0%` (`CHƯA ĐẠT` trong `multiturn_benchmark_results.md#L20`) |
| **Gate 4b: Stage 11 Golden 200** | **FAIL (KILLED)** | `.agent/harness_stage1_latest.log#L483-L500` & `docs/benchmarks/latest_benchmark_results.json` | `run_rag_benchmark.py` im lặng quá `240s` (`13:24:24` → `13:28:42`), bị `ThreadedSubprocessWatchdog` cưỡng chế hủy cây tiến trình. File `latest_benchmark_results.json` vẫn là bản cũ từ `2026-11-25 20:21:18`! |
| **Dataset Validation Gate (`--mode validate --with-e5`)** | **PASS** | `docs/benchmarks/dataset_validation_report.json` (`2026-11-26 13:29:24`) | `all_passed: true` (`4/4` models PASS, `522` held-out queries, `0` leaked) |

---

## 2. Kiểm Toán Chất Lượng Mã Nguồn & Chống Gian Lận (`git diff`)

### 2.1. Mã nguồn Runtime (`app/agent/router.py`, `app/services/chat_graph.py`)
- **Zero Regex Runtime:** Quét toàn bộ `app/**/*.py` xác nhận **`0` lệnh `import re` / `re.*`** trong mã thực thi (chỉ có chuỗi chú thích bình thường tại `app/services/chat.py#L450`).
- **Zero Quick-Fix / Zero Test-Set Snooping:** `0` chuỗi `BENCH-` hoặc `SESSION-`, `0` hardcode từ khóa đề thi.
  - `IntentRouter._has_verified_curriculum_topic` (`app/agent/router.py#L717-L737`) và cổng NLI override (`#L1126-L1140`) cài đặt đúng bất đẳng thức đại số §3.1 (`nli_conf >= 0.80 and p_oos >= 0.22 and (p_course - p_oos) < 0.25 and not topic_verified and not has_student_code`), giải quyết triệt để nhánh dead code `p_oos > p_course`.
  - `IntentRouter.is_curriculum_navigation` (`#L623-L654`) bổ sung `sim_chitchat` trên `self._chitchat_proto_matrix` khi `not has_nav_sig` — không ảnh hưởng các lượt điều hướng có chữ ký tường minh.
  - `app/services/chat_graph.py#L798` sửa `fb_high_conf = bool(fb_scores) and ...` đúng chuẩn fail-closed.

### 2.2. Dữ liệu & Kịch bản Offline (`scripts/`, `data/`, `tests/`)
- **83 file transcript (`data/transcripts/*/*_chunks.json`):** Kiểm tra độc lập toàn bộ `83` file cho kết quả `total_chunks = 6387`, `empty = 0`, `bad_chars = 0` (ngoài ASCII + 134 chữ cái NFC tiếng Việt + dấu câu chuẩn), `loops = 0`.
- **Corpus SLM & 3 Dataset Kaggle:** `router_training_corpus.json` (`496` mẫu), `router_hard_negative_hybrid_pool.json` (`58` mẫu), `router_training_corpus_v2_9_hybrid.json` (`552` mẫu, `audit.total_clean_samples == 552`, `0` ID `BENCH-`/`SESSION-`). Các bộ JSONL (`mdeberta_nli`: `1926`, `jina_reranker`: `674`, `qwen25_qlora`: `284` phủ `83/83` bài, `SOCRATIC_GROUNDED_PROMPT`, `len_total` `6377..6775`) và 3 trainer (`GroupShuffleSplit`, `DataCollatorForSeq2Seq`, `max_length=2048`) đạt chuẩn Spec 005.
- **Tests & Harness (`tests/test_spec005_unified_dataset_workflow.py`, `tests/test_unseen_edges_and_canonicalizer.py`, `scripts/master_autonomous_harness.py`):** Không phát hiện `@pytest.mark.skip`, `pytest.skip(`, nới lỏng assertion, hay sao chép đề thi benchmark.

---

## 3. Lý Do Bắt Buộc Từ Chối (REJECTED) Ở Vòng Lặp #1

1. **Stage 1 Harness thất bại (`exit_code = 1`) tại Gate 4b (`scripts/run_rag_benchmark.py`):**
   - Trong `.agent/harness_stage1_latest.log#L484-L500`, `scripts/run_rag_benchmark.py --dataset tests/data/benchmark_golden_dataset.json` bị treo im lặng quá `inactivity_timeout_sec=240` (`13:24:24` → `13:28:42`) ngay sau khi nạp `TextEmbedding` và bị `ThreadedSubprocessWatchdog` hủy tiến trình.
   - Nguyên nhân kỹ thuật quan sát được: `scripts/run_rag_benchmark.py` (`#L156`, `#L293`) gọi `print(...)` **không có `flush=True`**, đồng thời `scripts/master_autonomous_harness.py` / `ThreadedSubprocessWatchdog` (`#L188-L197`, `#L422-L424`) chạy `subprocess.Popen(..., stdout=subprocess.PIPE)` mà **không đặt `PYTHONUNBUFFERED=1`** (hoặc `-u`), khiến stdout của tiến trình con bị block-buffer và không xả dòng tiến độ về Watchdog suốt > 240 giây (hoặc tiến trình bị nghẽn trong pha warmup/search).
2. **Thiếu hoàn toàn bằng chứng khảo thí mới cho Stage 11 Golden 200 (`REQ-01` & `REQ-02`):**
   - Tệp `docs/benchmarks/latest_benchmark_results.json` vẫn giữ mốc thời gian cũ `2026-11-25 20:21:18` (trước khi sửa Spec 005). Do đó chưa có kết quả thực đo sau chỉnh sửa cho `Router >= 90.5%`, `CRAG >= 86.0%`, và đặc biệt mục tiêu sống còn `Timestamp Safety >= 86.5%` (vốn đang ở mức `86.0%` trong bản cũ).
3. **Cảnh báo chất lượng ở Multi-Turn Benchmark (`docs/benchmarks/multiturn_benchmark_results.md#L20`):**
   - Dù đạt ngưỡng `evaluate_quality_gates`, chỉ số `Multi-Grounding Timestamp Safety Rate = 88.74% (197/222)` vẫn dưới chuẩn mục tiêu `>= 90.0%` (`CHƯA ĐẠT (FAILED)` — đặc biệt `Tier 3: 76.19%`, `Tier 2: 88.33%`, `Tier 4: 88.33%`).

VERDICT: REJECTED: Stage 1 Harness thất bại (exit_code=1) do Gate 4b `scripts/run_rag_benchmark.py` bị Watchdog hủy sau 240s im lặng (thiếu `PYTHONUNBUFFERED=1` / `flush=True` hoặc nghẽn thực thi khiến `docs/benchmarks/latest_benchmark_results.json` vẫn cũ từ 2026-11-25, chưa chứng minh được REQ-01/REQ-02 Timestamp Safety >= 86.5%); đồng thời cần rà soát lại các ca tụt Multi-Grounding Timestamp Safety (88.74% < 90.0%) trong `docs/benchmarks/multiturn_benchmark_results.json`.
