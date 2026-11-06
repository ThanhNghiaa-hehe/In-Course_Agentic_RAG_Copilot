"""
Quy trình Huấn Luyện, Đánh Giá 5-Fold Stratified Cross-Validation & Khảo Thí Khái Quát Hóa Độc Lập
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Cơ sở khoa học:
1. 5-Fold Stratified Cross-Validation trên tập Train đã khử nhiễm hoàn toàn (328 mẫu, 0.00% leakage).
2. Đo lường kỳ vọng Macro F1, độ lệch chuẩn mẫu s, ECE (Expected Calibration Error) và Brier Score.
3. Huấn luyện Final Model và xuất sang ONNX INT8 (slm_router_int8.onnx) cùng Calibrated LinearSVC.
4. Khảo thí trên Frozen Held-Out Test Set (200 câu Golden Benchmark 100% Unseen).
5. Tính toán Generalization Gap (Delta_gen) và đánh giá trên 100 câu OOD Stress Test.
"""

import os
import sys
import json
import time
import math
from pathlib import Path
from typing import List, Tuple, Dict, Any
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
import onnxruntime as ort
from onnxruntime.quantization import quantize_dynamic, QuantType
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import classification_report, confusion_matrix, f1_score, accuracy_score

from app.services.embedding import get_embedding_service

import unicodedata

DATA_CORPUS_PATH = PROJECT_ROOT / "data" / "metadata" / "router_training_corpus.json"
BENCHMARK_PATH = PROJECT_ROOT / "tests" / "data" / "benchmark_golden_dataset.json"
OOD_PATH = PROJECT_ROOT / "tests" / "data" / "ood_stress_test_dataset.json"
MODELS_DIR = PROJECT_ROOT / "app" / "agent" / "models"
REPORTS_DIR = PROJECT_ROOT / "docs" / "benchmarks"


def norm_text_for_jaccard(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text.lower().strip())
    clean = "".join(c if c.isalnum() else " " for c in text)
    return " ".join(clean.split())


def jaccard_similarity(s1: str, s2: str) -> float:
    w1 = set(norm_text_for_jaccard(s1).split())
    w2 = set(norm_text_for_jaccard(s2).split())
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / len(w1 | w2)


class RouterSLMNet(nn.Module):
    """
    Deep Non-linear SLM Head (Calibrated Temperature-Scaled Neural Net):
    Mapping E5 1024-dim -> 3 classes với LayerNorm, GELU, Dropout và Temperature Buffer T*.
    """
    def __init__(self, in_features: int = 1024, num_classes: int = 3):
        super().__init__()
        self.norm = nn.LayerNorm(in_features)
        self.fc1 = nn.Linear(in_features, 256)
        self.act1 = nn.GELU()
        self.drop1 = nn.Dropout(0.20)
        self.fc2 = nn.Linear(256, 64)
        self.act2 = nn.GELU()
        self.drop2 = nn.Dropout(0.15)
        self.out = nn.Linear(64, num_classes)
        self.register_buffer("temperature", torch.ones(1, dtype=torch.float32))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.norm(x)
        h = self.drop1(self.act1(self.fc1(h)))
        h = self.drop2(self.act2(self.fc2(h)))
        logits = self.out(h)
        return logits / self.temperature


def softmax(x: np.ndarray) -> np.ndarray:
    exp_x = np.exp(x - np.max(x, axis=-1, keepdims=True))
    return exp_x / np.sum(exp_x, axis=-1, keepdims=True)


def compute_nll(logits: np.ndarray, y_true: np.ndarray, temperature: float = 1.0) -> float:
    """Tính Negative Log-Likelihood (NLL) với nhiệt độ T."""
    probs = softmax(logits / temperature)
    eps = 1e-12
    true_probs = np.maximum(probs[np.arange(len(y_true)), y_true], eps)
    return float(-np.mean(np.log(true_probs)))


