"""
Dual-Mastermind & Multi-Subagent Automated Pipeline (pstack Standards)
Dự án: In-Course Agentic RAG Copilot - Tác giả: Trần Thành Nghĩa (HUFLIT)

Kiến trúc Phối Hợp Đa Tác Nhân Khép Kín (Self-Iterative Optimization Loop - Zero Argon):
  1. POOL ĐẦU NÃO (Brain Pool: thanhnghiat42@gmail.com & thanhnghiaa1402@gmail.com):
     - Thinker (`rag-architect` & `solution-analyst`):
       Ưu tiên `gemini-4-neon-high` qua cả 2 account (`thanhnghiat42` -> `thanhnghiaa1402`);
       nếu cả 2 cạn Neon mới hạ sang `gemini-4-carbon-high` trên 2 account này.
       (Bật `--prefer-claude` để thử `claude-opus-5-5-high` / `claude-sonnet-5-5-high` trước).
     - Auditor (`codebase-auditor`):
       `gemini-4-carbon-high` trên `thanhnghiat42` -> `thanhnghiaa1402`, dự phòng `gemini-4-neon-high`.
  2. POOL THỰC THI & THẨM ĐỊNH (Exec Pool: seanpaul1402@gmail.com, dự phòng tranthehuy23@gmail.com):
     - Coder (`core-coder`): `gemini-4-hydrogen-high` (dự phòng `gemini-4-hydrogen-medium`).
     - Verifier (`grounding-evaluator` / `qa-tester`): `gemini-4-hydrogen-high` (hoặc `--light-verifier` dùng `gemini-3.8-flash-high`).
     - Scribe (`academic-scribe`): `gemini-4-hydrogen-high` (dự phòng `gemini-3.8-flash-high`).
Tự động chuyển đúng tài khoản theo vai trò qua `antigravity-server.exe switch <email>` (KHÔNG xoay vòng mù).
"""

import subprocess
import sys
import os
import time
import re
import json
import shutil
import argparse
from pathlib import Path

# Đường dẫn quản lý Quota trên máy bạn
ANTIGRAVITY_SERVER = Path(r"D:\PooL_quota\Antigravity Tools\antigravity-server.exe")

BRAIN_ACCOUNTS = ("thanhnghiat42@gmail.com", "thanhnghiaa1402@gmail.com")
EXEC_ACCOUNTS = ("seanpaul1402@gmail.com", "tranthehuy23@gmail.com")

# BẢNG ÁNH XẠ MÔ HÌNH THEO VAI TRÒ & ĐÚNG POOL TÀI KHOẢN (0% Argon, Model-First Across Scoped Accounts)
ROLE_ROUTING_PLANS = {
    "thinker": [
        ("gemini-4-neon-high", "thanhnghiat42@gmail.com"),
        ("gemini-4-neon-high", "thanhnghiaa1402@gmail.com"),
        ("gemini-4-carbon-high", "thanhnghiat42@gmail.com"),
        ("gemini-4-carbon-high", "thanhnghiaa1402@gmail.com"),
    ],
    "auditor": [
        ("gemini-4-carbon-high", "thanhnghiat42@gmail.com"),
        ("gemini-4-carbon-high", "thanhnghiaa1402@gmail.com"),
        ("gemini-4-neon-high", "thanhnghiat42@gmail.com"),
        ("gemini-4-neon-high", "thanhnghiaa1402@gmail.com"),
    ],
    "coder": [
        ("gemini-4-hydrogen-high", "seanpaul1402@gmail.com"),
        ("gemini-4-hydrogen-high", "tranthehuy23@gmail.com"),
        ("gemini-4-hydrogen-medium", "seanpaul1402@gmail.com"),
        ("gemini-4-hydrogen-medium", "tranthehuy23@gmail.com"),
    ],
    "verifier": [
        ("gemini-4-hydrogen-high", "seanpaul1402@gmail.com"),
        ("gemini-4-hydrogen-high", "tranthehuy23@gmail.com"),
        ("gemini-4-hydrogen-medium", "seanpaul1402@gmail.com"),
        ("gemini-3.8-flash-high", "seanpaul1402@gmail.com"),
        ("gemini-3.8-flash-high", "tranthehuy23@gmail.com"),
    ],
    "verifier_runner": [
        ("gemini-3.8-flash-high", "seanpaul1402@gmail.com"),
        ("gemini-3.8-flash-high", "tranthehuy23@gmail.com"),
        ("gemini-4-hydrogen-high", "seanpaul1402@gmail.com"),
    ],
    "scribe": [
        ("gemini-4-hydrogen-high", "seanpaul1402@gmail.com"),
        ("gemini-4-hydrogen-high", "tranthehuy23@gmail.com"),
        ("gemini-3.8-flash-high", "seanpaul1402@gmail.com"),
        ("gemini-3.8-flash-high", "tranthehuy23@gmail.com"),
    ],
}

CLAUDE_BRAIN_PREFIX = {
    "thinker": [
        ("claude-opus-5-5-high", "thanhnghiat42@gmail.com"),
        ("claude-opus-5-5-high", "thanhnghiaa1402@gmail.com"),
        ("claude-sonnet-5-5-high", "thanhnghiat42@gmail.com"),
        ("claude-sonnet-5-5-high", "thanhnghiaa1402@gmail.com"),
    ],
    "auditor": [
        ("claude-sonnet-5-5-high", "thanhnghiat42@gmail.com"),
        ("claude-sonnet-5-5-high", "thanhnghiaa1402@gmail.com"),
        ("claude-opus-5-5-high", "thanhnghiat42@gmail.com"),
        ("claude-opus-5-5-high", "thanhnghiaa1402@gmail.com"),
    ],
}

