# Unified E2E Spec 006: Oracle Database 23ai AI Vector Search RAG Adapter

- **Ngày lập / Phiên bản:** `2026-11-27` (v1.0)
- **Sinh viên thực hiện:** Trần Thành Nghĩa (MSSV: `23DH112252`) — Trường Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT)
- **Môn học / Giảng viên:** Các Hệ Quản Trị Cơ Sở Dữ Liệu — ThS. Lê Thị Minh Nguyện
- **Mã đề tài:** STT 23 — Mã đề 22: *AI Vector Search trên Oracle Database 23ai* (Báo cáo Word: `docs/23_22_TranThanhNghia.docx`)
- **Trạng thái:** `READY_FOR_CLONE` (Chỉ triển khai mã Oracle trong bản clone độc lập `D:\In_Course_Agentic_RAG_Copilot_Oracle23ai`, **tuyệt đối không** sửa đè lên repo Qdrant gốc đang gắn tag `v-qdrant-baseline`).
- **Phạm vi tác động (Layers):** `[x] Config (.env)` `[x] Database DDL/PLSQL` `[x] ETL Script` `[x] Retrieval Adapter` `[x] Health/Demo API` `[x] Tests` — **Bảo toàn 100%** Router, NLI, Socratic Guardrails, LangGraph, Embedding, LLM Serving & Playground UI.

---

## 1. Constitution Check & Bản đồ Kế thừa Kiến trúc (Inheritance Map)

### 1.1. Các nguyên tắc bất biến (`AGENTS.md` & `oracle-23ai-rag-adapter`)
- [x] **Clone Cô lập Trước khi Sửa (Non-Destructive Fork):** Chốt tag `v-qdrant-baseline` trên `D:\In_Course_Agentic_RAG_Copilot` và `git clone` sang `D:\In_Course_Agentic_RAG_Copilot_Oracle23ai`. Mọi thay đổi Oracle 23ai chỉ nằm ở repo clone.
- [x] **Zero-Regex Core (`app/`):** Duy trì `0% import re` trong thư mục `app/` trên cả bản clone (sử dụng HTMLParser, AST, Unicode intervals, Pydantic v2 & SQL parameterized bind variables).
- [x] **Asymmetric E5 Prefix & NFC Parity:** Giữ nguyên tiền tố `"passage: "` khi ETL nạp `LESSON_CHUNKS.embedding` và `"query: "` khi nhúng câu hỏi tìm kiếm `intfloat/multilingual-e5-large` (1024-dim, chuẩn hóa Unicode **NFC**).
- [x] **Oracle 23ai Mandatory Scope (Đề cương Mục 3.2 & Chương 4):** Tối thiểu **5 bảng quan hệ chuẩn 3NF**, **1 Native `VECTOR(1024, FLOAT32)` + HNSW Index**, **Views**, **B-Tree Indexes**, **1 PL/SQL Package + 3 Procedures/Functions + 2 Triggers có `RAISE_APPLICATION_ERROR`**, và **5 test cases `TC01`–`TC05` + `EXPLAIN PLAN`**.
- [x] **Zero Benchmark Hallucination:** Không ghi bất kỳ con số độ trễ/cost Oracle 23ai nào trước khi dựng container `FREEPDB1` và đo thực tế.

### 1.2. Bảng Phân tách Kế thừa 100% vs Tầng Adapter Oracle 23ai

