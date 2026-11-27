#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Kaggle GPU Serving Script: vLLM (Prefix Caching) + Socratic LoRA Auto-Attach
+ Cloudflare Signed Broadcast.
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Cách dùng trên Kaggle Notebook:
1. Gắn Dataset/Kernel Output chứa LoRA adapter
   (ví dụ: `paulsean1402/in-course-rag-qwen25-qlora-ft`).
2. Trong Kaggle Add-ons -> Secrets, thêm:
   - `KAGGLE_SYNC_TOPIC`  (từ `python scripts/sync_kaggle_llm_env.py --init`)
   - `KAGGLE_SYNC_SECRET` (từ `python scripts/sync_kaggle_llm_env.py --init`)
   - (Tùy chọn) `HF_TOKEN`
3. Dán toàn bộ script này vào 1 cell trên Kaggle GPU (T4 x2) và chạy.
"""

import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Optional

MODEL_NAME = os.environ.get(
    "BASE_QWEN_MODEL",
    "Qwen/Qwen2.5-Coder-7B-Instruct",
)
LORA_ALIAS = "socratic-lora"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "vllm")
PORT = int(os.environ.get("VLLM_PORT", "8000"))


def format_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def get_kaggle_or_env_secret(name: str, default: str = "") -> str:
    val = os.environ.get(name, "").strip()
    if val:
        return val
    try:
        from kaggle_secrets import UserSecretsClient

        sec = UserSecretsClient().get_secret(name)
        return str(sec or "").strip()
    except Exception:
        return default


def find_and_prepare_lora_adapter(
    input_root: Path = Path("/kaggle/input"),
    extract_dir: Path = Path("/kaggle/working/socratic_lora"),
) -> Optional[Path]:
    """
    Tự động tìm Socratic LoRA adapter trong `/kaggle/input` theo 2 dạng:
    1) Đã giải nén sẵn (`adapter_config.json`)
    2) Nén trong `model_bundle.zip` chứa `adapter_config.json` -> tự giải nén
       ra `extract_dir`.
    """
    if not input_root.exists():
        return None

    def _priority_key(p: Path) -> tuple[int, str]:
        low = str(p).lower()
        score = 0
        if "qwen" in low or "socratic" in low or "qlora" in low:
            score -= 2
        if "lora" in low:
            score -= 1
        return (score, str(p))

    direct_configs = sorted(
        input_root.rglob("adapter_config.json"),
        key=_priority_key,
    )
    for cfg in direct_configs:
        return cfg.parent

    zip_candidates = sorted(
        input_root.rglob("model_bundle.zip"),
        key=_priority_key,
    )
    for zpath in zip_candidates:
        try:
            with zipfile.ZipFile(zpath, "r") as zf:
                names = zf.namelist()
                has_cfg = any(
                    n == "adapter_config.json"
                    or n.endswith("/adapter_config.json")
                    for n in names
                )
                if not has_cfg:
                    continue
                if extract_dir.exists():
                    shutil.rmtree(extract_dir, ignore_errors=True)
                extract_dir.mkdir(parents=True, exist_ok=True)
                zf.extractall(extract_dir)
                nested_cfgs = list(
                    extract_dir.rglob("adapter_config.json")
                )
                if nested_cfgs:
                    return nested_cfgs[0].parent
        except Exception as err:
            print(f"   [!] Bỏ qua file zip không hợp lệ {zpath}: {err}")

    return None


def sign_and_broadcast_tunnel_url(
    public_url: str,
    served_model: str,
    sync_topic: str,
    sync_secret: str,
) -> bool:
    """
    Ký HMAC-SHA256 và đẩy URL Cloudflare `/v1` lên kênh đồng bộ ntfy.sh
    riêng tư.
    """
    import requests

    if not sync_topic or not sync_secret:
        print(
            "   [i] Chưa cấu hình KAGGLE_SYNC_TOPIC/KAGGLE_SYNC_SECRET"
            " — bỏ qua tự động đồng bộ .env."
        )
        return False

    ts = int(time.time())
    full_v1_url = f"{public_url.rstrip('/')}/v1"
    msg = f"{full_v1_url}|{served_model}|{ts}".encode("utf-8")
    sig = hmac.new(
        sync_secret.encode("utf-8"),
        msg,
        hashlib.sha256,
    ).hexdigest()
    payload = {
        "url": full_v1_url,
        "model": served_model,
        "ts": ts,
        "sig": sig,
    }
    try:
        resp = requests.post(
            f"https://ntfy.sh/{sync_topic}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Title": "kaggle-vllm-url",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        resp.raise_for_status()
        print(
            f"   [✔] Đã phát URL ký HMAC tới kênh '{sync_topic}' "
            f"(HTTPS -> {full_v1_url})."
        )
        return True
    except Exception as err:
        print(
            f"   [!] Không thể phát URL đồng bộ tự động ({err}). "
            "Vẫn có thể copy thủ công bên dưới."
        )
        return False


def main() -> None:
    import requests

    hf_token = get_kaggle_or_env_secret("HF_TOKEN")
    sync_topic = get_kaggle_or_env_secret("KAGGLE_SYNC_TOPIC")
    sync_secret = get_kaggle_or_env_secret("KAGGLE_SYNC_SECRET")

    print("=" * 70)
    print(
        "🚀 IN-COURSE AGENTIC RAG COPILOT — "
        "vLLM + SOCRATIC LORA + CLOUDFLARE"
    )
    print("=" * 70)

    # GIAI ĐOẠN 1: DỌN DẸP TIẾN TRÌNH & CÀI ĐẶT THƯ VIỆN + CLOUDFLARED
    print(
        f"\n[Giai đoạn 1/6] Dọn dẹp cổng {PORT}, "
        "cài vLLM và tải cloudflared..."
    )
    os.system(f"fuser -k {PORT}/tcp > /dev/null 2>&1")
    os.system("pkill -9 -f vllm > /dev/null 2>&1")
    os.system("pkill -9 -f cloudflared > /dev/null 2>&1")

    pip_start = time.time()
    print("   ⏳ Đang cài đặt vllm, huggingface_hub qua pip...")
    pip_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-q",
            "-U",
            "vllm",
            "huggingface_hub",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    while pip_proc.poll() is None:
        time.sleep(2)
        elapsed = format_time(time.time() - pip_start)
        print(
            f"\r   ⏳ Đang cài đặt gói thư viện... [{elapsed}]",
            end="",
            flush=True,
        )

    cf_url = (
        "https://github.com/cloudflare/cloudflared/"
        "releases/latest/download/cloudflared-linux-amd64"
    )
    subprocess.run(
        ["wget", "-q", cf_url, "-O", "/tmp/cloudflared"],
        check=False,
    )
    subprocess.run(["chmod", "+x", "/tmp/cloudflared"], check=False)
    pip_secs = int(time.time() - pip_start)
    print(
        f"\r   [✔] Hoàn tất cài vLLM & cloudflared trong {pip_secs} giây!"
        "        \n"
    )

    import torch
    from huggingface_hub import login, logout

    os.environ.pop("HF_TOKEN", None)
    os.environ.pop("HUGGING_FACE_HUB_TOKEN", None)
    if hf_token.startswith("hf_"):
        try:
            login(token=hf_token, add_to_git_credential=False)
            os.environ["HF_TOKEN"] = hf_token
            os.environ["HUGGING_FACE_HUB_TOKEN"] = hf_token
            print("   [✔] Đăng nhập Hugging Face thành công.")
        except Exception as hf_err:
            os.environ.pop("HF_TOKEN", None)
            os.environ.pop("HUGGING_FACE_HUB_TOKEN", None)
            try:
                logout()
            except Exception:
                pass
            print(
                f"   [!] HF_TOKEN không hợp lệ ({hf_err}) -> "
                "tự chuyển sang chế độ public."
            )
    else:
        try:
            logout()
        except Exception:
            pass
        print("   [i] Bỏ qua HF login (dùng chế độ public).")

    # GIAI ĐOẠN 2: KIỂM TOÁN PHẦN CỨNG & TỰ ĐỘNG NẠP SOCRATIC LORA
    print(
        "[Giai đoạn 2/6] Kiểm tra GPU Kaggle & "
        "tìm Socratic LoRA Adapter..."
    )
    num_gpus = torch.cuda.device_count()
    if num_gpus == 0:
        print(
            "   [!] CẢNH BÁO: Không tìm thấy GPU! "
            "Hãy chọn Accelerator là GPU T4 trong Settings."
        )
        sys.exit(1)

    gpu_name = torch.cuda.get_device_name(0)
    total_vram = (
        torch.cuda.get_device_properties(0).total_memory / (1024**3)
    )
    tp_size = 2 if num_gpus >= 2 else 1
    max_model_len = 8192 if tp_size == 2 else 4096

    lora_dir = find_and_prepare_lora_adapter()
    served_model_name = LORA_ALIAS if lora_dir else MODEL_NAME

    print(
        f"   [✔] Phát hiện: {num_gpus}x {gpu_name} "
        f"(Tổng VRAM: {total_vram:.1f} GB / GPU)"
    )
    print(
        f"   [✔] Tối ưu: TP={tp_size} | Max-Context={max_model_len} | "
        "Prefix-Caching=ON | Chunked-Prefill=ON"
    )
    if lora_dir:
        print(
            f"   [✔] Đã chuẩn bị LoRA Adapter: {lora_dir} "
            f"(served model: {served_model_name})"
        )
    else:
        print(
            "   [i] Không thấy LoRA trong /kaggle/input -> "
            f"chạy model gốc: {served_model_name}"
        )

    # GIAI ĐOẠN 3: KHỞI ĐỘNG vLLM (PREFIX CACHING + LORA NẾU CÓ)
    print(
        "\n[Giai đoạn 3/6] Khởi động vLLM Server & "
        f"Tải mô hình {served_model_name}..."
    )
    print("   (Log khởi tạo sẽ hiển thị bên dưới)\n" + "-" * 70)

    vllm_cmd = [
        sys.executable,
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--model",
        MODEL_NAME,
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
        "--dtype",
        "float16",
        "--max-model-len",
        str(max_model_len),
        "--gpu-memory-utilization",
        "0.90",
        "--tensor-parallel-size",
        str(tp_size),
        "--enable-prefix-caching",
        "--enable-chunked-prefill",
        "--max-num-batched-tokens",
        "2048",
        "--trust-remote-code",
        "--api-key",
        OPENAI_API_KEY,
        "--disable-log-requests",
    ]
    if lora_dir:
        vllm_cmd.extend(
            [
                "--enable-lora",
                "--max-lora-rank",
                "16",
                "--lora-modules",
                f"{LORA_ALIAS}={lora_dir}",
            ]
        )

    log_filename = "vllm_server.log"
    log_write = open(log_filename, "w", encoding="utf-8")
    vllm_proc = subprocess.Popen(
        vllm_cmd,
        stdout=log_write,
        stderr=subprocess.STDOUT,
    )
    log_read = open(
        log_filename,
        "r",
        encoding="utf-8",
        errors="replace",
    )

    start_init = time.time()
    server_ready = False

    while time.time() - start_init < 600:
        new_line = log_read.readline()
        if new_line:
            line_clean = new_line.strip()
            if line_clean:
                ts_fmt = format_time(time.time() - start_init)
                print(f"[{ts_fmt}] {line_clean}")
        else:
            if vllm_proc.poll() is not None:
                print(
                    "\n[!] LỖI: vLLM Server đã dừng đột ngột. "
                    "Kiểm tra log phía trên."
                )
                sys.exit(1)
            try:
                health_url = f"http://127.0.0.1:{PORT}/health"
                res = requests.get(health_url, timeout=1)
                if res.status_code == 200:
                    server_ready = True
                    break
            except Exception:
                pass
            time.sleep(0.5)

    if not server_ready:
        print("\n[!] Timeout chờ vLLM khởi động.")
        vllm_proc.terminate()
        sys.exit(1)

    print("-" * 70)
    load_secs = int(time.time() - start_init)
    print(f"   [✔] vLLM Server sẵn sàng! (Thời gian nạp: {load_secs}s)")

    # GIAI ĐOẠN 4: MỞ CLOUDFLARE QUICK TUNNEL
    print("\n[Giai đoạn 4/6] Đang mở Cloudflare Quick Tunnel...")
    cf_proc = subprocess.Popen(
        [
            "/tmp/cloudflared",
            "tunnel",
            "--no-autoupdate",
            "--url",
            f"http://127.0.0.1:{PORT}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    public_url = None
    cf_start = time.time()
    while time.time() - cf_start < 30:
        line = cf_proc.stdout.readline() if cf_proc.stdout else ""
        if not line:
            break
        m = re.search(
            r"https://[a-zA-Z0-9-]+\.trycloudflare\.com",
            line,
        )
        if m:
            public_url = m.group(0)
            break

    if not public_url:
        print("   [!] Không lấy được URL Cloudflare trong 30s.")
        vllm_proc.terminate()
        cf_proc.terminate()
        sys.exit(1)

    print(f"   [✔] CLOUDFLARE TUNNEL ĐÃ KẾT NỐI: {public_url}")

    # GIAI ĐOẠN 5: ĐỒNG BỘ URL KÝ HMAC TỚI .ENV LOCAL
    print(
        "\n[Giai đoạn 5/6] Phát tín hiệu đồng bộ URL "
        "tự động về máy local..."
    )
    sign_and_broadcast_tunnel_url(
        public_url,
        served_model_name,
        sync_topic,
        sync_secret,
    )

    # GIAI ĐOẠN 6: KIỂM THỬ STREAMING TTFT QUA TUNNEL
    print(
        "\n[Giai đoạn 6/6] Đo kiểm chứng TTFT Streaming qua Cloudflare..."
    )
    time.sleep(2)
    smoke_start = time.time()
    ttft_ms = None
    chunks_text = []
    try:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        messages = [
            {
                "role": "system",
                "content": "Bạn là trợ giảng C++ theo phương pháp Socratic.",
            },
            {
                "role": "user",
                "content": "Giải thích ngắn gọn kiểu int trong C++.",
            },
        ]
        with requests.post(
            f"{public_url}/v1/chat/completions",
            headers=headers,
            json={
                "model": served_model_name,
                "messages": messages,
                "max_tokens": 60,
                "temperature": 0.2,
                "stream": True,
            },
            stream=True,
            timeout=30,
        ) as resp:
            resp.raise_for_status()
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line or not raw_line.startswith("data: "):
                    continue
                payload = raw_line[6:].strip()
                if payload == "[DONE]":
                    break
                choice = json.loads(payload)["choices"][0]
                delta = choice["delta"].get("content", "")
                if delta:
                    if ttft_ms is None:
                        ttft_ms = int((time.time() - smoke_start) * 1000)
                    chunks_text.append(delta)
        total_ms = int((time.time() - smoke_start) * 1000)
        print(
            f"   [✔] Cloudflare Streaming OK | "
            f"TTFT: {ttft_ms} ms | Total: {total_ms} ms"
        )
        print(f"   [✔] Output: \"{''.join(chunks_text).strip()}\"")
    except Exception as test_err:
        print(
            "   [!] Kiểm thử qua Cloudflare bị lỗi "
            f"(có thể DNS mới chưa propagate hết): {test_err}"
        )

    print("\n" + "=" * 70)
    print("🎉 HỆ THỐNG PHỤC VỤ ĐÃ SẴN SÀNG!")
    print(f"👉 LLM_BASE_URL={public_url}/v1")
    print(f"👉 LLM_MODEL_NAME={served_model_name}")
    print("=" * 70)
    print(
        "📌 Giữ nguyên cell chạy nền để duy trì kết nối. "
        "Không bấm Stop!"
    )

    try:
        while True:
            time.sleep(30)
    except KeyboardInterrupt:
        print("\nĐang tắt máy chủ...")
        cf_proc.terminate()
        vllm_proc.terminate()
        log_read.close()
        log_write.close()


if __name__ == "__main__":
    main()
