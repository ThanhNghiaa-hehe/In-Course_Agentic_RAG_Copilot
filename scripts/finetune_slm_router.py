#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script Fine-Tune & Calibrate SLM Intent Router Local (ONNX INT8)
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Tính năng chính:
1. Gộp corpus nền (`router_training_corpus.json`) với bể mẫu tương phản sạch
   (`router_hard_negative_hybrid_pool.json`) và tự động kiểm tra khử nhiễm 3 tầng
   (Jaccard < 0.65 với Golden 200, OOD Stress 100, và Multi-Turn queries).
2. Thực thi 5-Fold Stratified CV + Out-of-Fold Temperature Scaling (`T*`)
   với sample weighting nhấn mạnh nhóm hard-negative hybrid.
3. Sao lưu mô hình cũ (`slm_router_int8.onnx.bak`) trước khi xuất FP32/INT8 mới.
4. Báo cáo định lượng Head-to-Head trên 200 câu Golden & 100 câu OOD Stress Test.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import numpy as np
import onnxruntime as ort
import torch
import torch.nn as nn
from onnxruntime.quantization import QuantType, quantize_dynamic
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedKFold
from torch.utils.data import DataLoader, TensorDataset

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.embedding import get_embedding_service
from scripts.train_and_validate_router_cv import (
    BENCHMARK_PATH,
    DATA_CORPUS_PATH,
    MODELS_DIR,
    OOD_PATH,
    REPORTS_DIR,
    RouterSLMNet,
    compute_brier_score,
    compute_ece,
    jaccard_similarity,
    norm_text_for_jaccard,
    optimize_temperature,
    softmax,
)

HARD_NEG_POOL_PATH = PROJECT_ROOT / "data" / "metadata" / "router_hard_negative_hybrid_pool.json"
MULTITURN_PATH = PROJECT_ROOT / "tests" / "data" / "multiturn_benchmark_dataset.json"
MERGED_CORPUS_OUT_PATH = PROJECT_ROOT / "data" / "metadata" / "router_training_corpus_v2_9_hybrid.json"


from scripts.validate_training_datasets import (
    check_decontamination_detailed,
    load_heldout_queries,
)


