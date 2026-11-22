---
name: oracle-23ai-rag-adapter
description: Technical blueprint, safe backup/clone migration runbook (Qdrant to Oracle 23ai), schema contracts (5 relational 3NF tables + native VECTOR column + Views/Indexes), PL/SQL package/procedure/trigger definitions, python-oracledb ETL & search integration, and oral defense cheatsheet for HUFLIT DBMS Final Project (STT 23 - Topic 22).
---

# Oracle Database 23ai AI Vector Search RAG Adapter
**Môn học:** Hệ Quản Trị Cơ Sở Dữ Liệu (Database Management Systems - Oracle Database 23ai)  
**Trường Đại học:** Ngoại ngữ - Tin học TP.HCM (HUFLIT) — Khoa Công nghệ Thông tin  
**Giảng viên phụ trách:** ThS. Lê Thị Minh Nguyện  
**Sinh viên thực hiện:** Trần Thành Nghĩa (MSSV: `23DH112252`)  
**Mã đề tài:** STT 23 — Mã đề 22: AI Vector Search (Làm cá nhân, Chương 6 - CLO2, CLO4, CLO5)  
**Quy ước tên file báo cáo:** `23_22_TranThanhNghia.docx` (`STT_MaDe_HoTenTruongNhom`)

---

## 0. QUY TRÌNH BACKUP & CLONE AN TOÀN TRƯỚC KHI CHUYỂN ĐỔI (QDRANT → ORACLE 23AI)

Tuyệt đối **KHÔNG** chỉnh sửa đè trực tiếp lên repo gốc đang chạy Qdrant (`d:\In_Course_Agentic_RAG_Copilot`). Thực hiện đúng 4 bước sau để giữ nguyên bản gốc và chuyển đổi mượt mà cho Demo 30/11:

1. **Chốt mốc backup trên repo gốc:**
   ```powershell
   git status
   git add AGENTS.md .agents/ docs/23_22_TranThanhNghia.docx
   git commit -m "chore: snapshot stable Qdrant baseline and DBMS report before Oracle 23ai fork"
   git tag v-qdrant-baseline
   ```
2. **Clone sang workspace độc lập cho bản Oracle 23ai:**
   ```powershell
   cd d:\
   git clone d:\In_Course_Agentic_RAG_Copilot d:\In_Course_Agentic_RAG_Copilot_Oracle23ai
   cd d:\In_Course_Agentic_RAG_Copilot_Oracle23ai
   python -m venv .venv
   .\.venv\Scripts\pip install -r requirements.txt
   .\.venv\Scripts\pip install oracledb
   ```
   *(Mẹo nhanh: có thể copy `.venv` từ repo gốc nếu muốn giữ sẵn model cache, rồi chạy `.\.venv\Scripts\pip install oracledb`).*
3. **Tách biệt `.env` & Dựng container Oracle Database 23ai Free:**
   * Cấu hình `.env` riêng trên bản clone: `ORACLE_USER=system`, `ORACLE_PASSWORD=YourPassword23ai`, `ORACLE_DSN=127.0.0.1:1521/FREEPDB1`.
   * Khởi chạy Docker Oracle 23ai Free:
     ```powershell
     docker run -d --name oracle23ai -p 1521:1521 -e ORACLE_PWD=YourPassword23ai container-registry.oracle.com/database/free:latest
     ```
4. **Nguyên tắc chuyển đổi tối thiểu (Adapter Pattern):**
   * Giữ nguyên toàn bộ `app/services/embedding.py`, `app/agent/`, `app/services/chat.py`, `app/templates/playground.html`.
   * Chỉ thay tầng lưu trữ/truy xuất (`app/services/qdrant.py`, `app/services/retrieval.py`) bằng `OracleVectorService` (`python-oracledb`) và bổ sung các API lịch sử/sinh viên cho buổi demo.

---

## 1. THÔNG TIN ĐĂNG KÝ ĐỀ TÀI CHUẨN MỰC

