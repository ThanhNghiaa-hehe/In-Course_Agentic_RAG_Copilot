---
name: rag-diagnostics-eval
description: Framework-agnostic RAG failure diagnostics clinic and automated quantitative evaluation runbook. Classifies incidents into 12 production failure patterns (P01-P12), drives RAGAS Triad metrics, and enforces CI/CD Quality Gates.
---

# RAG Diagnostics & Quantitative Evaluation Runbook

Kỹ năng chẩn đoán sự cố RAG đa phương thức và quy chuẩn đánh giá tự động CI/CD cho đồ án **In-Course Agentic RAG Copilot**.

---

## 1. Phân Loại 12 Lỗi RAG Thực Chiến (Failure Patterns P01–P12)

Khi hệ thống gặp lỗi truy xuất, chất lượng câu trả lời bị suy giảm hoặc Quality Gate bị FAIL, kỹ sư đối chiếu và gắn mã sự cố theo bảng chuẩn hóa:

| Mã | Tên Mẫu Lỗi (Pattern Name) | Triệu Chứng Thực Tế | Giải Pháp Cấu Trúc Khắc Phục (Structural Fix) |
| :--- | :--- | :--- | :--- |
| **P01** | **Retrieval Hallucination / Grounding Drift** | Câu trả lời mâu thuẫn trực tiếp với tài liệu Context truy xuất được. | Siết chặt Socratic Prompt, giảm LLM temperature xuống 0.2, tăng trọng số phạt ảo giác trong RAGAS. |
| **P02** | **Chunk Boundary & Semantic Split Bug** | Đoạn code C++ hoặc câu thoại video bị cắt ngang xương khiến LLM hiểu sai ngữ cảnh. | Chuyển sang Tree-sitter AST Chunking (cắt theo ranh giới hàm/class) và Time-aware sliding window (gối đầu 15s). |
| **P03** | **Embedding Distance Mismatch** | Khoảng cách Cosine của Dense Vector không phản ánh đúng mức độ liên quan. | Bổ sung mô hình Cross-Encoder Re-ranking (`jinaai/jina-reranker-v2-base-multilingual`) và chuẩn hóa Sigmoid. |
| **P04** | **Index Skew & Staleness** | Dữ liệu trên Qdrant bị trùng lặp hoặc không đồng bộ với bài giảng mới. | Áp dụng cơ chế sinh ID bất biến **UUIDv5** (`uuid.uuid5`) và dọn dẹp chỉ mục trước khi nạp lại. |
| **P05** | **Router Misalignment** | Intent Router gửi nhầm câu hỏi C++ vào Fast-Path hoặc gửi câu chào hỏi vào RAG. | Tinh chỉnh Regex Unicode NFC trong `app/agent/router.py`, bổ sung test case biên trong `tests/test_router.py`. |
| **P06** | **Long-chain Context Drift (Lost-in-the-Middle)** | LLM bỏ quên mốc video hoặc tài liệu quan trọng nằm ở giữa context dài. | Áp dụng thuật toán **U-Shaped Context Assembly** `[Top 1, Top 3, Top 2]` (Stanford/TACL 2024). |
| **P07** | **Ungrounded Tool Call** | LLM gọi hàm tìm kiếm bài giảng với tham số tự bịa (bịa `lesson_seq` hoặc `course_id`). | Đóng băng schema Pydantic v2 chặt chẽ, bắt buộc kiểm tra kiểu dữ liệu trước khi truyền vào service. |
| **P08** | **Empty Context Starvation** | Sinh viên hỏi bài chưa học, RAG trả về 0 chunks dẫn đến LLM tự bịa mốc video. | Kích hoạt **Negative Branch Guardrail**: Tuyệt đối CẤM sinh thẻ `<timestamp>`, thông báo bài học chưa đề cập. |
| **P09** | **Temporal Anchor Misalignment** | Mốc video `<timestamp sec="...">` bị lệch quá 15s so với thao tác gõ code trên màn hình. | Tinh chỉnh lại ngưỡng Silero VAD (`threshold=0.35`, `speech_pad_ms=400`) và kích hoạt Phase 2 Metadata Binding. |
| **P10** | **Pedagogical Ethics Violation** | Trợ giảng AI tự ý viết trọn vẹn mã nguồn giải bài tập hộ sinh viên. | Khóa chặt System Prompt: Bắt buộc từ chối giải hộ, chỉ cung cấp mã giả (pseudocode) và 1–2 câu hỏi gợi mở. |
| **P11** | **Quantization Degeneration** | Model LLM cục bộ bị lặp từ, sinh token vô nghĩa do lượng tử hóa quá sâu. | Sử dụng phiên bản lượng tử hóa chuẩn `Q4_K_M` (1.88 GB) hoặc `Q5_K_M` để bảo toàn năng lực lý luận. |
| **P12** | **Tag & Syntax Corruption** | Thẻ `<timestamp>` bị gõ sai cú pháp (thiếu thuộc tính `sec` hoặc sai định dạng `mm:ss`). | Kiểm soát đầu ra bằng Regex Validator trước khi phát luồng qua kênh Dual-Channel SSE. |

---

## 2. Quy Chuẩn Khảo Thí Tự Động Định Lượng (RAGAS Triad CI)

### Các Chỉ Số Đo Lường Bắt Buộc
1. **Faithfulness (Độ trung thực - Ngăn chặn Ảo giác):**
   $$\text{Faithfulness} = \frac{|\text{Các luận điểm được chứng minh bởi Context}|}{|\text{Tổng số luận điểm do LLM sinh ra}|} \ge 0.85$$
2. **Answer Relevance (Độ chuẩn đề):**
   $$\text{Relevance} \ge 0.80$$
3. **Context Precision (Độ chính xác truy xuất):**
   $$\text{Precision} \ge 0.80$$
4. **Video Timestamp Accuracy (Chỉ số mốc thời gian đặc thù):**
   $$|\Delta t| = |t_{\text{pred}} - t_{\text{ground\_truth}}| \le 15\text{s} \quad (\text{Tỷ lệ trúng} \ge 90\%)$$

### Quy Tắc Cổng Kiểm Soát Chất Lượng (Quality Gate Rules)
* **VERDICT: PASS (SHIP):** Khi cả 4 chỉ số trên đều vượt ngưỡng. Cho phép đóng gói bản phát hành hoặc triển khai phục vụ sinh viên.
* **VERDICT: FAIL (BLOCK):** Khi có bất kỳ chỉ số nào dưới ngưỡng. Ngắt quy trình release, gắn mã lỗi $P_{xx}$ và kích hoạt vòng phản hồi sửa chữa.