def _extract_test_queries() -> Tuple[List[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Đọc danh sách câu truy vấn các tập đánh giá giữ kín để kiểm tra khử nhiễm."""
    _, heldout_queries = load_heldout_queries()
    bench_data = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    ood_data = json.loads(OOD_PATH.read_text(encoding="utf-8")) if OOD_PATH.exists() else []
    return heldout_queries, bench_data, ood_data


def load_decontaminated_corpus(
    *,
    hard_neg_weight: float = 1.75,
    max_jaccard_threshold: float = 0.65,
    include_hard_pool: bool = True,
) -> Tuple[List[str], List[str], np.ndarray, List[str], Dict[str, Any]]:
    """Nạp tập train sạch, kiểm tra khử nhiễm chéo tuyệt đối với mọi tập test."""
    with open(DATA_CORPUS_PATH, "r", encoding="utf-8") as f:
        base_corpus = json.load(f)

    classes = list(base_corpus.get("classes", ["chit_chat", "course_query", "out_of_scope"]))
    heldout_queries, _, _ = _extract_test_queries()
    heldout_norm_set: Set[str] = {norm_text_for_jaccard(q) for q in heldout_queries}

    merged_samples: List[Dict[str, Any]] = []
    seen_norm_to_intent: Dict[str, str] = {}
    leaked_rejected: List[Dict[str, Any]] = []
    exact_conflict_rejected: List[Dict[str, Any]] = []

    def _try_add(sample: Dict[str, Any], weight: float) -> None:
        text = (sample.get("text") or "").strip()
        intent = sample.get("intent") or ""
        if not text or intent not in classes:
            return
        nt = norm_text_for_jaccard(text)
        if not nt:
            return
        if nt in seen_norm_to_intent:
            if seen_norm_to_intent[nt] != intent:
                exact_conflict_rejected.append({
                    "text": text,
                    "a_intent": seen_norm_to_intent[nt],
                    "b_intent": intent,
                })
            return
        ok, score, reason = check_decontamination_detailed(
            text,
            heldout_norm_set,
            heldout_queries,
            max_jaccard=max_jaccard_threshold,
            max_containment=0.85,
        )
        if not ok:
            leaked_rejected.append({"text": text, "reason": reason, "max_jaccard": score})
            return
        seen_norm_to_intent[nt] = intent
        entry = dict(sample)
        entry["sample_weight"] = float(weight)
        merged_samples.append(entry)

    for s in base_corpus.get("samples", []):
        _try_add(s, weight=1.0)

    hard_pool_count = 0
    if include_hard_pool and HARD_NEG_POOL_PATH.exists():
        with open(HARD_NEG_POOL_PATH, "r", encoding="utf-8") as f:
            hard_pool = json.load(f)
        for s in hard_pool.get("samples", []):
            before_n = len(merged_samples)
            _try_add(s, weight=hard_neg_weight)
            if len(merged_samples) > before_n:
                hard_pool_count += 1

    texts = [s["text"] for s in merged_samples]
    labels = [s["intent"] for s in merged_samples]
    weights = np.array([float(s["sample_weight"]) for s in merged_samples], dtype=np.float32)

    audit = {
        "base_samples": len(base_corpus.get("samples", [])),
        "accepted_hard_pool": hard_pool_count,
        "total_clean_samples": len(merged_samples),
        "class_distribution": dict(Counter(labels)),
        "leaked_rejected_count": len(leaked_rejected),
        "leaked_rejected_preview": leaked_rejected[:10],
        "exact_conflict_rejected_count": len(exact_conflict_rejected),
        "conflict_drops_count": 0,
        "heldout_queries_checked": len(heldout_queries),
    }

    with open(MERGED_CORPUS_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "description": "Double-Decontaminated Corpus + General Hard-Negative Hybrid Contrastive Pool (v2.9.0)",
                "version": "2.9.0",
                "author": "Trần Thành Nghĩa (MSSV: 23DH112252)",
                "classes": classes,
                "audit": audit,
                "samples": [{"text": s["text"], "intent": s["intent"], "group": s.get("group", "base")} for s in merged_samples],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    return texts, labels, weights, classes, audit


def _eval_onnx_session(onnx_path: Path, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, List[float]]:
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess = ort.InferenceSession(str(onnx_path), opts, providers=["CPUExecutionProvider"])
    probs_list: List[np.ndarray] = []
    preds_list: List[int] = []
    latencies: List[float] = []
    for i in range(len(X)):
        vec = X[i : i + 1].astype(np.float32)
        t0 = time.perf_counter()
        logits = sess.run(None, {"dense_vector": vec})[0][0]
        latencies.append((time.perf_counter() - t0) * 1000.0)
        p = softmax(logits)
        probs_list.append(p)
        preds_list.append(int(np.argmax(p)))
    return np.array(preds_list), np.array(probs_list), latencies


def _train_single_slm(
    X_tr: np.ndarray,
    y_tr: np.ndarray,
    w_tr: np.ndarray,
    *,
    num_classes: int,
    epochs: int,
    lr: float,
    weight_decay: float,
    label_smoothing: float,
    seed: int,
    device: torch.device,
) -> RouterSLMNet:
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = RouterSLMNet(in_features=1024, num_classes=num_classes).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    criterion = nn.CrossEntropyLoss(reduction="none", label_smoothing=label_smoothing)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, epochs))

    ds = TensorDataset(torch.from_numpy(X_tr), torch.from_numpy(y_tr), torch.from_numpy(w_tr))
    loader = DataLoader(ds, batch_size=32, shuffle=True)
    model.train()
    for _ in range(epochs):
        for bx, by, bw in loader:
            bx, by, bw = bx.to(device), by.to(device), bw.to(device)
            optimizer.zero_grad()
            logits = model(bx)
            per_sample_loss = criterion(logits, by)
            loss = torch.mean(per_sample_loss * bw)
            loss.backward()
            optimizer.step()
        scheduler.step()
    model.eval()
    return model


def finetune_and_evaluate(args: argparse.Namespace) -> int:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print(" FINE-TUNE & CALIBRATE SLM ROUTER ONNX INT8 (HARD-NEGATIVE HYBRID EDITION)")
    print(" Sinh viên: Trần Thành Nghĩa (MSSV: 23DH112252) — HUFLIT")
    print("=" * 80)

    train_texts, train_labels, sample_weights, classes, audit = load_decontaminated_corpus(
        hard_neg_weight=args.hard_neg_weight,
        max_jaccard_threshold=args.max_jaccard,
        include_hard_pool=not args.no_hard_pool,
    )
    print(f"[1/6] Corpus sau khử nhiễm: {audit['total_clean_samples']} mẫu | Distribution: {audit['class_distribution']}")
    print(f"      Hard-negative pool được nhận: {audit['accepted_hard_pool']} | Bị loại do Jaccard/Exact: {audit['leaked_rejected_count']}")

    _, bench_data, ood_data = _extract_test_queries()
    test_texts = [item.get("query") or item.get("prompt") for item in bench_data]
    test_labels = [item.get("expected_intent") or item.get("intent") for item in bench_data]
    test_tiers = [item.get("tier", "unknown") for item in bench_data]

    ood_texts = [item.get("query") or item.get("prompt") for item in ood_data]
    ood_labels = [item.get("expected_intent") or item.get("intent", "out_of_scope") for item in ood_data]

    class_to_idx = {c: i for i, c in enumerate(classes)}
    y_train = np.array([class_to_idx[l] for l in train_labels], dtype=np.int64)
    y_test = np.array([class_to_idx[l] for l in test_labels], dtype=np.int64)
    y_ood = np.array([class_to_idx.get(l, class_to_idx["out_of_scope"]) for l in ood_labels], dtype=np.int64) if ood_texts else np.array([], dtype=np.int64)

    emb_svc = get_embedding_service()

    def _embed_normalized(texts: List[str]) -> np.ndarray:
        raw = np.array([emb_svc.embed_query_dense(t) for t in texts], dtype=np.float32)
        return raw / np.maximum(np.linalg.norm(raw, axis=1, keepdims=True), 1e-9)

    print(f"[2/6] Đang nhúng dense E5 1024-dim (train={len(train_texts)}, golden={len(test_texts)}, ood={len(ood_texts)})...")
    t_emb = time.perf_counter()
    X_train = _embed_normalized(train_texts)
    X_test = _embed_normalized(test_texts)
    X_ood = _embed_normalized(ood_texts) if ood_texts else np.zeros((0, 1024), dtype=np.float32)
    print(f"      Hoàn tất embedding trong {time.perf_counter() - t_emb:.2f}s.")

    # Kiểm tra & loại xung đột nhãn thật (Jaccard >= 0.72 hoặc E5 Cosine >= 0.93 nhưng trái nhãn) trước khi CV
    merged_json = json.loads(MERGED_CORPUS_OUT_PATH.read_text(encoding="utf-8"))
    merged_samples = merged_json.get("samples", [])
    sim_mat = np.dot(X_train, X_train.T)
    conflict_drops: Set[int] = set()
    conflict_logs: List[str] = []
    for i in range(len(train_texts)):
        for j in range(i + 1, len(train_texts)):
            if train_labels[i] != train_labels[j]:
                jac = jaccard_similarity(train_texts[i], train_texts[j])
                if jac >= 0.72 or sim_mat[i, j] >= 0.93:
                    grp_i = merged_samples[i].get("group", "base") if i < len(merged_samples) else "base"
                    grp_j = merged_samples[j].get("group", "base") if j < len(merged_samples) else "base"
                    drop_idx = j if grp_j != "base" else (i if grp_i != "base" else j)
                    conflict_drops.add(drop_idx)
                    conflict_logs.append(f"cos={sim_mat[i,j]:.3f}, jac={jac:.2f} ({train_labels[i]} vs {train_labels[j]})")
    if conflict_drops:
        keep_mask = [idx for idx in range(len(train_texts)) if idx not in conflict_drops]
        X_train = X_train[keep_mask]
        train_texts = [train_texts[idx] for idx in keep_mask]
        train_labels = [train_labels[idx] for idx in keep_mask]
        sample_weights = sample_weights[keep_mask]
        y_train = y_train[keep_mask]
        merged_samples = [merged_samples[idx] for idx in keep_mask if idx < len(merged_samples)]
        audit["total_clean_samples"] = len(merged_samples)
        audit["class_distribution"] = dict(Counter(train_labels))
        audit["conflict_drops_count"] = len(conflict_drops)
        merged_json["samples"] = merged_samples
        merged_json["audit"] = audit
        MERGED_CORPUS_OUT_PATH.write_text(
            json.dumps(merged_json, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"      [Data Hygiene] Đã tự loại {len(conflict_drops)} mẫu xung đột nhãn thật và đồng bộ audit ({len(merged_samples)} mẫu): {conflict_logs[:5]}")
    else:
        audit["total_clean_samples"] = len(merged_samples)
        audit["class_distribution"] = dict(Counter(train_labels))
        audit["conflict_drops_count"] = 0
        merged_json["audit"] = audit
        MERGED_CORPUS_OUT_PATH.write_text(
            json.dumps(merged_json, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("      [Data Hygiene] 0 mẫu xung đột nhãn thật (cos>=0.93 hoặc jac>=0.72).")

    int8_path = MODELS_DIR / "slm_router_int8.onnx"
    fp32_path = MODELS_DIR / "slm_router_fp32.onnx"
    baseline_metrics: Dict[str, Any] = {}
    if int8_path.exists():
        b_preds, b_probs, _ = _eval_onnx_session(int8_path, X_test)
        b_acc = accuracy_score(y_test, b_preds) * 100.0
        b_f1 = f1_score(y_test, b_preds, average="macro") * 100.0
        b_adv_idx = [i for i, t in enumerate(test_tiers) if t == "adversarial_hybrid"]
        b_adv_acc = accuracy_score(y_test[b_adv_idx], b_preds[b_adv_idx]) * 100.0 if b_adv_idx else 0.0
        b_ood_acc = 0.0
        if len(X_ood) > 0:
            bo_preds, _, _ = _eval_onnx_session(int8_path, X_ood)
            b_ood_acc = accuracy_score(y_ood, bo_preds) * 100.0
        baseline_metrics = {
            "golden_acc": round(b_acc, 2),
            "golden_macro_f1": round(b_f1, 2),
            "golden_ece": round(compute_ece(y_test, b_probs), 4),
            "adversarial_hybrid_acc": round(b_adv_acc, 2),
            "ood_stress_acc": round(b_ood_acc, 2),
        }
        print(
            f"[Baseline SLM hiện tại] Golden Acc={b_acc:.2f}% | Macro F1={b_f1:.2f}% | "
            f"Adv-Hybrid={b_adv_acc:.2f}% | OOD Stress={b_ood_acc:.2f}%"
        )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[3/6] 5-Fold Stratified CV trên thiết bị: {device} (epochs={args.epochs}, lr={args.lr})...")
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    oof_logits = np.zeros((len(X_train), len(classes)), dtype=np.float32)
    cv_accs: List[float] = []
    cv_f1s: List[float] = []

    for fold, (tr_idx, val_idx) in enumerate(skf.split(X_train, y_train), start=1):
        m_fold = _train_single_slm(
            X_train[tr_idx],
            y_train[tr_idx],
            sample_weights[tr_idx],
            num_classes=len(classes),
            epochs=args.epochs,
            lr=args.lr,
            weight_decay=args.weight_decay,
            label_smoothing=args.label_smoothing,
            seed=42 + fold,
            device=device,
        )
        with torch.no_grad():
            vl = m_fold(torch.from_numpy(X_train[val_idx]).to(device)).cpu().numpy()
        oof_logits[val_idx] = vl
        vp = np.argmax(softmax(vl), axis=1)
        fa = accuracy_score(y_train[val_idx], vp) * 100.0
        ff = f1_score(y_train[val_idx], vp, average="macro") * 100.0
        cv_accs.append(fa)
        cv_f1s.append(ff)
        print(f"      Fold {fold}: Acc={fa:6.2f}% | Macro F1={ff:6.2f}%")

    optimal_T, nll_before, nll_after = optimize_temperature(oof_logits, y_train)
    oof_probs_cal = softmax(oof_logits / optimal_T)
    mean_cv_acc = float(np.mean(cv_accs))
    std_cv_acc = float(np.std(cv_accs, ddof=1))
    mean_cv_f1 = float(np.mean(cv_f1s))
    std_cv_f1 = float(np.std(cv_f1s, ddof=1))
    cal_ece = compute_ece(y_train, oof_probs_cal)
    cal_brier = compute_brier_score(y_train, oof_probs_cal)
    print(f"      CV Mean Acc={mean_cv_acc:.2f}%±{std_cv_acc:.2f}% | T*={optimal_T:.4f} (NLL {nll_before:.4f}->{nll_after:.4f}) | ECE={cal_ece:.4f}")

    print("[4/6] Huấn luyện mô hình cuối trên 100% tập train sạch & lượng tử hóa ONNX INT8...")
    final_model = _train_single_slm(
        X_train,
        y_train,
        sample_weights,
        num_classes=len(classes),
        epochs=args.epochs,
        lr=args.lr,
        weight_decay=args.weight_decay,
        label_smoothing=args.label_smoothing,
        seed=42,
        device=device,
    )
    final_model.temperature.fill_(float(optimal_T))

    cand_fp32 = MODELS_DIR / "slm_router_fp32.candidate.onnx"
    cand_int8 = MODELS_DIR / "slm_router_int8.candidate.onnx"
    dummy_in = torch.randn(1, 1024, device=device)
    torch.onnx.export(
        final_model,
        dummy_in,
        str(cand_fp32),
        input_names=["dense_vector"],
        output_names=["logits"],
        dynamic_axes={"dense_vector": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=14,
    )
    quantize_dynamic(model_input=str(cand_fp32), model_output=str(cand_int8), weight_type=QuantType.QInt8)

    print("[5/6] Đánh giá candidate mới trên Frozen Golden 200 & OOD Stress 100...")
    new_preds, new_probs, latencies = _eval_onnx_session(cand_int8, X_test)
    new_acc = accuracy_score(y_test, new_preds) * 100.0
    new_f1 = f1_score(y_test, new_preds, average="macro") * 100.0
    new_ece = compute_ece(y_test, new_probs)
    adv_idx = [i for i, t in enumerate(test_tiers) if t == "adversarial_hybrid"]
    new_adv_acc = accuracy_score(y_test[adv_idx], new_preds[adv_idx]) * 100.0 if adv_idx else 0.0
    new_ood_acc = 0.0
    if len(X_ood) > 0:
        no_preds, _, _ = _eval_onnx_session(cand_int8, X_ood)
        new_ood_acc = accuracy_score(y_ood, no_preds) * 100.0

    print("\n" + "-" * 80)
    print(f"  Golden 200 Acc    : {new_acc:.2f}% (Baseline: {baseline_metrics.get('golden_acc', 'N/A')}%)")
    print(f"  Golden Macro F1   : {new_f1:.2f}% (Baseline: {baseline_metrics.get('golden_macro_f1', 'N/A')}%)")
    print(f"  Adversarial-Hybrid: {new_adv_acc:.2f}% (Baseline: {baseline_metrics.get('adversarial_hybrid_acc', 'N/A')}%)")
    print(f"  OOD Stress 100 Acc: {new_ood_acc:.2f}% (Baseline: {baseline_metrics.get('ood_stress_acc', 'N/A')}%)")
    print(f"  ECE               : {new_ece:.4f} (Baseline: {baseline_metrics.get('golden_ece', 'N/A')})")
    print(f"  Latency P50 / P99 : {np.percentile(latencies, 50):.3f}ms / {np.percentile(latencies, 99):.3f}ms")
    print("-" * 80)
    print(classification_report(y_test, new_preds, target_names=classes, digits=4))

    should_promote = args.force_deploy or (
        not baseline_metrics
        or (new_acc >= baseline_metrics["golden_acc"] and new_ood_acc >= baseline_metrics["ood_stress_acc"] - 1.0)
    )
    if args.dry_run:
        print("[6/6] Dry-run mode: giữ nguyên slm_router_int8.onnx cũ, giữ file candidate để kiểm tra.")
    elif should_promote:
        if int8_path.exists():
            shutil.copy2(int8_path, MODELS_DIR / "slm_router_int8.onnx.bak")
        if fp32_path.exists():
            shutil.copy2(fp32_path, MODELS_DIR / "slm_router_fp32.onnx.bak")
        shutil.move(str(cand_fp32), str(fp32_path))
        shutil.move(str(cand_int8), str(int8_path))
        print(f"[6/6] Đã sao lưu *.bak và kích hoạt model mới tại: {int8_path}")
    else:
        print("[6/6] CẢNH BÁO: Candidate không vượt baseline nên GIỮ NGUYÊN model cũ (dùng --force-deploy nếu vẫn muốn ghi đè).")

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "author": "Trần Thành Nghĩa (MSSV: 23DH112252)",
        "promoted": bool(should_promote and not args.dry_run),
        "corpus_audit": audit,
        "hyperparams": {
            "epochs": args.epochs,
            "lr": args.lr,
            "weight_decay": args.weight_decay,
            "label_smoothing": args.label_smoothing,
            "hard_neg_weight": args.hard_neg_weight,
            "optimal_temperature": round(optimal_T, 4),
        },
        "cv_metrics": {
            "mean_acc": round(mean_cv_acc, 2),
            "std_acc": round(std_cv_acc, 2),
            "mean_macro_f1": round(mean_cv_f1, 2),
            "std_macro_f1": round(std_cv_f1, 2),
            "cal_oof_ece": round(cal_ece, 4),
            "cal_oof_brier": round(cal_brier, 4),
        },
        "baseline_metrics": baseline_metrics,
        "candidate_metrics": {
            "golden_acc": round(new_acc, 2),
            "golden_macro_f1": round(new_f1, 2),
            "golden_ece": round(new_ece, 4),
            "adversarial_hybrid_acc": round(new_adv_acc, 2),
            "ood_stress_acc": round(new_ood_acc, 2),
            "p50_ms": round(float(np.percentile(latencies, 50)), 4),
            "p99_ms": round(float(np.percentile(latencies, 99)), 4),
            "confusion_matrix": confusion_matrix(y_test, new_preds).tolist(),
        },
    }
    report_path = REPORTS_DIR / "slm_finetune_latest_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"      Đã lưu báo cáo chi tiết tại: {report_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune & calibrate local SLM Router ONNX INT8")
    parser.add_argument("--epochs", type=int, default=90)
    parser.add_argument("--lr", type=float, default=1.2e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-3)
    parser.add_argument("--label-smoothing", type=float, default=0.06)
    parser.add_argument("--hard-neg-weight", type=float, default=1.0)
    parser.add_argument("--max-jaccard", type=float, default=0.65)
    parser.add_argument("--no-hard-pool", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-deploy", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(finetune_and_evaluate(parse_args()))