* **Tên đề tài tiếng Việt:** **Xây dựng hệ thống Chatbot Trợ giảng trực tuyến hỗ trợ sinh viên học lập trình dựa trên công nghệ AI Vector Search trong Oracle Database 23ai (RAG)**
* **Tên đề tài tiếng Anh:** *Building an Online Tutoring Chatbot System Supporting Students in Programming Learning Based on Oracle Database 23ai AI Vector Search*
* **Đoạn văn mô tả bài toán (3–5 câu):**
  > *"Đề tài xây dựng một hệ thống Trợ giảng AI (Chatbot RAG) hỗ trợ sinh viên giải đáp thắc mắc và tra cứu kiến thức trong các khóa học lập trình (C++/OOP). Hệ thống tận dụng công nghệ **AI Vector Search bản địa của Oracle Database 23ai** để lưu trữ vector nhúng (Embedding Vector 1024 chiều) của các phân đoạn bài giảng và thực hiện tìm kiếm ngữ nghĩa thông qua độ đo **Cosine Distance**. Kết quả truy xuất từ Oracle 23ai được kết hợp cùng mô hình ngôn ngữ lớn (LLM) để phản hồi sinh viên theo phương pháp sư phạm Socratic và tự động điều khiển video player nhảy đến đúng mốc thời gian bài giảng liên quan. Hệ thống được triển khai thành ứng dụng Web hoàn chỉnh kết nối tới CSDL Oracle 23ai qua tầng API FastAPI."*

---

## 2. THIẾT KẾ LƯỢC ĐỒ 5 BẢNG CSDL QUAN HỆ TRONG ORACLE 23AI (CHUẨN 3NF)

Đáp ứng quy chuẩn bắt buộc tại Mục 3.2: *Có tối thiểu 5 bảng quan hệ chuẩn 3NF* (phi chuẩn hóa nhẹ có chủ đích `course_id`, `lesson_seq` trên `LESSON_CHUNKS` để tối ưu pre-filter cùng chỉ mục Vector):

```sql
-- 1. BẢNG KHÓA HỌC
CREATE TABLE COURSES (
    course_id    VARCHAR2(32) PRIMARY KEY,
    course_name  VARCHAR2(255) NOT NULL,
    description  VARCHAR2(1000),
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. BẢNG BÀI HỌC
CREATE TABLE LESSONS (
    lesson_id    VARCHAR2(32) PRIMARY KEY,
    course_id    VARCHAR2(32) NOT NULL,
    lesson_seq   NUMBER NOT NULL,
    lesson_title VARCHAR2(255) NOT NULL,
    video_url    VARCHAR2(500),
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_lessons_course FOREIGN KEY (course_id) REFERENCES COURSES(course_id) ON DELETE CASCADE,
    CONSTRAINT uq_course_lesson_seq UNIQUE (course_id, lesson_seq)
);

-- 3. BẢNG PHÂN ĐOẠN BÀI GIẢNG (CHỨA VECTOR EMBEDDING ORACLE 23AI)
CREATE TABLE LESSON_CHUNKS (
    chunk_id      VARCHAR2(64) PRIMARY KEY,
    lesson_id     VARCHAR2(32) NOT NULL,
    course_id     VARCHAR2(32) NOT NULL,
    lesson_seq    NUMBER NOT NULL,
    content_type  VARCHAR2(32) DEFAULT 'video_transcript'
                  CHECK (content_type IN ('video_transcript', 'code_ast', 'markdown_doc')),
    start_sec     NUMBER DEFAULT 0,
    end_sec       NUMBER DEFAULT 0,
    start_label   VARCHAR2(16),
    end_label     VARCHAR2(16),
    raw_text      CLOB NOT NULL,
    embedding     VECTOR(1024, FLOAT32),
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_chunks_lesson FOREIGN KEY (lesson_id) REFERENCES LESSONS(lesson_id) ON DELETE CASCADE
);

-- 4. BẢNG SINH VIÊN
CREATE TABLE STUDENTS (
    student_id   VARCHAR2(32) PRIMARY KEY,
    full_name    VARCHAR2(150) NOT NULL,
    email        VARCHAR2(150) UNIQUE NOT NULL,
    class_name   VARCHAR2(50),
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. BẢNG LỊCH SỬ HỎI ĐÁP CHATBOT
CREATE TABLE CHAT_QUERIES (
    query_id         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id       VARCHAR2(32) NOT NULL,
    course_id        VARCHAR2(32) NOT NULL,
    lesson_id        VARCHAR2(32) NOT NULL,
    user_prompt      CLOB NOT NULL,
    ai_response      CLOB NOT NULL,
    target_video_sec NUMBER,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_chat_student FOREIGN KEY (student_id) REFERENCES STUDENTS(student_id) ON DELETE CASCADE
);
```

