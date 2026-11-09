"""
Dual-Mastermind & Multi-Subagent Automated Pipeline (pstack Standards)
Dự án: In-Course Agentic RAG Copilot - Tác giả: Trần Thành Nghĩa (HUFLIT)

Kiến trúc Phối Hợp Đa Tác Nhân:
  1. HỘI ĐỒNG ĐẦU NÃO (Dual Mastermind Council):
     - Claude Sonnet 5.5 High -> Subagent 'codebase-auditor': Thanh tra phản biện, diệt 100% Quick-Fix & Hardcode.
     - Gemini 4 Argon High   -> Subagent 'rag-architect' & 'solution-analyst': Lý thuyết RAG/CRAG, Ngưỡng Pareto, Context Formulation.
  2. TẦNG THỰC THI (Worker Coder):
     - Gemini 3.8 Flash High -> Subagent 'core-coder': Gõ mã nguồn siêu tốc (70 tok/s), strict typing, Pydantic v2.
  3. HỘI ĐỒNG THẨM ĐỊNH (Evaluation Council):
     - Claude Sonnet 5.5 High -> Subagent 'grounding-evaluator': Tái cấu trúc chấm điểm công tâm, chống số liệu giả/overfitting.
     - Gemini 3.8 Flash High -> Subagent 'qa-tester': Chạy test suite độc lập, đo TTFT latency.
Tự động hoán đổi Quota qua Antigravity Tools (antigravity-server.exe).
"""

import subprocess
import sys
import time
import re
import argparse
from pathlib import Path

# Đường dẫn quản lý Quota trên máy bạn
ANTIGRAVITY_SERVER = Path(r"D:\PooL_quota\Antigravity Tools\antigravity-server.exe")

# BẢNG ÁNH XẠ MÔ HÌNH ĐỘNG THEO TỪNG TÀI KHOẢN (ACCOUNT-AWARE MODEL MAPPING)
# Giải quyết triệt để sự không đồng nhất giữa các tài khoản trong Pool
ACCOUNT_MODEL_PROFILES = {
    "thanhnghiaa1402@gmail.com": {
        "thinker": "gemini-4-argon-high",       # Account 1 có Argon còn 100%
        "auditor": "claude-sonnet-5-5-medium",   # Claude 5.5
        "coder":   "gemini-3.8-flash-high",     # Gemini Flash High
        "verifier": "gemini-4-argon-high"       # Tận dụng Argon dồi dào
    },
    "seanpaul1402@gmail.com": {
        "thinker": "claude-sonnet-4-6",          # Account 2 có Claude Thinking còn 100%!
        "auditor": "claude-sonnet-4-6",          # Claude 4.6 Thinking
        "coder":   "gemini-3.8-flash-high",     # Gemini Flash High
        "verifier": "claude-sonnet-4-6"          # Claude Thinking 100% Quota
    }
}

DEFAULT_PROFILE = {
    "thinker": "gemini-3.8-flash-high",
    "auditor": "gemini-3.8-flash-high",
    "coder":   "gemini-3.8-flash-high",
    "verifier": "gemini-3.8-flash-high"
}


def get_active_account_email() -> str:
    """Truy vấn tài khoản agy CLI đang kích hoạt từ Antigravity Tools"""
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
    return "thanhnghiaa1402@gmail.com"


def resolve_models_for_current_account():
    """Tự động phân giải bộ model chuẩn xác tương ứng với tài khoản đang active"""
    active_email = get_active_account_email()
    profile = ACCOUNT_MODEL_PROFILES.get(active_email, DEFAULT_PROFILE)
    print(f"[*] Tài khoản active hiện tại: {active_email}")
    print(f"[*] Bộ model tự động tương thích: Thinker={profile['thinker']} | Coder={profile['coder']} | Verifier={profile['verifier']}")
    return profile

# Cấu hình 24/7 Daemon & Quota Resilience
POOL_ACCOUNT_COUNT = 2      # Số tài khoản trong pool (thanhnghiaa & seanpaul)
COOLDOWN_SLEEP_SEC = 60     # Thời gian chờ khi toàn bộ tài khoản trong pool đều cạn hạn mức

QUOTA_ERROR_REGEX = re.compile(
    r"(quota exceeded|rate limit|resource_exhausted|429|too many requests|overloaded|capacity exceeded|credit balance|server error|service unavailable|503|504)",
    re.IGNORECASE
)


def switch_quota_account():
    """Tự động xoay sang tài khoản dự phòng tiếp theo qua Antigravity Tools"""
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


