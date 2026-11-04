# BÁO CÁO KHẢO THÍ ĐỐI CHỨNG: LINEARSVC + NLI vs. SLM ONNX INT8

**Sinh viên thực hiện:** Trần Thành Nghĩa (MSSV: 23DH112252) — HUFLIT
**Tập dữ liệu khảo thí:** Golden Dataset 200 câu hỏi thực tế (`tests/data/benchmark_golden_dataset.json`)

## 1. BẢNG SO SÁNH HIỆU NĂNG ĐỊNH LƯỢNG

| Tiêu Chí Đo Lường | Mô Hình A (LinearSVC + NLI) | Mô Hình B (SLM ONNX INT8) | Chênh Lệch & Kết Luận |
| :--- | :---: | :---: | :---: |
| **Độ Chính Xác (Accuracy)** | **89.00%** | **96.00%** | Tăng +7.00% |
| **Chỉ số Macro F1-Score** | **84.43%** | **95.34%** | Tăng +10.90% |
| **F1 `course_query`** | 92.47% | 97.12% | +4.66% |
| **F1 `out_of_scope`** | 73.33% | 88.89% | +15.56% |
| **F1 `chit_chat`** | 87.50% | 100.00% | +12.50% |
| **Độ trễ P50 (Median)** | 1.72 ms | **0.06 ms** | Nhanh hơn gấp 27.0x |
| **Độ trễ P99 (Worst-case)** | 508.15 ms | **0.17 ms** | Triệt tiêu độ trễ bimodal |

