# NHIỆM VỤ PSTACK VÒNG LẶP #5 — KHẮC PHỤC LỖI PLAYGROUND THỰC TẾ, DỌN CONFIG CHẾT & TỐI ƯU ĐỘ TRỄ E2E
> **Dự án:** In-Course Agentic RAG Copilot — LangGraph Stateful Orchestration  
> **Tác giả:** Sinh viên Trần Thành Nghĩa (MSSV: `23DH112252`), Trường Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT)  
> **Thời điểm cập nhật:** 2026-11-16T01:56:00+07:00  
> **Nguyên tắc tối thượng:** Zero Quick-Fix | 100% Data-Centric AI Integrity | Zero Test-Set Snooping | Zero "Qua Mặt" (Cấm tráo LLM tự lưu trữ sang API thương mại)

---

## 0. BẤT BIẾN HẠ TẦNG & MỐC BASELINE CẦN BẢO TOÀN (DO NOT REGRESS)
1. **Phân bổ Phần cứng RTX 2050 4 GB VRAM & ONNX Runtime:**
   - Trong `.venv`, giữ duy nhất `onnxruntime-gpu==1.23.2` (tuyệt đối không cài đè `onnxruntime` CPU gây mất `CUDAExecutionProvider`).
   - `intfloat/multilingual-e5-large` (Dense E5) chạy trên GPU (`CUDAExecutionProvider`, `EmbeddingService().device == "cuda"`, VRAM thực tế ~`3,161 / 4,096 MiB`).
   - `jina-reranker-v2-int8` (`data/models/jina-reranker-v2-int8/onnx/model.onnx`) ghim trên CPU (`USE_CPU_RERANKER=True`, `USE_INT8_RERANKER=True`, `RERANK_CPU_THREADS=4`, `RERANK_MAX_CHARS=600`).
   - Giữ `LLM_MAX_TOKENS=650` để không cắt cụt câu hỏi định hướng Socratic.
2. **Đo kiểm chứng E2E thực tế & Chống qua mặt:**
   - Tự lưu trữ LLM: `Qwen/Qwen2.5-Coder-7B-Instruct` qua Kaggle + Ngrok. Tuyệt đối **không** đề xuất hay cấu hình tráo sang API thương mại để làm đẹp số đo.
   - Mốc Baseline đo tách tầng trước Vòng #5 (`16/11/2026`): Ngrok RTT `~625–736 ms` | Tiny LLM streaming (`max_tokens=20`): `TTFT 4,083.8 ms`, `Total 5,192.6 ms` | Dense E5 GPU: `~63.09 ms` | CPU INT8 Rerank (4 docs): `~299.57 ms`.
3. **Cổng chất lượng Benchmark bắt buộc bảo toàn:**
   - `pytest` Test Suite: PASS 100% (không hồi quy các test đã pass, gồm `tests/test_multiturn_benchmark.py` và `tests/test_chat_stream.py`).
   - Multi-Turn Benchmark (50 sessions / 222 turns): Intent $\ge 94.0\%$, Retrieval Status $\ge 93.0\%$, ARR $\ge 97.0\%$, SRP $= 100.0\%$.
   - Stage 11 Golden 200: Router $\ge 90.5\%$, CRAG Precision $\ge 88.0\%$, Timestamp Safety $\ge 88.0\%$.
   - Liêm chính mã nguồn: `0%` hardcode keyword/regex chữa cháy (`whack-a-mole`), `0% BENCH-xxx` trong `app/`.

---

## 1. CÁC VẤN ĐỀ THỰC TẾ CẦN ĐIỀU TRA & XỬ LÝ TRIỆT ĐỂ TRONG VÒNG LẶP #5

### Vấn đề 1: Turn 3 phân loại nhầm câu hỏi kiểu dữ liệu cơ bản (`int` vs `double`) sang Bài 64
- **Bằng chứng log:** `logs/playground_debug/session_session_bgsi9hbkmwi6p227_20261116_014822.json` (Turn 3).
  - Bối cảnh: `course_id = "cpp-core"`, `lesson_seq = 3`, `prompt = "int và double khác nhau cái gì?"`.
  - Kết quả sai: `retrieval_status = "out_of_lesson"`, `target_lesson_seq = 64` (`lesson-64_64_-_BUỔI_8_C_Bài_Tập_Mảng_1_Chiều_Lý_Th.mp4`, `<timestamp sec="4869">81:09</timestamp>`), độ trễ cao nhất phiên (`ttft_ms = 27779`, `total_ms = 35340`).
