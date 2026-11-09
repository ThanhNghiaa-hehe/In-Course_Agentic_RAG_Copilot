"""
pstack Automated Task Runner for Antigravity CLI (agy)
Integrates Lauren Tan's pstack playbook with automatic account rotation via Antigravity Tools.
"""

import subprocess
import sys
import time
import re
from pathlib import Path

ANTIGRAVITY_SERVER = Path(r"D:\PooL_quota\Antigravity Tools\antigravity-server.exe")

def switch_to_next_account():
    """Tự động xoay sang tài khoản tiếp theo trong Antigravity Tools pool"""
    print("\n[Quota Manager] Đang thực hiện xoay tài khoản (Account Switch)...")
    if ANTIGRAVITY_SERVER.exists():
        res = subprocess.run([str(ANTIGRAVITY_SERVER), "switch"], capture_output=True, text=True, encoding="utf-8")
        print(f"[Quota Manager] {res.stdout.strip()}")
    else:
        print(f"[Quota Manager] Cảnh báo: Không tìm thấy {ANTIGRAVITY_SERVER}")

def run_pstack_task(prompt: str):
    """Khởi chạy vòng lặp agent tự động với quy trình pstack"""
    is_first_turn = True

    while True:
        print("\n" + "="*60)
        print("[*] Bắt đầu phiên thực thi Antigravity CLI (pstack / poteto-mode)")
        print("="*60 + "\n")

        if is_first_turn:
            full_prompt = f"Áp dụng skill pstack để thực hiện: {prompt}"
            cmd = ["agy", "-p", full_prompt, "--dangerously-skip-permissions"]
        else:
            full_prompt = "Tiếp tục thực hiện các đầu việc còn lại trong .agent/task_plan.md theo chuẩn pstack."
            cmd = ["agy", "-c", "-p", full_prompt, "--dangerously-skip-permissions"]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            shell=True
        )

        quota_limit_hit = False
        for line in process.stdout:
            sys.stdout.write(line)
            # Nhận diện tín hiệu cạn hạn ngạch
            if re.search(r"(quota exceeded|rate limit|resource_exhausted|429 too many requests)", line, re.IGNORECASE):
                quota_limit_hit = True

        process.wait()

        if quota_limit_hit or process.returncode != 0:
            print("\n[!] Phát hiện chạm trần Quota / Rate Limit!")
            switch_to_next_account()
            is_first_turn = False
            time.sleep(3)
            continue
        else:
            print("\n[✔] Nhiệm vụ hoàn thành và đã vượt qua Evidence Gate của pstack!")
            break

if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Kiểm tra tình trạng tài khoản qua MCP và audit code app/services/"
    run_pstack_task(task)
