# Unified E2E Spec: `<Slug / Feature / Bugbatch>`

- **Ngày lập / Phiên bản:** `YYYY-MM-DD` (v1)
- **Tác giả Spec:** `<Agent / Coordinator / User>`
- **Trạng thái:** `DRAFT` | `AUDITED [approved]` | `VERIFIED`
- **Phạm vi tác động (Layers):** `[ ] Router` `[ ] Curriculum` `[ ] Retrieval` `[ ] ChatGraph/CRAG` `[ ] ContextAssembly` `[ ] StreamGuardrail` `[ ] TelemetryCritic` `[ ] Frontend`

---

## 1. Constitution Check (`AGENTS.md` & Rigor Invariants)
- [ ] **Zero Quick-Fix:** Xử lý theo *Lớp bài toán (Problem Class)*, cấm hardcode regex/từ khóa cá biệt cho câu hỏi mẫu.
- [ ] **Zero Fake Fallback:** Không dùng fallback trả lời sai/câu hỏi giả che lỗi thực; phân định rõ offline vs live.
- [ ] **Static Prefix Cache (`messages[0]`):** Giữ `messages[0]` tĩnh 100% cho vLLM KV prefix caching.
- [ ] **Data/Code Separation:** Luật/từ khóa đặt trong JSON manifest (`data/metadata/*.json`), tách khỏi mã Python.
- [ ] **No "Qua Mặt" Model Swaps:** Mọi kiểm chuẩn E2E live phải chạy đúng model phục vụ thực tế trong `.env`.

---

## 2. Chẩn đoán Nguyên nhân Gốc E2E (Root-Cause & Problem Classes)
*(Liệt kê từng lớp bài toán rút ra từ trace thực tế — ghi rõ file, hàm, dòng và luồng dữ liệu gây sai lệch.)*

### Problem Class PC-01: `<Tên lớp lỗi>`
- **Bằng chứng thực tế (Log / Turn):** `<file log, turn_idx, prompt, hành vi sai>`
- **Vết thực thi (E2E Trace):**
  `Router (...) -> Curriculum (...) -> Retrieval (...) -> CRAG (...) -> ContextAssembly (...) -> Stream/Guard (...)`
- **Nguyên nhân gốc:** `<Giải thích kỹ thuật chính xác>`

---

## 3. Hợp đồng Hành vi End-to-End (E2E Behavioral Contract)

| ID | Lớp đầu vào / Ngữ cảnh | Tầng 1: `IntentRouter` | Tầng 2: `Curriculum / Retrieval` | Tầng 3: `CRAG / ContextAssembly` | Tầng 4: `LLM / StreamGuardrail` | Điều kiện PASS |
|---|---|---|---|---|---|---|
| `REQ-01` | `<Mô tả lớp câu hỏi>` | `intent=...`, `used_fast_path=...` | `<retrieval_status / candidates>` | `<system_prompt / context blocks>` | `<ràng buộc trả lời / timestamp / ?>` | `<Assert cụ thể>` |

---

## 4. Đặc tả Sửa đổi Theo Thứ tự Phụ thuộc (Dependency-Ordered Changes)
*(Ghi rõ thay đổi theo luồng từ đầu vào tới đầu ra để không chồng chéo.)*
1. **Lớp 1 — Manifest / Data (`data/metadata/...`):** ...
2. **Lớp 2 — Router (`app/agent/router.py`):** ...
3. **Lớp 3 — Curriculum / Retrieval (`app/services/curriculum.py`, `app/services/retrieval.py`):** ...
4. **Lớp 4 — ChatGraph / ContextAssembly (`app/services/chat_graph.py`):** ...
5. **Lớp 5 — Streaming / Guardrails (`app/services/chat.py`, `app/agent/guardrails.py`):** ...

---

## 5. Cross-Layer Conflict & Invariant Matrix (Ma trận Chống Xung đột Chéo)
*(BẮT BUỘC đánh giá trước khi viết code xem mỗi sửa đổi có phá bất biến hoặc suite nào đang xanh không.)*

| Thay đổi dự kiến | Nguy cơ xung đột chéo tiềm ẩn | Cơ chế phòng ngừa trong Spec | Kiểm chứng bắt buộc |
|---|---|---|---|
| `<Ví dụ: Bảo vệ follow-up ngắn khỏi out_of_scope>` | `<Có thể lọt câu ngoài lề thực sự như "nấu mì 5 phút" hay "hello"?>` | `<Yêu cầu kiểm tra NLI/anaphora + lịch sử course_query hợp lệ, không dùng độ dài thuần túy>` | `<M2-T07, M3-T02, Golden 200 out_of_scope>` |

---

## 6. Kế hoạch Nghiệm thu & Chống Hồi quy (Verification Plan)
1. **Unit / Integration Tests mới (tái hiện từng `PC-*`, không mock xóa logic thật):**
   - `tests/<file>.py::<test_name>` -> Khóa `PC-01`...
2. **Regression Pytest tuần tự (`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`, sau bản sửa cuối):**
   - `tests/test_playback_temporal_and_disambiguation.py`
   - `tests/test_unseen_edges_and_canonicalizer.py`
   - `tests/test_group1_2_optimizations.py`
   - `tests/test_p0_regression.py`
   - `tests/test_e2e_anti_parroting_and_critic.py`
   - `tests/test_chat_stream.py`
   - `tests/test_search_api.py`
   - `tests/test_multiturn_benchmark.py -k "test_tier_2_socratic_refusal_precision"`
3. **Live E2E Verification:**
   - `scripts/e2e_matrix_harness.py --suite all` (`all_passed: true`) + kịch bản kiểm tra mới (M4 / Playground verify).