---

## 3. CHỈ MỤC AI VECTOR SEARCH, B-TREE INDEX & VIEWS TRÊN ORACLE 23AI

```sql
-- 1. Chỉ mục vector In-Memory Neighbor Graph (HNSW) với độ đo Cosine
CREATE VECTOR INDEX idx_lesson_chunks_vector ON LESSON_CHUNKS(embedding)
ORGANIZATION INMEMORY NEIGHBOR GRAPH
DISTANCE COSINE;

-- 2. Chỉ mục B-Tree phục vụ lọc giáo trình & lịch sử hỏi đáp
CREATE INDEX idx_chunks_course_seq ON LESSON_CHUNKS(course_id, lesson_seq);
CREATE INDEX idx_chat_student_time ON CHAT_QUERIES(student_id, created_at DESC);

-- 3. Views thống kê giáo trình & tương tác sinh viên
CREATE OR REPLACE VIEW v_course_chunk_summary AS
SELECT c.course_id, c.course_name,
       COUNT(DISTINCT l.lesson_id) AS total_lessons,
       COUNT(ch.chunk_id) AS total_chunks,
       SUM(CASE WHEN ch.content_type = 'video_transcript' THEN 1 ELSE 0 END) AS video_chunks,
       SUM(CASE WHEN ch.content_type = 'code_ast' THEN 1 ELSE 0 END) AS code_ast_chunks
FROM COURSES c
LEFT JOIN LESSONS l ON c.course_id = l.course_id
LEFT JOIN LESSON_CHUNKS ch ON l.lesson_id = ch.lesson_id
GROUP BY c.course_id, c.course_name;

CREATE OR REPLACE VIEW v_student_query_stats AS
SELECT s.student_id, s.full_name, s.class_name,
       COUNT(q.query_id) AS total_queries,
       MAX(q.created_at) AS last_query_at
FROM STUDENTS s
LEFT JOIN CHAT_QUERIES q ON s.student_id = q.student_id
GROUP BY s.student_id, s.full_name, s.class_name;
```

---

## 4. LẬP TRÌNH PL/SQL: PACKAGE, PROCEDURES & TRIGGERS

Đáp ứng quy chuẩn bắt buộc: *Tối thiểu 1 package, 3 procedure/function, 2 trigger có xử lý exception*:

### A. Package Specification
```sql
CREATE OR REPLACE PACKAGE PKG_RAG_TUTOR AS
    FUNCTION fn_semantic_search(
        p_query_vec   IN VECTOR,
        p_course_id   IN VARCHAR2,
        p_max_seq     IN NUMBER,
        p_top_k       IN NUMBER DEFAULT 4
    ) RETURN SYS_REFCURSOR;

    PROCEDURE sp_log_chat_interaction(
        p_student_id  IN VARCHAR2,
        p_course_id   IN VARCHAR2,
        p_lesson_id   IN VARCHAR2,
        p_user_prompt IN CLOB,
        p_ai_response IN CLOB,
        p_video_sec   IN NUMBER
    );

    FUNCTION fn_get_student_query_count(
        p_student_id IN VARCHAR2
    ) RETURN NUMBER;
END PKG_RAG_TUTOR;
/
```

