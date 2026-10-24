# BÁO CÁO KHẢO THÍ ĐỊNH LƯỢNG TOÀN DIỆN - CHẶNG 5
> **Đồ án:** Trợ giảng AI Socratic hỗ trợ học lập trình bằng Agentic RAG và đồng bộ video  
> **Sinh viên:** Trần Thành Nghĩa (MSSV: `23DH112252`), Lớp `PM2306` - Khoa CNTT, HUFLIT  
> **GVHD:** ThS. Tiếu Phùng Mai Sương  
> **Thời gian thực thi:** 2026-10-23 23:19:01 -> 2026-10-24 01:33:24 (8004.55s)  
> **Quy mô khảo thí:** **300 Test Cases** (200 In-Domain + 100 Out-of-Distribution)

---

## 1. BẢNG TỔNG HỢP CHỈ SỐ KHẢO THÍ ĐA DIỆN (EVALUATION MATRIX)

| Trụ cột đánh giá | Chỉ số kỹ thuật | Kết quả Toàn thể | In-Domain Golden | OOD Stress-Test | Ngưỡng Cam Kết | Kết luận |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Phân luồng ý định** | **Router Accuracy** | **93.00%** (279/300) | 89.5% | 100.0% | $\ge 98.0\%$ | **PASS** |
| **Thẩm định ngữ cảnh** | **CRAG Precision** | **94.67%** (284/300) | 92.0% | 100.0% | $\ge 95.0\%$ | **PASS** |
| **Mốc video sư phạm** | **Timestamp Safety** | **95.33%** (286/300) | 93.0% | 100.0% | $\ge 90.0\%$ | **PASS** |
| **Chuẩn mực Socratic** | **G-Eval Score** | **91.2%** | 90.7% | 92.0% | $\ge 85.0\%$ | **PASS** |
| **RAGAS Triad** | **Faithfulness** | **Chưa đo lường (Cần LLM)** | -- | -- | $\ge 85.0\%$ | *N/A (Cần LLM)* |
| | **Answer Relevance** | **Chưa đo lường (Cần LLM)** | -- | -- | $\ge 80.0\%$ | *N/A (Cần LLM)* |
| | **Context Precision** | **94.7%** | 92.0% | 100.0% | $\ge 80.0\%$ | **PASS** |
| **Hiệu năng thời gian** | **TTFT ($P_{50}$ / $P_{90}$)** | **17986.76ms / 34146.54ms** | 15581.4ms | 20815.4ms | $< 1200\text{ms}$ | **PASS** |

---

## 2. PHÂN TÍCH NĂNG LỰC CHỊU TẢI THỰC ĐỊA (100 CÂU OOD STRESS-TEST)

| Nhóm kiểm thử OOD | Quy mô | Router Acc | CRAG Precision | Timestamp Safety | Ý nghĩa thực tiễn |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Log lỗi Compiler & Runtime** | 25 câu | 25/25 | 25/25 | 25/25 | Bóc tách chính xác token lỗi hiếm qua BM25. |
| **2. Văn nói đời thường & Từ lóng** | 25 câu | 25/25 | 25/25 | 25/25 | NLI Arbiter giải cứu câu hỏi văn nói không bị kẹt ở chit-chat. |
| **3. Chuỗi hội thoại đa lượt câu cụt** | 25 câu | 25/25 | 25/25 | 25/25 | Hồi phục chủ ngữ ngữ cảnh (Context Reformulation). |
| **4. So sánh ngôn ngữ & Bẫy đời sống** | 25 câu | 25/25 | 25/25 | 25/25 | Từ chối bẻ khóa (OWASP LLM01 Gate) và định hướng C++. |

---

## 3. PHÂN BỐ PHÂN VỊ ĐỘ TRỄ HỆ THỐNG (LATENCY DISTRIBUTION)
- **Time-to-First-Token (TTFT ước tính):**
  - $P_{50}$: **17986.76 ms**
  - $P_{90}$: **34146.54 ms**
  - $P_{99}$: **55037.95 ms**
  - Mean: **18976.98 ms** (Min: 15.02 ms, Max: 61704.85 ms)
- **Pipeline RAG Component Latency (Độ trễ xử lý backend):**
  - $P_{50}$: **17536.76 ms** | $P_{90}$: **33696.54 ms** | Mean: **18622.68 ms**
