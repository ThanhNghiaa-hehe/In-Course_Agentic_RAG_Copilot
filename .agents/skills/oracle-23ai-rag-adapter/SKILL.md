---
name: oracle-23ai-rag-adapter
description: Technical blueprint, schema contracts (5 relational tables + native VECTOR column), PL/SQL package/procedure/trigger definitions, python-oracledb integration, and oral defense cheatsheet for adapting In-Course Agentic RAG Copilot to Oracle Database 23ai AI Vector Search (HUFLIT DBMS Final Project - Topic 22).
---

# Oracle Database 23ai AI Vector Search RAG Adapter
**Môn học:** Hệ Quản Trị Cơ Sở Dữ Liệu (Database Management Systems - Oracle Database 23ai)  
**Trường Đại học:** Ngoại ngữ - Tin học TP.HCM (HUFLIT) — Khoa Công nghệ Thông tin  
**Giảng viên phụ trách:** ThS. Lê Thị Minh Nguyện  
**Sinh viên thực hiện:** Trần Thành Nghĩa (MSSV: `23DH112252`)  
**Mã đề tài:** Đề tài số 22 — Nhóm 7: AI Vector Search (Chương 6 - CLO2, CLO4, CLO5)  

---

## 1. THÔNG TIN ĐĂNG KÝ ĐỀ TÀI CHUẨN MỰC (MỤC 3.1)

* **Tên đề tài tiếng Việt:** **Xây dựng hệ thống Chatbot Trợ giảng trực tuyến hỗ trợ sinh viên học lập trình dựa trên công nghệ AI Vector Search trong Oracle Database 23ai (RAG)**
* **Tên đề tài tiếng Anh:** *Building an Online Tutoring Chatbot System Supporting Students in Programming Learning Based on Oracle Database 23ai AI Vector Search*
* **Đoạn văn mô tả bài toán nộp Giảng viên duyệt (3–5 câu):**
  > *"Đề tài xây dựng một hệ thống Trợ giảng AI (Chatbot RAG) hỗ trợ sinh viên giải đáp thắc mắc và tra cứu kiến thức trong các khóa học lập trình (C++/OOP). Hệ thống tận dụng công nghệ **AI Vector Search bản địa của Oracle Database 23ai** để lưu trữ vector nhúng (Embedding Vector 1024 chiều) của các phân đoạn bài giảng và thực hiện tìm kiếm ngữ nghĩa thông qua độ đo **Cosine Distance**. Kết quả truy xuất từ Oracle 23ai được kết hợp cùng mô hình ngôn ngữ lớn (LLM) để phản hồi sinh viên theo phương pháp sư phạm Socratic và tự động điều khiển video player nhảy đến đúng mốc thời gian bài giảng liên quan. Hệ thống được triển khai thành ứng dụng Web hoàn chỉnh kết nối tới CSDL Oracle 23ai qua tầng API FastAPI."*

---

## 2. THIẾT KẾ LƯỢC ĐỒ 5 BẢNG CSDL QUAN HỆ TRONG ORACLE 23AI

Đáp ứng quy chuẩn bắt buộc tại Mục 3.2: *Có tối thiểu 5 bảng quan hệ chuẩn 3NF*:

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
    content_type  VARCHAR2(32) DEFAULT 'video_transcript' CHECK (content_type IN ('video_transcript', 'code_ast', 'markdown_doc')),
    start_sec     NUMBER DEFAULT 0,
    end_sec       NUMBER DEFAULT 0,
    start_label   VARCHAR2(16),
    end_label     VARCHAR2(16),
    raw_text      CLOB NOT NULL,
    -- CỘT VECTOR TRỌNG TÂM CỦA ORACLE DATABASE 23AI (1024-dim từ multilingual-e5-large)
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

## 3. CHỈ MỤC AI VECTOR SEARCH TRÊN ORACLE 23AI

```sql
-- Tạo chỉ mục vector In-Memory Neighbor Graph (HNSW) với độ đo Cosine
CREATE VECTOR INDEX idx_lesson_chunks_vector ON LESSON_CHUNKS(embedding)
ORGANIZATION INMEMORY NEIGHBOR GRAPH
DISTANCE COSINE;
```