### B. Package Body
```sql
CREATE OR REPLACE PACKAGE BODY PKG_RAG_TUTOR AS

    FUNCTION fn_semantic_search(
        p_query_vec   IN VECTOR,
        p_course_id   IN VARCHAR2,
        p_max_seq     IN NUMBER,
        p_top_k       IN NUMBER DEFAULT 4
    ) RETURN SYS_REFCURSOR IS
        v_cursor SYS_REFCURSOR;
    BEGIN
        OPEN v_cursor FOR
            SELECT chunk_id, lesson_id, lesson_seq, content_type,
                   start_sec, end_sec, start_label, end_label, raw_text,
                   VECTOR_DISTANCE(embedding, p_query_vec, COSINE) AS distance
            FROM LESSON_CHUNKS
            WHERE course_id = p_course_id
              AND lesson_seq <= p_max_seq
            ORDER BY distance ASC
            FETCH FIRST p_top_k ROWS ONLY;
        RETURN v_cursor;
    EXCEPTION
        WHEN OTHERS THEN
            RAISE_APPLICATION_ERROR(-20002, 'Lỗi trong quá trình tìm kiếm ngữ nghĩa Vector: ' || SQLERRM);
    END fn_semantic_search;

    PROCEDURE sp_log_chat_interaction(
        p_student_id  IN VARCHAR2,
        p_course_id   IN VARCHAR2,
        p_lesson_id   IN VARCHAR2,
        p_user_prompt IN CLOB,
        p_ai_response IN CLOB,
        p_video_sec   IN NUMBER
    ) IS
    BEGIN
        INSERT INTO CHAT_QUERIES (
            student_id, course_id, lesson_id, user_prompt, ai_response, target_video_sec
        ) VALUES (
            p_student_id, p_course_id, p_lesson_id, p_user_prompt, p_ai_response, p_video_sec
        );
        COMMIT;
    EXCEPTION
        WHEN OTHERS THEN
            ROLLBACK;
            RAISE_APPLICATION_ERROR(-20003, 'Không thể ghi log phiên chat: ' || SQLERRM);
    END sp_log_chat_interaction;

    FUNCTION fn_get_student_query_count(
        p_student_id IN VARCHAR2
    ) RETURN NUMBER IS
        v_count NUMBER := 0;
    BEGIN
        SELECT COUNT(*) INTO v_count
        FROM CHAT_QUERIES
        WHERE student_id = p_student_id;
        RETURN v_count;
    END fn_get_student_query_count;

END PKG_RAG_TUTOR;
/
```

### C. Hai Trigger Bắt Buộc (Có xử lý Exception)
```sql
-- Trigger 1: Ngăn chặn sinh viên gửi câu hỏi liên tiếp dưới 3 giây (Anti-spam)
-- Lưu ý: An toàn cho INSERT ... VALUES đơn dòng; nếu insert lô (INSERT SELECT) cần nâng cấp lên COMPOUND TRIGGER tránh ORA-04091.
CREATE OR REPLACE TRIGGER trg_prevent_chat_spam
BEFORE INSERT ON CHAT_QUERIES
FOR EACH ROW
DECLARE
    v_last_time TIMESTAMP;
    v_diff_sec  NUMBER;
BEGIN
    SELECT MAX(created_at) INTO v_last_time
    FROM CHAT_QUERIES
    WHERE student_id = :NEW.student_id;

    IF v_last_time IS NOT NULL THEN
        v_diff_sec := EXTRACT(DAY FROM (:NEW.created_at - v_last_time)) * 86400
                    + EXTRACT(HOUR FROM (:NEW.created_at - v_last_time)) * 3600
                    + EXTRACT(MINUTE FROM (:NEW.created_at - v_last_time)) * 60
                    + EXTRACT(SECOND FROM (:NEW.created_at - v_last_time));
        IF v_diff_sec < 3.0 THEN
            RAISE_APPLICATION_ERROR(-20001, 'Thao tác quá nhanh! Vui lòng chờ 3 giây giữa hai câu hỏi.');
        END IF;
    END IF;
END;
/

-- Trigger 2: Kiểm toán tính hợp lệ của mốc thời gian bài giảng
CREATE OR REPLACE TRIGGER trg_validate_chunk_timestamps
BEFORE INSERT OR UPDATE ON LESSON_CHUNKS
FOR EACH ROW
BEGIN
    IF :NEW.content_type = 'video_transcript' THEN
        IF :NEW.start_sec < 0 OR :NEW.end_sec < :NEW.start_sec THEN
            RAISE_APPLICATION_ERROR(-20004, 'Mốc thời gian video không hợp lệ (start_sec phải <= end_sec).');
        END IF;
    END IF;
END;
/
```

