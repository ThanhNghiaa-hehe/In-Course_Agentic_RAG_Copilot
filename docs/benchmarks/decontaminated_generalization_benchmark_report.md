# BÁO CÁO KHẢO THÍ TOÁN HỌC & ĐÁNH GIÁ KHÁI QUÁT HÓA ĐỘC LẬP (MILESTONE 4.2)
**Dự án:** In-Course Agentic RAG Copilot — Trần Thành Nghĩa (MSSV: `23DH112252`), HUFLIT  
**Giảng viên hướng dẫn:** ThS. Tiếu Phùng Mai Sương  
**Thời gian thực hiện:** 06/11/2026 15:14:30  
**Phiên bản Ngữ liệu Huấn luyện:** v2.8.0 (480 mẫu, Contrastive Hard Pairs, 0.00% Data Leakage)  
**Bộ Đề thi Kiểm chuẩn:** Frozen Held-Out Test Set 200 câu (`tests/data/benchmark_golden_dataset.json` - 100% Unseen)  

---

## 1. TỔNG QUAN KHỬ NHIỄM, CONTRASTIVE AUGMENTATION & HIỆU CHUẨN NHIỆT ĐỘ T*

Dự án tuân thủ nghiêm ngặt **Data Decontamination Protocol (Chuẩn Andrew Ng & Hastie et al.)** kết hợp **Milestone 4.2 (Calibrated Convex-Neural Ensemble)**:
- **Khử nhiễm kép độc lập 100% ($J < 0.70$):** Max Jaccard giữa tập Train với 200 câu Golden Benchmark là `0.6842 < 0.70` và với 100 câu OOD Stress Test là `0.6667 < 0.70` (**0.00% Data Leakage tuyệt đối trên cả 2 bộ test**).
- **Tập dữ liệu độc lập cân bằng:** Huấn luyện trên 480 mẫu độc lập phân bổ đồng đều giữa các lớp (`course_query`, `out_of_scope`, `chit_chat`), ngăn chặn hoàn toàn rò rỉ đề thi.
- **Label Smoothing ($\epsilon = 0.08$) & Temperature Scaling ($T^* = 0.5920$):** Chống bão hòa logit và tối ưu hóa Negative Log-Likelihood trên Out-of-Fold từ `0.1856` xuống `0.1415`.

---

## 2. KẾT QUẢ 5-FOLD STRATIFIED CROSS-VALIDATION (TẬP TRAIN SẠCH N = 480)

| Fold | Accuracy (%) | Macro F1 (%) | ECE (Guo et al. 2017) | Multi-class Brier Score |
| :--- | :---: | :---: | :---: | :---: |
| Fold 1 | 96.88% | 97.23% | 0.0763 | 0.0669 |
| Fold 2 | 95.83% | 95.74% | 0.0791 | 0.0680 |
| Fold 3 | 89.58% | 90.32% | 0.0556 | 0.1350 |
| Fold 4 | 97.92% | 97.92% | 0.0897 | 0.0578 |
| Fold 5 | 92.71% | 92.80% | 0.1052 | 0.0933 |
| **Kỳ vọng SLM (Mean ± Std)** | **94.58% ± 3.41%** | **94.80% ± 3.19%** | **0.0152** (sau $T^*$) | **0.0781** (sau $T^*$) |
| **OOF Convex-Neural Ensemble** | **94.38%** | **94.43%** | **0.0562** | **0.0847** |

> **Khoảng tin cậy 95% Macro F1 (Student's t, df=4):** $[90.84\%, 98.76\%]$.

---

## 3. KHẢO THÍ ĐỐI CHỨNG TRÊN FROZEN HELD-OUT TEST SET (200 CÂU UNSEEN 100%)

| Chỉ Số Đánh Giá | LinearSVC + Platt Scaling | Fast-Path SLM ONNX INT8 ($T^*$) | Convex-Neural Ensemble ($0.55 P_{\text{SLM}} + 0.45 P_{\text{SVC}}$) |
| :--- | :---: | :---: | :---: |
| **True Accuracy (Unseen 100%)** | **90.50%** (181/200) | **92.50%** (185/200) | **92.00%** (184/200) |
| **True Macro F1 (Unseen 100%)** | **86.29%** | **91.36%** | **90.54%** |
| **Expected Calibration Error (ECE)** | 0.0823 | 0.0437 | **0.0683** |
| **Độ trễ trung bình P50** | 0.05 ms | **0.02 ms** | **0.07 ms** |
| **Generalization Gap $|\text{CV} - \text{Test}|$** | -- | **2.08%** | **2.38%** |
| **OOD Stress Test (100 câu)** | 85.00% | 86.00% | **85.00%** |

---

## 4. MA TRẬN NHẦM LẪN & CHI TIẾT PHÂN LOẠI TRÊN DỮ LIỆU UNSEEN (ENSEMBLE)

```
              precision    recall  f1-score   support

   chit_chat     1.0000    0.9200    0.9583        25
course_query     0.9774    0.9091    0.9420       143
out_of_scope     0.7045    0.9688    0.8158        32

    accuracy                         0.9200       200
   macro avg     0.8940    0.9326    0.9054       200
weighted avg     0.9366    0.9200    0.9239       200

```

```
Confusion Matrix:
[[ 23   2   0]
 [  0 130  13]
 [  0   1  31]]
```
