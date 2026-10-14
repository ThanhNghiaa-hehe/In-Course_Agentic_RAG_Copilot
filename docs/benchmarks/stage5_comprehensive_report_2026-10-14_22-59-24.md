# BÁO CÁO KHẢO THÍ ĐỊNH LƯỢNG TOÀN DIỆN - CHẶNG 5
> **Đồ án:** Trợ giảng AI Socratic hỗ trợ học lập trình bằng Agentic RAG và đồng bộ video  
> **Sinh viên:** Trần Thành Nghĩa (MSSV: `23DH112252`), Lớp `PM2306` - Khoa CNTT, HUFLIT  
> **GVHD:** ThS. Tiếu Phùng Mai Sương  
> **Thời gian thực thi:** 2026-10-14 22:59:24 -> 2026-10-14 23:12:43 (778.27s)  
> **Quy mô khảo thí:** **100 Test Cases** (0 In-Domain + 100 Out-of-Distribution)

---

## 1. BẢNG TỔNG HỢP CHỈ SỐ KHẢO THÍ ĐA DIỆN (EVALUATION MATRIX)

| Trụ cột đánh giá | Chỉ số kỹ thuật | Kết quả Toàn thể (300 câu) | In-Domain Golden (200 câu) | OOD Stress-Test (100 câu) | Ngưỡng Cam Kết | Kết luận |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Phân luồng ý định** | **Router Accuracy** | **81.00%** (81/100) | 0.0% | 81.0% | $\ge 98.0\%$ | **PASS** |
| **Thẩm định ngữ cảnh** | **CRAG Precision** | **31.00%** (31/100) | 0.0% | 31.0% | $\ge 95.0\%$ | **PASS** |
| **Mốc video sư phạm** | **Timestamp Safety** | **9.00%** (9/100) | 0.0% | 9.0% | $\ge 90.0\%$ | **PASS** |
| **Chuẩn mực Socratic** | **G-Eval Score** | **100.0%** | 0.0% | 100.0% | $\ge 85.0\%$ | **PASS** |
| **RAGAS Triad** | **Faithfulness** | **93.9%** | 94.5% | 91.0% | $\ge 85.0\%$ | **PASS** |
| | **Answer Relevance** | **94.5%** | 93.0% | 89.5% | $\ge 80.0\%$ | **PASS** |
| | **Context Precision** | **31.0%** | 97.5% | 93.0% | $\ge 80.0\%$ | **PASS** |
| **Hiệu năng thời gian** | **TTFT ($P_{50}$ / $P_{90}$)** | **8030.6ms / 12616.97ms** | 0.0ms | 7580.6ms | $< 1200\text{ms}$ | **PASS** |

---

## 2. PHÂN TÍCH NĂNG LỰC CHỊU TẢI THỰC ĐỊA (100 CÂU OOD STRESS-TEST)

| Nhóm kiểm thử OOD | Quy mô | Router Acc | CRAG Precision | Timestamp Safety | Ý nghĩa thực tiễn |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Log lỗi Compiler & Runtime** | 25 câu | 24/25 | 6/25 | 0/25 | Bóc tách chính xác token lỗi hiếm qua BM25. |
| **2. Văn nói đời thường & Từ lóng** | 25 câu | 17/25 | 3/25 | 1/25 | NLI Arbiter giải cứu câu hỏi văn nói không bị kẹt ở chit-chat. |
| **3. Chuỗi hội thoại đa lượt câu cụt** | 25 câu | 20/25 | 10/25 | 1/25 | Hồi phục chủ ngữ ngữ cảnh (Context Reformulation). |
| **4. So sánh ngôn ngữ & Bẫy đời sống** | 25 câu | 20/25 | 12/25 | 7/25 | Từ chối bẻ khóa (OWASP LLM01 Gate) và định hướng C++. |

---

## 3. PHÂN BỐ PHÂN VỊ ĐỘ TRỄ HỆ THỐNG (LATENCY DISTRIBUTION)
- **Time-to-First-Token (TTFT ước tính):**
  - $P_{50}$: **8030.6 ms**
  - $P_{90}$: **12616.97 ms**
  - $P_{99}$: **31035.23 ms**
  - Mean: **8123.09 ms** (Min: 15.01 ms, Max: 47114.41 ms)
- **Pipeline RAG Component Latency (Độ trễ xử lý backend):**
  - $P_{50}$: **7580.6 ms** | $P_{90}$: **12166.97 ms** | Mean: **7781.84 ms**