---

## 5. TÍCH HỢP PYTHON FASTAPI & ETL NẠP DỮ LIỆU ORACLE 23AI (`python-oracledb`)

Cài đặt thư viện chính thức: `pip install oracledb`

### A. Hàm ETL nạp Embeddings vào `LESSON_CHUNKS` (tiền tố `passage: `)
```python
import oracledb
from fastembed import TextEmbedding

def ingest_chunks_to_oracle23ai(chunks: list[dict], dsn: str = "127.0.0.1:1521/FREEPDB1"):
    """Sinh Vector 1024 chiều từ intfloat/multilingual-e5-large và nạp vào Oracle 23ai bằng MERGE INTO."""
    embed_model = TextEmbedding("intfloat/multilingual-e5-large")
    passages = [f"passage: {c['raw_text']}" for c in chunks]
    vectors = list(embed_model.embed(passages, batch_size=32))

    conn = oracledb.connect(user="system", password="YourPassword23ai", dsn=dsn)
    cur = conn.cursor()
    sql_merge = """
        MERGE INTO LESSON_CHUNKS tgt
        USING (SELECT :chunk_id AS cid FROM DUAL) src
        ON (tgt.chunk_id = src.cid)
        WHEN MATCHED THEN UPDATE SET
            tgt.raw_text = :raw_text,
            tgt.embedding = TO_VECTOR(:vec_str, 1024, FLOAT32)
        WHEN NOT MATCHED THEN INSERT (
            chunk_id, lesson_id, course_id, lesson_seq, content_type,
            start_sec, end_sec, start_label, end_label, raw_text, embedding
        ) VALUES (
            :chunk_id, :lesson_id, :course_id, :lesson_seq, :content_type,
            :start_sec, :end_sec, :start_label, :end_label, :raw_text,
            TO_VECTOR(:vec_str, 1024, FLOAT32)
        )
    """
    for chunk, vec in zip(chunks, vectors):
        vec_str = "[" + ",".join(f"{float(x):.6f}" for x in vec.tolist()) + "]"
        cur.execute(sql_merge, {
            "chunk_id": chunk["chunk_id"], "lesson_id": chunk["lesson_id"],
            "course_id": chunk["course_id"], "lesson_seq": chunk["lesson_seq"],
            "content_type": chunk["content_type"], "start_sec": chunk["start_sec"],
            "end_sec": chunk["end_sec"], "start_label": chunk["start_label"],
            "end_label": chunk["end_label"], "raw_text": chunk["raw_text"],
            "vec_str": vec_str,
        })
    conn.commit()
    cur.close()
    conn.close()
```

