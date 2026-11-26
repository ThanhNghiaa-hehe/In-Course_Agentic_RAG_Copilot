# BÁO CÁO KIỂM TOÁN NỢ KỸ THUẬT & PHÂN TÍCH NGUYÊN NHÂN GỐC TOÀN LUỒNG
## PSTACK NHỊP 1A — VÒNG LẶP #1 (SPEC 005): ĐỒNG BỘ RUNTIME – TRANSCRIPT SANITIZER – VALIDATOR – GENERATOR – TRAINER (4 MÔ HÌNH)

> **Hệ thống:** In-Course Agentic RAG Copilot — LangGraph Stateful Orchestration & 4-Model Fine-Tuning Pipeline  
> **Sinh viên thực hiện:** Trần Thành Nghĩa (MSSV: `23DH112252`), Trường Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT)  
> **Vai trò thực thi:** `codebase-auditor` (theo [`.agents/agents/codebase-auditor.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agents/agents/codebase-auditor.md)) — **chế độ chỉ đọc 100% trên `app/`, `scripts/`, `tests/`, `data/`, `specs/`**  
> **Thời điểm kiểm toán:** `2026-11-26T12:08+07:00` | **Base Commit:** `31d00d4` + Working Tree hiện tại  
> **Phạm vi truy vết liên tầng:**  
> - **Luồng Runtime E2E:** `IntentRouter (Layer 0a..0d → SLM → NLI Arbiter) → CurriculumService → RetrievalService (In-HNSW + Jina Reranker + Pareto CRAG) → ChatGraph (router_node / retrieval_node / crag_grader_node / context_assembly_node) → ChatService (StreamingSocraticFooterGuard / Whitelist) → TelemetryCritic`  
> - **Luồng Data & AutoML E2E:** `Transcript Chunks (83 bài) → Canonicalizer Sanitizer → Corpus / Manifests → AutoML Dataset Generators → 5-Gate Dataset Validator → Local SLM & Remote Kaggle Trainers (mDeBERTa / Jina / Qwen2.5)`  
> **Nguyên tắc bất biến:** `0%` Regex Runtime (`import re` trong `app/`) | `0%` Quick-Fix | `0%` Test-Set Snooping | `100%` Bảo toàn `chunk_id` / `lesson_seq` / `start_sec` | `100%` Data-Inspected Verification

---

## 0. TÓM TẮT ĐIỀU HÀNH (EXECUTIVE FORENSIC SUMMARY)

Qua truy vết trực tiếp mã nguồn kết hợp đối chiếu thực nghiệm trên **3 bộ kiểm chuẩn Runtime** ([`latest_benchmark_results.json`](file:///D:/In_Course_Agentic_RAG_Copilot/docs/benchmarks/latest_benchmark_results.json), [`multiturn_benchmark_results.json`](file:///D:/In_Course_Agentic_RAG_Copilot/docs/benchmarks/multiturn_benchmark_results.json), [`e2e_matrix_latest_summary.json`](file:///D:/In_Course_Agentic_RAG_Copilot/logs/playground_debug/e2e_matrix_latest_summary.json)) và **4 tập dữ liệu huấn luyện** ([`dataset_validation_report.md`](file:///D:/In_Course_Agentic_RAG_Copilot/docs/benchmarks/dataset_validation_report.md), [`slm_finetune_latest_report.json`](file:///D:/In_Course_Agentic_RAG_Copilot/docs/benchmarks/slm_finetune_latest_report.json), `scratch/kaggle_bundle/*`), kiểm toán viên xác nhận hiện tượng **"False Green" nghiêm trọng ở Validator (`4/4 PASS` ảo)** song song với **3 lỗi cấu trúc ở Runtime** đang kéo `Stage 11 Timestamp Safety` xuống `86.0% (< 86.5% FAIL)`:

| Mã lỗi | Tầng / Tệp nguồn | Hiện trạng Đo lường Thực tế | Bản chất Lỗi Cấu trúc Liên Tầng (Root Cause) | Mức độ |
|---|---|---|---|---|
| **RC-005-01** | **Runtime Router Dead Branch & Uncomputed Guard** ([router.py#L1047-L1123](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L1047-L1123)) | Nhánh `nli_intent == "out_of_scope"` khi `top1_class == "course_query"` bị chết 100% (`0%` kích hoạt); `adversarial_hybrid` đạt `28/40 (70.0%)` | 1. Dòng `#L1110` viết `if nli_conf >= 0.85 and p_oos > p_course:` bên trong `if top1_class == "course_query":` là **bất khả thi đại số** vì `top1_class == "course_query"` $\implies p_{\text{course}} = \max(\mathbf{p}) \ge p_{\text{oos}}$.<br>2. **Bẫy liên tầng ẩn:** Cờ `has_curriculum_topic` tại `#L1048` chỉ được tính khi `top1_class == "out_of_scope" and p_course < 0.16`, nên luôn bằng `False` khi `top1_class == "course_query"`! Nếu không tính lại `has_curriculum_topic` trước khi mở khóa nhánh `#L1110`, câu học tập/ẩn dụ sẽ mất khiên bảo vệ. | **P0** |
| **RC-005-02** | **Runtime Advice Subintent Hijack & Timestamp Safety Gate (`86.0% < 86.5%`)** ([router.py#L406-L427](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L406-L427), [#L624-L652](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L624-L652)) | `Stage 11 TS Safety = 86.0% (172/200)` (**trượt cổng `>= 86.5%` đúng 1 ca**); `chit_chat` trượt 2 ca lời khuyên (`BENCH-173`, `BENCH-174`) dù SLM đạt `p_chit = 0.940` & `0.991`! | Tầng `0c` `is_curriculum_navigation` chạy **trước** SLM (`#L986`). Trong hàm này, cổng cách ly tương phản (`#L624-L645`) chỉ so với `max(sim_soc, sim_sys)` (`greeting/gratitude/goodbye` + `identity/socratic`) mà **bỏ quên hoàn toàn nhóm `"advice"`** đã có trong `self._chitchat_proto_matrix`! Hệ quả: câu xin lời khuyên/động viên học tập (`all_cc_sim = 0.983` & `0.925 > nav_sim = 0.903` & `0.881`) bị cướp sang `course_query` $\implies$ RAG sinh `<timestamp>` sai cho `chit_chat`, làm rớt đồng thời `router_ok`, `status_ok` và `ts_ok` (`-2` ca TS Safety)! | **P0** |
| **RC-005-03** | **Runtime Empty-Fallback Fail-Open Bug** ([chat_graph.py#L793-L805](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L793-L805)) | Rỗng điểm (`fb_scores == []`) vẫn được chấm `fb_high_conf = True` | Dòng `#L798` viết `fb_high_conf = (not fb_scores) or (max(fb_scores) >= settings.MODALITY_GATE_VIDEO_HIGH_CONFIDENCE)` vi phạm nguyên tắc *Zero Fake/Bogus Fallback* (phải fail-closed `bool(fb_scores) and ...`). | **P0** |
| **RC-005-04** | **Transcript Sanitizer Sót Ký Tự Ngoại Lai, Lặp Rác & Hallucination ASCII** ([canonicalize_transcripts_ast.py#L737-L803](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/canonicalize_transcripts_ast.py#L737-L803)) | Quét `83` bài / `6,387` chunks còn sót **`72` mã ký tự lạ**, `5` cụm lặp chữ cách khoảng, `305` cụm lặp từ `3+`, và `39` chunk thuần ASCII/tiếng Anh | `_CORRUPTED_ASR_CHAR_RE` chỉ lọc CJK/Hangul/Cyrillic/Arabic/Thai/FFFD; bỏ lọt Hy Lạp (`39` lần), Do Thái (`21` lần), Tamil/Devanagari (`6` lần), dấu CJK `\u3000-\u303F` (`13` lần), dấu Latin ngoại lai Thổ Nhĩ Kỳ/Bắc Âu/Ba Lan (`ä, ö, ı, İ, ü, å, ç, ş, ż, ę, ß, ø, ğ, ł...`), Emoji (`12` lần), toán học ngoại lai (`₁, ₂, →, ∞, ½, ×, €`), lặp `e e e e`, lặp từ `phim, phim, phim` / `cout, cout, cout`, và câu ảo giác tiếng Anh thuần của Whisper. | **P0** |
| **RC-005-05** | **Rò rỉ Token Containment, Lệch SSOT, Xung đột Solicitation & Stale Audit** ([validate_training_datasets.py#L92-L252](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/validate_training_datasets.py#L92-L252), [finetune_slm_router.py#L96-L290](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/finetune_slm_router.py#L96-L290)) | Validator báo `leaked=0`, nhưng thực tế có **`13–18` mẫu** containment/near-leakage (`>= 0.85`) và câu nhái kịch bản đề thi; `audit=534 != len(samples)=533`; Candidate SLM tụt `87.5% -> 87.0%` | 1. Ba file tự viết hàm lọc rò rỉ riêng, chỉ đo `Jaccard < 0.65` nên câu nối dài từ mẫu (`operator>> trà sữa`, `gcd hòa giải`, `dd/mm/yyyy ngày cưới`, `&& đẹp trai giàu có`, `TinhGPA`) hạ mẫu số hợp để lách Jaccard dù **Containment đạt `0.88–1.00`**!<br>2. `validate_slm_corpus` loại trùng `if nt in seen:` trước khi xét xung đột nhãn; không cập nhật `data["audit"]`.<br>3. Mâu thuẫn nhãn solicitation giữa câu jailbreak gán `out_of_scope` (`#L441, #L449, #L469`) với câu xin code gán `course_query`, cộng thiếu hụt mẫu `contrastive_advice` sạch (`chỉ 4 mẫu`). | **P0** |
| **RC-005-06** | **Điểm Mù Validator "False Green" trên 3 Model Kaggle & Ghi đè Report** ([validate_training_datasets.py#L281-L581](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/validate_training_datasets.py#L281-L581)) | Báo `4/4 PASS` dù NLI có `0` mẫu `neutral`, Jina `490/498` mẫu `> 600` ký tự & `100%` dính `từ khóa:`, Qwen2.5 `0/256` có `?` trước `<timestamp>` & `64/256` kết bằng `!` | - **NLI:** Chỉ kiểm `0 in lbl_dist and 2 in lbl_dist`, bỏ qua mất hẳn lớp `1 (neutral)`, đa entailment và lệch `temporal_nli` (`20:0` / `0:20`).<br>- **Jina:** `if clean_in_place: continue` không loại dòng lỗi ở mode `validate`; trần `1800` thay vì `600`; chặn nhầm intra-lesson hard negative qua `pos.split("|")[0]`.<br>- **Qwen2.5:** Map timestamp gộp toàn cục 83 bài; không kiểm `SOCRATIC_GROUNDED_PROMPT`, ngữ cảnh RAG, dấu `?` trước `<timestamp>`, rò rỉ `bits/stdc++.h`/`cin >>`/`cout <<`, cắt cụt `...`.<br>- **Report:** Chạy `--models <1_task>` ghi đè xóa mất 3 model kia. | **P0** |
| **RC-005-07** | **Lệch Hợp đồng Train–Serve ở Generators & Rò rỉ Chia Tập / Sai Hàm Loss ở Trainers** ([kaggle_automl_runner.py#L115-L362](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/kaggle_automl_runner.py#L115-L362), `scripts/kaggle_jobs/train_*.py`) | Qwen2.5 bỏ rơi **19/83 bài** (`len(kws)<2`, mất trắng Bài `72..83`), `192/256` mẫu cắt cụt `...`, tính loss cả lên `system+user`; NLI & Jina rò rỉ train/val | 1. Generators sinh dữ liệu trái hẳn định dạng runtime (`retrieval.py#L734-L741`, `chat_graph.py#L1095-L1123`, `chat.py#L1529-L1633`).<br>2. Cả 3 script `train_*.py` dùng `random.shuffle` cắt dòng đơn lẻ thay vì `GroupShuffleSplit` theo `premise` / `(query, lesson_seq)` / `lesson_seq`.<br>3. `train_qwen25_qlora.py#L100-L135` gán nhãn lên cả `system+user` rồi truyền `DataCollatorForLanguageModeling(mlm=False)` ghi đè toàn bộ `labels = input_ids`! | **P0** |

---

## 1. ĐỐI CHIẾU ĐỊNH LƯỢNG HIỆN TRẠNG 3 BỘ CHUẨN RUNTIME & 4 DATASET (DATA-INSPECTED)

### 1.1. Hiện trạng 3 Bộ Kiểm Chuẩn Runtime
Nguồn kiểm chứng trực tiếp:
- [`docs/benchmarks/latest_benchmark_results.json`](file:///D:/In_Course_Agentic_RAG_Copilot/docs/benchmarks/latest_benchmark_results.json) (`2026-11-25 20:26:13`)
- [`docs/benchmarks/multiturn_benchmark_results.json`](file:///D:/In_Course_Agentic_RAG_Copilot/docs/benchmarks/multiturn_benchmark_results.json) (`2026-11-25T20:21:12`)
- [`logs/playground_debug/e2e_matrix_latest_summary.json`](file:///D:/In_Course_Agentic_RAG_Copilot/logs/playground_debug/e2e_matrix_latest_summary.json) (`2026-11-25T20:15:48`)

| Bộ kiểm chuẩn | Chỉ số | Hiện trạng | Ngưỡng Cổng (`thinker_doer_pipeline.py`) | Đánh giá Kiểm toán |
|---|---|---:|---:|---|
| **E2E Matrix (`9` suites: `M1..M8, S1`)** | `all_passed` / Health Score | `true` (`9/9`) / `95..100` | `true` (`9/9`) | ✅ Đang xanh — **Bắt buộc bảo toàn 100%** (chú ý `M8-T1` có 1 cảnh báo drift `-15đ`, Health `95`) |
| **Multi-Turn (`50` phiên / `222` lượt)** | Intent Classification Accuracy | `98.65%` (`219/222`) | `>= 94.0%` | ✅ Đạt (`+4.65%`) |
| | Retrieval Status Accuracy | `93.24%` (`207/222`) | `>= 90.0%` | ✅ Đạt (`+3.24%`) |
| | Anaphora Resolution (`ARR`) | `98.94%` (`93/94`) | `>= 97.0%` | ✅ Đạt (`+1.94%`) |
| | Socratic Refusal (`SRP`) | `100.00%` (`15/15`) | `= 100.0%` | ✅ Đạt tuyệt đối |
| | Context Budget (`<= 2400` chars) | `100.00%` (`max 894`) | `= 100.0%` | ✅ Đạt tuyệt đối |
| | Mean Latency | `1325.26 ms` | `<= 7500 ms` | ✅ Đạt |
| **Stage 11 Golden `200`** | Router Accuracy | `93.0%` (`186/200`) | `>= 90.5%` | ✅ Đạt (`in_scope: 80/80`, `out_of_lesson: 40/40`, `adversarial_hybrid: 28/40`, `chit_chat: 38/40`) |
| | CRAG Grader Precision | `87.0%` (`174/200`) | `>= 86.0%` | ✅ Đạt (`+1.0%`) |
| | **Timestamp Safety (Multi-Grounding)** | **`86.0%` (`172/200`)** | **`>= 86.5%` (`>= 173/200`)** | ❌ **ĐANG TRƯỢT CỔNG `-1` CA** (do `12` ca Router sai `OOS/Chit-Chat -> course_query` sinh nhầm `<timestamp>`, đặc biệt 2 ca `advice` `BENCH-173/174`)! |

### 1.2. Hiện trạng 4 Tập Dữ Liệu Huấn Luyện (Bóc trần "False Green")

| Mô hình | Tệp dữ liệu hiện tại | Báo cáo cũ (`dataset_validation_report.md`) | Sự thật Kiểm toán Trực tiếp (Data-Inspected) |
|---|---|---|---|
| **1. `slm_router`** | `data/metadata/router_training_corpus_v2_9_hybrid.json` (`533` mẫu) | `PASS` (`Leaked=0`) | ❌ **13 mẫu** trong `v2.9` (và **17–18 mẫu** trên `base + hard_pool`) vi phạm **Token Containment `>= 0.85`** hoặc nhái thẳng kịch bản đề thi (`operator>>` `1.00`, `dd/mm/yyyy` `0.944`, `advice` `0.923`, `&&` `0.917`, `timestamp` `0.909`, `vector db` `0.909`, `gcd` `0.882`, `TinhGPA` content-containment `1.00`); `audit.total_clean_samples = 534 != 533`; Candidate SLM tụt `87.5% -> 87.0%`. |
| **2. `mdeberta_nli`** | `scratch/kaggle_bundle/mdeberta_nli/dataset/mdeberta_nli_train.jsonl` (`1639` dòng) | `PASS` (`Labels={0:553, 2:1086}`) | ❌ **`0` mẫu `neutral (1)`** (`0.0%` — làm sụp đổ logit lớp 1 của mô hình XNLI 3 lớp!); `temporal_nli` lệch tuyệt đối **`in_video = {2: 20}` (`0:20`)** và **`off_topic = {0: 20}` (`20:0`)**; câu hỏi Python/Java/SQL bị ép gán `label=0 (entailment)` cho giả thuyết `"unrealistic or humorous metaphor..."`! |
| **3. `jina_reranker`** | `scratch/kaggle_bundle/jina_reranker/dataset/jina_reranker_train.jsonl` (`498` dòng) | `PASS` (`FN=0, Garbled=0`) | ❌ **`490/498` (`98.4%`)** vượt trần runtime `600` ký tự (`max=911`); **`498/498` (`100%`)** chèn shortcut `| từ khóa: ...` khớp y hệt từ khóa câu hỏi; **`0` intra-lesson hard negatives**; **`0` `code_ast` chunks**! |
| **4. `qwen25_qlora`** | `scratch/kaggle_bundle/qwen25_qlora/dataset/qwen25_socratic_train.jsonl` (`256` dòng) | `PASS` (`BadTS=0, Openings=78`) | ❌ Bỏ sót **19/83 bài học** (toàn bộ `Bài 72..83` bị mất trắng do `len(kws) < 2`); **`0/256`** dùng `SOCRATIC_GROUNDED_PROMPT`; **`0/256`** có khối `[NGỮ CẢNH BÀI GIẢNG...]`; **`0/256`** có dấu `?` ngay trước `<timestamp>`; **`64/256` (`25%`)** kết thúc bằng dấu cảm thán `nhé!`; **`192/256` (`75%`)** cắt cụt giữa chừng bằng `summary[:130]...`; ghép lỗi compiler theo phép chia dư `idx % 14` lệch hẳn chủ đề bài học! |

---

## 2. PHÂN TÍCH NGUYÊN NHÂN GỐC TỪNG HẠNG MỤC THEO THỨ TỰ PHỤ THUỘC

### 2.1. Hạng mục 1 — Runtime `IntentRouter` & `ChatGraph` (`app/agent/router.py`, `app/services/chat_graph.py`)

#### A. Nhánh Chết Đại Số & Biến Bảo Vệ Chưa Khởi Tạo tại `app/agent/router.py`
- **Vị trí chính xác:** [app/agent/router.py#L1047-L1068](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L1047-L1068) và [app/agent/router.py#L1108-L1123](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L1108-L1123).
- **Truy vết toán học:**
  1. Tại `#L1013-L1021`, `self._classes = ["chit_chat", "course_query", "out_of_scope"]`, `top1_idx = int(np.argmax(probs))` và `top1_class = self._classes[top1_idx]`. Do đó khi `top1_class == "course_query"`, bất đẳng thức $p_{\text{course}} \ge \max(p_{\text{chit}}, p_{\text{oos}})$ luôn đúng tuyệt đối.
  2. Tại `#L1109-L1110`:
     ```python
     elif nli_intent == "out_of_scope":
         if top1_class == "course_query":
             if nli_conf >= 0.85 and p_oos > p_course:
     ```
     Biểu thức `p_oos > p_course` **luôn nhận giá trị `False` (100% thời gian)**! Toàn bộ nhánh lật phán quyết từ `course_query` sang `out_of_scope` khi SLM phân vân là dead code.
  3. **Điểm mù liên tầng cực kỳ nguy hiểm nếu sửa thiếu đồng bộ:** Tại `#L1047-L1061`:
     ```python
     has_curriculum_topic = False
     if top1_class == "out_of_scope" and p_course < 0.16:
         ... # Chỉ tính has_curriculum_topic khi top1_class == "out_of_scope"!
     ```
     Nếu Coder chỉ sửa `#L1110` thành `if ... and not has_curriculum_topic:` mà **không tính `has_curriculum_topic` cho trường hợp `top1_class == "course_query"`**, thì `has_curriculum_topic` luôn là `False`, khiến các câu hỏi ẩn dụ sư phạm hoặc câu hỏi C++ thật bị NLI zero-shot nghi ngờ sẽ mất hoàn toàn lá chắn chủ đề giáo trình!
- **Bằng chứng phân phối xác suất thực tế trên `Golden 200` (Probe trực tiếp):**
  - Toàn bộ các câu `in_scope` / `out_of_lesson` / `adversarial_hybrid (course_query)` mà NLI zero-shot trả `out_of_scope` (`BENCH-052`, `BENCH-102`, `BENCH-123`, `BENCH-144`) đều có **`p_course >= 0.727`, `p_oos <= 0.194`, `margin >= 0.533`**, `nli_conf <= 0.464` (và `BENCH-123`, `BENCH-144` có `has_curriculum_topic = True`).
  - Ngược lại, một câu ngoài lề đánh lừa SLM rơi vào vùng phân vân của `course_query` (`is_ambiguous_slm == True` tại `#L1064-L1066`) luôn có `margin < 0.25` và xác suất cạnh tranh `p_oos >= 0.22` (hoặc `p_oos / p_course >= 0.45`), không chứa AST code C++ của học viên (`not _detect_student_cpp_ast(clean_prompt)`) và không có chủ đề bài học xác thực (`not has_curriculum_topic`).
- **Công thức biên quyết định chuẩn toán học (0% Quick-Fix, 0% Hồi quy `in_scope` / `adversarial_hybrid`):**
  - Tách helper `_has_verified_curriculum_topic(clean_prompt)` (gọi `c_svc.find_lesson_for_query` + `_has_topical_overlap` hoặc `_has_symbol_keyword_match`).
  - Trong `elif nli_intent == "out_of_scope":` -> `if top1_class == "course_query":`:
    1. Tính `topic_verified = has_curriculum_topic or self._has_verified_curriculum_topic(clean_prompt)` và `has_student_code = _detect_student_cpp_ast(clean_prompt)`.
    2. Cho phép NLI bác bỏ `SLM course_query` sang `out_of_scope` khi và chỉ khi đồng thời thỏa mãn:
       - `nli_conf >= 0.80` (NLI tự tin cao là ngoài phạm vi),
       - `p_oos >= 0.22` và `(p_course - p_oos) < 0.25` (SLM thực sự đang phân vân giữa `course_query` và `out_of_scope`, không phải `course_query` tự tin cao và cũng không phải đang phân vân với `chit_chat`),
       - `not topic_verified` và `not has_student_code` (bảo vệ tuyệt đối câu học tập/ẩn dụ gắn giáo trình và câu chứa code C++).

#### B. Lỗi Bỏ Quên Nhóm `"advice"` ở Cổng Cách Ly Tương Phản `is_curriculum_navigation` (Nguyên nhân trực tiếp làm `TS Safety = 86.0% < 86.5%`)
- **Vị trí chính xác:** [app/agent/router.py#L404-L428](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L404-L428) và [app/agent/router.py#L623-L653](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L623-L653).
- **Bằng chứng thực nghiệm (Probe trên toàn bộ `Golden 200` & `9` suites `E2E Matrix`):**
  - Trong `router_intent_manifest.json`, `chitchat_subintents` gồm **6 nhóm**: `greeting`, `gratitude`, `goodbye` (`pure_keys`), `identity_architecture`, `socratic_pedagogy` (`sys_keys`), và **`advice`**.
  - Tại `is_curriculum_navigation` (`#L624-L645`), khi câu hỏi **không có chữ ký điều hướng tường minh (`not has_nav_sig`)**, cổng cách ly tương phản chỉ kiểm tra `max(sim_soc, sim_sys)` mà bỏ rơi nhóm `advice` (dù `self._chitchat_proto_matrix` đã nhúng sẵn cả 6 nhóm ở `#L420`!).
  - Kết quả đo thực tế:
    - Ca hỏi lời khuyên/động viên học tập: `nav_sim = 0.903` & `0.881` (`>= 0.875`), `max(sim_soc, sim_sys) = 0.835` & `0.856`, nhưng **`sim_all_chitchat` trên `_chitchat_proto_matrix` đạt `0.983` và `0.925`** (`>> nav_sim`)! Do bị Tầng `0c` bắt nhầm `is_nav = True`, cả hai câu không bao giờ chạm tới SLM (`p_chit = 0.940` và `0.991`), bị đẩy vào RAG sinh `<timestamp>` sai cho `chit_chat`, trực tiếp kéo `Stage 11 Timestamp Safety` xuống `86.0% (172/200) < 86.5%`!
    - Đối chứng trên **toàn bộ 9 suites `E2E Matrix` (`M1..M8 + S1`)**: Mọi lượt điều hướng thật (`M1-T9`, `M2-T1`, `M2-T4`, `M2-T5`, `M2-T6`, `S1-T2`, `M6-T3`, `M7-T2`, `M8-T3`) đều có `has_nav_sig == True` **và** `nav_sim > sim_all_chitchat` (`all_cc <= 0.860`).
  - **Khắc phục chuẩn Data-Driven (0% Regex, 0% Hardcode):** Trong `is_curriculum_navigation`, tính `sim_chitchat = float(np.max(np.dot(self._chitchat_proto_matrix, qv)))` (khi `self._chitchat_proto_matrix` khả dụng) và dùng `max(sim_soc, sim_sys, sim_chitchat)` tại cổng cách ly `#L645` khi `not has_nav_sig` (cũng như chặn sớm nếu `not has_nav_sig and not has_folded_sig and sim_chitchat >= 0.90 and sim_chitchat > max_sim + 0.02`). Bảo toàn `100%` `E2E Matrix` đồng thời khôi phục `chit_chat` và đưa `Timestamp Safety` vượt ngưỡng `>= 87.0%`!

#### C. Sửa Lỗi Fail-Open Rỗng Điểm tại `app/services/chat_graph.py`
- **Vị trí chính xác:** [app/services/chat_graph.py#L793-L805](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L793-L805).
- **Hiện trạng:**
  ```python
  fb_high_conf = (not fb_scores) or (
      max(fb_scores) >= settings.MODALITY_GATE_VIDEO_HIGH_CONFIDENCE
  )
  ```
- **Khắc phục bắt buộc:** Đổi thành:
  ```python
  fb_high_conf = bool(fb_scores) and (
      max(fb_scores) >= settings.MODALITY_GATE_VIDEO_HIGH_CONFIDENCE
  )
  ```
- **Kiểm tra tương thích test hiện hữu:** Đã kiểm chứng [test_spec004_unified_workflow_hardening.py#L1171-L1184](file:///D:/In_Course_Agentic_RAG_Copilot/tests/test_spec004_unified_workflow_hardening.py#L1171-L1184) (`test_pc07c` đã truyền `"confidence_score": 0.52` và `0.26`). Bổ sung thêm kịch bản kiểm thử `chunks=[]` / thiếu `confidence_score` phải trả `fb_high_conf == False` (giữ nguyên `out_of_lesson`).

---

### 2.2. Hạng mục 2 — Deterministic Sanitizer trong `scripts/canonicalize_transcripts_ast.py`

- **Vị trí chính xác:** [scripts/canonicalize_transcripts_ast.py#L737-L803](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/canonicalize_transcripts_ast.py#L737-L803), `#L1580-L1585`, và `#L2758-L2838`.
- **Kiểm kê dữ liệu thực tế trên 83 tệp `data/transcripts/*/*_chunks.json` (`6,387` chunks):**
  1. **Nhóm chữ viết ngoại lai ngoài hệ Latin (`79` lần xuất hiện):**
     - Hy Lạp (`\u0370-\u03FF`, `\u1F00-\u1FFF`): `ι, ε, α, κ, τ, ο, ρ, λ, έ, ά, ί` (`39` lần — vd `lesson-05 chunk_3034_3101`, `lesson-33 chunk_4326_4388`, `lesson-52 chunk_2139_2203`).
     - Do Thái (`\u0590-\u05FF`): `ל, ז, ה, ו, מ, ס, י, א, נ` (`21` lần — vd `lesson-02 chunk_2042_2106`, `lesson-05 chunk_3358_3471`, `lesson-56 chunk_2223_2284`).
     - Tamil & Devanagari/Indic (`\u0900-\u0DFF`, bao gồm Tamil `\u0B80-\u0BFF`): `ோ, ள, ர, व` (`6` lần — vd `lesson-11 chunk_357_419`, `lesson-12 chunk_1769_1834`, `lesson-29 chunk_1608_1672`).
     - Dấu câu CJK & Halfwidth/Fullwidth (`\u3000-\u303F`, `\uFF00-\uFFEF`): `、, 《, 》, 【` (`13` lần — bị sót do regex cũ bắt đầu từ `\u3040` thay vì `\u3000`).
  2. **Nhóm dấu Latin ngoại lai (Thổ Nhĩ Kỳ / Bắc Âu / Ba Lan / Đức — `110+` lần xuất hiện):**
     - Gồm: `ä (20), ö (16), ı (15), ü (13), å (10), ç (8), ş (8), ż (6), ę (5), ß (4), ø (3), Ö (2), ą (2), ğ (2), ā (2), İ (1), ł (1), š (1), ï (1)`...
     - **CẢNH BÁO BẪY CHẾT NGƯỜI (VIETNAMESE DIACRITIC COLLISION):** Dải Unicode `U+00C0..U+01FF` chứa xen kẽ **chữ quốc ngữ tiếng Việt hợp lệ** (`à, á, â, ã, è, é, ê, ì, í, ò, ó, ô, õ, ù, ú, ý, ă, đ, ĩ, ũ, ơ, ư` và chữ hoa tương ứng). **TUYỆT ĐỐI CẤM** dùng dải regex thô `[\u00C0-\u024F]` để xóa! Bắt buộc khai báo tập hằng bất biến **`VIETNAMESE_NFC_LETTERS`** (đúng 134 chữ cái có dấu tiếng Việt chuẩn NFC + ASCII): mọi ký tự `unicodedata.category(ch).startswith("L")` có `ord(ch) > 127` mà `ch not in VIETNAMESE_NFC_LETTERS` và không thuộc khối chữ tượng hình/ngoại lai khác thì chuyển vị (transliterate/fold) an toàn (`ı->i, İ->I, ł->l, Ł->L, ø->o, Ø->O, ß->ss, æ->ae, œ->oe`, còn lại NFD bỏ dấu `Mn`) hoặc bóc sạch nếu nằm trong token rác ngoại ngữ!
  3. **Emoji & Ký hiệu toán học/tiền tệ ngoại lai (`43` lần xuất hiện):**
     - Emoji & Pictographs (`\U0001F000-\U0001FAFF`, `\u2600-\u27BF`, `\uFE00-\uFE0F`): `📷, 🤟, 😎, ♥, 😃, 🤬` -> xóa thành khoảng trắng.
     - Ký hiệu ngoại lai: `→ (\u2192)` -> `"->"` (hoặc khoảng trắng khi không phải toán tử C++), `× (\u00D7)` -> `"*"`, chỉ số dưới `₁ (\u2081), ₂ (\u2082)` -> `"1", "2"`, và xóa sạch `∞ (\u221E), ½ (\u00BD), € (\u20AC)` cùng các khối Mathematical Operators / Arrows / Currency lạ không thuộc toán tử ASCII C++ (`+ - * / % = < > ! & | ^ ~`).
  4. **Lặp chữ cái cách khoảng & Lặp từ rác Whisper:**
     - Lặp chữ đơn cách khoảng (`>= 4` lần, vd `e e e e e e e e e` tại `lesson-37 chunk_1813_1874`): thu gọn/loại bỏ bằng biểu thức biên từ `(?i)\b([a-z])\s+(?:\1\s+){2,}\1\b`.
     - Lặp từ/cụm rác liên tiếp có hoặc không có dấu phẩy (`>= 3` lần liên tiếp như `phim, phim, phim`, `cout, cout, cout`, `cầm, cầm, cầm, cầm`, `orr, orr, orr`, `trinket, trinket, trinket`, `increase, increase, increase`): thu gọn `w(,? w){2,}` về **1 từ đơn `w`** (giữ lại 1 từ `cout` hoặc từ gốc thay vì xóa trắng cả cụm để không làm gãy câu tiếng Việt tự nhiên như `"nhỏ nhỏ nhỏ"` -> `"nhỏ"`!).
  5. **Chuỗi Whisper Hallucination tiếng Anh / ASCII vô nghĩa (`39` chunk thuần ASCII + câu chèn giữa chunk):**
     - Ví dụ thực tế: `lesson-38 chunk_2190_2257` (`"If you have any question, you can leave feedback in comments below the video..."`), `lesson-24 chunk_1158_1229` (`"When click -> browse -> plus, paus -> slice -> secure -> autopx -> Hoax..."`), `lesson-05 chunk_5025_5098` (`"transfer, Give kick sound Job ije Job Std, DOU-T parish, rade cops..."`).
     - **Ràng buộc bảo toàn siêu dữ liệu (`100% Metadata Immutability`):**
       - Tuyệt đối **KHÔNG xóa phần tử chunk** khỏi mảng JSON; giữ nguyên `100%` `chunk_id`, `start_sec`, `end_sec`, `start_label`, `end_label`, `lesson_seq` và tổng số chunk của từng bài!
       - Lưu ý tại `run_repair_asr_artifacts_cli` ([#L2795](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/canonicalize_transcripts_ast.py#L2795)): hiện tại viết `if cleaned_txt and cleaned_txt != orig_txt:`. Nếu một chunk `100%` là câu rác tiếng Anh của Whisper (như `lesson-38 chunk_2190_2257`), khi lọc sạch câu tiếng Anh mà `cleaned_txt == ""`, điều kiện `if cleaned_txt:` sẽ **bỏ qua không ghi**, để nguyên câu rác tiếng Anh trong file JSON! Do đó, với chunk thuần hallucination tiếng Anh không còn nội dung tiếng Việt, cần giữ lại các từ khóa C++ hợp lệ có trong chunk hoặc đặt chuỗi trung tính tối giản hợp lệ (ví dụ `"[Đoạn thao tác mã nguồn C++ trên màn hình]"`) VÀ ở tầng Generator (`kaggle_automl_runner.py`) chỉ chọn chunk có đủ tỷ lệ từ tiếng Việt chuẩn để sinh mẫu huấn luyện!
       - Khi chạy thử cục bộ ở Nhịp 2: chỉ chạy `.venv\Scripts\python.exe scripts/canonicalize_transcripts_ast.py --repair-asr-artifacts --apply --refresh-chapters` (**KHÔNG** bật `--gemini` và **KHÔNG** bật `--sync-qdrant`).

---

### 2.3. Hạng mục 3 — Thống nhất SSOT Khử Rò rỉ & Vá Toàn Bộ Điểm Mù `scripts/validate_training_datasets.py` + `scripts/finetune_slm_router.py`

#### A. Hợp nhất SSOT `check_decontamination()` (Jaccard `< 0.65` + Token Containment `< 0.85`)
- **Vị trí trùng lặp hiện tại:**
  1. [scripts/validate_training_datasets.py#L92-L108](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/validate_training_datasets.py#L92-L108) (`check_decontamination`)
  2. [scripts/finetune_slm_router.py#L104-L115](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/finetune_slm_router.py#L104-L115) (tự viết lại vòng lặp Jaccard cục bộ)
  3. [scripts/kaggle_automl_runner.py#L68-L73](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/kaggle_automl_runner.py#L68-L73) (`_is_clean_text`)
- **Thiết kế toán học SSOT bắt buộc:**
  - Với tập token chuẩn hóa $T(x) = \text{set}(\text{norm\_text\_for\_jaccard}(x).\text{split}())$, định nghĩa đồng thời:
    $$J(a, h) = \frac{|T(a) \cap T(h)|}{|T(a) \cup T(h)|}, \qquad C(a, h) = \frac{|T(a) \cap T(h)|}{\min(|T(a)|, |T(h)|)} = \max\!\left(\frac{|T(a) \cap T(h)|}{|T(a)|}, \frac{|T(a) \cap T(h)|}{|T(h)|}\right)$$
  - Bổ sung thêm kiểm tra **Content-Token Containment** (loại hư từ hỏi tiếng Việt phổ thông khi cả 2 câu có $\ge 4$ từ nội dung) hoặc ngưỡng `C(a, h) >= 0.85` để bắt trọn cả ca `TinhGPA` (`J = 0.6471`, `C_raw = 0.7857`, **`C_content = 1.000`**!).
  - **Lưu ý 2 biên toán học đã chứng minh thực nghiệm:**
    1. Trong `router_training_corpus.json` ([#L629-L655](file:///D:/In_Course_Agentic_RAG_Copilot/data/metadata/router_training_corpus.json#L629-L655)) có 4 câu chào 1–2 từ (`"Xin chào"`, `"chào"`, `"chào bạn"`, `"hello"`) bị trùng tập con 100% với câu held-out `"Xin chào AI trợ giảng, hôm nay bạn thế nào?"` (`522/522` câu held-out đều có $\ge 4$ từ). Thay các câu 1–2 từ này bằng câu chào tự nhiên $\ge 4$ từ không trùng held-out (vì Tầng 1 `is_pure_social` đã phủ câu chào 1–2 từ bằng vector prototype), giúp công thức `C(a, h) < 0.85` áp dụng **thuần khiết 100% không cần ngoại lệ độ dài**!
    2. Trong `validate_qwen25_jsonl`, `user_msg` sẽ chứa cả `[CÂU HỎI THẮC MẮC CỦA HỌC VIÊN]` lẫn khối `[NGỮ CẢNH BÀI GIẢNG...]` dài hàng trăm từ. Nếu truyền nguyên `user_msg` vào `check_decontamination`, khối transcript dài sẽ (i) làm loãng mẫu số Jaccard che giấu câu hỏi rò rỉ, đồng thời (ii) làm tăng tử số Containment gây báo giả trên các câu held-out ngắn hỏi cùng bài học! Vì vậy `validate_qwen25_jsonl` **BẮT BUỘC** tách riêng phần câu hỏi của học viên (trước `[NGỮ CẢNH` / `[LƯU Ý`) để kiểm tra `check_decontamination`!

#### B. Thanh tra `router_training_corpus.json` & `router_hard_negative_hybrid_pool.json` (Loại bỏ Test-Set Snooping & Xung đột Nhãn)
- **Phát hiện kiểm toán trên dữ liệu gốc:**
  1. **18 mẫu Near-Leakage / Padded Clones trong `router_training_corpus.json` & `hard_pool`:** Các dòng `#L29` (`TinhGPA`), `#L33` (`Euclid gcd`), `#L309-L315` (`TinhGPA ghi-ta`, `chuanHoaThongTin Facebook`), `#L425` (`&& đẹp trai giàu có`), `#L585` (`giải tham chiếu dấu sao dấu và`), `#L1125` (`thời tiết hôm nay thế nào`), `#L1209-L1351` và `#L1425-L1467` (`lẩu sôi const`, `operator>> trà sữa trân châu đường đen`, `constructor quần áo buổi sáng`, `displayInfor rạp chiếu phim`, `gcd hòa giải cãi nhau`, `chieuCao phi công`, `PhanSo mối quan hệ phức tạp`, `std::sort tiệc cưới`, `dd/mm/yyyy kỷ niệm ngày cưới`, `timestamp`, `cơ sở dữ liệu vector`, `mới làm quen C++ lời khuyên`) có cấu trúc nhái sát sạt tập Golden/OOD. Bắt buộc loại bỏ/viết lại sang miền khái niệm tổng quát độc lập hoàn toàn với đề thi!
  2. **Mâu thuẫn nhãn Solicitation:**
     - Các dòng `#L441`, `#L449`, `#L469` trong `router_training_corpus.json` ghép cụm xin giải bài (`"giải hoàn chỉnh bài tập"`, `"viết toàn bộ code C++ giải bài toán"`, `"chép code giải bài tập"`) với câu lệnh prompt injection rồi gán nhãn `out_of_scope`, xung đột trực diện trong không gian E5 với nhóm câu học viên xin code hoàn chỉnh gán nhãn `course_query` (`#L445, #L457, #L465, #L481, #L1933-L1995`). Trong kiến trúc thực tế, prompt injection đã bị `SecurityInputGuardrail` chặn ở Tầng `0a` trước SLM; tập huấn luyện SLM chỉ nên giữ các câu jailbreak thuần bảo mật/hệ thống cho `out_of_scope` và giữ nhất quán mọi câu xin giải bài tập C++ là `course_query` (để vào RAG từ chối theo Socratic)!
     - Ba câu hỏi meta về phương pháp Socratic (`router_training_corpus.json#L1397, #L1877` và `router_hard_negative_hybrid_pool.json#L238`) chứa chuỗi con `"giải hộ"`, `"viết sẵn"`, `"viết hộ"` trùng khớp `solicitation_words` khiến `router.py#L1032` (`not has_solicitation`) khóa nhầm cổng `socratic_pedagogy`. Cần diễn đạt sạch câu meta-pedagogy trong corpus/pool và bổ sung cân đối **`contrastive_advice` sạch** (`12–18` mẫu đa dạng về phương pháp tự học, quản lý thời gian ôn tập, vượt tâm lý sợ code, định hướng rèn tư duy) để cân bằng 3 lớp!
  3. **Sửa lỗi `validate_slm_corpus` & `finetune_slm_router.py`:**
     - Trong `validate_slm_corpus` ([#L169-L188](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/validate_training_datasets.py#L169-L188)): lưu `seen_norm_to_intent: Dict[str, str]` để bắt `exact_duplicate_label_conflicts` **trước khi** `continue` loại trùng; cập nhật lại `data["audit"]` khớp chính xác `len(clean_rows)` và `class_distribution`.
     - Trong `finetune_slm_router.py` ([#L280-L290](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/finetune_slm_router.py#L280-L290)): sau khi loại `conflict_drops`, bắt buộc ghi đồng bộ lại cả `samples` lẫn `audit` vào `router_training_corpus_v2_9_hybrid.json`!

#### C. Đặc tả Khóa Toàn Bộ Điểm Mù trong `scripts/validate_training_datasets.py`
1. **`validate_mdeberta_jsonl` ([#L281-L334](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/validate_training_datasets.py#L281-L334)):**
   - Nạp trực tiếp `router_intent_manifest.json` lấy đúng 3 `main_hypotheses` và 2 `temporal_hypotheses`. Mọi dòng có `hypothesis` lạ -> tăng `bad_hypothesis_count` (`HARD FAIL`).
   - Bắt buộc có đủ cả 3 nhãn `{0, 1, 2}` và cân bằng hợp lý (mỗi nhãn `>= 12%` tổng mẫu; tỷ lệ `max_lbl / min_lbl <= 4.0`).
   - Gom theo `norm_premise` trên nhóm 3 `main_hypotheses`: nếu 1 `premise` có `>= 2` dòng mang `label == 0 (entailment)` -> tăng `multi_entailment_count` (`HARD FAIL`).
   - Kiểm tra riêng 2 `temporal_hypotheses` (`in_video`, `off_topic`): mỗi giả thuyết bắt buộc có mặt cả nhãn `0 (entailment)` lẫn `2 (contradiction)` (và có `1 (neutral)`), tỷ lệ lệch không vượt quá `3:1` (chặn đứng lỗi `20:0` / `0:20`).
2. **`validate_jina_jsonl` ([#L337-L419](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/validate_training_datasets.py#L337-L419)):**
   - **Luôn lọc & đếm dòng nhiễu ở cả 2 mode `validate` và `clean`** (xóa bỏ `if clean_in_place:` ở `#L365` và `#L369`; `passed` yêu cầu mọi bộ đếm lỗi `== 0`).
   - Kiểm tra `len(pos) <= 600` và `len(neg) <= 600` (`settings.RERANK_MAX_CHARS = 600`).
   - Kiểm tra định dạng dòng đầu khớp 100% runtime: bắt đầu bằng `[Bài giảng Video ` (có ` mốc `) **hoặc** `[Mã nguồn ` (`[Mã nguồn CPP - ...]\n`), và **cấm tuyệt đối** chứa `| từ khóa:` hay `từ khóa:` trên dòng tiêu đề (`header_shortcut_count == 0`).
   - **HARD FAIL** nếu `pos` hoặc `neg` dính `_contains_corrupted_asr_artifacts` mở rộng (chữ ngoại lai, dấu Latin ngoại lai, Emoji, ký hiệu toán lạ, lặp chữ `e e e e`, lặp từ `3+`, hoặc câu hallucination tiếng Anh thuần ASCII). Riêng từ đồng âm tiếng Việt theo ngữ cảnh trong `cpp_academic_glossary.json["asr_phonetic_glossary"]` (`cốt`, `vòng lập`, `mạng một chiều`...) ghi nhận vào trường cảnh báo telemetry `asr_homophone_warnings` (không đánh trượt Chặng 1 deterministic để xử lý tiếp ở Chặng 2 `--gemini`).
   - Cập nhật kiểm tra False-Negative để **hỗ trợ Intra-Lesson Hard Negatives**: cấm `pos` và `neg` trùng cùng mốc giây trong cùng bài (hoặc cùng `code_scope` trong cùng bài), và yêu cầu `neg_overlap <= pos_overlap` (không cấm cùng tên video bài giảng khi khác mốc thời gian xa!).
3. **`validate_qwen25_jsonl` ([#L421-L496](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/validate_training_datasets.py#L421-L496)):**
   - Đổi `load_valid_lesson_timestamps()` sang **ánh xạ theo từng bài học `Dict[int, Dict[int, str]]`** (`lesson_seq -> {sec: "MM:SS"}`, hợp nhất từ `lessons_manifest.json["video_chapters"]`, `data/transcripts/*/*_chunks.json`, và `data/metadata/lesson_code_video_binding.json`). Đối chiếu `<timestamp sec="S">MM:SS</timestamp>` trong `assistant` phải khớp đúng `lesson_seq` trích từ khối ngữ cảnh của `user` (và đúng nhãn `MM:SS`)!
   - Bắt buộc `messages[0]["role"] == "system"` và `messages[0]["content"] == SOCRATIC_GROUNDED_PROMPT`.
   - Bắt buộc `user` chứa khối ngữ cảnh RAG thật (`[NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC]`), và chạy `check_decontamination` trên phần câu hỏi học viên tách khỏi khối ngữ cảnh RAG.
   - Kiểm tra `assistant` kết thúc bằng đúng 1 câu hỏi Socratic kết thúc bởi dấu `?` ngay trước footer `📍 **Mốc video bài giảng:** <timestamp ...>` (hoặc thẻ `<timestamp ...>` cuối bài); **HARD FAIL** nếu kết câu trước timestamp bằng `!`, thiếu `?`, có câu kết sáo rỗng trong `forbidden_closing_prefixes`, hoặc đặt câu hỏi sau thẻ `<timestamp>`!
   - Mở rộng chặn rò rỉ code giải: cấm `#include` (bao gồm `#include <bits/stdc++.h>`, `#include <iostream>`), `using namespace std`, `int main`, `void main`, `signed main`, `return 0;`, `cin >>`, `cout <<`.
   - Chặn cắt cụt giữa từ / dấu ba chấm lười (`"..." in asst_msg` hoặc `"…" in asst_msg`).
   - Đo đa dạng mở đầu thật sau khi chuẩn hóa/loại bỏ tiền tố tên bài `Bài \d+(: ...)?` trên cả câu hỏi `user` và câu mở đầu `assistant` (yêu cầu phủ đủ `83/83` bài học!).
4. **`run_validation` ([#L544-L581](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/validate_training_datasets.py#L544-L581)):**
   - Khi truyền `--models` chỉ lọc một tập con model, đọc `dataset_validation_report.json` hiện có (nếu tồn tại), cập nhật (merge) các model vừa chạy vào từ điển `models`, tính lại `all_passed` trên đủ 4 khóa chuẩn `("slm_router", "mdeberta_nli", "jina_reranker", "qwen25_qlora")`, rồi mới xuất JSON và Markdown!

---

### 2.4. Hạng mục 4 — Dataset Generators (`scripts/kaggle_automl_runner.py`) & Kaggle Trainers (`scripts/kaggle_jobs/`)

1. **`build_mdeberta_nli_dataset` ([kaggle_automl_runner.py#L115-L150](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/kaggle_automl_runner.py#L115-L150)):**
   - Khớp nguyên văn `nli_template`, `nli_hypotheses`, `temporal_nli_template`, `temporal_nli_labels` từ `router_intent_manifest.json`.
   - Phân biệt bản chất ngữ nghĩa khi sinh nhãn `0 / 1 / 2`:
     - Với câu hỏi lập trình **ngôn ngữ ngoài khóa học** (`Python`, `Java`, `Node.js`, `PostgreSQL`, `React`, `Docker`, `CSS`, `Kubernetes`): `course_query` (`C++`) = `2 (contradiction)`, `chit_chat` = `2 (contradiction)`, còn `out_of_scope` (`"unrealistic or humorous metaphor, everyday life question, or off-topic conversation"`) nhận **`1 (neutral)`** ở một phần mẫu biên kỹ thuật hoặc bổ sung các cặp `neutral (1)` chuẩn xác: (i) câu ẩn dụ sư phạm C++ đối chiếu với giả thuyết `out_of_scope` -> `1 (neutral)`; (ii) câu tâm sự/xin lời khuyên học C++ (`advice`) đối chiếu với giả thuyết `course_query` -> `1 (neutral)`; (iii) câu hỏi khái niệm C++ không đề cập thời gian video đối chiếu với giả thuyết `temporal in_video` -> `1 (neutral)`. Đảm bảo 0% multi-entailment ở 3 intent chính và tỷ lệ lớp `1 (neutral)` đạt `~20%–30%`.
     - Sinh bộ mẫu `temporal_nli` cân bằng hoàn toàn trên cả 2 giả thuyết `in_video` và `off_topic` (cả câu hỏi mốc phút/đoạn video bài giảng thật -> `in_video=0, off_topic=2`; câu đời sống có từ thời gian/vị trí như bóng đá, nấu ăn, thời tiết -> `off_topic=0, in_video=2`; câu trung lập không rõ ngữ cảnh -> `1`), xóa sổ hoàn toàn lệch `20:0` / `0:20`.
2. **`build_jina_reranker_dataset` ([kaggle_automl_runner.py#L153-L239](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/kaggle_automl_runner.py#L153-L239)):**
   - Định dạng passage khớp **100% bit-for-bit** với [app/services/retrieval.py#L734-L741](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/retrieval.py#L734-L741) & `#L1797-L1815`:
     - Video transcript: `truncate_rerank_text(f"[Bài giảng Video {vid_title} mốc {start_lbl}]\n{clean_txt}", max_chars=600)` (dùng đúng `vid_title = f"{folder_name}.mp4"` như `canonicalize_transcripts_ast.py#L2386`, tuyệt đối **không** có `| từ khóa:`).
     - Code AST: đọc từ `data/sample_codes/*/*_ast_chunks.json` và các file `.cpp` qua `extract_cpp_ast_symbols`, định dạng `truncate_rerank_text(f"[Mã nguồn CPP - {code_scope}]\n{ctx_code}", max_chars=600)`.
   - Sinh `query` bám sát nội dung thực sự xuất hiện trong `pos_passage` (trích cụm thuật ngữ/định danh AST/khái niệm thực tế trong chính đoạn chunk đó, khử nhiễm qua SSOT `check_decontamination`), **không** ghép máy móc `title + kws[:3]` của cả bài.
   - Kết hợp **3 loại negative chất lượng cao**: (a) **Intra-lesson hard negatives** (chunk khác phân đoạn cách xa `>= 90s` trong cùng bài học không chứa cụm khái niệm đang hỏi), (b) **Cross-lesson hard negatives** (bài học lân cận cùng khóa nhưng khác chủ đề), và (c) **Cross-modality / `code_ast` triplets**. Lưu kèm `"lesson_seq"` trong mỗi dòng JSONL phục vụ `GroupShuffleSplit`.
3. **`build_qwen25_socratic_dataset` ([kaggle_automl_runner.py#L241-L362](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/kaggle_automl_runner.py#L241-L362)):**
   - **Phủ đủ 100% (`83/83`) bài học:** Xóa điều kiện `if len(kws) < 2: continue` tại `#L295` (nguyên nhân làm rớt 19 bài: `17, 19, 33, 39, 40, 42, 51, 72..83`). Với bài chỉ có 1 keyword trong manifest, tự động trích thêm khái niệm từ `title`, `extract_lesson_lexicon(course_id, seq)` và nội dung chunk đã làm sạch.
   - `messages[0]["content"] = SOCRATIC_GROUNDED_PROMPT` (bảo toàn 100% hợp đồng runtime + KV Prefix Cache).
   - `messages[1]["content"]` đóng gói đúng chuẩn `crag_grader_node` ([chat_graph.py#L1120-L1123](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L1120-L1123)) và `_format_context_block` (`#L168-L201`):
     ```text
     [CÂU HỎI THẮC MẮC CỦA HỌC VIÊN]
     {user_q}

     [NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC]
     Nguồn Bài {seq} (mốc <timestamp sec="{sec}">{lbl}</timestamp>): {clean_excerpt}
     ```
     *(cắt `clean_excerpt` tại ranh giới câu/từ trọn vẹn `<= 380` ký tự, không sinh `...` cắt giữa từ).*
   - `messages[2]["content"]` tuân thủ tuyệt đối `SOCRATIC_GROUNDED_PROMPT` + `StreamingSocraticFooterGuard` ([chat.py#L1529-L1633](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat.py#L1529-L1633)):
     - Mở đầu đa dạng đi thẳng vào bản chất kỹ thuật (0% `"Chào bạn!"`, 0% cắt cụt `...`, 0% `#include` / `int main` / `cin >>` / `cout <<`, chỉ dùng mã giả hoặc biểu thức ngắn hợp lệ khi cần).
     - Kết thúc phần văn xuôi bằng **đúng 1 câu hỏi Socratic định hướng tư duy có dấu `?`**, ngay sau đó là dòng footer chuẩn:
       `\n\n📍 **Mốc video bài giảng:** <timestamp sec="{sec}">{lbl}</timestamp>`
   - **Ghép lỗi Compiler theo Chủ đề Bài học (Cấm `%`):** Ánh xạ ngữ nghĩa `category` / `target_concepts` trong `compiler_diagnostics_manifest.json` vào đúng nhóm bài học tương ứng (vd: `redeclaration_conflict`, `lvalue_assignment`, `undeclared_identifier`, `syntax_missing_token` -> Bài nhập môn/biến `1..3`; `division_by_zero` -> Toán tử Bài `3`; `switch_datatype_constraint` -> Rẽ nhánh Bài `4, 5, 78`; `break_outside_loop` -> Vòng lặp Bài `6`; `overloaded_ambiguous` -> Hàm Bài `7, 8`; `array_out_of_bounds_segfault`, `variable_length_array_init` -> Mảng Bài `11..19, 67`; `pointer_type_conversion`, `null_pointer_dereference` -> Con trỏ/DSLK Bài `57, 58, 79, 81`; `class_struct_member_access` -> Struct/OOP Bài `50..56, 69, 75, 83`). Lưu kèm `"lesson_seq": seq` ở cấp ngoài JSONL.
4. **3 Kaggle Trainers trong `scripts/kaggle_jobs/`:**
   - [train_mdeberta_nli.py#L85-L89](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/kaggle_jobs/train_mdeberta_nli.py#L85-L89): Thay `random.shuffle` bằng `GroupShuffleSplit(n_splits=1, test_size=0.10, random_state=seed)` nhóm theo `premise` chuẩn hóa; bổ sung `macro_f1` vào `compute_metrics`.
   - [train_jina_reranker.py#L132-L135](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/kaggle_jobs/train_jina_reranker.py#L132-L135): Thay `random.shuffle` bằng `GroupShuffleSplit(n_splits=1, test_size=0.10, random_state=seed)` nhóm theo khóa `(norm_query, lesson_seq)`.
   - [train_qwen25_qlora.py#L97-L135](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/kaggle_jobs/train_qwen25_qlora.py#L97-L135):
     1. Chia train/val bằng `GroupShuffleSplit(n_splits=1, test_size=0.10, random_state=seed)` nhóm theo `lesson_seq` (trích từ trường `"lesson_seq"` hoặc `Nguồn Bài \d+` trong `user`).
     2. **Sửa hàm `_tokenize` & Collator để chỉ tính Loss trên token `assistant`:**
        - Render prefix `prompt_text = tokenizer.apply_chat_template(example["messages"][:2], tokenize=False, add_generation_prompt=True)` và full `full_text = tokenizer.apply_chat_template(example["messages"], tokenize=False, add_generation_prompt=False)`.
        - Tokenize không pad trước (hoặc đo `prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]`, `full_ids = tokenizer(full_text, truncation=True, max_length=1536, add_special_tokens=False)["input_ids"]` — lưu ý tăng `max_length` lên `1536` hoặc `2048` vì `SOCRATIC_GROUNDED_PROMPT` + RAG context + assistant câu trả lời dài `~950–1,250` tokens, nếu để `max_length=1024` sẽ cắt cụt mất phần `assistant` và thẻ `<timestamp>` ở cuối!!).
        - Đặt `labels = [-100] * mask_len + full_ids[mask_len:]` (kiểm chứng `any(x != -100 for x in labels)` trên mọi mẫu!).
        - Thay `DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)` bằng `DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model, label_pad_token_id=-100, pad_to_multiple_of=8)` (hoặc custom tensor collator giữ nguyên `labels` và pad bằng `-100`), **tuyệt đối không để collator ghi đè `labels` bằng `input_ids`**!

---

## 3. KIỂM TOÁN LIÊM CHÍNH MÃ NGUỒN & VỆ SINH KỸ THUẬT HIỆN TẠI

| Tiêu chí Kiểm toán | Trạng thái hiện tại | Nhận xét & Ràng buộc cho Nhịp 1B / Nhịp 2 |
|---|---|---|
| **Zero-Regex Runtime (`app/`)** | ✅ **PASS** | `0` lệnh `import re` trong toàn bộ `app/`. Mọi thay đổi tại `app/agent/router.py` và `app/services/chat_graph.py` ở Nhịp 2 **bắt buộc giữ nguyên `0%` regex**. (Regex chỉ được phép dùng trong các script offline `scripts/`). |
| **Zero Test-Set Snooping (`app/`, `data/`)** | ⚠️ **CẦN LÀM SẠCH Ở `data/metadata/`** | `app/` sạch `100%`, nhưng `router_training_corpus.json` đang chứa các câu nhái kịch bản `Golden 200` (`#L29`, `#L309-L315`, `#L425`, `#L1281-L1467`). Phải khử sạch ở Nhịp 2 bằng SSOT `check_decontamination` + viết lại câu tổng quát. |
| **`TelemetryCritic` Self-Flattery Audit** | ✅ **PASS** | [`app/services/telemetry_critic.py`](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py) kiểm tra chặt AST `#include`/`main()`, dấu `?` trước footer `📍`, Whitelist `<timestamp>`, False Student Attribution và Cross-Lesson Drift. |
| **Harness Suite Registration** | ⚠️ **CẦN CẬP NHẬT KHI THÊM TEST MỚI** | [`scripts/master_autonomous_harness.py#L375-L388`](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/master_autonomous_harness.py#L375-L388) hiện đăng ký `12` suites tuần tự. Khi bổ sung file unit test mới khóa Spec 005 (vd `tests/test_spec005_unified_dataset_workflow.py`), cần đăng ký vào `SEQUENTIAL_PYTEST_SUITES` (nâng lên `13` suites). |

---

## 4. MA TRẬN CHỐNG XUNG ĐỘT LIÊN TẦNG ĐỀ XUẤT CHO SPEC 005 (`C005-01` .. `C005-08`)

`rag-architect` và `solution-analyst` trong **Nhịp 1B** cần đưa đầy đủ 8 ràng buộc khóa xung đột sau vào [`specs/005-unified-dataset-workflow-repair/spec.md`](file:///D:/In_Course_Agentic_RAG_Copilot/specs/005-unified-dataset-workflow-repair/spec.md):

| Mã | Hạng mục Sửa đổi | Nguy cơ Xung đột Chéo Tiềm ẩn | Cơ chế Phòng ngừa Bắt buộc trong Spec 005 | Kiểm chứng Khóa Hồi quy |
|---|---|---|---|---|
| **C005-01** | Mở khóa nhánh `nli_intent == "out_of_scope"` khi `top1_class == "course_query"` tại `router.py#L1109-L1123` | NLI zero-shot nhầm câu `in_scope` (`BENCH-052`), `out_of_lesson` (`BENCH-102`) hoặc ẩn dụ sư phạm (`BENCH-123`, `BENCH-144`) sang `out_of_scope` do `has_curriculum_topic` chưa được tính. | Tính `topic_verified = has_curriculum_topic or _has_verified_curriculum_topic(clean_prompt)` + `not _detect_student_cpp_ast(clean_prompt)` + yêu cầu SLM thực sự phân vân (`p_oos >= 0.22`, `p_course - p_oos < 0.25`, `nli_conf >= 0.80`). | `in_scope = 80/80`, `out_of_lesson = 40/40`, `adversarial_hybrid` không tụt, unit test mới cho cả 2 chiều (OOS override vs curriculum/metaphor shield). |
| **C005-02** | Bổ sung nhóm `"advice"` (`_chitchat_proto_matrix`) vào cổng cách ly tương phản của `is_curriculum_navigation` (`router.py#L624-L652`) | Chặn nhầm các câu điều hướng lộ trình thật sự (`"mới bắt đầu học C++ thì học bài nào trước"`, `M1-T9`, `M2-T1..T6`, `S1-T2`, `M6-T3`, `M7-T2`, `M8-T3`). | Chỉ kích hoạt chặn tương phản `sim_chitchat` khi **không có chữ ký điều hướng tường minh (`not has_nav_sig`)** và `sim_chitchat >= max_sim - 0.02`. Mọi câu có `"bài nào"`, `"bài mấy"`, `"lộ trình học"`, `"bắt đầu từ đâu"` (`has_nav_sig=True`) giữ nguyên 100%! | `E2E Matrix 9/9 PASS`, `chit_chat` lên `40/40`, `Stage 11 TS Safety >= 87.0% (>= 86.5%)`. |
| **C005-03** | Sửa `fb_high_conf = bool(fb_scores) and ...` tại `chat_graph.py#L798` | Phá vỡ cứu xét đại từ hồi chỉ hợp lệ (`CORE-09 T3`, `OOP-12 T3`, `STRESS-44 T2`, `STRESS-49 T4`) nếu chunk hợp lệ thiếu trường `confidence_score`. | Mọi chunk từ `RetrievalService.hybrid_search` đều gán `confidence_score`; chỉ từ chối khi `chunks == []` hoặc `max(fb_scores) < 0.30`. | `test_spec004_unified_workflow_hardening.py` PASS + unit test mới `fb_scores == [] -> False` + Multi-turn Status `>= 90.0%`. |
| **C005-04** | Mở rộng Sanitizer Deterministic tại `canonicalize_transcripts_ast.py` & chạy `--repair-asr-artifacts --apply --refresh-chapters` | 1. Regex dải Latin xóa nhầm dấu tiếng Việt.<br>2. Xóa trắng chunk thuần ASCII làm rỗng `raw_text` hoặc làm lệch `start_sec` / `video_chapters`. | 1. Dùng tập hằng `VIETNAMESE_NFC_LETTERS` bảo vệ tuyệt đối 134 chữ cái tiếng Việt có dấu.<br>2. Giữ nguyên 100% số lượng chunk, `chunk_id`, `start_sec`, `end_sec`; nếu chunk bị rỗng sau khi bóc câu tiếng Anh ảo giác thì gán nhãn mô tả trung tính hợp lệ, không để lọt câu rác cũ. | `test_unseen_edges_and_canonicalizer.py` PASS; kiểm đếm `0` ký tự Hy Lạp/Do Thái/Tamil/Latin lạ/Emoji trên toàn bộ `83` bài; `Stage 11` & `Multi-Turn` không hồi quy. |
| **C005-05** | Hợp nhất SSOT `check_decontamination` (Jaccard `< 0.65` + Containment `< 0.85`) & làm sạch SLM Corpus + Re-train SLM | 1. Câu chào ngắn 1–2 từ bị dính containment `1.0` với câu dài.<br>2. `validate_qwen25_jsonl` kiểm containment lên cả khối RAG context gây báo giả.<br>3. SLM mới làm xê dịch xác suất trên `Golden 200` / `E2E Matrix`. | 1. Chuẩn hóa câu chào trong corpus thành $\ge 4$ từ; tách riêng câu hỏi `user` khỏi khối `[NGỮ CẢNH BÀI GIẢNG...]` khi kiểm rò rỉ Qwen2.5.<br>2. Chỉ promote `slm_router_int8.onnx` khi vượt/giữ vững cổng đánh giá trên Golden 200 & OOD 100, hoặc kiểm chứng trực tiếp bằng Stage 1 Harness! | `validate_training_datasets.py --with-e5` báo `slm_router: PASS (leaked=0, fatal_conflict=0, audit khớp 100%)`; `Golden Router >= 93.0%`. |
| **C005-06** | Chuẩn hóa `build_jina_reranker_dataset` (`<= 600` chars, không `từ khóa:`) + Intra-Lesson Hard Negatives + `validate_jina_jsonl` | Luật cũ `pos.split("|")[0] == neg.split("|")[0]` đánh trượt nhầm toàn bộ Intra-Lesson Hard Negatives cùng bài học! | Thay kiểm tra tiêu đề thô bằng kiểm tra khác mốc thời gian (`abs(sec_pos - sec_neg) >= 90` hoặc khác `code_scope`) + `neg_overlap <= pos_overlap`. | `jina_reranker` đạt `PASS` với `0` mẫu `> 600` chars, `0` `từ khóa:`, có đủ cả intra-lesson hard negatives và `code_ast` triplets. |
| **C005-07** | Viết lại `build_qwen25_socratic_dataset` (83 bài, `SOCRATIC_GROUNDED_PROMPT`, RAG context, `?` trước `📍 <timestamp>`) | `SOCRATIC_GROUNDED_PROMPT` (~850 tokens) + RAG context (~250 tokens) + Assistant (~200 tokens) vượt quá `max_length = 1024` trong `train_qwen25_qlora.py#L99` làm cắt mất thẻ `<timestamp>` và làm toàn bộ `labels == -100` (`loss = NaN`)! | 1. Giữ tổng độ dài ký tự `messages` gọn (`clean_excerpt <= 360` chars).<br>2. Nâng `max_length` trong `train_qwen25_qlora.py` lên **`2048`** (`Qwen2.5-7B` hỗ trợ 32k, 4-bit LoRA batch=1 với `2048` chỉ tốn ~6.5 GB trên T4 16 GB!) và kiểm tra `any(l != -100)` trước khi đưa vào `Dataset`! | `qwen25_qlora` phủ đủ `83/83` bài, `100%` có `?` trước `<timestamp>`, `0%` cắt cụt `...`, `0%` code leak, `labels = -100` cho `system+user` giữ nguyên qua collator. |
| **C005-08** | Merge báo cáo trong `run_validation` khi truyền `--models` | Chạy đơn lẻ 1 model ghi đè mất kết quả 3 model còn lại hoặc báo `all_passed=True` khi mới kiểm 1/4 model. | Merge vào `existing["models"]` và chỉ đặt `all_passed = True` khi đủ cả 4 model chuẩn đều có `passed == True`. | Unit test kiểm chứng chạy `--models jina_reranker` không làm mất `slm_router`, `mdeberta_nli`, `qwen25_qlora` trong `dataset_validation_report.{json,md}`. |

---

## 5. THỨ TỰ THỰC THI BẮT BUỘC CHO NHỊP 1B (`THINKER`) & NHỊP 2 (`CODER`)

1. **Bước 1 — Thiết kế Spec 005 hoàn chỉnh (Nhịp 1B):**
   - Hoàn thiện [`specs/005-unified-dataset-workflow-repair/spec.md`](file:///D:/In_Course_Agentic_RAG_Copilot/specs/005-unified-dataset-workflow-repair/spec.md), đồng bộ [`.agent/implementation_spec.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/implementation_spec.md) và [`.agent/task_plan.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/task_plan.md) khóa chặt `RC-005-01..07` và `C005-01..08`.
2. **Bước 2 — Sửa Runtime Router & ChatGraph (`app/agent/router.py`, `app/services/chat_graph.py`):**
   - Sửa `#L1108-L1123` + helper `_has_verified_curriculum_topic` và cổng cách ly `advice` trong `is_curriculum_navigation` tại `app/agent/router.py` (`0%` `import re`).
   - Sửa `fb_high_conf = bool(fb_scores) and ...` tại `app/services/chat_graph.py#L798`.
3. **Bước 3 — Mở rộng Sanitizer Deterministic & Làm sạch 83 Transcript (`scripts/canonicalize_transcripts_ast.py`):**
   - Mở rộng `_CORRUPTED_ASR_CHAR_RE` & `_sanitize_corrupted_asr_artifacts` (bảo vệ 100% `VIETNAMESE_NFC_LETTERS`, `chunk_id`, `start_sec`, `lesson_seq`).
   - Chạy `.venv\Scripts\python.exe scripts/canonicalize_transcripts_ast.py --repair-asr-artifacts --apply --refresh-chapters` (không gọi `--gemini`, không gọi `--sync-qdrant`).
4. **Bước 4 — Thống nhất SSOT `check_decontamination`, Làm sạch SLM Corpus & Vá Validator (`scripts/validate_training_datasets.py`, `scripts/finetune_slm_router.py`):**
   - Cập nhật `check_decontamination` (Jaccard `< 0.65` + Token Containment `< 0.85`), làm sạch các câu near-leakage/snooping & mâu thuẫn solicitation trong `router_training_corpus.json` + bổ sung `contrastive_advice` sạch trong `router_hard_negative_hybrid_pool.json`.
   - Khóa toàn bộ điều kiện kiểm định của `validate_slm_corpus`, `validate_mdeberta_jsonl`, `validate_jina_jsonl`, `validate_qwen25_jsonl` và merge-safe `run_validation`.
   - Chạy `finetune_slm_router.py` tái tạo `router_training_corpus_v2_9_hybrid.json` sạch `100%` (`leaked = 0`, `fatal_conflict = 0`, `audit` đồng bộ tuyệt đối).
5. **Bước 5 — Viết lại Dataset Generators & Kaggle Trainers (`scripts/kaggle_automl_runner.py`, `scripts/kaggle_jobs/train_*.py`):**
   - Cập nhật 3 hàm `build_*_dataset` và 3 script `train_*.py` (`GroupShuffleSplit` + mask loss `assistant`-only + `max_length=2048` + `DataCollatorForSeq2Seq` cho Qwen2.5).
   - Chạy `.venv\Scripts\python.exe scripts/kaggle_automl_runner.py --dry-run --skip-validate` sinh lại 3 bundle JSONL mới.
   - Chạy `.venv\Scripts\python.exe scripts/validate_training_datasets.py --mode validate --with-e5` xác nhận **4/4 PASS thật sự** (`all_passed: true`).
6. **Bước 6 — Bổ sung Unit Tests Khóa Spec 005 & Đăng ký Harness:**
   - Viết unit tests khóa toàn bộ `RC-005-01..07` & `C005-01..08`, đăng ký vào `SEQUENTIAL_PYTEST_SUITES` và kiểm chứng tuần tự với `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` trước khi bàn giao sang Nhịp 3 Deterministic Harness.

---

## 6. HỒ SƠ PROBE THỰC NGHIỆM (LƯU NGOÀI REPOSITORY — `0` TỆP RÁC TRONG WORKSPACE)
Toàn bộ script thăm dò chỉ đọc phục vụ kiểm toán Nhịp 1A được lưu tách biệt tại `C:\Users\Admin\.gemini\antigravity-cli\brain\63f2263d-156d-48dc-932a-d9d32fa62528\scratch\`:
- `audit_pstack_005.py` — Kiểm kê 14 ca lỗi Router, 28 ca lỗi TS trên Golden 200, toàn bộ 72 ký tự lạ / 305 cụm lặp từ / 39 chunk thuần ASCII trên 6,387 chunks, và 19 bài học `< 2` keywords.
- `audit_router_and_datasets_deep.py` — Truy vết xác suất `(p_chit, p_course, p_oos, margin)`, `nli_intent`, `has_curriculum_topic` trên toàn bộ 200 ca Golden và phân tích cấu trúc 3 tệp JSONL trong `scratch/kaggle_bundle/`.
- `audit_containment_detail.py` & `audit_containment_ssot.py` — Định lượng chính xác các mẫu rò rỉ Token Containment (`>= 0.85`) và Content-Token Containment (`TinhGPA`, `gcd`, `dd/mm/yyyy`, `operator>>`, `&&`, `advice`).
- `audit_bundles_and_tokens.py` — Kiểm toán độ đa dạng mở đầu thật của Qwen2.5, tỷ lệ cắt cụt `...` (`192/256`), và kiểm tra trùng lặp trước khử trùng.
- `audit_nav_vs_advice.py` — Chứng minh thực nghiệm lỗi bỏ sót `"advice"` trong `is_curriculum_navigation` trên toàn bộ `Golden 200` và `9` suites `E2E Matrix`.
