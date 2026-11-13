"""
Dual-Mastermind & Multi-Subagent Automated Pipeline (pstack Standards)
Dự án: In-Course Agentic RAG Copilot - Tác giả: Trần Thành Nghĩa (HUFLIT)

Kiến trúc Phối Hợp Đa Tác Nhân Khép Kín (Self-Iterative Optimization Loop):
  1. HỘI ĐỒNG ĐẦU NÃO (Dual Mastermind Council):
     - Claude Sonnet 5.5 High -> Subagent 'codebase-auditor': Thanh tra phản biện, diệt 100% Quick-Fix & Hardcode.
     - Gemini 4 Argon High   -> Subagent 'rag-architect' & 'solution-analyst': Lý thuyết RAG/CRAG, Ngưỡng Pareto, Context Formulation.
  2. TẦNG THỰC THI (Worker Coder):
     - Gemini 3.8 Flash High -> Subagent 'core-coder': Gõ mã nguồn siêu tốc (70 tok/s), strict typing, Pydantic v2.
  3. HỘI ĐỒNG THẨM ĐỊNH (Evaluation Council):
     - Claude Sonnet 5.5 High -> Subagent 'grounding-evaluator': Tái cấu trúc chấm điểm công tâm, chống số liệu giả/overfitting.
     - Gemini 3.8 Flash High -> Subagent 'qa-tester': Chạy test suite độc lập, đo TTFT latency, kiểm chuẩn Quality Gates.
Tự động hoán đổi Quota qua Antigravity Tools (antigravity-server.exe).
Tự động lặp lại vòng tối ưu hóa (Closed-Loop Convergence) nếu chưa đạt chuẩn hoặc phát hiện hồi quy.
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

# BẢNG ÁNH XẠ MÔ HÌNH ĐỘNG THEO TỪNG TÀI KHOẢN (ACCOUNT-AWARE MODEL MAPPING)
# Chuẩn hóa 100% theo danh mục mô hình chính thức trả về từ `agy models` và quota thực tế (12/11/2026)
ACCOUNT_MODEL_PROFILES = {
    "thanhnghiat42@gmail.com": {
        # Tài khoản chính (PRO - 100% Quota ở Gemini 4 Argon, Claude 5.5, Gemini 3.8):
        # Chia tải thông minh giữa 2 pool độc lập: Claude 5.5 Weekly (100%) + Gemini 4 Argon Weekly (100%)
        "auditor":  "claude-sonnet-5-5-high",   # Claude Sonnet 5.5 High (Thanh tra phản biện, diệt quick-fix)
        "thinker":  "gemini-4-argon-high",      # Gemini 4 Argon High (Đầu não toán học RAG/CRAG/Pareto)
        "coder":    "gemini-3.8-flash-high",    # Gemini 3.8 Flash High (Gõ code siêu tốc, strict typing)
        "verifier": "claude-sonnet-5-5-high",   # Claude Sonnet 5.5 High (Thẩm định độc lập & Quality Gates)
    },
    "seanpaul1402@gmail.com": {
        # Tài khoản dự phòng (PRO - KHÔNG có Argon/5.5; Claude 4.6 đang 0% 5H / 7% Weekly, Gemini 3.8 còn 88%-95%):
        # Ưu tiên Gemini 3.8 Flash High (dồi dào quota); chỉ dùng Claude 4.6 khi thủ công bật lại sau reset
        "auditor":  "gemini-3.8-flash-high",
        "thinker":  "gemini-3.8-flash-high",
        "coder":    "gemini-3.8-flash-high",
        "verifier": "gemini-3.8-flash-high",
    }
}

# CHUỖI DỰ PHÒNG MÔ HÌNH KHI CẠN HẠN MỨC HOẶC KHÔNG KHẢ DỤNG (TIERED MODEL FALLBACK CHAIN)
# Thứ tự ưu tiên chuyển sang pool quota độc lập cùng tài khoản trước (ví dụ Claude 5.5 -> Gemini 4 Argon -> Gemini 3.8)
MODEL_FALLBACK_CHAINS = {
    "claude-opus-5-5-high":      ["claude-sonnet-5-5-high", "gemini-4-argon-high", "gemini-3.8-flash-high"],
    "claude-sonnet-5-5-high":    ["gemini-4-argon-high", "claude-sonnet-5-5-medium", "gemini-3.8-flash-high"],
    "claude-sonnet-5-5-medium":  ["gemini-4-argon-high", "gemini-3.8-flash-high"],
    "gemini-4-argon-high":       ["gemini-4-argon-medium", "claude-sonnet-5-5-high", "gemini-3.8-flash-high"],
    "gemini-4-argon-medium":     ["claude-sonnet-5-5-high", "gemini-3.8-flash-high"],
    "claude-opus-4-6-thinking":  ["claude-sonnet-4-6", "gemini-3.8-flash-high"],
    "claude-sonnet-4-6":         ["gemini-3.8-flash-high"],
    "gemini-3.8-flash-high":     ["gemini-3.8-flash-medium", "gemini-4-argon-medium", "claude-sonnet-5-5-high", "gemini-3.8-flash-low"],
    "gemini-3.8-flash-medium":   ["gemini-4-argon-medium", "claude-sonnet-5-5-high", "gemini-3.8-flash-low"],
}

DEFAULT_PROFILE = {
    "thinker": "gemini-3.8-flash-high",
    "auditor": "gemini-3.8-flash-high",
    "coder":   "gemini-3.8-flash-high",
    "verifier": "gemini-3.8-flash-high"
}


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
POOL_ACCOUNT_COUNT = 2      # Số tài khoản trong pool (thanhnghiat42 & seanpaul1402)
COOLDOWN_SLEEP_SEC = 60     # Thời gian chờ khi toàn bộ tài khoản trong pool đều cạn hạn mức

QUOTA_ERROR_REGEX = re.compile(
    r"(quota exceeded|rate limit|resource_exhausted|429|too many requests|overloaded|capacity exceeded|credit balance|server error|service unavailable|503|504|invalid model selection|individual quota reached)",
    re.IGNORECASE
)


def switch_quota_account():
    """Tự động xoay sang tài khoản dự phòng tiếp theo qua Antigravity Tools."""
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
    tracker: "PipelineProgressTracker" = None
) -> bool:
    """
    Thực thi một nhịp của quy trình với cơ chế TỰ ĐỘNG THÍCH ỨNG MODEL THEO TÀI KHOẢN:
    - Kiểm chứng danh sách model thực tế qua `agy models` trước khi gọi (0% lỗi invalid model selection).
    - Nếu cạn quota trên một model của `thanhnghiat42`, ưu tiên giáng cấp sang pool model độc lập cùng tài khoản
      (VD: Claude 5.5 -> Gemini 4 Argon -> Gemini 3.8) TRƯỚC KHI switch sang tài khoản dự phòng.
    """
    attempt = 0
    cycle_account_flips = 0
    tried_on_current_account: set[str] = set()
    override_model = None

    while True:
        attempt += 1
        active_email, profile = resolve_models_for_current_account()
        available_models = get_available_models()

        candidate = override_model or profile.get(role_key, "gemini-3.8-flash-high")
        if available_models and candidate not in available_models:
            # Chọn fallback hợp lệ đầu tiên có trong available_models và chưa thử trên account này
            chain = MODEL_FALLBACK_CHAINS.get(candidate, ["gemini-3.8-flash-high"])
            valid_fallback = next(
                (m for m in chain if m in available_models and m not in tried_on_current_account),
                available_models[0]
            )
            print(f"[Model Guard] Model '{candidate}' không khả dụng trên {active_email} -> chọn '{valid_fallback}'.")
            active_model = valid_fallback
        else:
            active_model = candidate

        tried_on_current_account.add(active_model)

        print("\n" + "=" * 75)
        print(f"[*] {phase_title.upper()} (Lần chạy #{attempt})")
        print(f"[*] Tài khoản: {active_email} | Vai trò: {role_key.upper()} | Model: {active_model}")
        print(f"[*] Chế độ: {'Nối tiếp phiên (--continue)' if is_continue else 'Khởi tạo phiên mới'}")
        print("=" * 75 + "\n")

        if tracker:
            tracker.start_phase(phase_idx, phase_title, role_key, active_model)

        agy_bin = shutil.which("agy") or "agy"
        cmd = [agy_bin, "--model", active_model, "--dangerously-skip-permissions"]
        if is_continue:
            cmd.append("--continue")
        cmd.extend(["--print", prompt])

        try:
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

            phase_timeout = 3600 if role_key == "verifier" else 1800
            process.wait(timeout=phase_timeout)

            if not quota_hit and process.returncode == 0:
                print(f"\n[✔] {phase_title} ĐÃ HOÀN TẤT THÀNH CÔNG!\n")
                if tracker:
                    tracker.end_phase(phase_title, success=True)
                return True

            print(f"\n[!] Nhịp gặp lỗi hạn mức hoặc gián đoạn (Exit Code: {process.returncode}, quota_hit={quota_hit}).")
            if tracker:
                tracker.end_phase(phase_title, success=False)

            # 1. Thử fallback sang pool model độc lập NGAY TRÊN CÙNG TÀI KHOẢN trước khi switch
            same_account_chain = [
                m for m in MODEL_FALLBACK_CHAINS.get(active_model, [])
                if (not available_models or m in available_models) and m not in tried_on_current_account
            ]
            if same_account_chain:
                next_same_acc = same_account_chain[0]
                print(f"\n[Same-Account Pool Fallback] '{active_model}' gặp lỗi trên {active_email}.")
                print(f"[Same-Account Pool Fallback] Chuyển sang model độc lập cùng tài khoản: '{next_same_acc}'.")
                override_model = next_same_acc
                time.sleep(2)
                continue

            # 2. Khi mọi model trên tài khoản hiện tại đều đã thử/cạn -> xoay sang tài khoản khác
            switch_quota_account()
            tried_on_current_account.clear()
            override_model = None
            cycle_account_flips += 1

            if cycle_account_flips >= POOL_ACCOUNT_COUNT:
                print(f"\n[24/7 Cooldown Guard] Toàn bộ {POOL_ACCOUNT_COUNT} tài khoản trong Pool đều chạm hạn ngạch.")
                print(f"[24/7 Cooldown Guard] Tự động tạm dừng {COOLDOWN_SLEEP_SEC} giây để cửa sổ hạn mức hồi phục...")
                for remaining in range(COOLDOWN_SLEEP_SEC, 0, -10):
                    print(f"  --> Sẽ tự động kiểm tra và tiếp tục sau {remaining} giây...")
                    time.sleep(10)
                cycle_account_flips = 0
            else:
                time.sleep(3)

        except subprocess.TimeoutExpired:
            print("\n[Timeout Warning] Lượt chạy vượt quá 30 phút, đang tái khởi động an toàn...")
            process.kill()
            switch_quota_account()
            tried_on_current_account.clear()
            override_model = None
            is_continue = True
            continue
        except KeyboardInterrupt:
            print("\n[User Cancel] Người dùng chủ động dừng pipeline (Ctrl+C).")
            return False
        except Exception as ex:
            print(f"\n[System Blip] Bắt lỗi ngoại lệ ngoại vi: {ex}. Nghỉ 5s rồi thử lại...")
            time.sleep(5)
            continue


def _to_pct(value: float) -> float:
    """Chuẩn hóa đơn vị phần trăm (hỗ trợ cả dạng 0..1 và 0..100 từ JSON benchmark)."""
    val = float(value)
    return val * 100.0 if val <= 1.0 else val


def evaluate_quality_gates() -> tuple[bool, str]:
    """
    Kiểm toán tự động Quality Gates sau mỗi vòng lặp tối ưu:
    1. Đọc kết quả Khảo thí Đa lượt (multiturn_benchmark_results.json)
    2. Đọc kết quả Khảo thí Đơn lượt Stage 11 Golden 200 (latest_benchmark_results.json)
    3. Thẩm định Git Diff phát hiện vi phạm Quick-Fix / Cheat hardcode.
    """
    issues = []

    # 1. Khảo thí Đa Lượt 50 sessions / 222 turns
    mt_file = Path("docs/benchmarks/multiturn_benchmark_results.json")
    if mt_file.exists():
        try:
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
            if status_acc < 93.0:
                issues.append(f"Multi-turn Retrieval Status Acc chưa đạt ({status_acc:.2f}% < 93.0%)")
            if arr < 95.0:
                issues.append(f"Multi-turn ARR chưa đạt ({arr:.2f}% < 95.0%)")
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
            with open(stage11_file, "r", encoding="utf-8") as f:
                s11_data = json.load(f)
            summary = s11_data.get("summary", {})
            router_acc = _to_pct(summary.get("router_accuracy", 0.0))
            crag_prec = _to_pct(summary.get("crag_precision", 0.0))
            ts_safe = _to_pct(summary.get("timestamp_safety", 0.0))
            if router_acc < 90.5:
                issues.append(f"Stage 11 Router Acc chưa đạt ({router_acc:.1f}% < 90.5%)")
            if crag_prec < 88.0:
                issues.append(f"Stage 11 CRAG Precision chưa đạt ({crag_prec:.1f}% < 88.0%)")
            if ts_safe < 88.0:
                issues.append(f"Stage 11 Timestamp Safety chưa đạt ({ts_safe:.1f}% < 88.0%)")
        except Exception as e:
            issues.append(f"Lỗi phân tích Stage 11 results: {e}")
    else:
        issues.append("Chưa tìm thấy docs/benchmarks/latest_benchmark_results.json")

    # 3. Thẩm định Git Diff chống 100% Quick-Fix (Whack-a-mole cheats)
    try:
        diff_res = subprocess.run(["git", "diff", "app/"], capture_output=True, text=True, errors="replace")
        diff_text = diff_res.stdout
        cheat_patterns = [
            r'^\+\s*(?:import\s+re\b|from\s+re\s+import)',
            r'^\+.*(?:BENCH-\d+|SESSION-)',
            r'if\s+["\']mảng 2 chiều["\']',
            r'if\s+["\']con trỏ["\']',
            r'if\s+["\']sắp xếp["\']',
            r'if\s+.*in\s+raw_prompt\.lower\(\)\s*:\s*return',
        ]
        for pat in cheat_patterns:
            if re.search(pat, diff_text, re.IGNORECASE | re.MULTILINE):
                issues.append(f"VI PHẠM NGUYÊN TẮC ZERO QUICK-FIX: Phát hiện pattern '{pat}' trong git diff app/")
    except Exception:
        pass

    if issues:
        return False, " | ".join(issues)
    return True, "Tất cả Quality Gates ĐẠT CHUẨN 100%!"


def run_pipeline(task: str, max_iterations: int = 3):
    """
    Vận hành toàn bộ quy trình Multi-Subagent Khép Kín (Self-Iterative Optimization Loop):
    - Chạy chu trình 3 Nhịp: Auditor -> Thinker/Architect -> Coder -> Verifier.
    - Tự động chạy benchmark và kiểm tra Quality Gates.
    - Nếu có chỉ số chưa đạt hoặc hồi quy, tự động lặp lại vòng tiếp theo để điều chỉnh giải thuật.
    """
    start_time = time.time()
    Path(".agent").mkdir(parents=True, exist_ok=True)
    tracker = PipelineProgressTracker(total_loops=max_iterations, total_phases=4)

    print("\n" + "#" * 75)
    print("# DUAL-MASTERMIND & MULTI-SUBAGENT 24/7 AUTOMATED CLOSED-LOOP PIPELINE")
    print("# Cơ chế: Account-Aware Dynamic Model Resolution + Self-Iterative Loop")
    print(f"# Mục tiêu tối đa: {max_iterations} vòng lặp tự hội tụ")
    print(f"# Nhiệm vụ: {task[:80]}...")
    print("#" * 75 + "\n")

    iteration_feedback = ""

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

        # =========================================================================
        # NHỊP 1A: THANH TRA PHẢN BIỆN (auditor) - ĐỌC TRỰC TIẾP MISSION & BENCHMARK HIỆN HÀNH
        # =========================================================================
        p1a_prompt = (
            f"KÍCH HOẠT QUY TRÌNH PSTACK - NHỊP 1A (VÒNG LẶP #{loop_idx}): THANH TRA & PHÂN TÍCH NGUYÊN NHÂN GỐC.\n"
            f"Bạn là Thanh tra phản biện cấp cao.\n"
            f"BẮT BUỘC TRIỆU HỒI SUBAGENT 'codebase-auditor' bằng invoke_subagent:\n"
            f"- Đọc toàn bộ nhiệm vụ hiện hành trong '.agent/prompt_mission.md' và kiểm tra kết quả benchmark thực tế tại "
            f"'docs/benchmarks/latest_benchmark_results.json' và 'docs/benchmarks/multiturn_benchmark_results.json'.\n"
            f"- Điều tra các ca fail còn lại, tuyệt đối KHÔNG làm hỏng các phần đã ổn định (Router 90.5%+, Multi-turn Intent 94.59%, ARR 97.87%, SRP 100%).\n"
            f"- BÀI TRỪ 100% REGEX CHỮA CHÁY, TEST-SET SNOOPING & HARDCODE TỪ KHÓA ĐỀ THI.\n"
            f"- Xuất bản báo cáo kiểm toán mới nhất vào '.agent/technical_debt_audit.md'.\n"
            f"Nhiệm vụ chi tiết:\n{task}{feedback_ctx}"
        )
        if not execute_phase(f"Nhịp 1A: Thanh Tra Nợ Kỹ Thuật (Vòng #{loop_idx})", p1a_prompt, role_key="auditor", is_continue=False, phase_idx=1, tracker=tracker):
            tracker.close()
            return

        # =========================================================================
        # NHỊP 1B: ĐẦU NÃO KIẾN TRÚC TOÁN HỌC (thinker) - ĐỌC TRỰC TIẾP ARTIFACT
        # =========================================================================
        p1b_prompt = (
            f"KÍCH HOẠT QUY TRÌNH PSTACK - NHỊP 1B (VÒNG LẶP #{loop_idx}): THIẾT KẾ KIẾN TRÚC & SPEC GIẢI QUYẾT TRIỆT ĐỂ.\n"
            f"Bạn là Kiến trúc sư trưởng.\n"
            f"BẮT BUỘC TRIỆU HỒI SUBAGENT 'rag-architect' và 'solution-analyst' bằng invoke_subagent:\n"
            f"- ĐỌC TRỰC TIẾP '.agent/prompt_mission.md' và báo cáo '.agent/technical_debt_audit.md' vừa xuất bản.\n"
            f"- Thiết kế phương án chuẩn mực theo lớp bài toán (0% Quick-Fix, 0% Test-Set Snooping): phân tách OWASP LLM01 Prompt Injection vs "
            f"Academic Code Solicitation (để giữ intent='course_query' + Socratic Scaffolding, giải quyết pytest 15/15 và Tier 2 Multi-Turn), "
            f"đồng bộ MODALITY_GATE_VIDEO_HIGH_CONFIDENCE với AGENTS.md, gỡ bỏ nhánh pass/comment BENCH-xxx và tối ưu NLI Rescue.\n"
            f"- Xuất bản '.agent/implementation_spec.md' và cập nhật checklist '.agent/task_plan.md'."
        )
        if not execute_phase(f"Nhịp 1B: Thiết Kế Kiến Trúc & Spec (Vòng #{loop_idx})", p1b_prompt, role_key="thinker", is_continue=False, phase_idx=2, tracker=tracker):
            tracker.close()
            return

        # =========================================================================
        # NHỊP 2: THỢ GÕ MÃ NGUỒN SIÊU TỐC (coder) - ĐỌC TRỰC TIẾP IMPLEMENTATION SPEC
        # =========================================================================
        p2_prompt = (
            f"KÍCH HOẠT QUY TRÌNH PSTACK - NHỊP 2 (VÒNG LẶP #{loop_idx}): TRIỂN KHAI CODE NGUYÊN TỬ.\n"
            f"Bạn là Kỹ sư lập trình lõi.\n"
            f"BẮT BUỘC TRIỆU HỒI SUBAGENT 'core-coder' bằng invoke_subagent:\n"
            f"- ĐỌC KỸ '.agent/implementation_spec.md' và '.agent/task_plan.md' vừa xuất bản.\n"
            f"- Triển khai chính xác vào các file liên quan theo đúng thiết kế, giữ nguyên các invariant đã chốt.\n"
            f"- Tuân thủ strict typing, Pydantic v2, Zero Regex cheat, cập nhật trạng thái checklist trong '.agent/task_plan.md'."
        )
        if not execute_phase(f"Nhịp 2: Gõ Code Siêu Tốc (Vòng #{loop_idx})", p2_prompt, role_key="coder", is_continue=False, phase_idx=3, tracker=tracker):
            tracker.close()
            return

        # =========================================================================
        # FAST AST SYNTAX GATE (0.5s): Chặn đứng SyntaxError ngay sau Nhịp 2
        # =========================================================================
        print("\n" + "-" * 75)
        print("[*] ĐANG KIỂM TRA AN TOÀN CÚ PHÁP AST (0.5s Fast Syntax Gate)...")
        syntax_errors = []
        for py_path in Path("app").rglob("*.py"):
            try:
                import py_compile
                py_compile.compile(str(py_path), doraise=True)
            except Exception as e:
                syntax_errors.append(f"{py_path.name}: {e}")
        if syntax_errors:
            print(f"[!] PHÁT HIỆN LỖI CÚ PHÁP PYTHON: {'; '.join(syntax_errors)}")
        else:
            print("[✔] 100% Cú pháp AST các file Python trong app/ hợp lệ hoàn hảo!")
        print("-" * 75 + "\n")
        tracker.log_syntax_gate(syntax_errors)

        # =========================================================================
        # NHỊP 3: HỘI ĐỒNG THẨM ĐỊNH & KIỂM THỬ ĐỘC LẬP (verifier)
        # =========================================================================
        p3_prompt = (
            f"KÍCH HOẠT QUY TRÌNH PSTACK - NHỊP 3 (VÒNG LẶP #{loop_idx}): CỔNG NGHIỆM THU BẰNG CHỨNG (EVIDENCE GATE).\n"
            f"Bạn là Trưởng ban thẩm định.\n"
            f"BẮT BUỘC TRIỆU HỒI 2 SUBAGENT:\n"
            f"1. Subagent 'qa-tester': Thực thi tuần tự '.\\.venv\\Scripts\\python.exe -m pytest tests/ -v', '.\\.venv\\Scripts\\python.exe scripts/run_multiturn_benchmark.py' và '.\\.venv\\Scripts\\python.exe scripts/run_rag_benchmark.py --dataset tests/data/benchmark_golden_dataset.json'. "
            f"Đồng thời kiểm tra health của settings.LLM_BASE_URL: nếu server LLM đang Online (HTTP 200), chạy thêm '.\\.venv\\Scripts\\python.exe scripts/run_multiturn_benchmark.py --mode e2e --tier tier_2_socratic' (ghi ra multiturn_benchmark_e2e_results.json); nếu Offline thì ghi rõ trạng thái Offline.\n"
            f"2. Subagent 'grounding-evaluator': CHỈ đối chiếu trên bộ kết quả benchmark MỚI NHẤT vừa được 'qa-tester' xuất sau Nhịp 2 (kiểm tra metadata.end_time, tuyệt đối không dùng số liệu cũ); thẩm tra tính trung thực của toàn bộ git diff, chống 100% fake data, overfitting, comment chứa BENCH-xxx và regex.\n"
            f"Chỉ cho phép kết luận ĐẠT khi 15/15 bài test PASS, SRP = 100% (0 code leak), CRAG Precision >= 88.0%, Multi-Turn Intent >= 94.0%, Multi-Turn Status >= 93.0% và 0% Quick-Fix/Hardcode!"
        )
        if not execute_phase(f"Nhịp 3: Hội Đồng Thẩm Định & Nghiệm Thu (Vòng #{loop_idx})", p3_prompt, role_key="verifier", is_continue=False, phase_idx=4, tracker=tracker):
            tracker.close()
            return

        # =========================================================================
        # KIỂM TOÁN TỰ ĐỘNG QUALITY GATES ĐỂ QUYẾT ĐỊNH HỘI TỤ
        # =========================================================================
        print("\n" + "-" * 75)
        print(f"[*] ĐANG KIỂM CHUẨN TỰ ĐỘNG QUALITY GATES CHO VÒNG #{loop_idx}...")
        is_passed, summary_report = evaluate_quality_gates()
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

    elapsed = round(time.time() - start_time, 1)
    tracker.close()
    print("\n" + "=" * 75)
    print(f"🎉 TOÀN BỘ TIẾN TRÌNH PIPELINE TỐI ƯU HÓA HOÀN TẤT TRONG {elapsed} GIÂY!")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dual-Mastermind & Multi-Subagent 24/7 Automated Pipeline")
    parser.add_argument("task", nargs="*", default=[], help="Mô tả nhiệm vụ (nếu không dùng file)")
    parser.add_argument("--file", "-f", default=None, help="Đường dẫn đến file prompt chi tiết")
    parser.add_argument("--loops", "-l", type=int, default=3, help="Số vòng lặp tối đa tự động hội tụ (mặc định: 3)")
    args = parser.parse_args()

    target_file = Path(args.file) if args.file else Path(".agent/prompt_mission.md")
    if target_file.exists():
        print(f"[*] Đã nạp thành công Prompt hoàn thiện từ file: {target_file}")
        with open(target_file, "r", encoding="utf-8") as f:
            task_input = f.read().strip()
    elif args.task:
        task_input = " ".join(args.task)
    else:
        task_input = "Tối ưu hóa khép kín: sửa lỗi CUBLAS VRAM Re-ranker, chuẩn hóa N-gram Topical Overlap, và kích hoạt Action chuyển bài."

    run_pipeline(task_input, max_iterations=args.loops)