| Thành phần trong Repo Gốc (`v-qdrant-baseline`) | Trạng thái ở Bản Clone Oracle 23ai | Lý do & Hợp đồng |
|---|---|---|
| `app/services/embedding.py` (E5-large 1024-dim + `@lru_cache`) | **Kế thừa 100% (không sửa)** | Sinh vector 1024-dim `FLOAT32` chuẩn E5, truyền thẳng vào Oracle `TO_VECTOR(:vec_str, 1024, FLOAT32)`. |
| `app/agent/router.py`, `slm_router_int8.onnx` (v2.3.0), `mDeBERTa-v3` | **Kế thừa 100% (không sửa)** | Đã đạt Golden `88.00%`, Adv-Hybrid `77.50%`, OOD `92.00%`, 70/70 pytest PASS. |
| `app/agent/guardrails.py`, `app/agent/prompts.py`, `app/services/curriculum.py` | **Kế thừa 100% (không sửa)** | Bảo toàn OWASP LLM01, Socratic AST Sanitizer, FSM Timestamp Whitelist $\mathcal{W}$, DAG 83 bài học. |
| `app/services/chat_graph.py`, `app/services/chat.py`, `app/templates/playground.html` | **Kế thừa 99% (chỉ gọi hook ghi log SQL)** | Cuối mỗi lượt stream hoàn chỉnh gọi bất đồng bộ `sp_log_chat_interaction` lưu vào `CHAT_QUERIES` (xử lý graceful `ORA-20001`). |
| `data/curriculum/lessons_manifest.json`, `data/transcripts/`, `data/code_samples/` | **Kế thừa 100% làm nguồn ETL** | Toàn bộ 83 bài học (`52 cpp-core` + `31 cpp-oop`) + transcript + AST code chunks được nạp trực tiếp vào Oracle 23ai. |
| `scripts/kaggle_jobs/serve_qwen25_vllm_kaggle.py`, `scripts/sync_kaggle_llm_env.py`, `data/models/qwen25-coder-7b-socratic-lora/` | **Kế thừa 100%** | Dùng nguyên QLoRA v2 trên Kaggle GPU qua tunnel Cloudflare/HMAC đã kiểm chứng. |
| `app/services/qdrant.py` | **Thay / Bọc bởi `app/services/oracle_db.py`** | Tầng kết nối `python-oracledb` Thin Mode (`oracledb.create_pool`), kiểm tra `/health` Oracle `FREEPDB1`. |
| `app/services/retrieval.py` | **Mở rộng theo Adapter Pattern** | Phân nhánh theo `settings.VECTOR_BACKEND` (`oracle23ai` vs `qdrant`), vẫn giữ nguyên đầu ra cho Jina Reranker INT8 & CRAG Grader. |
| *(Mới)* `database/oracle23ai/*.sql` & `scripts/etl_ingest_oracle23ai.py` | **Tạo mới hoàn toàn** | DDL 5 bảng 3NF, HNSW + B-Tree Indexes, Views, `PKG_RAG_TUTOR`, Triggers và script ETL `MERGE INTO`. |
| *(Mới)* `app/api/v1/oracle_demo.py` | **Tạo mới hoàn toàn** | Endpoint demo DBMS: `/courses`, `/students`, `/chat/history`, `/analytics/stats`. |

---

## 2. Hợp đồng Lược đồ CSDL Quan hệ 3NF & Native Vector (`Oracle 23ai`)

### 2.1. Mô hình 5 bảng chuẩn 3NF + Cột `VECTOR(1024, FLOAT32)`
Lưu thành `database/oracle23ai/01_schema.sql`:

1. **`COURSES`** (`course_id PK`, `course_name`, `description`, `created_at`)
2. **`LESSONS`** (`lesson_id PK`, `course_id FK -> COURSES ON DELETE CASCADE`, `lesson_seq`, `lesson_title`, `video_url`, `created_at`, `CONSTRAINT uq_course_lesson_seq UNIQUE (course_id, lesson_seq)`)
3. **`LESSON_CHUNKS`** (`chunk_id PK`, `lesson_id FK -> LESSONS ON DELETE CASCADE`, `course_id NOT NULL`, `lesson_seq NOT NULL`, `content_type CHECK IN ('video_transcript','code_ast','markdown_doc')`, `start_sec`, `end_sec`, `start_label`, `end_label`, `raw_text CLOB NOT NULL`, `embedding VECTOR(1024, FLOAT32)`, `created_at`)
   - *Phi chuẩn hóa có chủ đích (`course_id`, `lesson_seq`):* Tránh phép `JOIN` đắt đỏ với `LESSONS` bên trong vòng quét vector `WHERE course_id = :c AND lesson_seq <= :max_seq` cùng `VECTOR_DISTANCE(...)`.
4. **`STUDENTS`** (`student_id PK`, `full_name NOT NULL`, `email UNIQUE NOT NULL`, `class_name`, `created_at`)
5. **`CHAT_QUERIES`** (`query_id NUMBER GENERATED ALWAYS AS IDENTITY PK`, `student_id FK -> STUDENTS ON DELETE CASCADE`, `course_id`, `lesson_id`, `user_prompt CLOB`, `ai_response CLOB`, `target_video_sec NUMBER`, `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`)

### 2.2. Chỉ mục & Views (`02_indexes_and_views.sql`)
- **Vector Index (HNSW In-Memory):**
  ```sql
  CREATE VECTOR INDEX idx_lesson_chunks_vector ON LESSON_CHUNKS(embedding)
  ORGANIZATION INMEMORY NEIGHBOR GRAPH
  DISTANCE COSINE;
  ```
- **B-Tree Indexes:**
  - `idx_chunks_course_seq ON LESSON_CHUNKS(course_id, lesson_seq)`
  - `idx_chat_student_time ON CHAT_QUERIES(student_id, created_at DESC)`