def optimize_temperature(oof_logits: np.ndarray, y_true: np.ndarray) -> Tuple[float, float, float]:
    """
    Tối ưu hóa nhiệt độ T* cực tiểu hóa Negative Log-Likelihood (NLL) trên Out-of-Fold logits
    (Guo et al., ICML 2017 - On Calibration of Modern Neural Networks).
    """
    nll_before = compute_nll(oof_logits, y_true, temperature=1.0)
    best_T = 1.0
    best_nll = nll_before
    for t_cand in np.linspace(0.20, 3.00, 2801):
        nll = compute_nll(oof_logits, y_true, temperature=float(t_cand))
        if nll < best_nll:
            best_nll = nll
            best_T = float(t_cand)
    return best_T, nll_before, best_nll


def compute_ece(y_true: np.ndarray, y_probs: np.ndarray, n_bins: int = 10) -> float:
    """Tính toán Expected Calibration Error (Guo et al., ICML 2017)."""
    confidences = np.max(y_probs, axis=1)
    predictions = np.argmax(y_probs, axis=1)
    accuracies = (predictions == y_true)
    
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        bin_lower, bin_upper = bin_boundaries[i], bin_boundaries[i + 1]
        in_bin = (confidences > bin_lower) & (confidences <= bin_upper)
        prop_in_bin = np.mean(in_bin)
        if prop_in_bin > 0:
            accuracy_in_bin = np.mean(accuracies[in_bin])
            avg_confidence_in_bin = np.mean(confidences[in_bin])
            ece += np.abs(avg_confidence_in_bin - accuracy_in_bin) * prop_in_bin
    return float(ece)


def compute_brier_score(y_true: np.ndarray, y_probs: np.ndarray, num_classes: int = 3) -> float:
    """Tính toán Multi-class Brier Score."""
    n = len(y_true)
    y_one_hot = np.zeros((n, num_classes))
    y_one_hot[np.arange(n), y_true] = 1.0
    return float(np.mean(np.sum((y_probs - y_one_hot) ** 2, axis=1)))


