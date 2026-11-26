#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Kaggle GPU Kernel: Fine-tune MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Đầu vào  : /kaggle/input/*/mdeberta_nli_train.jsonl
Đầu ra   : /kaggle/working/model_bundle.zip (chứa thư mục model HF sẵn sàng cho NLIArbiter)
"""

import json
import os
import random
import shutil
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import torch
from sklearn.metrics import f1_score
from sklearn.model_selection import GroupShuffleSplit
from torch.utils.data import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
)

MODEL_ID = os.environ.get("BASE_NLI_MODEL", "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7")
OUTPUT_DIR = Path("/kaggle/working/mdeberta-v3-xnli-ft")
ZIP_PATH = Path("/kaggle/working/model_bundle.zip")


def normalize_premise_group(premise: str) -> str:
    norm = unicodedata.normalize("NFC", str(premise or "")).lower()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in norm).split())


def split_nli_rows_by_premise(
    rows: Sequence[Dict[str, Any]],
    test_size: float = 0.10,
    seed: int = 42,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Chia train/val theo nhóm `norm_premise` bằng GroupShuffleSplit (0% rò rỉ premise giữa train & val)."""
    items = list(rows)
    if len(items) < 2:
        return items, items
    groups = [normalize_premise_group(r.get("premise", "")) or f"row_{i}" for i, r in enumerate(items)]
    if len(set(groups)) < 2:
        split_idx = max(1, int(len(items) * (1.0 - test_size)))
        return items[:split_idx], items[split_idx:] or items[:1]

    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_idx, val_idx = next(gss.split(items, groups=groups))
    return [items[i] for i in train_idx], [items[i] for i in val_idx]


def compute_zero_shot_ranking_accuracy(
    val_rows: Sequence[Dict[str, Any]],
    val_logits: np.ndarray,
    entailment_id: int = 0,
) -> float:
    """
    Mô phỏng đúng ZeroShotClassificationPipeline.postprocess(..., multi_label=False):
    trên các premise validation có đồng thời giả thuyết đúng (label == 0) và giả thuyết khác (label != 0),
    kiểm tra xem `argmax(logits[:, entailment_id])` có chọn trúng giả thuyết có `label == 0` hay không.
    """
    if len(val_rows) == 0 or len(val_logits) != len(val_rows):
        return 0.0

    grouped: Dict[str, List[Tuple[int, float]]] = {}
    for row, logit_vec in zip(val_rows, val_logits):
        p_key = normalize_premise_group(row.get("premise", ""))
        ent_score = float(logit_vec[entailment_id])
        grouped.setdefault(p_key, []).append((int(row.get("label", -1)), ent_score))

    hits = 0
    total = 0
    for entries in grouped.values():
        has_pos = any(lbl == 0 for lbl, _ in entries)
        has_neg = any(lbl != 0 for lbl, _ in entries)
        if not (has_pos and has_neg):
            continue
        best_lbl, _ = max(entries, key=lambda x: x[1])
        total += 1
        if best_lbl == 0:
            hits += 1

    return round(hits / total, 4) if total > 0 else 0.0


def find_dataset_file(filename: str) -> Path:
    candidates = list(Path("/kaggle/input").rglob(filename))
    if not candidates:
        local_fallback = Path(filename)
        if local_fallback.exists():
            return local_fallback
        raise FileNotFoundError(f"Không tìm thấy {filename} trong /kaggle/input")
    return candidates[0]


class NLIPairDataset(Dataset):
    def __init__(self, rows, tokenizer, max_length: int = 256):
        self.rows = rows
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, idx):
        row = self.rows[idx]
        enc = self.tokenizer(
            row["premise"],
            row["hypothesis"],
            truncation=True,
            max_length=self.max_length,
        )
        item = {k: list(v) for k, v in enc.items()}
        item["labels"] = int(row["label"])
        return item


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    acc = float((preds == labels).mean())
    macro_f1 = float(f1_score(labels, preds, average="macro", zero_division=0))
    return {
        "accuracy": round(acc, 4),
        "macro_f1": round(macro_f1, 4),
    }


def main():
    seed = 42
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    data_path = find_dataset_file("mdeberta_nli_train.jsonl")
    with open(data_path, "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    train_rows, val_rows = split_nli_rows_by_premise(rows, test_size=0.10, seed=seed)
    print(f"[NLI Kaggle] Base={MODEL_ID} | Train={len(train_rows)} | Val={len(val_rows)} (GroupShuffleSplit by premise)")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    # Ép FP32 rõ ràng vì config gốc của mDeBERTa-v3 đặt torch_dtype=float16 dễ tràn số/NaN trên DeBERTa-v2
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID, torch_dtype=torch.float32)

    # Bảo toàn ánh xạ label chuẩn NLI của MoritzLaurer/mDeBERTa-v3 (entailment=0, neutral=1, contradiction=2)
    print(f"[NLI Kaggle] label2id={model.config.label2id}")
    entailment_id = int(model.config.label2id.get("entailment", 0))

    train_ds = NLIPairDataset(train_rows, tokenizer)
    val_ds = NLIPairDataset(val_rows, tokenizer)
    collator = DataCollatorWithPadding(tokenizer=tokenizer, pad_to_multiple_of=8)

    n_gpus = max(1, torch.cuda.device_count())
    eff_batch = 16 * n_gpus
    steps_per_epoch = max(1, (len(train_ds) + eff_batch - 1) // eff_batch)
    warmup_steps = max(1, int(0.10 * steps_per_epoch * 5))
    train_args = TrainingArguments(
        output_dir="/kaggle/working/nli_checkpoints",
        num_train_epochs=5,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=32,
        learning_rate=1.5e-5,
        weight_decay=0.02,
        warmup_steps=warmup_steps,
        max_grad_norm=1.0,
        fp16=False,
        bf16=False,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="macro_f1",
        greater_is_better=True,
        logging_steps=20,
        save_total_limit=1,
        report_to="none",
        seed=seed,
    )

    trainer = Trainer(
        model=model,
        args=train_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=collator,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )
    trainer.train()
    eval_res = trainer.evaluate()
    pred_out = trainer.predict(val_ds)
    zs_rank_acc = compute_zero_shot_ranking_accuracy(val_rows, pred_out.predictions, entailment_id=entailment_id)
    eval_res["zero_shot_ranking_acc"] = zs_rank_acc
    print(f"[NLI Kaggle] Validation metrics: {eval_res} | zero_shot_ranking_acc={zs_rank_acc:.4f}")

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(OUTPUT_DIR))
    tokenizer.save_pretrained(str(OUTPUT_DIR))

    with open(OUTPUT_DIR / "training_summary.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "base_model": MODEL_ID,
                "train_samples": len(train_rows),
                "val_samples": len(val_rows),
                "eval": eval_res,
                "zero_shot_ranking_acc": zs_rank_acc,
            },
            f,
            indent=2,
        )

    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in OUTPUT_DIR.rglob("*"):
            if p.is_file():
                zf.write(p, arcname=p.relative_to(OUTPUT_DIR))
    print(f"[NLI Kaggle] Đã đóng gói hoàn chỉnh: {ZIP_PATH} ({ZIP_PATH.stat().st_size / (1024*1024):.2f} MB)")
    shutil.rmtree("/kaggle/working/nli_checkpoints", ignore_errors=True)
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
