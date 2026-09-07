---
name: qdrant-hybrid-inspector
description: Deep inspection, payload schema contract verification, dual vector sanity check (1024-dim dense + sparse BM25), In-HNSW index auditing, and international latency benchmarking for Qdrant Cloud cluster.
---

# Qdrant Hybrid Inspector Runbook

## 1. Mục Đích & Phạm Vi Áp Dụng
Sử dụng kỹ năng này khi:
- Cần kiểm định sức khỏe và tính toàn vẹn của cluster **Qdrant Cloud** sau mỗi lần nạp video hoặc mã nguồn AST.
- Gặp lỗi truy vấn không ra kết quả hoặc nghi ngờ dữ liệu bị mất, bị trùng lặp points.
- Cần xác thực **6 Payload Indexes** bắt buộc phục vụ In-HNSW Dynamic Pre-filtering (`lesson_seq <= current_seq`).
- Đo đạc độ trễ mạng quốc tế (Latency round-trip) từ local đến cluster GCP Australia.

---

## 2. Quy Trình Thực Hiện & Debug (Step-by-Step)

```text
[BƯỚC 1: HEALTHCHECK] ➔ [BƯỚC 2: VECTOR AUDIT] ➔ [BƯỚC 3: INDEX AUDIT] ➔ [BƯỚC 4: PAYLOAD SANITY] ➔ [BƯỚC 5: DRY-RUN PROBE]
```

### Bước 1: Kiểm Tra Trạng Thái Kết Nối & Cluster
1. Đảm bảo biến môi trường `QDRANT_URL` và `QDRANT_API_KEY` đã được khai báo trong `.env`.
2. Chạy lệnh kiểm tra kết nối cơ bản:
   ```powershell
   .venv\Scripts\python scripts\verify_qdrant.py
   ```
3. **Tiêu chuẩn đạt:**
   - Status: `green`.
   - Timeout: luôn cài đặt `timeout=60.0` trong `AsyncQdrantClient` để chống đứt kết nối quốc tế.

### Bước 2: Kiểm Định Cấu Hình Named Vectors Kép (Dual Vector Audit)
Kiểm tra thông số cấu hình collection `In-Course_Agentic_RAG_Copilot`:
* **Dense Vector:**
  - Tên vector: `"dense"`
  - Kích thước: đúng **1024 chiều** (`intfloat/multilingual-e5-large`)
  - Distance Metric: `Cosine`
  - Cấu hình HNSW: `m=16`, `ef_construct=128`
* **Sparse Vector:**
  - Tên vector: `"sparse"`
  - Loại index: `SparseIndexParams(on_disk=False)`
  - Distance Metric: `DotProduct` (chuẩn BM25)

### Bước 3: Rà Soát 6 Payload Indexes Bắt Buộc (In-HNSW Indexes)
Xác nhận sự tồn tại của đủ 6 chỉ mục để đảm bảo truy vấn không bị rớt về chế độ quét cạn (Full-scan):
1. `course_id`: `models.PayloadSchemaType.KEYWORD`
2. `lesson_id`: `models.PayloadSchemaType.KEYWORD`
3. `lesson_seq`: `models.PayloadSchemaType.INTEGER` (phục vụ bộ lọc `<=`)
4. `content_type`: `models.PayloadSchemaType.KEYWORD` (`video_transcript` hoặc `code_ast`)
5. `start_sec`: `models.PayloadSchemaType.INTEGER`
6. `code_scope`: `models.PayloadSchemaType.KEYWORD`

*Nếu thiếu bất kỳ index nào, chạy lệnh khởi tạo lại ngay:*
```powershell
.venv\Scripts\python scripts\init_qdrant.py
```

### Bước 4: Kiểm Tra Hợp Đồng Dữ Liệu & Tính Tất Định (Payload Sanity Check)
1. **Tính tất định (Idempotency):**
   - Chạy lại script nạp bài cũ. Số lượng points trên cluster **phải giữ nguyên** (nhờ cơ chế băm `UUIDv5` từ chuỗi `{course_id}_{lesson_id}_chunk_{start}_{end}`).
2. **Kiểm tra trường bắt buộc:**
   - Đối với `content_type="video_transcript"`: Mỗi point phải có `start_sec`, `end_sec`, `start_label`, `end_label`, `raw_text`, `video_title`.
   - Tuyệt đối không để trường `raw_text` rỗng hoặc null.

### Bước 5: Thử Nghiệm Truy Vấn Mẫu (Dry-run Hybrid Search Probe)
Chạy script kiểm thử truy vấn để đo đạc độ trễ và độ chính xác:
```powershell
.venv\Scripts\python scripts\test_search.py "Tại sao dùng lệnh cout trong C++ lại bị báo đỏ gạch chân?" --seq 2
```
* **Tiêu chuẩn kết quả:**
  - Lấy được Top 10 ứng viên ban đầu trong $< 400$ms.
  - Điểm Sigmoid Normalized Score $\ge 0.35$.
  - Trích xuất được thẻ `<timestamp sec="...">` chính xác để tua video.

---

## 3. Xử Lý Sự Cố Thường Gặp (Troubleshooting)

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| :--- | :--- | :--- |
| `ConnectTimeout` | Mạng quốc tế chập chờn hoặc chưa set timeout | Kiểm tra tham số `timeout=60.0` trong `QdrantClient(...)`. |
| `Points Count` tăng vọt gấp đôi khi chạy lại | Chưa dùng UUIDv5 hoặc key băm bị thay đổi | Kiểm tra hàm sinh ID trong `scripts/ingest_video.py`, đảm bảo dùng `uuid.uuid5(uuid.NAMESPACE_DNS, deterministic_key)`. |
| Truy vấn chậm $> 1.5$s | Thiếu Payload Index khiến Qdrant phải scan cạn | Chạy lại `python scripts/init_qdrant.py` để bổ sung index. |
| Điểm tương đồng Cosine thấp bất thường | Quên thêm prefix cho mô hình E5 | Thêm `passage: ` vào text lúc ingest và `query: ` lúc tìm kiếm. |