# Tương thích ngược cho các module khác tham chiếu profile/fallback (0% Argon)
ACCOUNT_MODEL_PROFILES = {
    "thanhnghiat42@gmail.com": {
        "auditor":  "gemini-4-carbon-high",
        "thinker":  "gemini-4-neon-high",
        "coder":    "gemini-4-hydrogen-high",
        "verifier": "gemini-4-hydrogen-high",
        "scribe":   "gemini-4-hydrogen-high",
    },
    "thanhnghiaa1402@gmail.com": {
        "auditor":  "gemini-4-carbon-high",
        "thinker":  "gemini-4-neon-high",
        "coder":    "gemini-4-hydrogen-high",
        "verifier": "gemini-4-hydrogen-high",
        "scribe":   "gemini-4-hydrogen-high",
    },
    "seanpaul1402@gmail.com": {
        "auditor":  "gemini-4-hydrogen-high",
        "thinker":  "gemini-4-hydrogen-high",
        "coder":    "gemini-4-hydrogen-high",
        "verifier": "gemini-4-hydrogen-high",
        "scribe":   "gemini-4-hydrogen-high",
    },
    "tranthehuy23@gmail.com": {
        "auditor":  "gemini-4-hydrogen-high",
        "thinker":  "gemini-4-hydrogen-high",
        "coder":    "gemini-4-hydrogen-high",
        "verifier": "gemini-4-hydrogen-high",
        "scribe":   "gemini-4-hydrogen-high",
    },
}

MODEL_FALLBACK_CHAINS = {
    "gemini-4-neon-high":        ["gemini-4-carbon-high", "gemini-4-hydrogen-high", "gemini-3.8-flash-high"],
    "gemini-4-neon-xhigh":       ["gemini-4-neon-high", "gemini-4-carbon-high", "gemini-4-hydrogen-high"],
    "gemini-4-carbon-high":      ["gemini-4-neon-high", "gemini-4-hydrogen-high", "gemini-3.8-flash-high"],
    "gemini-4-carbon-medium":    ["gemini-4-hydrogen-medium", "gemini-3.8-flash-high"],
    "gemini-4-hydrogen-high":    ["gemini-4-hydrogen-medium", "gemini-3.8-flash-high"],
    "gemini-4-hydrogen-xhigh":   ["gemini-4-hydrogen-high", "gemini-4-hydrogen-medium", "gemini-3.8-flash-high"],
    "gemini-4-hydrogen-medium":  ["gemini-3.8-flash-high", "gemini-4-hydrogen-low"],
    "claude-opus-5-5-high":      ["claude-sonnet-5-5-high", "gemini-4-neon-high", "gemini-4-carbon-high"],
    "claude-sonnet-5-5-high":    ["gemini-4-carbon-high", "gemini-4-neon-high", "gemini-4-hydrogen-high"],
    "claude-sonnet-5-5-medium":  ["gemini-4-carbon-medium", "gemini-4-hydrogen-medium", "gemini-3.8-flash-high"],
    "claude-opus-4-6-thinking":  ["gemini-4-hydrogen-high", "claude-sonnet-4-6", "gemini-3.8-flash-high"],
    "claude-sonnet-4-6":         ["gemini-4-hydrogen-high", "gemini-3.8-flash-high"],
    "gemini-3.8-flash-high":     ["gemini-4-hydrogen-medium", "gemini-3.8-flash-medium"],
    "gemini-3.8-flash-medium":   ["gemini-3.8-flash-low"],
}

DEFAULT_PROFILE = {
    "thinker":  "gemini-4-neon-high",
    "auditor":  "gemini-4-carbon-high",
    "coder":    "gemini-4-hydrogen-high",
    "verifier": "gemini-4-hydrogen-high",
    "scribe":   "gemini-4-hydrogen-high",
}


def get_role_routing_plan(
    role_key: str,
    prefer_claude: bool = False,
    light_verifier: bool = False,
) -> list[tuple[str, str]]:
    """Trả về danh sách (model_id, account_email) theo đúng thứ tự ưu tiên cho từng vai trò."""
    effective_key = "verifier_runner" if (role_key == "verifier" and light_verifier) else role_key
    plan = list(ROLE_ROUTING_PLANS.get(effective_key, ROLE_ROUTING_PLANS["verifier"]))
    if prefer_claude and role_key in CLAUDE_BRAIN_PREFIX:
        plan = list(CLAUDE_BRAIN_PREFIX[role_key]) + plan
    return plan


