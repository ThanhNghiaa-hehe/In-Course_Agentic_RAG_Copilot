"""
Huấn luyện và Hiệu chuẩn Mô hình Phân loại Ý định (Platt-Calibrated Intent Router)
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Cơ sở khoa học:
- Tầng phân loại: Linear Support Vector Classifier (LinearSVC) với chuẩn hóa L2 trên không gian E5 (1024-dim).
- Tầng hiệu chuẩn: Platt Scaling (Platt, 1999) qua CalibratedClassifierCV 3-fold cross-validation.
- Kiểm chứng thực nghiệm: Đo đạc thời gian huấn luyện & độ trễ suy luận qua time.perf_counter() (μ ± σ),
  tính toán Expected Calibration Error (ECE - Guo et al., ICML 2017) và Multi-class Brier Score.
"""

import sys
import json
import time
from pathlib import Path
from typing import List, Tuple, Dict, Any
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV
import joblib

from app.services.embedding import get_embedding_service


# =========================================================================
# 1. TẬP DỮ LIỆU HUẤN LUYỆN Ý ĐỊNH CÂN BẰNG (TẢI TỪ DATA MANIFEST JSON)
# =========================================================================

CORPUS_JSON_PATH = PROJECT_ROOT / "data" / "metadata" / "router_training_corpus.json"

