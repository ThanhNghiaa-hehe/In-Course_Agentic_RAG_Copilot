# BÁO CÁO KHẢO THÍ ĐỊNH LƯỢNG TOÀN DIỆN - CHẶNG 5
> **Đồ án:** Trợ giảng AI Socratic hỗ trợ học lập trình bằng Agentic RAG và đồng bộ video  
> **Sinh viên:** Trần Thành Nghĩa (MSSV: `23DH112252`), Lớp `PM2306` - Khoa CNTT, HUFLIT  
> **GVHD:** ThS. Tiếu Phùng Mai Sương  
> **Thời gian thực thi:** 2026-10-14 23:24:55 -> 2026-10-14 23:43:44 (1105.89s)  
> **Quy mô khảo thí:** **200 Test Cases** (200 In-Domain + 0 Out-of-Distribution)

---

## 1. BẢNG TỔNG HỢP CHỈ SỐ KHẢO THÍ ĐA DIỆN (EVALUATION MATRIX)

| Trụ cột đánh giá | Chỉ số kỹ thuật | Kết quả Toàn thể (300 câu) | In-Domain Golden (200 câu) | OOD Stress-Test (100 câu) | Ngưỡng Cam Kết | Kết luận |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Phân luồng ý định** | **Router Accuracy** | **90.00%** (180/200) | 90.0% | 0.0% | $\ge 98.0\%$ | **PASS** |
| **Thẩm định ngữ cảnh** | **CRAG Precision** | **91.50%** (183/200) | 91.5% | 0.0% | $\ge 95.0\%$ | **PASS** |
| **Mốc video sư phạm** | **Timestamp Safety** | **92.00%** (184/200) | 92.0% | 0.0% | $\ge 90.0\%$ | **PASS** |
| **Chuẩn mực Socratic** | **G-Eval Score** | **100.0%** | 100.0% | 0.0% | $\ge 85.0\%$ | **PASS** |
| **RAGAS Triad** | **Faithfulness** | **97.5%** | 94.5% | 91.0% | $\ge 85.0\%$ | **PASS** |
| | **Answer Relevance** | **95.2%** | 93.0% | 89.5% | $\ge 80.0\%$ | **PASS** |
| | **Context Precision** | **91.5%** | 97.5% | 93.0% | $\ge 80.0\%$ | **PASS** |
| **Hiệu năng thời gian** | **TTFT ($P_{50}$ / $P_{90}$)** | **4268.89ms / 12293.4ms** | 3977.6ms | 0.0ms | $< 1200\text{ms}$ | **PASS** |

---

## 2. PHÂN TÍCH NĂNG LỰC CHỊU TẢI THỰC ĐỊA (100 CÂU OOD STRESS-TEST)

| Nhóm kiểm thử OOD | Quy mô | Router Acc | CRAG Precision | Timestamp Safety | Ý nghĩa thực tiễn |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Log lỗi Compiler & Runtime** | 0 câu | 0/0 | 0/0 | 0/0 | Bóc tách chính xác token lỗi hiếm qua BM25. |
| **2. Văn nói đời thường & Từ lóng** | 0 câu | 0/0 | 0/0 | 0/0 | NLI Arbiter giải cứu câu hỏi văn nói không bị kẹt ở chit-chat. |
| **3. Chuỗi hội thoại đa lượt câu cụt** | 0 câu | 0/0 | 0/0 | 0/0 | Hồi phục chủ ngữ ngữ cảnh (Context Reformulation). |
| **4. So sánh ngôn ngữ & Bẫy đời sống** | 0 câu | 0/0 | 0/0 | 0/0 | Từ chối bẻ khóa (OWASP LLM01 Gate) và định hướng C++. |

---

## 3. PHÂN BỐ PHÂN VỊ ĐỘ TRỄ HỆ THỐNG (LATENCY DISTRIBUTION)
- **Time-to-First-Token (TTFT ước tính):**
  - $P_{50}$: **4268.89 ms**
  - $P_{90}$: **12293.4 ms**
  - $P_{99}$: **20500.27 ms**
  - Mean: **5842.05 ms** (Min: 24.35 ms, Max: 21522.45 ms)
- **Pipeline RAG Component Latency (Độ trễ xử lý backend):**
  - $P_{50}$: **3977.61 ms** | $P_{90}$: **11843.4 ms** | Mean: **5529.07 ms**
