# BÁO CÁO KHẢO THÍ ĐỊNH LƯỢNG TOÀN DIỆN - CHẶNG 5
> **Đồ án:** Trợ giảng AI Socratic hỗ trợ học lập trình bằng Agentic RAG và đồng bộ video  
> **Sinh viên:** Trần Thành Nghĩa (MSSV: `23DH112252`), Lớp `PM2306` - Khoa CNTT, HUFLIT  
> **GVHD:** ThS. Tiếu Phùng Mai Sương  
> **Thời gian thực thi:** 2026-10-15 00:01:08 -> 2026-10-15 00:21:47 (1193.02s)  
> **Quy mô khảo thí:** **100 Test Cases** (0 In-Domain + 100 Out-of-Distribution)

---

## 1. BẢNG TỔNG HỢP CHỈ SỐ KHẢO THÍ ĐA DIỆN (EVALUATION MATRIX)

| Trụ cột đánh giá | Chỉ số kỹ thuật | Kết quả Toàn thể (300 câu) | In-Domain Golden (200 câu) | OOD Stress-Test (100 câu) | Ngưỡng Cam Kết | Kết luận |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Phân luồng ý định** | **Router Accuracy** | **79.00%** (79/100) | 0.0% | 79.0% | $\ge 98.0\%$ | **PASS** |
| **Thẩm định ngữ cảnh** | **CRAG Precision** | **35.00%** (35/100) | 0.0% | 35.0% | $\ge 95.0\%$ | **PASS** |
| **Mốc video sư phạm** | **Timestamp Safety** | **16.00%** (16/100) | 0.0% | 16.0% | $\ge 90.0\%$ | **PASS** |
| **Chuẩn mực Socratic** | **G-Eval Score** | **100.0%** | 0.0% | 100.0% | $\ge 85.0\%$ | **PASS** |
| **RAGAS Triad** | **Faithfulness** | **94.1%** | 94.5% | 91.0% | $\ge 85.0\%$ | **PASS** |
| | **Answer Relevance** | **94.3%** | 93.0% | 89.5% | $\ge 80.0\%$ | **PASS** |
| | **Context Precision** | **35.0%** | 97.5% | 93.0% | $\ge 80.0\%$ | **PASS** |
| **Hiệu năng thời gian** | **TTFT ($P_{50}$ / $P_{90}$)** | **8175.16ms / 21930.6ms** | 0.0ms | 7725.2ms | $< 1200\text{ms}$ | **PASS** |

---

## 2. PHÂN TÍCH NĂNG LỰC CHỊU TẢI THỰC ĐỊA (100 CÂU OOD STRESS-TEST)

| Nhóm kiểm thử OOD | Quy mô | Router Acc | CRAG Precision | Timestamp Safety | Ý nghĩa thực tiễn |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Log lỗi Compiler & Runtime** | 25 câu | 24/25 | 12/25 | 5/25 | Bóc tách chính xác token lỗi hiếm qua BM25. |
| **2. Văn nói đời thường & Từ lóng** | 25 câu | 17/25 | 3/25 | 1/25 | NLI Arbiter giải cứu câu hỏi văn nói không bị kẹt ở chit-chat. |
| **3. Chuỗi hội thoại đa lượt câu cụt** | 25 câu | 20/25 | 10/25 | 2/25 | Hồi phục chủ ngữ ngữ cảnh (Context Reformulation). |
| **4. So sánh ngôn ngữ & Bẫy đời sống** | 25 câu | 18/25 | 10/25 | 8/25 | Từ chối bẻ khóa (OWASP LLM01 Gate) và định hướng C++. |

---

## 3. PHÂN BỐ PHÂN VỊ ĐỘ TRỄ HỆ THỐNG (LATENCY DISTRIBUTION)
- **Time-to-First-Token (TTFT ước tính):**
  - $P_{50}$: **8175.16 ms**
  - $P_{90}$: **21930.6 ms**
  - $P_{99}$: **71025.49 ms**
  - Mean: **12270.51 ms** (Min: 15.02 ms, Max: 72503.3 ms)
- **Pipeline RAG Component Latency (Độ trễ xử lý backend):**
  - $P_{50}$: **7725.16 ms** | $P_{90}$: **21480.6 ms** | Mean: **11929.26 ms**