---

## 4. LẬP TRÌNH PL/SQL: PACKAGE, PROCEDURES & TRIGGERS

Đáp ứng quy chuẩn bắt buộc: *Tối thiểu 1 package, 3 procedure/function, 2 trigger có xử lý exception*:

### A. Package Specification
```sql
CREATE OR REPLACE PACKAGE PKG_RAG_TUTOR AS
    -- 1. Hàm tìm kiếm ngữ nghĩa theo Vector Cosine Distance
    FUNCTION fn_semantic_search(
        p_query_vec   IN VECTOR,
        p_course_id   IN VARCHAR2,
        p_max_seq     IN NUMBER,
        p_top_k       IN NUMBER DEFAULT 4
    ) RETURN SYS_REFCURSOR;

    -- 2. Thủ tục lưu vết lịch sử tương tác của sinh viên
    PROCEDURE sp_log_chat_interaction(
        p_student_id  IN VARCHAR2,
        p_course_id   IN VARCHAR2,
        p_lesson_id   IN VARCHAR2,
        p_user_prompt IN CLOB,
        p_ai_response IN CLOB,
        p_video_sec   IN NUMBER
    );

    -- 3. Hàm đếm số lượt hỏi bài của sinh viên
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
        v_diff_sec := EXTRACT(SECOND FROM (:NEW.created_at - v_last_time));
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
            RAISE_APPLICATION_ERROR(-20004, 'Mốc thời gian video không hợp lệ (start_sec phải nhỏ hơn end_sec).');
        END IF;
    END IF;
END;
/
```

---

## 5. TÍCH HỢP PYTHON FASTAPI VỚI ORACLE 23AI (`python-oracledb`)

Cài đặt thư viện chính thức: `pip install oracledb`

Đoạn code thay thế `qdrant_client` trong `app/services/retrieval.py`:

```python
import oracledb
import numpy as np
from app.config import settings

def search_oracle23ai_vector(query_vector: np.ndarray, course_id: str, lesson_seq: int, top_k: int = 4):
    """
    Thực hiện Semantic Vector Search trực tiếp trên Oracle Database 23ai bằng python-oracledb.
    """
    connection = oracledb.connect(
        user="system",
        password="YourPassword23ai",
        dsn="127.0.0.1:1521/FREEPDB1"
    )
    cursor = connection.cursor()
    
    # Định dạng mảng float32 thành chuỗi vector Oracle
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

---

## 6. CẨM NANG VẤN ĐÁP BẢO VỆ ĐẠT ĐIỂM TỐI ĐA (MỤC 6.3)

* **Câu 1: "Vì sao bạn chọn độ đo Cosine Distance thay vì Euclidean?"**
  * *Trả lời:* "Dạ thưa Cô, độ đo Cosine đo góc lệch giữa 2 vector trong không gian 1024 chiều, phản ánh chính xác sự tương đồng về ngữ nghĩa mà không bị ảnh hưởng bởi độ dài ngắn của văn bản (độ lớn module vector). Khoảng cách Euclidean bị chi phối bởi độ dài đoạn văn nên dễ chọn sai đoạn văn ngắn."
* **Câu 2: "Embedding vector được tạo ra từ đâu và cập nhật thế nào khi bài giảng thay đổi?"**
  * *Trả lời:* "Dạ thưa Cô, vector được sinh bởi mô hình `multilingual-e5-large` thông qua pipeline Python. Khi giảng viên cập nhật bài mới, hệ thống tính toán vector và gọi lệnh `MERGE INTO LESSON_CHUNKS` để cập nhật cột `embedding`. Chỉ mục `INMEMORY NEIGHBOR GRAPH (HNSW)` của Oracle 23ai sẽ tự động tái cân bằng các liên kết lân cận."
* **Câu 3: "Trigger của bạn có xử lý ngoại lệ gì đặc biệt?"**
  * *Trả lời:* "Dạ thưa Cô, trigger `trg_prevent_chat_spam` kiểm soát tần suất gửi request của sinh viên, bắt lỗi nếu gửi dưới 3 giây và gọi `RAISE_APPLICATION_ERROR(-20001)` để bảo vệ tài nguyên tính toán của CSDL."