- **Yêu cầu gốc rễ (Root-Cause Fix, 0% Quick-Fix):**
  - Rà soát cơ chế chấm điểm `_score_future_points`, điều kiện Pareto Dominance / Prerequisite Priority trong `app/services/retrieval.py` và metadata giáo trình các bài nhập môn (`Bài 1–3`) trong `data/curriculum/lessons_manifest.json`.
  - Tại sao kiến thức cơ bản thuộc bài đầu khóa ở `lesson_seq = 3` lại bị bài luyện tập nâng cao `lesson_seq = 64` cướp quyền thành `out_of_lesson`? Khắc phục tổng quát theo phân lớp bài toán (Foundational Prerequisite Priority & Curriculum Alignment), tuyệt đối không gắn rule riêng cho từ khóa `"int"` / `"double"`.

### Vấn đề 2: Turn 4 nhiễm chéo chunk Bài 64/63 khi đang ở Bài 1 + Rò rỉ Timestamp & Câu xin lỗi
- **Bằng chứng log:** `logs/playground_debug/session_session_bgsi9hbkmwi6p227_20261116_014822.json` (Turn 4).
  - Bối cảnh: `course_id = "cpp-core"`, `lesson_seq = 1`, `prompt = "hình như có nhầm lẫn không? tại sao lại ở bài 64"`.
  - Kết quả sai nghiêm trọng:
    1. `retrieval_status = "grounded"`, `retrieved_chunk_count = 3`, nhưng cả 3 `sources` đều thuộc **`lesson-64`** (`48.66%`, `sec: 4231`; `37.02%`, `sec: 227`) và **`lesson-63`** (`28.03%`, `start_sec: null` -> bị ép thành `<timestamp sec="0">00:00</timestamp>`), vi phạm bất biến `lesson_seq <= current_lesson_seq` (`lesson_seq <= 1`).
    2. Trong `response_text`: LLM mở đầu bằng `"Xin lỗi vì sự nhầm lẫn trước đó."` (trái quy tắc chống xin lỗi trong `app/agent/prompts.py`), tự sinh text thường không có thẻ (`📍 **Mốc video bài giảng:** 0:56`), và mời chuyển sang **Bài 2** nhưng cuối câu lại gắn `<timestamp sec="4231">70:31</timestamp> | <timestamp sec="0">00:00</timestamp>` của Bài 64 & 63.
- **Yêu cầu gốc rễ:**
  - Điều tra vì sao `lesson-63` / `lesson-64` lại lọt vào `retrieved_chunks` với trạng thái `grounded` khi `state["lesson_seq"] == 1` (kiểm tra `router_node`, `is_curriculum_navigation` trong `retrieval.py`, luồng fallback hoặc payload Qdrant, và cách `crag_grader_node` đóng gói `sources`/`timestamps`).
  - Xử lý triệt để trường hợp chunk có `start_sec = None` (không được ép mặc định thành `<timestamp sec="0">00:00</timestamp>` nếu không phải mốc thực tế).
  - Rà soát `app/agent/guardrails.py` / `app/services/chat.py` / `app/agent/prompts.py` để chặn dòng text mốc thời gian giả mạo không nằm trong whitelist (như `0:56`) và đảm bảo nhất quán giữa `target_lesson_seq` gợi ý với `<timestamp>` đính kèm.

### Vấn đề 3: Kiểm toán & Dọn dẹp `app/config.py` (`27/98` biến chưa có caller)
- **Hiện trạng đo được:** Toàn bộ `app/`, `scripts/`, `tests/` chỉ tham chiếu `71/98` trường trong `app/config.py`. Có `27` trường chưa được gọi:
  `PORT`, `HOST`, `LLM_PROVIDER`, `ANTHROPIC_API_KEY`, `REDIS_URL`, `USE_ONNX`, `MODALITY_GATE_VIDEO_EARLY_EXIT`, `FUTURE_PROBE_ACTIVATION_GATE`, `FUTURE_PROBE_MARGIN`, `FUTURE_PROBE_MIN_CONFIDENCE`, `PARETO_MARGINAL_VIDEO_MAX`, `PARETO_DOMINANCE_MARGIN`, `PARETO_DOMINANCE_FUTURE_MIN`, `PARETO_DOMINANCE_CODE_MARGIN`, `PARETO_NAV_FUTURE_MIN`, `PARETO_NAV_MARGIN`, `PARETO_INTRA_MODULE_FUTURE_MIN`, `PARETO_INTRA_MODULE_MARGIN`, `WHISPER_MODEL_SIZE`, `WHISPER_DEVICE`, `WHISPER_COMPUTE_TYPE`, `ROUTER_DRIFT_COHERE_THRESHOLD`, `ROUTER_SOCIAL_PURE_THRESHOLD`, `ROUTER_CONTEXTUAL_COURSE_MIN`, `MARKOV_HIJACK_PENALTY`, `CRITIC_GREETING_LOOP_PENALTY`, `GREETING_LOOP_PENALTY`.
