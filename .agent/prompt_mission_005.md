# NHIỆM VỤ PSTACK 005: SỬA ĐỒNG BỘ TOÀN BỘ WORKFLOW RUNTIME – VALIDATOR – GENERATOR – TRAINER (4 MÔ HÌNH + SANITIZER TRANSCRIPT)

Mục tiêu: Khắc phục dứt điểm toàn bộ lỗi cấu trúc & điểm mù liên tầng vừa kiểm toán (ZERO Quick-Fix, ZERO Test-Set Snooping, 0% regex runtime trong `app/`, giữ nguyên 100% `start_sec` / `lesson_seq` / `chunk_id` của video).

## Phạm vi & Hợp đồng Bắt buộc Theo Thứ Tự Phụ Thuộc

1. **Runtime Router & ChatGraph (`app/agent/router.py`, `app/services/chat_graph.py`):**
   - Tại `app/agent/router.py` (quanh `#L1108-L1123`), trong nhánh `elif nli_intent == "out_of_scope":` -> `if top1_class == "course_query":`, sửa điều kiện bất khả thi `if nli_conf >= 0.85 and p_oos > p_course:` (vốn đánh giá `False` 100% thời gian vì `top1_class == "course_query"` => `p_course >= p_oos`). Thay bằng điều kiện toán học hợp lệ + bảo vệ câu học tập/ẩn dụ (`has_curriculum_topic`), chạy test hồi quy cả `adversarial_hybrid` và `in_scope` + `tests/test_spec004_unified_workflow_hardening.py`.
   - Tại `app/services/chat_graph.py` (quanh `#L798`), sửa `fb_high_conf = (not fb_scores) or (...)` thành `bool(fb_scores) and max(fb_scores) >= settings.MODALITY_GATE_VIDEO_HIGH_CONFIDENCE`.

2. **Mở rộng Sanitizer Deterministic trong `scripts/canonicalize_transcripts_ast.py`:**
   - Mở rộng `_CORRUPTED_ASR_CHAR_RE` & `_sanitize_corrupted_asr_artifacts` để lọc/sửa triệt để: chữ Hy Lạp (`\u0370-\u03FF`), Do Thái (`\u0590-\u05FF`), Tamil (`\u0B80-\u0BFF`), dấu Latin ngoại lai (Thổ Nhĩ Kỳ/Bắc Âu/Ba Lan `ı, İ, ğ, ş, ö, ä, ç, ø, ß`), Emoji (`\U0001F300-\U0001FAFF`), ký hiệu toán ngoại lai (`→, ∞, ½`), lặp chữ cái cách khoảng (`e e e e`), lặp từ rác (`phim, phim, phim`, `cout, cout, cout`), và chuỗi Whisper hallucination ASCII/tiếng Anh thuần.
   - Chạy thử chế độ cục bộ deterministic (`--repair-asr-artifacts --apply --refresh-chapters`, KHÔNG gọi `--gemini` hoặc `--sync-qdrant` trong vòng Coder; bước Gemini 5-key đồng âm tiếng Việt & Qdrant upsert sẽ chạy ngay sau khi Spec 005 hội tụ).

