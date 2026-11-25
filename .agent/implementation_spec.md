# ĐẶC TẢ TRIỂN KHAI KỸ THUẬT & TOÁN HỌC — SPEC 004 v2.0 (PSTACK NHỊP 1B — VÒNG LẶP #2)

> **Hệ thống:** In-Course Agentic RAG Copilot — LangGraph Stateful Orchestration  
> **Sinh viên thực hiện:** Trần Thành Nghĩa (MSSV: `23DH112252`), Trường Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT)  
> **Ngày ban hành:** `2026-11-25` | **Base Commit:** `5986d5d` + Working Tree Vòng #1 (`Spec 004 v1.0`)  
> **Vai trò Thiết kế:** `rag-architect` & `solution-analyst`  
> **Đặc tả Nguồn duy nhất (SSOT):** [`specs/004-unified-rag-workflow-hardening/spec.md`](file:///D:/In_Course_Agentic_RAG_Copilot/specs/004-unified-rag-workflow-hardening/spec.md) (`v2.0`)  
> **Cơ sở Kiểm toán Vòng #2:** [`.agent/technical_debt_audit.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/technical_debt_audit.md) & [`.agent/verification_verdict.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/verification_verdict.md)  
> **Kỷ luật bắt buộc cho `@core-coder` (Nhịp 2 Vòng #2):** Cross-Layer Unified Fix | **0% Regex Runtime (`import re`)** | **0% Quick-Fix** | **0% Test-Set Snooping** | **100% Data/Code Separation** | **Giữ nguyên 100% `lessons_manifest.json`, `syllabus_embeddings.npz`, và `scratch/spec004_baseline/`**

---

## 0. RÀNG BUỘC CỨNG & BẢO TOÀN THÀNH QUẢ VÒNG #1

1. **KHÔNG chạy lại Bước 0 Baseline và KHÔNG ghi đè `scratch/spec004_baseline/`:** Bản chụp Baseline tại `HEAD 5986d5d` (`2026-11-25 18:37–18:47`) đã đầy đủ và chính xác.
2. **GIỮ NGUYÊN 100% các bản vá Vòng #1 đã hội tụ:**
   - `app/config.py` (`PARETO_UNRESOLVED_NAV_*`), `data/metadata/router_intent_manifest.json` (`temporal_nli_*`), `app/agent/router.py` (`or -> and` & fail-closed), `app/schemas/chat.py`, `app/services/chat.py` (chống lặp `📍`), `app/services/telemetry_critic.py`, `scripts/e2e_matrix_harness.py`.
   - Trong `app/services/retrieval.py`: giữ nguyên `nav_label_verified_in_window`, `nav_unresolved_self_match`, Pareto 3A-2, `_compute_calibrated_rrf_norm`, degraded `[0.15, 0.29]`, `_build_lightweight_future_chunk` (`is_approximate=True`), `grade_document_relevance` (`code_ast >= 0.35`), và 3 docstring Yan et al. (`arXiv:2401.15884`).
3. **Bảo toàn phần cứng RTX 2050 4 GB VRAM:** Giữ nguyên `onnxruntime-gpu==1.23.2`, Dense E5 trên GPU, `jina-reranker-v2-int8` trên CPU (`USE_CPU_RERANKER=True`, `USE_INT8_RERANKER=True`, `RERANK_CPU_THREADS=4`); chạy kiểm thử tuần tự với `HF_HUB_OFFLINE=1` và `TRANSFORMERS_OFFLINE=1`.

---

## 1. HƯỚNG DẪN TRIỂN KHAI DELTA VÒNG #2 (4 BƯỚC PHỤ THUỘC)

### Bước V2-1 — `app/services/retrieval.py` (`C8-v2`, `C11a`, `C11b`, `C13a`)

1. **Thêm helper `_sort_rrf_points_deterministically` (ngay trước `deduplicate_temporal_candidates` tại [`app/services/retrieval.py#L98`](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L98)):**
   ```python
   def _sort_rrf_points_deterministically(
       points: List[Any],
       *,
       prefer_earlier_seq: bool = True,
   ) -> List[Any]:
       """
       Chuẩn hóa thứ tự tất định cho các ứng viên hòa điểm RRF từ Qdrant Cloud đa phân mảnh.
       - Khi `prefer_earlier_seq=True` (bài học tương lai > current_lesson_seq): ưu tiên `lesson_seq` nhỏ hơn
         theo Prerequisite Order Pareto Invariant (ICLR 2025).
       - Khi `prefer_earlier_seq=False` (cửa sổ bài hiện tại <= current_lesson_seq): ưu tiên `lesson_seq` lớn hơn
         (gần bài hiện tại nhất) để bài nhập môn cũ không đẩy bài hiện tại khỏi lát cắt top_candidates.
       - Khóa phụ `str(hit.id)` loại bỏ hoàn toàn bất định giữa các lần gọi liên tiếp.
       """
       if not points or len(points) <= 1:
           return list(points) if points else []

       def _key(hit: Any) -> Tuple[float, int, str]:
           raw_score = float(getattr(hit, "score", 0.0) or 0.0)
           payload = getattr(hit, "payload", None) or {}
           seq_val = payload.get("lesson_seq")
           if seq_val is not None:
               seq_int = int(seq_val)
               seq_key = seq_int if prefer_earlier_seq else -seq_int
           else:
               seq_key = 9999
           return (-round(raw_score, 6), seq_key, str(getattr(hit, "id", "")))

       return sorted(points, key=_key)
   ```

2. **Nâng `limit` truy vấn thô trước NMS & sắp xếp tất định tại `_fetch_future_points` ([`#L478-L482`](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L478-L482)), `_score_future_points` ([`#L658-L661`](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L658-L661)), và `search` ([`#L1714-L1720`](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L1714-L1720)):**
   - Tại `_fetch_future_points#L479`:
     ```python
     query=models.FusionQuery(fusion=models.Fusion.RRF),
     limit=max(settings.FUTURE_PROBE_LIMIT * 2, 20),
     ```
     và dòng `#L481`:
     ```python
     points = future_resp.points if future_resp and hasattr(future_resp, "points") else []
     return _sort_rrf_points_deterministically(points, prefer_earlier_seq=True)
     ```
   - Tại `_score_future_points#L659-L660`:
     ```python
     future_points = _sort_rrf_points_deterministically(future_points, prefer_earlier_seq=True)
     future_points = deduplicate_temporal_candidates(future_points)
     future_points = future_points[:settings.FUTURE_PROBE_LIMIT]
     ```
     *(Quan trọng: vẫn giữ `[:settings.FUTURE_PROBE_LIMIT]` trước khi gọi CPU Cross-Encoder để không tăng độ trễ!)*
   - Tại `search#L1715`:
     ```python
     raw_candidates = _sort_rrf_points_deterministically(raw_candidates, prefer_earlier_seq=False)
     deduped_candidates = deduplicate_temporal_candidates(raw_candidates)
     ```

3. **Sửa lỗi ngược chiều khóa học ở `is_future_curriculum_target` ([`#L1499-L1506`](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L1499-L1506)):**
   ```python
   is_future_curriculum_target = (
       False
       if is_temporal_current_lesson
       else bool(
           curriculum_matched_seq is not None
           and int(curriculum_matched_seq) > int(current_lesson_seq)
       )
   )
   ```
   *(KHÔNG chạm nhánh `NavBypass` ở `#L1658-L1662` — giữ nguyên hỗ trợ điều hướng xuyên khóa cho `is_curriculum_navigation=True`!)*

4. **Triển khai Đồng thuận Tương lai Liên tầng cho `has_future_topic_signal` ([`#L2070-L2080`](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2070-L2080)):**
   ```python
   is_verified_future_curriculum_signal = bool(
       is_future_curriculum_target
       and (
           not is_continuation_turn
           or max_current_score < settings.PARETO_LOCAL_GROUNDING_THRESHOLD
           or (
               target_seq is not None
               and curriculum_matched_seq is not None
               and int(target_seq) == int(curriculum_matched_seq)
           )
       )
   )
   has_future_topic_signal = bool(
       is_verified_future_curriculum_signal
       or (target_seq is not None and target_seq > current_lesson_seq and target_has_topical_match)
   )
   ```

5. **Khử `except Exception: pass` im lặng ([`#L2199-L2200`](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2199-L2200)):**
   ```python
   except Exception as rev_err:
       logger.debug(f"[RetrievalService:Pareto 3A-2] Lỗi kiểm tra is_revision_of: {rev_err}")
   ```

6. **Đồng bộ `assemble_balanced_modality` cho Phase-2 Bound Code AST ở Tầng 3 ([`#L2368-L2389`](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L2368-L2389)):**
   - Giữ nguyên 100% lọc `content_type == "video_transcript"` của `low_confidence_items` tại `#L2350-L2366` (Decision Gate).
   - Bên trong `if low_confidence_items:` (`#L2368-L2379`), thay thế bằng:
     ```python
     if low_confidence_items:
         tier3_bound_code_items = [
             it for it in candidate_items
             if it.get("content_type") == "code_ast"
             and int(it.get("lesson_seq") or 0) == int(current_lesson_seq)
             and (it.get("code_scope") or "") not in BOILERPLATE_SCOPES
             and it.get("approx_video_sec") is not None
             and it.get("confidence_score", 0.0) >= settings.VIDEO_SCORE_THRESHOLD
         ]
         anchor_candidates = assemble_balanced_modality(
             video_items=low_confidence_items,
             code_items=tier3_bound_code_items,
             final_top_k=final_top_k,
             prefer_balanced=bool(tier3_bound_code_items),
         )
         final_assembled = reorder_lost_in_the_middle(anchor_candidates)
         logger.info(
             f"[RetrievalService] Tầng 3 Graceful Degradation: {len(low_confidence_items)} video chunks "
             f"đạt chuẩn CRAG Ambiguous (+ {len(tier3_bound_code_items)} Phase-2 bound AST, "
             f"max_current={max_current_score:.4f}, max_video={max_video_score:.4f}). "
             f"Gắn cờ is_low_confidence=True, is_approximate=True."
         )
         return RetrievalResult(
             chunks=final_assembled,
             status="grounded",
             is_low_confidence=True,
             is_approximate=True,
             scoring_source=current_scoring_source,
             skip_nav_rerank=skip_nav_rerank,
             curriculum_matched_seq=curriculum_matched_seq,
             curriculum_matched_course=curriculum_matched_course,
         )
     ```

---

### Bước V2-2 — `app/services/chat_graph.py` (`C12`)

Tại `retrieval_node` ([`app/services/chat_graph.py#L763-L791`](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L763-L791)), cập nhật Bước 2 Contextual Fallback:
```python
            # Bước 2: Contextual Fallback khi raw_prompt bị coverage_gap, is_low_confidence,
            # hoặc out_of_lesson thiếu đồng thuận syllabus (anaphoric false-OOL hijack) và search_query != raw_prompt
            is_unverified_anaphoric_ool = bool(
                retrieval_res.status == "out_of_lesson"
                and retrieval_res.curriculum_matched_seq != retrieval_res.target_lesson_seq
            )
            if (
                retrieval_res.status == "coverage_gap"
                or retrieval_res.is_low_confidence
                or is_unverified_anaphoric_ool
            ) and search_query != raw_prompt:
                logger.info(
                    f"[LangGraph:retrieval_node] raw_prompt thiếu thực thể ({retrieval_res.status}, "
                    f"unverified_ool={is_unverified_anaphoric_ool}), "
                    f"kích hoạt Fallback với search_query: '{search_query[:45]}...'"
                )
                try:
                    fallback_res: RetrievalResult = await retrieval_service.hybrid_search(
                        query_text=search_query,
                        course_id=state["course_id"],
                        current_lesson_seq=state["lesson_seq"],
                        top_candidates=settings.DEFAULT_TOP_CANDIDATES,
                        final_top_k=settings.DEFAULT_FINAL_TOP_K,
                        is_curriculum_navigation=False,
                        is_continuation_turn=is_cont_turn,
                        current_video_sec=effective_video_sec,
                    )
                    if retrieval_res.status == "coverage_gap":
                        accept_fallback = fallback_res.status in ("grounded", "out_of_lesson")
                    elif is_unverified_anaphoric_ool:
                        fb_scores = [
                            float(c["confidence_score"])
                            for c in (fallback_res.chunks or [])
                            if c.get("confidence_score") is not None
                        ]
                        fb_high_conf = (not fb_scores) or (
                            max(fb_scores) >= settings.MODALITY_GATE_VIDEO_HIGH_CONFIDENCE
                        )
                        accept_fallback = (
                            fallback_res.status == "grounded"
                            and not fallback_res.is_low_confidence
                            and fb_high_conf
                        )
                    else:
                        accept_fallback = (
                            fallback_res.status in ("grounded", "out_of_lesson")
                            and not fallback_res.is_low_confidence
                        )
                    if accept_fallback:
                        retrieval_res = fallback_res
                except Exception as fb_err:
                    logger.warning(f"[LangGraph:retrieval_node] Lỗi truy xuất Fallback Contextual: {fb_err}")
```

---

### Bước V2-3 — `scripts/master_autonomous_harness.py` (`C13b`) & `tests/test_spec004_unified_workflow_hardening.py`

1. **[`scripts/master_autonomous_harness.py#L375-L387`](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/master_autonomous_harness.py#L375-L387) & [`#L452-L454`](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/master_autonomous_harness.py#L452-L454):**
   - Thêm `"tests/test_spec004_unified_workflow_hardening.py",` vào cuối tuple `SEQUENTIAL_PYTEST_SUITES`.
   - Cập nhật nhãn phase tại `#L454`: `"Gate 2: Sequential Pytest (12 Suites)"`.
2. **[`tests/test_spec004_unified_workflow_hardening.py`](file:///D:/In_Course_Agentic_RAG_Copilot/tests/test_spec004_unified_workflow_hardening.py):**
   - Giữ nguyên toàn bộ `10` unit tests V1 (`PC-01..PC-06`).
   - Bổ sung `4` unit tests khóa `C8-v2`, `C11a`, `C11b`, `C12` theo `specs/004-unified-rag-workflow-hardening/spec.md §7.1` (`#11..#14`), tuyệt đối `0%` ID `BENCH-`/`SESSION-` và `0%` sao chép đề thi.

---

## 2. CHECKLIST NGHIỆM THU CUỐI VÒNG #2 (BÀN GIAO NHỊP 3)
1. Chạy `pytest tests/test_spec004_unified_workflow_hardening.py -v` (`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`) $\implies$ **`14/14 PASSED`**.
2. Chạy `.\.venv\Scripts\python.exe scripts\master_autonomous_harness.py --stage 1 --force-eval` $\implies$ **`exit_code = 0`**:
   - Gate 1: `0` lỗi AST, `0` vi phạm Anti-Bypass Diff, `0` `except Exception: pass` mới.
   - Gate 2: **`12/12` suites PASS** (`110/110` tests, `0` failed, `0` skipped).
   - Gate 3: `E2E Matrix` **`all_passed: true` (`9/9`: `M1..M3`, `S1`, `M4..M8`)**, Health $\ge 90/100$.
   - Gate 4a: Multi-Turn (`50/222`) Intent $\ge 94.0\%$, **Status $\ge 90.0\%$** (dự kiến `91.5%–92.8%`), ARR $\ge 97.0\%$, SRP $= 100.0\%$, Budget $= 100.0\%$.
   - Gate 4b: Stage 11 Golden 200 Router $\ge 90.5\%$, CRAG $\ge 86.0\%$, **Timestamp Safety $\ge 86.5\%$** (`>= 173/200`).
3. Đối chiếu Pre/Post từng lượt giữa `scratch/spec004_baseline/` và kết quả mới, trình `grounding-evaluator` xuất `VERDICT: APPROVED`.
