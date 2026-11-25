# Unified E2E Spec: `004-unified-rag-workflow-hardening`

- **Ngày lập / Phiên bản:** `2026-11-25` (**v2.0 — PSTACK Nhịp 1B, Vòng lặp #2**, hậu kiểm trực tiếp từ Báo cáo Kiểm toán Vòng #2 [`.agent/technical_debt_audit.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/technical_debt_audit.md), Phán quyết Vòng #1 [`.agent/verification_verdict.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/verification_verdict.md) & kiểm chứng mã nguồn trực tiếp)
- **Tác giả Đồ án:** Trần Thành Nghĩa (MSSV: `23DH112252`), Trường Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT)
- **Vai trò Thiết kế Spec:** `rag-architect` & `solution-analyst`
- **Trạng thái:** `READY_FOR_LOOP2_IMPLEMENTATION` *(Bản v1.0 đã hội tụ `E2E Matrix 9/9 PASS` ở Vòng #1; bản v2.0 khóa triệt để 4 nguyên nhân gốc `RC-L2-01..04` gây trượt biên 1 ca ở Stage 1 Harness để đạt `VERDICT: APPROVED`)*
- **Phạm vi tác động (6 Layers + Harness):** `[x] Layer 0: Config & Manifest (V1 giữ nguyên)` `[x] Layer 1: IntentRouter (V1 giữ nguyên)` `[x] Layer 2: RetrievalService (V1 + V2 delta)` `[x] Layer 3: ChatGraph / CRAG (V1 + V2 delta)` `[x] Layer 4: ChatService & Schemas (V1 giữ nguyên)` `[x] Layer 5: TelemetryCritic & Harness (V1 + V2 delta)` *(Giữ nguyên 100% `data/curriculum/lessons_manifest.json`, `syllabus_embeddings.npz`, `app/services/curriculum.py` DAG root rule, `app/agent/guardrails.py`, và bản chụp Baseline `HEAD 5986d5d` tại `scratch/spec004_baseline/`)*

---

## 0. Tóm tắt Chuyển tiếp Vòng #1 → Vòng #2 (Loop #1 Post-Mortem & Non-Regression Lock)

Vòng #1 (`Spec 004 v1.0`) đã hội tụ **toàn bộ Cụm B (`M6-T03 -> L43`, `M7-T02 -> L54`, `M8-T03 -> L58`)**, đưa `E2E Matrix` từ `6/9` lên **`9/9` suites PASS (`all_passed: true`, Health `99..100/100`)**, giữ `0%` regex / `0%` test-set snooping / `100%` Data-Code Separation. Tuy nhiên, Stage 1 Harness trả `exit_code = 1` và Verifier trả `VERDICT: REJECTED` do đúng **4 nguyên nhân gốc đã chứng minh thực nghiệm**:

| Mã | Nguyên nhân gốc Vòng #1 (Đã kiểm chứng trực tiếp) | Chỉ số trượt Vòng #1 | Cơ chế sửa đồng bộ trong Spec v2.0 (Zero Quick-Fix) |
|---|---|---|---|
| **RC-L2-01** | **Bất đối xứng lắp ghép đa phương thức ở Tầng 3 (`PC-05a` quá tay):** Tầng 3 giữ cổng `video_transcript`-only (đúng) nhưng bỏ hoàn toàn `assemble_balanced_modality` nên làm rơi chunk `code_ast` đúng bài (`lesson_seq==7`, non-boilerplate, `score=0.3391`, Ground-Truth `approx_video_sec=5750`) của `BENCH-037`. | Stage 11 TS Safety `86.0% < 86.5%` (`172/200`, `-1` ca `BENCH-037`) | **`C8-v2` (Tách Cổng Quyết Định & Cổng Đóng Gói Tầng 3):** Giữ nguyên cổng `if low_confidence_items:` chỉ xét `video_transcript` (chặn 100% `code_ast` tự bật `grounded` và chặn `code_ast < 0.22`), nhưng sau khi `low_confidence_items` hợp lệ thì đính kèm `tier3_bound_code_items` (`lesson_seq==current`, non-boilerplate, `approx_video_sec!=None`, `score >= VIDEO_SCORE_THRESHOLD=0.22`) qua `assemble_balanced_modality`. |
| **RC-L2-02** | **Tổ hợp 3 lỗi cấu trúc liên tầng trên hội thoại đa lượt (`PC-07`):**<br>(a) Cắt `limit=10` trước NMS & hòa điểm RRF không tất định trên Qdrant Cloud (`STRESS-45 T2` lật qua lại giữa `L28` và `L37`).<br>(b) `is_future_curriculum_target` dùng `curriculum_matched_course != course_id` biến bài quá khứ `cpp-core` (`seq 1..52`) thành "tương lai" khi học viên ở `cpp-oop` (`53..83`), và `has_future_topic_signal` đơn phương tắt `active_continuation_shield` / Tầng 3 dù `Syllabus` & `Qdrant` bất đồng hoàn toàn (`matched != target`, `topical=False`).<br>(c) Đại từ hồi chỉ (`"nó"`, `"ở trong đó"`) ở `retrieval_node` bị `raw_prompt` đẩy nhầm sang `out_of_lesson` không đồng thuận syllabus, không bao giờ đối chiếu `search_query` dù `search_query` đạt `0.34–0.57` Tier-1 Grounded (`CORE-09 T3`, `OOP-12 T3`, `STRESS-44 T2`, `STRESS-49 T4`). | Multi-Turn Retrieval Status `89.64% < 90.0%` (`199/222`, `-1` lượt `STRESS-45 T2`) | **`PC-07` (`C11a + C11b + C12`):**<br>(a) `_sort_rrf_points_deterministically` (ưu tiên `min seq` cho future / `max seq` cho current window, tie-break `str(id)`) + tăng fetch RRF thô của `_fetch_future_points` lên `max(FUTURE_PROBE_LIMIT * 2, 20)` trước NMS (giữ nguyên trần `FUTURE_PROBE_LIMIT` cho CPU CE).<br>(b) Sửa `is_future_curriculum_target` theo `seq > current_lesson_seq` (giữ nguyên `NavBypass` xuyên khóa) + **Cross-Layer Future Topic Consensus** cho lượt nối tiếp (`is_continuation_turn=True`).<br>(c) **Anaphoric Unverified-OOL Rescue** trong `ChatGraph.retrieval_node` (chỉ chạy khi `search_query != raw_prompt` AND `matched != target`, và chỉ nhận khi `fallback_res` `grounded`, `not is_low_confidence`, `max_score >= 0.30`). |
| **RC-L2-03** | Khối `except Exception: pass` im lặng ở nhánh `Revision Non-Dominance Shield` ([`app/services/retrieval.py#L2199-L2200`](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2199-L2200)). | Lỗi vệ sinh mã nguồn (`P1`) | **`C13a`:** Đổi thành `except Exception as rev_err: logger.debug(...)`. |
| **RC-L2-04** | Suite mới `tests/test_spec004_unified_workflow_hardening.py` chưa đăng ký vào `MasterAutonomousHarness.SEQUENTIAL_PYTEST_SUITES`. | Gate 2 chỉ chạy `11` suites cũ (`P1`) | **`C13b`:** Đăng ký vào `SEQUENTIAL_PYTEST_SUITES` (nâng Gate 2 lên `12` suites tuần tự, `110+` tests). |

> [!IMPORTANT]
> **Nguyên tắc Bảo toàn Vòng #1 & Baseline:**
> - **KHÔNG đảo ngược** các bản vá Vòng #1 đã hội tụ (`PC-01` Cụm B, `PC-02` `or->and` & temporal NLI fail-closed, `PC-03` monotonic `coverage_gap` fallback, `PC-04` `_compute_calibrated_rrf_norm` & degraded `[0.15, 0.29]`, `PC-05b/c` lightweight `is_approximate=True` & anti-double `📍`, `PC-06` `TelemetryCritic`).
> - **KHÔNG ghi đè** bản chụp Pre-Optimization Baseline tại `scratch/spec004_baseline/` (`HEAD 5986d5d`, chụp `2026-11-25 18:37–18:47`).

---

## 1. Constitution Check (`AGENTS.md` & Hardware/Rigor Invariants)
- [x] **Zero Quick-Fix & Zero Regex Runtime:** 100% giải quyết theo *Lớp bài toán (Problem Class)*; `0` lệnh `import re` / `re.*()` trong `app/`; cấm mọi điều kiện bắt chuỗi cứng câu hỏi hoặc số thứ tự bài học.
- [x] **Zero Test-Set Snooping:** Không thêm từ khóa riêng của đề thi vào `data/curriculum/lessons_manifest.json`; không tái sinh `data/curriculum/syllabus_embeddings.npz`; không sửa nhãn `Golden 200` / `Multi-Turn`; `0` chuỗi `BENCH-` / `SESSION-` trong `app/` và `tests/test_spec004_unified_workflow_hardening.py`.
- [x] **Zero Fake Fallback & ICLR 2025 Context Sufficiency:** RRF-fallback khi Cross-Encoder lỗi bị chặn cứng trong `[0.15, 0.29]` (`< 0.30` & `< 0.35`, `is_low_confidence=True, is_approximate=True`); Tầng 3 giữ cổng quyết định `video_transcript`-only (không cho `code_ast < 0.35` tự kích hoạt `grounded`, và chặn hoàn toàn `code_ast < 0.22` khỏi ngữ cảnh Tầng 3).
- [x] **Static Prefix Cache (`messages[0]`):** Giữ `messages[0]` tĩnh 100% cho vLLM KV prefix caching (`SOCRATIC_GROUNDED_PROMPT`, `OUT_OF_LESSON_PROMPT`, `CURRICULUM_OVERVIEW_PROMPT`, `COVERAGE_GAP_PROMPT`).
- [x] **Data/Code Separation:** `temporal_nli_*` lưu trong `data/metadata/router_intent_manifest.json`; mọi ngưỡng Pareto & Modality đọc qua `app/config.py`.
- [x] **CRAG Attribution Invariant (Yan et al., arXiv:2401.15884):** Đã chuẩn hóa 4 docstring tại `app/services/retrieval.py` & `app/services/chat_graph.py`.
- [x] **Hardware & Sequential Execution Invariant (RTX 2050 4 GB VRAM):** Bảo toàn `onnxruntime-gpu==1.23.2`, Dense E5 trên GPU, `jina-reranker-v2-int8` trên CPU (`USE_CPU_RERANKER=True`, `USE_INT8_RERANKER=True`, `RERANK_CPU_THREADS=4`); không tăng số lượng tài liệu đưa vào CPU Cross-Encoder (sau NMS vẫn cắt `[:FUTURE_PROBE_LIMIT]`); mọi lệnh kiểm thử chạy tuần tự từng tiến trình với `HF_HUB_OFFLINE=1` và `TRANSFORMERS_OFFLINE=1`.
- [x] **Pre/Post-Optimization Benchmark Cycle:** Đối chiếu từng ca/từng lượt giữa Baseline `HEAD 5986d5d` (`scratch/spec004_baseline/`) và kết quả hậu kiểm Vòng #2.

---

## 2. Chẩn đoán Nguyên nhân Gốc E2E (7 Problem Classes: `PC-01..PC-07`)

### Problem Class PC-01 (Cụm B — ĐÃ HỘI TỤ V1, GIỮ NGUYÊN): Điều hướng Khái niệm Tương lai Có Kèm Bối cảnh Hiện tại (`M6-T03`, `M7-T02`, `M8-T03`)
- **Bản chất:** Câu điều hướng lộ trình (`is_curriculum_navigation=True`) nhắc kèm bối cảnh bài hiện tại khiến `CurriculumService.find_lesson_for_query` tự khớp `matched == current`, kích hoạt 3 lối tắt tin mù (`focused_lesson_seq`, `skip_nav_rerank`, Pareto 3A xóa `target_seq`) và 2 ghi đè hạ nguồn ở `crag_grader_node`.
- **Trạng thái V1:** Đã sửa triệt để bằng vị từ `nav_label_verified_in_window`, biên Pareto Unresolved-Nav `(0.40, -0.12)` + Revision Non-Dominance Shield, và `is_ce_resolved_future_nav` trong `crag_grader_node`. Kết quả thực đo: `M6-T03 -> L43`, `M7-T02 -> L54`, `M8-T03 -> L58`, `E2E Matrix 9/9 PASS`.
- **V2 delta duy nhất:** Thay `except Exception: pass` ở dòng `#L2199-L2200` bằng `logger.debug(...)` (`RC-L2-03`).

### Problem Class PC-02 (Cụm A1 — ĐÃ HỘI TỤ V1, GIỮ NGUYÊN): Contextual NLI (`or → and`) & Temporal NLI Fail-Closed
- **Trạng thái V1:** Đã sửa `or → and` tại `app/agent/router.py#L875`, tách `temporal_nli_*` sang `router_intent_manifest.json`, chuyển `verify_in_video_temporal_query` sang fail-closed `(False, 1.0)`.

### Problem Class PC-03 (Cụm A2 — ĐÃ HỘI TỤ V1, NÂNG CẤP ĐỒNG BỘ VỚI `PC-07c`): Tính Đơn điệu của Contextual Retrieval Fallback
- **Trạng thái V1:** Đã sửa `app/services/chat_graph.py#L780-L788` theo thứ tự đơn điệu $\text{coverage\_gap} \prec \text{grounded}(\text{low\_conf}) \prec \{\text{grounded}(\text{high\_conf}), \text{out\_of\_lesson}\}$.
- **V2 mở rộng đồng bộ (`PC-07c`):** Bổ sung nhánh cứu xét anaphora cho `out_of_lesson` thiếu đồng thuận syllabus (xem §3.5).

### Problem Class PC-04 (Cụm A3 — ĐÃ HỘI TỤ V1, GIỮ NGUYÊN): Chuẩn hóa RRF Tuyệt đối & Trần Suy giảm Minh bạch
- **Trạng thái V1:** Đã triển khai `_compute_calibrated_rrf_norm(..., theoretical_max=1.0)` và tách `reranker_failed` khỏi `skip_nav_rerank`, khóa điểm suy giảm trong $[0.15, 0.29]$ với `is_low_confidence=True, is_approximate=True, scoring_source="rrf_fallback_degraded"`.

### Problem Class PC-05 (Cụm A4a/b/c — TINH CHỈNH `PC-05a` Ở V2, GIỮ NGUYÊN `PC-05b/c`):
1. **PC-05a (`C8-v2` — Tinh chỉnh V2 cho `RC-L2-01`):**
   - Vòng #1 đã đóng đúng lỗ hổng `grade_document_relevance` (`code_ast >= 0.35`) và lọc `content_type == "video_transcript"` ở Tầng 3, chặn hoàn toàn `code_ast < 0.35` tự kích hoạt `grounded`.
   - Tuy nhiên, khi `low_confidence_items` (`video_transcript` đạt chuẩn Ambiguous) đã xác lập hợp lệ `status = "grounded"`, Tầng 3 Vòng #1 bỏ qua `assemble_balanced_modality` (trái ngược với Tầng 1 [#L1992-L2008](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L1992-L2008) & Tầng 2 [#L2288-L2304](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2288-L2304)), làm rơi đoạn `code_ast` đúng bài, phi-boilerplate, mang mốc Phase-2 Ground-Truth `approx_video_sec = 5750` (`function_thamChieu`, `score = 0.3391`) của `BENCH-037`.
   - **Giải pháp V2 (`C8-v2`):** Tách bạch **Cổng Quyết Định (`Decision Gate`)** và **Cổng Đóng Gói Đa Phương Thức (`Balanced Modality Context Assembly`)** ở Tầng 3 (xem §3.3).
2. **PC-05b & PC-05c (Giữ nguyên V1):** `_build_lightweight_future_chunk` gắn `is_approximate=True` cho chapter & `00:00` (`approx_video_sec=None`); `ChatService` chống lặp dòng `📍`.

### Problem Class PC-06 (Observability & Critic — ĐÃ HỘI TỤ V1, GIỮ NGUYÊN):
- 4 trường quan sát (`scoring_source`, `skip_nav_rerank`, `curriculum_matched_seq`, `curriculum_matched_course`) đã đồng bộ suốt `RetrievalResult -> AgentState -> StreamMetadataEvent -> e2e_matrix_harness.py`, và `TelemetryCritic` bắt lỗi `Unresolved Curriculum Navigation (-15)` & `Degraded RRF Fallback (-5)`.

### Problem Class PC-07 (MỚI TRONG V2 — KHẮC PHỤC `RC-L2-02`): Ổn định Hội thoại Đa lượt, Khử Bất định Hòa điểm RRF & Cứu xét Đại từ Hồi chỉ Bị Cướp sang `out_of_lesson`
- **3 vết gãy cấu trúc liên tầng đã chứng minh bằng probe thực nghiệm ([`.agent/technical_debt_audit.md §3`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/technical_debt_audit.md#L91-L147)):**
  1. **PC-07a (`C11a` — RRF Tie-Break Non-Determinism & Pre-NMS Truncation):**
     - `_fetch_future_points` (`retrieval.py#L479`) đặt `limit=settings.FUTURE_PROBE_LIMIT (10)` ngay trên Qdrant RRF **trước** `deduplicate_temporal_candidates`: một bài tương lai dài có nhiều đoạn gối đầu (vd `L37` chiếm 5/10 slot) đẩy bài tiên quyết phía trước (`L28`) ra rìa cắt `limit=10`.
     - Trên Qdrant Cloud đa phân mảnh, các điểm hòa điểm RRF (`0.5000`, `0.3333`, `0.2500`, ...) đổi thứ tự ngẫu nhiên giữa hai lần gọi liên tiếp nếu thiếu khóa sắp xếp thứ cấp tất định, gây dao động `STRESS-45 T2` (`L28 -> grounded` vs `L37 -> out_of_lesson`).
  2. **PC-07b (`C11b` — Course-Direction Bug & Unverified Future Topic Signal):**
     - `is_future_curriculum_target` (`retrieval.py#L1503`) kiểm tra `curriculum_matched_course != course_id`, biến bài quá khứ `cpp-core` (`seq 1..52`) thành "tương lai" khi học viên đang học `cpp-oop` (`seq 53..83`) — làm tắt oan Tier-1 Early Exit, `active_continuation_shield`, và Tầng 3 (`OOP-12 T3 -> L18`, `STRESS-49 T5 -> L6`).
     - Trên lượt hội thoại nối tiếp (`is_continuation_turn=True`), `has_future_topic_signal` (`retrieval.py#L2070-L2073`) tin mù vào phỏng đoán đơn phương của `CurriculumService` ngay cả khi bài hiện tại đã có cơ sở cục bộ ($S_{\text{current}} \ge 0.22$) và Qdrant Future Prober **bất đồng hoàn toàn** (`target_seq != curriculum_matched_seq`, `target_has_topical_match=False`) — tắt sạch `active_continuation_shield` (`STRESS-45 T2`, `CORE-09 T3`, `STRESS-42 T2`).
  3. **PC-07c (`C12` — Anaphoric False-OOL Hijack tại `ChatGraph.retrieval_node`):**
     - `retrieval_node` (`chat_graph.py#L764`) chỉ chạy fallback bằng `search_query` khi `raw_prompt` ra `coverage_gap` hoặc `is_low_confidence`.
     - Khi câu tiếp nối chứa đại từ hồi chỉ (*`"qua nó"`, `"thì nó"`, `"thoát khỏi nó"`, `"ở trong đó"`*), `router_node` đã xác minh `is_context_dependent=True` và `not is_topic_shift` (sinh `search_query != raw_prompt`), nhưng `raw_prompt` cụt chủ ngữ bị đẩy nhầm sang `out_of_lesson` **không có đồng thuận syllabus** (`curriculum_matched_seq != target_lesson_seq`), khiến `retrieval_node` không bao giờ thử `search_query` dù `search_query` đạt `0.34–0.57` Tier-1 Grounded tại bài hiện tại (`CORE-09 T3`, `OOP-12 T3`, `STRESS-44 T2`, `STRESS-49 T4`).

---

## 3. Chứng minh Toán học & Biên Độ Quyết Định (`@solution-analyst`)

### 3.1. Vị từ `nav_label_verified_in_window` & Biên Pareto Unresolved-Nav (`PC-01`, Giữ nguyên V1)
$$V_{\text{win}} \triangleq N \land (L_m \neq \varnothing) \land (C_m = C_c) \land \Big((L_{\text{exp}} \neq \varnothing \land L_{\text{exp}} \le L_c) \lor R_{\text{curr}} \lor O \lor (L_m < L_c)\Big)$$
$$U_{\text{self}} \triangleq N \land (L_m \neq \varnothing) \land (C_m = C_c) \land (L_m = L_c) \land \neg V_{\text{win}}$$
Khi $U_{\text{self}} = \text{True}$: áp dụng Biên Pareto Unresolved-Nav $S_{\text{future}} \ge 0.40 \land (S_{\text{future}} - S_{\text{current}}) \ge -0.12 \land \neg\text{is\_revision\_of}(L_{\text{target}}, L_c)$.

### 3.2. Chuẩn hóa RRF Tuyệt đối & Trần Suy giảm Minh bạch (`PC-04`, Giữ nguyên V1)
$$\tilde{r}(i) = \begin{cases} \operatorname{clip}_{[0,1]}\!\left(\dfrac{r_i - r_{\min}}{r_{\max} - r_{\min}}\right), & r_{\max} - r_{\min} > 10^{-6} \\[6pt] \operatorname{clip}_{[0,1]}\!\left(\dfrac{r_i}{R_{\max}^{\star}}\right), & r_{\max} - r_{\min} \le 10^{-6}\; (R_{\max}^{\star}=1.0) \end{cases}, \qquad p_{\text{degraded}}(i) = 0.15 + 0.14\tilde{r}(i) \in [0.15,\; 0.29]$$

### 3.3. Tách Bạch Cổng Quyết Định & Cổng Đóng Gói Đa Phương Thức Tầng 3 (`PC-05a` / `C8-v2` — MỚI V2)
Đặt tập ứng viên `video_transcript` đạt chuẩn CRAG Ambiguous là $\mathcal{V}_{\text{amb}}$ (`low_confidence_items`, lọc tường minh `content_type == "video_transcript"` và giữ nguyên `grade_document_relevance` với ngưỡng `code_ast >= 0.35`).
1. **Cổng Quyết Định (Decision Gate — Bất biến):**
   $$\text{Tier3Grounded} \iff (\mathcal{V}_{\text{amb}} \neq \varnothing)$$
   *Chứng minh bảo toàn `PC-05a`:* Nếu không có `video_transcript` đạt chuẩn Ambiguous ($\mathcal{V}_{\text{amb}} = \varnothing$), hệ thống **chắc chắn trả `coverage_gap`**, cấm tuyệt đối `code_ast` điểm `< 0.35` tự kích hoạt `grounded`.
2. **Cổng Đóng Gói Đa Phương Thức & Bảo toàn Phase-2 Binding (Chỉ kích hoạt khi $\mathcal{V}_{\text{amb}} \neq \varnothing$):**
   Định nghĩa tập `tier3_bound_code_items`:
   $$\mathcal{C}_{\text{bound}}^{(3)} = \Big\{ c \in \mathcal{D} \;\Big|\; \text{type}(c)=\texttt{code\_ast} \;\land\; \text{seq}(c)=L_c \;\land\; \text{scope}(c)\notin \mathcal{B} \;\land\; \text{approx\_video\_sec}(c)\neq\varnothing \;\land\; S(c) \ge \tau_{\text{vid}} \Big\}$$
   với $\mathcal{B} = \texttt{BOILERPLATE\_SCOPES}$ và $\tau_{\text{vid}} = \texttt{VIDEO\_SCORE\_THRESHOLD} = 0.22$.
   - **Tại sao chọn sàn $\tau_{\text{vid}} = 0.22$ chặt hơn $0.15$?**
     1. Triệt tiêu **100%** khả năng `code_ast` nhiễu trong vùng $[0.15, 0.22)$ (đúng trọng tâm Cụm A4a) lọt vào ngữ cảnh Tầng 3 ngay cả ở vai trò phụ trợ.
     2. Bảo toàn **100%** các đoạn `code_ast` cận ngưỡng $[0.22, 0.35)$ thuộc đúng bài hiện tại, phi-boilerplate, đã gắn mốc Ground-Truth Phase 2 (như `function_thamChieu` `S = 0.3391`, `approx_video_sec = 5750` của `BENCH-037`).
     3. Lắp ghép qua `assemble_balanced_modality(video_items=low_confidence_items, code_items=tier3_bound_code_items, final_top_k=final_top_k, prefer_balanced=bool(tier3_bound_code_items))` rồi `reorder_lost_in_the_middle(...)`, giữ nguyên `is_low_confidence=True, is_approximate=True` trên `RetrievalResult`.

### 3.4. Khóa Sắp Xếp RRF Tất Định & Đồng Thuận Tương Lai Liên Tầng (`PC-07a/b` / `C11` — MỚI V2)
1. **Khóa sắp xếp RRF tất định đối xứng theo khoảng cách tới bài hiện tại $|L_i - L_c|$ (`C11a`):**
   - Với tập tương lai ($L_i > L_c$, `prefer_earlier_seq=True`):
     $$K_{\text{fut}}(h) = \big(-\operatorname{round}(s_{\text{RRF}}(h), 6),\; \text{seq}(h),\; \text{str}(\text{id}(h))\big)$$
     *(Ưu tiên $\min L_i$ khi hòa điểm RRF — khớp 100% *Prerequisite Order Pareto Invariant*; nâng `limit` truy vấn thô lên `max(FUTURE_PROBE_LIMIT * 2, 20)` trước NMS và vẫn cắt `[:FUTURE_PROBE_LIMIT]` trước Cross-Encoder để giữ nguyên ngân sách CPU).*
   - Với tập cửa sổ hiện tại ($L_i \le L_c$, `prefer_earlier_seq=False`):
     $$K_{\text{curr}}(h) = \big(-\operatorname{round}(s_{\text{RRF}}(h), 6),\; -\text{seq}(h),\; \text{str}(\text{id}(h))\big)$$
     *(Ưu tiên bài gần `current_lesson_seq` nhất khi hòa điểm RRF — ngăn bài nhập môn `L1/L2` đẩy bài hiện tại ra khỏi lát cắt `[:top_candidates]`, đồng thời giữ NMS 100% tất định).*
2. **Định nghĩa đơn điệu `is_future_curriculum_target` & Đồng thuận Tương lai Liên tầng (`C11b`):**
   Vì toàn bộ 83 bài trong `lessons_manifest.json` đánh số đơn điệu toàn cục (`cpp-core`: `1..52`, `cpp-oop`: `53..83`):
   $$F_{\text{curr}} \triangleq \neg T_{\text{curr}} \land (L_m \neq \varnothing) \land (L_m > L_c)$$
   *(Tách biệt hoàn toàn với `NavBypass` xuyên khóa ở `#L1658-L1662` dành riêng cho `is_curriculum_navigation=True`.)*

   Định nghĩa **Tín hiệu Chủ đề Tương lai Đã Xác thực Liên tầng**:
   $$F_{\text{ver}} \triangleq F_{\text{curr}} \land \Big(\neg I_{\text{cont}} \;\lor\; (S_{\text{current}} < 0.22) \;\lor\; (L_{\text{target}} \neq \varnothing \land L_{\text{target}} = L_m)\Big)$$
   $$H_{\text{fut}} \triangleq F_{\text{ver}} \;\lor\; \big(L_{\text{target}} \neq \varnothing \land L_{\text{target}} > L_c \land T_{\text{topical}}(L_{\text{target}}, q)\big)$$
   **Kiểm chứng bất biến toán học:**
   - **Đơn lượt (`Golden 200`, mọi Turn 1):** $I_{\text{cont}} = \text{False} \implies F_{\text{ver}} \equiv F_{\text{curr}}$ (**bảo toàn 100% phân phối đơn lượt**).
   - **Chuyển bài tương lai thật trong đa lượt (`M4-T02`, `S1-T06`, `S1-T07`, `SWITCH-31..40`):** Thỏa $L_{\text{target}} = L_m$ (`8=8`, `3=3`, `43=43`) hoặc $S_{\text{current}} < 0.22$ hoặc $T_{\text{topical}} = \text{True} \implies H_{\text{fut}} = \text{True}$ (**bảo toàn 100% `out_of_lesson`**).
   - **Lượt nối tiếp bị đoán nhầm đơn phương (`STRESS-45 T2` `L7`, `matched=43`, `target=37/28`, `topical=False`, $S_{\text{current}}=0.2992 \ge 0.22$):** $F_{\text{ver}} = \text{False} \land T_{\text{topical}} = \text{False} \implies H_{\text{fut}} = \text{False} \implies$ **`active_continuation_shield = True`** $\implies$ **`grounded` ổn định 100%**.

### 3.5. Cứu Xét Đại Từ Hồi Chỉ Bị Cướp Sang `out_of_lesson` Không Đồng Thuận (`PC-07c` / `C12` — MỚI V2)
Tại `ChatGraph.retrieval_node` (`#L764-L790`, nhánh `not is_curriculum_nav`), định nghĩa trạng thái `out_of_lesson` chưa có đồng thuận syllabus:
$$O_{\text{unver}} \triangleq (\text{status}(\text{raw}) = \texttt{out\_of\_lesson}) \;\land\; (L_m(\text{raw}) \neq L_{\text{target}}(\text{raw}))$$
Khi `search_query != raw_prompt` (tức `router_node` đã xác nhận `is_context_dependent=True` và `not is_topic_shift`) và $(\text{status}(\text{raw})=\texttt{coverage\_gap} \lor \text{low\_conf}(\text{raw}) \lor O_{\text{unver}})$, chạy `fallback_res` trên `search_query` và áp dụng **quy tắc nâng cấp đơn điệu 3 nhánh**:
1. Gốc `coverage_gap`: chấp nhận nếu `fallback_res.status in ("grounded", "out_of_lesson")`.
2. Gốc $O_{\text{unver}}$ (`out_of_lesson` không đồng thuận): **chỉ** chấp nhận nếu đồng thời thỏa mãn **cả 3 rào chắn**:
   $$\text{status}(\text{fb}) = \texttt{grounded} \;\land\; \neg \text{low\_conf}(\text{fb}) \;\land\; \max_{c \in \text{chunks}(\text{fb})} S(c) \ge 0.30$$
   *(Rào chắn $\ge 0.30 = \texttt{MODALITY\_GATE\_VIDEO\_HIGH\_CONFIDENCE}$ ngăn tuyệt đối ngữ cảnh `anchor_query` yếu $0.22..0.29$ kéo ngược một ca `out_of_lesson` thật về `grounded`; trong khi các ca hồi chỉ thực sự đạt `0.3414..0.5744`, vượt xa ngưỡng `0.30`!)*
3. Gốc `grounded(is_low_confidence=True)`: chỉ chấp nhận nếu `fallback_res.status in ("grounded", "out_of_lesson") and not fallback_res.is_low_confidence`.

---

## 4. Bản đồ Đồng bộ Toàn luồng & Hợp đồng Hành vi E2E (v2.0)

### 4.1. End-to-End Flow Synchronization Map (Delta V2 bổ sung trên nền V1)

| PC | Layer 0–1 (`Config / Router`) | Layer 2 (`RetrievalService`) | Layer 3 (`ChatGraph / CRAG`) | Layer 4–5 (`Chat / Critic / Harness`) |
|---|---|---|---|---|
| **PC-01..04, 05b/c, 06** *(Giữ nguyên V1)* | `PARETO_UNRESOLVED_NAV_*`, `temporal_nli_*`, `or->and`, fail-closed | `nav_label_verified_in_window`, Pareto 3A-2, `_compute_calibrated_rrf_norm`, degraded `[0.15, 0.29]`, lightweight `is_approximate=True`, CRAG Yan et al. docstrings | `is_ce_resolved_future_nav`, ưu tiên `target_lesson_seq`, đồng bộ `has_approximate` | `StreamMetadataEvent` +4 trường, chống lặp `📍`, `TelemetryCritic` Kiểm toán 4 |
| **PC-05a (`C8-v2`)** *(Tinh chỉnh V2)* | Không đổi | Giữ `grade_document_relevance` (`code_ast >= 0.35`) & `low_confidence_items` (`video_transcript` only); khi `low_confidence_items` không rỗng, ghép `tier3_bound_code_items` (`seq==current`, non-boilerplate, `approx_video_sec!=None`, `score >= 0.22`) qua `assemble_balanced_modality` + `reorder_lost_in_the_middle` | `crag_grader_node` tự động đọc `approx_video_sec` của `code_ast` đầu danh sách vào `suggested_timestamps` & `sources` | `run_rag_benchmark.py` khôi phục Ground-Truth `5750s` (`BENCH-037` PASS, TS Safety `>= 86.5%`) |
| **PC-07 (`C11 + C12`)** *(Mới V2)* | Không đổi | 1. Thêm `_sort_rrf_points_deterministically` (`prefer_earlier_seq=True/False`) + nâng `_fetch_future_points` RRF `limit` lên `max(FUTURE_PROBE_LIMIT*2, 20)` trước NMS.<br>2. Sửa `is_future_curriculum_target` thành `seq > current_lesson_seq`.<br>3. Nâng cấp `has_future_topic_signal` theo Đồng thuận Liên tầng cho `is_continuation_turn=True`. | `retrieval_node#L764-L790`: thêm nhánh `is_unverified_anaphoric_ool` (`status=="out_of_lesson"` & `matched!=target`) với điều kiện nhận chặt (`grounded`, `not is_low_confidence`, `max_score >= 0.30`) | Giữ nguyên `E2E Matrix 9/9`; Multi-Turn Status từ `89.64%` lên vùng `91.5%–92.8%` |
| **C13** *(Vệ sinh & Harness V2)* | Không đổi | Đổi `except Exception: pass` (`retrieval.py#L2199-L2200`) thành `logger.debug(...)` | Không đổi | Đăng ký `"tests/test_spec004_unified_workflow_hardening.py"` vào `MasterAutonomousHarness.SEQUENTIAL_PYTEST_SUITES` (`12` suites) |

### 4.2. Hợp đồng Hành vi E2E Bổ sung cho Vòng #2 (`REQ-06v2`, `REQ-09..REQ-11`)
*(Giữ nguyên `REQ-01..REQ-05`, `REQ-07`, `REQ-08` từ v1.0; cập nhật `REQ-06` và bổ sung `REQ-09..REQ-11`:)*

| ID | Lớp đầu vào / Ngữ cảnh | `RetrievalService` | `ChatGraph / Harness` | Điều kiện PASS |
|---|---|---|---|---|
| `REQ-06v2` | **PC-05a (`C8-v2`)**: (a) Chỉ có `code_ast < 0.35`, không có video Ambiguous; (b) Có video Ambiguous (`0.187`) + `code_ast` nhiễu (`0.18`) vs `code_ast` bound đúng bài phi-boilerplate (`0.339`, `approx_video_sec=5750`) | (a) `coverage_gap`; (b) `grounded (is_low_confidence=True, is_approximate=True)`, loại `code_ast 0.18`, giữ `code_ast 0.339` kèm `approx_video_sec=5750` ở vị trí ưu tiên | `crag_grader_node` xuất `5750s` vào `suggested_timestamps` | Unit test khóa đủ 3 nhánh + Stage 11 Golden TS Safety `>= 86.5%` (`BENCH-037` PASS) |
| `REQ-09` | **PC-07a (`C11a`)**: Hai lô ứng viên RRF hòa điểm theo thứ tự đảo ngược từ Qdrant Cloud; bài dài chiếm 5 đoạn gối đầu | `_sort_rrf_points_deterministically` trả cùng 1 kết quả 100% bất biến thứ tự đầu vào; bài tiên quyết không bị cắt cụt trước NMS; CPU CE vẫn chỉ nhận `<= FUTURE_PROBE_LIMIT` | Không tăng latency trung bình | Unit test hoán vị đầu vào ra kết quả giống hệt nhau |
| `REQ-10` | **PC-07b (`C11b`)**: (a) Học viên `cpp-oop` (`L53`) có `matched=L18 (cpp-core)`; (b) Lượt nối tiếp `L7` (`S_curr=0.299`) có `matched=L43` nhưng Qdrant trả `target=L37` (`topical=False`) | (a) `is_future_curriculum_target=False` (không chặn Early Exit/Shield); (b) `has_future_topic_signal=False` → `active_continuation_shield=True` → `grounded` L7; đối chứng `matched==target` vẫn `out_of_lesson` | `M4-T02`, `S1-T06`, `S1-T07`, `SWITCH-31..40` giữ nguyên `out_of_lesson` | Unit test khóa cả 3 trường hợp + `STRESS-45 T2` `grounded` ổn định |
| `REQ-11` | **PC-07c (`C12`) & `C13`**: `raw_prompt` có đại từ hồi chỉ (`search_query != raw_prompt`) trả `out_of_lesson` với `matched != target` vs `matched == target` | `search_query` đạt `grounded` (`0.52 >= 0.30`, `not is_low_confidence`) vs yếu (`0.26 < 0.30`) | `matched != target` + `fb >= 0.30` → nhận `grounded`; `fb < 0.30` hoặc `matched == target` → giữ `out_of_lesson`; Harness Gate 2 chạy đủ `12/12` suites | Unit test khóa 3 nhánh + Multi-Turn Status `>= 90.0%` + Gate 2 `12/12` PASS |

---

## 5. Đặc tả Sửa đổi Theo Thứ tự Phụ thuộc (Dependency-Ordered Changes — Vòng #2 Delta)

> **Quy tắc Vòng #2:** Bước 0 (`scratch/spec004_baseline/`) và các Bước 1, 2, 5, 6 của Vòng #1 **ĐÃ HOÀN TẤT & ĐƯỢC BẢO TOÀN** — KHÔNG chạy lại Bước 0 và KHÔNG sửa ngược `app/config.py`, `router_intent_manifest.json`, `app/agent/router.py`, `app/schemas/chat.py`, `app/services/chat.py`, `app/services/telemetry_critic.py`, `scripts/e2e_matrix_harness.py`. Vòng #2 chỉ thực thi 4 bước nguyên tử tinh gọn sau:

| Bước | Lớp / Tệp | Thay đổi nguyên tử Vòng #2 | Phụ thuộc | Cổng thoát bước |
|:-:|---|---|:-:|---|
| **V2-1** | **Lớp 2 — `RetrievalService`**<br>[`app/services/retrieval.py`](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py) | 1. Thêm `_sort_rrf_points_deterministically(points, *, prefer_earlier_seq=True)`; áp dụng tại `_fetch_future_points` (cùng nâng `limit=max(settings.FUTURE_PROBE_LIMIT * 2, 20)`), `_score_future_points` (trước NMS, giữ `[:settings.FUTURE_PROBE_LIMIT]`), và `search` (`raw_candidates`, `prefer_earlier_seq=False`, trước NMS).<br>2. Sửa `is_future_curriculum_target` (`#L1499-L1506`) thành `bool(curriculum_matched_seq is not None and int(curriculum_matched_seq) > int(current_lesson_seq))` (giữ nguyên `NavBypass` `#L1658-L1662`).<br>3. Nâng cấp `has_future_topic_signal` (`#L2070-L2080`) với `is_verified_future_curriculum_signal` cho `is_continuation_turn=True`.<br>4. Thay `except Exception: pass` (`#L2199-L2200`) bằng `except Exception as rev_err: logger.debug(...)`.<br>5. Tầng 3 (`#L2368-L2379`): giữ nguyên `low_confidence_items` (`video_transcript`-only), bổ sung `tier3_bound_code_items` (`lesson_seq==current`, non-boilerplate, `approx_video_sec!=None`, `confidence_score >= settings.VIDEO_SCORE_THRESHOLD`) và đóng gói qua `assemble_balanced_modality` + `reorder_lost_in_the_middle`. | V1 hoàn tất | `py_compile` + `test_session_7aky9_debug_fixes.py` + `test_playground_scenario1_fixes.py` |
| **V2-2** | **Lớp 3 — `ChatGraph`**<br>[`app/services/chat_graph.py`](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py) | `retrieval_node#L763-L790`: thêm `is_unverified_anaphoric_ool = bool(retrieval_res.status == "out_of_lesson" and retrieval_res.curriculum_matched_seq != retrieval_res.target_lesson_seq)` vào điều kiện gọi `fallback_res` khi `search_query != raw_prompt`, chỉ chấp nhận `fallback_res` cho nhánh này khi `status == "grounded" and not is_low_confidence` và `max(confidence_score) >= settings.MODALITY_GATE_VIDEO_HIGH_CONFIDENCE`. | V2-1 | `test_stage13_context_hygiene.py` + `test_playground_scenario1_fixes.py` |
| **V2-3** | **Harness & Test Suite Spec 004**<br>[`scripts/master_autonomous_harness.py`](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/master_autonomous_harness.py)<br>[`tests/test_spec004_unified_workflow_hardening.py`](file:///D:/In_Course_Agentic_RAG_Copilot/tests/test_spec004_unified_workflow_hardening.py) | 1. Đăng ký `"tests/test_spec004_unified_workflow_hardening.py"` vào `SEQUENTIAL_PYTEST_SUITES` (`12` suites) và cập nhật tiêu đề Gate 2.<br>2. Giữ nguyên `10` tests V1 và thêm `4` unit tests khóa `C8-v2`, `C11a`, `C11b`, `C12` (`14/14` tests, `0%` ID benchmark, `0%` sao chép đề thi). | V2-1, V2-2 | `pytest tests/test_spec004_unified_workflow_hardening.py -v` (`14/14 PASSED`) |
| **V2-4** | **Master Verification Gate (Vòng #2)** | Chạy `.\.venv\Scripts\python.exe scripts\master_autonomous_harness.py --stage 1 --force-eval` (tuần tự, `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`) và đối chiếu Pre/Post với `scratch/spec004_baseline/`. | V2-1..V2-3 | `exit_code = 0`, Gate 1–4 xanh 100%, `VERDICT: APPROVED` |

---

## 6. Cross-Layer Conflict & Invariant Matrix (Cổng Chống Xung đột Chéo `C1..C13`)

Ký hiệu tác động: `●` trực tiếp · `○` gián tiếp · `—` không chạm.

| Mã | Thay đổi dự kiến | Router | Curr | Retr | Graph | Chat | Critic / Harness | Nguy cơ xung đột chéo tiềm ẩn | Cơ chế phòng ngừa đã khóa trong Spec v2.0 | Bộ kiểm chứng bắt buộc |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|---|---|---|
| **C1** | Vị từ `nav_label_verified_in_window` + Pareto 3A-2 `(0.40, -0.12)` (`PC-01`, V1) | ○ | — | ● | ○ | — | ○ | Cướp nhầm câu hỏi bài hiện tại hoặc chạm 17 lượt false-OOL Multi-Turn. | Chỉ chạy khi `is_curriculum_navigation=True` & `matched==current` & không explicit/curr_ref/overview; giữ `floor=0.40, margin=-0.12` + Revision Shield. | `M1..M8`, `S1`, `test_spec004` (`PC-01`) |
| **C2** | Tách `nav_unresolved_self_match` khỏi `focused_lesson_seq` & `skip_nav_rerank` (`PC-01`, V1) | — | — | ● | — | — | — | Phá quay lại bài trong cửa sổ (`M7-T03`, `M2-T01`, `matched < current`). | `explicit <= current`, `has_curr_ref`, `is_overview`, `matched < current` giữ `nav_label_verified_in_window=True`. | `M1`, `M2-T01`, `M7-T03`, `test_spec004` |
| **C3** | `crag_grader_node` giữ `target_lesson_seq` & tắt `competing_lessons` khi CE resolved (`PC-01`, V1) | — | ○ | ○ | ● | ○ | ○ | Phá disambiguation đa chủ đề (`M2-T05`) hoặc `NavBypass` mơ hồ (`M1-T09`). | Luôn giữ `multi_topic_disjunction`; chỉ tắt `competing_lessons` khi `f_chunk["scoring_source"]=="cross_encoder"` & `score >= 0.40`. | `M1-T09`, `M2-T05`, `S1-T02`, `test_playground_scenario1_fixes.py` |
| **C4** | Sửa `or → and` ở `classify_contextual` (`PC-02`, V1) | ● | — | — | ○ | — | ○ | Nguy cơ giảm `ARR` trên câu hồi chỉ. | Đã kiểm chứng V1: `ARR = 98.94%`, `Intent = 98.65%` (`0` hồi quy). | Multi-Turn `ARR >= 97.0%`, `test_spec004` |
| **C5** | `verify_in_video_temporal_query` fail-closed + tách nhãn ra manifest (`PC-02`, V1) | ● | — | — | ○ | — | ○ | Từ chối câu mốc thời gian khi model offline thiếu cache. | Đã kiểm chứng V1: `M1..M8` `9/9` PASS, `test_playback_temporal_and_disambiguation.py` PASS. | `M1`, `M2`, `test_playback_temporal_and_disambiguation.py` |
| **C6** | `retrieval_node` nâng cấp đơn điệu `coverage_gap -> Tầng 3` (`PC-03`, V1) | — | — | ○ | ● | ○ | ○ | Tăng False Grounded nếu neo kéo câu ngoài giáo trình. | Chỉ chạy khi `search_query != raw_prompt` (đã qua Topic Shift & Recency Gate); giữ nguyên `is_approximate=True`. | Multi-Turn Pre/Post diff, `test_spec004` |
| **C7** | RRF-fallback trần $R_{\max}^{\star}=1.0$ & dải suy giảm `[0.15, 0.29]` (`PC-04`, V1) | — | — | ● | ○ | ○ | ○ | Dịch chuyển điểm Golden 200 khi `len >= 2`. | Khi `max_rrf - min_rrf > 1e-6` và CE bình thường: giống bit-for-bit công thức cũ (đã chứng minh `199/200` y hệt V1). | Golden 200 CRAG `>= 86.0%`, `test_spec004` |
| **C8-v2** | **Tầng 3 giữ cổng quyết định `video_transcript`-only nhưng ghép `tier3_bound_code_items` (`seq==current`, non-boilerplate, `approx_video_sec!=None`, `score >= 0.22`) qua `assemble_balanced_modality` (`PC-05a`, V2)** | — | — | ● | ○ | — | — | (1) `code_ast` rác `< 0.35` tự kích hoạt `grounded` khi không có video.<br>(2) `code_ast` điểm `0.15..0.21` lọt vào Tầng 3 hoặc kéo `function_main`/bài cũ làm sai mốc video. | (1) Cổng `if low_confidence_items:` **chỉ** xét `video_transcript` → `0` video vẫn trả `coverage_gap` 100%.<br>(2) Ràng buộc 5 lớp: `seq==current`, `scope not in BOILERPLATE_SCOPES`, `approx_video_sec is not None`, **`score >= 0.22`** (chặn 100% `[0.15, 0.22)`). | `BENCH-037` PASS (`5750s`), Golden TS Safety `>= 86.5%`, `test_spec004` (`PC-05a` V1 + V2) |
| **C9** | `_build_lightweight_future_chunk` gắn `is_approximate=True` cho chapter & `00:00` (`PC-05b`, V1) | — | — | ● | ● | ○ | ○ | Mất `has_ts` ở Golden 200 hoặc phá `test_session_7aky9_debug_fixes.py`. | Đã kiểm chứng V1: giữ `start_sec`, đồng bộ `has_approximate`, `0` hồi quy. | `test_session_7aky9_debug_fixes.py`, Golden TS `>= 86.5%` |
| **C10** | Chống lặp `📍` (`PC-05c`) & Critic `Unresolved Nav` (`PC-06`, V1) | — | — | — | — | ● | ● | Phạt nhầm Health Score trên `M1..M8`. | Đã kiểm chứng V1: Health `99..100/100` trên cả 9 suites. | `test_chat_stream.py`, `test_e2e_anti_parroting_and_critic.py`, E2E Health `>= 90` |
| **C11** | **Khóa sắp xếp RRF tất định trước NMS (`limit >= 20` cho future) + sửa `is_future_curriculum_target` (`seq > current`) + Đồng thuận `has_future_topic_signal` cho lượt nối tiếp (`PC-07a/b`, V2)** | — | — | ● | — | — | — | (1) Tăng độ trễ CPU Cross-Encoder nếu nâng `limit` future.<br>(2) Phá điều hướng xuyên khóa `cpp-oop -> cpp-core`.<br>(3) Chặn nhầm ca chuyển bài tương lai thật (`M4-T02`, `S1-T06`, `S1-T07`, `SWITCH-31..40`, `Golden 200`). | (1) Vẫn cắt `[:settings.FUTURE_PROBE_LIMIT]` sau NMS → **0** thêm cặp cho CPU CE.<br>(2) Giữ nguyên `NavBypass` `#L1658-L1662` cho `is_curriculum_navigation=True`.<br>(3) Với đơn lượt (`is_continuation_turn=False`): **bất biến 100%** (`Golden 200` không đổi). Với đa lượt: `has_future_topic_signal` vẫn `True` khi `target==matched` (`M4-T02`, `S1-T06`, `S1-T07`) hoặc `target_has_topical_match` hoặc `max_current_score < 0.22`. | `STRESS-45 T2` `grounded` tất định; `M4-T02 -> 8`, `S1-T06 -> 3`, `S1-T07 -> 43`, `SWITCH-31..40` PASS; Golden `out_of_lesson` không giảm; `test_spec004` (`PC-07a/b`) |
| **C12** | **`retrieval_node` cứu xét `out_of_lesson` không đồng thuận bằng `search_query` khi đạt `grounded` tự tin cao (`PC-07c`, V2)** | ○ | — | ○ | ● | — | — | `anchor_query` từ bài cũ kéo ngược một câu hỏi bài mới (`out_of_lesson` thật) về `grounded` bài cũ. | **Cổng chặn cứng 3 lớp:** Chỉ chạy khi `search_query != raw_prompt` (đã qua `is_context_dependent` & `not is_topic_shift`) **VÀ** `curriculum_matched_seq != target_lesson_seq` (`M4-T02` `8==8`, `S1-T06` `3==3`, `S1-T07` `43==43` bị chặn từ cửa!) **VÀ** chỉ nhận khi `fallback_res.status == "grounded" and not fallback_res.is_low_confidence and max_score >= 0.30`. | `CORE-09 T3`, `OOP-12 T3`, `STRESS-44 T2`, `STRESS-49 T4` phục hồi `grounded`; `E2E Matrix 9/9` PASS; Multi-Turn Status `>= 91.5%`; `test_spec004` (`PC-07c`) |
| **C13** | **Khử `except Exception: pass` (`retrieval.py#L2199-L2200`) & đăng ký `test_spec004_unified_workflow_hardening.py` vào `SEQUENTIAL_PYTEST_SUITES` (`RC-L2-03/04`, V2)** | — | — | ● | — | — | ● | Tăng nhẹ thời gian Gate 2 (~15s). | Chạy cô lập tuần tự cùng `offline_env` (`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`), an toàn tuyệt đối trên RTX 2050 4 GB VRAM. | Gate 1 `0` lỗi; Gate 2 `12/12` suites PASS (`110/110+` tests) |

---

## 7. Kế hoạch Nghiệm thu & Chống Hồi quy (Verification Plan — Vòng #2)

### 7.1. Bộ Unit/Integration Test Spec 004 (`tests/test_spec004_unified_workflow_hardening.py` — `14` Tests)
*(Giữ nguyên 10 tests V1 `PC-01..PC-06`, bổ sung 4 tests mới cho V2 — tuyệt đối `0%` ID `BENCH-`/`SESSION-`, `0%` sao chép nguyên văn đề thi):*
11. `test_pc05a_tier3_preserves_phase2_bound_code_ast_while_blocking_low_code`:
    - Khi Tầng 3 có `video_transcript` Ambiguous (`0.19`) + `code_ast` bound đúng bài phi-boilerplate (`0.33`, `approx_video_sec=5750`) + `code_ast` nhiễu (`0.18`, `approx_video_sec=100`) + `code_ast` `function_main` (`0.34`, `approx_video_sec=50`) $\implies$ `status="grounded"`, `is_low_confidence=True, is_approximate=True`, giữ đúng `code_ast` `0.33` (`5750`), loại cả `0.18` và `function_main`.
12. `test_pc07a_deterministic_rrf_tie_break_and_pre_nms_future_limit`:
    - Truyền danh sách điểm hòa RRF theo 2 thứ tự đảo ngược vào `_sort_rrf_points_deterministically` (`prefer_earlier_seq=True` chọn `min seq`, `prefer_earlier_seq=False` chọn `max seq`, cùng `seq` tie-break theo `str(id)`).
    - Kiểm chứng `_fetch_future_points` gửi `limit >= 20` tới Qdrant và `_score_future_points` vẫn cắt `<= FUTURE_PROBE_LIMIT` trước khi gọi `rerank_documents_async`.
13. `test_pc07b_monotonic_future_target_and_continuation_consensus`:
    - (a) Học viên `cpp-oop` (`L53`) có `curriculum_matched_course="cpp-core", seq=18` $\implies$ `is_future_curriculum_target=False` (Tier-1 Early Exit vẫn hoạt động, không bị bài cũ chặn).
    - (b) Lượt nối tiếp (`is_continuation_turn=True`, `L7`, `max_current=0.29 >= 0.22`) có `curriculum_matched_seq=43` nhưng Qdrant trả `L37` (`video_transcript`, `topical=False`) $\implies$ `has_future_topic_signal=False` $\implies$ `active_continuation_shield=True` $\implies$ `grounded` L7.
    - (c) Đối chứng đồng thuận (`curriculum_matched_seq == target_seq == 8`) trên lượt nối tiếp $\implies$ `out_of_lesson -> L8`.
14. `test_pc07c_retrieval_node_anaphoric_unverified_ool_rescue_and_consensus_guard`:
    - (a) `raw_prompt` trả `out_of_lesson (target=46, matched=27)` + `search_query != raw_prompt` + `fallback_res` trả `grounded (score=0.52, not is_low_confidence)` $\implies$ nhận `grounded`.
    - (b) `raw_prompt` trả `out_of_lesson (target=46, matched=27)` + `fallback_res` trả `grounded (score=0.26 < 0.30)` $\implies$ từ chối, giữ `out_of_lesson`.
    - (c) Đối chứng đồng thuận (`target=8, matched=8`) $\implies$ KHÔNG gọi `fallback_res` lần thứ 2, giữ `out_of_lesson -> 8`.

### 7.2. Cổng Nghiệm thu Toàn Phần (Master Autonomous Harness Gate — Vòng #2)
Chạy tuần tự với `HF_HUB_OFFLINE=1` và `TRANSFORMERS_OFFLINE=1`:
```powershell
.\.venv\Scripts\python.exe scripts\master_autonomous_harness.py --stage 1 --force-eval
```

**Tiêu chuẩn PASS tuyệt đối (`VERDICT: APPROVED`):**
- **Gate 1 (AST + Anti-Bypass Diff):** `0` lỗi cú pháp, `0%` regex / quick-fix / snooping trong `git diff app/`, `0` `except Exception: pass` mới, `0%` test tampering trong `tests/`.
- **Gate 2 (Sequential Pytest — `12/12` Suites):** Toàn bộ `11` suites cũ (`96/96`) + `tests/test_spec004_unified_workflow_hardening.py` (`14/14`) = **`110/110` PASSED, 0 failed, 0 skipped**.
- **Gate 3 (E2E Matrix `--suite all --routing-only`):** **`all_passed: true` (`9/9` suites: `M1..M3`, `S1`, `M4..M8`)**, Critic Health $\ge 90/100$ trên mọi suite.
- **Gate 4 (Macro Benchmarks + Pre/Post Diff so với `scratch/spec004_baseline/`):**
  - **Multi-Turn (`50` sessions / `222` turns):** Intent $\ge 94.0\%$, **Retrieval Status $\ge 90.0\%$** (mục tiêu $\ge 91.5\%$), ARR $\ge 97.0\%$, SRP $= 100.0\%$, Context Budget $= 100.0\%$.
  - **Stage 11 Golden 200:** Router $\ge 90.5\%$, CRAG Precision $\ge 86.0\%$, **Timestamp Safety $\ge 86.5\%$** (`>= 173/200`, khôi phục `BENCH-037`).