- **Yêu cầu:**
  - `@codebase-auditor` & `@rag-architect` phân loại rõ từng biến: biến nào thực ra bị `app/services/retrieval.py` / `telemetry_critic.py` quên chưa nối vào `settings` (đang hardcode hằng số trong code), biến nào là cấu hình chết hoặc alias thừa không còn dùng ở bất kỳ đâu (kể cả script ingestion/offline).
  - Gắn lại đúng các ngưỡng đang bị hardcode (nếu cần), xóa sạch cấu hình chết, đảm bảo `100%` các trường còn lại trong `app/config.py` đều có lý do tồn tại rõ ràng.

### Vấn đề 4: Tối ưu hóa Độ trễ RAG E2E thực chất (`avg TTFT 11,280 ms`, Turn 3 `27,779 ms`)
- **Hiện trạng:** Tiny LLM qua Ngrok chỉ mất `~4.08 s`, trong khi các lượt RAG đầy đủ trong Playground (`session_bgsi9hbkmwi6p227`) tốn `13.4s` (Turn 2), `27.8s` (Turn 3), `11.3s` (Turn 4).
- **Yêu cầu:** Profiling chi tiết thời gian từng bước trong `LangGraph` (`router_node` -> `retrieval_node` + `_score_future_points` CPU Rerank -> `crag_grader_node` -> LLM prefill TTFT) để xác định điểm nghẽn thật sự (ví dụ số lượng document đẩy qua INT8 CPU Reranker trong nhánh `future_points` hoặc độ dài system/context prompt) và tối ưu hóa không làm giảm chất lượng sư phạm hay độ chính xác CRAG.

---

## 2. QUY TRÌNH THỰC THI PSTACK VÒNG LẶP #5
1. **Nhịp 1A (`auditor` - `gemini-4-argon-high`):** Kiểm toán nguyên nhân gốc Vấn đề 1, 2, 3, 4; xuất báo cáo `.agent/technical_debt_audit.md`. Cấm Quick-Fix/Regex.
2. **Nhịp 1B (`thinker` - `gemini-4-hydrogen-high`):** Thiết kế đặc tả toán học & kiến trúc sửa triệt để Turn 3/4, chuẩn hóa `app/config.py` và tối ưu latency; xuất `.agent/implementation_spec.md` & cập nhật `.agent/task_plan.md`.
3. **Nhịp 2 (`coder` - `gemini-4-argon-medium`):** Triển khai nguyên tử theo `.agent/implementation_spec.md`, bảo toàn 100% bất biến ONNX GPU/CPU và `LLM_MAX_TOKENS=650`.
4. **Nhịp 3 (`verifier` - `gemini-4-hydrogen-high`):** Chạy `pytest tests/ -v`, `scripts/run_multiturn_benchmark.py`, `scripts/run_rag_benchmark.py --dataset tests/data/benchmark_golden_dataset.json`, kèm kiểm thử tái lập trực tiếp hai ca Turn 3 (`"int và double khác nhau cái gì?"` ở Bài 3) và Turn 4 (`"hình như có nhầm lẫn không? tại sao lại ở bài 64"` ở Bài 1) không còn sai Bài 64 hay rò rỉ chunk/timestamp.

---

## 3. TIÊU CHUẨN NGHIỆM THU VÒNG LẶP #5
1. **Pytest Test Suite:** 100% PASSED (gồm test hồi quy mới cho Turn 3 & Turn 4).
2. **Stage 11 Golden 200:** Router Accuracy $\ge 90.5\%$, CRAG Precision $\ge 88.0\%$, Timestamp Safety $\ge 88.0\%$.
3. **Multi-Turn Benchmark (50 Sessions / 222 Turns):** Intent $\ge 94.0\%$, Retrieval Status $\ge 93.0\%$, ARR $\ge 97.0\%$, SRP $= 100.0\%$.
4. **Config Hygiene & Liêm chính:** 0 biến chết thừa trong `app/config.py`, 0% Regex quick-fix, 0% tráo API thương mại, ONNX E5 GPU + INT8 CPU Reranker nguyên vẹn.