- **Views phân tích SQL:**
  - `v_course_chunk_summary` (thống kê số bài, tổng chunk, phân loại `video_transcript` vs `code_ast` theo khóa học)
  - `v_student_query_stats` (thống kê tổng lượt hỏi & thời điểm hỏi gần nhất theo sinh viên)

### 2.3. Đối chiếu Ánh xạ Dữ liệu Qdrant $\leftrightarrow$ Oracle 23ai

| Trường dữ liệu trên Qdrant (`payload` / `vector`) | Cột trên Oracle 23ai (`LESSON_CHUNKS`) | Biến đổi ở tầng Python Adapter |
|---|---|---|
| `point.id` (UUIDv5) | `chunk_id VARCHAR2(64)` | Giữ nguyên UUIDv5 idempotent để chạy `MERGE INTO` không trùng bản ghi. |
| `vector["dense"]` (`float[1024]`) | `embedding VECTOR(1024, FLOAT32)` | Serialize `"[" + ",".join(f"{x:.6f}" for x in vec) + "]"` -> `TO_VECTOR(:vec_str, 1024, FLOAT32)`. |
| `payload["text"]` / `raw_text` | `raw_text CLOB` | Bắt buộc cấu hình `oracledb.defaults.fetch_lobs = False` để nhận `str` trực tiếp, không tốn thêm round-trip đọc `LOB`. |
| `payload["course_id"]`, `lesson_seq` | `course_id`, `lesson_seq` | Ràng buộc điều kiện `WHERE course_id = :2 AND lesson_seq <= :3` chống rò rỉ bài tương lai (`In-Course Leak Prevention`). |
| `payload["start_sec"]`, `end_sec`, `start_label`, `end_label` | `start_sec`, `end_sec`, `start_label`, `end_label` | Trả nguyên về `RetrievalResult` để giữ 100% Whitelist Timestamp $\mathcal{W}$ và `player.seekTo(sec)`. |
| `hit.score` (`Cosine Similarity`, cao là tốt) | `VECTOR_DISTANCE(embedding, :qvec, COSINE) AS distance` | **Quy đổi bắt buộc:** Oracle trả `distance` $[0, 2]$ (càng nhỏ càng gần), Adapter chuẩn hóa `similarity = max(0.0, 1.0 - float(distance))` rồi đẩy tiếp qua Jina Reranker INT8 & CRAG. |

---

## 3. Hợp đồng PL/SQL Package & Triggers (`03_plsql_package_and_triggers.sql`)

1. **`PKG_RAG_TUTOR` Package:**
   - `fn_semantic_search(p_query_vec IN VECTOR, p_course_id IN VARCHAR2, p_max_seq IN NUMBER, p_top_k IN NUMBER DEFAULT 4) RETURN SYS_REFCURSOR` — Truy vấn `VECTOR_DISTANCE(embedding, p_query_vec, COSINE) ASC FETCH FIRST p_top_k ROWS ONLY`, bắt `EXCEPTION WHEN OTHERS` và ném `ORA-20002`.
   - `sp_log_chat_interaction(p_student_id, p_course_id, p_lesson_id, p_user_prompt, p_ai_response, p_video_sec)` — `INSERT INTO CHAT_QUERIES ...; COMMIT;`, lỗi thì `ROLLBACK` và ném `ORA-20003`.
   - `fn_get_student_query_count(p_student_id IN VARCHAR2) RETURN NUMBER` — Đếm số lượt tương tác của sinh viên.
2. **2 Triggers kiểm soát nghiệp vụ & toàn vẹn:**
   - `trg_prevent_chat_spam` (`BEFORE INSERT ON CHAT_QUERIES FOR EACH ROW`): Tính `v_diff_sec = :NEW.created_at - MAX(created_at)`; nếu `< 3.0` giây thì ném `ORA-20001`.
     > *Lưu ý kiến trúc:* Dùng `INSERT ... VALUES` từng lượt hỏi đơn lẻ không gây `ORA-04091` (Mutating Table); nếu nâng cấp chèn lô `INSERT ... SELECT`, phải chuyển sang `COMPOUND TRIGGER`.
   - `trg_validate_chunk_timestamps` (`BEFORE INSERT OR UPDATE ON LESSON_CHUNKS FOR EACH ROW`): Khi `content_type = 'video_transcript'`, bắt buộc `0 <= start_sec <= end_sec`, sai ném `ORA-20004`.

---

## 4. Thứ tự Triển khai trên Bản Clone (Dependency-Ordered Steps)