3. **Thống nhất SSOT Khử Rò rỉ & Vá Toàn Bộ Điểm Mù `scripts/validate_training_datasets.py` + `scripts/finetune_slm_router.py`:**
   - Bổ sung kiểm tra **Token Containment** (`>= 0.85`) song song `Jaccard < 0.65` vào `check_decontamination()` và dùng chung ở `finetune_slm_router.py` & `kaggle_automl_runner.py`.
   - Trong `validate_slm_corpus`: quét xung đột nhãn của câu trùng khít TRƯỚC khi loại trùng (`if nt in seen`), tự cập nhật `data["audit"]` cho khớp số mẫu thật, không cho lọt 13–18 ca near-leakage/containment với held-out (`TinhGPA`, `gcd`, `dd/mm/yyyy`, `operator>>`...), giải quyết mâu thuẫn nhãn solicitation và tăng cường `contrastive_advice` sạch trong `router_hard_negative_hybrid_pool.json` -> chạy `finetune_slm_router.py` (hoặc tái tạo `router_training_corpus_v2_9_hybrid.json`) bảo đảm cân bằng lớp & `0` rò rỉ.
   - Trong `validate_mdeberta_jsonl`: bắt buộc có & cân bằng nhãn `neutral (1)`, chặn 1 premise có >= 2 `entailment (0)` ở nhóm 3 intent chính, chặn lệch hypothesis/temporal (`20:0` / `0:20`).
   - Trong `validate_jina_jsonl`: luôn lọc/đếm dòng nhiễu ở cả 2 mode `validate`/`clean`, kiểm tra độ dài `<= 600` ký tự khớp runtime `[Bài giảng Video ... mốc ...]\n`, chặn header shortcut `| từ khóa:`, bắt Whisper noise mở rộng (`HARD FAIL` cho ký tự ngoại lai/loop/ASCII gibberish; đồng âm tiếng Việt ngữ cảnh như `cốt`, `vòng lập` ghi nhận vào telemetry warning để xử lý tiếp ở Chặng 2 `--gemini`).
   - Trong `validate_qwen25_jsonl`: đổi sang map timestamp **theo từng bài học (per-lesson)**, bắt buộc `user` chứa ngữ cảnh RAG + `messages[0] == SOCRATIC_GROUNDED_PROMPT`, kiểm tra `assistant` kết thúc bằng đúng 1 câu hỏi Socratic `?` ngay trước thẻ `<timestamp>` footer (không `!`), chặn `#include <bits/stdc++.h>`, `cin >>`, `cout <<`, chặn cắt cụt giữa từ `...`, đo đa dạng mở đầu thật (sau khi bỏ prefix `Bài X`).
   - Trong `run_validation`: không ghi đè toàn bộ `dataset_validation_report.{json,md}` khi chỉ chạy lọc `--models`.

4. **Viết lại Dataset Generators trong `scripts/kaggle_automl_runner.py` (`--dry-run`) & Trainers trong `scripts/kaggle_jobs/`:**
   - `build_mdeberta_nli_dataset`: khớp nguyên văn `router_intent_manifest.json`; sinh đủ nhãn `neutral (1)` thật (ẩn dụ biên/gợi ý trung lập/câu hỏi ngôn ngữ khác không gắn sai sang `"unrealistic metaphor"`); cân bằng cả 2 vế `temporal_nli_labels` (`in_video` & `off_topic` đều có `0/1/2`); 0 multi-entailment mâu thuẫn.
   - `build_jina_reranker_dataset`: khớp 100% format runtime (`600` chars, không header `từ khóa`), query bám sát chính nội dung chunk, bổ sung **intra-lesson hard negatives** và **`code_ast` chunks**.
   - `build_qwen25_socratic_dataset`: phủ đủ **toàn bộ 83 bài** (bỏ lọc `len(kws) < 2`), dùng `SOCRATIC_GROUNDED_PROMPT`, đưa ngữ cảnh RAG thật vào `user`, đặt câu trả lời Socratic + đúng 1 `?` trước `<timestamp>` (khớp `StreamingSocraticFooterGuard`), không cắt cụt giữa từ, ghép lỗi compiler khớp chủ đề bài học (cấm `%`).
   - `scripts/kaggle_jobs/train_{mdeberta_nli,jina_reranker,qwen25_qlora}.py`: đổi sang **`GroupShuffleSplit`** theo `premise` (NLI), `(query, lesson_seq)` (Jina), bài học/chủ đề (Qwen2.5); sửa `train_qwen25_qlora.py` để chỉ tính loss trên token **`assistant`** (`labels = -100` cho `system` + `user`, thay collator không ghi đè `labels`).

5. **Kiểm chứng bắt buộc trước khi kết thúc Nhịp 2:**
   - Chạy `.venv\Scripts\python.exe scripts/kaggle_automl_runner.py --dry-run --skip-validate` và `.venv\Scripts\python.exe scripts/validate_training_datasets.py --mode validate --with-e5` xác nhận **4/4 PASS** (không đẩy job lên Kaggle).
   - Không làm hồi quy Stage 1 RAG Benchmarks (`Router >= 90.5%`, `CRAG >= 86.0%`, `TS Safety >= 86.5%`, `Multi-turn >= 94/90/97/100`, `12/12` pytests + test mới cho các ca sửa).
