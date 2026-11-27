# Checklist Kiểm thử Oracle 23ai & Quy chuẩn Báo cáo HUFLIT

Tài liệu tham chiếu chi tiết đi kèm skill [oracle-23ai-rag-adapter](../SKILL.md) cho đồ án môn *Các Hệ Quản Trị Cơ Sở Dữ Liệu* (HUFLIT — Giảng viên: ThS. Lê Thị Minh Nguyện).

---

## 1. Năm Kịch Bản Kiểm Thử Bắt Buộc (Demo 30/11 & Phụ lục Kiểm chứng)

Theo yêu cầu đề cương `Nganh HTTT_ CNPM DBMS_25_De_Tai_Do_An_Cuoi_Ky.pdf` (Mục 3.1 & Chương 4):

| Mã KB | Kịch bản kiểm thử & Điều kiện đầu vào | Kết quả kỳ vọng trên Oracle 23ai |
| :--- | :--- | :--- |
| `TC01` | Tìm kiếm ngữ nghĩa hợp lệ trong phạm vi bài đã học (`course_id='cpp-core'`, `lesson_seq <= 6`). | `fn_semantic_search` trả Top-K chunks theo `VECTOR_DISTANCE(COSINE)` tăng dần kèm `start_sec`. |
| `TC02` | Chống rò rỉ kiến thức bài tương lai: hỏi khái niệm OOP khi ở Bài 1 (`lesson_seq <= 1`). | Mệnh đề `WHERE course_id = :2 AND lesson_seq <= 1` loại bỏ hoàn toàn các chunk bài sau. |
| `TC03` | Kiểm thử biên Trigger `trg_prevent_chat_spam`: gọi `sp_log_chat_interaction` 2 lần liên tiếp `< 3s` cùng `student_id`. | Oracle ném ngoại lệ `ORA-20001`, thực hiện `ROLLBACK` bảo toàn CSDL. |
| `TC04` | Kiểm thử lỗi dữ liệu Trigger `trg_validate_chunk_timestamps`: chèn chunk `video_transcript` có `end_sec < start_sec`. | Oracle ném ngoại lệ `ORA-20004`, từ chối bản ghi thời gian sai lệch trước khi `COMMIT`. |
| `TC05` | Chạy `EXPLAIN PLAN FOR` cho truy vấn `VECTOR_DISTANCE` trước và sau khi tạo `idx_lesson_chunks_vector` (HNSW) & `idx_chunks_course_seq`. | Chuyển từ `TABLE ACCESS FULL` sang `VECTOR INDEX SCAN` / `Range Scan`, giảm Cost truy vấn (chụp ảnh minh chứng bỏ vào báo cáo). |

---

## 2. Nguyên Tắc Trung Thực Số Liệu (Zero Hallucination)

* Tuyệt đối **không** ghi các con số benchmark độ trễ Oracle 23ai (như `< 20ms`) khi chưa dựng container Oracle 23ai và đo thực tế.
* Phân tách rõ ràng giữa:
  * **Nguyên mẫu đang vận hành:** `83` bài học (`52` `cpp-core` + `31` `cpp-oop`), `faster-whisper` + Silero VAD (`threshold=0.35`, `min_speech_duration_ms=150`, `min_silence_duration_ms=800`, `speech_pad_ms=400`), `CppASTChunker`, `intfloat/multilingual-e5-large` (`@lru_cache(maxsize=512)`), `jinaai/jina-reranker-v2-base-multilingual`, `TimestampWhitelistHTMLParser`, Playground 3 cột.
  * **Tầng chuyển đổi Oracle 23ai:** Lược đồ 5 bảng, Views, Indexes, PL/SQL, Triggers, ETL & API mở rộng.

---

## 3. Quy Chuẩn Xuất Báo Cáo Word HUFLIT (`23_22_TranThanhNghia.docx`)

Đã kiểm chứng 1-to-1 với mẫu `Report_KLTN_1_ Duy - Copy.docx`:
* **Tên file:** `STT_MaDe_HoTenTruongNhom.docx` → `23_22_TranThanhNghia.docx` (bỏ chữ nhóm nếu làm cá nhân).
* **Lề trang:** Phần đầu (`Sec 0, 1`): `T=3.0, B=3.0, L=3.5, R=2.0 cm`; Phần nội dung (`Sec 2`): `T=2.5, B=2.5, L=3.0, R=2.0 cm`.
* **Header & Footer:** Header dùng trường Word `STYLEREF 1 \* MERGEFORMAT` (`Times New Roman 11pt`, đen `#000000`, kẻ ngang bên dưới); Footer chỉ có số trang `13pt` căn giữa (`lowerRoman` ở phần đầu, `decimal` ở nội dung). Trang bìa để trống Header/Footer.
* **Cỡ chữ & Màu sắc:** 100% chữ & sơ đồ màu đen `#000000`; `Heading 1` `15pt` Đậm căn giữa; `Heading 2` `14pt` Đậm; `Heading 3` `13pt` Đậm Nghiêng; Nội dung `Times New Roman 13pt`, giãn dòng `1.5`, thụt đầu dòng `1.27 cm`, gạch đầu dòng `– `.
* **Bảng biểu & Khung Code:** Hàng tiêu đề tô `#D9D9D9` (`13pt` Đậm căn giữa); Bảng Đặc tả Use Case đặt hàng `UseCase ID | UC0x` làm hàng đầu tiên tô `#D9D9D9`; Khung code nền `#F2F2F2`, `Consolas 10pt`, viền đen.
* **Sơ đồ UML/ERD/Kiến trúc:** Xuất 300 DPI nền trắng nét đen (không màu mè, không nền tối AI slop); kiểm tra cuối cùng bằng `validate_docx.py` và Microsoft Word COM (`TablesOfContents.Update()`, `Fields.Update()`).