def get_active_account_email() -> str:
    """Truy vấn tài khoản agy CLI đang kích hoạt từ Antigravity Tools."""
    if ANTIGRAVITY_SERVER.exists():
        try:
            res = subprocess.run(
                [str(ANTIGRAVITY_SERVER), "current"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5
            )
            for line in res.stdout.splitlines():
                if "agy:" in line:
                    email = line.split("agy:")[1].strip()
                    if "@" in email:
                        return email
        except Exception:
            pass
    return "thanhnghiat42@gmail.com"


def get_available_models() -> list[str]:
    """Lấy danh sách model ID khả dụng thực tế trên tài khoản đang kích hoạt qua `agy models`."""
    agy_bin = shutil.which("agy") or "agy"
    try:
        res = subprocess.run(
            [agy_bin, "models"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15
        )
        models_found = []
        for line in res.stdout.splitlines():
            stripped = line.strip()
            if not stripped or stripped.lower().startswith("fetching"):
                continue
            model_id = stripped.split()[0]
            if "-" in model_id:
                models_found.append(model_id)
        return models_found
    except Exception:
        return []


def resolve_models_for_current_account():
    """Tự động phân giải bộ model chuẩn xác tương ứng với tài khoản đang active."""
    active_email = get_active_account_email()
    profile = ACCOUNT_MODEL_PROFILES.get(active_email, DEFAULT_PROFILE)
    print(f"[*] Tài khoản active hiện tại: {active_email}")
    print(f"[*] Bộ model tự động tương thích: Auditor={profile['auditor']} | Thinker={profile['thinker']} | Coder={profile['coder']} | Verifier={profile['verifier']}")
    return active_email, profile

# Cấu hình 24/7 Daemon & Quota Resilience
POOL_ACCOUNT_COUNT = 4      # Số tài khoản trong pool (thanhnghiat42, thanhnghiaa1402, seanpaul1402, tranthehuy23)
COOLDOWN_SLEEP_SEC = 60     # Thời gian chờ khi toàn bộ cặp (model, account) hợp lệ của vai trò đều cạn hạn mức
MAX_COOLDOWN_CYCLES = 3     # Chặn tuyệt đối vòng lặp vô tận nếu toàn bộ pool hết quota dài hạn hoặc lỗi CLI liên tiếp

QUOTA_ERROR_REGEX = re.compile(
    r"(quota exceeded|resource_exhausted|too many requests|capacity exceeded|credit balance|service unavailable|invalid model selection|individual quota reached|http\s*(?:status\s*)?(?:429|503|504)|status\s*(?:429|503|504)|error\s*(?:429|503|504))",
    re.IGNORECASE
)


def switch_to_account(target_email: str) -> bool:
    """Chuyển agy CLI sang tài khoản chỉ định qua `antigravity-server.exe switch <email>` (KHÔNG xoay vòng mù)."""
    current_email = get_active_account_email()
    if current_email == target_email:
        return True
    print(f"[Account Router] Chuyển agy CLI: {current_email} -> {target_email}")
    if ANTIGRAVITY_SERVER.exists():
        try:
            res = subprocess.run(
                [str(ANTIGRAVITY_SERVER), "switch", target_email],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10
            )
            print(f"[Account Router] {res.stdout.strip()}")
            return res.returncode == 0
        except Exception as e:
            print(f"[Account Router] Lỗi khi switch sang {target_email}: {e}")
            return False
    print(f"[Account Router] Cảnh báo: Không tìm thấy {ANTIGRAVITY_SERVER}")
    return False


def switch_quota_account():
    """Giữ tương thích ngược: xoay sang tài khoản kế tiếp khi gọi thủ công không tham số."""
    print("\n" + "!" * 75)
    print("[Quota Self-Healing] Đang thực hiện xoay tài khoản trong Antigravity Pool...")
    print("!" * 75)
    if ANTIGRAVITY_SERVER.exists():
        try:
            res = subprocess.run(
                [str(ANTIGRAVITY_SERVER), "switch"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10
            )
            print(f"[Quota Manager] {res.stdout.strip()}")
        except Exception as e:
            print(f"[Quota Manager] Lỗi khi gọi switch: {e}")
    else:
        print(f"[Quota Manager] Cảnh báo: Không tìm thấy {ANTIGRAVITY_SERVER}")


class PipelineProgressTracker:
    """
    Thanh tiến trình trực quan thời gian thực (Live Console Progress Tracker).
    Sử dụng CONOUT$ để hiển thị trực tiếp lên màn hình Console của Windows
    ngay cả khi toàn bộ stdout/stderr đang bị chuyển hướng qua file log (*> logs/overnight_loop.log).
    """
    def __init__(self, total_loops: int, total_phases: int = 4):
        self.total_loops = total_loops
        self.total_phases = total_phases
        self.current_loop = 1
        self.current_phase_idx = 1
        self.current_phase_title = ""
        self.current_role = ""
        self.current_model = ""
        self.start_time = time.time()
        self.phase_start_time = time.time()
        self._conout = None
        if os.name == "nt":
            try:
                self._conout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
            except Exception:
                self._conout = None

    def _write_console(self, text: str, newline: bool = False):
        full_text = text + ("\n" if newline else "")
        if self._conout:
            try:
                self._conout.write(full_text)
                self._conout.flush()
                return
            except Exception:
                pass
        # Fallback khi chạy tương tác không chuyển hướng file
        if hasattr(sys.stderr, "isatty") and sys.stderr.isatty():
            try:
                sys.stderr.write(full_text)
                sys.stderr.flush()
            except Exception:
                pass

    def start_loop(self, loop_idx: int):
        self.current_loop = loop_idx
        sep = "=" * 75
        msg = f"\n{sep}\n[Tracker] 🔄 VÒNG LẶP #{loop_idx}/{self.total_loops} - TỰ ĐỘNG HỘI TỤ & KIỂM CHUẨN CHẤT LƯỢNG\n{sep}\n"
        self._write_console(msg, newline=True)

    def start_phase(self, phase_idx: int, phase_title: str, role_key: str, active_model: str):
        self.current_phase_idx = phase_idx
        self.current_phase_title = phase_title
        self.current_role = role_key
        self.current_model = active_model
        self.phase_start_time = time.time()
        pct = int((phase_idx - 1) / self.total_phases * 100)
        bar_len = 16
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        header = f"\n[Tracker] [{bar}] {pct:>2}% | Khởi động: {phase_title} | Model: {active_model}\n"
        self._write_console(header, newline=True)

    def update_subagent(self, line_count: int, snippet: str = ""):
        elapsed = int(time.time() - self.phase_start_time)
        m, s = divmod(elapsed, 60)
        time_frac = min(0.85, elapsed / 600.0)
        pct = int(((self.current_phase_idx - 1) + time_frac) / self.total_phases * 100)
        bar_len = 16
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)

        snippet = snippet.strip()
        if len(snippet) > 28:
            snippet = snippet[:25] + "..."

        status_line = (
            f"\r[Tracker] [{bar}] {pct:>2}% | "
            f"L{self.current_loop} P{self.current_phase_idx}/4 | "
            f"{self.current_role.upper()[:8]} {m:02d}m{s:02d}s | "
            f"Logs: {line_count:>4} | {snippet:<28}  "
        )
        self._write_console(status_line, newline=False)

    def end_phase(self, phase_title: str, success: bool = True):
        elapsed = int(time.time() - self.phase_start_time)
        m, s = divmod(elapsed, 60)
        status = "[✔] XONG" if success else "[!] GIÁN ĐOẠN"
        pct = int(self.current_phase_idx / self.total_phases * 100)
        bar_len = 16
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        line = f"\r[Tracker] [{bar}] {pct:>2}% | {phase_title}: {status} ({m:02d}m{s:02d}s)                           \n"
        self._write_console(line, newline=True)

    def log_syntax_gate(self, errors: list):
        if not errors:
            self._write_console("[Tracker] [Fast AST Gate] [✔] 100% Cú pháp Python AST hợp lệ!\n", newline=True)
        else:
            self._write_console(f"[Tracker] [Fast AST Gate] [!] Lỗi cú pháp: {'; '.join(errors)}\n", newline=True)

    def log_gate(self, is_passed: bool, report: str):
        status = "[✔] TẤT CẢ QUALITY GATES ĐẠT CHUẨN 100%!" if is_passed else f"[!] QUALITY GATES CHƯA ĐẠT: {report}"
        self._write_console(f"\n[Tracker] [Quality Gates] {status}\n", newline=True)

    def close(self):
        if self._conout:
            try:
                self._conout.close()
            except Exception:
                pass


def execute_phase(
    phase_title: str,
    prompt: str,
    role_key: str,
    is_continue: bool = True,
    phase_idx: int = 1,
    tracker: "PipelineProgressTracker" = None,
    prefer_claude: bool = False,
    light_verifier: bool = False,
) -> bool:
    """
    Thực thi một nhịp của quy trình với cơ chế ĐỊNH TUYẾN THEO ĐÚNG POOL TÀI KHOẢN & MODEL:
    - Thinker: `gemini-4-neon-high` (`thanhnghiat42` -> `thanhnghiaa1402`) -> `gemini-4-carbon-high` (`thanhnghiat42` -> `thanhnghiaa1402`).
    - Auditor: `gemini-4-carbon-high` (`thanhnghiat42` -> `thanhnghiaa1402`) -> `gemini-4-neon-high` (`thanhnghiat42` -> `thanhnghiaa1402`).
    - Coder / Verifier / Scribe: `gemini-4-hydrogen-high` (`seanpaul1402` -> `tranthehuy23`) -> fallback nhẹ cùng pool.
    - Kiểm chứng danh sách model thực tế qua `agy models` trên đúng account vừa chuyển trước khi gọi.
    """
    attempt = 0
    cooldown_cycles = 0

    while True:
        plan = get_role_routing_plan(
            role_key,
            prefer_claude=prefer_claude,
            light_verifier=light_verifier,
        )
        for active_model, target_email in plan:
            attempt += 1
            if not switch_to_account(target_email):
                print(f"[Account Router] Bỏ qua cặp ({active_model} @ {target_email}) vì switch thất bại.")
                continue

            available_models = get_available_models()
            if available_models and active_model not in available_models:
                print(f"[Model Guard] Model '{active_model}' không khả dụng trên {target_email} -> thử cặp kế tiếp.")
                continue

            print("\n" + "=" * 75)
            print(f"[*] {phase_title.upper()} (Lần chạy #{attempt})")
            print(f"[*] Tài khoản: {target_email} | Vai trò: {role_key.upper()} | Model: {active_model}")
            print(f"[*] Chế độ: {'Nối tiếp phiên (--continue)' if is_continue else 'Khởi tạo phiên mới'}")
            print("=" * 75 + "\n")

            if tracker:
                tracker.start_phase(phase_idx, phase_title, role_key, f"{active_model}@{target_email.split('@')[0]}")

            agy_bin = shutil.which("agy") or "agy"
            cmd = [agy_bin, "--model", active_model, "--dangerously-skip-permissions"]
            if is_continue:
                cmd.append("--continue")
            cmd.extend(["--print", prompt])

            try:
                phase_timeout = 3600 if role_key == "verifier" else 1800
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    shell=False
                )

                quota_hit = False
                line_count = 0
                last_render = time.time()
                phase_start = time.time()
                for line in process.stdout:
                    line_count += 1
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    if QUOTA_ERROR_REGEX.search(line):
                        quota_hit = True
                    now = time.time()
                    if now - last_render >= 1.0:
                        clean_snip = line.strip().replace("\r", " ").replace("\n", " ")
                        if tracker:
                            tracker.update_subagent(line_count, snippet=clean_snip)
                        last_render = now
                    if (now - phase_start) > phase_timeout:
                        raise subprocess.TimeoutExpired(cmd=cmd, timeout=phase_timeout)

                process.wait(timeout=30)

                # Nếu tiến trình CLI trả exit code 0 và có output thực tế -> thành công
                # (không đánh trượt nhầm chỉ vì báo cáo kiểm toán nhắc tới "rate limit" hoặc số "429"/"503")
                if process.returncode == 0 and line_count > 0:
                    print(f"\n[✔] {phase_title} ĐÃ HOÀN TẤT THÀNH CÔNG!\n")
                    if tracker:
                        tracker.end_phase(phase_title, success=True)
                    return True

                print(f"\n[!] Nhịp gặp lỗi hạn mức hoặc gián đoạn trên ({active_model} @ {target_email}) | Exit={process.returncode}, quota_hit={quota_hit}.")
                if tracker:
                    tracker.end_phase(phase_title, success=False)
                time.sleep(2)

            except subprocess.TimeoutExpired:
                print(f"\n[Timeout Warning] Lượt chạy ({active_model} @ {target_email}) vượt quá ngưỡng timeout, chuyển cặp dự phòng...")
                process.kill()
                is_continue = True
                continue
            except KeyboardInterrupt:
                print("\n[User Cancel] Người dùng chủ động dừng pipeline (Ctrl+C).")
                return False
            except Exception as ex:
                print(f"\n[System Blip] Bắt lỗi ngoại lệ ngoại vi: {ex}. Nghỉ 5s rồi thử cặp kế tiếp...")
                time.sleep(5)
                continue

        cooldown_cycles += 1
        if cooldown_cycles >= MAX_COOLDOWN_CYCLES:
            print(f"\n[Safety Stop] Đã hết {MAX_COOLDOWN_CYCLES} chu kỳ thử toàn bộ {len(plan)} cặp (model, account) cho vai trò '{role_key}'. Dừng an toàn để tránh vòng lặp vô tận!")
            return False

        print(f"\n[24/7 Cooldown Guard] Toàn bộ {len(plan)} cặp (model, account) cho vai trò '{role_key}' đều chạm hạn mức (Chu kỳ #{cooldown_cycles}/{MAX_COOLDOWN_CYCLES}).")
        print(f"[24/7 Cooldown Guard] Tạm dừng {COOLDOWN_SLEEP_SEC} giây để cửa sổ hạn mức hồi phục...")
        for remaining in range(COOLDOWN_SLEEP_SEC, 0, -10):
            print(f"  --> Sẽ tự động kiểm tra và tiếp tục sau {remaining} giây...")
            time.sleep(10)


def _to_pct(value: float) -> float:
    """Chuẩn hóa đơn vị phần trăm (hỗ trợ cả dạng 0..1 và 0..100 từ JSON benchmark)."""
    val = float(value)
    return val * 100.0 if val <= 1.0 else val


def audit_anti_bypass_git_diff() -> list[str]:
    """
    Cổng chống qua mặt & chống Quick-Fix trên git diff:
    - Cấm thêm `import re`, literal `BENCH-`/`SESSION-`, hardcode từ khóa câu hỏi trong `app/`.
    - Cấm thêm `@pytest.mark.skip`, `pytest.skip(`, hoặc xóa/nới lỏng ngưỡng trong `tests/` & harness.
    """
    violations: list[str] = []
    try:
        diff_app = subprocess.run(["git", "diff", "app/"], capture_output=True, text=True, errors="replace").stdout
        cheat_patterns = [
            r'^\+\s*(?:import\s+re\b|from\s+re\s+import)',
            r'^\+.*(?:BENCH-\d+|SESSION-)',
            r'^\+.*if\s+["\']mảng 2 chiều["\']',
            r'^\+.*if\s+["\']con trỏ["\']',
            r'^\+.*if\s+["\']sắp xếp["\']',
            r'^\+.*if\s+.*in\s+raw_prompt\.lower\(\)\s*:\s*return',
            r'^\+\s*except\s+.*:\s*pass\b',
        ]
        for pat in cheat_patterns:
            if re.search(pat, diff_app, re.IGNORECASE | re.MULTILINE):
                violations.append(f"ZERO QUICK-FIX VIOLATION trong git diff app/: khớp pattern '{pat}'")
    except Exception as e:
        violations.append(f"Không thể kiểm tra git diff app/: {e}")

    try:
        diff_guard = subprocess.run(
            ["git", "diff", "tests/", "scripts/e2e_matrix_harness.py"],
            capture_output=True,
            text=True,
            errors="replace",
        ).stdout
        bypass_patterns = [
            r'^\+[^+].*@pytest\.mark\.skip',
            r'^\+[^+].*pytest\.skip\(',
            r'^\+[^+].*\bassert\s+True\b',
        ]
        for pat in bypass_patterns:
            if re.search(pat, diff_guard, re.IGNORECASE | re.MULTILINE):
                violations.append(f"TEST TAMPERING / BYPASS VIOLATION: khớp pattern '{pat}'")
    except Exception:
        pass

    return violations


def run_deterministic_verification_harness(
    *,
    force_eval: bool = True,
    live_llm: bool = False,
) -> tuple[int, str]:
    """
    Chạy TRỰC TIẾP bằng Python (0% qua LLM trung gian) bộ kiểm chứng Stage 1 của `master_autonomous_harness.py`:
    AST + Anti-Bypass Diff -> 11 Sequential Pytests -> E2E Matrix (M1..M8 + S1) -> Macro Benchmarks.
    Ghi log đầy đủ vào `.agent/harness_stage1_latest.log` để Verifier kiểm toán.
    """
    py_exe = str(Path(sys.executable))
    cmd = [py_exe, "scripts/master_autonomous_harness.py", "--stage", "1"]
    if force_eval:
        cmd.append("--force-eval")
    if live_llm:
        cmd.append("--live-llm")

    env = dict(os.environ)
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"

    log_path = Path(".agent/harness_stage1_latest.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    print("\n" + "=" * 75)
    print("[Deterministic Harness] ĐANG CHẠY TRỰC TIẾP STAGE 1 VERIFICATION (4 GATES)")
    print(f"[Deterministic Harness] Lệnh: {' '.join(cmd)}")
    print("=" * 75 + "\n")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        shell=False,
    )
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        lines.append(line)
    proc.wait()

    full_log = "".join(lines)
    log_path.write_text(full_log, encoding="utf-8")
    return proc.returncode, full_log


def evaluate_quality_gates(
    *,
    min_artifact_ts: float = 0.0,
    harness_exit_code: int | None = None,
    require_verdict: bool = False,
) -> tuple[bool, str]:
    """
    Kiểm toán tự động Quality Gates sau mỗi vòng lặp tối ưu:
    1. Kiểm tra exit code từ Deterministic Harness (nếu được truyền vào).
    2. Kiểm tra tính mới (mtime >= min_artifact_ts) & điểm của Multi-turn, Stage 11 Golden 200 và E2E Matrix.
    3. Kiểm tra VERDICT của Verifier (`grounding-evaluator`) trong `.agent/verification_verdict.md`.
    4. Thẩm định Git Diff phát hiện vi phạm Quick-Fix / Cheat / Test Tampering.
    """
    issues = []

    if harness_exit_code is not None and harness_exit_code != 0:
        issues.append(f"Deterministic Harness Stage 1 thất bại (exit_code={harness_exit_code})")

    # 1. Khảo thí Đa Lượt 50 sessions / 222 turns
    mt_file = Path("docs/benchmarks/multiturn_benchmark_results.json")
    if mt_file.exists():
        try:
            if min_artifact_ts > 0 and mt_file.stat().st_mtime < min_artifact_ts:
                issues.append("multiturn_benchmark_results.json là file cũ trước khi Coder sửa (không được dùng số liệu cũ)")
            with open(mt_file, "r", encoding="utf-8") as f:
                mt_data = json.load(f)
            metrics = mt_data.get("summary_metrics", {})
            intent_acc = _to_pct(metrics.get("intent_accuracy", 0.0))
            status_acc = _to_pct(metrics.get("retrieval_status_accuracy", 0.0))
            arr = _to_pct(metrics.get("arr", 0.0))
            srp = _to_pct(metrics.get("srp", 0.0))
            mean_lat = float(metrics.get("mean_latency_ms", 99999.0))

            if intent_acc < 94.0:
                issues.append(f"Multi-turn Intent Acc chưa đạt ({intent_acc:.2f}% < 94.0%)")
            if status_acc < 90.0:
                issues.append(f"Multi-turn Retrieval Status Acc chưa đạt ({status_acc:.2f}% < 90.0%)")
            if arr < 97.0:
                issues.append(f"Multi-turn ARR chưa đạt ({arr:.2f}% < 97.0%)")
            if srp < 100.0:
                issues.append(f"Multi-turn SRP chưa đạt 100% ({srp:.2f}% < 100.0%)")
            if mean_lat > 7500.0:
                issues.append(f"Multi-turn độ trễ TB cao ({mean_lat:.1f}ms > 7500ms)")
        except Exception as e:
            issues.append(f"Lỗi phân tích multiturn results: {e}")
    else:
        issues.append("Chưa tìm thấy docs/benchmarks/multiturn_benchmark_results.json")

    # 2. Khảo thí Đơn Lượt Golden Set 200 câu
    stage11_file = Path("docs/benchmarks/latest_benchmark_results.json")
    if stage11_file.exists():
        try:
            if min_artifact_ts > 0 and stage11_file.stat().st_mtime < min_artifact_ts:
                issues.append("latest_benchmark_results.json là file cũ trước khi Coder sửa (không được dùng số liệu cũ)")
            with open(stage11_file, "r", encoding="utf-8") as f:
                s11_data = json.load(f)
            summary = s11_data.get("summary", {})
            router_acc = _to_pct(summary.get("router_accuracy", 0.0))
            crag_prec = _to_pct(summary.get("crag_precision", 0.0))
            ts_safe = _to_pct(summary.get("timestamp_safety", 0.0))
            if router_acc < 90.5:
                issues.append(f"Stage 11 Router Acc chưa đạt ({router_acc:.1f}% < 90.5%)")
            if crag_prec < 86.0:
                issues.append(f"Stage 11 CRAG Precision chưa đạt ({crag_prec:.1f}% < 86.0%)")
            if ts_safe < 86.5:
                issues.append(f"Stage 11 Timestamp Safety chưa đạt ({ts_safe:.1f}% < 86.5%)")
        except Exception as e:
            issues.append(f"Lỗi phân tích Stage 11 results: {e}")
    else:
        issues.append("Chưa tìm thấy docs/benchmarks/latest_benchmark_results.json")

    # 3. Kiểm tra E2E Matrix Summary
    e2e_file = Path("logs/playground_debug/e2e_matrix_latest_summary.json")
    if e2e_file.exists():
        try:
            if min_artifact_ts > 0 and e2e_file.stat().st_mtime < min_artifact_ts:
                issues.append("e2e_matrix_latest_summary.json là file cũ trước khi Coder sửa")
            with open(e2e_file, "r", encoding="utf-8") as f:
                e2e_data = json.load(f)
            if not e2e_data.get("all_passed", False):
                failed_suites = [s.get("suite_id") for s in e2e_data.get("suites", []) if not s.get("passed")]
                issues.append(f"E2E Matrix chưa đạt all_passed (failed={failed_suites})")
        except Exception as e:
            issues.append(f"Lỗi phân tích e2e_matrix_latest_summary.json: {e}")
    else:
        issues.append("Chưa tìm thấy logs/playground_debug/e2e_matrix_latest_summary.json")

    # 4. Kiểm tra Verdict độc lập của Verifier (grounding-evaluator)
    if require_verdict:
        verdict_file = Path(".agent/verification_verdict.md")
        if not verdict_file.exists():
            issues.append("Verifier chưa xuất .agent/verification_verdict.md")
        else:
            if min_artifact_ts > 0 and verdict_file.stat().st_mtime < min_artifact_ts:
                issues.append(".agent/verification_verdict.md là file cũ chưa được Verifier cập nhật cho vòng này")
            v_text = verdict_file.read_text(encoding="utf-8", errors="replace")
            if "VERDICT: APPROVED" not in v_text:
                issues.append(f"Verifier không phê duyệt (không thấy 'VERDICT: APPROVED' trong .agent/verification_verdict.md)")

    # 5. Thẩm định Git Diff chống 100% Quick-Fix & Bypass
    issues.extend(audit_anti_bypass_git_diff())

    if issues:
        return False, " | ".join(issues)
    return True, "Tất cả Quality Gates & Verifier Audit ĐẠT CHUẨN 100%!"


def run_pipeline(
    task: str,
    max_iterations: int = 3,
    spec_path: str = "",
    prefer_claude: bool = False,
    light_verifier: bool = False,
):
    """
    Vận hành toàn bộ quy trình Multi-Subagent Khép Kín (pstack Spec-Driven Closed Loop):
    - Nhịp 1A (Auditor): Carbon High / Claude trên Brain Pool (`thanhnghiat42` / `thanhnghiaa1402`).
    - Nhịp 1B (Thinker): Neon High -> Carbon High trên Brain Pool (`thanhnghiat42` / `thanhnghiaa1402`).
    - Nhịp 2  (Coder):   Hydrogen High trên Exec Pool (`seanpaul1402` -> `tranthehuy23`).
    - Nhịp 3  (Verifier): Hydrogen High (hoặc Flash 3.8 với `--light-verifier`) trên Exec Pool.
    """
    start_time = time.time()
    initial_account = get_active_account_email()
    Path(".agent").mkdir(parents=True, exist_ok=True)
    tracker = PipelineProgressTracker(total_loops=max_iterations, total_phases=4)
    spec_hint = spec_path or "specs/<slug>/spec.md"

    print("\n" + "#" * 75)
    print("# SPEC-DRIVEN MULTI-SUBAGENT CLOSED-LOOP PIPELINE (ZERO ARGON)")
    print(f"# Brain Pool : {', '.join(BRAIN_ACCOUNTS)} (Thinker=Neon->Carbon, Auditor=Carbon->Neon)")
    print(f"# Exec Pool  : {', '.join(EXEC_ACCOUNTS)} (Coder/Verifier/Scribe=Hydrogen High)")
    print(f"# Spec Target: {spec_hint} | Loops: {max_iterations} | Prefer Claude: {prefer_claude}")
    print(f"# Nhiệm vụ   : {task[:80]}...")
    print("#" * 75 + "\n")

    iteration_feedback = ""

    try:
        for loop_idx in range(1, max_iterations + 1):
            loop_start = time.time()
            tracker.start_loop(loop_idx)
            print("\n" + "=" * 75)
            print(f"🔄 BẮT ĐẦU VÒNG LẶP TỰ TỐI ƯU HÓA #{loop_idx} / {max_iterations}")
            print("=" * 75 + "\n")

            feedback_ctx = ""
            if iteration_feedback:
                feedback_ctx = (
                    f"\n\n[PHẢN HỒI KIỂM TOÁN TỪ VÒNG #{loop_idx - 1} CẦN KHẮC PHỤC]:\n"
                    f"{iteration_feedback}\n"
                    f"Yêu cầu: Không được áp dụng lại phương pháp cũ bị lỗi hoặc gây hồi quy!"
                )

            p1a_prompt = (
                f"KÍCH HOẠT QUY TRÌNH PSTACK - NHỊP 1A (VÒNG LẶP #{loop_idx}): THANH TRA & PHÂN TÍCH NGUYÊN NHÂN GỐC TOÀN LUỒNG.\n"
                f"Thực hiện trực tiếp theo vai trò 'codebase-auditor' (đọc `.agents/agents/codebase-auditor.md`):\n"
                f"- Truy vết toàn bộ luồng liên tầng (`IntentRouter` -> `CurriculumService` -> `RetrievalService` -> `ChatGraph` -> `ChatService` -> `TelemetryCritic`) chứ KHÔNG nhìn riêng lẻ từng hàm.\n"
                f"- Đối chiếu kết quả thực tế tại `docs/benchmarks/latest_benchmark_results.json`, `docs/benchmarks/multiturn_benchmark_results.json` và `logs/playground_debug/e2e_matrix_latest_summary.json`.\n"
                f"- BÀI TRỪ 100% REGEX CHỮA CHÁY, TEST-SET SNOOPING & SỬA LỆCH CỤC BỘ GÂY XUNG ĐỘT CHÉO.\n"
                f"- Xuất báo cáo kiểm toán mới nhất vào `.agent/technical_debt_audit.md`.\n"
                f"Nhiệm vụ chi tiết:\n{task}{feedback_ctx}"
            )
            if not execute_phase(
                f"Nhịp 1A: Thanh Tra Nợ Kỹ Thuật (Vòng #{loop_idx})",
                p1a_prompt,
                role_key="auditor",
                is_continue=False,
                phase_idx=1,
                tracker=tracker,
                prefer_claude=prefer_claude,
            ):
                return

            p1b_prompt = (
                f"KÍCH HOẠT QUY TRÌNH PSTACK - NHỊP 1B (VÒNG LẶP #{loop_idx}): THIẾT KẾ UNIFIED E2E SPEC & CONFLICT MATRIX.\n"
                f"Thực hiện trực tiếp theo vai trò 'rag-architect' và 'solution-analyst' (đọc `.agents/agents/rag-architect.md` & `solution-analyst.md`):\n"
                f"- ĐỌC TRỰC TIẾP `.agent/technical_debt_audit.md` và mô tả nhiệm vụ:\n{task}{feedback_ctx}\n"
                f"- Thiết kế phương án đồng bộ theo toàn luồng RAG (0% Quick-Fix, 0% Test-Set Snooping, 100% Data/Code Separation).\n"
                f"- Xuất Unified E2E Spec kèm bảng **Cross-Layer Conflict Matrix** và **Dependency-Ordered Changes** tại `{spec_hint}` "
                f"(và đồng bộ `.agent/implementation_spec.md`, `.agent/task_plan.md`)."
            )
            if not execute_phase(
                f"Nhịp 1B: Thiết Kế Spec & Conflict Matrix (Vòng #{loop_idx})",
                p1b_prompt,
                role_key="thinker",
                is_continue=False,
                phase_idx=2,
                tracker=tracker,
                prefer_claude=prefer_claude,
            ):
                return

            p2_prompt = (
                f"KÍCH HOẠT QUY TRÌNH PSTACK - NHỊP 2 (VÒNG LẶP #{loop_idx}): TRIỂN KHAI CODE NGUYÊN TỬ THEO SPEC.\n"
                f"Thực hiện trực tiếp theo vai trò 'core-coder' (đọc `.agents/agents/core-coder.md`):\n"
                f"- ĐỌC KỸ `{spec_hint}`, `.agent/implementation_spec.md` và `.agent/task_plan.md` vừa duyệt.\n"
                f"- Triển khai đúng thứ tự phụ thuộc trong Spec, sửa đồng bộ các lớp liên quan, giữ nguyên bất biến liên tầng, strict typing, Pydantic v2, 0% regex runtime.\n"
                f"- Cấm tuyệt đối sửa lùi/bỏ qua/nới lỏng test hay ngưỡng trong `tests/` và `scripts/`; chỉ được bổ sung unit test mới khóa các ca trong Spec.\n"
                f"- Cập nhật trạng thái checklist trong `.agent/task_plan.md`."
            )
            if not execute_phase(
                f"Nhịp 2: Triển Khai Code Theo Spec (Vòng #{loop_idx})",
                p2_prompt,
                role_key="coder",
                is_continue=False,
                phase_idx=3,
                tracker=tracker,
            ):
                return

            coder_done_ts = time.time()

            # ---------------------------------------------------------------------
            # CỔNG HARNESS TẤT ĐỊNH (CHẠY TRỰC TIẾP BẰNG PYTHON - 0% LLM QUA MẶT)
            # Bỏ qua hoàn toàn Stage 2 (gen Word); chỉ chạy Stage 1:
            # AST + Anti-Bypass Diff -> 11 Pytests -> E2E Matrix (M1..M8 + S1) -> Macro Benchmarks
            # ---------------------------------------------------------------------
            harness_rc, harness_log = run_deterministic_verification_harness(
                force_eval=True,
                live_llm=False,
            )
            harness_tail = harness_log[-3500:] if len(harness_log) > 3500 else harness_log

            p3_prompt = (
                f"KÍCH HOẠT QUY TRÌNH PSTACK - NHỊP 3 (VÒNG LẶP #{loop_idx}): KIỂM TOÁN ĐỘC LẬP BẰNG CHỨNG THẬT.\n"
                f"Thực hiện trực tiếp theo vai trò 'grounding-evaluator' (đọc `.agents/agents/grounding-evaluator.md`):\n"
                f"- Python Harness Stage 1 VỪA CHẠY XONG (không cần chạy lại test; kết quả exit_code={harness_rc}).\n"
                f"- Đọc trực tiếp `.agent/harness_stage1_latest.log`, các file JSON benchmark mới nhất, `{spec_hint}` và chạy `git diff` trên `app/`, `tests/`, `scripts/`.\n"
                f"- Kiểm toán khắt khe: Có quick-fix, hardcode từ khóa, regex runtime, test-set snooping, nới lỏng assertion, hoặc phá luồng khác không?\n"
                f"- Xuất báo cáo thẩm định vào `.agent/verification_verdict.md` và BẮT BUỘC kết thúc bằng đúng 1 dòng:\n"
                f"  `VERDICT: APPROVED` (chỉ khi exit_code==0 và 0% vi phạm)\n"
                f"  HOẶC `VERDICT: REJECTED: <chi tiết lỗi cần sửa ở vòng sau>`.\n\n"
                f"[TÓM TẮT CUỐI LOG HARNESS]:\n{harness_tail}"
            )
            if not execute_phase(
                f"Nhịp 3: Verifier Kiểm Toán Diff & Bằng Chứng (Vòng #{loop_idx})",
                p3_prompt,
                role_key="verifier",
                is_continue=False,
                phase_idx=4,
                tracker=tracker,
                light_verifier=light_verifier,
            ):
                return

            print("\n" + "-" * 75)
            print(f"[*] ĐANG KIỂM CHUẨN TỰ ĐỘNG QUALITY GATES CHO VÒNG #{loop_idx}...")
            is_passed, summary_report = evaluate_quality_gates(
                min_artifact_ts=coder_done_ts,
                harness_exit_code=harness_rc,
                require_verdict=True,
            )
            loop_duration = round(time.time() - loop_start, 1)
            tracker.log_gate(is_passed, summary_report)

            if is_passed:
                print(f"[✔] VÒNG #{loop_idx} THÀNH CÔNG VƯỢT TRỘI ({loop_duration}s)!")
                print(f"    -> Đánh giá: {summary_report}")
                print(f"    -> ĐÃ ĐẠT ĐIỂM HỘI TỤ TOÀN DIỆN, KẾT THÚC VÒNG LẶP!\n")
                break
            else:
                print(f"[!] CẢNH BÁO: VÒNG #{loop_idx} CHƯA HỘI TỤ HOẶC CÓ HỒI QUY ({loop_duration}s):")
                print(f"    -> Chi tiết vi phạm: {summary_report}")
                iteration_feedback = summary_report
                with open(".agent/iteration_feedback.md", "w", encoding="utf-8") as f:
                    f.write(f"# PHẢN HỒI KIỂM TOÁN VÒNG #{loop_idx}\nThời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n{summary_report}\n")
                if loop_idx < max_iterations:
                    print(f"[*] Tự động chuyển tiếp sang Vòng lặp #{loop_idx + 1} để điều chỉnh phương pháp giải thuật...")
                else:
                    print(f"[!] Đã hoàn thành tối đa {max_iterations} vòng lặp. Dừng để báo cáo.")
    finally:
        switch_to_account(initial_account)
        tracker.close()

    elapsed = round(time.time() - start_time, 1)
    print("\n" + "=" * 75)
    print(f"🎉 TOÀN BỘ TIẾN TRÌNH PIPELINE TỐI ƯU HÓA HOÀN TẤT TRONG {elapsed} GIÂY!")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spec-Driven Multi-Subagent Automated Pipeline (Zero Argon)")
    parser.add_argument("task", nargs="*", default=[], help="Mô tả nhiệm vụ (nếu không dùng file)")
    parser.add_argument("--file", "-f", default=None, help="Đường dẫn đến file prompt chi tiết")
    parser.add_argument("--spec", "-s", default="", help="Đường dẫn Spec mục tiêu (vd: specs/004-unified-rag-workflow-hardening/spec.md)")
    parser.add_argument("--loops", "-l", type=int, default=3, help="Số vòng lặp tối đa tự động hội tụ (mặc định: 3)")
    parser.add_argument("--prefer-claude", action="store_true", help="Ưu tiên Claude Opus/Sonnet 5.5 cho Thinker/Auditor trước khi dùng Neon/Carbon")
    parser.add_argument("--light-verifier", action="store_true", help="Dùng gemini-3.8-flash-high làm model chính cho pha Verifier để tiết kiệm Hydrogen High")
    args = parser.parse_args()

    target_file = Path(args.file) if args.file else Path(".agent/prompt_mission.md")
    if target_file.exists():
        print(f"[*] Đã nạp thành công Prompt hoàn thiện từ file: {target_file}")
        with open(target_file, "r", encoding="utf-8") as f:
            task_input = f.read().strip()
    elif args.task:
        task_input = " ".join(args.task)
    else:
        task_input = "Kiểm toán và xử lý đồng bộ toàn bộ logic fallback liên tầng theo quy trình pstack + Cross-Layer Conflict Matrix."

    run_pipeline(
        task_input,
        max_iterations=args.loops,
        spec_path=args.spec,
        prefer_claude=args.prefer_claude,
        light_verifier=args.light_verifier,
    )
