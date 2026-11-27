#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tiện ích đồng bộ tự động URL Cloudflare/vLLM từ Kaggle về tệp `.env` cục bộ
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Cơ chế bảo mật:
- Tín hiệu gửi qua kênh ntfy.sh riêng (`KAGGLE_SYNC_TOPIC`) được ký HMAC-SHA256 bằng
  `KAGGLE_SYNC_SECRET` để chống giả mạo URL endpoint.
- Xác thực tên miền HTTPS hợp lệ (`.trycloudflare.com` / `.ngrok-free.app`) và chống replay quá hạn.
- Hỗ trợ `--init` (tạo khóa bí mật trong `.env`), `--once` (đồng bộ 1 lần), `--watch` (nghe liên tục
  & tự kích hoạt hot-reload `uvicorn --reload`), và `--url` (cập nhật thủ công 1 lệnh).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "app" / "config.py"
ALLOWED_TUNNEL_SUFFIXES: Tuple[str, ...] = (".trycloudflare.com", ".ngrok-free.app", ".ngrok.io")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def read_env_dict(env_path: Path) -> Dict[str, str]:
    """Đọc các cặp KEY=VALUE từ tệp `.env`."""
    data: Dict[str, str] = {}
    if not env_path.exists():
        return data
    for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def upsert_env_vars(env_path: Path, updates: Dict[str, str]) -> Dict[str, Optional[str]]:
    """
    Cập nhật giá trị các biến trong `.env` tại chỗ, giữ nguyên thứ tự và các dòng comment hiện có.
    Trả về dict `{key: old_value}` (hoặc `None` nếu biến chưa từng tồn tại).
    """
    old_values: Dict[str, Optional[str]] = {k: None for k in updates}
    lines: List[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8", errors="replace").splitlines()

    seen: set[str] = set()
    out_lines: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            k_clean = k.strip()
            if k_clean in updates:
                old_values[k_clean] = v.strip()
                if k_clean not in seen:
                    out_lines.append(f"{k_clean}={updates[k_clean]}")
                    seen.add(k_clean)
                continue
        out_lines.append(line)

    for k, v in updates.items():
        if k not in seen:
            out_lines.append(f"{k}={v}")

    env_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return old_values


def sign_sync_payload(url: str, model: str, ts: int, secret: str) -> str:
    msg = f"{url}|{model}|{int(ts)}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def verify_sync_payload(
    payload: Dict[str, Any],
    secret: str,
    max_age_sec: int = 86400,
    now_ts: Optional[int] = None,
) -> Tuple[bool, str]:
    """Kiểm tra tính hợp lệ, chữ ký HMAC-SHA256 và miền URL tunnel của gói tin đồng bộ."""
    if not secret:
        return False, "Thiếu KAGGLE_SYNC_SECRET"

    url = str(payload.get("url") or "").strip()
    model = str(payload.get("model") or "").strip()
    sig = str(payload.get("sig") or "").strip()
    try:
        ts = int(payload.get("ts"))
    except (TypeError, ValueError):
        return False, "Thiếu hoặc sai định dạng timestamp `ts`"

    if not url.startswith("https://") or not url.endswith("/v1"):
        return False, f"URL không đúng định dạng https://.../v1: {url}"

    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if not any(host.endswith(sfx) for sfx in ALLOWED_TUNNEL_SUFFIXES):
        return False, f"Host không nằm trong whitelist tunnel ({host})"

    if not model:
        return False, "Thiếu tên model phục vụ"

    cur = int(time.time()) if now_ts is None else int(now_ts)
    if abs(cur - ts) > max_age_sec:
        return False, f"Tín hiệu đã quá hạn ({abs(cur - ts)}s > {max_age_sec}s)"

    expected_sig = sign_sync_payload(url, model, ts, secret)
    if not hmac.compare_digest(sig, expected_sig):
        return False, "Chữ ký HMAC-SHA256 không khớp"

    return True, "ok"


def trigger_uvicorn_reload(config_path: Path = DEFAULT_CONFIG_PATH) -> bool:
    """Chạm timestamp của `app/config.py` để kích hoạt `uvicorn --reload` nạp lại `.env`."""
    if not config_path.exists():
        return False
    os.utime(config_path, None)
    return True


