"""Unit tests for Kaggle vLLM LoRA auto-attach and HMAC-signed Cloudflare URL `.env` sync."""

from __future__ import annotations

import time
import zipfile
from pathlib import Path

from scripts.kaggle_jobs.serve_qwen25_vllm_kaggle import find_and_prepare_lora_adapter
from scripts.sync_kaggle_llm_env import (
    sign_sync_payload,
    upsert_env_vars,
    verify_sync_payload,
)


def test_verify_sync_payload_hmac_and_security_guards():
    secret = "test_secret_key_for_hmac_verification"
    now = int(time.time())
    url = "https://alpha-beta-gamma.trycloudflare.com/v1"
    model = "socratic-lora"
    sig = sign_sync_payload(url, model, now, secret)

    ok, reason = verify_sync_payload({"url": url, "model": model, "ts": now, "sig": sig}, secret, now_ts=now)
    assert ok is True and reason == "ok"

    # Tampered URL rejected
    ok_bad_url, _ = verify_sync_payload(
        {"url": "https://attacker.trycloudflare.com/v1", "model": model, "ts": now, "sig": sig},
        secret,
        now_ts=now,
    )
    assert ok_bad_url is False

    # Untrusted host rejected even if signed with secret
    evil_url = "https://evil-domain.com/v1"
    evil_sig = sign_sync_payload(evil_url, model, now, secret)
    ok_evil, _ = verify_sync_payload(
        {"url": evil_url, "model": model, "ts": now, "sig": evil_sig},
        secret,
        now_ts=now,
    )
    assert ok_evil is False

    # Wrong secret rejected
    ok_bad_sec, _ = verify_sync_payload({"url": url, "model": model, "ts": now, "sig": sig}, "wrong", now_ts=now)
    assert ok_bad_sec is False

    # Expired timestamp rejected
    stale_ts = now - 90000
    stale_sig = sign_sync_payload(url, model, stale_ts, secret)
    ok_stale, _ = verify_sync_payload(
        {"url": url, "model": model, "ts": stale_ts, "sig": stale_sig},
        secret,
        max_age_sec=3600,
        now_ts=now,
    )
    assert ok_stale is False


def test_upsert_env_vars_preserves_existing_keys_and_comments(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# Core Config\n"
        "QDRANT_URL=https://example.qdrant.io\n"
        "LLM_BASE_URL=https://old-tunnel.trycloudflare.com/v1\n"
        "LLM_MODEL_NAME=Qwen/Qwen2.5-Coder-7B-Instruct\n",
        encoding="utf-8",
    )

    old = upsert_env_vars(
        env_file,
        {
            "LLM_BASE_URL": "https://new-tunnel.trycloudflare.com/v1",
            "LLM_MODEL_NAME": "socratic-lora",
            "KAGGLE_SYNC_TOPIC": "rag-vllm-abc123",
        },
    )
    assert old["LLM_BASE_URL"] == "https://old-tunnel.trycloudflare.com/v1"
    assert old["KAGGLE_SYNC_TOPIC"] is None

    updated = env_file.read_text(encoding="utf-8")
    assert "# Core Config" in updated
    assert "QDRANT_URL=https://example.qdrant.io" in updated
    assert "LLM_BASE_URL=https://new-tunnel.trycloudflare.com/v1" in updated
    assert "LLM_MODEL_NAME=socratic-lora" in updated
    assert "KAGGLE_SYNC_TOPIC=rag-vllm-abc123" in updated


def test_find_and_prepare_lora_adapter_supports_direct_and_zip(tmp_path: Path):
    # 1. Zipped model_bundle.zip inside /kaggle/input/qwen25-qlora-ft/
    in_root = tmp_path / "input"
    zip_dir = in_root / "in-course-rag-qwen25-qlora-ft"
    zip_dir.mkdir(parents=True)
    bundle_zip = zip_dir / "model_bundle.zip"
    with zipfile.ZipFile(bundle_zip, "w") as zf:
        zf.writestr("adapter_config.json", '{"r": 16}')
        zf.writestr("adapter_model.safetensors", "stub")

    extract_dir = tmp_path / "working" / "socratic_lora"
    resolved_zip = find_and_prepare_lora_adapter(input_root=in_root, extract_dir=extract_dir)
    assert resolved_zip == extract_dir
    assert (extract_dir / "adapter_config.json").exists()

    # 2. Direct extracted adapter directory preferred over zip
    direct_dir = in_root / "socratic-lora-direct"
    direct_dir.mkdir(parents=True)
    (direct_dir / "adapter_config.json").write_text('{"r": 16}', encoding="utf-8")
    resolved_direct = find_and_prepare_lora_adapter(input_root=in_root, extract_dir=extract_dir)
    assert resolved_direct == direct_dir