def execute_phase(phase_title: str, prompt: str, role_key: str, is_continue: bool = True) -> bool:
    """
    Thực thi một nhịp của quy trình với cơ chế TỰ ĐỘNG THÍCH ỨNG MODEL THEO TÀI KHOẢN:
    - Tra cứu tài khoản đang active để chọn đúng model mà tài khoản đó sở hữu.
    - Không bao giờ gọi sai model giữa Account 1 (có Argon/Claude 5.5) và Account 2 (có Claude Thinking 4.6).
    """
    attempt = 0
    cycle_account_flips = 0

    while True:
        attempt += 1
        # Phân giải mô hình động dựa trên tài khoản đang active
        profile = resolve_models_for_current_account()
        active_model = profile.get(role_key, "gemini-3.8-flash-high")

        print("\n" + "=" * 75)
        print(f"[*] {phase_title.upper()} (Lần chạy #{attempt})")
        print(f"[*] Vai trò: {role_key.upper()} | Mô hình thích ứng: {active_model}")
        print(f"[*] Chế độ: {'Nối tiếp phiên (--continue)' if is_continue else 'Khởi tạo phiên mới'}")
        print("=" * 75 + "\n")

        # Đặt --model và --dangerously-skip-permissions lên trước --print để tránh lỗi cmd.exe nuốt cờ
        cmd = ["agy", "--model", active_model, "--dangerously-skip-permissions"]
        if is_continue:
            cmd.append("--continue")
        cmd.extend(["--print", prompt])

        try:
            # shell=False để Windows CreateProcess truyền thẳng mảng tham số, bảo đảm 100% không bị cmd.exe làm rơi cờ --model
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
            for line in process.stdout:
                sys.stdout.write(line)
                if QUOTA_ERROR_REGEX.search(line):
                    quota_hit = True

            process.wait()

            # Nếu chạy thành công mỹ mãn
            if not quota_hit and process.returncode == 0:
                print(f"\n[✔] {phase_title} ĐÃ HOÀN TẤT THÀNH CÔNG!\n")
                return True

            # Nếu gặp lỗi hạn mức hoặc tiến trình kết thúc thất thường
            print(f"\n[!] Nhịp gặp lỗi hạn mức hoặc gián đoạn mạng (Exit Code: {process.returncode}).")
            switch_quota_account()
            cycle_account_flips += 1
            is_continue = True # Sau lần đầu, bắt buộc tiếp tục phiên (-c)

            # Nếu đã xoay hết 1 vòng toàn bộ tài khoản trong pool mà vẫn nghẽn
            if cycle_account_flips >= POOL_ACCOUNT_COUNT:
                print(f"\n[24/7 Cooldown Guard] Toàn bộ {POOL_ACCOUNT_COUNT} tài khoản trong Pool đều đang chạm hạn ngạch.")
                print(f"[24/7 Cooldown Guard] Tự động tạm dừng {COOLDOWN_SLEEP_SEC} giây để cửa sổ hạn mức hồi phục...")
                for remaining in range(COOLDOWN_SLEEP_SEC, 0, -10):
                    print(f"  --> Sẽ tự động kiểm tra và tiếp tục sau {remaining} giây...")
                    time.sleep(10)
                cycle_account_flips = 0
            else:
                time.sleep(3) # Nghỉ ngắn khi đổi tài khoản mới

        except KeyboardInterrupt:
            print("\n[User Cancel] Người dùng chủ động dừng pipeline (Ctrl+C).")
            return False
        except Exception as ex:
            print(f"\n[System Blip] Bắt lỗi ngoại lệ ngoại vi: {ex}. Nghỉ 5s rồi thử lại...")
            time.sleep(5)
            continue


