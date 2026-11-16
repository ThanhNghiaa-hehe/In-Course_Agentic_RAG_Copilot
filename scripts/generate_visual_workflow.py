"""
Script thiết kế sơ đồ kiến trúc quy trình chuẩn Học thuật / Enterprise Light Theme (Zero AI Slop).
Phong cách: Nền trắng tinh khiết (#ffffff), bố cục thoáng, ít màu sắc nhiễu, phân cấp thị giác rõ ràng.
Dự án: In-Course Agentic RAG Copilot
Tác giả: Sinh viên Trần Thành Nghĩa (MSSV: 23DH112252) — HUFLIT
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path


def draw_cylinder(ax, x, y, w, h, title, subtitle, edge_color="#0f766e", fill_color="#f0fdfa"):
    """Vẽ biểu tượng Database Cylinder chuẩn kỹ thuật."""
    ellipse_h = h * 0.16
    body_h = h - ellipse_h

    # Thân trụ
    rect = patches.Rectangle((x, y + ellipse_h / 2), w, body_h,
                             linewidth=0, facecolor=fill_color, zorder=2)
    ax.add_patch(rect)

    # Đường viền trái, phải
    ax.plot([x, x], [y + ellipse_h / 2, y + h - ellipse_h / 2], color=edge_color, lw=1.6, zorder=3)
    ax.plot([x + w, x + w], [y + ellipse_h / 2, y + h - ellipse_h / 2], color=edge_color, lw=1.6, zorder=3)

    # Đáy trụ (cung dưới)
    bottom_arc = patches.Arc((x + w / 2, y + ellipse_h / 2), w, ellipse_h,
                             angle=0, theta1=180, theta2=360, color=edge_color, lw=1.6, zorder=3)
    bottom_fill = patches.Ellipse((x + w / 2, y + ellipse_h / 2), w, ellipse_h,
                                  facecolor=fill_color, edgecolor="none", zorder=1)
    ax.add_patch(bottom_fill)
    ax.add_patch(bottom_arc)

    # Nắp trụ (ellipse trên)
    top_ellipse = patches.Ellipse((x + w / 2, y + h - ellipse_h / 2), w, ellipse_h,
                                  facecolor="#ccfbf1", edgecolor=edge_color, lw=1.6, zorder=4)
    ax.add_patch(top_ellipse)

    # Text bên trong
    ax.text(x + w / 2, y + h * 0.50, title, ha="center", va="center",
            fontsize=10.5, fontweight="bold", color="#0f172a", fontfamily="sans-serif", zorder=5)
    ax.text(x + w / 2, y + h * 0.27, subtitle, ha="center", va="center",
            fontsize=8.2, color="#334155", fontfamily="monospace", zorder=5)


def draw_step_box(ax, x, y, w, h, badge, title, tech_line, algo_line,
                  accent="#2563eb", bg="#ffffff", border="#cbd5e1"):
    """Vẽ node quy trình nền trắng tối giản, viền sắc nét, không AI slop."""
    box = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.25,rounding_size=0.6",
                                 linewidth=1.3, edgecolor=border, facecolor=bg, zorder=2)
    ax.add_patch(box)

    # Thanh accent mỏng bên trái tạo điểm nhấn tinh tế
    accent_bar = patches.FancyBboxPatch((x - 0.15, y + 0.6), 0.35, h - 1.2,
                                        boxstyle="round,pad=0.0,rounding_size=0.15",
                                        linewidth=0, facecolor=accent, zorder=3)
    ax.add_patch(accent_bar)

    # Badge số thứ tự nhỏ gọn
    ax.text(x + 0.9, y + h - 1.5, badge, ha="left", va="center",
            fontsize=7.8, fontweight="bold", color=accent, fontfamily="monospace", zorder=4)

    # Tiêu đề chính
    ax.text(x + 0.9, y + h - 3.6, title, ha="left", va="center",
            fontsize=10.5, fontweight="bold", color="#0f172a", fontfamily="sans-serif", zorder=4)

    # Đường kẻ phân cách mảnh
    ax.plot([x + 0.9, x + w - 0.9], [y + h - 4.8, y + h - 4.8], color="#e2e8f0", lw=0.9, zorder=3)

    # Công nghệ
    ax.text(x + 0.9, y + h - 6.6, "Công nghệ:", ha="left", va="center",
            fontsize=7.3, fontweight="bold", color="#64748b", fontfamily="sans-serif", zorder=4)
    ax.text(x + 0.9, y + h - 8.2, tech_line, ha="left", va="center",
            fontsize=8.3, fontweight="bold", color="#0f172a", fontfamily="monospace", zorder=4)

    # Kỹ thuật / Thuật toán
    ax.text(x + 0.9, y + 4.3, "Kỹ thuật:", ha="left", va="center",
            fontsize=7.3, fontweight="bold", color="#64748b", fontfamily="sans-serif", zorder=4)
    ax.text(x + 0.9, y + 2.1, algo_line, ha="left", va="center",
            fontsize=8.1, color="#334155", fontfamily="sans-serif", zorder=4)


def draw_arrow(ax, x1, y1, x2, y2, color="#475569", label="", rad=0.0,
               dashed=False, label_offset=(0, 0), bidir=False):
    """Vẽ mũi tên kết nối sạch sẽ với nhãn tùy chọn."""
    arrow_style = "<->" if bidir else "->"
    ls = "--" if dashed else "-"
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=f"{arrow_style},head_width=0.32,head_length=0.5",
                                color=color, lw=1.6, linestyle=ls,
                                connectionstyle=f"arc3,rad={rad}", shrinkA=2, shrinkB=2),
                zorder=5)
    if label:
        mx = (x1 + x2) / 2 + label_offset[0]
        my = (y1 + y2) / 2 + label_offset[1]
        ax.text(mx, my, label, ha="center", va="center",
                fontsize=7.8, fontweight="bold", color=color, fontfamily="monospace",
                bbox=dict(boxstyle="round,pad=0.22", facecolor="#ffffff", edgecolor="#cbd5e1", lw=0.8),
                zorder=6)


def generate_clean_workflow(output_path: str):
    fig, ax = plt.subplots(figsize=(28, 15.75), dpi=150)  # 4200 x 2362 px

    # Nền trắng tinh khiết chuẩn báo cáo khoa học / Enterprise Light
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    # Bảng màu tiết chế, chuyên nghiệp (Slate + Indigo + Teal)
    C_SLATE_900 = "#0f172a"
    C_SLATE_600 = "#475569"
    C_SLATE_300 = "#cbd5e1"
    C_BG_LANE = "#f8fafc"
    C_INDIGO = "#2563eb"
    C_TEAL = "#0f766e"
    C_AMBER = "#b45309"

    # =========================================================================
    # HEADER
    # =========================================================================
    ax.text(3.0, 96.2, "IN-COURSE AGENTIC RAG COPILOT — SYSTEM ARCHITECTURE & WORKFLOW",
            fontsize=20, fontweight="bold", color=C_SLATE_900, fontfamily="sans-serif")
    ax.text(3.0, 93.5, "Luồng xử lý dữ liệu từ Offline Indexing (Stages 1–5) đến Online LangGraph Serving (Stages 6–10) và Quality Gates (Stages 11–12)",
            fontsize=11.5, color=C_SLATE_600, fontfamily="sans-serif")

    # Author tag (tối giản)
    author_box = patches.FancyBboxPatch((69.0, 92.8), 28.0, 4.6, boxstyle="round,pad=0.2,rounding_size=0.5",
                                        linewidth=1.0, edgecolor=C_SLATE_300, facecolor=C_BG_LANE)
    ax.add_patch(author_box)
    ax.text(83.0, 95.8, "Trần Thành Nghĩa  •  MSSV: 23DH112252  •  HUFLIT",
            ha="center", va="center", fontsize=9.8, fontweight="bold", color=C_SLATE_900, fontfamily="sans-serif")
    ax.text(83.0, 93.8, "github.com/ThanhNghiaa-hehe/In-Course_Agentic_RAG_Copilot",
            ha="center", va="center", fontsize=8.5, color=C_INDIGO, fontfamily="monospace")

    ax.plot([3.0, 97.0], [91.3, 91.3], color="#e2e8f0", lw=1.2)

    # =========================================================================
    # SWIMLANE 1: OFFLINE INGESTION & INDEXING PIPELINE (Y: 62 -> 89)
    # =========================================================================
    lane1 = patches.FancyBboxPatch((3.0, 62.5), 94.0, 26.5, boxstyle="round,pad=0.3,rounding_size=0.8",
                                   linewidth=1.1, edgecolor="#cbd5e1", facecolor=C_BG_LANE, zorder=1)
    ax.add_patch(lane1)
    ax.text(4.5, 86.8, "1. OFFLINE KNOWLEDGE INGESTION & INDEXING PIPELINE (STAGES 1 ➔ 5)",
            fontsize=11.5, fontweight="bold", color=C_TEAL, fontfamily="sans-serif")

    # Stage 1: Raw Input + Audio
    draw_step_box(ax, 4.5, 65.5, 16.5, 18.0, "STAGE 1  •  INGESTION", "Video & Audio Extract",
                  "yt-dlp + FFmpeg", "83 bài giảng YouTube\nChuẩn hóa 16kHz Mono PCM",
                  accent=C_TEAL)

    # Stage 2: Whisper + VAD
    draw_step_box(ax, 23.5, 65.5, 17.5, 18.0, "STAGE 2  •  ASR & VAD", "Speech-to-Text + Bias",
                  "faster-whisper + Silero VAD", "VAD 0.35 lọc tạp âm\nHotwords C++/Java + Canonicalizer",
                  accent=C_TEAL)

    # Stage 3: AST Code Chunker
    draw_step_box(ax, 43.5, 65.5, 17.5, 18.0, "STAGE 3  •  AST CHUNKER", "Semantic Code Parsing",
                  "tree-sitter (C++, Java)", "Cắt theo hàm/lớp nguyên vẹn\nGắn approx_video_sec (Phase 2)",
                  accent=C_TEAL)

    # Stage 4: Dual Embedder
    draw_step_box(ax, 63.5, 65.5, 16.5, 18.0, "STAGE 4  •  EMBEDDING", "Dual Vector Encoding",
                  "fastembed (ONNX Runtime)", "Dense: E5-Large (1024-dim)\nSparse: BM25 (passage: prefix)",
                  accent=C_TEAL)

    # Stage 5: Qdrant Cylinder
    draw_cylinder(ax, 82.8, 65.2, 12.5, 18.8, "Qdrant Cloud\nVector DB",
                  "Dense + BM25\nIn-HNSW Index\nUUIDv5 Idempotent",
                  edge_color=C_TEAL, fill_color="#f0fdfa")

    draw_arrow(ax, 21.3, 74.5, 23.2, 74.5, color=C_TEAL)
    draw_arrow(ax, 41.3, 74.5, 43.2, 74.5, color=C_TEAL)
    draw_arrow(ax, 61.3, 74.5, 63.2, 74.5, color=C_TEAL)
    draw_arrow(ax, 80.3, 74.5, 82.5, 74.5, color=C_TEAL, label="Upsert", label_offset=(0, 1.8))

    # =========================================================================
    # SWIMLANE 2: ONLINE LANGGRAPH AGENTIC SERVING PIPELINE (Y: 20 -> 59)
    # =========================================================================
    lane2 = patches.FancyBboxPatch((3.0, 19.5), 94.0, 39.5, boxstyle="round,pad=0.3,rounding_size=0.8",
                                   linewidth=1.1, edgecolor="#cbd5e1", facecolor=C_BG_LANE, zorder=1)
    ax.add_patch(lane2)
    ax.text(4.5, 56.8, "2. ONLINE MULTI-TURN AGENTIC SERVING PIPELINE — LANGGRAPH STATEGRAPH (STAGES 6 ➔ 10)",
            fontsize=11.5, fontweight="bold", color=C_INDIGO, fontfamily="sans-serif")

    # Client / Studio UI (Left)
    draw_step_box(ax, 4.5, 31.5, 14.2, 17.5, "CLIENT  •  3-COL UI", "Learning Studio",
                  "FastAPI SSE + YouTube API", "Syllabus (83 bài) + Video\nClick <timestamp> ➔ seekTo()",
                  accent=C_SLATE_900, bg="#ffffff", border="#94a3b8")

    # Stage 6: Cascade Router
    draw_step_box(ax, 22.2, 31.5, 15.8, 17.5, "STAGE 6  •  ROUTER", "Cascade Intent & NLI",
                  "LinearSVC (2ms) + mDeBERTa", "Phân 4 lớp + Zero-Regex NLI\nKhử câu cụt đa lượt (ARR 98.9%)",
                  accent=C_INDIGO)

    # Stage 7 & 8: Hybrid Search + Rerank
    draw_step_box(ax, 41.5, 31.5, 16.0, 17.5, "STAGE 7–8  •  RETRIEVAL", "Hybrid + Rerank",
                  "Qdrant RRF + bge-reranker", "In-HNSW: lesson_seq <= cur\nCalibrated Sigmoid σ(z)",
                  accent=C_INDIGO)

    # Stage 9: CRAG Grader
    draw_step_box(ax, 61.0, 31.5, 15.8, 17.5, "STAGE 9  •  CRAG", "CRAG Grader & Pareto",
                  "Yan et al. + ICLR 2025", "grounded / out_of_lesson / gap\nWhitelist Timestamp W (0% bịa)",
                  accent=C_INDIGO)

    # Stage 10: Socratic Synthesis
    draw_step_box(ax, 80.3, 31.5, 15.2, 17.5, "STAGE 10  •  SERVING", "Socratic Synthesis",
                  "LangGraph + Guardrails", "Window k=5 (<=2400c), U-Shape\nCấm giải hộ code (SRP 100%)",
                  accent=C_INDIGO)

    # Forward Flow Arrows
    draw_arrow(ax, 19.0, 40.2, 21.9, 40.2, color=C_INDIGO, label="Prompt", label_offset=(0, 1.5))
    draw_arrow(ax, 38.3, 40.2, 41.2, 40.2, color=C_INDIGO, label="course_query", label_offset=(0, 1.5))
    draw_arrow(ax, 57.8, 40.2, 60.7, 40.2, color=C_INDIGO, label="Top-K", label_offset=(0, 1.5))
    draw_arrow(ax, 77.1, 40.2, 80.0, 40.2, color=C_INDIGO, label="Verified", label_offset=(0, 1.5))

    # Bi-directional Hybrid Query to Qdrant Cylinder (Routes cleanly through inter-lane gap)
    draw_arrow(ax, 49.5, 49.3, 89.0, 64.8, color=C_TEAL,
               label="In-HNSW Hybrid Query (query: E5 + BM25)", rad=-0.20, bidir=True, label_offset=(2.0, 2.2))

    # Branch 1: Fast-Path (Chit-chat / Out-of-scope) -> Bottom loop back to UI
    draw_arrow(ax, 30.1, 31.2, 11.6, 31.2, color=C_AMBER,
               label="Fast-Path: chit_chat / out_of_scope (< 50ms, bỏ qua RAG)",
               rad=-0.26, dashed=True, label_offset=(0, -3.3))

    # Branch 2: CRAG Out-of-Lesson / Coverage Gap note
    out_pill = patches.FancyBboxPatch((59.4, 21.5), 19.0, 5.2, boxstyle="round,pad=0.2,rounding_size=0.5",
                                      linewidth=1.0, edgecolor=C_AMBER, facecolor="#fffbeb", zorder=3)
    ax.add_patch(out_pill)
    ax.text(68.9, 24.8, "Nhánh CRAG: out_of_lesson / coverage_gap", ha="center", va="center",
            fontsize=8.2, fontweight="bold", color=C_AMBER, fontfamily="sans-serif", zorder=4)
    ax.text(68.9, 22.8, "Điều hướng sang bài học đúng (Pareto v2.1)", ha="center", va="center",
            fontsize=7.8, color="#78350f", fontfamily="sans-serif", zorder=4)
    draw_arrow(ax, 68.9, 31.2, 68.9, 27.0, color=C_AMBER, dashed=True)

    # Return Stream: Stage 10 -> Client UI (Top arc inside Online lane)
    draw_arrow(ax, 87.9, 49.3, 11.6, 49.3, color=C_INDIGO,
               label="SSE Token Stream + Gợi ý Socratic + Verified <timestamp sec='...'>",
               rad=0.07, label_offset=(0, 2.5))

    # =========================================================================
    # SWIMLANE 3: EVALUATION, QUALITY GATES & BENCHMARKS (Y: 3 -> 16.5)
    # =========================================================================
    lane3 = patches.FancyBboxPatch((3.0, 3.0), 94.0, 13.5, boxstyle="round,pad=0.3,rounding_size=0.8",
                                   linewidth=1.1, edgecolor="#cbd5e1", facecolor="#ffffff", zorder=1)
    ax.add_patch(lane3)
    ax.text(4.5, 14.5, "3. CONTINUOUS EVALUATION & QUALITY GATES (STAGES 11–12)",
            fontsize=11.0, fontweight="bold", color=C_SLATE_900, fontfamily="sans-serif")

    def draw_metric_card(x, y, w, h, title, val, detail, accent=C_INDIGO):
        card = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=0.5",
                                      linewidth=1.0, edgecolor="#e2e8f0", facecolor=C_BG_LANE, zorder=2)
        ax.add_patch(card)
        ax.text(x + 1.1, y + h - 1.8, title, fontsize=9.0, fontweight="bold", color=C_SLATE_600, fontfamily="sans-serif")
        ax.text(x + 1.1, y + 4.3, val, fontsize=17.5, fontweight="bold", color=accent, fontfamily="monospace")
        ax.text(x + 1.1, y + 1.5, detail, fontsize=8.2, color=C_SLATE_600, fontfamily="sans-serif")

    draw_metric_card(4.5, 4.3, 21.5, 8.5, "Stage 11: Intent Router (200 QAs)", "91.0%", "182/200 đạt chuẩn • CRAG Precision 86.5%", C_INDIGO)
    draw_metric_card(28.0, 4.3, 21.5, 8.5, "Stage 12: Anaphora Resolution", "98.94%", "50 Sessions / 222 Turns • Khử câu cụt", C_TEAL)
    draw_metric_card(51.5, 4.3, 21.5, 8.5, "Socratic Refusal Precision", "100.0%", "Zero Code Leak • Không giải hộ bài tập", C_SLATE_900)
    draw_metric_card(75.0, 4.3, 20.5, 8.5, "Context Budget & TS Safety", "100% / 99.1%", "Max 895/2400 chars • Whitelist TS", C_INDIGO)

    # Trace connection from Online Serving to Evaluation
    draw_arrow(ax, 87.8, 31.2, 87.8, 16.8, color=C_SLATE_600, label="Trace Logs", dashed=True, label_offset=(4.0, 0))

    resolved_path = str(Path(output_path).resolve())
    Path(resolved_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(resolved_path, facecolor="#ffffff", edgecolor="none", bbox_inches="tight", dpi=150)
    plt.close()
    print(f"Clean Light-Theme Diagram saved to: {resolved_path}")


if __name__ == "__main__":
    generate_clean_workflow("docs/architecture/end_to_end_workflow.png")
