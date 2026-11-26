#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Kaggle GPU Kernel: QLoRA 4-bit SFT cho Qwen2.5-Coder-7B-Instruct (Socratic Tutor)
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Đầu vào  : /kaggle/input/*/qwen25_socratic_train.jsonl (ChatML messages + lesson_seq)
Đầu ra   : /kaggle/working/model_bundle.zip (LoRA adapter + tokenizer sẵn sàng serve vLLM/PEFT)
"""

import json
import os
import random
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import torch
from sklearn.model_selection import GroupShuffleSplit

MODEL_ID = os.environ.get("BASE_QWEN_MODEL", "Qwen/Qwen2.5-Coder-7B-Instruct")
OUTPUT_DIR = Path("/kaggle/working/qwen25-coder-7b-socratic-lora")
ZIP_PATH = Path("/kaggle/working/model_bundle.zip")
MAX_SEQ_LENGTH = 2048

_NGUON_BAI_RE = re.compile(r"Nguồn Bài\s+(\d+)")


def extract_qwen_lesson_group(row: Dict[str, Any], fallback_idx: int = 0) -> str:
    if row.get("lesson_seq") is not None:
        return f"lesson_{int(row['lesson_seq'])}"
    for m in row.get("messages") or []:
        if m.get("role") == "user":
            hit = _NGUON_BAI_RE.search(str(m.get("content", "")))
            if hit:
                return f"lesson_{int(hit.group(1))}"
    return f"row_{fallback_idx}"


def split_qwen_rows_by_lesson(
    rows: Sequence[Dict[str, Any]],
    test_size: float = 0.10,
    seed: int = 42,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Chia train/val bằng GroupShuffleSplit theo `lesson_seq` (0% rò rỉ bài học giữa train & val)."""
    items = list(rows)
    if len(items) < 2:
        return items, items
    groups = [extract_qwen_lesson_group(r, i) for i, r in enumerate(items)]
    if len(set(groups)) < 2:
        split_idx = max(1, int(len(items) * (1.0 - test_size)))
        return items[:split_idx], items[split_idx:] or items[:1]

    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_idx, val_idx = next(gss.split(items, groups=groups))
    return [items[i] for i in train_idx], [items[i] for i in val_idx]


def tokenize_assistant_only_sft(
    example: Dict[str, Any],
    tokenizer: Any,
    max_length: int = MAX_SEQ_LENGTH,
) -> Dict[str, List[int]]:
    """
    Chỉ tính Cross-Entropy Loss trên các token `assistant`:
    - Render `prompt_text = apply_chat_template(msgs[:2], add_generation_prompt=True)`
    - Render `full_text = apply_chat_template(msgs, add_generation_prompt=False)`
    - Gán `labels = [-100] * mask_len + full_ids[mask_len:]` và kiểm tra bắt buộc `any(x != -100)`
      để ngăn `loss = NaN` hoặc cắt mất thẻ `<timestamp>` ở cuối.
    """
    msgs = example["messages"]
    prompt_text = tokenizer.apply_chat_template(
        msgs[:2],
        tokenize=False,
        add_generation_prompt=True,
    )
    full_text = tokenizer.apply_chat_template(
        msgs,
        tokenize=False,
        add_generation_prompt=False,
    )
    prompt_ids = list(tokenizer(prompt_text, add_special_tokens=False)["input_ids"])
    full_enc = tokenizer(
        full_text,
        truncation=True,
        max_length=max_length,
        add_special_tokens=False,
    )
    full_ids = list(full_enc["input_ids"])
    attn_mask = list(full_enc.get("attention_mask", [1] * len(full_ids)))

    mask_len = min(len(prompt_ids), len(full_ids))
    labels = [-100] * mask_len + full_ids[mask_len:]
    if not any(tok != -100 for tok in labels):
        raise ValueError(
            f"Assistant tokens were completely masked/truncated (prompt_len={len(prompt_ids)}, "
            f"full_len={len(full_ids)}, max_length={max_length})."
        )
    return {
        "input_ids": full_ids,
        "attention_mask": attn_mask,
        "labels": labels,
    }


def ensure_deps():
    for pkg in ("peft", "bitsandbytes", "accelerate", "datasets"):
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


def main():
    ensure_deps()
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        DataCollatorForSeq2Seq,
        Trainer,
        TrainingArguments,
    )

    seed = 42
    random.seed(seed)
    torch.manual_seed(seed)

    data_path = find_dataset_file("qwen25_socratic_train.jsonl")
    with open(data_path, "r", encoding="utf-8") as f:
        raw_rows = [json.loads(line) for line in f if line.strip()]

    train_rows, val_rows = split_qwen_rows_by_lesson(raw_rows, test_size=0.10, seed=seed)
    print(f"[Qwen2.5 QLoRA] Base={MODEL_ID} | Train={len(train_rows)} | Val={len(val_rows)} (GroupShuffleSplit by lesson_seq)")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,
    )
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    def _tok_fn(ex):
        return tokenize_assistant_only_sft(ex, tokenizer, max_length=MAX_SEQ_LENGTH)

    raw_train_ds = Dataset.from_list(train_rows)
    raw_val_ds = Dataset.from_list(val_rows)
    train_ds = raw_train_ds.map(_tok_fn, remove_columns=list(raw_train_ds.column_names))
    val_ds = raw_val_ds.map(_tok_fn, remove_columns=list(raw_val_ds.column_names))

    collator = DataCollatorForSeq2Seq(
        tokenizer=tokenizer,
        model=model,
        label_pad_token_id=-100,
        pad_to_multiple_of=8,
    )

    warmup_steps = max(1, int(0.05 * max(1, (len(train_ds) + 7) // 8) * 2))
    train_args = TrainingArguments(
        output_dir="/kaggle/working/qwen25_checkpoints",
        num_train_epochs=2,
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=8,
        prediction_loss_only=True,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_steps=warmup_steps,
        fp16=True,
        logging_steps=10,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        save_total_limit=1,
        report_to="none",
        optim="paged_adamw_8bit",
        seed=seed,
    )

    trainer = Trainer(
        model=model,
        args=train_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=collator,
    )
    trainer.train()
    eval_res = trainer.evaluate()
    print(f"[Qwen2.5 QLoRA] Validation metrics: {eval_res}")

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(OUTPUT_DIR))
    tokenizer.save_pretrained(str(OUTPUT_DIR))

    with open(OUTPUT_DIR / "training_summary.json", "w", encoding="utf-8") as f:
        json.dump({"base_model": MODEL_ID, "train_samples": len(train_ds), "eval": eval_res}, f, indent=2)

    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in OUTPUT_DIR.rglob("*"):
            if p.is_file():
                zf.write(p, arcname=p.relative_to(OUTPUT_DIR))
    print(f"[Qwen2.5 QLoRA] Đã đóng gói hoàn chỉnh: {ZIP_PATH} ({ZIP_PATH.stat().st_size / (1024*1024):.2f} MB)")
    shutil.rmtree("/kaggle/working/qwen25_checkpoints", ignore_errors=True)
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