def verify_endpoint_live(base_url: str, api_key: str = "vllm", timeout: float = 8.0) -> Tuple[bool, List[str]]:
    """Kiểm tra `<base_url>/models` trả HTTP 200 và đọc danh sách model đang phục vụ."""
    models_url = f"{base_url.rstrip('/')}/models"
    req = urllib.request.Request(
        models_url,
        headers={
            "Authorization": f"Bearer {api_key or 'vllm'}",
            "User-Agent": "Mozilla/5.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return False, []
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
            ids = [str(item.get("id")) for item in (body.get("data") or []) if item.get("id")]
            return True, ids
    except Exception:
        return False, []


def _apply_verified_update(
    env_path: Path,
    url: str,
    model: str,
    *,
    skip_health_check: bool = False,
) -> bool:
    env_cur = read_env_dict(env_path)
    api_key = env_cur.get("OPENAI_API_KEY", "vllm")
    if not skip_health_check:
        ok_live, live_models = verify_endpoint_live(url, api_key=api_key)
        if not ok_live:
            print(f"[Sync] Cảnh báo: {url}/models chưa phản hồi HTTP 200 (có thể tunnel vừa đóng hoặc DNS mới).")
            return False
        if live_models and model not in live_models:
            print(f"[Sync] Lưu ý: model '{model}' chưa thấy trong {live_models}; ưu tiên '{live_models[-1]}'.")
            model = live_models[-1]

    old = upsert_env_vars(env_path, {"LLM_BASE_URL": url, "LLM_MODEL_NAME": model})
    reloaded = trigger_uvicorn_reload()
    print(f"[Sync] Đã cập nhật {env_path}:")
    print(f"       LLM_BASE_URL   : {old.get('LLM_BASE_URL')} -> {url}")
    print(f"       LLM_MODEL_NAME : {old.get('LLM_MODEL_NAME')} -> {model}")
    if reloaded:
        print(f"[Sync] Đã chạm {DEFAULT_CONFIG_PATH.name} để kích hoạt uvicorn --reload.")
    return True


def cmd_init(env_path: Path) -> int:
    env_cur = read_env_dict(env_path)
    topic = env_cur.get("KAGGLE_SYNC_TOPIC") or f"rag-vllm-{secrets.token_hex(10)}"
    secret = env_cur.get("KAGGLE_SYNC_SECRET") or secrets.token_hex(24)

    updates: Dict[str, str] = {}
    if not env_cur.get("KAGGLE_SYNC_TOPIC"):
        updates["KAGGLE_SYNC_TOPIC"] = topic
    if not env_cur.get("KAGGLE_SYNC_SECRET"):
        updates["KAGGLE_SYNC_SECRET"] = secret
    if updates:
        upsert_env_vars(env_path, updates)

    print("[Init] Khóa đồng bộ Kaggle <-> Local `.env` đã sẵn sàng:")
    print(f"  KAGGLE_SYNC_TOPIC  = {topic}")
    print(f"  KAGGLE_SYNC_SECRET = {secret}")
    print("\nBước tiếp theo trên Kaggle Notebook:")
    print("  1. Vào Add-ons -> Secrets trên Kaggle và thêm đúng 2 khóa trên (KAGGLE_SYNC_TOPIC, KAGGLE_SYNC_SECRET).")
    print("  2. Gắn thêm input từ Kaggle Output `paulsean1402/in-course-rag-qwen25-qlora-ft` để tự nạp LoRA Socratic.")
    print("  3. Chạy nội dung `scripts/kaggle_jobs/serve_qwen25_vllm_kaggle.py` trên Kaggle GPU T4 x2.")
    print("  4. Ở máy local, chạy `--watch` để tự cập nhật `.env` và reload `uvicorn --reload` mỗi lần Kaggle khởi động.")
    return 0


def _decode_ntfy_line(line: str) -> Optional[Dict[str, Any]]:
    try:
        envelope = json.loads(line)
    except Exception:
        return None
    if envelope.get("event") != "message":
        return None
    msg_raw = envelope.get("message")
    if not msg_raw:
        return None
    try:
        return json.loads(msg_raw) if isinstance(msg_raw, str) else dict(msg_raw)
    except Exception:
        return None


def cmd_poll_once(env_path: Path, since: str = "12h", skip_health_check: bool = False) -> int:
    env_cur = read_env_dict(env_path)
    topic = env_cur.get("KAGGLE_SYNC_TOPIC", "").strip()
    secret = env_cur.get("KAGGLE_SYNC_SECRET", "").strip()
    if not topic or not secret:
        print("[Lỗi] Thiếu KAGGLE_SYNC_TOPIC hoặc KAGGLE_SYNC_SECRET trong `.env`. Hãy chạy `--init` trước.")
        return 1

    poll_url = f"https://ntfy.sh/{urllib.parse.quote(topic)}/json?poll=1&since={urllib.parse.quote(since)}"
    req = urllib.request.Request(poll_url, headers={"User-Agent": "InCourseRAGSync/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw_lines = resp.read().decode("utf-8", errors="replace").splitlines()
    except Exception as err:
        print(f"[Lỗi] Không thể đọc kênh đồng bộ {poll_url}: {err}")
        return 1

    valid_payloads: List[Dict[str, Any]] = []
    for ln in raw_lines:
        if not ln.strip():
            continue
        p = _decode_ntfy_line(ln)
        if not p:
            continue
        ok, _ = verify_sync_payload(p, secret)
        if ok:
            valid_payloads.append(p)

    if not valid_payloads:
        print(f"[Sync] Chưa có tín hiệu Kaggle hợp lệ nào trong {since} gần nhất trên kênh `{topic}`.")
        return 1

    newest = max(valid_payloads, key=lambda x: int(x.get("ts", 0)))
    applied = _apply_verified_update(
        env_path,
        newest["url"],
        newest["model"],
        skip_health_check=skip_health_check,
    )
    return 0 if applied else 2


def cmd_watch(env_path: Path, skip_health_check: bool = False) -> int:
    env_cur = read_env_dict(env_path)
    topic = env_cur.get("KAGGLE_SYNC_TOPIC", "").strip()
    secret = env_cur.get("KAGGLE_SYNC_SECRET", "").strip()
    if not topic or not secret:
        print("[Lỗi] Thiếu KAGGLE_SYNC_TOPIC hoặc KAGGLE_SYNC_SECRET trong `.env`. Hãy chạy `--init` trước.")
        return 1

    stream_url = f"https://ntfy.sh/{urllib.parse.quote(topic)}/json?since=10m"
    print(f"[Watch] Đang lắng nghe tự động kênh `{topic}` -> cập nhật `{env_path.name}` & kích hoạt uvicorn --reload...")
    print("        Nhấn Ctrl+C để dừng.")
    last_applied: Optional[Tuple[str, str, int]] = None

    while True:
        try:
            req = urllib.request.Request(stream_url, headers={"User-Agent": "InCourseRAGSync/1.0"})
            with urllib.request.urlopen(req, timeout=90) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    payload = _decode_ntfy_line(line)
                    if not payload:
                        continue
                    ok, reason = verify_sync_payload(payload, secret)
                    if not ok:
                        print(f"[Watch] Bỏ qua gói tin không hợp lệ: {reason}")
                        continue
                    key = (payload["url"], payload["model"], int(payload["ts"]))
                    if key == last_applied:
                        continue
                    if _apply_verified_update(
                        env_path,
                        payload["url"],
                        payload["model"],
                        skip_health_check=skip_health_check,
                    ):
                        last_applied = key
        except KeyboardInterrupt:
            print("\n[Watch] Đã dừng lắng nghe.")
            return 0
        except Exception as err:
            print(f"[Watch] Mất kết nối stream ({err}), thử kết nối lại sau 5s...")
            time.sleep(5)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto-sync Kaggle vLLM Cloudflare URL -> local `.env`")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_PATH, help="Đường dẫn tới tệp .env cục bộ")
    parser.add_argument("--init", action="store_true", help="Khởi tạo KAGGLE_SYNC_TOPIC & KAGGLE_SYNC_SECRET trong .env")
    parser.add_argument("--watch", action="store_true", help="Chạy nền nghe liên tục và tự động reload uvicorn")
    parser.add_argument("--once", action="store_true", help="Lấy URL hợp lệ mới nhất 1 lần rồi thoát (mặc định)")
    parser.add_argument("--since", type=str, default="12h", help="Khoảng thời gian tìm gói tin cho --once (vd: 1h, 12h)")
    parser.add_argument("--url", type=str, default=None, help="Cập nhật thủ công 1 URL https://.../v1 trực tiếp vào .env")
    parser.add_argument("--model", type=str, default=None, help="Ghi kèm LLM_MODEL_NAME khi dùng --url")
    parser.add_argument("--skip-health-check", action="store_true", help="Bỏ qua kiểm tra GET /v1/models trước khi ghi .env")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.init:
        return cmd_init(args.env_file)
    if args.url:
        clean_url = args.url.strip().rstrip("/")
        if not clean_url.endswith("/v1"):
            clean_url = f"{clean_url}/v1"
        env_cur = read_env_dict(args.env_file)
        model = (args.model or env_cur.get("LLM_MODEL_NAME") or "socratic-lora").strip()
        ok = _apply_verified_update(args.env_file, clean_url, model, skip_health_check=args.skip_health_check)
        return 0 if ok else 2
    if args.watch:
        return cmd_watch(args.env_file, skip_health_check=args.skip_health_check)
    return cmd_poll_once(args.env_file, since=args.since, skip_health_check=args.skip_health_check)


if __name__ == "__main__":
    raise SystemExit(main())
