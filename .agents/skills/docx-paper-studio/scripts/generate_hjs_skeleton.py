"""
Generate a complete HUFLIT Journal of Science (HJS) paper skeleton (.docx)
matching the verified layout of HJS@MTF-GCN_R3.pdf (US Letter, Cambria 10pt,
Page 1 journal banner, Page 2+ running header, centered Roman-numeral sections,
native OMML equations, Three-Line Booktabs tables, dynamic 300-DPI JSON charts,
and bilingual Vietnamese closing abstract block).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from docx_helpers import (
    FONT_HJS,
    add_academic_heading,
    add_author_bio_block,
    add_figure_with_caption,
    add_hjs_journal_headers,
    add_reference_entry,
    add_three_line_table,
    create_hjs_document,
    set_run_font,
)
from hjs_benchmark_charts import plot_multiturn_tiers, plot_stage11_tiers
from omml_math import add_display_equation, add_inline_equation


def _add_hjs_section_h1(doc, title: str):
    return add_academic_heading(doc, title.upper(), level=1, size_pt=12.0, centered=True, italic=False, font_name=FONT_HJS)


def _add_hjs_section_h2(doc, title: str):
    return add_academic_heading(doc, title.upper(), level=2, size_pt=10.0, centered=False, italic=True, font_name=FONT_HJS)


def _add_hjs_para(doc, text: str = "", first_line_indent_cm: float = 0.0, size_pt: float = 10.0, italic: bool = False):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    if first_line_indent_cm > 0:
        p.paragraph_format.first_line_indent = Cm(first_line_indent_cm)
    p.paragraph_format.line_spacing = 1.15
    p.paragraph_format.space_after = Pt(4)
    if text:
        set_run_font(p.add_run(text), name=FONT_HJS, size_pt=size_pt, italic=italic)
    return p


def _add_placeholder_note(doc, note_text: str):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.left_indent = Cm(0.5)
    p.paragraph_format.right_indent = Cm(0.5)
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(5)
    pPr = p._p.get_or_add_pPr()
    pPr.append(parse_xml(f'<w:shd {nsdecls("w")} w:fill="F8FAFC"/>'))
    pPr.append(
        parse_xml(
            f'<w:pBdr {nsdecls("w")}>'
            '<w:left w:val="single" w:sz="12" w:space="6" w:color="4F46E5"/>'
            "</w:pBdr>"
        )
    )
    set_run_font(
        p.add_run(f"[DRAFT FRAME] {note_text}"),
        name=FONT_HJS,
        size_pt=9.5,
        italic=True,
        color_rgb=(51, 65, 85),
    )
    return p


def build_hjs_skeleton(out_docx: Path, benchmarks_dir: Path, figures_dir: Path) -> Path:
    doc = create_hjs_document(
        preset="hjs_journal",
        margin_top_cm=1.9,
        margin_bottom_cm=1.9,
        margin_left_cm=1.8,
        margin_right_cm=1.75,
        font_size_pt=10.0,
        font_name=FONT_HJS,
    )

    eng_title = (
        "PARETO-SUFFICIENT AGENTIC RAG WITH AST-VIDEO SYNCHRONIZATION "
        "FOR SOCRATIC IN-COURSE PROGRAMMING TUTORING"
    )
    add_hjs_journal_headers(
        doc,
        running_title=eng_title,
        author_names="Tran Thanh Nghia, [Advisor Name]",
    )

    # Title
    tp = doc.add_paragraph()
    tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    tp.paragraph_format.space_before = Pt(2)
    tp.paragraph_format.space_after = Pt(6)
    set_run_font(tp.add_run(eng_title), name=FONT_HJS, size_pt=14.0, bold=True, color_rgb=(15, 23, 42))

    # Author
    ap = doc.add_paragraph()
    ap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    ap.paragraph_format.space_after = Pt(2)
    set_run_font(ap.add_run("Tran Thanh Nghia "), name=FONT_HJS, size_pt=10.0, bold=True)
    r_star = ap.add_run("*")
    r_star.font.superscript = True
    set_run_font(r_star, name=FONT_HJS, size_pt=10.0, bold=True)

    # Affiliation
    aff = doc.add_paragraph()
    aff.alignment = WD_ALIGN_PARAGRAPH.CENTER
    aff.paragraph_format.space_after = Pt(2)
    set_run_font(
        aff.add_run(
            "Faculty of Information Technology (Student ID: 23DH112252),\n"
            "Ho Chi Minh City University of Foreign Languages – Information Technology (HUFLIT), Vietnam"
        ),
        name=FONT_HJS,
        size_pt=9.0,
    )

    em = doc.add_paragraph()
    em.alignment = WD_ALIGN_PARAGRAPH.CENTER
    em.paragraph_format.space_after = Pt(8)
    set_run_font(
        em.add_run("*Corresponding author: [student_email@huflit.edu.vn]"),
        name=FONT_HJS,
        size_pt=9.0,
        italic=True,
    )

    # Abstract
    ab = doc.add_paragraph()
    ab.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    ab.paragraph_format.space_after = Pt(5)
    set_run_font(ab.add_run("ABSTRACT — "), name=FONT_HJS, size_pt=9.0, bold=True)
    set_run_font(
        ab.add_run(
            "[Khung tóm tắt mẫu — Nội dung chính thức sẽ được cập nhật sau khi hoàn tất Loop 3 và kiểm chuẩn "
            "--mode e2e]. Bài báo đề xuất kiến trúc In-Course Agentic RAG Copilot phục vụ trợ giảng lập trình theo "
            "phương pháp Socratic, kết hợp truy xuất lai (Multilingual E5-Large + BM25) có lọc trước In-HNSW, "
            "thẩm định ngữ cảnh Corrective RAG đa tầng theo bất đẳng thức Pareto và đồng bộ mốc thời gian video "
            "thông qua ánh xạ cây cú pháp trừu tượng (AST-to-Video Binding)."
        ),
        name=FONT_HJS,
        size_pt=9.0,
    )

    # Keywords
    kw = doc.add_paragraph()
    kw.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    kw.paragraph_format.space_after = Pt(8)
    set_run_font(kw.add_run("Keywords — "), name=FONT_HJS, size_pt=9.0, bold=True)
    set_run_font(
        kw.add_run(
            "Agentic RAG, Corrective RAG, Socratic Tutoring, AST Code Chunking, "
            "Video Timestamp Grounding, Context Sufficiency"
        ),
        name=FONT_HJS,
        size_pt=9.0,
    )

    # I. INTRODUCTION
    _add_hjs_section_h1(doc, "I. INTRODUCTION")
    _add_hjs_para(
        doc,
        "Trong giáo dục lập trình trực tuyến dựa trên video bài giảng dài (30–60 phút), sinh viên thường gặp hai rào cản lớn: "
        "(1) khó định vị chính xác phân đoạn video chứa lời giải thích cho lỗi cú pháp hiện tại, và "
        "(2) các hệ thống hỏi đáp LLM thông thường dễ sinh mã giải bài hộ (solution leakage) hoặc trả lời kiến thức "
        "vượt quá tiến độ bài học (out-of-lesson hallucination).",
        first_line_indent_cm=0.0,
    )
    _add_placeholder_note(
        doc,
        "Mục I sẽ trình bày động lực nghiên cứu, 3 thách thức cốt lõi (Vocabulary Mismatch trên văn nói Whisper, "
        "hiện tượng 'bài cũ nuốt bài mới', và bảo toàn ngữ cảnh đa lượt) cùng danh sách 4 đóng góp khoa học chính.",
    )

    # II. RELATED WORK
    _add_hjs_section_h1(doc, "II. RELATED WORK")
    _add_hjs_section_h2(doc, "A. CORRECTIVE RETRIEVAL-AUGMENTED GENERATION AND CONTEXT SUFFICIENCY")
    _add_placeholder_note(
        doc,
        "Đối chiếu trực tiếp Yan et al. (CRAG, arXiv:2401.15884) [1], chuẩn Context Sufficiency (ICLR 2025) [2], "
        "và hiệu ứng Lost-in-the-Middle của Liu et al. [3].",
    )
    _add_hjs_section_h2(doc, "B. SOCRATIC AI TUTORS AND MULTIMODAL VIDEO-CODE GROUNDING")
    _add_placeholder_note(
        doc,
        "So sánh với các hệ thống RAG đóng hộp và lý giải nguyên lý 'Use First, Build Custom for Domain Core' "
        "(Router LinearSVC + mDeBERTa NLI Arbiter, Tree-sitter AST binding).",
    )

    # III. PROPOSED ARCHITECTURE & FORMULATION
    _add_hjs_section_h1(doc, "III. SYSTEM ARCHITECTURE AND MATHEMATICAL FORMULATION")
    _add_hjs_section_h2(doc, "A. HYBRID RETRIEVAL AND SIGMOID CALIBRATION")

    p_sig = _add_hjs_para(doc, first_line_indent_cm=0.0)
    set_run_font(
        p_sig.add_run(
            "Điểm tương quan thô từ Cross-Encoder thường bị lệch thang đo trên các truy vấn học thuật ngắn; "
            "do đó hệ thống áp dụng chuẩn hóa Logistic Sigmoid "
        ),
        name=FONT_HJS,
        size_pt=10.0,
    )
    add_inline_equation(p_sig, r"\sigma(z) = \frac{1}{1+e^{-z}}", font_size_pt=10.0)
    set_run_font(
        p_sig.add_run(" để ánh xạ điểm tin cậy về miền xác suất [0, 1] trước khi đi qua bộ thẩm định CRAG."),
        name=FONT_HJS,
        size_pt=10.0,
    )

    add_display_equation(
        doc,
        r"S_{\text{hybrid}}(q,d) = \alpha \cdot \cos(E_q, E_d) + (1-\alpha) \cdot \text{BM25}(q,d)",
        eq_number="1",
        content_width_twips=10200,
    )

    _add_hjs_section_h2(doc, "B. PARETO CONTEXT SUFFICIENCY AND PREREQUISITE INVARIANT")
    _add_hjs_para(
        doc,
        "Nhằm ngăn chặn văn nói nhắc lướt ở bài học hiện tại che lấp bài giảng chuyên sâu ở bài tương lai, "
        "bài học tương lai chỉ được phép kích hoạt trạng thái out_of_lesson khi thỏa mãn điều kiện biên độ Pareto:",
        first_line_indent_cm=0.0,
    )
    add_display_equation(
        doc,
        r"S_{\text{future}} - \max(S_{\text{current}}) > \Delta_{\text{margin}}",
        eq_number="2",
        content_width_twips=10200,
    )

    # Table 1: Architectural Invariants (Authentic HJS Full Grid Style)
    add_three_line_table(
        doc,
        caption="Table 1. Core Architectural Components and Verification Thresholds",
        headers=["Component", "Mechanism", "Verified Threshold / Budget"],
        rows=[
            ["Cascade Semantic Router", "LinearSVC + mDeBERTa-v3 NLI Arbiter", "P_oos < 0.75 triggers NLI rescue"],
            ["Hybrid Retrieval", "Multilingual E5-Large + BM25 (In-HNSW)", "lesson_seq <= current_lesson_seq"],
            ["Modality Gate & Pareto", "Video Transcript vs. Tree-sitter AST", "Video >= 0.30, AST >= 0.35, Delta >= 0.12"],
            ["Stateful Context Window", "LangGraph MemorySaver + Summarizer", "k = 5 turns, <= 2,400 chars budget"],
        ],
        col_widths_cm=[4.2, 6.8, 6.2],
        font_size_pt=9.0,
        border_style="hjs_grid",
    )

    # IV. EXPERIMENTAL SETUP
    _add_hjs_section_h1(doc, "IV. EXPERIMENTAL SETUP")
    _add_placeholder_note(
        doc,
        "Mô tả dữ liệu khóa học 83 bài giảng C++/Java, bộ Stage 11 Golden Benchmark (200 câu hỏi đơn lượt theo 4 tầng) "
        "và bộ Multi-Turn Benchmark (50 phiên / 222 lượt hội thoại: Anaphora, Socratic Guardrail, Topic Switch, Budget Stress).",
    )

    # V. EXPERIMENTAL RESULTS (Bound dynamically to existing JSON snapshots, marked as Pre-Loop 3)
    _add_hjs_section_h1(doc, "V. PRELIMINARY RESULTS (PRE-LOOP 3 VISUALIZATION TEST)")
    s11_path = benchmarks_dir / "latest_benchmark_results.json"
    mt_path = benchmarks_dir / "multiturn_benchmark_results.json"

    rows_res = []
    if s11_path.exists():
        s11 = json.loads(s11_path.read_text(encoding="utf-8"))["summary"]
        s11_total = sum(v["total"] for v in s11["tier_breakdown"].values())
        rows_res.append(
            [
                f"Stage 11 Golden ({s11_total} queries)",
                f"{s11['router_accuracy']}% ({s11['router_correct']}/{s11_total})",
                f"{s11['crag_precision']}% ({s11['crag_correct']}/{s11_total})",
                f"{s11['timestamp_safety']}% (Multi-TS)",
                f"{s11['avg_latency_ms']} ms",
            ]
        )
        fig1_png = figures_dir / "fig_stage11_tiers.png"
        plot_stage11_tiers(s11_path, fig1_png)
        add_figure_with_caption(
            doc,
            fig1_png,
            "Figure 1: Stage 11 Golden 200 accuracy breakdown across tiers (Snapshot: Loop 2 baseline).",
            width_cm=15.0,
            italic_body=False,
        )

    if mt_path.exists():
        mt = json.loads(mt_path.read_text(encoding="utf-8"))
        meta = mt["metadata"]
        sm = mt["summary_metrics"]
        rows_res.append(
            [
                f"Multi-Turn ({meta['total_sessions']} sess / {meta['total_turns']} turns)",
                f"{sm['intent_accuracy']}%",
                f"{sm['retrieval_status_accuracy']}%",
                f"{sm['multi_grounding_timestamp_safety_rate']}% (Multi-TS)",
                f"Budget {sm['context_budget_compliance_rate']}%",
            ]
        )
        fig2_png = figures_dir / "fig_multiturn_tiers.png"
        plot_multiturn_tiers(mt_path, fig2_png)
        add_figure_with_caption(
            doc,
            fig2_png,
            "Figure 2: Multi-turn stateful dialogue evaluation across 4 tiers (Mode: retrieval baseline).",
            width_cm=15.4,
            italic_body=False,
        )

    if rows_res:
        add_three_line_table(
            doc,
            caption="Table 2. Snapshot Benchmark Metrics Bound Dynamically from JSON Artifacts (Pending Loop 3 + E2E)",
            headers=["Benchmark Suite", "Router / Intent", "CRAG Status", "Timestamp Grounding", "Latency / Budget"],
            rows=rows_res,
            col_widths_cm=[4.2, 3.3, 3.2, 3.5, 3.0],
            font_size_pt=8.5,
            border_style="hjs_grid",
        )

    # VI. CONCLUSION
    _add_hjs_section_h1(doc, "VI. DISCUSSION AND CONCLUSION")
    _add_placeholder_note(
        doc,
        "Sẽ tổng hợp kết quả cuối cùng sau khi chạy Loop 3 (--mode e2e Socratic Output Guardrail + Ablation Study) "
        "và phân tích các ca biên còn lại.",
    )

    # VII. ACKNOWLEDGMENTS
    _add_hjs_section_h1(doc, "VII. ACKNOWLEDGMENTS")
    _add_placeholder_note(
        doc,
        "Lời cảm ơn dành cho Khoa Công nghệ Thông tin, Trường Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT) "
        "và Giảng viên hướng dẫn đã hỗ trợ định hướng nghiên cứu.",
    )

    # VIII. REFERENCES
    _add_hjs_section_h1(doc, "VIII. REFERENCES")
    refs = [
        "S.-Q. Yan et al., \"Corrective Retrieval Augmented Generation,\" arXiv preprint arXiv:2401.15884, 2024.",
        "H. Joren et al., \"Sufficient Context: A New Lens on Retrieval Augmented Generation Systems,\" in Proc. ICLR, 2025.",
        "N. F. Liu et al., \"Lost in the Middle: How Language Models Use Long Contexts,\" Trans. Assoc. Comput. Linguist., vol. 12, pp. 157–173, 2024.",
        "L. Wang et al., \"Multilingual E5 Text Embeddings: A Technical Report,\" arXiv preprint arXiv:2402.05672, 2024.",
    ]
    for idx, ref in enumerate(refs, start=1):
        add_reference_entry(doc, idx, ref, font_name=FONT_HJS, size_pt=9.5)

    # Bilingual Vietnamese Closing Block (matching HJS@MTF-GCN_R3.pdf page 8)
    vi_title = (
        "KIẾN TRÚC AGENTIC RAG ĐẠT NGƯỠNG ĐỦ NGỮ CẢNH PARETO KẾT HỢP ĐỒNG BỘ AST-VIDEO "
        "CHO TRỢ GIẢNG LẬP TRÌNH THEO PHƯƠNG PHÁP SOCRATIC"
    )
    vp = doc.add_paragraph()
    vp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    vp.paragraph_format.space_before = Pt(14)
    vp.paragraph_format.space_after = Pt(4)
    set_run_font(vp.add_run(vi_title), name=FONT_HJS, size_pt=14.0, bold=True, color_rgb=(15, 23, 42))

    va = doc.add_paragraph()
    va.alignment = WD_ALIGN_PARAGRAPH.CENTER
    va.paragraph_format.space_after = Pt(6)
    set_run_font(va.add_run("Trần Thành Nghĩa, [Tên Giảng Viên Hướng Dẫn]"), name=FONT_HJS, size_pt=10.0, bold=True, italic=True)

    vab = doc.add_paragraph()
    vab.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    vab.paragraph_format.space_after = Pt(4)
    set_run_font(vab.add_run("TÓM TẮT — "), name=FONT_HJS, size_pt=9.0, bold=True)
    set_run_font(
        vab.add_run(
            "[Phần tóm tắt tiếng Việt đối xứng cuối bài theo chuẩn Tạp chí Khoa học HUFLIT — "
            "sẽ đồng bộ nội dung chuẩn xác với Abstract tiếng Anh sau khi chốt số liệu Loop 3]."
        ),
        name=FONT_HJS,
        size_pt=9.0,
    )

    vkw = doc.add_paragraph()
    vkw.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    vkw.paragraph_format.space_after = Pt(10)
    set_run_font(vkw.add_run("Từ khóa — "), name=FONT_HJS, size_pt=9.0, bold=True)
    set_run_font(
        vkw.add_run("Agentic RAG, Corrective RAG, Trợ giảng Socratic, Phân mảnh AST, Đồng bộ mốc thời gian video"),
        name=FONT_HJS,
        size_pt=9.0,
    )

    # Author Biography + Portrait grid (matching page 8 of HJS@MTF-GCN_R3.pdf)
    add_author_bio_block(
        doc,
        bios=[
            {
                "name": "Trần Thành Nghĩa",
                "bio": "hiện đang là sinh viên ngành Công nghệ Thông tin (MSSV: 23DH112252), Trường Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT).",
                "research": "Retrieval-Augmented Generation, NLP Giáo dục, Trợ giảng AI Socratic.",
            },
            {
                "name": "[Tên Giảng Viên Hướng Dẫn]",
                "bio": "[Học vị, đơn vị công tác tại Khoa Công nghệ Thông tin, Trường Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT)].",
                "research": "[Hướng nghiên cứu chính của đồng tác giả].",
            },
        ],
    )

    out_docx.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_docx))
    print(f"[OK] Generated HJS Paper Skeleton -> {out_docx}")
    return out_docx


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Build HJS journal paper skeleton DOCX for verification.")
    parser.add_argument("--out", default="scratch/HJS_Paper_Skeleton.docx")
    parser.add_argument("--benchmarks-dir", default="docs/benchmarks")
    parser.add_argument("--figures-dir", default="scratch/paper_figures")
    args = parser.parse_args()

    build_hjs_skeleton(Path(args.out), Path(args.benchmarks_dir), Path(args.figures_dir))


if __name__ == "__main__":
    main()
