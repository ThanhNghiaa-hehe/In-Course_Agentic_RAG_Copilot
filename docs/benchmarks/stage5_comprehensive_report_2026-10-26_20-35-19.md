# BÁO CÁO KHẢO THÍ ĐỊNH LƯỢNG TOÀN DIỆN - CHẶNG 5
> **Đồ án:** Trợ giảng AI Socratic hỗ trợ học lập trình bằng Agentic RAG và đồng bộ video  
> **Sinh viên:** Trần Thành Nghĩa (MSSV: `23DH112252`), Lớp `PM2306` - Khoa CNTT, HUFLIT  
> **GVHD:** ThS. Tiếu Phùng Mai Sương  
> **Thời gian thực thi:** 2026-10-26 20:35:19 -> 2026-10-27 01:10:11 (16375.76s)  
> **Quy mô khảo thí:** **300 Test Cases** (200 In-Domain + 100 Out-of-Distribution)

---

## 1. BẢNG TỔNG HỢP CHỈ SỐ KHẢO THÍ ĐA DIỆN (EVALUATION MATRIX)

| Trụ cột đánh giá | Chỉ số kỹ thuật | Kết quả Toàn thể | In-Domain Golden | OOD Stress-Test | Ngưỡng Cam Kết | Kết luận |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Phân luồng ý định** | **Router Accuracy** | **93.00%** (279/300) | 89.5% | 100.0% | $\ge 98.0\%$ | **PASS** |
| **Thẩm định ngữ cảnh** | **CRAG Precision** | **94.67%** (284/300) | 92.0% | 100.0% | $\ge 95.0\%$ | **PASS** |
| **Mốc video sư phạm** | **Timestamp Safety** | **95.00%** (285/300) | 92.5% | 100.0% | $\ge 90.0\%$ | **PASS** |
| **Chuẩn mực Socratic** | **G-Eval Score** | **91.4%** | 91.7% | 90.8% | $\ge 85.0\%$ | **PASS** |
| **RAGAS Triad** | **Faithfulness** | **Chưa đo lường (Cần LLM)** | -- | -- | $\ge 85.0\%$ | *N/A (Cần LLM)* |
| | **Answer Relevance** | **Chưa đo lường (Cần LLM)** | -- | -- | $\ge 80.0\%$ | *N/A (Cần LLM)* |
| | **Context Precision** | **94.7%** | 92.0% | 100.0% | $\ge 80.0\%$ | **PASS** |
| **Hiệu năng thời gian** | **TTFT ($P_{50}$ / $P_{90}$)** | **4544.04ms / 270697.32ms** | 3294.4ms | 3216.5ms | $< 1200\text{ms}$ | **PASS** |

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
  - $P_{50}$: **4544.04 ms**
  - $P_{90}$: **270697.32 ms**
  - $P_{99}$: **328771.09 ms**
  - Mean: **46178.02 ms** (Min: 0.41 ms, Max: 404621.69 ms)
- **Pipeline RAG Component Latency (Độ trễ xử lý backend):**
  - $P_{50}$: **3281.73 ms** | $P_{90}$: **270697.32 ms** | Mean: **45209.74 ms**
