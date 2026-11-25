# BÁO CÁO THẨM ĐỊNH ĐỘC LẬP — PSTACK NHỊP 3 (VÒNG LẶP #2)

- **Vai trò thẩm định:** `grounding-evaluator` (Kiểm toán độc lập bằng chứng thực nghiệm)
- **Ngày thẩm định:** `2026-11-25`
- **Đặc tả đối chiếu:** [`specs/004-unified-rag-workflow-hardening/spec.md`](file:///D:/In_Course_Agentic_RAG_Copilot/specs/004-unified-rag-workflow-hardening/spec.md) (`v2.0`)
- **Nguồn bằng chứng đã kiểm tra trực tiếp:**
  - [`.agent/harness_stage1_latest.log`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/harness_stage1_latest.log) (`exit_code = 1`)
  - [`docs/benchmarks/latest_benchmark_results.json`](file:///D:/In_Course_Agentic_RAG_Copilot/docs/benchmarks/latest_benchmark_results.json) (`stage11_results_2026-11-25_20-21-18.json`) vs Vòng #1 (`stage11_results_2026-11-25_19-19-05.json`) & Baseline [`scratch/spec004_baseline/latest_benchmark_results.json`](file:///D:/In_Course_Agentic_RAG_Copilot/scratch/spec004_baseline/latest_benchmark_results.json)
  - [`docs/benchmarks/multiturn_benchmark_results.json`](file:///D:/In_Course_Agentic_RAG_Copilot/docs/benchmarks/multiturn_benchmark_results.json) vs Baseline [`scratch/spec004_baseline/multiturn_benchmark_results.json`](file:///D:/In_Course_Agentic_RAG_Copilot/scratch/spec004_baseline/multiturn_benchmark_results.json)
  - [`logs/playground_debug/e2e_matrix_latest_summary.json`](file:///D:/In_Course_Agentic_RAG_Copilot/logs/playground_debug/e2e_matrix_latest_summary.json)
  - `git diff` trên `app/`, `data/`, `tests/`, `scripts/` và [`tests/test_spec004_unified_workflow_hardening.py`](file:///D:/In_Course_Agentic_RAG_Copilot/tests/test_spec004_unified_workflow_hardening.py)

---

## 1. Tổng hợp Kết quả Các Cổng Stage 1 (Harness `exit_code = 1`)

| Cổng kiểm chứng | Kết quả Vòng #2 | Ngưỡng yêu cầu (`Spec 004 v2.0`) | Trạng thái |
|---|---|---|---|
| **Gate 1 — AST & Anti-Bypass Diff** | 0 lỗi cú pháp (`py_compile`), 0 vi phạm static scan | 0 lỗi | **PASS** |
| **Gate 2 — Sequential Pytest (`12/12` suites)** | **`110/110` PASSED** (`11` suites cũ `96/96` + `test_spec004_unified_workflow_hardening.py` `14/14`), 0 failed, 0 skipped | `12/12` suites PASS | **PASS** |
| **Gate 3 — E2E Matrix (`--suite all --routing-only`)** | `all_passed: true` (`9/9` suites: `M1=99`, `M2=100`, `M3=100`, `S1=100`, `M4=100`, `M5=100`, `M6=100`, `M7=100`, `M8=95`) | `9/9` PASS, Health $\ge 90$ | **PASS** |
| **Gate 4a — Multi-Turn (`50` sessions / `222` turns)** | Intent **`98.65%`** (`219/222`), **Retrieval Status `93.24%`** (`207/222`, **+3.15%** vs Baseline `90.09%`), ARR **`98.94%`** (`93/94`), SRP **`100.00%`** (`15/15`), Multi-Grounding TS **`88.74%`** (`197/222`, +3.15% vs Baseline `85.59%`), Budget **`100.00%`** (`894/2400` chars), Mean Latency `1325.26ms` | Intent $\ge 94.0\%$, **Status $\ge 90.0\%$**, ARR $\ge 97.0\%$, SRP $= 100\%$ | **PASS** |
| **Gate 4b — Stage 11 Golden 200** | Router **`93.0%`** (`186/200`), CRAG **`87.0%`** (`174/200`), **Timestamp Multi-Grounding `86.0%`** (`172/200`), Strict TS `80.5%` (`161/200`), Avg Latency `1368.2 ms` | Router $\ge 90.5\%$, CRAG $\ge 86.0\%$, **TS Safety $\ge 86.5\%$** | **FAIL (`TS Safety 86.0% < 86.5%`)** |

---

## 2. Kiểm toán Liêm chính Mã nguồn & Chống Quick-Fix (`git diff`)

1. **`app/` & `data/`:**
   - **Zero Regex Runtime & Zero Snooping:** Static scan `git diff app/` xác nhận `0` lệnh `import re` / `from re import`, `0` literal `BENCH-` / `SESSION-`, `0` hardcode từ khóa đề thi.
   - **Khắc phục `RC-L2-03`:** Khối `except Exception: pass` ở nhánh Revision Non-Dominance Shield đã được sửa thành `logger.debug(...)` tại [`app/services/retrieval.py#L2244-L2245`](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2244-L2245).
   - **Data Integrity:** `data/curriculum/lessons_manifest.json` và `data/curriculum/syllabus_embeddings.npz` giữ nguyên `0` thay đổi. `data/metadata/router_intent_manifest.json` chỉ tách cấu hình `temporal_nli_*`.
2. **`tests/`:**
   - `git diff tests/` sạch (`0` thay đổi trên các suite hiện có, `0` `@pytest.mark.skip`, `0` `assert True`, `0` nới lỏng assertion).
   - [`tests/test_spec004_unified_workflow_hardening.py`](file:///D:/In_Course_Agentic_RAG_Copilot/tests/test_spec004_unified_workflow_hardening.py) chạy đủ **14/14 PASSED** (`10` test V1 + `4` test V2 cho `C8-v2`, `C11a`, `C11b`, `C12`), `0` benchmark IDs, `0` sao chép nguyên văn đề thi.
3. **`scripts/`:**
   - **Khắc phục `RC-L2-04`:** [`scripts/master_autonomous_harness.py#L375-L388`](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/master_autonomous_harness.py#L375-L388) đã đăng ký `"tests/test_spec004_unified_workflow_hardening.py"` vào `SEQUENTIAL_PYTEST_SUITES` (`12` suites tuần tự). *(Ghi chú nhỏ không gây lỗi: chuỗi banner/tóm tắt ở `#L598, L623` vẫn in `"11"`.)*
   - Toàn bộ ngưỡng Quality Gates trong [`scripts/thinker_doer_pipeline.py`](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/thinker_doer_pipeline.py) giữ nguyên (`Status >= 90.0%`, `TS Safety >= 86.5%`), không bị nới lỏng.

---

## 3. Đối chiếu Pre/Post & Truy vết Nguyên nhân Thất bại Vòng #2

### 3.1. Các hạng mục đã hội tụ hoàn toàn ở Vòng #2
- **Multi-Turn Retrieval Status (`PC-07`):** Tăng từ `90.09%` (Baseline) / `89.64%` (V1) lên **`93.24% (207/222)`** (+7 lượt cải thiện so với Baseline: `SESSION-CORE-09 T3`, `SESSION-OOP-12 T3`, `SESSION-SOCRATIC-16 T3`, `SESSION-STRESS-42 T2`, `SESSION-STRESS-47 T3`, `SESSION-STRESS-49 T4`, `SESSION-STRESS-49 T5`; `0` lượt hồi quy `status_ok`; `SESSION-STRESS-45 T2` giữ ổn định `grounded`).
- **Stage 11 `BENCH-037` (`C8-v2` / `PC-05a`):** Đã khôi phục hoàn toàn về `grounded`, trả chunk `code_ast` `function_thamChieu` (`score=0.3391`, `approx_video_sec=5750`, `lesson_seq=7`) $\rightarrow$ `in_scope` `ts_ok` phục hồi từ `71/80` lên **`72/80`** (khớp Baseline).

### 3.2. Nguyên nhân gốc duy nhất khiến Stage 11 TS Safety vẫn `86.0% (172/200) < 86.5%`
- **Ca hồi quy mới xuất hiện ở Vòng #2:** `BENCH-135` (`adversarial_hybrid`, `cpp-core`, `lesson_seq=3`): *"Toán tử tiền tố ++x có làm tăng tiền lương của tôi ngay trong tháng này không?"* (nhãn kỳ vọng: `intent="out_of_scope"`, `status="coverage_gap"`, `has_timestamp=False`).
- **Đối chiếu Baseline & V1 vs V2:**
  - **Baseline (`18:42:23`) & V1 (`19:19:05`):** `router_ok=False` (`course_query`), nhưng `actual_status="coverage_gap"`, `has_timestamp=False`, `chunks=[]` $\rightarrow$ `status_ok=True`, `ts_ok=True`.
  - **V2 (`20:21:18`):** `router_ok=False` (`course_query`), **`actual_status="grounded"`**, **`has_timestamp=True`**, **`video_sec=1275`** $\rightarrow$ `status_ok=False`, `ts_ok=False` (làm CRAG Precision giảm `87.5% -> 87.0%`, Timestamp Safety bị kẹt tại `172/200 = 86.0%`).
- **Bằng chứng truy xuất trực tiếp tại V2 (`BENCH-135`):**
  - `_sort_rrf_points_deterministically(raw_candidates, prefer_earlier_seq=False)` trước NMS ([`app/services/retrieval.py#L1817`](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L1817)) đưa chunk `video_transcript` `438cd872-ab61-5fe4-8d06-f795395041b5` (`lesson_seq=3`, `start_sec=1275`, `confidence_score=0.1831`, `raw_semantic_score=0.1755`) lọt vào `candidate_items` của Bài 3.
  - Vì `IntentRouter` phân loại nhầm câu ẩn dụ đời sống này thành `course_query` thay vì `out_of_scope` **VÀ** nhánh Tầng 3 Điều kiện 2 ([`app/services/retrieval.py#L2405-L2411`](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2405-L2411)) cho phép `is_curr_foundational` kích hoạt `grounded` chỉ với `confidence_score >= 0.18` (`0.1831 >= 0.18`) và `raw_semantic_score >= 0.16` (`0.1755 >= 0.16`), câu hỏi ngoài lề thuần túy bị ghép gượng vào đoạn giảng `++A` ở phút `21:15` (`1275s`).

---

## 4. Kết luận & Yêu cầu Chỉnh sửa cho Vòng #3 (Zero Quick-Fix)

1. Tuyệt đối **KHÔNG** đảo ngược `C8-v2` (đã cứu `BENCH-037`), `C11a/b`, `C12` (đã nâng Multi-Turn Status lên `93.24%`), hoặc dùng regex/từ khóa cá biệt cho `BENCH-135`.
2. Đề xuất xử lý theo **Lớp bài toán (Problem Class)** cho Vòng #3:
   - **Hướng chuẩn mực ở Layer 1 (`IntentRouter` / NLI Adversarial OOS Boundary)** và/hoặc **Layer 2 (Tier-3 Semantic Sufficiency cho câu hỏi chỉ khớp từ khóa kỹ thuật trong ngữ cảnh phi-lập-trình)**: Phân tích nguyên nhân vì sao 12 ca `adversarial_hybrid` (như câu hỏi kết hợp toán tử/từ khóa C++ với chủ đề đời sống ngoài lề: tiền lương, tình bạn, sắc đẹp, tua thời gian) lọt qua `IntentRouter` thành `course_query`, hoặc vì sao Tầng 3 (`raw_semantic_score ~ 0.17`) vẫn gắn `grounded` cho câu hỏi không có ý định học cú pháp.

VERDICT: REJECTED: Stage 1 Harness exit_code=1; although Multi-Turn Retrieval Status surged to 93.24% (207/222), Gate 2 passed 12/12 suites (110/110), E2E Matrix passed 9/9, and BENCH-037 was restored to 5750s, Stage 11 Timestamp Safety remained at 86.0% (172/200 < 86.5%) because deterministic current-window RRF sorting surfaced lesson 3 video_transcript chunk 438cd872 (confidence_score=0.1831, raw_semantic_score=0.1755) into Tier-3 Condition 2 (PARETO_THEORY_GROUNDING_FLOOR=0.18), flipping adversarial_hybrid BENCH-135 from coverage_gap to grounded (1275s) and dropping CRAG Precision from 87.5% to 87.0%.