Mọi bước dưới đây **chỉ chạy trong workspace clone `D:\In_Course_Agentic_RAG_Copilot_Oracle23ai`**:

1. **Bước 1 — Clone & Cô lập Môi trường:**
   - `git clone D:\In_Course_Agentic_RAG_Copilot D:\In_Course_Agentic_RAG_Copilot_Oracle23ai`
   - Kế thừa `.venv`, `data/models/`, `.env` từ repo gốc; cài `pip install oracledb`.
   - Thêm cấu hình Oracle vào `.env` & `app/config.py`: `VECTOR_BACKEND=oracle23ai`, `ORACLE_USER=system`, `ORACLE_PASSWORD=...`, `ORACLE_DSN=127.0.0.1:1521/FREEPDB1`.
2. **Bước 2 — Khởi tạo Oracle Database 23ai Free (Docker) & Chạy SQL Schema:**
   - Dựng container `container-registry.oracle.com/database/free:latest` (`1521:1521`).
   - Tạo thư mục `database/oracle23ai/` gồm `01_schema.sql`, `02_indexes_and_views.sql`, `03_plsql_package_and_triggers.sql`, `04_seed_students_and_courses.sql`.
3. **Bước 3 — Xây dựng & Chạy ETL Ingestion (`scripts/etl_ingest_oracle23ai.py`):**
   - Đọc `lessons_manifest.json` + transcript chunks (`*_chunks.json`) + AST code chunks (`*_code_chunks.json`).
   - Nạp `COURSES` (2 khóa), `LESSONS` (83 bài) và `LESSON_CHUNKS` (~6.400+ phân đoạn) bằng E5 `"passage: "` + NFC + `MERGE INTO`, kiểm tra đếm dòng khớp 100% giữa manifest và Oracle.
4. **Bước 4 — Hiện thực `app/services/oracle_db.py` & Retrieval Adapter:**
   - Tạo `OracleVectorService` (`python-oracledb` Thin Mode, connection pool, `fetch_lobs=False`).
   - Nối nhánh `VECTOR_BACKEND == "oracle23ai"` trong `app/services/retrieval.py`: ưu tiên gọi `VECTOR_DISTANCE(..., COSINE)` (hoặc `PKG_RAG_TUTOR.fn_semantic_search`), chuyển `similarity = 1.0 - distance`, giữ nguyên tầng Jina Reranker v2 INT8 & Hybrid/TS boosting ở phía sau.
   - Cập nhật `/health` báo cáo trạng thái Oracle `FREEPDB1` + số dòng `LESSON_CHUNKS` + trạng thái `VECTOR INDEX`.
5. **Bước 5 — Bổ sung API Demo DBMS & Hook Ghi log Hội thoại:**
   - Thêm router `app/api/v1/oracle_demo.py`: `GET /api/v1/courses`, `GET /api/v1/students`, `GET /api/v1/chat/history`, `GET /api/v1/analytics/stats` (truy vấn Views `v_course_chunk_summary`, `v_student_query_stats`).
   - Gắn hook gọi `PKG_RAG_TUTOR.sp_log_chat_interaction` vào luồng hoàn tất `/api/v1/chat/stream` (nếu vướng `ORA-20001` do gửi < 3s thì ghi cảnh báo log mà không làm crash SSE stream hoặc trả mã 429 có kiểm soát theo kịch bản test).
6. **Bước 6 — Nghiệm thu `TC01`–`TC05`, `EXPLAIN PLAN` & Hoàn thiện Báo cáo Word `23_22_TranThanhNghia.docx`.**

---

## 5. Cross-Layer Conflict & Invariant Matrix (Cổng Chống Xung đột Chéo)

