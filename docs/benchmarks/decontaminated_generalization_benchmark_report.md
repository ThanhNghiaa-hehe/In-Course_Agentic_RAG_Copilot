# BÁO CÁO KHẢO THÍ TOÁN HỌC & ĐÁNH GIÁ KHÁI QUÁT HÓA ĐỘC LẬP (MILESTONE 4.2)
**Dự án:** In-Course Agentic RAG Copilot — Trần Thành Nghĩa (MSSV: `23DH112252`), HUFLIT  
**Giảng viên hướng dẫn:** ThS. Tiếu Phùng Mai Sương  
**Thời gian thực hiện:** 05/11/2026 21:19:46  
**Phiên bản Ngữ liệu Huấn luyện:** v2.7.0 (416 mẫu, Contrastive Hard Pairs, 0.00% Data Leakage)  
**Bộ Đề thi Kiểm chuẩn:** Frozen Held-Out Test Set 200 câu (`tests/data/benchmark_golden_dataset.json` - 100% Unseen)  

---

## 1. TỔNG QUAN KHỬ NHIỄM, CONTRASTIVE AUGMENTATION & HIỆU CHUẨN NHIỆT ĐỘ T*

Dự án tuân thủ nghiêm ngặt **Data Decontamination Protocol (Chuẩn Andrew Ng & Hastie et al.)** kết hợp **Milestone 4.2 (Calibrated Convex-Neural Ensemble)**:
- **Khử nhiễm 100% ($J < 0.70$):** Max Jaccard giữa tập Train và 200 câu Golden Benchmark là `0.6842 < 0.70` (**0.00% Data Leakage**).
- **48 Contrastive Hard Pairs:** Tăng cường ranh giới phân lớp giữa câu hỏi mô hình hóa C++ (`course_query`), câu nói phi lý vật lý/tình cảm chứa từ khóa C++ (`out_of_scope`), và câu hỏi kiến trúc hệ thống / sư phạm Socratic (`chit_chat`), với Max Jaccard trên OOD là `0.1905 < 0.70`.
- **Label Smoothing ($\epsilon = 0.08$) & Temperature Scaling ($T^* = 0.7520$):** Chống bão hòa logit và tối ưu hóa Negative Log-Likelihood trên Out-of-Fold từ `0.2616` xuống `0.2437`.

---

## 2. KẾT QUẢ 5-FOLD STRATIFIED CROSS-VALIDATION (TẬP TRAIN SẠCH N = 416)

| Fold | Accuracy (%) | Macro F1 (%) | ECE (Guo et al. 2017) | Multi-class Brier Score |
| :--- | :---: | :---: | :---: | :---: |
| Fold 1 | 88.10% | 88.51% | 0.0572 | 0.1639 |
| Fold 2 | 87.95% | 87.72% | 0.0658 | 0.1695 |
| Fold 3 | 91.57% | 92.40% | 0.0759 | 0.1181 |
| Fold 4 | 90.36% | 90.06% | 0.0925 | 0.1592 |
| Fold 5 | 96.39% | 96.00% | 0.0912 | 0.0547 |
| **Kỳ vọng SLM (Mean ± Std)** | **90.87% ± 3.44%** | **90.94% ± 3.35%** | **0.0241** (sau $T^*$) | **0.1326** (sau $T^*$) |
| **OOF Convex-Neural Ensemble** | **91.83%** | **91.94%** | **0.0665** | **0.1349** |

> **Khoảng tin cậy 95% Macro F1 (Student's t, df=4):** $[86.79\%, 95.09\%]$.

---

## 3. KHẢO THÍ ĐỐI CHỨNG TRÊN FROZEN HELD-OUT TEST SET (200 CÂU UNSEEN 100%)

| Chỉ Số Đánh Giá | LinearSVC + Platt Scaling | Fast-Path SLM ONNX INT8 ($T^*$) | Convex-Neural Ensemble ($0.55 P_{\text{SLM}} + 0.45 P_{\text{SVC}}$) |
| :--- | :---: | :---: | :---: |
| **True Accuracy (Unseen 100%)** | **92.50%** (185/200) | **92.50%** (185/200) | **92.00%** (184/200) |
| **True Macro F1 (Unseen 100%)** | **90.54%** | **91.17%** | **90.31%** |
| **Expected Calibration Error (ECE)** | 0.1218 | 0.0165 | **0.0579** |
| **Độ trễ trung bình P50** | 0.08 ms | **0.05 ms** | **0.13 ms** |
| **Generalization Gap $|\text{CV} - \text{Test}|$** | -- | **1.63%** | **0.17%** |
| **OOD Stress Test (100 câu)** | 96.00% | 96.00% | **96.00%** |

---

## 4. MA TRẬN NHẦM LẪN & CHI TIẾT PHÂN LOẠI TRÊN DỮ LIỆU UNSEEN (ENSEMBLE)

```
              precision    recall  f1-score   support

   chit_chat     1.0000    0.8800    0.9362        25
course_query     0.9774    0.9091    0.9420       143
out_of_scope     0.7111    1.0000    0.8312        32

    accuracy                         0.9200       200
   macro avg     0.8962    0.9297    0.9031       200
weighted avg     0.9376    0.9200    0.9236       200

```

```
Confusion Matrix:
[[ 22   3   0]
 [  0 130  13]
 [  0   0  32]]
```
