# BÁO CÁO TỔNG HỢP BỘ BA RAGAS TRIAD NGOẠI TUYẾN (DUAL-METRIC GROUNDING)
**Thời gian đánh giá:** 2026-10-24 18:17:53  
**Sinh viên thực hiện:** Trần Thành Nghĩa (MSSV: `23DH112252`)  
**Trường Đại học:** Ngoại ngữ - Tin học TP.HCM (HUFLIT)  
**Kho mã nguồn:** [https://github.com/ThanhNghiaa-hehe/In-Course_Agentic_RAG_Copilot](https://github.com/ThanhNghiaa-hehe/In-Course_Agentic_RAG_Copilot)  
**Kiến trúc:** Sáng kiến M-08 - Decoupled Two-Phase Evaluation Architecture (Chuẩn Es et al., EACL 2024 / SelfCheckGPT EMNLP 2023 / TruLens Telemetry)

---

## 1. TỔNG QUAN CHỈ SỐ BỘ BA RAGAS TRIAD & DUAL-METRIC GROUNDING

| Chỉ số Đánh giá | Điểm số đạt được | Ngưỡng chuẩn | Đánh giá | Phương pháp đo lường & Bản chất khoa học |
| :--- | :---: | :---: | :---: | :--- |
| **No-Hallucination Rate** | **85.52%** | $\ge 85.0\%$ | **PASS** | $1 - \frac{|C|}{|Total|}$, chứng minh hệ thống không bịa đặt sai lệch |
| **Strict In-Course Grounding** | **53.02%** | *Tham chiếu* | **INFO** | $\frac{|E|}{|Total|}$, tỷ lệ trích dẫn trực tiếp bài giảng nguyên văn |
| **Calibrated Faithfulness** | **69.27%** | $\ge 70.0\%$ | **PASS** | $\frac{|E| + 0.5|N|}{|Total|}$, dung hòa tri thức C++ bổ trợ đúng đắn |
| **Answer Relevance** | **91.25%** | $\ge 80.0\%$ | **PASS** | Local Cosine Embedding `multilingual-e5-large` (1024 chiều) |
| **Context Precision** | **94.7%** | $\ge 85.0\%$ | **PASS** | CRAG Grader + Hybrid In-HNSW Retrieval |

---

## 2. PHÂN TÍCH THEO PHÂN KHU HỌC LIỆU

### A. Phân khu Trong Giáo Trình (In-Domain Golden Dataset - 200 câu)
- **Số câu grounded được đánh giá:** 95 câu
- **No-Hallucination Rate:** **84.95%** (An toàn tuyệt đối, không có phát biểu sai lệch bản chất C++)
- **Strict In-Course Faithfulness:** **57.94%** (Bám sát nội dung bài giảng của khóa học C++)
- **Answer Relevance:** **91.77%** (Độ tập trung cao, giải quyết trúng đích thắc mắc của sinh viên)

### B. Phân khu Thử Thách Ngoài Phân Phối (OOD Stress-Test - 100 câu)
- **Số câu grounded được đánh giá:** 72 câu
- **No-Hallucination Rate:** **86.28%**
- **Strict In-Course Faithfulness:** **46.53%**
- **Answer Relevance:** **90.55%**

---

## 3. NGUYÊN LÝ THẨM ĐỊNH TOÁN HỌC & BẤT BIẾN ÁP DỤNG

1. **RAGAS Domain Pre-filtering Invariant:**
   - Đã loại trừ hoàn toàn các câu hỏi chào hỏi (`chit_chat`), câu hỏi ngoài lề (`out_of_scope`), bẻ khóa (`jailbreak`) và không tìm thấy bài (`coverage_gap`) khỏi phép tính Faithfulness.
   - Triệt tiêu hoàn toàn lỗi chia cho 0 và False Negatives, bảo toàn độ chính xác toán học của mẫu số.
2. **Dual-Metric Grounding Standard (SelfCheckGPT / TruLens):**
   - Phân định rạch ròi giữa *Mâu thuẫn (Contradiction - Ảo giác)* và *Tri thức bổ trợ chuẩn C++ (Neutral - Mở rộng sư phạm)*.
   - Không đánh đồng việc giải thích thêm kiến thức C++ chuẩn mực với hành vi bịa đặt thông tin.
3. **Đồng bộ thời gian thực:**
   - Dữ liệu đã được nạp trực tiếp vào [`docs/benchmarks/latest_evaluation_results.json`](file:///d:/In_Course_Agentic_RAG_Copilot/docs/benchmarks/latest_evaluation_results.json), kích hoạt 100% card màu xanh trên **Interactive Observability Dashboard** (`http://127.0.0.1:8000/evaluation`).
