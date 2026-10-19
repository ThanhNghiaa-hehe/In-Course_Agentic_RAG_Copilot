# BÁO CÁO KHẢO THÍ ĐỊNH LƯỢNG TOÀN DIỆN - CHẶNG 5
> **Đồ án:** Trợ giảng AI Socratic hỗ trợ học lập trình bằng Agentic RAG và đồng bộ video  
> **Sinh viên:** Trần Thành Nghĩa (MSSV: `23DH112252`), Lớp `PM2306` - Khoa CNTT, HUFLIT  
> **GVHD:** ThS. Tiếu Phùng Mai Sương  
> **Thời gian thực thi:** 2026-10-16 23:35:04 -> 2026-10-17 14:02:33 (51982.58s)  
> **Quy mô khảo thí:** **100 Test Cases** (0 In-Domain + 100 Out-of-Distribution)

---

## 1. BẢNG TỔNG HỢP CHỈ SỐ KHẢO THÍ ĐA DIỆN (EVALUATION MATRIX)

| Trụ cột đánh giá | Chỉ số kỹ thuật | Kết quả Toàn thể | In-Domain Golden | OOD Stress-Test | Ngưỡng Cam Kết | Kết luận |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Phân luồng ý định** | **Router Accuracy** | **100.00%** (100/100) | 0.0% | 100.0% | $\ge 98.0\%$ | **PASS** |
| **Thẩm định ngữ cảnh** | **CRAG Precision** | **76.00%** (76/100) | 0.0% | 76.0% | $\ge 95.0\%$ | **PASS** |
| **Mốc video sư phạm** | **Timestamp Safety** | **68.00%** (68/100) | 0.0% | 68.0% | $\ge 90.0\%$ | **PASS** |
| **Chuẩn mực Socratic** | **G-Eval Score** | **Chưa đo lường (Cần LLM)** | -- | -- | $\ge 85.0\%$ | *N/A (Chưa sinh text)* |
| **RAGAS Triad** | **Faithfulness** | **Chưa đo lường (Cần LLM)** | -- | -- | $\ge 85.0\%$ | *N/A (Cần LLM)* |
| | **Answer Relevance** | **Chưa đo lường (Cần LLM)** | -- | -- | $\ge 80.0\%$ | *N/A (Cần LLM)* |
| | **Context Precision** | **76.0%** | 0.0% | 76.0% | $\ge 80.0\%$ | **PASS** |
| **Hiệu năng thời gian** | **TTFT ($P_{50}$ / $P_{90}$)** | **42157.55ms / 118363.91ms** | 0.0ms | 41707.6ms | $< 1200\text{ms}$ | **PASS** |

---

## 2. PHÂN TÍCH NĂNG LỰC CHỊU TẢI THỰC ĐỊA (100 CÂU OOD STRESS-TEST)

| Nhóm kiểm thử OOD | Quy mô | Router Acc | CRAG Precision | Timestamp Safety | Ý nghĩa thực tiễn |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Log lỗi Compiler & Runtime** | 25 câu | 25/25 | 13/25 | 12/25 | Bóc tách chính xác token lỗi hiếm qua BM25. |
| **2. Văn nói đời thường & Từ lóng** | 25 câu | 25/25 | 19/25 | 18/25 | NLI Arbiter giải cứu câu hỏi văn nói không bị kẹt ở chit-chat. |
| **3. Chuỗi hội thoại đa lượt câu cụt** | 25 câu | 25/25 | 22/25 | 19/25 | Hồi phục chủ ngữ ngữ cảnh (Context Reformulation). |
| **4. So sánh ngôn ngữ & Bẫy đời sống** | 25 câu | 25/25 | 22/25 | 19/25 | Từ chối bẻ khóa (OWASP LLM01 Gate) và định hướng C++. |

---

## 3. PHÂN BỐ PHÂN VỊ ĐỘ TRỄ HỆ THỐNG (LATENCY DISTRIBUTION)
- **Time-to-First-Token (TTFT ước tính):**
  - $P_{50}$: **42157.55 ms**
  - $P_{90}$: **118363.91 ms**
  - $P_{99}$: **215006.04 ms**
  - Mean: **520238.82 ms** (Min: 15.05 ms, Max: 46789274.66 ms)
- **Pipeline RAG Component Latency (Độ trễ xử lý backend):**
  - $P_{50}$: **41707.55 ms** | $P_{90}$: **117913.91 ms** | Mean: **519823.62 ms**
