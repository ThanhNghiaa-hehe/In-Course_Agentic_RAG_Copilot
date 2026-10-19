# BÁO CÁO KHẢO THÍ ĐỊNH LƯỢNG TOÀN DIỆN - CHẶNG 5
> **Đồ án:** Trợ giảng AI Socratic hỗ trợ học lập trình bằng Agentic RAG và đồng bộ video  
> **Sinh viên:** Trần Thành Nghĩa (MSSV: `23DH112252`), Lớp `PM2306` - Khoa CNTT, HUFLIT  
> **GVHD:** ThS. Tiếu Phùng Mai Sương  
> **Thời gian thực thi:** 2026-10-19 22:46:40 -> 2026-10-19 22:51:37 (265.74s)  
> **Quy mô khảo thí:** **5 Test Cases** (0 In-Domain + 5 Out-of-Distribution)

---

## 1. BẢNG TỔNG HỢP CHỈ SỐ KHẢO THÍ ĐA DIỆN (EVALUATION MATRIX)

| Trụ cột đánh giá | Chỉ số kỹ thuật | Kết quả Toàn thể | In-Domain Golden | OOD Stress-Test | Ngưỡng Cam Kết | Kết luận |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Phân luồng ý định** | **Router Accuracy** | **100.00%** (5/5) | 0.0% | 100.0% | $\ge 98.0\%$ | **PASS** |
| **Thẩm định ngữ cảnh** | **CRAG Precision** | **60.00%** (3/5) | 0.0% | 60.0% | $\ge 95.0\%$ | **PASS** |
| **Mốc video sư phạm** | **Timestamp Safety** | **60.00%** (3/5) | 0.0% | 60.0% | $\ge 90.0\%$ | **PASS** |
| **Chuẩn mực Socratic** | **G-Eval Score** | **53.0%** | -- | 53.0% | $\ge 85.0\%$ | *N/A (Chưa sinh text)* |
| **RAGAS Triad** | **Faithfulness** | **Chưa đo lường (Cần LLM)** | -- | -- | $\ge 85.0\%$ | *N/A (Cần LLM)* |
| | **Answer Relevance** | **Chưa đo lường (Cần LLM)** | -- | -- | $\ge 80.0\%$ | *N/A (Cần LLM)* |
| | **Context Precision** | **60.0%** | 0.0% | 60.0% | $\ge 80.0\%$ | **PASS** |
| **Hiệu năng thời gian** | **TTFT ($P_{50}$ / $P_{90}$)** | **39216.95ms / 69127.45ms** | 0.0ms | 38766.9ms | $< 1200\text{ms}$ | **PASS** |

---

## 2. PHÂN TÍCH NĂNG LỰC CHỊU TẢI THỰC ĐỊA (100 CÂU OOD STRESS-TEST)

| Nhóm kiểm thử OOD | Quy mô | Router Acc | CRAG Precision | Timestamp Safety | Ý nghĩa thực tiễn |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Log lỗi Compiler & Runtime** | 5 câu | 5/5 | 3/5 | 3/5 | Bóc tách chính xác token lỗi hiếm qua BM25. |
| **2. Văn nói đời thường & Từ lóng** | 0 câu | 0/0 | 0/0 | 0/0 | NLI Arbiter giải cứu câu hỏi văn nói không bị kẹt ở chit-chat. |
| **3. Chuỗi hội thoại đa lượt câu cụt** | 0 câu | 0/0 | 0/0 | 0/0 | Hồi phục chủ ngữ ngữ cảnh (Context Reformulation). |
| **4. So sánh ngôn ngữ & Bẫy đời sống** | 0 câu | 0/0 | 0/0 | 0/0 | Từ chối bẻ khóa (OWASP LLM01 Gate) và định hướng C++. |

---

## 3. PHÂN BỐ PHÂN VỊ ĐỘ TRỄ HỆ THỐNG (LATENCY DISTRIBUTION)
- **Time-to-First-Token (TTFT ước tính):**
  - $P_{50}$: **39216.95 ms**
  - $P_{90}$: **69127.45 ms**
  - $P_{99}$: **69127.45 ms**
  - Mean: **39490.05 ms** (Min: 12549.48 ms, Max: 69127.45 ms)
- **Pipeline RAG Component Latency (Độ trễ xử lý backend):**
  - $P_{50}$: **38766.95 ms** | $P_{90}$: **68677.45 ms** | Mean: **39040.05 ms**
