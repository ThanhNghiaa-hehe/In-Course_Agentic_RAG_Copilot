"""
Script tạo ảnh sơ đồ kiến trúc quy trình End-to-End Workflow chuẩn khoa học (Zero AI-Slop).
Dự án: In-Course Agentic RAG Copilot
Tác giả: Trần Thành Nghĩa (MSSV: 23DH112252) — HUFLIT
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path

def draw_workflow_diagram(output_path: str):
    # Kích thước chuẩn 16:9 sắc nét (Widescreen 24 x 13.5 inches, 150 DPI = 3600 x 2025 px)
    fig, ax = plt.subplots(figsize=(24, 13.5), dpi=150)
    fig.patch.set_facecolor('#0f172a') # Dark slate background for ultra-modern engineering look
    ax.set_facecolor('#0f172a')
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis('off')

    # Color Palette (Tailwind / Modern Engineering UI)
    C_BG_CARD = '#1e293b'
    C_BORDER_CARD = '#334155'
    C_CYAN = '#06b6d4'
    C_BLUE = '#3b82f6'
    C_INDIGO = '#6366f1'
    C_VIOLET = '#8b5cf6'
    C_EMERALD = '#10b981'
    C_AMBER = '#f59e0b'
    C_ROSE = '#f43f5e'
    C_TEXT_MAIN = '#f8fafc'
    C_TEXT_MUTED = '#94a3b8'
    C_TEXT_DIM = '#64748b'

    # 1. Header & Title Banner
    ax.text(50, 96.5, "IN-COURSE AGENTIC RAG COPILOT — END-TO-END SYSTEM WORKFLOW",
            ha='center', va='center', fontsize=20, fontweight='bold', color=C_TEXT_MAIN, fontfamily='sans-serif')
    ax.text(50, 94.2, "Kiến Trúc Hoàn Chỉnh: Từ Offline Ingestion, Online Serving LangGraph Đến CI/CD Quality Gate",
            ha='center', va='center', fontsize=12, color=C_CYAN, fontfamily='sans-serif')
    ax.text(50, 92.3, "Tác giả: Sinh viên Trần Thành Nghĩa (MSSV: 23DH112252) • ĐH Ngoại ngữ - Tin học TP.HCM (HUFLIT)",
            ha='center', va='center', fontsize=10.5, color=C_TEXT_MUTED, fontfamily='sans-serif')

    def draw_card(x, y, w, h, title, stage_badge, subtitle, tech_stack, key_algo, border_color):
        # Card Background
        card = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.5,rounding_size=1.0",
                                     linewidth=1.5, edgecolor=border_color, facecolor=C_BG_CARD)
        ax.add_patch(card)
        
        # Badge
        badge = patches.FancyBboxPatch((x + 1.2, y + h - 2.8), 4.2, 1.8, boxstyle="round,pad=0.2,rounding_size=0.5",
                                      linewidth=0, facecolor=border_color)
        ax.add_patch(badge)
        ax.text(x + 3.3, y + h - 1.9, stage_badge, ha='center', va='center',
                fontsize=8.5, fontweight='bold', color='#ffffff', fontfamily='monospace')
        
        # Title
        ax.text(x + 6.0, y + h - 1.9, title, ha='left', va='center',
                fontsize=11.5, fontweight='bold', color=C_TEXT_MAIN, fontfamily='sans-serif')
        
        # Subtitle
        ax.text(x + 1.2, y + h - 4.5, subtitle, ha='left', va='center',
                fontsize=9.0, color=C_TEXT_MUTED, fontfamily='sans-serif')
        
        # Tech Stack Tag
        ax.text(x + 1.2, y + 4.2, f"Tech: {tech_stack}", ha='left', va='center',
                fontsize=8.5, fontweight='bold', color=C_CYAN, fontfamily='monospace')
        
        # Key Algo / Formula Tag
        ax.text(x + 1.2, y + 1.8, f"Algo: {key_algo}", ha='left', va='center',
                fontsize=8.0, color=C_EMERALD, fontfamily='sans-serif')

    def draw_arrow(x1, y1, x2, y2, color=C_CYAN, label=""):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->,head_width=0.4,head_length=0.6",
                                    color=color, lw=2.0, shrinkA=3, shrinkB=3))
        if label:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2 + 1.2
            ax.text(mx, my, label, ha='center', va='center',
                    fontsize=8.0, fontweight='bold', color=color, fontfamily='monospace',
                    bbox=dict(boxstyle="round,pad=0.2", facecolor=C_BG_CARD, edgecolor=color, lw=0.8))

    # =========================================================================
    # ROW 1: OFFLINE PIPELINE (Stages 1 -> 5)
    # =========================================================================
    # Background Group Box for Offline
    offline_box = patches.FancyBboxPatch((2, 60), 96, 29, boxstyle="round,pad=0.8,rounding_size=1.2",
                                         linewidth=1.2, edgecolor='#047857', facecolor='#064e3b', alpha=0.25)
    ax.add_patch(offline_box)
    ax.text(4, 87.2, "PHÂN TẦNG 1: OFFLINE DATA INGESTION & IDEMPOTENT INDEXING PIPELINE (STAGES 1 ➔ 5)",
            fontsize=12, fontweight='bold', color='#34d399', fontfamily='sans-serif')

    draw_card(3.5, 62, 16.5, 23, "Audio Ingestion", "STAGE 1",
              "Tách xuất luồng âm thanh 16kHz mono\ntừ video bài giảng YouTube/Local.",
              "yt-dlp, FFmpeg", "16kHz Mono 16-bit PCM", C_EMERALD)

    draw_card(23.5, 62, 16.5, 23, "Speech-to-Text", "STAGE 2",
              "Nhận dạng lời thoại & VAD lọc tạp âm,\nđịnh hướng hotwords C++/Java.",
              "faster-whisper, Silero", "Lexicon Biasing, VAD 0.35", C_EMERALD)

    draw_card(43.5, 62, 16.5, 23, "AST Code Chunker", "STAGE 3",
              "Bóc tách ranh giới hàm/lớp AST,\nkhử cắt vụn code, gán video mốc.",
              "tree-sitter (C++/Java)", "approx_video_sec binding", C_EMERALD)

    draw_card(63.5, 62, 16.5, 23, "Dual Embedding", "STAGE 4",
              "Mã hóa ngữ nghĩa Dense 1024-dim\nvà ma trận từ vựng BM25 Sparse.",
              "fastembed (E5 + BM25)", "passage: prefix, 1024-dim", C_EMERALD)

    draw_card(81.5, 62, 15.5, 23, "Qdrant Indexing", "STAGE 5",
              "Lưu trữ vector đa năng hai thành phần,\nIn-HNSW, Pre-filter, Deduplication.",
              "Qdrant Cloud, Python", "In-HNSW, Deterministic UUID", C_EMERALD)

    # Arrows for Row 1
    draw_arrow(20.5, 73.5, 23.0, 73.5, C_EMERALD)
    draw_arrow(40.5, 73.5, 43.0, 73.5, C_EMERALD)
    draw_arrow(60.5, 73.5, 63.0, 73.5, C_EMERALD)
    draw_arrow(80.5, 73.5, 81.0, 73.5, C_EMERALD)

    # Bridge between Offline and Online
    ax.annotate("", xy=(50, 56.5), xytext=(89, 61.5),
                arrowprops=dict(arrowstyle="->,head_width=0.4,head_length=0.6",
                                color='#38bdf8', lw=2.0, connectionstyle="arc3,rad=0.35"))
    ax.text(78, 58.5, "Index Ready (Dual Named Vectors)", fontsize=9, fontweight='bold', color='#38bdf8')

    # =========================================================================
    # ROW 2: ONLINE AGENTIC SERVING PIPELINE (Stages 6 -> 10)
    # =========================================================================
    # Background Group Box for Online
    online_box = patches.FancyBboxPatch((2, 27), 96, 29, boxstyle="round,pad=0.8,rounding_size=1.2",
                                        linewidth=1.2, edgecolor='#1d4ed8', facecolor='#1e3a8a', alpha=0.25)
    ax.add_patch(online_box)
    ax.text(4, 54.2, "PHÂN TẦNG 2: ONLINE AGENTIC SERVING & LANGGRAPH ORCHESTRATION PIPELINE (STAGES 6 ➔ 10)",
            fontsize=12, fontweight='bold', color='#60a5fa', fontfamily='sans-serif')

    draw_card(3.5, 29, 16.5, 23, "Intent Router", "STAGE 6",
              "Phân loại ý định siêu tốc 2.06ms,\nNLI giải cứu câu cụt & chào hỏi.",
              "LinearSVC, mDeBERTa", "Cascade Routing, ARR 98.9%", C_BLUE)

    draw_card(23.5, 29, 16.5, 23, "Hybrid Search", "STAGE 7",
              "Tìm kiếm lai Dense E5 + BM25,\nlọc trước HNSW theo bài hiện tại.",
              "Qdrant In-HNSW Filter", "lesson_seq <= current_seq", C_BLUE)

    draw_card(43.5, 29, 16.5, 23, "Rerank & Sigmoid", "STAGE 8",
              "Chấm điểm tương quan Cross-Encoder\nvới chuẩn hóa Logistic Sigmoid.",
              "bge-reranker-large", "σ(z) = 1 / (1 + e^-z)", C_BLUE)

    draw_card(63.5, 29, 16.5, 23, "CRAG Grader", "STAGE 9",
              "Thẩm định 3 trạng thái tin cậy,\nWhitelist timestamp tuyệt đối.",
              "Yan et al. (arXiv:2401)", "grounded / out_of_lesson", C_BLUE)

    draw_card(81.5, 29, 15.5, 23, "Socratic Serving", "STAGE 10",
              "Phát luồng SSE, Socratic từ chối code,\nđồng bộ video seekTo(sec).",
              "FastAPI SSE, YouTube", "Zero Code Dumping, U-Shape", C_BLUE)

    # Arrows for Row 2
    draw_arrow(20.5, 40.5, 23.0, 40.5, C_BLUE)
    draw_arrow(40.5, 40.5, 43.0, 40.5, C_BLUE)
    draw_arrow(60.5, 40.5, 63.0, 40.5, C_BLUE)
    draw_arrow(80.5, 40.5, 81.0, 40.5, C_BLUE)

    # =========================================================================
    # ROW 3: CONTINUOUS EVALUATION & OBSERVABILITY (Stages 11 & 12)
    # =========================================================================
    eval_box = patches.FancyBboxPatch((2, 2.5), 96, 21.5, boxstyle="round,pad=0.8,rounding_size=1.2",
                                      linewidth=1.2, edgecolor='#b45309', facecolor='#78350f', alpha=0.25)
    ax.add_patch(eval_box)
    ax.text(4, 22.2, "PHÂN TẦNG 3: CONTINUOUS EVALUATION, QUALITY GATES & MULTI-TURN OBSERVABILITY (STAGES 11 & 12)",
            fontsize=12, fontweight='bold', color='#fbbf24', fontfamily='sans-serif')

    draw_card(3.5, 4.5, 22, 16, "Single-Turn Benchmark", "STAGE 11",
              "Khảo thí 200 Golden QAs 4 tầng độc lập:\nRouter 91%, CRAG 86.5%, TS Safety 87%.",
              "Ragas Triad, Pytest", "200 QAs, CI Quality Gate", C_AMBER)

    draw_card(27.5, 4.5, 22, 16, "Multi-Turn Benchmark", "STAGE 12",
              "Khảo thí 50 sessions / 222 turns đa lượt:\nARR 98.9%, SRP 100%, Budget 100%.",
              "LangGraph MemorySaver", "Sliding Window k=5, <=2400c", C_AMBER)

    draw_card(51.5, 4.5, 22, 16, "Guardrails & Safety", "GATEWAY",
              "Security Input & Socratic Output Guardrails\nkhử triệt để Prompt Injection & Leak Code.",
              "Guardrail Filters", "Strict SRP 100%, Whitelist TS", C_ROSE)

    draw_card(75.5, 4.5, 21.5, 16, "Learning Studio", "STUDIO",
              "Giao diện tương tác 3 cột chuẩn EdTech:\nSyllabus 83 bài | Video Canvas | Socratic Chat.",
              "HTML5, Lucide SVG", "YouTube IFrame API Sync", C_VIOLET)

    # Connect Online to Evaluation
    draw_arrow(50, 28.5, 50, 24.5, C_AMBER, label="Trace Log")

    plt.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight', dpi=150)
    plt.close()
    print(f"Diagram successfully saved to {output_path}")

if __name__ == '__main__':
    draw_workflow_diagram('docs/architecture/end_to_end_workflow.png')