def run_pipeline(task: str):
    """Vận hành toàn bộ quy trình Multi-Subagent khép kín"""
    start_time = time.time()
    Path(".agent").mkdir(parents=True, exist_ok=True)

    print("\n" + "#" * 75)
    print("# DUAL-MASTERMIND & MULTI-SUBAGENT 24/7 AUTOMATED PIPELINE")
    print("# Cơ chế: Account-Aware Dynamic Model Resolution (Thích ứng đa tài khoản)")
    print(f"# Nhiệm vụ: {task[:80]}...")
    print("#" * 75 + "\n")

    # =========================================================================
    # NHỊP 1A: THANH TRA PHẢN BIỆN (auditor)
    # =========================================================================
    p1a_prompt = (
        f"KÍCH HOẠT QUY TRÌNH PSTACK - NHỊP 1A: THANH TRA BÓC TRẦN NỢ KỸ THUẬT.\n"
        f"Bạn là Thanh tra phản biện cấp cao.\n"
        f"BẮT BUỘC TRIỆU HỒI SUBAGENT 'codebase-auditor' bằng invoke_subagent:\n"
        f"- Quét sâu toàn bộ chat_graph.py, telemetry_critic.py và router.py.\n"
        f"- Bóc trần toàn bộ hardcode regex, magic numbers (như len < 4), bẫy if not is_course_query.\n"
        f"- Xuất bản báo cáo nợ kỹ thuật vào '.agent/technical_debt_audit.md'.\n"
        f"Đề bài cần audit: {task}"
    )
    if not execute_phase("Nhịp 1A: Thanh Tra Bóc Trần Nợ Kỹ Thuật (Subagent: codebase-auditor)", p1a_prompt, role_key="auditor", is_continue=False):
        return

    # =========================================================================
    # NHỊP 1B: ĐẦU NÃO KIẾN TRÚC TOÁN HỌC (thinker)
    # =========================================================================
    p1b_prompt = (
        f"KÍCH HOẠT QUY TRÌNH PSTACK - NHỊP 1B: THIẾT KẾ KIẾN TRÚC TOÁN HỌC & SPEC.\n"
        f"Bạn là Kiến trúc sư trưởng.\n"
        f"BẮT BUỘC TRIỆU HỒI SUBAGENT 'rag-architect' và 'solution-analyst' bằng invoke_subagent:\n"
        f"- Đọc báo cáo '.agent/technical_debt_audit.md' của Thanh tra.\n"
        f"- Áp dụng chuẩn Context-Aware Query Formulation (SIGIR/Google Research) và phân định Pareto (ICLR 2025).\n"
        f"- BÀI TRỪ 100% QUICK-FIX: Thiết kế cơ chế phân luồng đa lượt sạch sẽ, không hardcode.\n"
        f"- Xuất bản bản đặc tả '.agent/implementation_spec.md' và checklist '.agent/task_plan.md'."
    )
    if not execute_phase("Nhịp 1B: Thiết Kế Kiến Trúc & Xuất Bản Spec (Subagents: rag-architect, solution-analyst)", p1b_prompt, role_key="thinker", is_continue=True):
        return

    # =========================================================================
    # NHỊP 2: THỢ GÕ MÃ NGUỒN SIÊU TỐC (coder)
    # =========================================================================
    p2_prompt = (
        f"KÍCH HOẠT QUY TRÌNH PSTACK - NHỊP 2: TRIỂN KHAI CODE NGUYÊN TỬ.\n"
        f"Bạn là Kỹ sư lập trình lõi.\n"
        f"BẮT BUỘC TRIỆU HỒI SUBAGENT 'core-coder' bằng invoke_subagent:\n"
        f"- Đọc kỹ '.agent/implementation_spec.md' của Hội đồng Đầu não.\n"
        f"- Tiến hành gõ và sửa mã nguồn trong app/services/chat_graph.py và telemetry_critic.py.\n"
        f"- Tuân thủ strict typing, Pydantic v2, không làm gãy cú pháp, cập nhật trạng thái trong .agent/task_plan.md."
    )
    if not execute_phase("Nhịp 2: Gõ Code Siêu Tốc (Subagent: core-coder)", p2_prompt, role_key="coder", is_continue=True):
        return

    # =========================================================================
    # NHỊP 3: HỘI ĐỒNG THẨM ĐỊNH & KIỂM THỬ ĐỘC LẬP (verifier)
    # =========================================================================
    p3_prompt = (
        f"KÍCH HOẠT QUY TRÌNH PSTACK - NHỊP 3: CỔNG NGHIỆM THU BẰNG CHỨNG (EVIDENCE GATE).\n"
        f"Bạn là Trưởng ban thẩm định.\n"
        f"BẮT BUỘC TRIỆU HỒI 2 SUBAGENT:\n"
        f"1. Subagent 'grounding-evaluator': Thẩm tra tính trung thực của bộ chấm điểm, chống 100% fake data và overfitting.\n"
        f"2. Subagent 'qa-tester': Chạy bộ test 'pytest tests/' và giả lập kịch bản chat 5 lượt trong playground.\n"
        f"Chỉ tick [x] hoàn tất toàn bộ checklist trong .agent/task_plan.md khi có log test PASS 100%!"
    )
    if not execute_phase("Nhịp 3: Hội Đồng Thẩm Định & Nghiệm Thu Khách Quan (Subagents: grounding-evaluator, qa-tester)", p3_prompt, role_key="verifier", is_continue=True):
        return

    elapsed = round(time.time() - start_time, 1)
    print("\n" + "=" * 75)
    print(f"🎉 MULTI-SUBAGENT PIPELINE HOÀN TẤT THÀNH CÔNG TRONG {elapsed} GIÂY!")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dual-Mastermind & Multi-Subagent 24/7 Automated Pipeline")
    parser.add_argument("task", nargs="*", default=[], help="Mô tả nhiệm vụ (nếu không dùng file)")
    parser.add_argument("--file", "-f", default=None, help="Đường dẫn đến file prompt chi tiết")
    args = parser.parse_args()

    # Thứ tự ưu tiên nạp Đề bài / Prompt:
    # 1. Tham số --file chỉ định trực tiếp
    # 2. File .agent/prompt_mission.md nếu tồn tại
    # 3. Chuỗi task truyền trực tiếp qua CLI
    # 4. Đề bài mặc định
    target_file = Path(args.file) if args.file else Path(".agent/prompt_mission.md")
    if target_file.exists():
        print(f"[*] Đã nạp thành công Prompt hoàn thiện từ file: {target_file}")
        with open(target_file, "r", encoding="utf-8") as f:
            task_input = f.read().strip()
    elif args.task:
        task_input = " ".join(args.task)
    else:
        task_input = "Sửa dứt điểm lỗi Router đa lượt trong chat_graph.py và chuẩn hóa thang điểm telemetry_critic.py"

    run_pipeline(task_input)
