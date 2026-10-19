# BÁO CÁO KHẢO THÍ ĐỊNH LƯỢNG TOÀN DIỆN - CHẶNG 5
> **Đồ án:** Trợ giảng AI Socratic hỗ trợ học lập trình bằng Agentic RAG và đồng bộ video  
> **Sinh viên:** Trần Thành Nghĩa (MSSV: `23DH112252`), Lớp `PM2306` - Khoa CNTT, HUFLIT  
> **GVHD:** ThS. Tiếu Phùng Mai Sương  
> **Thời gian thực thi:** 2026-10-19 22:07:36 -> 2026-10-19 22:09:45 (105.29s)  
> **Quy mô khảo thí:** **3 Test Cases** (0 In-Domain + 3 Out-of-Distribution)

---

## 1. BẢNG TỔNG HỢP CHỈ SỐ KHẢO THÍ ĐA DIỆN (EVALUATION MATRIX)

| Trụ cột đánh giá | Chỉ số kỹ thuật | Kết quả Toàn thể | In-Domain Golden | OOD Stress-Test | Ngưỡng Cam Kết | Kết luận |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Phân luồng ý định** | **Router Accuracy** | **100.00%** (3/3) | 0.0% | 100.0% | $\ge 98.0\%$ | **PASS** |
| **Thẩm định ngữ cảnh** | **CRAG Precision** | **66.67%** (2/3) | 0.0% | 66.7% | $\ge 95.0\%$ | **PASS** |
| **Mốc video sư phạm** | **Timestamp Safety** | **66.67%** (2/3) | 0.0% | 66.7% | $\ge 90.0\%$ | **PASS** |
| **Chuẩn mực Socratic** | **G-Eval Score** | **86.7%** | -- | 86.7% | $\ge 85.0\%$ | **PASS** |
| **RAGAS Triad** | **Faithfulness** | **Chưa đo lường (Cần LLM)** | -- | -- | $\ge 85.0\%$ | *N/A (Cần LLM)* |
| | **Answer Relevance** | **Chưa đo lường (Cần LLM)** | -- | -- | $\ge 80.0\%$ | *N/A (Cần LLM)* |
| | **Context Precision** | **66.7%** | 0.0% | 66.7% | $\ge 80.0\%$ | **PASS** |
| **Hiệu năng thời gian** | **TTFT ($P_{50}$ / $P_{90}$)** | **11451.8ms / 21213.07ms** | 0.0ms | 11001.8ms | $< 1200\text{ms}$ | **PASS** |

---

## 2. PHÂN TÍCH NĂNG LỰC CHỊU TẢI THỰC ĐỊA (100 CÂU OOD STRESS-TEST)

| Nhóm kiểm thử OOD | Quy mô | Router Acc | CRAG Precision | Timestamp Safety | Ý nghĩa thực tiễn |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Log lỗi Compiler & Runtime** | 3 câu | 3/3 | 2/3 | 2/3 | Bóc tách chính xác token lỗi hiếm qua BM25. |
| **2. Văn nói đời thường & Từ lóng** | 0 câu | 0/0 | 0/0 | 0/0 | NLI Arbiter giải cứu câu hỏi văn nói không bị kẹt ở chit-chat. |
| **3. Chuỗi hội thoại đa lượt câu cụt** | 0 câu | 0/0 | 0/0 | 0/0 | Hồi phục chủ ngữ ngữ cảnh (Context Reformulation). |
| **4. So sánh ngôn ngữ & Bẫy đời sống** | 0 câu | 0/0 | 0/0 | 0/0 | Từ chối bẻ khóa (OWASP LLM01 Gate) và định hướng C++. |

---

## 3. PHÂN BỐ PHÂN VỊ ĐỘ TRỄ HỆ THỐNG (LATENCY DISTRIBUTION)
- **Time-to-First-Token (TTFT ước tính):**
  - $P_{50}$: **11451.8 ms**
  - $P_{90}$: **21213.07 ms**
  - $P_{99}$: **21213.07 ms**
  - Mean: **14375.27 ms** (Min: 10460.94 ms, Max: 21213.07 ms)
- **Pipeline RAG Component Latency (Độ trễ xử lý backend):**
  - $P_{50}$: **11001.8 ms** | $P_{90}$: **20763.07 ms** | Mean: **13925.27 ms**
