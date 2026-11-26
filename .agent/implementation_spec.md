# ĐẶC TẢ TRIỂN KHAI KỸ THUẬT & TOÁN HỌC — SPEC 005 v1.0 (PSTACK NHỊP 1B — VÒNG LẶP #1)

> **Hệ thống:** In-Course Agentic RAG Copilot — LangGraph Stateful Orchestration & 4-Model Fine-Tuning Pipeline  
> **Sinh viên thực hiện:** Trần Thành Nghĩa (MSSV: `23DH112252`), Trường Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT)  
> **Ngày ban hành:** `2026-11-26` | **Base Commit:** `31d00d4` + Working Tree hiện tại  
> **Vai trò Thiết kế:** `rag-architect` & `solution-analyst`  
> **Đặc tả Nguồn duy nhất (SSOT):** [`specs/005-unified-dataset-workflow-repair/spec.md`](file:///D:/In_Course_Agentic_RAG_Copilot/specs/005-unified-dataset-workflow-repair/spec.md) (`v1.0`)  
> **Cơ sở Kiểm toán Nhịp 1A:** [`.agent/technical_debt_audit.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/technical_debt_audit.md)  
> **Kỷ luật bắt buộc cho `@core-coder` (Nhịp 2):** Cross-Layer Unified Fix | **0% Regex Runtime (`import re` trong `app/`)** | **0% Quick-Fix** | **0% Test-Set Snooping** | **100% Data/Code Separation** | **100% Bảo toàn `chunk_id` / `lesson_seq` / `start_sec` / `end_sec`** | **KHÔNG chạy `--gemini`, `--sync-qdrant`, KHÔNG push Kaggle**

---

## 0. RÀNG BUỘC CỨNG TRƯỚC KHI TRIỂN KHAI

1. **Giữ nguyên 100% thành quả Spec 004 v2.0** trong `app/services/retrieval.py`, `app/services/chat.py`, `app/services/telemetry_critic.py`, `app/config.py`, `tests/test_spec004_unified_workflow_hardening.py`.
2. **Bảo toàn phần cứng RTX 2050 4 GB VRAM:** Giữ nguyên `onnxruntime-gpu==1.23.2`, Dense E5 GPU, `jina-reranker-v2-int8` CPU; mọi lệnh kiểm thử chạy **tuần tự từng tiến trình** với `HF_HUB_OFFLINE=1` và `TRANSFORMERS_OFFLINE=1`.
3. **Không chỉnh sửa dữ liệu kiểm chuẩn:** Giữ nguyên 100% `tests/data/benchmark_golden_dataset.json`, `tests/data/ood_stress_test_dataset.json`, `tests/data/multiturn_benchmark_dataset.json`.

---

## 1. HƯỚNG DẪN TRIỂN KHAI CHI TIẾT THEO 6 BƯỚC PHỤ THUỘC (`B1..B6`)

### Bước B1 — Runtime Router & ChatGraph (`app/agent/router.py`, `app/services/chat_graph.py`)

1. **[`app/agent/router.py`](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py) (`RC-005-01`, `RC-005-02`, `0% import re`):**
   - **Thêm helper `_has_verified_curriculum_topic(self, clean_prompt: str) -> bool`** (dùng lại tại `#L1048`, `#L1110`, `#L1126`):
     ```python
     def _has_verified_curriculum_topic(self, clean_prompt: str) -> bool:
         """Kiểm tra câu hỏi có khớp chủ đề bài học xác thực trong giáo trình (Zero Regex)."""
         try:
             from app.services.curriculum import get_curriculum_service, _has_topical_overlap
             c_svc = get_curriculum_service()
             matched = c_svc.find_lesson_for_query(clean_prompt)
             if not matched:
                 return False
             m_lesson, _ = matched
             return bool(
                 _has_topical_overlap(
                     m_lesson,
                     clean_prompt,
                     c_svc._stop_words,
                     conflict_groups=c_svc._modifier_conflict_groups,
                     domain_tokens=c_svc._domain_specific_tokens,
                 )
             )
         except Exception as e:
             logger.debug(f"[IntentRouter] Lỗi kiểm tra _has_verified_curriculum_topic ({e}).")
             return False
     ```
   - **Sửa nhánh chết `#L1108-L1123`** (`elif nli_intent == "out_of_scope":` $\to$ `if top1_class == "course_query":`):
     ```python
     elif nli_intent == "out_of_scope":
         if top1_class == "course_query":
             topic_verified = has_curriculum_topic or self._has_verified_curriculum_topic(clean_prompt)
             has_student_code = _detect_student_cpp_ast(clean_prompt)
             if (
                 nli_conf >= 0.80
                 and p_oos >= 0.22
                 and (p_course - p_oos) < 0.25
                 and not topic_verified
                 and not has_student_code
             ):
                 logger.info(
                     f"[IntentRouter-Cascade] NLI Arbiter lật SLM course_query phân vân "
                     f"(NLI={nli_conf*100:.1f}%, P_course={p_course:.3f}, P_oos={p_oos:.3f}) -> out_of_scope"
                 )
                 return RouterClassification(
                     intent="out_of_scope",
                     direct_response=OFFTOPIC_CASUAL_RESPONSES,
                     is_course_query=False,
                 )
             else:
                 logger.info(
                     f"[IntentRouter-Cascade] Recall-First Protection bảo vệ SLM course_query "
                     f"(NLI={nli_conf*100:.1f}%, P_course={p_course:.3f}, P_oos={p_oos:.3f}, "
                     f"topic={topic_verified}, ast={has_student_code}) -> course_query"
                 )
                 return RouterClassification(intent="course_query", direct_response=None, is_course_query=True)
     ```
   - **Sửa cổng cách ly tương phản `is_curriculum_navigation` (`#L623-L653`):**
     - Tính `sim_chitchat = float(np.max(np.dot(self._chitchat_proto_matrix, qv))) if (self._chitchat_proto_matrix is not None and len(self._chitchat_proto_matrix) > 0) else 0.0` (phủ đủ 6 nhóm gồm `"advice"`).
     - Khi `not has_nav_sig`:
       - Chặn sớm nếu `not has_folded_sig and sim_chitchat >= 0.90 and sim_chitchat > max_sim + 0.02: return (False, max_sim)`.
       - Đổi `#L645` thành `if not has_nav_sig and max_sim <= max(sim_soc, sim_sys, sim_chitchat) + 0.02:` (giữ nguyên nhánh cứu xét `has_folded_sig and folded_sim >= 0.82 and _has_curriculum_topic()`).

2. **[`app/services/chat_graph.py#L798`](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L798) (`RC-005-03`):**
   - Đổi:
     ```python
     fb_high_conf = bool(fb_scores) and (
         max(fb_scores) >= settings.MODALITY_GATE_VIDEO_HIGH_CONFIDENCE
     )
     ```

---

### Bước B2 — Mở rộng Sanitizer Deterministic (`scripts/canonicalize_transcripts_ast.py`)

1. **Khai báo hằng bất biến `VIETNAMESE_NFC_LETTERS`** (đúng `134` chữ cái tiếng Việt có dấu chuẩn NFC: `67` thường + `67` hoa) và bảng `_FOREIGN_LATIN_FOLD_MAP = {"ı": "i", "İ": "I", "ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE"}`.
2. **Mở rộng `_CORRUPTED_ASR_CHAR_RE` & các regex dọn rác:**
   - Khối chữ ngoại lai: CJK/Kana/Hangul/Cyrillic/Arabic/Thai/FFFD/Bidi + **Hy Lạp (`\u0370-\u03FF`, `\u1F00-\u1FFF`)**, **Do Thái (`\u0590-\u05FF`)**, **Devanagari/Tamil/Indic (`\u0900-\u0DFF`)**, **CJK Punctuation (`\u3000-\u303F`)**, **Halfwidth/Fullwidth (`\uFF00-\uFFEF`)**, **Emoji/Pictographs (`\U0001F000-\U0001FAFF`, `\u2600-\u27BF`, `\uFE00-\uFE0F`)**, **Toán/Mũi tên/Tiền tệ ngoại lai (`\u2190-\u21FF`, `\u2200-\u22FF`, `\u20A0-\u20CF`, `\u00BD`, `\u00BC`, `\u00BE`, `\u00D7`, `\u2080-\u2089`)**.
   - Lặp chữ cái cách khoảng `>= 4` lần (`e e e e`): `re.compile(r"(?i)(?<!\w)([a-z])(?:\s+\1){3,}(?!\w)")` $\to$ `" "`.
   - Lặp từ/cụm rác liên tiếp `>= 3` lần (`phim, phim, phim`, `cout, cout, cout`): `re.compile(r"(?i)\b([^\W\d_]{2,})(?:[\s,;]+\1){2,}\b")` $\to$ `r"\1"` (không đụng chuỗi số như `0, 0, 0`).
   - Hallucination tiếng Anh/ASCII thuần của Whisper: phát hiện câu YouTube boilerplate (`"if you have any question"`, `"leave feedback in comments"`, `"thanks for watching"`, `"subscribe to"`, `"please subscribe"`, `"like and subscribe"`) và chunk dài $\ge 40$ chars có `0` chữ có dấu tiếng Việt + tỷ lệ từ tiếng Anh/gibberish ngoài từ khóa C++ $\ge 0.70$ (hoặc chuỗi mũi tên `->` rác).
3. **Đồng bộ `_contains_corrupted_asr_artifacts(text)` và `_sanitize_corrupted_asr_artifacts(text)`:**
   - Thay `→` (`\u2192`) bằng `"->"` (hoặc khoảng trắng nếu là chuỗi mũi tên hallucination), `×` bằng `"*"`, chỉ số dưới `₀..₉` bằng `0..9`.
   - Mọi chữ cái `ord(ch) > 127` thuộc `L*` mà `ch not in VIETNAMESE_NFC_LETTERS`: nếu nằm trong khối ngoại lai $\to$ `" "`, nếu Latin ngoại lai $\to$ map qua `_FOREIGN_LATIN_FOLD_MAP` hoặc NFD bỏ combining marks `Mn`.
   - Tại `run_repair_asr_artifacts_cli#L2795`: nếu `orig_txt` bị phát hiện corrupted/English hallucination và sau lọc `len(cleaned_txt) < 15` (hoặc rỗng), gán hằng `ASR_EMPTY_FALLBACK_TEXT = "[Đoạn thao tác mã nguồn C++ trên màn hình]"` thay vì bỏ qua không ghi. **Bảo toàn 100%** số lượng chunk (`6,387`), `chunk_id`, `start_sec`, `end_sec`, `start_label`, `end_label`, `lesson_seq`.
4. **Thực thi cục bộ:**
   ```powershell
   .\.venv\Scripts\python.exe scripts\canonicalize_transcripts_ast.py --repair-asr-artifacts --apply --refresh-chapters
   ```
   *(Tuyệt đối KHÔNG chạy `--gemini` hoặc `--sync-qdrant` trong vòng này.)*

---

### Bước B3 — Thống nhất SSOT `check_decontamination` & Vá Toàn Bộ Điểm Mù `scripts/validate_training_datasets.py`

1. **SSOT `check_decontamination()` (dùng chung ở `validate_training_datasets.py`, `finetune_slm_router.py`, `kaggle_automl_runner.py`):**
   - Tham số: `(text, heldout_norms, heldout_queries, max_jaccard=0.65, max_containment=0.85) -> Tuple[bool, float]`.
   - Kiểm tra đủ 4 cổng toán học §3.3: `exact_match`, `Jaccard >= 0.65`, `C_raw >= 0.85`, và `C_content >= 0.85` (khi `min(|T_c(a)|, |T_c(h)|) >= 4`).
   - Caching bộ token hóa `(raw_set, content_set)` của `heldout_queries` theo `id(heldout_queries)` / độ dài để giữ tốc độ `< 0.2s`.
2. **`validate_slm_corpus`:**
   - Dùng `seen_norm_to_intent: Dict[str, str]` để phát hiện & ghi nhận `exact_duplicate_label_conflicts` **trước** `if nt in seen_norm_to_intent: continue` (đưa vào `fatal_conflicts`!).
   - Khi `clean_in_place=True`, cập nhật lại đầy đủ `data["audit"]` (`total_clean_samples`, `class_distribution`, `leaked_rejected_count`, `fatal_conflict_count`) khớp 100% `len(clean_rows)`.
   - Kiểm tra cả `audit_mismatch` (`data.get("audit", {}).get("total_clean_samples") == len(samples)`) ở mode `validate`.
3. **`validate_mdeberta_jsonl`:**
   - Nạp 3 `main_hypotheses` và 2 `temporal_hypotheses` nguyên văn từ `router_intent_manifest.json` (`bad_hypothesis_count == 0`).
   - Yêu cầu đủ `{0, 1, 2}`: mỗi nhãn `>= 12%` tổng mẫu sạch và `max_lbl / min_lbl <= 4.0`.
   - Chặn multi-entailment: 1 `norm_premise` có `>= 2` dòng `label == 0` trên 3 `main_hypotheses` $\implies$ `multi_entailment_count` (`HARD FAIL`).
   - Kiểm tra riêng `in_video_hyp` và `off_topic_hyp`: mỗi giả thuyết có đủ `{0, 1, 2}` và `max(c0, c2) / max(1, min(c0, c2)) <= 3.0` (`temporal_imbalance_count == 0`).
4. **`validate_jina_jsonl`:**
   - Xóa `if clean_in_place:` ở `#L365` và `#L369`: luôn đếm & lọc dòng lỗi ở **cả 2 mode**.
   - Khóa trần độ dài `<= 600` ký tự (`settings.RERANK_MAX_CHARS = 600`).
   - Khóa định dạng dòng đầu khớp runtime (`[Bài giảng Video ... mốc ...]` hoặc `[Mã nguồn ...]`), cấm `| từ khóa:` / `từ khóa:` trên dòng tiêu đề (`header_shortcut_count == 0`).
   - `HARD FAIL` cho `_contains_corrupted_asr_artifacts(pos)` hoặc `neg` (`garbled_count == 0`).
   - Quét `asr_phonetic_glossary` từ `cpp_academic_glossary.json` vào telemetry warning `asr_homophone_warnings` (không đánh fail Chặng 1).
   - Cập nhật kiểm tra False-Negative hỗ trợ **intra-lesson hard negatives**: phân tích header lấy `(kind, lesson_key, sec_or_scope)`; cấm trùng `(lesson_key, sec)` với `abs(sec_pos - sec_neg) < 60` hoặc trùng `(lesson_key, code_scope)`; yêu cầu `neg_overlap <= pos_overlap + 1`. Yêu cầu `intra_lesson_negative_count >= 1` và `code_ast_triplet_count >= 1`.
5. **`validate_qwen25_jsonl`:**
   - Đổi `load_valid_lesson_timestamps()` sang **`Dict[int, Dict[int, str]]`** (`lesson_seq -> {sec: "MM:SS"}`), hợp nhất từ `lessons_manifest.json`, `data/transcripts/*/*_chunks.json`, và `data/metadata/lesson_code_video_binding.json`.
   - Bắt buộc `messages[0]["role"] == "system"` và `messages[0]["content"] == SOCRATIC_GROUNDED_PROMPT`.
   - Bắt buộc `user` có `[NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC]`, trích `lesson_seq` từ `Nguồn Bài (\d+)` (khớp `row.get("lesson_seq")`), tách riêng câu hỏi học viên trước `[NGỮ CẢNH` / `[LƯU Ý` để chạy `check_decontamination`.
   - Đối chiếu mọi `<timestamp sec="S">MM:SS</timestamp>` trong `assistant` theo đúng `valid_ts_by_lesson[lesson_seq]` **và** phải xuất hiện trong `user` RAG context (`invalid_timestamp_count == 0`).
   - Kiểm tra kết cấu Socratic: tách prose trước footer `📍 **Mốc video bài giảng:**` (hoặc thẻ `<timestamp` cuối); prose phải kết thúc bằng **đúng 1 câu hỏi Socratic `?`** ngay trước footer (cấm `!`, cấm câu kết trong `forbidden_closing_prefixes`, cấm `?` nằm sau footer, cấm lời chào `"Chào bạn!"` / `"Xin chào!"`).
   - Mở rộng cấm rò rỉ code: `#include`, `using namespace std`, `int main`, `void main`, `signed main`, `return 0;`, `cin >>`, `cout <<`, ` ```cpp `, ` ```c++ `.
   - Cấm cắt cụt `"..."` và `"…"` trong `assistant`.
   - Cập nhật trần độ dài `sum(len(m["content"])) <= 5500` chars.
   - Đo `unique_user_openings >= 12` và `unique_assistant_openings >= 12` sau khi strip prefix `Bài \d+(: ...)?`; yêu cầu `lessons_covered == 83`.
6. **`run_validation` (Merge-Safe):**
   - Khai báo `ALL_MODELS = ("slm_router", "mdeberta_nli", "jina_reranker", "qwen25_qlora")`.
   - Nếu `models` là tập con, đọc `dataset_validation_report.json` cũ (nếu tồn tại), giữ nguyên các khóa không nằm trong `selected`, cập nhật các khóa vừa chạy, rồi tính `all_passed = all(bool(merged.get(m, {}).get("passed")) for m in ALL_MODELS)`.

---

### Bước B4 — Làm sạch SLM Corpus & Re-sync `scripts/finetune_slm_router.py`

1. **[`data/metadata/router_training_corpus.json`](file:///D:/In_Course_Agentic_RAG_Copilot/data/metadata/router_training_corpus.json):**
   - Xóa/viết lại sang ngữ cảnh tổng quát độc lập toàn bộ `18` mẫu vi phạm Containment / nhái kịch bản đề thi đã nêu tại [`.agent/technical_debt_audit.md#L169`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/technical_debt_audit.md#L169).
   - Thay 4 câu chào 1–2 từ (`#L629-L647`: `"Xin chào"`, `"xin chào"`, `"chào"`, `"chào bạn"`, `"hello"`, `"hi"`, `"alo"`) bằng câu chào tự nhiên $\ge 4$ từ không dính containment với held-out.
   - Xóa/viết lại 3 câu solicitation+jailbreak trái nhãn (`#L441, #L449, #L469`) sang jailbreak bảo mật thuần túy (không chứa cụm xin giải bài tập C++), giữ nhất quán mọi câu xin code bài tập C++ là `course_query`.
   - Viết lại 2 câu meta-Socratic (`#L1397, #L1877`) không dùng chuỗi con trong `solicitation_words`.
2. **[`data/metadata/router_hard_negative_hybrid_pool.json`](file:///D:/In_Course_Agentic_RAG_Copilot/data/metadata/router_hard_negative_hybrid_pool.json):**
   - Sửa `#L238` (không dùng `"viết hộ"` trong câu meta-Socratic) và mở rộng `contrastive_advice` sạch từ 4 mẫu lên `14–18` mẫu đa dạng (phương pháp tự học C++, quản lý thời gian luyện bài, tâm lý học code, rèn tư duy thuật toán, vai trò AI hỗ trợ kỹ sư phần mềm) đạt `0` rò rỉ containment.
3. **[`scripts/finetune_slm_router.py`](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/finetune_slm_router.py):**
   - Import và gọi trực tiếp `check_decontamination()` từ `scripts/validate_training_datasets.py` trong `load_decontaminated_corpus()`.
   - Sau bước lọc `conflict_drops` (`#L280-L290`), cập nhật lại `merged_json["samples"]` và `merged_json["audit"]` (`total_clean_samples`, `class_distribution`, `conflict_drops_count`) rồi ghi lại vào `MERGED_CORPUS_OUT_PATH`.
   - Chạy `finetune_slm_router.py` (không dùng `--force-deploy` để cổng an toàn tự bảo vệ `slm_router_int8.onnx` nếu candidate chưa vượt baseline, đồng thời xuất `router_training_corpus_v2_9_hybrid.json` sạch 100%).

---

### Bước B5 — Viết lại Dataset Generators (`scripts/kaggle_automl_runner.py`) & Kaggle Trainers (`scripts/kaggle_jobs/`)

1. **[`scripts/kaggle_automl_runner.py`](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/kaggle_automl_runner.py):**
   - `_is_clean_text()` gọi trực tiếp SSOT `check_decontamination()`.
   - **`build_mdeberta_nli_dataset`:** Triển khai đúng §3.5 (`0` multi-entailment, đủ `neutral (1)` ~`20%–30%`, `temporal_nli` cân bằng `0/1/2` cho cả `in_video` & `off_topic`).
   - **`build_jina_reranker_dataset`:**
     - Video passage: `truncate_rerank_text(f"[Bài giảng Video {vid_title} mốc {start_lbl}]\n{clean_txt}", max_chars=600)` (lấy đúng `vid_title` từ `lessons_manifest.json` hoặc `f"{folder_name}.mp4"`, bỏ qua chunk placeholder `ASR_EMPTY_FALLBACK_TEXT` và mọi chunk dính `_contains_corrupted_asr_artifacts`).
     - Code AST passage: đọc từ `data/sample_codes/*/*_ast_chunks.json`, lọc bỏ `header_preamble`, định dạng `truncate_rerank_text(f"[Mã nguồn CPP - {code_scope}]\n{ctx_code}", max_chars=600)`.
     - Query trích trực tiếp cụm khái niệm/định danh có thật trong `pos_passage` (không ghép rập khuôn `title + kws[:3]`), lọc sạch qua SSOT `check_decontamination`.
     - Kết hợp **intra-lesson hard negatives** (cách xa `>= 90s` trong cùng bài, `neg_overlap <= pos_overlap`), **cross-lesson hard negatives**, và **`code_ast` triplets** (negative là `code_ast` hàm/bài khác hoặc video bài khác). Lưu `"lesson_seq"` trong mỗi dòng JSONL.
   - **`build_qwen25_socratic_dataset`:**
     - Bỏ lọc `if len(kws) < 2: continue` để phủ **đủ 83/83 bài học** (tự bổ sung khái niệm từ `title` + `extract_lesson_lexicon` + nội dung chunk sạch).
     - `messages[0] = {"role": "system", "content": SOCRATIC_GROUNDED_PROMPT}`.
     - `messages[1]` đúng định dạng runtime `crag_grader_node`:
       ```text
       [CÂU HỎI THẮC MẮC CỦA HỌC VIÊN]
       {user_q}

       [NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC]
       Nguồn Bài {seq} (mốc <timestamp sec="{sec}">{lbl}</timestamp>): {clean_excerpt}
       ```
       (`clean_excerpt` cắt tại ranh giới câu/từ hoàn chỉnh `<= 360` chars, không `...`).
     - `messages[2]` mở đầu đa dạng (không `"Chào bạn!"`, không `Bài X` lặp cứng), giải thích bản chất + kết thúc bằng **đúng 1 câu hỏi Socratic `?`** ngay trước `\n\n📍 **Mốc video bài giảng:** <timestamp sec="{sec}">{lbl}</timestamp>` (`0` `!`, `0` `...`, `0` code leak).
     - Ánh xạ `compiler_diagnostics_manifest.json` theo đúng chủ đề bài học (`CATEGORY_TO_LESSON_SEQS` ánh xạ 14 `category` tới nhóm bài tương ứng — cấm phép `%`). Lưu `"lesson_seq": seq` ở cấp ngoài JSONL.

2. **3 Kaggle Trainers trong `scripts/kaggle_jobs/`:**
   - [`train_mdeberta_nli.py`](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/kaggle_jobs/train_mdeberta_nli.py): `GroupShuffleSplit(n_splits=1, test_size=0.10, random_state=seed)` theo `norm_premise`; thêm `macro_f1` vào `compute_metrics` (`metric_for_best_model="macro_f1"`).
   - [`train_jina_reranker.py`](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/kaggle_jobs/train_jina_reranker.py): `GroupShuffleSplit(n_splits=1, test_size=0.10, random_state=seed)` theo khóa `f"{lesson_seq}::{norm_query}"`.
   - [`train_qwen25_qlora.py`](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/kaggle_jobs/train_qwen25_qlora.py):
     - `GroupShuffleSplit(n_splits=1, test_size=0.10, random_state=seed)` theo `lesson_seq`.
     - Nâng `max_length = 2048`.
     - Trong `_tokenize(example)`: render `prompt_text = apply_chat_template(msgs[:2], add_generation_prompt=True)` và `full_text = apply_chat_template(msgs, add_generation_prompt=False)`; tokenize `add_special_tokens=False`; tính `mask_len = min(len(prompt_ids), len(full_ids))`; đặt `labels = [-100] * mask_len + full_ids[mask_len:]`; kiểm tra `assert any(x != -100 for x in labels)`.
     - Đổi `DataCollatorForLanguageModeling` sang `DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model, label_pad_token_id=-100, pad_to_multiple_of=8)`.

---

### Bước B6 — Unit Tests Khóa Spec 005 & Kiểm Chứng Toàn Phần

1. Tạo [`tests/test_spec005_unified_dataset_workflow.py`](file:///D:/In_Course_Agentic_RAG_Copilot/tests/test_spec005_unified_dataset_workflow.py) khóa toàn bộ `RC-005-01..07` và `C005-01..10` (`8+` tests, `0%` ID `BENCH-`/`SESSION-`).
2. Đăng ký `"tests/test_spec005_unified_dataset_workflow.py"` vào `MasterAutonomousHarness.SEQUENTIAL_PYTEST_SUITES` (`13` suites) tại [`scripts/master_autonomous_harness.py#L375-L388`](file:///D:/In_Course_Agentic_RAG_Copilot/scripts/master_autonomous_harness.py#L375-L388).
3. Chạy tuần tự (`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`):
   - `.\.venv\Scripts\python.exe scripts\kaggle_automl_runner.py --dry-run --skip-validate`
   - `.\.venv\Scripts\python.exe scripts\validate_training_datasets.py --mode validate --with-e5` $\implies$ **4/4 PASS (`all_passed: true`)**
   - `.\.venv\Scripts\python.exe scripts\master_autonomous_harness.py --stage 1 --force-eval` $\implies$ **exit_code = 0**, `13/13` pytest suites PASS, `E2E Matrix 9/9 PASS`, Multi-Turn `>= 94/90/97/100`, Stage 11 Golden `Router >= 90.5%`, `CRAG >= 86.0%`, **`TS Safety >= 86.5%`**.