### B. Hàm truy vấn thay thế `qdrant_client` trong `app/services/retrieval.py`
```python
import oracledb
import numpy as np

def search_oracle23ai_vector(query_vector: np.ndarray, course_id: str, lesson_seq: int, top_k: int = 4):
    """Thực hiện Semantic Vector Search trực tiếp trên Oracle Database 23ai bằng python-oracledb."""
    connection = oracledb.connect(
        user="system",
        password="YourPassword23ai",
        dsn="127.0.0.1:1521/FREEPDB1"
    )
    cursor = connection.cursor()
    vec_str = "[" + ",".join(map(str, query_vector.tolist())) + "]"

    sql = """
        SELECT chunk_id, lesson_id, lesson_seq, content_type,
               start_sec, end_sec, start_label, end_label, raw_text,
               VECTOR_DISTANCE(embedding, TO_VECTOR(:1), COSINE) AS distance
        FROM LESSON_CHUNKS
        WHERE course_id = :2
          AND lesson_seq <= :3
        ORDER BY distance ASC
        FETCH FIRST :4 ROWS ONLY
    """
    cursor.execute(sql, [vec_str, course_id, lesson_seq, top_k])
    rows = cursor.fetchall()
    cursor.close()
    connection.close()
    return rows
```

### C. Các API cần bổ sung ở bản clone cho Demo 30/11
* Giữ nguyên: `POST /api/v1/search`, `POST /api/v1/chat/stream`, `POST /api/v1/chat/reset`, `GET /health`.
* Bổ sung cho Oracle 23ai: `GET /api/v1/courses`, `GET /api/v1/students`, `GET /api/v1/chat/history` (truy vấn `CHAT_QUERIES` + `fn_get_student_query_count`), và gọi `PKG_RAG_TUTOR.sp_log_chat_interaction` cuối mỗi lượt `/api/v1/chat/stream`.

👉 Xem chi tiết **5 kịch bản kiểm thử (`TC01`–`TC05` + `EXPLAIN PLAN`)** và **chuẩn xuất báo cáo Word HUFLIT** tại:
[migration_and_report_checklist.md](./references/migration_and_report_checklist.md)

---

## 6. CẨM NANG VẤN ĐÁP BẢO VỆ ĐẠT ĐIỂM TỐI ĐA

* **Câu 1: "Vì sao bạn chọn độ đo Cosine Distance thay vì Euclidean?"**
  * *Trả lời:* "Dạ thưa Cô, độ đo Cosine đo góc lệch giữa 2 vector trong không gian 1024 chiều, phản ánh chính xác sự tương đồng về ngữ nghĩa mà không bị ảnh hưởng bởi độ dài ngắn của văn bản (độ lớn module vector). Khoảng cách Euclidean bị chi phối bởi độ dài đoạn văn nên dễ chọn sai đoạn văn ngắn."
* **Câu 2: "Embedding vector được tạo ra từ đâu và cập nhật thế nào khi bài giảng thay đổi?"**
  * *Trả lời:* "Dạ thưa Cô, vector được sinh bởi mô hình `intfloat/multilingual-e5-large` thông qua pipeline Python (`passage: ` khi index, `query: ` khi hỏi). Khi giảng viên cập nhật bài mới, hệ thống tính toán lại vector và gọi lệnh `MERGE INTO LESSON_CHUNKS` để cập nhật cột `embedding`. Chỉ mục `INMEMORY NEIGHBOR GRAPH (HNSW)` của Oracle 23ai tự động cập nhật liên kết lân cận."
* **Câu 3: "Trigger của bạn có xử lý ngoại lệ gì và có gây lỗi Mutating Table không?"**
  * *Trả lời:* "Dạ thưa Cô, trigger `trg_prevent_chat_spam` kiểm soát tần suất gửi request của sinh viên, bắt lỗi nếu gửi dưới 3 giây và gọi `RAISE_APPLICATION_ERROR(-20001)` để bảo vệ tài nguyên CSDL. Với luồng `INSERT ... VALUES` từng lượt hỏi đơn lẻ thì không gây `ORA-04091`; nếu sau này mở rộng chèn lô bằng `INSERT INTO ... SELECT`, em sẽ chuyển sang `COMPOUND TRIGGER` để lưu trạng thái ở cấp statement."