| Thay đổi Oracle 23ai | Nguy cơ xung đột chéo với hệ thống RAG hiện có | Cơ chế phòng ngừa bắt buộc | Kiểm chứng |
|---|---|---|---|
| Thay Cosine Similarity của Qdrant bằng `VECTOR_DISTANCE(..., COSINE)` của Oracle | `VECTOR_DISTANCE` trả khoảng cách ($0$ là giống nhất, $2$ là ngược hướng), nếu đưa thẳng vào Jina/CRAG sẽ đảo ngược thứ tự lọc ngưỡng! | Chuyển đổi ngay ở Adapter: `score = max(0.0, 1.0 - float(distance))`, thêm unit test kiểm tra thứ tự giảm dần. | Unit test Retrieval Adapter + `TC01` |
| Cột `raw_text`, `user_prompt`, `ai_response` dùng kiểu `CLOB` | Mặc định `python-oracledb` trả `LOB` object gây chậm 10x nếu mở stream đọc từng dòng. | Đặt `oracledb.defaults.fetch_lobs = False` ngay khi khởi tạo pool trong `oracle_db.py`. | Smoke test `fn_semantic_search` |
| Trigger `trg_prevent_chat_spam` ném `ORA-20001` khi gửi dưới `3s` | Khi chạy script test tự động (E2E harness) nhiều lượt liên tiếp < 3s, Trigger sẽ chặn làm lỗi phiên test! | Bọc `sp_log_chat_interaction` trong `try/except oracledb.DatabaseError`: phát hiện `ORA-20001` trả log cảnh báo nhẹ hoặc chỉ bật test trigger chuyên biệt qua `TC03` / API riêng. | `TC03` + Live Playground test |
| Chạy đồng thời Docker Oracle 23ai Free + Local FastAPI GPU + Local PyTorch | Docker Oracle 23ai Free chiếm ~2–4 GB RAM hệ thống; kết hợp E5 GPU dễ chạm ngưỡng VRAM 4 GB RTX 2050 nếu bật 2 process E5. | Chỉ chạy **1** server `uvicorn` duy nhất; đóng ứng dụng nặng khi đo `TC05` / demo; chạy pytest/ETL với `CUDA_VISIBLE_DEVICES=-1` nếu `uvicorn` đang bật. | `nvidia-smi` + `docker stats` |
| Thiếu Lexical BM25 bản địa trên bảng `LESSON_CHUNKS` khi bỏ Qdrant Sparse | Truy vấn chứa tên hàm C++ chính xác (`push_back`, `std::sort`) có thể tụt nhẹ điểm dense nếu không có lexical match. | Giữ Jina Reranker v2 INT8 trên Top-K ($K=12..15$) từ Oracle Vector Index; nếu cần có thể bổ sung Oracle Text index hoặc tính điểm token overlap nhẹ trên tập Top-K đã rút về Python. | `TC01` + so sánh chất lượng với `v-qdrant-baseline` |

---

## 6. Kế hoạch Nghiệm thu (`TC01`–`TC05` & Demo 30/11)

1. **5 Kịch bản Kiểm thử Bắt buộc (`pytest tests/test_oracle23ai_suite.py` & SQL*Plus/SQLcl):**
   - `TC01`: `fn_semantic_search` trong phạm vi `course_id='cpp-core'`, `lesson_seq <= 6` trả đúng Top-K chunks & `start_sec` tăng dần theo tương đồng.
   - `TC02`: Ở Bài 1 (`lesson_seq <= 1`), hỏi kiến thức OOP — mệnh đề `lesson_seq <= 1` chặn 100% chunk bài tương lai.
   - `TC03`: Gọi `sp_log_chat_interaction` 2 lần liên tiếp `< 3s` cùng `student_id` -> bắt đúng ngoại lệ `ORA-20001`.
   - `TC04`: Chèn `LESSON_CHUNKS` có `content_type='video_transcript'` và `end_sec < start_sec` -> bắt đúng ngoại lệ `ORA-20004`.
   - `TC05`: Chạy `EXPLAIN PLAN FOR SELECT ... ORDER BY VECTOR_DISTANCE(...) FETCH FIRST 4 ROWS ONLY` **trước** và **sau** khi tạo `idx_lesson_chunks_vector` (HNSW) + `idx_chunks_course_seq` -> chụp ảnh minh chứng chuyển từ `TABLE ACCESS FULL` sang `VECTOR INDEX` vào Phụ lục báo cáo.
2. **Kiểm chứng End-to-End Ứng dụng Web trên Clone:**
   - `GET /health` -> Oracle `FREEPDB1` online, đủ 83 bài học & `LESSON_CHUNKS` > 6.400 dòng.
   - `GET /api/v1/courses`, `/api/v1/students`, `/api/v1/chat/history`, `/api/v1/analytics/stats` -> HTTP 200 dữ liệu thật từ Oracle.
   - Chat trên Playground UI -> trả lời Socratic qua QLoRA v2 + click `<timestamp>` tua video + kiểm tra bảng `CHAT_QUERIES` ghi nhận bản ghi mới.
3. **Chốt Báo cáo Word HUFLIT (`docs/23_22_TranThanhNghia.docx`):**
   - Đính kèm đầy đủ ảnh/log thực tế sau khi chạy `TC01`–`TC05` (tuyệt đối không dùng số liệu ước lượng), kiểm tra chuẩn định dạng với `validate_docx.py` & Word COM (`TablesOfContents.Update()`).
