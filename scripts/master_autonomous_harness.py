"""
Master Autonomous Harness & Overnight Verification Suite
In-Course Agentic RAG Copilot — HUFLIT Final Project & HJS Publication Suite

Author Invariant:
- Sole Author: Tran Thanh Nghia (Student ID: 23DH112252), Faculty of Information Technology, HUFLIT.
- Academic Advisor (Consultative Mentorship): M.Sc. Tieu Phung Mai Suong (Acknowledged in Section VII).

Two-Stage Unified Closed Loop (Zero Argon):
STAGE 1: Code Optimization & Sequential Cross-Layer Verification Gates
  - Gate 1: Fast AST Syntax Gate (py_compile app/ & scripts/) + Zero Quick-Fix Diff Audit
  - Gate 2: Sequential Isolated Pytest Regression Gate (11 suites, HF_HUB_OFFLINE=1)
  - Gate 3: E2E Multi-Turn Matrix Harness (e2e_matrix_harness.py --routing-only or live)
  - Gate 4: Macro Benchmark Freshness & Quality Gates (@codebase-auditor: gemini-4-carbon-high on Brain Pool)

STAGE 2: Multi-Subagent Paper Studio & HJS Word Suite (Autonomous Paper Studio)
  - Nhịp 4: Ground-Truth Data Freeze (@grounding-evaluator, gemini-4-hydrogen-high)
  - Nhịp 5: Section III Mathematical Architecture (@rag-architect, gemini-4-neon-high -> carbon-high on Brain Pool)
  - Nhịp 6: Academic Manuscript & Bilingual Suite (@academic-scribe, gemini-4-hydrogen-high -> flash-3.8 on Exec Pool)
  - Nhịp 7: Quality & Compliance Invariant Gate (@codebase-auditor, gemini-4-carbon-high / claude-opus-5-5-high)
  - Nhịp 8: Deterministic OOXML Word Compiler (Produces Variant A & Variant B)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MasterAutonomousHarness")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILL_SCRIPTS = PROJECT_ROOT / ".agents" / "skills" / "docx-paper-studio" / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

SCRATCH_DIR = PROJECT_ROOT / "scratch" / "master_harness"
CHECKPOINT_FILE = SCRATCH_DIR / "master_harness_checkpoint.json"
METRICS_MANIFEST_FILE = SCRATCH_DIR / "verified_metrics_manifest.json"
ANTIGRAVITY_TOOLS = Path(r"D:\PooL_quota\Antigravity Tools\antigravity-server.exe")

QUOTA_ERROR_REGEX = re.compile(
    r"(quota exceeded|rate limit|resource_exhausted|429|too many requests|overloaded|capacity exceeded|credit balance|server error|service unavailable|503|504|invalid model selection|individual quota reached)",
    re.IGNORECASE,
)

# -----------------------------------------------------------------------------
# 1. LIVE CONSOLE PROGRESS TRACKER (CONOUT$ DUAL CHANNEL)
# -----------------------------------------------------------------------------

class MasterProgressTracker:
    """
    Live Console Progress Tracker using direct Windows CONOUT$ channel.
    Displays an interactive real-time visual progress bar directly to the Windows terminal screen,
    even when stdout/stderr is redirected to a file (*> logs/master_harness.log).
    """
    def __init__(self, total_stages: int = 2, total_phases_per_stage: int = 4):
        self.total_stages = total_stages
        self.total_phases = total_phases_per_stage
        self.current_stage = 1
        self.current_phase_idx = 1
        self.phase_start_time = time.time()
        self.start_time = time.time()
        self.current_agent = ""
        self.current_model = ""
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
        if hasattr(sys.stderr, "isatty") and sys.stderr.isatty():
            try:
                sys.stderr.write(full_text)
                sys.stderr.flush()
            except Exception:
                pass

    def start_stage(self, stage_idx: int, title: str):
        self.current_stage = stage_idx
        sep = "=" * 78
        header = f"\n{sep}\n[Master Harness] 🌟 GIAI ĐOẠN {stage_idx}/{self.total_stages}: {title.upper()}\n{sep}\n"
        self._write_console(header, newline=True)

    def start_phase(self, phase_idx: int, phase_title: str, agent_name: str, model_name: str):
        self.current_phase_idx = phase_idx
        self.current_agent = agent_name
        self.current_model = model_name
        self.phase_start_time = time.time()
        overall_phase = ((self.current_stage - 1) * self.total_phases) + phase_idx
        total_all_phases = self.total_stages * self.total_phases
        pct = int((overall_phase - 1) / total_all_phases * 100)
        bar_len = 16
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        header = f"\n[Master Tracker] [{bar}] {pct:>2}% | S{self.current_stage}P{phase_idx}: {phase_title} | Agent: {agent_name} ({model_name})\n"
        self._write_console(header, newline=True)

    def update_subagent(self, line_count: int, snippet: str = ""):
        elapsed = int(time.time() - self.phase_start_time)
        m, s = divmod(elapsed, 60)
        overall_phase = ((self.current_stage - 1) * self.total_phases) + self.current_phase_idx
        total_all_phases = self.total_stages * self.total_phases
        time_frac = min(0.85, elapsed / 300.0)
        pct = int(((overall_phase - 1) + time_frac) / total_all_phases * 100)
        bar_len = 16
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)

        clean_snip = snippet.strip().replace("\r", " ").replace("\n", " ")
        if len(clean_snip) > 28:
            clean_snip = clean_snip[:25] + "..."

        status_line = (
            f"\r[Master Tracker] [{bar}] {pct:>2}% | "
            f"S{self.current_stage} P{self.current_phase_idx} | "
            f"{self.current_agent[:12]:<12} {m:02d}m{s:02d}s | "
            f"Logs: {line_count:>4} | {clean_snip:<28}  "
        )
        self._write_console(status_line, newline=False)

    def end_phase(self, phase_title: str, success: bool = True):
        elapsed = int(time.time() - self.phase_start_time)
        m, s = divmod(elapsed, 60)
        status = "[✔] THÀNH CÔNG" if success else "[!] GIÁN ĐOẠN"
        overall_phase = ((self.current_stage - 1) * self.total_phases) + self.current_phase_idx
        total_all_phases = self.total_stages * self.total_phases
        pct = int(overall_phase / total_all_phases * 100)
        bar_len = 16
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        line = f"\r[Master Tracker] [{bar}] {pct:>2}% | {phase_title}: {status} ({m:02d}m{s:02d}s)                           \n"
        self._write_console(line, newline=True)

    def log_message(self, msg: str):
        self._write_console(f"[Master Tracker] {msg}\n", newline=True)

    def close(self):
        if self._conout:
            try:
                self._conout.close()
            except Exception:
                pass


# -----------------------------------------------------------------------------
# 2. THREADED HEARTBEAT WATCHDOG (ANTI-DEADLOCK)
# -----------------------------------------------------------------------------

class ThreadedSubprocessWatchdog:
    """
    Executes subprocesses with a threaded non-blocking reader and active heartbeat.
    Terminates the process tree if inactive for > inactivity_timeout seconds,
    or if total execution exceeds total_timeout seconds.
    """

    @staticmethod
    def run_command(
        cmd: List[str],
        inactivity_timeout_sec: int = 180,
        total_timeout_sec: int = 1200,
        env: Optional[Dict[str, str]] = None,
        tracker: Optional[MasterProgressTracker] = None,
    ) -> Tuple[int, str, bool]:
        logger.info(f"[Watchdog] Executing: {' '.join(cmd[:6])}...")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            env=env,
        )

        output_lines: List[str] = []
        line_queue: queue.Queue[str] = queue.Queue()

        def _enqueue_output(out_pipe, q: queue.Queue):
            try:
                for line in iter(out_pipe.readline, ""):
                    q.put(line)
                out_pipe.close()
            except Exception:
                pass

        reader_thread = threading.Thread(target=_enqueue_output, args=(process.stdout, line_queue), daemon=True)
        reader_thread.start()

        start_time = time.time()
        last_activity = time.time()
        last_render = time.time()
        line_count = 0
        quota_hit = False

        while True:
            try:
                line = line_queue.get(timeout=0.5)
                line_count += 1
                output_lines.append(line)
                sys.stdout.write(line)
                sys.stdout.flush()
                last_activity = time.time()

                if QUOTA_ERROR_REGEX.search(line):
                    quota_hit = True

                now = time.time()
                if tracker and (now - last_render >= 0.8):
                    tracker.update_subagent(line_count, snippet=line)
                    last_render = now

            except queue.Empty:
                if process.poll() is not None:
                    while not line_queue.empty():
                        drain_line = line_queue.get_nowait()
                        output_lines.append(drain_line)
                        sys.stdout.write(drain_line)
                        sys.stdout.flush()
                    break

            now = time.time()
            if now - last_activity > inactivity_timeout_sec:
                logger.warning(
                    f"[Watchdog ALERT] Tiến trình im lặng quá {inactivity_timeout_sec}s! Đang cưỡng chế hủy cây tiến trình..."
                )
                ThreadedSubprocessWatchdog._kill_process_tree(process.pid)
                return -1, "".join(output_lines), True

            if now - start_time > total_timeout_sec:
                logger.warning(
                    f"[Watchdog ALERT] Tiến trình vượt quá {total_timeout_sec}s! Đang cưỡng chế hủy cây tiến trình..."
                )
                ThreadedSubprocessWatchdog._kill_process_tree(process.pid)
                return -2, "".join(output_lines), True

        process.wait()
        return process.returncode, "".join(output_lines), quota_hit

    @staticmethod
    def _kill_process_tree(pid: int):
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=5)
            else:
                import signal
                os.killpg(os.getpgid(pid), signal.SIGKILL)
        except Exception as e:
            logger.debug(f"[Watchdog] Lỗi khi kill process {pid}: {e}")


# -----------------------------------------------------------------------------
# 3. ACCOUNT POOL MANAGER (ANTI-QUOTA)
# -----------------------------------------------------------------------------

class AccountPoolManager:
    @staticmethod
    def get_active_email() -> str:
        if ANTIGRAVITY_TOOLS.exists():
            try:
                res = subprocess.run(
                    [str(ANTIGRAVITY_TOOLS), "current"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    encoding="utf-8",
                    errors="replace",
                )
                for line in res.stdout.splitlines():
                    if "agy:" in line:
                        email = line.split("agy:")[1].strip()
                        if "@" in email:
                            return email
            except Exception:
                pass
        return "thanhnghiat42@gmail.com"

    @staticmethod
    def rotate_account() -> bool:
        logger.info("[AccountPool] Đang xoay tài khoản trong Antigravity Tools...")
        if ANTIGRAVITY_TOOLS.exists():
            try:
                res = subprocess.run(
                    [str(ANTIGRAVITY_TOOLS), "switch"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    encoding="utf-8",
                    errors="replace",
                )
                logger.info(f"[AccountPool Result] {res.stdout.strip()}")
                return True
            except Exception as e:
                logger.error(f"[AccountPool Error] {e}")
        return False


# -----------------------------------------------------------------------------
# 4. STATE MACHINE & CHECKPOINT PERSISTENCE
# -----------------------------------------------------------------------------

@dataclass
class MasterCheckpoint:
    stage1_done: bool = False
    stage1_quality_report: str = ""
    stage2_done: bool = False
    completed_steps: List[str] = field(default_factory=list)
    step_durations: Dict[str, float] = field(default_factory=dict)
    last_updated: float = 0.0


# -----------------------------------------------------------------------------
# 5. MASTER HARNESS ORCHESTRATOR
# -----------------------------------------------------------------------------

class MasterAutonomousHarness:
    def __init__(self, max_optimization_loops: int = 1):
        self.max_loops = max_optimization_loops
        self.scratch_dir = SCRATCH_DIR
        self.checkpoint_file = CHECKPOINT_FILE
        self.metrics_file = METRICS_MANIFEST_FILE
        self.scratch_dir.mkdir(parents=True, exist_ok=True)

        self.checkpoint = self._load_checkpoint()
        self.tracker = MasterProgressTracker(total_stages=2, total_phases_per_stage=4)

    def _load_checkpoint(self) -> MasterCheckpoint:
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return MasterCheckpoint(**data)
            except Exception:
                pass
        return MasterCheckpoint()

    def _save_checkpoint(self):
        self.checkpoint.last_updated = time.time()
        with open(self.checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(asdict(self.checkpoint), f, indent=2)

    def is_step_done(self, step_name: str) -> bool:
        return step_name in self.checkpoint.completed_steps

    def mark_step_done(self, step_name: str, duration: float):
        if step_name not in self.checkpoint.completed_steps:
            self.checkpoint.completed_steps.append(step_name)
        self.checkpoint.step_durations[step_name] = round(duration, 2)
        self._save_checkpoint()
        logger.info(f"[State Machine] Step '{step_name}' -> COMPLETED ({duration:.1f}s)")

    SEQUENTIAL_PYTEST_SUITES: Tuple[str, ...] = (
        "tests/test_p0_regression.py",
        "tests/test_playground_scenario1_fixes.py",
        "tests/test_playground_e2e_convergence.py",
        "tests/test_playback_temporal_and_disambiguation.py",
        "tests/test_session_7aky9_debug_fixes.py",
        "tests/test_stage13_context_hygiene.py",
        "tests/test_group1_2_optimizations.py",
        "tests/test_e2e_anti_parroting_and_critic.py",
        "tests/test_chat_stream.py",
        "tests/test_search_api.py",
        "tests/test_unseen_edges_and_canonicalizer.py",
        "tests/test_spec004_unified_workflow_hardening.py",
    )

    @staticmethod
    def _latest_mtime(root_dirs: Sequence[Path], suffixes: Tuple[str, ...] = (".py", ".json")) -> float:
        latest = 0.0
        for rdir in root_dirs:
            if not rdir.exists():
                continue
            for p in rdir.rglob("*"):
                if p.is_file() and p.suffix in suffixes:
                    try:
                        mt = p.stat().st_mtime
                        if mt > latest:
                            latest = mt
                    except OSError:
                        pass
        return latest

    # -------------------------------------------------------------------------
    # STAGE 1: CODE OPTIMIZATION & SEQUENTIAL CROSS-LAYER VERIFICATION GATES
    # -------------------------------------------------------------------------
    def run_stage_1_optimization(
        self,
        *,
        force_eval: bool = False,
        live_llm: bool = False,
        e2e_suite: str = "all",
    ) -> bool:
        self.tracker.start_stage(1, "Kiểm Chứng Liên Tầng & Hội Tụ Benchmark")
        logger.info("\n" + "=" * 80)
        logger.info("🔧 [STAGE 1] SEQUENTIAL CROSS-LAYER VERIFICATION HARNESS")
        logger.info("=" * 80)

        offline_env = dict(os.environ)
        offline_env["HF_HUB_OFFLINE"] = "1"
        offline_env["TRANSFORMERS_OFFLINE"] = "1"
        py_exe = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")

        # 1.1 Gate 1: Fast AST Syntax & Anti-Bypass Static Diff Gate
        t0 = time.time()
        self.tracker.start_phase(1, "Gate 1: AST & Zero Quick-Fix Gate", "Compiler", "Python-AST")
        syntax_errors = []
        for folder in ("app", "scripts"):
            for py_path in (PROJECT_ROOT / folder).rglob("*.py"):
                try:
                    import py_compile
                    py_compile.compile(str(py_path), doraise=True)
                except Exception as e:
                    syntax_errors.append(f"{py_path.name}: {e}")

        if syntax_errors:
            logger.error(f"[AST Syntax Gate FAILED] {syntax_errors}")
            self.tracker.end_phase("Gate 1: AST & Zero Quick-Fix Gate", success=False)
            return False

        from thinker_doer_pipeline import audit_anti_bypass_git_diff
        diff_violations = audit_anti_bypass_git_diff()
        if diff_violations:
            logger.error(f"[Anti-Bypass Diff Gate FAILED] {diff_violations}")
            self.tracker.end_phase("Gate 1: AST & Zero Quick-Fix Gate", success=False)
            return False

        self.tracker.end_phase("Gate 1: AST & Zero Quick-Fix Gate", success=True)
        self.mark_step_done("STAGE_1_AST_GATE", time.time() - t0)

        # 1.2 Gate 2: Sequential Isolated Pytest Regression Gate (12 suites)
        t0 = time.time()
        self.tracker.start_phase(2, "Gate 2: Sequential Pytest (12 Suites)", "@qa-tester", "pytest-isolated")
        failed_suites: List[str] = []
        for suite_rel in self.SEQUENTIAL_PYTEST_SUITES:
            suite_path = PROJECT_ROOT / suite_rel
            if not suite_path.exists():
                continue
            logger.info(f"[Gate 2] Running isolated suite: {suite_rel}")
            py_cmd = [py_exe, "-m", "pytest", suite_rel, "-q", "--tb=short"]
            ret_code, stdout, _ = ThreadedSubprocessWatchdog.run_command(
                py_cmd,
                inactivity_timeout_sec=180,
                total_timeout_sec=360,
                env=offline_env,
                tracker=self.tracker,
            )
            if ret_code != 0:
                logger.error(f"[Pytest Gate FAILED] {suite_rel}: {stdout[-300:]}")
                failed_suites.append(suite_rel)

        if failed_suites:
            self.tracker.end_phase("Gate 2: Sequential Pytest", success=False)
            logger.error(f"[Gate 2 FAILED] Các suite lỗi: {failed_suites}")
            return False

        self.tracker.end_phase("Gate 2: Sequential Pytest", success=True)
        self.mark_step_done("STAGE_1_PYTEST_GATE", time.time() - t0)

        # 1.3 Gate 3: E2E Multi-Turn Matrix Harness (routing-only hoặc live_llm)
        t0 = time.time()
        mode_lbl = "live_llm" if live_llm else "routing_only"
        self.tracker.start_phase(3, f"Gate 3: E2E Matrix ({e2e_suite}, {mode_lbl})", "@qa-tester", "e2e-matrix")
        e2e_cmd = [py_exe, "scripts/e2e_matrix_harness.py", "--suite", e2e_suite]
        if not live_llm:
            e2e_cmd.append("--routing-only")
        ret_code, stdout, _ = ThreadedSubprocessWatchdog.run_command(
            e2e_cmd,
            inactivity_timeout_sec=240,
            total_timeout_sec=900,
            env=offline_env,
            tracker=self.tracker,
        )
        if ret_code != 0:
            self.tracker.end_phase("Gate 3: E2E Matrix", success=False)
            logger.error(f"[Gate 3 FAILED] e2e_matrix_harness exit={ret_code}")
            return False

        self.tracker.end_phase("Gate 3: E2E Matrix", success=True)
        self.mark_step_done("STAGE_1_E2E_MATRIX_GATE", time.time() - t0)

        # 1.4 Gate 4: Macro Benchmark Freshness & Quality Gates
        t0 = time.time()
        self.tracker.start_phase(4, "Gate 4: Macro Eval & Quality Gates", "@codebase-auditor", "gemini-4-carbon-high")
        mt_file = PROJECT_ROOT / "docs" / "benchmarks" / "multiturn_benchmark_results.json"
        s11_file = PROJECT_ROOT / "docs" / "benchmarks" / "latest_benchmark_results.json"
        code_mtime = self._latest_mtime([PROJECT_ROOT / "app", PROJECT_ROOT / "data" / "metadata", PROJECT_ROOT / "data" / "curriculum"])
        mt_stale = (not mt_file.exists()) or (mt_file.stat().st_mtime < code_mtime)
        s11_stale = (not s11_file.exists()) or (s11_file.stat().st_mtime < code_mtime)

        if force_eval or mt_stale:
            logger.info("[Gate 4] Chạy lại Multi-Turn Benchmark (50 sessions / 222 turns)...")
            rc_mt, _, _ = ThreadedSubprocessWatchdog.run_command(
                [py_exe, "scripts/run_multiturn_benchmark.py", "--mode", "retrieval"],
                inactivity_timeout_sec=240,
                total_timeout_sec=1200,
                env=offline_env,
                tracker=self.tracker,
            )
            if rc_mt != 0:
                self.tracker.end_phase("Gate 4: Macro Eval & Quality Gates", success=False)
                return False

        if force_eval or s11_stale:
            logger.info("[Gate 4] Chạy lại Stage 11 Golden 200 Benchmark...")
            rc_s11, _, _ = ThreadedSubprocessWatchdog.run_command(
                [py_exe, "scripts/run_rag_benchmark.py", "--dataset", "tests/data/benchmark_golden_dataset.json"],
                inactivity_timeout_sec=240,
                total_timeout_sec=1200,
                env=offline_env,
                tracker=self.tracker,
            )
            if rc_s11 != 0:
                self.tracker.end_phase("Gate 4: Macro Eval & Quality Gates", success=False)
                return False

        from thinker_doer_pipeline import evaluate_quality_gates
        passed, report = evaluate_quality_gates()
        self.checkpoint.stage1_quality_report = report
        self.checkpoint.stage1_done = passed
        self.mark_step_done("STAGE_1_QUALITY_GATE", time.time() - t0)
        self.tracker.end_phase("Gate 4: Macro Eval & Quality Gates", success=passed)
        self.tracker.log_message(f"Kết quả Quality Gates Stage 1: {report}")
        return passed

    # -------------------------------------------------------------------------
    # STAGE 2: MULTI-SUBAGENT PAPER STUDIO & HJS COMPILATION
    # -------------------------------------------------------------------------
    def run_stage_2_paper_studio(self, variants: List[str] = ["A", "B"]) -> bool:
        self.tracker.start_stage(2, "Xưởng Bài Báo Khoa Học (Multi-Subagent Paper Studio)")
        logger.info("\n" + "=" * 80)
        logger.info("🎓 [STAGE 2] MULTI-SUBAGENT PAPER STUDIO & HJS PUBLICATION SUITE")
        logger.info("=" * 80)

        from autonomous_paper_harness import AutonomousPaperHarness
        paper_harness = AutonomousPaperHarness(scratch_dir=self.scratch_dir, benchmarks_dir=PROJECT_ROOT / "docs" / "benchmarks")

        # 2.1 Stage 0: Ground-Truth Freeze
        metrics = paper_harness.run_stage_0_preflight()

        # 2.2 Process each variant
        for var in variants:
            self.tracker.start_phase(2, f"Section III Toán Pareto (Bản {var})", "@rag-architect", "gemini-4-neon-high")
            paper_harness.run_stage_1_architecture_section(metrics, variant=var)
            self.tracker.end_phase(f"Section III Toán Pareto (Bản {var})", success=True)

            self.tracker.start_phase(3, f"Bản Thảo Học Thuật HJS (Bản {var})", "@academic-scribe", "gemini-4-hydrogen-high")
            paper_harness.run_stage_2_manuscript_suite(metrics, variant=var)
            self.tracker.end_phase(f"Bản Thảo Học Thuật HJS (Bản {var})", success=True)

            self.tracker.start_phase(4, f"Đóng Gói Word DOCX (Bản {var})", "Deterministic-Compiler", "Native OMML")
            paper_harness.run_stage_3_compilation(metrics, variant=var)
            self.tracker.end_phase(f"Đóng Gói Word DOCX (Bản {var})", success=True)

        self.checkpoint.stage2_done = True
        self._save_checkpoint()
        return True

    # -------------------------------------------------------------------------
    # MASTER RUNNER
    # -------------------------------------------------------------------------
    def execute(
        self,
        variants: List[str] = ["A", "B"],
        *,
        stage: str = "all",
        force_eval: bool = False,
        live_llm: bool = False,
        e2e_suite: str = "all",
    ):
        start_time = time.time()
        print("\n" + "=" * 80)
        print("🏛️ UNIFIED MASTER AUTONOMOUS HARNESS: TWO-STAGE CLOSED LOOP (ZERO ARGON)")
        print("   Author    : Tran Thanh Nghia (Student ID: 23DH112252)")
        print("   Mentor    : M.Sc. Tieu Phung Mai Suong (HUFLIT)")
        print("   Stage 1   : AST + 11 Sequential Pytests + E2E Matrix + Macro Benchmark")
        print("   Stage 2   : Multi-Subagent Paper Studio (Brain=Neon/Carbon, Exec=Hydrogen)")
        print("=" * 80 + "\n")

        if stage in ("1", "all"):
            st1_ok = self.run_stage_1_optimization(
                force_eval=force_eval,
                live_llm=live_llm,
                e2e_suite=e2e_suite,
            )
            if not st1_ok:
                logger.error("[Master Harness] Giai đoạn 1 chưa hội tụ, dừng trước khi chuyển bước.")
                self.tracker.close()
                sys.exit(1)

        if stage in ("2", "all"):
            self.run_stage_2_paper_studio(variants=variants)

        total_elapsed = time.time() - start_time
        self.tracker.close()

        print("\n" + "=" * 80)
        print(f"🎉 MASTER HARNESS HOÀN TẤT (stage={stage}) TRONG {total_elapsed:.1f} GIÂY!")
        print("=" * 80)
        if stage in ("1", "all"):
            print("  • Stage 1 (Verification) : [✔] AST + 11 Pytest Suites + E2E Matrix + Quality Gates PASS.")
        if stage in ("2", "all"):
            print("  • Stage 2 (Paper Studio) : [✔] Đã đóng gói 2 bản thảo Word (.docx):")
            print("    - Bản A (Kiến trúc & Giải thuật): docs/HJS_Paper_Variant_A_Algorithmic.docx")
            print("    - Bản B (Phương pháp Sư phạm)   : docs/HJS_Paper_Variant_B_Socratic.docx")
            print("    - Bản mặc định đồng bộ          : docs/HJS_Paper_Final.docx")
        print("=" * 80 + "\n")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Unified Master Autonomous Harness (Zero Argon)")
    parser.add_argument("--stage", choices=["1", "2", "all"], default="1", help="Chọn giai đoạn: 1 (Verify RAG - mặc định, bỏ qua Word), 2 (Paper), hoặc all")
    parser.add_argument("--variants", choices=["A", "B", "all"], default="all", help="Chọn biến thể bài báo (A, B hoặc all)")
    parser.add_argument("--e2e-suite", choices=["core", "deep", "all", "M1", "M2", "M3", "S1", "M4", "M5", "M6", "M7", "M8"], default="all", help="Chọn bộ suite cho Gate 3 E2E Matrix")
    parser.add_argument("--force-eval", action="store_true", help="Ép chạy lại Multi-Turn & Golden 200 kể cả khi JSON cũ mới hơn")
    parser.add_argument("--live-llm", action="store_true", help="Chạy Gate 3 E2E Matrix với LLM thật thay vì --routing-only")
    parser.add_argument("--reset", action="store_true", help="Xóa sạch cache checkpoint và chạy lại từ đầu")
    args = parser.parse_args()

    if args.reset:
        if CHECKPOINT_FILE.exists():
            CHECKPOINT_FILE.unlink()
        paper_ckpt = SCRATCH_DIR / "harness_checkpoint.json"
        if paper_ckpt.exists():
            paper_ckpt.unlink()
        logger.info("[Master Harness] Đã xóa cache checkpoint cũ để chạy lại từ đầu.")

    harness = MasterAutonomousHarness()
    target_vars = ["A", "B"] if args.variants == "all" else [args.variants.upper()]
    harness.execute(
        variants=target_vars,
        stage=args.stage,
        force_eval=args.force_eval,
        live_llm=args.live_llm,
        e2e_suite=args.e2e_suite,
    )


if __name__ == "__main__":
    main()