def load_training_corpus() -> Tuple[List[str], List[str], List[str]]:
    """Tải tập dữ liệu huấn luyện ý định từ file JSON độc lập."""
    if not CORPUS_JSON_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy tập dữ liệu huấn luyện tại: {CORPUS_JSON_PATH}")

    with open(CORPUS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    classes = data.get("classes", ["chit_chat", "course_query", "out_of_scope"])
    samples = data.get("samples", [])
    texts = [item["text"] for item in samples]
    labels = [item["intent"] for item in samples]
    return texts, labels, classes


# =========================================================================
# 2. CÔNG THỨC ĐO LƯỜNG ĐỊNH LƯỢNG (ECE & BRIER SCORE)
# =========================================================================

def compute_ece(y_true_indices: np.ndarray, y_probs: np.ndarray, n_bins: int = 10) -> float:
    """
    Tính Expected Calibration Error (ECE - Guo et al., ICML 2017).
    """
    confidences = np.max(y_probs, axis=1)
    predictions = np.argmax(y_probs, axis=1)
    accuracies = (predictions == y_true_indices)

    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    n_samples = len(y_true_indices)

    for i in range(n_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]
        in_bin = (confidences > bin_lower) & (confidences <= bin_upper)
        bin_size = np.sum(in_bin)

        if bin_size > 0:
            bin_acc = np.mean(accuracies[in_bin])
            bin_conf = np.mean(confidences[in_bin])
            ece += (bin_size / n_samples) * np.abs(bin_acc - bin_conf)

    return float(ece)


def compute_brier_score(y_true_indices: np.ndarray, y_probs: np.ndarray, n_classes: int = 3) -> float:
    """
    Tính Multi-Class Brier Score (Brier, 1950).
    """
    y_one_hot = np.zeros((len(y_true_indices), n_classes))
    y_one_hot[np.arange(len(y_true_indices)), y_true_indices] = 1.0
    brier = np.mean(np.sum((y_probs - y_one_hot) ** 2, axis=1))
    return float(brier)


# =========================================================================
# 3. QUY TRÌNH HUẤN LUYỆN, ĐO LƯỜNG & ĐÓNG GÓI MODEL
# =========================================================================

def train_and_evaluate_router():
    print("=" * 74)
    print(" HUẤN LUYỆN VÀ HIỆU CHUẨN MÔ HÌNH INTENT ROUTER (PLATT SCALING)")
    print(" Tác giả: Trần Thành Nghĩa (MSSV: 23DH112252) - HUFLIT")
    print("=" * 74)

    texts, labels, classes = load_training_corpus()
    class_to_idx = {c: i for i, c in enumerate(classes)}
    y_indices = np.array([class_to_idx[l] for l in labels], dtype=np.int32)

    print(f"[INFO] Tổng số mẫu huấn luyện: {len(texts)}")
    for c in classes:
        print(f"   • Lớp '{c}': {labels.count(c)} mẫu")

    # 1. Nhúng vector bằng multilingual-e5-large
    print("\n[BƯỚC 1] Nhúng vector 1024-dim bằng multilingual-e5-large...")
    emb_svc = get_embedding_service()
    t0_embed = time.perf_counter()
    X_vectors = np.array([emb_svc.embed_query_dense(t) for t in texts], dtype=np.float32)
    # L2 normalize
    X_vectors /= np.maximum(np.linalg.norm(X_vectors, axis=1, keepdims=True), 1e-9)
    embed_duration_s = time.perf_counter() - t0_embed
    print(f"   v Đã nhúng {len(texts)} vectors trong {embed_duration_s:.2f}s. Kích thước ma trận: {X_vectors.shape}")

    # 2. Huấn luyện LinearSVC + CalibratedClassifierCV
    print("\n[BƯỚC 2] Huấn luyện LinearSVC + Platt Scaling (3-fold CV)...")
    base_svc = LinearSVC(C=1.0, dual=False, random_state=42)
    calibrated_clf = CalibratedClassifierCV(
        estimator=base_svc,
        method="sigmoid",  # Platt Scaling (Platt, 1999)
        cv=3
    )

    t0_fit = time.perf_counter()
    calibrated_clf.fit(X_vectors, y_indices)
    fit_time_ms = (time.perf_counter() - t0_fit) * 1000.0
    print(f"   v Huấn luyện & Hiệu chuẩn hoàn tất trong: {fit_time_ms:.2f} ms")

    # 3. Đo lường Thực nghiệm Độ trễ Suy luận (Hardware Latency Benchmark)
    print("\n[BƯỚC 3] Đo lường thực nghiệm độ trễ suy luận (100 lần lặp qua time.perf_counter)...")
    sample_query = X_vectors[0:1]
    latencies = []
    for _ in range(100):
        t_infer_start = time.perf_counter()
        _ = calibrated_clf.predict_proba(sample_query)
        latencies.append((time.perf_counter() - t_infer_start) * 1000.0)

    latency_mean = float(np.mean(latencies))
    latency_std = float(np.std(latencies))
    print(f"   v Độ trễ suy luận thực nghiệm: {latency_mean:.3f} ± {latency_std:.3f} ms")

    # 4. Tính toán ECE và Brier Score trên tập huấn luyện
    y_probs = calibrated_clf.predict_proba(X_vectors)
    y_preds = np.argmax(y_probs, axis=1)
    train_acc = float(np.mean(y_preds == y_indices) * 100.0)
    ece_score = compute_ece(y_indices, y_probs, n_bins=10)
    brier_score = compute_brier_score(y_indices, y_probs, n_classes=3)

    print("\n[BƯỚC 4] Kiểm chứng Định lượng Hiệu chuẩn (Empirical Calibration Metrics):")
    print(f"   • Độ chính xác (Training Accuracy):    {train_acc:.1f}%")
    print(f"   • Expected Calibration Error (ECE):   {ece_score:.4f} (Ngưỡng cam kết: <= 0.0800)")
    print(f"   • Multi-Class Brier Score:             {brier_score:.4f} (Ngưỡng cam kết: <= 0.1500)")

    # 5. Lưu trữ Model và Metadata
    models_dir = PROJECT_ROOT / "app" / "agent" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    model_path = models_dir / "calibrated_router.joblib"
    joblib.dump(calibrated_clf, model_path)
    print(f"\n[BƯỚC 5] Đã lưu model đã hiệu chuẩn tại: {model_path}")

    metadata_path = PROJECT_ROOT / "data" / "metadata" / "router_calibration_metrics.json"
    metadata_payload = {
        "model_name": "LinearSVC + Platt Scaling (CalibratedClassifierCV)",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "author": "Trần Thành Nghĩa (MSSV: 23DH112252)",
        "university": "HUFLIT",
        "classes": classes,
        "n_samples": len(texts),
        "fit_time_ms": round(fit_time_ms, 2),
        "inference_latency_ms": {
            "mean": round(latency_mean, 3),
            "std": round(latency_std, 3)
        },
        "metrics": {
            "accuracy": round(train_acc, 2),
            "ece": round(ece_score, 4),
            "brier_score": round(brier_score, 4)
        }
    }
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata_payload, f, ensure_ascii=False, indent=2)
    print(f"   v Đã lưu hồ sơ kiểm chứng thực nghiệm tại: {metadata_path}")
    print("=" * 74)


if __name__ == "__main__":
    train_and_evaluate_router()