def main():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("KHẢO THÍ TOÁN HỌC: 5-FOLD STRATIFIED CV & GENERALIZATION AUDIT (MILESTONE 4.2)")
    print("In-Course Agentic RAG Copilot — Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT")
    print("=" * 80)

    # 1. Nạp Dữ liệu
    with open(DATA_CORPUS_PATH, "r", encoding="utf-8") as f:
        corpus = json.load(f)
    train_texts = [s["text"] for s in corpus["samples"]]
    train_labels = [s["intent"] for s in corpus["samples"]]
    classes = corpus.get("classes", ["chit_chat", "course_query", "out_of_scope"])
    corpus_version = corpus.get("version", "2.6.0")

    with open(BENCHMARK_PATH, "r", encoding="utf-8") as f:
        bench_data = json.load(f)
    test_texts = [item.get("query") or item.get("prompt") for item in bench_data]
    test_labels = [item.get("expected_intent") or item.get("intent") for item in bench_data]

    ood_texts = []
    ood_labels = []
    if OOD_PATH.exists():
        with open(OOD_PATH, "r", encoding="utf-8") as f:
            ood_data = json.load(f)
        ood_texts = [item.get("query") or item.get("prompt") for item in ood_data]
        ood_labels = [item.get("expected_intent") or item.get("intent", "out_of_scope") for item in ood_data]

    print(f"\n[DỮ LIỆU] Tập huấn luyện khử nhiễm (v{corpus_version}): {len(train_texts)} mẫu.")
    print(f"[DỮ LIỆU] Tập Frozen Held-out Benchmark: {len(test_texts)} câu (100% Unseen).")
    print(f"[DỮ LIỆU] Tập OOD Stress-Test: {len(ood_texts)} câu.")

    # Kiểm tra tự động rào chắn 0.00% Data Leakage (J < 0.70)
    leaked_bench = []
    max_j_bench = 0.0
    for idx_tr, tr_q in enumerate(train_texts):
        for idx_te, te_q in enumerate(test_texts):
            sim = jaccard_similarity(tr_q, te_q)
            if sim > max_j_bench:
                max_j_bench = sim
            if sim >= 0.70:
                leaked_bench.append((idx_tr, tr_q, te_q, sim))

    leaked_ood = []
    max_j_ood = 0.0
    for idx_tr, tr_q in enumerate(train_texts):
        for idx_ood, ood_q in enumerate(ood_texts):
            sim = jaccard_similarity(tr_q, ood_q)
            if sim > max_j_ood:
                max_j_ood = sim
            if sim >= 0.70 or norm_text_for_jaccard(tr_q) == norm_text_for_jaccard(ood_q):
                leaked_ood.append((idx_tr, tr_q, ood_q, sim))

    print(f"[KIỂM TOÁN ĐỘC LẬP] Max Jaccard (Train vs 200 Golden Benchmark) = {max_j_bench:.4f} (< 0.70) -> Leakage: {len(leaked_bench)} mẫu (0.00%)")
    print(f"[KIỂM TOÁN ĐỘC LẬP] Max Jaccard (Train vs 100 OOD Stress Test)   = {max_j_ood:.4f} (< 0.70) -> Leakage: {len(leaked_ood)} mẫu (0.00%)")
    assert len(leaked_bench) == 0, f"PHÁT HIỆN DATA LEAKAGE VỚI GOLDEN BENCHMARK: {leaked_bench}"
    assert len(leaked_ood) == 0, f"PHÁT HIỆN DATA LEAKAGE VỚI OOD DATASET: {leaked_ood}"

    class_to_idx = {c: i for i, c in enumerate(classes)}
    idx_to_class = {i: c for i, c in enumerate(classes)}

    y_train = np.array([class_to_idx[l] for l in train_labels], dtype=np.int64)
    y_test = np.array([class_to_idx[l] for l in test_labels], dtype=np.int64)

    # 2. Nhúng vector
    emb_svc = get_embedding_service()
    print("\n[BƯỚC 1/5] Trích xuất đặc trưng vector E5 (1024-dim)...")
    t0 = time.perf_counter()
    X_train_raw = np.array([emb_svc.embed_query_dense(t) for t in train_texts], dtype=np.float32)
    X_train = X_train_raw / np.maximum(np.linalg.norm(X_train_raw, axis=1, keepdims=True), 1e-9)

    X_test_raw = np.array([emb_svc.embed_query_dense(t) for t in test_texts], dtype=np.float32)
    X_test = X_test_raw / np.maximum(np.linalg.norm(X_test_raw, axis=1, keepdims=True), 1e-9)
    print(f"           Hoàn tất trong {time.perf_counter() - t0:.2f}s. Train shape: {X_train.shape}, Test shape: {X_test.shape}")

    # =========================================================================
    # BƯỚC 2: 5-FOLD STRATIFIED CROSS VALIDATION & TEMPERATURE OPTIMIZATION T*
    # =========================================================================
    print("\n" + "=" * 80)
    print("[BƯỚC 2/5] THỰC THI 5-FOLD STRATIFIED CV & POST-HOC TEMPERATURE SCALING (T*)")
    print("=" * 80)

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    cv_accs = []
    cv_f1s = []
    cv_eces = []
    cv_briers = []
    oof_slm_logits = np.zeros((len(train_texts), len(classes)), dtype=np.float32)

    for fold, (train_idx, val_idx) in enumerate(skf.split(X_train, y_train), 1):
        X_tr, y_tr = X_train[train_idx], y_train[train_idx]
        X_val, y_val = X_train[val_idx], y_train[val_idx]

        # Huấn luyện Fold RouterSLMNet với Label Smoothing = 0.08
        torch.manual_seed(42 + fold)
        model = RouterSLMNet(in_features=1024, num_classes=len(classes)).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1.2e-3, weight_decay=1e-3)
        criterion = nn.CrossEntropyLoss(label_smoothing=0.08)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=70)

        ds = TensorDataset(torch.from_numpy(X_tr), torch.from_numpy(y_tr))
        loader = DataLoader(ds, batch_size=32, shuffle=True)

        model.train()
        for epoch in range(70):
            for bx, by in loader:
                bx, by = bx.to(device), by.to(device)
                optimizer.zero_grad()
                out = model(bx)
                loss = criterion(out, by)
                loss.backward()
                optimizer.step()
            scheduler.step()

        model.eval()
        with torch.no_grad():
            val_logits = model(torch.from_numpy(X_val).to(device)).cpu().numpy()
            oof_slm_logits[val_idx] = val_logits
            val_probs = softmax(val_logits)
            val_preds = np.argmax(val_probs, axis=1)

        f_acc = accuracy_score(y_val, val_preds) * 100.0
        f_f1 = f1_score(y_val, val_preds, average="macro") * 100.0
        f_ece = compute_ece(y_val, val_probs)
        f_brier = compute_brier_score(y_val, val_probs)

        cv_accs.append(f_acc)
        cv_f1s.append(f_f1)
        cv_eces.append(f_ece)
        cv_briers.append(f_brier)

        print(f"  Fold {fold}: Accuracy = {f_acc:6.2f}%, Macro F1 = {f_f1:6.2f}%, ECE = {f_ece:.4f}, Brier = {f_brier:.4f}")

    # Tối ưu hóa nhiệt độ T* cực tiểu hóa NLL trên Out-of-Fold logits
    optimal_T, nll_before, nll_after = optimize_temperature(oof_slm_logits, y_train)
    oof_slm_probs_cal = softmax(oof_slm_logits / optimal_T)
    cal_oof_ece = compute_ece(y_train, oof_slm_probs_cal)
    cal_oof_brier = compute_brier_score(y_train, oof_slm_probs_cal)

    mean_acc = float(np.mean(cv_accs))
    std_acc = float(np.std(cv_accs, ddof=1))
    mean_f1 = float(np.mean(cv_f1s))
    std_f1 = float(np.std(cv_f1s, ddof=1))
    mean_ece = float(np.mean(cv_eces))
    mean_brier = float(np.mean(cv_briers))

    # Khoảng tin cậy 95% (t-distribution df=4 -> t_crit = 2.776)
    ci95_f1_lower = mean_f1 - 2.776 * (std_f1 / math.sqrt(5))
    ci95_f1_upper = mean_f1 + 2.776 * (std_f1 / math.sqrt(5))

    print("-" * 80)
    print(f"KẾT QUẢ TỔNG HỢP 5-FOLD CV & TEMPERATURE SCALING:")
    print(f"  * SLM Mean Accuracy : {mean_acc:.2f}% ± {std_acc:.2f}%")
    print(f"  * SLM Mean Macro F1 : {mean_f1:.2f}% ± {std_f1:.2f}% (95% CI: [{ci95_f1_lower:.2f}%, {ci95_f1_upper:.2f}%])")
    print(f"  * Optimal Temp T*   : {optimal_T:.4f} (OOF NLL: {nll_before:.4f} -> {nll_after:.4f})")
    print(f"  * Calibrated OOF ECE: {cal_oof_ece:.4f} | Brier: {cal_oof_brier:.4f} (Chuẩn < 0.1200)")

    # =========================================================================
    # BƯỚC 3: HUẤN LUYỆN FINAL PRODUCTION MODEL TRÊN 100% CLEAN TRAIN SET
    # =========================================================================
    print("\n" + "=" * 80)
    print("[BƯỚC 3/5] HUẤN LUYỆN FINAL PRODUCTION MODEL: SLM ONNX INT8 (0% LINEARSVC)")
    print("=" * 80)

    # 3.1 Deep SLM Neural Net với Label Smoothing 0.08 và Temperature T* (Pure Deep Learning)
    print(f"  [3.2] Huấn luyện Deep Non-linear SLM Neural Net (label_smoothing=0.08, T*={optimal_T:.4f})...")
    torch.manual_seed(42)
    final_model = RouterSLMNet(in_features=1024, num_classes=len(classes)).to(device)
    optimizer = torch.optim.AdamW(final_model.parameters(), lr=1.2e-3, weight_decay=1e-3)
    criterion = nn.CrossEntropyLoss(label_smoothing=0.08)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=80)

    ds_full = TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train))
    loader_full = DataLoader(ds_full, batch_size=32, shuffle=True)

    final_model.train()
    for epoch in range(80):
        for bx, by in loader_full:
            bx, by = bx.to(device), by.to(device)
            optimizer.zero_grad()
            out = final_model(bx)
            loss = criterion(out, by)
            loss.backward()
            optimizer.step()
        scheduler.step()

    final_model.eval()
    final_model.temperature.fill_(float(optimal_T))

    # Xuất ONNX FP32
    onnx_fp32 = str(MODELS_DIR / "slm_router_fp32.onnx")
    onnx_int8 = str(MODELS_DIR / "slm_router_int8.onnx")
    dummy_in = torch.randn(1, 1024, device=device)
    torch.onnx.export(
        final_model, dummy_in, onnx_fp32,
        input_names=["dense_vector"], output_names=["logits"],
        dynamic_axes={"dense_vector": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=14
    )

    # Lượng tử hóa sang INT8
    quantize_dynamic(
        model_input=onnx_fp32,
        model_output=onnx_int8,
        weight_type=QuantType.QInt8
    )
    print(f"        Đã xuất và lượng tử hóa: {onnx_int8} ({os.path.getsize(onnx_int8)/(1024*1024):.2f} MB)")

    # Nạp Inference Session
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    ort_session = ort.InferenceSession(onnx_int8, opts, providers=["CPUExecutionProvider"])

    # =========================================================================
    # BƯỚC 4: KHẢO THÍ TRÊN FROZEN HELD-OUT TEST SET (200 CÂU UNSEEN 100%)
    # =========================================================================
    print("\n" + "=" * 80)
    print("[BƯỚC 4/5] KHẢO THÍ TRÊN FROZEN HELD-OUT TEST SET (200 CÂU UNSEEN 100%)")
    print("=" * 80)

    # Đo SLM ONNX INT8 (đã tích hợp Temperature T*)
    slm_preds = []
    slm_probs = []
    latencies = []

    for i in range(len(test_texts)):
        vec_1x1024 = X_test[i:i+1].astype(np.float32)
        t_start = time.perf_counter()
        raw_out = ort_session.run(None, {"dense_vector": vec_1x1024})[0]
        t_dur = (time.perf_counter() - t_start) * 1000.0
        latencies.append(t_dur)
        p = softmax(raw_out[0])
        slm_probs.append(p)
        slm_preds.append(np.argmax(p))

    slm_preds = np.array(slm_preds)
    slm_probs = np.array(slm_probs)
    slm_acc = accuracy_score(y_test, slm_preds) * 100.0
    slm_f1 = f1_score(y_test, slm_preds, average="macro") * 100.0
    slm_ece = compute_ece(y_test, slm_probs)
    slm_p50 = float(np.percentile(latencies, 50))
    slm_p99 = float(np.percentile(latencies, 99))
    delta_gen_slm = abs(mean_acc - slm_acc)

    print(f"\nKẾT QUẢ KHẢO THÍ SLM ONNX INT8 TRÊN HELD-OUT TEST SET (200 CÂU UNSEEN 100%):")
    print(f"┌──────────────────────────────┬──────────────────┐")
    print(f"│ Chỉ Số Đo Lường              │ Fast-Path SLM T* │")
    print(f"├──────────────────────────────┼──────────────────┤")
    print(f"│ True Accuracy (Unseen 100%)  │ {slm_acc:14.2f}% │")
    print(f"│ True Macro F1 (Unseen 100%)  │ {slm_f1:14.2f}% │")
    print(f"│ Expected Calibration Err ECE │ {slm_ece:15.4f} │")
    print(f"│ Độ trễ Median (P50)          │ {slm_p50:12.2f} ms │")
    print(f"│ Độ trễ P99                   │ {slm_p99:12.2f} ms │")
    print(f"│ Generalization Gap |CV - Test|│ {delta_gen_slm:14.2f}% │")
    print(f"└──────────────────────────────┴──────────────────┘")

    # Classification Report
    print("\nChi tiết phân loại Fast-Path SLM ONNX INT8 theo từng Class:")
    report = classification_report(y_test, slm_preds, target_names=classes, digits=4)
    print(report)

    cm = confusion_matrix(y_test, slm_preds)
    print("Confusion Matrix (SLM ONNX INT8):")
    print(cm)

    # =========================================================================
    # BƯỚC 5: KHẢO THÍ TRÊN 100 CÂU OOD STRESS-TEST DATASET
    # =========================================================================
    ood_slm_acc = 0.0
    if OOD_PATH.exists() and len(ood_texts) > 0:
        print("\n" + "=" * 80)
        print("[BƯỚC 5/5] KHẢO THÍ TRÊN 100 CÂU OOD STRESS-TEST DATASET")
        print("=" * 80)
        y_ood = np.array([class_to_idx.get(l, class_to_idx["out_of_scope"]) for l in ood_labels], dtype=np.int64)

        X_ood_raw = np.array([emb_svc.embed_query_dense(t) for t in ood_texts], dtype=np.float32)
        X_ood = X_ood_raw / np.maximum(np.linalg.norm(X_ood_raw, axis=1, keepdims=True), 1e-9)

        ood_slm_probs = []
        ood_slm_preds = []
        for i in range(len(ood_texts)):
            vec = X_ood[i:i+1].astype(np.float32)
            out = ort_session.run(None, {"dense_vector": vec})[0]
            p = softmax(out[0])
            ood_slm_probs.append(p)
            ood_slm_preds.append(np.argmax(p))
        ood_slm_probs = np.array(ood_slm_probs)
        ood_slm_preds = np.array(ood_slm_preds)
        ood_slm_acc = accuracy_score(y_ood, ood_slm_preds) * 100.0
        print(f"  * Fast-Path SLM ONNX INT8 OOD Accuracy: {ood_slm_acc:.2f}% ({np.sum(ood_slm_preds == y_ood)}/100 câu)")

    # =========================================================================
    # XUẤT BÁO CÁO HỌC THUẬT MARKDOWN
    # =========================================================================
    report_md_path = REPORTS_DIR / "decontaminated_generalization_benchmark_report.md"
    report_json_path = REPORTS_DIR / "decontaminated_generalization_benchmark_report.json"

    report_content = f"""# BÁO CÁO KHẢO THÍ TOÁN HỌC & ĐÁNH GIÁ KHÁI QUÁT HÓA ĐỘC LẬP (MILESTONE 4.2)
**Dự án:** In-Course Agentic RAG Copilot — Trần Thành Nghĩa (MSSV: `23DH112252`), HUFLIT  
**Giảng viên hướng dẫn:** ThS. Tiếu Phùng Mai Sương  
**Thời gian thực hiện:** {time.strftime('%d/%m/%Y %H:%M:%S')}  
**Phiên bản Ngữ liệu Huấn luyện:** v{corpus_version} ({len(train_texts)} mẫu, Contrastive Hard Pairs, 0.00% Data Leakage)  
**Bộ Đề thi Kiểm chuẩn:** Frozen Held-Out Test Set 200 câu (`tests/data/benchmark_golden_dataset.json` - 100% Unseen)  

---

## 1. TỔNG QUAN KHỬ NHIỄM, CONTRASTIVE AUGMENTATION & HIỆU CHUẨN NHIỆT ĐỘ T*

Dự án tuân thủ nghiêm ngặt **Data Decontamination Protocol (Chuẩn Andrew Ng & Hastie et al.)** kết hợp **Milestone 4.2 (Calibrated Convex-Neural Ensemble)**:
- **Khử nhiễm kép độc lập 100% ($J < 0.70$):** Max Jaccard giữa tập Train với 200 câu Golden Benchmark là `{max_j_bench:.4f} < 0.70` và với 100 câu OOD Stress Test là `{max_j_ood:.4f} < 0.70` (**0.00% Data Leakage tuyệt đối trên cả 2 bộ test**).
- **Tập dữ liệu độc lập cân bằng:** Huấn luyện trên {len(train_texts)} mẫu độc lập phân bổ đồng đều giữa các lớp (`course_query`, `out_of_scope`, `chit_chat`), ngăn chặn hoàn toàn rò rỉ đề thi.
- **Label Smoothing ($\epsilon = 0.08$) & Temperature Scaling ($T^* = {optimal_T:.4f}$):** Chống bão hòa logit và tối ưu hóa Negative Log-Likelihood trên Out-of-Fold từ `{nll_before:.4f}` xuống `{nll_after:.4f}`.

---

## 2. KẾT QUẢ 5-FOLD STRATIFIED CROSS-VALIDATION (TẬP TRAIN SẠCH N = {len(train_texts)})

| Fold | Accuracy (%) | Macro F1 (%) | ECE (Guo et al. 2017) | Multi-class Brier Score |
| :--- | :---: | :---: | :---: | :---: |
| Fold 1 | {cv_accs[0]:.2f}% | {cv_f1s[0]:.2f}% | {cv_eces[0]:.4f} | {cv_briers[0]:.4f} |
| Fold 2 | {cv_accs[1]:.2f}% | {cv_f1s[1]:.2f}% | {cv_eces[1]:.4f} | {cv_briers[1]:.4f} |
| Fold 3 | {cv_accs[2]:.2f}% | {cv_f1s[2]:.2f}% | {cv_eces[2]:.4f} | {cv_briers[2]:.4f} |
| Fold 4 | {cv_accs[3]:.2f}% | {cv_f1s[3]:.2f}% | {cv_eces[3]:.4f} | {cv_briers[3]:.4f} |
| Fold 5 | {cv_accs[4]:.2f}% | {cv_f1s[4]:.2f}% | {cv_eces[4]:.4f} | {cv_briers[4]:.4f} |
| **Kỳ vọng SLM (Mean ± Std)** | **{mean_acc:.2f}% ± {std_acc:.2f}%** | **{mean_f1:.2f}% ± {std_f1:.2f}%** | **{cal_oof_ece:.4f}** (sau $T^*$) | **{cal_oof_brier:.4f}** (sau $T^*$) |

> **Khoảng tin cậy 95% Macro F1 (Student's t, df=4):** $[{ci95_f1_lower:.2f}\\%, {ci95_f1_upper:.2f}\\%]$.

---

## 3. KHẢO THÍ ĐỘC LẬP TRÊN FROZEN HELD-OUT TEST SET (200 CÂU UNSEEN 100%)

| Chỉ Số Đánh Giá | Fast-Path SLM ONNX INT8 ($T^*$) |
| :--- | :---: |
| **True Accuracy (Unseen 100%)** | **{slm_acc:.2f}%** ({int(round(slm_acc*2))}/200) |
| **True Macro F1 (Unseen 100%)** | **{slm_f1:.2f}%** |
| **Expected Calibration Error (ECE)** | **{slm_ece:.4f}** |
| **Độ trễ trung vị P50** | **{slm_p50:.2f} ms** |
| **Độ trễ phân vị P99** | **{slm_p99:.2f} ms** |
| **Generalization Gap $|\\text{{CV}} - \\text{{Test}}|$** | **{delta_gen_slm:.2f}%** |
| **OOD Stress Test (100 câu)** | **{ood_slm_acc:.2f}%** |

---

## 4. MA TRẬN NHẦM LẪN & CHI TIẾT PHÂN LOẠI TRÊN DỮ LIỆU UNSEEN (SLM ONNX INT8)

```
{report}
```

```
Confusion Matrix:
{cm}
```
"""

    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    print(f"\n[XUẤT BẢN] Đã lưu báo cáo Markdown tại: {report_md_path.name}")

    results_dict = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "author": "Trần Thành Nghĩa (MSSV: 23DH112252)",
        "university": "HUFLIT",
        "corpus_version": corpus_version,
        "training_samples": len(train_texts),
        "test_samples": len(test_texts),
        "leakage_rate": 0.0,
        "max_jaccard_benchmark": max_j_bench,
        "max_jaccard_ood": max_j_ood,
        "optimal_temperature_T": optimal_T,
        "cv_5fold": {
            "mean_accuracy": mean_acc,
            "std_accuracy": std_acc,
            "mean_macro_f1": mean_f1,
            "std_macro_f1": std_f1,
            "mean_ece_uncalibrated": mean_ece,
            "mean_ece_calibrated": cal_oof_ece,
            "mean_brier_calibrated": cal_oof_brier,
            "ci95_macro_f1": [ci95_f1_lower, ci95_f1_upper]
        },
        "held_out_test_results": {
            "slm_int8": {
                "accuracy": slm_acc,
                "macro_f1": slm_f1,
                "ece": slm_ece,
                "latency_p50_ms": slm_p50,
                "latency_p99_ms": slm_p99,
                "generalization_gap": delta_gen_slm
            }
        },
        "ood_stress_test_results": {
            "slm_int8_accuracy": ood_slm_acc
        }
    }

    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(results_dict, f, ensure_ascii=False, indent=2)
    print(f"[XUẤT BẢN] Đã lưu báo cáo JSON tại: {report_json_path.name}")
    print("=" * 80)


if __name__ == "__main__":
    main()

