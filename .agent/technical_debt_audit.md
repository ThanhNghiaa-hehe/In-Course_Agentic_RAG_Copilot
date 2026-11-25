# BÁO CÁO KIỂM TOÁN NỢ KỸ THUẬT & PHÂN TÍCH NGUYÊN NHÂN GỐC TOÀN LUỒNG
## PSTACK NHỊP 1A — VÒNG LẶP #2 (SPEC 004): HẬU KIỂM HỒI QUY VÒNG #1 & KHÓA ĐỒNG BỘ LIÊN TẦNG

> **Hệ thống:** In-Course Agentic RAG Copilot — LangGraph Stateful Orchestration  
> **Sinh viên thực hiện:** Trần Thành Nghĩa (MSSV: `23DH112252`), Trường Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT)  
> **Vai trò:** `codebase-auditor` (theo [`.agents/agents/codebase-auditor.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agents/agents/codebase-auditor.md)) — **chế độ chỉ đọc trên `app/`, `specs/`, `tests/`, `scripts/`**  
> **Thời điểm kiểm toán:** `2026-11-25T19:52+07:00` | **Base Commit:** `5986d5d` + Working Tree Vòng #1 (`Spec 004` v1.0)  
> **Phạm vi truy vết liên tầng:** `IntentRouter → CurriculumService → RetrievalService → ChatGraph (retrieval_node / crag_grader_node / context_assembly_node) → ChatService → TelemetryCritic → MasterAutonomousHarness`  
> **Nguyên tắc bất biến:** Cross-Layer Unified Fix | `0%` Regex Runtime (`import re`) | `0%` Quick-Fix | `0%` Test-Set Snooping | `100%` Data-Inspected Verification

---

## 0. TÓM TẮT ĐIỀU HÀNH VÒNG #2 (EXECUTIVE AUDIT SUMMARY)

Vòng #1 của Spec 004 đã giải quyết thành công **toàn bộ Cụm B (`M6-T03 -> L43`, `M7-T02 -> L54`, `M8-T03 -> L58`)** đưa `E2E Matrix` lên **`9/9` suites PASS (`all_passed: true`, Health `99..100/100`)** và giữ `0%` regex / `0%` test-set snooping. Tuy nhiên, **Deterministic Harness Stage 1 trả `exit_code = 1`** do **2 cổng định lượng bị trượt sát biên 1 ca** và **2 lỗi vệ sinh/đăng ký harness**:

| Mã | Hạng mục Kiểm toán Vòng #2 | Hiện trạng Vòng #1 | Nguyên nhân gốc toàn luồng (Đã chứng minh thực nghiệm) | Mức độ |
|---|---|---|---|---|
| **RC-L2-01** | **Stage 11 Timestamp Safety trượt cổng (`86.0% < 86.5%`)** | `173/200 (86.5%)` → **`172/200 (86.0%)`**; Strict TS `81.0%` → `80.5%` (duy nhất ca `BENCH-037` tại `L7`) | **Bất đối xứng lắp ghép đa phương thức giữa Tầng 1/2 và Tầng 3 (`PC-05a` quá tay):** Tại [retrieval.py#L2349-L2389](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2349-L2389), Tầng 3 dùng `max_current_score = 0.3391` (từ `code_ast` `function_thamChieu` có Ground-Truth `approx_video_sec = 5750`) để mở cổng `max_current_score >= 0.25`, và đã có `5` `video_transcript` hợp lệ (`0.1872 @ 495s`), nhưng lại **vứt bỏ hoàn toàn `assemble_balanced_modality`** nên đánh mất mốc Phase-2 Ground-Truth `5750s` (khác hẳn Tầng 1 [#L1992-L2008](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L1992-L2008) & Tầng 2 [#L2288-L2304](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2288-L2304)). | **P0** |
| **RC-L2-02** | **Multi-Turn Retrieval Status trượt cổng (`89.64% < 90.0%`) & Biên an toàn `0` lượt** | Baseline `200/222 (90.09%)` → Vòng #1 **`199/222 (89.64%)`** (`SESSION-STRESS-45 T2` tại `L7` lật `grounded → out_of_lesson L37`) | **Tổ hợp 3 lỗi cấu trúc liên tầng (KHÔNG phải nhiễu ngẫu nhiên đơn thuần):**<br>1. **Lỗi bất định thứ tự hòa điểm RRF (`RRF Tie-Break Non-Determinism`)** tại [retrieval.py#L478-L481](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L478-L481) & [#L659-L660](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L659-L660): Qdrant cắt `limit=10` trước khi NMS deduplicate; 2 lần gọi liên tiếp cùng đầu vào lúc có `Seq 28 (0.3488)` → `grounded`, lúc mất `Seq 28` còn `Seq 37 (0.4014)` → `out_of_lesson` (§3.2).<br>2. **Lỗi tín hiệu bài tương lai không đồng thuận (`Unverified Future Topic Signal`)** tại [retrieval.py#L1499-L1506](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L1499-L1506) & [#L2070-L2080](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2070-L2080): (i) `curriculum_matched_course != course_id` gắn nhãn nhầm bài cũ của `cpp-core` (`seq 1..52`) thành "tương lai" khi học viên đang ở `cpp-oop` (`seq 53..83`); (ii) `is_future_curriculum_target` đơn phương tắt `active_continuation_shield` và Tầng 3 ngay cả khi `CurriculumService` (`L43`) và Qdrant Prober (`L37`) **bất đồng hoàn toàn (`matched != target`)** và `target_has_topical_match=False`.<br>3. **Điểm mù đại từ hồi chỉ bị cướp sang `out_of_lesson` ở `retrieval_node`** tại [chat_graph.py#L764-L788](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L764-L788): Câu nối tiếp có đại từ (`"qua nó"`, `"xóa bộ đệm thì nó"`, `"thoát khỏi nó"`, `"ở trong đó"`) bị `raw_prompt` đẩy nhầm sang `out_of_lesson` không đồng thuận syllabus, nên `retrieval_node` không bao giờ thử `search_query` dù `search_query` đạt **Tier-1 Grounded `0.52–0.57`**! | **P0** |
| **RC-L2-03** | **Vi phạm vệ sinh ngoại lệ im lặng (`except Exception: pass`)** | Xuất hiện mới trong diff Vòng #1 | Tại [retrieval.py#L2199-L2200](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2199-L2200) (nhánh `Revision Non-Dominance Shield` của Pareto 3A-2), khối `except Exception:\n pass` nuốt lỗi không ghi `logger.debug(...)`. | **P1** |
| **RC-L2-04** | **Thiếu đăng ký bộ test Spec 004 vào Harness Gate 2** | `SEQUENTIAL_PYTEST_SUITES` chỉ chạy `11` suites cũ (`96` tests) | [scripts/master_autonomous_harness.py#L375-L387](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/master_autonomous_harness.py#L375-L387) chưa thêm `"tests/test_spec004_unified_workflow_hardening.py"`, khiến Gate 2 không tự động khóa hồi quy các ca Spec 004. | **P1** |

> [!IMPORTANT]
> **Bảo toàn thành quả Vòng #1 & Baseline chuẩn:**
> 1. Bản chụp Baseline tại `HEAD 5986d5d` đã được lưu đầy đủ ở `scratch/spec004_baseline/` (`2026-11-25 18:37–18:47`). **TUYỆT ĐỐI KHÔNG ghi đè `scratch/spec004_baseline/` ở Vòng #2** (tiết kiệm 35 phút và giữ nguyên mốc Pre-Optimization trung thực tại `5986d5d`).
> 2. Toàn bộ logic `PC-01` (`nav_label_verified_in_window`, `Pareto 3A-2`, `is_ce_resolved_future_nav`), `PC-02` (`or -> and` & `temporal_nli` fail-closed), `PC-04` (`_compute_calibrated_rrf_norm` & degraded `[0.15, 0.29]`), `PC-05b/c` (`is_approximate=True` cho lightweight chunk & chống lặp dòng `📍`), và `PC-06` (`TelemetryCritic`) đang hoạt động chính xác — **giữ nguyên, không đảo ngược**.

---

## 1. ĐỐI CHIẾU ĐỊNH LƯỢNG PRE/POST TOÀN BỘ 3 BỘ CHUẨN (DATA-INSPECTED)

Nguồn đối chiếu trực tiếp:
- Baseline (`HEAD 5986d5d`): `scratch/spec004_baseline/{latest_benchmark_results,multiturn_benchmark_results,e2e_matrix_latest_summary}.json`
- Vòng #1 Post-Fix: [`docs/benchmarks/latest_benchmark_results.json`](file:///D:/In_Course_Agentic_RAG_Copilot/docs/benchmarks/latest_benchmark_results.json), [`docs/benchmarks/multiturn_benchmark_results.json`](file:///D:/In_Course_Agentic_RAG_Copilot/docs/benchmarks/multiturn_benchmark_results.json), [`logs/playground_debug/e2e_matrix_latest_summary.json`](file:///D:/In_Course_Agentic_RAG_Copilot/logs/playground_debug/e2e_matrix_latest_summary.json), [`.agent/harness_stage1_latest.log`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/harness_stage1_latest.log).

| Bộ kiểm chuẩn | Chỉ số | Baseline (`5986d5d`) | Vòng #1 (`Post-Fix`) | Ngưỡng Cổng Spec 004 | Chênh lệch & Đánh giá |
|---|---|---:|---:|---:|---|
| **Gate 2 — Sequential Pytest** | Suites / Tests | `11/11` (`96/96`) | `11/11` (`96/96`) + `10/10` riêng | `100% PASS` | ✅ Đạt (cần đăng ký suite thứ 12 vào Harness) |
| **Gate 3 — E2E Matrix (`9` suites)** | `all_passed` (`M1..M3, S1, M4..M8`) | `false` (`6/9`: trượt `M6, M7, M8`) | **`true` (`9/9` PASS)** | `true` (`9/9`) | ✅ **Hội tụ hoàn toàn Cụm B** (`M6->43`, `M7->54`, `M8->58`) |
| | Critic Health Score | `95..100` | **`99..100`** | `>= 90` | ✅ Đạt |
| **Gate 4a — Multi-Turn (`50` phiên / `222` lượt)** | Intent Accuracy | `98.65%` (`219/222`) | **`98.65%` (`219/222`)** | `>= 94.0%` | ✅ `0` đổi |
| | **Retrieval Status Accuracy** | `90.09%` (`200/222`) | **`89.64%` (`199/222`)** | **`>= 90.0%` (`>= 200/222`)** | ❌ **FAIL `-1` lượt (`SESSION-STRESS-45 T2`)** |
| | Anaphora Resolution (`ARR`) | `98.94%` (`93/94`) | **`98.94%` (`93/94`)** | `>= 97.0%` | ✅ `0` đổi |
| | Socratic Refusal (`SRP`) | `100.00%` (`15/15`) | **`100.00%` (`15/15`)** | `= 100.0%` | ✅ `0` đổi |
| | Context Budget (`<= 2400` chars) | `100.00%` (`max 894`) | **`100.00%` (`max 894`)** | `= 100.0%` | ✅ `0` đổi |
| | Mean Latency | `1428.48 ms` | **`1360.74 ms`** | `<= 7500 ms` | ✅ Nhanh hơn `67.7 ms` |
| **Gate 4b — Stage 11 Golden `200`** | Router Accuracy | `93.0%` (`186/200`) | **`93.0%` (`186/200`)** | `>= 90.5%` | ✅ `0` đổi (`199/200` ca y hệt bit-for-bit về cờ) |
| | CRAG Grader Precision | `87.5%` (`175/200`) | **`87.5%` (`175/200`)** | `>= 86.0%` | ✅ `0` đổi |
| | **Timestamp Safety (Multi-Grounding)** | `86.5%` (`173/200`) | **`86.0%` (`172/200`)** | **`>= 86.5%` (`>= 173/200`)** | ❌ **FAIL `-1` ca (`BENCH-037`)** |
| | Strict Timestamp (Tier 1) | `81.0%` (`162/200`) | `80.5%` (`161/200`) | tham khảo | `-1` ca (cùng ca `BENCH-037`) |

---

## 2. PHÂN TÍCH NGUYÊN NHÂN GỐC #1 (`RC-L2-01`): VÌ SAO `PC-05a` VÒNG #1 LÀM RỚT TIMESTAMP SAFETY Ở TẦNG 3 (`BENCH-037`)

### 2.1. Bằng chứng truy vết từng bước trên mã nguồn & dữ liệu thực
Trên toàn bộ `200` ca của `Golden 200`, phép so sánh từng phần tử (`pass_flags` & `actual`) giữa Baseline (`18:42:23`) và Vòng #1 (`19:19:05`) xác nhận **199/200 ca giữ nguyên 100%**, chỉ duy nhất **1 ca thay đổi**:
- **Ca hồi quy:** `BENCH-037` (`in_scope`, `course_id="cpp-core"`, `lesson_seq=7`):
  - Truy vấn: *"Toán tử & trong định nghĩa tham số hàm void func(int &x) có tác dụng gì?"*
  - Đáp án chuẩn: `status="grounded"`, `target_video_sec = 5750`, `valid_video_intervals = [[1463, 1553], [5705, 5795]]`.
- **Phân phối điểm ứng viên thực tế tại `RetrievalService.hybrid_search` (`lesson_seq <= 7`):**
  1. Ứng viên `code_ast` tốt nhất thuộc **Bài 7**: `code_scope = "function_thamChieu"` (hàm chuyên biệt, **không** thuộc `BOILERPLATE_SCOPES`), `confidence_score = 0.3391` (`< 0.35 = CODE_SCORE_THRESHOLD`), mang liên kết Ground-Truth Phase 2 **`approx_video_sec = 5750`** (từ `data/metadata/code_video_bindings.json` tại [retrieval.py#L1745-L1750](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L1745-L1750)).
  2. Ứng viên `video_transcript` thuộc **Bài 7**: `5` phân đoạn trong dải Ambiguous `[0.15, 0.22)` dẫn đầu bởi `0.1872 @ 495s`, `0.1821 @ 5531s`, `0.1778 @ 2355s` (`max_video_score = 0.0` do `< 0.22`, `max_any_video_score = 0.1872`).
  3. Tại Tầng 2: bài tương lai (`L8`, `future_score = 0.2651`, `code_ast < 0.35`) không thống trị; vì `valid_video_items = []` và `valid_ast_items = []`, truy vấn đi xuống **Tầng 3 Graceful Degradation** ([retrieval.py#L2349-L2389](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2349-L2389)).
  4. Tại Tầng 3 Điều kiện 1 ([retrieval.py#L2350](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2350)):
     - `max_current_score = 0.3391 >= 0.25` (chính nhờ `code_ast` `function_thamChieu` của Bài 7!).
     - `low_confidence_items` lọc `content_type == "video_transcript"` thu được **5 video chunks hợp lệ của Bài 7** $\implies$ xác lập hợp lệ `status = "grounded"`.
  5. **Điểm gãy kiến trúc do bản vá `PC-05a` Vòng #1 gây ra ([retrieval.py#L2368-L2375](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2368-L2375)):**
     - Ở **Tầng 1** ([#L1992-L2008](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L1992-L2008)) và **Tầng 2** ([#L2288-L2304](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2288-L2304)), sau khi `video_transcript` đã bảo chứng trạng thái `grounded`, hệ thống luôn thu thập `eligible_code_items` cùng `current_lesson_seq` (`confidence_score >= 0.15`) và ghép qua `assemble_balanced_modality(..., prefer_balanced=bool(eligible_code_items))` để bảo toàn **Phase 2 Code-to-Video Metadata Binding (`approx_video_sec`)** cho cả `crag_grader_node` ([chat_graph.py#L1023-L1030](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L1023-L1030)) lẫn `run_rag_benchmark.py` ([#L202-L203](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/run_rag_benchmark.py#L202-L203)).
     - Ngược lại, ở **Tầng 3**, Vòng #1 viết `top_low_conf = sorted(low_confidence_items, ...)[:final_top_k]` chỉ lấy `video_transcript` thuần túy, loại bỏ hoàn toàn `function_thamChieu (0.3391, approx_video_sec=5750)`. Hệ quả: `chunks` chỉ còn `3` video điểm thấp (`0.1872 @ 495s`, `0.1821 @ 5531s`, `0.1778 @ 2355s`), đều trượt cả Tier 1 Strict (`[5705, 5795]`) lẫn Tier 2 Multi-Grounding (`0.1872 < 0.22` tại [run_rag_benchmark.py#L265-L266](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/run_rag_benchmark.py#L265-L266))!

### 2.2. Giải pháp Chuẩn Kiến trúc cho Nhịp 1B (0% Quick-Fix, Bảo toàn 100% `PC-05a`)
Tách bạch rạch ròi **Cổng Quyết Định Trạng Thái (`Decision Gate`)** và **Cổng Đóng Gói Đa Phương Thức (`Balanced Modality Context & Binding Assembly`)** ở Tầng 3:
1. **Giữ nguyên 100% Cổng Quyết Định `PC-05a`:**
   - `grade_document_relevance` ([retrieval.py#L315](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L315)) giữ nguyên `settings.CODE_SCORE_THRESHOLD (0.35)` cho `code_ast`.
   - `low_confidence_items` ([retrieval.py#L2351-L2366](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2351-L2366)) **chỉ** xét `content_type == "video_transcript"`. Nếu không có `video_transcript` nào đạt chuẩn CRAG Ambiguous (`low_confidence_items == []`), hệ thống **bắt buộc trả `coverage_gap`** (chặn tuyệt đối `code_ast` điểm `< 0.35` tự kích hoạt `grounded`, giữ xanh test `PC-05a`).
2. **Đồng bộ `assemble_balanced_modality` cho Phase-2 Bound Code AST khi `low_confidence_items` đã hợp lệ:**
   - Khi và chỉ khi `bool(low_confidence_items)` đã đạt chuẩn `grounded`, thu thập `tier3_bound_code_items` gồm các ứng viên `code_ast` thỏa mãn đồng thời 4 điều kiện nghiêm ngặt:
     - `int(it.get("lesson_seq") or 0) == int(current_lesson_seq)` (đúng bài hiện tại, không kéo bài cũ),
     - `(it.get("code_scope") or "") not in BOILERPLATE_SCOPES` (loại bỏ `header_preamble`, `function_main`, `type_class_specifier` nhiễu),
     - `it.get("approx_video_sec") is not None` (có mốc Ground-Truth Phase 2 đã kiểm chứng trong manifest),
     - `it.get("confidence_score", 0.0) >= settings.VIDEO_FALLBACK_MIN_THRESHOLD` (`>= 0.15`).
   - Đóng gói qua `assemble_balanced_modality(video_items=low_confidence_items, code_items=tier3_bound_code_items, final_top_k=final_top_k, prefer_balanced=bool(tier3_bound_code_items))` rồi `reorder_lost_in_the_middle(...)`.
3. **Kiểm chứng tác động chéo trên toàn bộ 200 ca `Golden 200`:**
   - Quét toàn bộ `200` ca trong `latest_benchmark_results.json` chỉ có đúng `2` ca rơi vào Tầng 3 (`BENCH-027` tại `L6` không có `code_ast` khớp và `BENCH-037` tại `L7`).
   - Không có bất kỳ ca `coverage_gap` / `adversarial_hybrid` nào bị mở thêm (vì cổng `if low_confidence_items:` không đổi), trong khi `BENCH-037` khôi phục mốc Ground-Truth `5750s` (`ts_strict_ok: True`, `ts_ok: True`), đưa **Stage 11 Timestamp Safety trở lại `86.5% (173/200)` (PASS)** và **Strict TS lên `81.0% (162/200)`**.

---

## 3. PHÂN TÍCH NGUYÊN NHÂN GỐC #2 (`RC-L2-02`): VÌ SAO MULTI-TURN STATUS LẬT Ở `SESSION-STRESS-45 T2` & 3 LỖI CẤU TRÚC LIÊN TẦNG

### 3.1. Bằng chứng sống: Hiện tượng bất định giữa 2 lần gọi liên tiếp trên cùng 1 truy vấn
Khi chạy probe trực tiếp `RetrievalService.hybrid_search` hai lần liên tiếp cách nhau `2 giây` trên cùng câu `SESSION-STRESS-45 T2` (`lesson_seq = 7`, `is_continuation_turn = True`, *"Khi hàm kết thúc thì biến cục bộ trong stack frame của nó được giải phóng ra sao?"*):
- **Lần gọi #1:** `_fetch_future_points` (`limit = 10`) trả về `10` ứng viên tương lai không có `Bài 28` → `_score_future_points` chọn `target_seq = 37` (`future_score = 0.4014`, `margin = +0.1022`) → **`out_of_lesson` (FAIL)**.
- **Lần gọi #2 (cùng tham số 100%):** `_fetch_future_points` (`limit = 10`) trả về `[(37, 'vid', 0.7), ..., (28, 'vid', 0.3333), ...]` có mặt `Bài 28` (`Score = 0.3488 >= 0.30`) → `Prerequisite Order Invariant` chọn `earliest_seq = 28` (`future_score = 0.3488`, `margin = +0.0496 < margin_req 0.0998`) → **`grounded` tại Bài 7 (`5662s`, PASS)**!

Đây cũng chính là nguyên nhân khiến `20` lượt trong `Multi-Turn` có sự xê dịch nhẹ thứ tự `suggested_timestamps` giữa hai lần chạy (`CORE-07 T1`, `SWITCH-34 T1`, `STRESS-44 T2`, `STRESS-45 T2`).

### 3.2. Bóc tách 3 Lỗi Cấu trúc Liên Tầng tạo nên Hồi quy Multi-Turn

#### Lỗi 3.2A — Cắt cụt trước khử trùng lặp & Hòa điểm RRF không tất định (`RRF Tie-Break Non-Determinism`)
- **Vị trí:** [app/services/retrieval.py#L478-L481](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L478-L481), [#L659-L660](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L659-L660), [#L1620-L1622](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L1620-L1622), [#L1715-L1720](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L1715-L1720).
- **Cơ chế lỗi:**
  1. `_fetch_future_points` phát `4` nhánh prefetch (`12 + 6 + 4 + 4 = 26` điểm) nhưng đặt `limit = settings.FUTURE_PROBE_LIMIT (10)` ngay trên Qdrant `Fusion.RRF` **trước khi** chạy `deduplicate_temporal_candidates`. Trên `STRESS-45 T2`, riêng Bài 37 chiếm `5/10` vị trí bởi các đoạn video gối đầu nhau, đẩy các bài tiên quyết phía trước (`Bài 28`) ra rìa cắt `limit = 10`.
  2. Trong công thức RRF $\sum \frac{1}{2 + r}$, các ứng viên cùng hạng ở các nhánh khác nhau có điểm RRF **bằng nhau tuyệt đối** (`0.5000`, `0.3333`, `0.2500`, `0.2000`, `0.1667`). Trên Qdrant Cloud đa phân mảnh, thứ tự giữa các điểm hòa RRF thay đổi theo độ trễ replica nếu client không chuẩn hóa khóa sắp xếp thứ cấp tất định!
- **Hướng khắc phục cấu trúc:**
  - Nâng `limit` truy vấn RRF thô trong `_fetch_future_points` lên `max(settings.FUTURE_PROBE_LIMIT * 2, 20)` (chỉ tăng truyền JSON metadata vài KB trong cùng 1 HTTP request, **không** tăng số lượng tài liệu đưa vào CPU Cross-Encoder vì sau `deduplicate_temporal_candidates` vẫn cắt `[:settings.FUTURE_PROBE_LIMIT]`).
  - Áp dụng khóa sắp xếp tất định `(-round(float(hit.score), 6), int((hit.payload or {}).get("lesson_seq") or 9999), str(hit.id))` trước khi chạy `deduplicate_temporal_candidates` ở cả `hybrid_search` và `_score_future_points` (khi hòa điểm RRF, ưu tiên bài có `lesson_seq` nhỏ hơn đúng tinh thần *Prerequisite Order Pareto Invariant*).

#### Lỗi 3.2B — Lỗi Ngược Chiều Khóa Học ở `is_future_curriculum_target` & Tín hiệu Tương lai Đơn phương Không Đồng thuận (`Unverified Future Topic Signal`)
- **Vị trí:** [app/services/retrieval.py#L1499-L1506](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L1499-L1506), [#L2070-L2080](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2070-L2080), [#L2350-L2366](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2350-L2366).
- **Bằng chứng dữ liệu (`lessons_manifest.json` & Probe §3):**
  1. Toàn bộ `83` bài học đánh số `seq` **đơn điệu toàn cục duy nhất**: `cpp-core` = `1..52` (`52` bài), `cpp-oop` = `53..83` (`31` bài). Thế nhưng dòng `1503` viết:
     ```python
     (curriculum_matched_course is not None and curriculum_matched_course != course_id)
     or (curriculum_matched_seq is not None and curriculum_matched_seq > current_lesson_seq)
     ```
     Khi học viên đang học **`cpp-oop` Bài 53**, nếu câu hỏi nối tiếp khớp về bài nền tảng **`cpp-core` Bài 6 hoặc Bài 18** (`STRESS-49 T5 -> L6`, `OOP-12 T3 -> L18`), điều kiện `curriculum_matched_course != course_id` biến **bài quá khứ (`6 < 53`, `18 < 53`)** thành `is_future_curriculum_target = True`! *(Lưu ý: `NavBypass` ở [#L1659-L1661](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L1659-L1661) dùng điều kiện riêng cho `is_curriculum_navigation=True` nên giữ nguyên để hỗ trợ điều hướng xuyên khóa).*
  2. Dòng `2070–2073` đặt `has_future_topic_signal = bool(is_future_curriculum_target or (... and target_has_topical_match))`. Khi học viên đang hội thoại nối tiếp (`is_continuation_turn = True`), một từ vựng phụ trong câu (`"stack"` trong *"stack frame"* của hàm Bài 7 ở `STRESS-45 T2`; `"xóa bộ đệm"` ở `CORE-09 T3`; `"x += 5"` ở `STRESS-42 T2`) làm `CurriculumService` đoán nhầm một bài tương lai (`L43`, `L27`, `L5`), trong khi Qdrant Chunk Prober lại trỏ sang bài hoàn toàn khác (`target_seq = 37`, `46`, `4`) với `target_has_topical_match = False`!
  3. Dù hai tầng **bất đồng hoàn toàn (`curriculum_matched_seq != target_seq`)** và không có từ khóa chủ đề của `target_seq`, cờ `has_future_topic_signal = True` vẫn **tắt sạch `active_continuation_shield`** ([#L2074-L2080](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2074-L2080)) và **khóa luôn Tầng 3 Graceful Degradation** ([#L2350, #L2360](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2350))!
- **Đối chứng với các ca `out_of_lesson` thật sự (`M4-T02`, `S1-T06`, `S1-T07`, `SWITCH-31..40`, `Golden 200`):**
  - `M4-T02` (`L7 -> L8`): `matched_seq = 8 == target_seq = 8` **VÀ** `future_chunk_type == "code_ast"` (`0.4854`).
  - `S1-T06` (`L2 -> L3`): `matched_seq = 3 == target_seq = 3` **VÀ** `max_current_score < 0.22`.
  - `S1-T07` (`L2 -> L43`): `matched_seq = 43 == target_seq = 43` **VÀ** `target_has_topical_match = True`.
  - `Golden 200` (`200` ca đơn lượt): `is_continuation_turn = False` trên cả `200/200` ca!
  $\implies$ Yêu cầu **Đồng thuận Tương lai Liên tầng (`Cross-Layer Future Topic Consensus`)** cho lượt nối tiếp (`curriculum_matched_seq > current_lesson_seq` VÀ (`target_seq == curriculum_matched_seq` HOẶC `target_has_topical_match` HOẶC `max_current_score < 0.22`)) bảo toàn **100%** `M4-T02`, `S1-T06`, `S1-T07`, `SWITCH-31..40`, `Golden 200`, đồng thời giải cứu tức thì `STRESS-45 T2`, `CORE-09 T3`, `STRESS-42 T2`, `STRESS-49 T5`!

#### Lỗi 3.2C — Đại từ Hồi chỉ bị Cướp sang `out_of_lesson` ở `ChatGraph.retrieval_node` (`Anaphoric False-OOL Hijack`)
- **Vị trí:** [app/services/chat_graph.py#L763-L790](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L763-L790).
- **Bằng chứng thực nghiệm từ Probe §4 (`raw_prompt` vs `search_query` đã qua `Topic Shift Isolation Gate`):**

| Phiên & Lượt | `raw_prompt` (thiếu chủ ngữ do đại từ `"nó"`/`"đó"`) | Kết quả `raw_prompt` | Điểm Top Chunks Bài Hiện Tại khi chạy `search_query` |
|---|---|---|---|
| `SESSION-CORE-09 T3` (`L18`) | *"Nếu không xóa bộ đệm thì **nó** sẽ nuốt ký tự enter đúng không?"* | `out_of_lesson` (`target=46`, `matched=27`) ❌ | **`0.5206`, `0.4730`, `0.4077` (Bài 18 — Tier 1 Grounded!)** |
| `SESSION-OOP-12 T3` (`L53`) | *"Cú pháp truy cập qua **nó** là dùng dấu chấm hay dấu mũi tên ->?"* | `out_of_lesson` (`target=57`, `matched=18 <= 53`) ❌ | **`0.5744`, `0.5405`, `0.4607` (Bài 53 — Tier 1 Grounded!)** |
| `SESSION-STRESS-44 T2` (`L6`) | *"Làm sao để thoát khỏi **nó** khi người dùng chọn lệnh thoát chương trình?"* | `out_of_lesson` (`target=78/33`, `matched!=target`) ❌ | **`0.3414`, `0.3238` (Bài 6 — Grounded!)** |
| `SESSION-STRESS-49 T4` (`L53`) | *"Nếu trong class có con trỏ cấp phát động new thì ta giải phóng delete **ở trong đó** đúng không?"* | `out_of_lesson` (`target=57`, `matched=53 <= 53`) ❌ | **`0.5369` (video), `0.4431` (code_ast), `0.4156` (Bài 53 — Tier 1 Grounded!)** |

- **Nguyên nhân gốc:** Dòng `764` chỉ kích hoạt Contextual Fallback khi `retrieval_res.status == "coverage_gap" or retrieval_res.is_low_confidence`. Khi câu hỏi có đại từ hồi chỉ (`search_query != raw_prompt`, tức `router_node` đã xác minh `is_context_dependent=True` và `not is_topic_shift`), phần vị ngữ cụt chủ ngữ (`"dấu mũi tên ->"`, `"delete ở trong đó"`) bị đẩy nhầm sang `out_of_lesson` **không có đồng thuận syllabus** (`retrieval_res.curriculum_matched_seq != retrieval_res.target_lesson_seq`), nên `retrieval_node` không bao giờ đối chiếu với `search_query`!
- **Rào chắn chống xung đột với `M4-T02` / `S1-T06` / `S1-T07`:**
  Chỉ cho phép Contextual Fallback kiểm tra thêm nhánh `out_of_lesson` khi đồng thời thỏa mãn **cả 3 điều kiện**:
  1. `search_query != raw_prompt` (đã qua `is_context_dependent` & `not is_topic_shift`),
  2. **Không có đồng thuận Syllabus–Chunk về bài tương lai:** `retrieval_res.curriculum_matched_seq != retrieval_res.target_lesson_seq` (nên `M4-T02` `8==8`, `S1-T06` `3==3`, `S1-T07` `43==43` **hoàn toàn không kích hoạt fallback**!),
  3. Kết quả `fallback_res` trên `search_query` đạt **`status == "grounded" and not fallback_res.is_low_confidence`** (bằng chứng tự tin cao ở cửa sổ bài hiện tại).
- **Tác động định lượng dự kiến:** Đưa `Multi-Turn Retrieval Status` từ `199/222 (89.64%)` lên vùng **`204–206 / 222 (~91.9%–92.8%)`**, tạo **đệm an toàn `+4..+6` lượt** trên ngưỡng `90.0%` (`200/222`), chấm dứt vĩnh viễn rủi ro trượt cổng do biên 1 lượt!

---

## 4. KIỂM TOÁN LIÊM CHÍNH MÃ NGUỒN, VỆ SINH CODE & ĐĂNG KÝ HARNESS

| Hạng mục Kiểm toán | Tệp & Dòng | Trạng thái | Chi tiết & Yêu cầu xử lý ở Vòng #2 |
|---|---|---|---|
| **Zero-Regex Runtime** | `git diff app/` | ✅ **PASS** | `0` lệnh `import re` / `from re import` / `re.*()` trong toàn bộ `app/`. |
| **Zero Test-Set Snooping** | `git diff app/ data/ tests/` | ✅ **PASS** | `0` chuỗi `BENCH-` / `SESSION-`; `lessons_manifest.json` và `syllabus_embeddings.npz` giữ nguyên `100%` (`0` diff); không sửa lùi bất kỳ test cũ nào. |
| **Data/Code Separation & CRAG Attribution** | `router.py`, `config.py`, `retrieval.py`, `chat_graph.py` | ✅ **PASS** | `temporal_nli_*` đã tách sang `router_intent_manifest.json`; 4 docstring CRAG đã chuẩn hóa thành `Yan et al. (Google DeepMind / USTC / UCLA, arXiv:2401.15884)`. |
| **Silent Exception (`RC-L2-03`)** | [app/services/retrieval.py#L2199-L2200](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2199-L2200) | ❌ **CẦN SỬA** | Đổi `except Exception:\n pass` thành `except Exception as rev_err:\n logger.debug(f"[RetrievalService:Pareto 3A-2] Lỗi kiểm tra is_revision_of: {rev_err}")`. |
| **Harness Suite Registration (`RC-L2-04`)** | [scripts/master_autonomous_harness.py#L375-L387](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/master_autonomous_harness.py#L375-L387) | ❌ **CẦN SỬA** | Bổ sung `"tests/test_spec004_unified_workflow_hardening.py"` vào `SEQUENTIAL_PYTEST_SUITES` (nâng Gate 2 lên `12` suites tuần tự) và cập nhật log/docstring tương ứng. |

---

## 5. MA TRẬN XUNG ĐỘT LIÊN TẦNG CẬP NHẬT CHO NHỊP 1B VÒNG #2 (`C11..C14`)

*(Giữ nguyên các mục `C1..C10` của Spec 004 v1.0 đã kiểm chứng xanh trên E2E Matrix `9/9`, bổ sung/cập nhật 4 ràng buộc chống hồi quy cho Vòng #2):*

| Mã | Thay đổi đồng bộ Vòng #2 | Router | Curr | Retr | Graph | Harness | Nguy cơ xung đột chéo tiềm ẩn | Cơ chế khóa an toàn bắt buộc trong Spec v2.0 | Bộ kiểm chứng bắt buộc |
|---|---|:---:|:---:|:---:|:---:|:---:|---|---|---|
| **C8-v2** | Tầng 3 giữ cổng quyết định `video_transcript`-only nhưng ghép `tier3_bound_code_items` (`lesson_seq==current`, non-boilerplate, `approx_video_sec!=None`, `>=0.15`) qua `assemble_balanced_modality` (`RC-L2-01`) | — | — | ● | ○ | — | (1) `code_ast` rác `< 0.35` tự kích hoạt `grounded` khi không có video.<br>(2) Kéo `function_main` hoặc bài cũ vào Tầng 3 làm sai timestamp. | (1) Cổng `if low_confidence_items:` **chỉ** xét `video_transcript` → `0` video thì vẫn trả `coverage_gap` 100%.<br>(2) Ràng buộc chặt `lesson_seq == current_lesson_seq`, `code_scope not in BOILERPLATE_SCOPES`, `approx_video_sec is not None`. | `BENCH-037` PASS (`5750s`), Golden TS Safety `>= 86.5%`, unit test `PC-05a` (code-only `< 0.35` -> `coverage_gap` **và** video Ambiguous + bound AST -> bảo toàn `approx_video_sec`) |
| **C11** | Sửa `is_future_curriculum_target` (`seq > current`) + Đồng thuận `has_future_topic_signal` cho lượt nối tiếp + Sắp xếp RRF tất định & `limit` trước NMS (`RC-L2-02a/b`) | — | — | ● | — | — | Chặn nhầm các ca chuyển sang bài tương lai thật sự trong hội thoại (`M4-T02`, `S1-T06`, `S1-T07`, `SWITCH-31..40`, `Golden 200` `out_of_lesson`). | (1) Giữ nguyên `NavBypass` xuyên khóa cho `is_curriculum_navigation=True`.<br>(2) `has_future_topic_signal` vẫn `True` khi `target_has_topical_match=True` HOẶC `target_seq == curriculum_matched_seq` (`M4-T02` `8==8`, `S1-T06` `3==3`, `S1-T07` `43==43`) HOẶC `max_current_score < 0.22`.<br>(3) Chỉ thu hẹp tín hiệu không đồng thuận khi `is_continuation_turn=True` (`0%` chạm `Golden 200` đơn lượt). | `STRESS-45 T2` `grounded` ổn định qua nhiều lần chạy liên tiếp; `M4-T02 -> 8`, `S1-T06 -> 3`, `S1-T07 -> 43`, `SWITCH-31..40` `10/10` PASS; Golden `out_of_lesson` `39/40` không giảm |
| **C12** | `retrieval_node` cứu xét `out_of_lesson` thiếu đồng thuận syllabus bằng `search_query` khi đạt `grounded` tự tin cao (`RC-L2-02c`) | ○ | — | ○ | ● | — | Gộp `anchor_query` vào câu hỏi bài mới (`M4-T02`, `S1-T06`) làm kéo ngược `out_of_lesson` về `grounded` bài cũ. | **Cổng chặn cứng kép:** Chỉ chạy khi `search_query != raw_prompt` **VÀ** `retrieval_res.curriculum_matched_seq != retrieval_res.target_lesson_seq` **VÀ** nhận kết quả chỉ khi `fallback_res.status == "grounded" and not fallback_res.is_low_confidence`. (`M4-T02`, `S1-T06`, `S1-T07` đều có `matched == target` nên bị chặn ngay từ cửa!). | `CORE-09 T3`, `OOP-12 T3`, `STRESS-44 T2`, `STRESS-49 T4` phục hồi `grounded`; `E2E Matrix 9/9` (`M4-T02`, `S1-T06`, `S1-T07`) PASS; Multi-Turn Status `>= 91.5%` |
| **C13** | Thay `except Exception: pass` bằng `logger.debug` (`RC-L2-03`) & đăng ký `test_spec004_unified_workflow_hardening.py` vào `SEQUENTIAL_PYTEST_SUITES` (`RC-L2-04`) | — | — | ● | — | ● | Tăng thời gian chạy Gate 2 thêm ~15s. | Chạy tuần tự cô lập cùng `offline_env` (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`), hoàn toàn an toàn trên RTX 2050 4 GB VRAM. | Gate 1 Anti-Bypass `0` vi phạm; Gate 2 `12/12` suites PASS (`100%`) |

---

## 6. THỨ TỰ THỰC THI KHUYẾN NGHỊ CHO NHỊP 1B & NHỊP 2 (VÒNG #2)

1. **Nhịp 1B (`rag-architect` & `solution-analyst`):**
   - Nâng cấp [`specs/004-unified-rag-workflow-hardening/spec.md`](file:///D:/In_Course_Agentic_RAG_Copilot/specs/004-unified-rag-workflow-hardening/spec.md) lên **v2.0** (và đồng bộ [`.agent/implementation_spec.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/implementation_spec.md), [`.agent/task_plan.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/task_plan.md)):
     - Giữ nguyên `PC-01..PC-04`, `PC-05b/c`, `PC-06` đã hội tụ.
     - Tinh chỉnh **`PC-05a` (`C8-v2`)**: Bổ sung `assemble_balanced_modality` cho `tier3_bound_code_items` sau cổng quyết định `low_confidence_items` của `video_transcript`.
     - Bổ sung **`PC-07` (`C11 + C12` — Cross-Layer Multi-Turn Continuation Stability & Deterministic RRF Tie-Breaking)**: Khóa công thức toán học cho `is_future_curriculum_target`, `has_future_topic_signal`, khóa sắp xếp RRF tất định trước NMS, và điều kiện cứu xét anaphoric `out_of_lesson` không đồng thuận trong `ChatGraph.retrieval_node`.
     - Bổ sung **`C13`**: Khử `except Exception: pass` tại `retrieval.py#L2199-L2200` và đăng ký `tests/test_spec004_unified_workflow_hardening.py` vào `MasterAutonomousHarness.SEQUENTIAL_PYTEST_SUITES`.
2. **Nhịp 2 (`core-coder`):**
   - **KHÔNG chạy lại Bước 0 Baseline** (giữ nguyên `scratch/spec004_baseline/` tại `HEAD 5986d5d`).
   - Triển khai nguyên tử trên `app/services/retrieval.py`, `app/services/chat_graph.py`, `scripts/master_autonomous_harness.py`, và bổ sung unit test khóa `C8-v2`, `C11`, `C12` vào `tests/test_spec004_unified_workflow_hardening.py`.
3. **Nhịp 3 (Deterministic Harness & `grounding-evaluator`):**
   - Thực thi `master_autonomous_harness.py --stage 1 --force-eval` xác nhận đồng thời: Gate 1 (`0` lỗi), Gate 2 (`12/12` suites PASS), Gate 3 (`9/9` E2E Matrix PASS), Gate 4a (Multi-Turn Status `>= 90.0%`), Gate 4b (Golden 200 TS Safety `>= 86.5%`), xuất `VERDICT: APPROVED`.

---

## 7. HỒ SƠ PROBE KIỂM TOÁN VÒNG #2 (LƯU NGOÀI REPO)
Toàn bộ script thăm dò chỉ đọc nằm tại `C:\Users\Admin\.gemini\antigravity-cli\brain\fdd2b8a3-ab68-4dea-a1cf-346185f14710\scratch\` (`0` tệp rác ghi vào workspace):
- `inspect_regressions.py` — Đối chiếu từng ca/từng lượt giữa `scratch/spec004_baseline/` và `docs/benchmarks/`.
- `list_all_failures.py` — Liệt kê toàn bộ `23` lượt trượt status Multi-Turn và các ca trượt `ts_ok` của Golden 200.
- `probe_loop2_deep.py` — Truy vết trực tiếp `BENCH-037` và tái hiện hiện tượng bất định RRF tie-break trên `SESSION-STRESS-45 T2`.
- `probe_mt_cross_layer.py` & `probe_hypotheses.py` — Kiểm chứng toàn cục `seq 1..83`, đối chứng `M4-T02 / S1-T06 / S1-T07 / SWITCH-31..40`, và kiểm tra toàn bộ ca Tầng 3 trên Golden 200.
- `probe_impact_audit.py` — Đo điểm Cross-Encoder thực tế của `raw_prompt` vs `search_query` trên các phiên đa lượt có đại từ hồi chỉ (`CORE-09 T3`, `OOP-12 T3`, `STRESS-44 T2`, `STRESS-49 T4`).
