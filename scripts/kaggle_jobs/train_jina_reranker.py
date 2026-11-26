#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Kaggle GPU Kernel: Fine-tune jinaai/jina-reranker-v2-base-multilingual & Export ONNX FP32
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Đầu vào  : /kaggle/input/*/jina_reranker_train.jsonl (triplets: query, pos_passage, neg_passage, lesson_seq)
Đầu ra   : /kaggle/working/model_bundle.zip (chứa onnx/model.onnx FP32 + tokenizer/*.json
           để tải về local và chạy scripts/quantize_reranker_int8.py)
"""

import inspect
import json
import os
import random
import re
import shutil
import subprocess
import sys
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import torch
import torch.nn as nn
from sklearn.model_selection import GroupShuffleSplit
from torch.utils.data import DataLoader, Dataset
from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

MODEL_ID = os.environ.get("BASE_RERANKER_MODEL", "jinaai/jina-reranker-v2-base-multilingual")
OUTPUT_DIR = Path("/kaggle/working/jina-reranker-v2-ft-fp32")
ZIP_PATH = Path("/kaggle/working/model_bundle.zip")

_LESSON_FALLBACK_RE = re.compile(r"(?i)(?:lesson[-_](\d+)|bài\s+(\d+))")


def compute_jina_group_key(row: Dict[str, Any]) -> str:
    seq_val = row.get("lesson_seq")
    if seq_val is None:
        m = _LESSON_FALLBACK_RE.search(str(row.get("pos_passage", "")))
        seq_val = int(m.group(1) or m.group(2)) if m else 0
    norm_q = unicodedata.normalize("NFC", str(row.get("query", ""))).lower()
    norm_q = " ".join("".join(ch if ch.isalnum() else " " for ch in norm_q).split())
    return f"{int(seq_val)}::{norm_q}"


def split_jina_triplets_by_group(
    rows: Sequence[Dict[str, Any]],
    test_size: float = 0.10,
    seed: int = 42,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Chia train/val bằng GroupShuffleSplit theo khóa `lesson_seq::norm_query` (0% rò rỉ nhóm giữa train & val)."""
    items = list(rows)
    if len(items) < 2:
        return items, items
    groups = [compute_jina_group_key(r) for r in items]
    if len(set(groups)) < 2:
        split_idx = max(1, int(len(items) * (1.0 - test_size)))
        return items[:split_idx], items[split_idx:] or items[:1]

    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_idx, val_idx = next(gss.split(items, groups=groups))
    return [items[i] for i in train_idx], [items[i] for i in val_idx]


def ensure_deps():
    for pkg in ("einops", "onnx", "onnxscript"):
        try:
            __import__(pkg)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])


def find_dataset_file(filename: str) -> Path:
    candidates = list(Path("/kaggle/input").rglob(filename))
    if not candidates:
        local_fallback = Path(filename)
        if local_fallback.exists():
            return local_fallback
        raise FileNotFoundError(f"Không tìm thấy {filename} trong /kaggle/input")
    return candidates[0]


class RerankTripletDataset(Dataset):
    def __init__(self, rows):
        self.rows = rows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, idx):
        return self.rows[idx]


def collate_triplets(batch, tokenizer, max_len: int = 384):
    pos_pairs = [(b["query"], b["pos_passage"]) for b in batch]
    neg_pairs = [(b["query"], b["neg_passage"]) for b in batch]
    pos_enc = tokenizer(
        [p[0] for p in pos_pairs],
        [p[1] for p in pos_pairs],
        truncation=True,
        max_length=max_len,
        padding=True,
        return_tensors="pt",
    )
    neg_enc = tokenizer(
        [n[0] for n in neg_pairs],
        [n[1] for n in neg_pairs],
        truncation=True,
        max_length=max_len,
        padding=True,
        return_tensors="pt",
    )
    return pos_enc, neg_enc


class _OnnxLogitsWrapper(nn.Module):
    def __init__(self, model: nn.Module):
        super().__init__()
        self.model = model

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        return self.model(input_ids=input_ids, attention_mask=attention_mask).logits


def export_onnx_fp32(model, tokenizer, out_dir: Path):
    onnx_dir = out_dir / "onnx"
    onnx_dir.mkdir(parents=True, exist_ok=True)
    onnx_path = onnx_dir / "model.onnx"

    model_cpu = model.to("cpu").eval()
    wrapper = _OnnxLogitsWrapper(model_cpu).eval()
    sample = tokenizer(
        ["Vòng lặp while trong C++ hoạt động thế nào?"],
        ["[Bài giảng Video lesson-06.mp4 mốc 05:20]\nBài giảng về vòng lặp while và điều kiện dừng trong C++."],
        truncation=True,
        max_length=256,
        padding=True,
        return_tensors="pt",
    )
    input_names = ["input_ids", "attention_mask"]
    inputs = (sample["input_ids"], sample["attention_mask"])
    dynamic_axes = {
        "input_ids": {0: "batch_size", 1: "sequence_length"},
        "attention_mask": {0: "batch_size", 1: "sequence_length"},
        "logits": {0: "batch_size"},
    }

    export_kwargs: Dict[str, Any] = {
        "input_names": input_names,
        "output_names": ["logits"],
        "dynamic_axes": dynamic_axes,
        "opset_version": 17,
        "do_constant_folding": True,
    }
    if "dynamo" in inspect.signature(torch.onnx.export).parameters:
        export_kwargs["dynamo"] = False

    torch.onnx.export(wrapper, inputs, str(onnx_path), **export_kwargs)
    model_cpu.config.save_pretrained(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))
    print(f"[Jina Kaggle] Exported ONNX FP32 -> {onnx_path} ({onnx_path.stat().st_size / (1024*1024):.2f} MB)")


def main():
    ensure_deps()
    seed = 42
    random.seed(seed)
    torch.manual_seed(seed)

    data_path = find_dataset_file("jina_reranker_train.jsonl")
    with open(data_path, "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    train_rows, val_rows = split_jina_triplets_by_group(rows, test_size=0.10, seed=seed)
    print(f"[Jina Kaggle] Base={MODEL_ID} | Train={len(train_rows)} | Val={len(val_rows)} (GroupShuffleSplit)")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    config = AutoConfig.from_pretrained(MODEL_ID, trust_remote_code=True)
    if hasattr(config, "use_flash_attn"):
        config.use_flash_attn = False
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_ID,
        config=config,
        trust_remote_code=True,
        torch_dtype=torch.float32,
    ).to(device)

    train_loader = DataLoader(
        RerankTripletDataset(train_rows),
        batch_size=8,
        shuffle=True,
        collate_fn=lambda b: collate_triplets(b, tokenizer),
    )
    val_loader = DataLoader(
        RerankTripletDataset(val_rows),
        batch_size=8,
        shuffle=False,
        collate_fn=lambda b: collate_triplets(b, tokenizer),
    )

    epochs = 3
    optimizer = torch.optim.AdamW(model.parameters(), lr=1.5e-5, weight_decay=0.01)
    num_training_steps = max(1, len(train_loader) * epochs)
    num_warmup_steps = max(1, int(0.10 * num_training_steps))
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=num_warmup_steps,
        num_training_steps=num_training_steps,
    )
    margin_loss_fn = nn.MarginRankingLoss(margin=1.2)
    bce_loss_fn = nn.BCEWithLogitsLoss()

    pair_acc = 0.0
    best_pair_acc = -1.0
    best_pos_sig_mean = 0.0
    best_neg_sig_mean = 0.0
    best_state_dict = None
    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        for step, (pos_enc, neg_enc) in enumerate(train_loader, start=1):
            pos_enc = {k: v.to(device) for k, v in pos_enc.items()}
            neg_enc = {k: v.to(device) for k, v in neg_enc.items()}
            optimizer.zero_grad()
            pos_logits = model(**pos_enc).logits.view(-1)
            neg_logits = model(**neg_enc).logits.view(-1)

            targets_rank = torch.ones_like(pos_logits)
            loss_rank = margin_loss_fn(pos_logits, neg_logits, targets_rank)
            loss_bce = 0.5 * (
                bce_loss_fn(pos_logits, torch.ones_like(pos_logits))
                + bce_loss_fn(neg_logits, torch.zeros_like(neg_logits))
            )
            loss = loss_rank + 0.5 * loss_bce
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            total_loss += float(loss.item())

        model.eval()
        val_hits, val_tot = 0, 0
        pos_sig_sum, neg_sig_sum = 0.0, 0.0
        with torch.no_grad():
            for pos_enc, neg_enc in val_loader:
                pos_enc = {k: v.to(device) for k, v in pos_enc.items()}
                neg_enc = {k: v.to(device) for k, v in neg_enc.items()}
                pos_logits = model(**pos_enc).logits.view(-1)
                neg_logits = model(**neg_enc).logits.view(-1)
                val_hits += int((pos_logits > neg_logits).sum().item())
                val_tot += int(pos_logits.numel())
                pos_sig_sum += float(torch.sigmoid(pos_logits).sum().item())
                neg_sig_sum += float(torch.sigmoid(neg_logits).sum().item())
        pair_acc = (val_hits / max(1, val_tot)) * 100.0
        val_pos_sig_mean = pos_sig_sum / max(1, val_tot)
        val_neg_sig_mean = neg_sig_sum / max(1, val_tot)
        print(
            f"[Jina Kaggle] Epoch {epoch}/{epochs} | TrainLoss={total_loss/max(1,len(train_loader)):.4f} "
            f"| PairAcc={pair_acc:.2f}% | PosSig={val_pos_sig_mean:.4f} | NegSig={val_neg_sig_mean:.4f}"
        )
        if pair_acc >= best_pair_acc:
            best_pair_acc = pair_acc
            best_pos_sig_mean = val_pos_sig_mean
            best_neg_sig_mean = val_neg_sig_mean
            best_state_dict = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    if best_state_dict is not None:
        model.load_state_dict(best_state_dict)

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    export_onnx_fp32(model, tokenizer, OUTPUT_DIR)

    with open(OUTPUT_DIR / "training_summary.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "base_model": MODEL_ID,
                "train_triplets": len(train_rows),
                "val_triplets": len(val_rows),
                "val_pair_acc": round(best_pair_acc, 2),
                "val_pos_sigmoid_mean": round(best_pos_sig_mean, 4),
                "val_neg_sigmoid_mean": round(best_neg_sig_mean, 4),
            },
            f,
            indent=2,
        )

    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in OUTPUT_DIR.rglob("*"):
            if p.is_file():
                zf.write(p, arcname=p.relative_to(OUTPUT_DIR))
    print(f"[Jina Kaggle] Đã đóng gói hoàn chỉnh: {ZIP_PATH} ({ZIP_PATH.stat().st_size / (1024*1024):.2f} MB)")
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
