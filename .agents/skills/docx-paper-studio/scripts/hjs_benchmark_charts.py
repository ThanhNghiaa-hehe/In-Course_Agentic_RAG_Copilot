"""
Generate publication-grade 300-DPI PNG charts directly from verified workspace benchmark JSON files
(docs/benchmarks/latest_benchmark_results.json & multiturn_benchmark_results.json).
Zero hardcoded or fabricated numbers.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot_stage11_tiers(s11_json: Path, out_png: Path) -> None:
    data = json.loads(s11_json.read_text(encoding="utf-8"))
    tb = data["summary"]["tier_breakdown"]

    tiers = [
        ("in_scope", "Tier 1\nIn-Scope"),
        ("out_of_lesson", "Tier 2\nOut-of-Lesson"),
        ("adversarial_hybrid", "Tier 3\nAdv. Hybrid"),
        ("chit_chat", "Tier 4\nChit-Chat/OOS"),
    ]
    labels = [lbl for _, lbl in tiers]
    router_pct = [tb[k]["router_ok"] / tb[k]["total"] * 100.0 for k, _ in tiers]
    crag_pct = [tb[k]["status_ok"] / tb[k]["total"] * 100.0 for k, _ in tiers]
    ts_pct = [tb[k]["ts_ok"] / tb[k]["total"] * 100.0 for k, _ in tiers]

    x = list(range(len(labels)))
    width = 0.25

    plt.rcParams["font.family"] = "DejaVu Sans"
    fig, ax = plt.subplots(figsize=(7.2, 4.0), dpi=300)
    b1 = ax.bar([i - width for i in x], router_pct, width, label="Router Accuracy", color="#4f46e5")
    b2 = ax.bar(x, crag_pct, width, label="CRAG Precision", color="#0ea5e9")
    b3 = ax.bar([i + width for i in x], ts_pct, width, label="Timestamp Safety", color="#10b981")

    for bars in (b1, b2, b3):
        for bar in bars:
            h = bar.get_height()
            ax.annotate(
                f"{h:.1f}",
                xy=(bar.get_x() + bar.get_width() / 2, h),
                xytext=(0, 2),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=7.5,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 114)
    ax.set_ylabel("Accuracy (%)", fontsize=9.5)
    ax.set_title("Stage 11 Golden 200 Benchmark Breakdown by Tier", fontsize=10.5, fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3, fontsize=8.5)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] Saved Stage 11 chart -> {out_png}")


def plot_multiturn_tiers(mt_json: Path, out_png: Path) -> None:
    data = json.loads(mt_json.read_text(encoding="utf-8"))
    tb = data["tier_breakdown"]

    tiers = [
        ("tier_1_anaphora", "Tier 1\nAnaphora"),
        ("tier_2_socratic", "Tier 2\nSocratic"),
        ("tier_3_topic_switch", "Tier 3\nTopic Switch"),
        ("tier_4_budget", "Tier 4\nBudget Stress"),
    ]
    labels = [lbl for k, lbl in tiers if k in tb]
    keys = [k for k, _ in tiers if k in tb]
    intent_acc = [tb[k]["intent_accuracy"] for k in keys]
    status_acc = [tb[k]["status_accuracy"] for k in keys]
    multi_ts = [tb[k].get("multi_timestamp_hit_rate", tb[k]["timestamp_hit_rate"]) for k in keys]
    budget = [tb[k]["budget_compliance"] for k in keys]

    x = list(range(len(labels)))
    width = 0.2

    plt.rcParams["font.family"] = "DejaVu Sans"
    fig, ax = plt.subplots(figsize=(7.5, 4.1), dpi=300)
    b1 = ax.bar([i - 1.5 * width for i in x], intent_acc, width, label="Intent Acc", color="#4f46e5")
    b2 = ax.bar([i - 0.5 * width for i in x], status_acc, width, label="CRAG Status Acc", color="#0ea5e9")
    b3 = ax.bar([i + 0.5 * width for i in x], multi_ts, width, label="Multi-Grounding TS", color="#10b981")
    b4 = ax.bar([i + 1.5 * width for i in x], budget, width, label="Budget Compliance", color="#64748b")

    for bars in (b1, b2, b3, b4):
        for bar in bars:
            h = bar.get_height()
            ax.annotate(
                f"{h:.1f}",
                xy=(bar.get_x() + bar.get_width() / 2, h),
                xytext=(0, 2),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=7.0,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 114)
    ax.set_ylabel("Score (%)", fontsize=9.5)
    ax.set_title("Multi-Turn Evaluation (50 Sessions / 222 Turns) by Tier", fontsize=10.5, fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=4, fontsize=8.0)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] Saved Multi-Turn chart -> {out_png}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Generate paper figures directly from benchmark JSONs.")
    parser.add_argument("--benchmarks-dir", default="docs/benchmarks")
    parser.add_argument("--out-dir", default="scratch/paper_figures")
    args = parser.parse_args()

    bdir = Path(args.benchmarks_dir)
    odir = Path(args.out_dir)

    s11 = bdir / "latest_benchmark_results.json"
    mt = bdir / "multiturn_benchmark_results.json"
    if s11.exists():
        plot_stage11_tiers(s11, odir / "fig_stage11_tiers.png")
    if mt.exists():
        plot_multiturn_tiers(mt, odir / "fig_multiturn_tiers.png")


if __name__ == "__main__":
    main()

