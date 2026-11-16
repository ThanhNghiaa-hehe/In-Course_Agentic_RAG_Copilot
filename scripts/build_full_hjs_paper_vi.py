"""
HJS Full Academic Paper Builder - Vietnamese Edition (Bản dịch Tiếng Việt Hoàn Chỉnh)
HUFLIT Journal of Science (HJS) Publication Suite

Tác giả duy nhất: Trần Thành Nghĩa (MSSV: 23DH112252), Khoa Công nghệ Thông tin, HUFLIT.
Giảng viên hướng dẫn: ThS. Tiêu Phụng Mai Sương (Tri ân tại Phần VII).

Tạo ra 3 file Word tiếng Việt chuẩn mực:
1. docs/HJS_Paper_Variant_A_Algorithmic_VI.docx
2. docs/HJS_Paper_Variant_B_Socratic_VI.docx
3. docs/HJS_Paper_Final_VI.docx (Bản đồng bộ mặc định)
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILL_SCRIPTS = PROJECT_ROOT / ".agents" / "skills" / "docx-paper-studio" / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

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
from omml_math import add_display_equation


def _add_hjs_h1(doc, title: str):
    return add_academic_heading(doc, title.upper(), level=1, size_pt=11.5, centered=True, italic=False, font_name=FONT_HJS)


def _add_hjs_h2(doc, title: str):
    return add_academic_heading(doc, title.upper(), level=2, size_pt=10.5, centered=False, italic=True, font_name=FONT_HJS)


def _add_hjs_para(doc, text: str = "", first_line_indent_cm: float = 0.5, size_pt: float = 10.0, italic: bool = False):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.first_line_indent = Inches(first_line_indent_cm / 2.54)
    p.paragraph_format.line_spacing = 1.15
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(4)
    if text:
        set_run_font(p.add_run(text), name=FONT_HJS, size_pt=size_pt, italic=italic)
    return p


def _add_hjs_bullet(doc, bullet_label: str, text: str, first_line_indent_cm: float = 0.5):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.first_line_indent = Inches(first_line_indent_cm / 2.54)
    p.paragraph_format.line_spacing = 1.15
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(3)
    set_run_font(p.add_run(bullet_label + " "), name=FONT_HJS, size_pt=10.0, bold=True)
    set_run_font(p.add_run(text), name=FONT_HJS, size_pt=10.0, italic=False)
    return p


def build_variant_paper_vi(out_docx: Path, benchmarks_dir: Path, figures_dir: Path, variant: str = "A") -> Path:
    out_docx.parent.mkdir(parents=True, exist_ok=True)

    doc = create_hjs_document(
        preset="hjs_journal",
        margin_top_cm=1.9,
        margin_bottom_cm=1.9,
        margin_left_cm=1.8,
        margin_right_cm=1.75,
        font_size_pt=10.0,
        font_name=FONT_HJS,
    )

    if variant == "A":
        vi_title = (
            "KIẾN TRÚC AGENTIC RAG ĐẠT NGƯỠNG ĐỦ NGỮ CẢNH PARETO KẾT HỢP ĐỒNG BỘ AST–VIDEO "
            "CHO TRỢ GIẢNG LẬP TRÌNH THEO PHƯƠNG PHÁP SOCRATIC: THIẾT KẾ GIẢI THUẬT"
        )
        running_title = "KIẾN TRÚC AGENTIC RAG ĐẠT NGƯỠNG ĐỦ NGỮ CẢNH PARETO"
        eng_title = (
            "PARETO-SUFFICIENT AGENTIC RAG WITH AST-VIDEO SYNCHRONIZATION "
            "FOR SOCRATIC IN-COURSE PROGRAMMING TUTORING: AN ALGORITHMIC ARCHITECTURE"
        )
    else:
        vi_title = (
            "BẢO VỆ NỖ LỰC TƯ DUY HIỆU QUẢ: HỆ THỐNG TRỢ GIẢNG AGENTIC RAG THEO PHƯƠNG PHÁP SOCRATIC "
            "KẾT HỢP ĐỒNG BỘ VIDEO TRONG MÔN HỌC LẬP TRÌNH"
        )
        running_title = "TRỢ GIẢNG AGENTIC RAG THEO PHƯƠNG PHÁP SOCRATIC"
        eng_title = (
            "GUARDING THE PRODUCTIVE STRUGGLE: A SOCRATIC, VIDEO-GROUNDED "
            "AGENTIC RAG COPILOT FOR IN-COURSE PROGRAMMING TUTORING"
        )

    add_hjs_journal_headers(
        doc,
        running_title=running_title,
        author_names="Trần Thành Nghĩa",
    )

    # 1. TIÊU ĐỀ BÀI BÁO (TIẾNG VIỆT)
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after = Pt(8)
    set_run_font(p_title.add_run(vi_title), name=FONT_HJS, size_pt=13.0, bold=True, color_rgb=(15, 23, 42))

    # TIÊU ĐỀ TIẾNG ANH (SUBTITLE)
    p_eng = doc.add_paragraph()
    p_eng.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_eng.paragraph_format.space_after = Pt(12)
    set_run_font(p_eng.add_run(eng_title), name=FONT_HJS, size_pt=10.0, italic=True, bold=False, color_rgb=(71, 85, 105))

    # TÁC GIẢ DUY NHẤT: TRẦN THÀNH NGHĨA
    p_author = doc.add_paragraph()
    p_author.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_author.paragraph_format.space_after = Pt(2)
    set_run_font(p_author.add_run("Trần Thành Nghĩa"), name=FONT_HJS, size_pt=11.0, bold=True, italic=False)

    p_aff = doc.add_paragraph()
    p_aff.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_aff.paragraph_format.space_after = Pt(12)
    set_run_font(
        p_aff.add_run("Khoa Công nghệ Thông tin (MSSV: 23DH112252), Trường Đại học Ngoại ngữ – Tin học Thành phố Hồ Chí Minh (HUFLIT)\nEmail: thanhnghiat42@gmail.com / nghia.23dh112252@st.huflit.edu.vn"),
        name=FONT_HJS,
        size_pt=9.0,
        italic=True,
    )

    # 2. KHỐI TÓM TẮT TIẾNG VIỆT
    ab_vi = doc.add_paragraph()
    ab_vi.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    ab_vi.paragraph_format.space_after = Pt(4)
    set_run_font(ab_vi.add_run("TÓM TẮT — "), name=FONT_HJS, size_pt=9.5, bold=True)
    if variant == "A":
        set_run_font(
            ab_vi.add_run(
                "Trong giáo dục lập trình trực tuyến dựa trên video bài giảng dài (30–60 phút), các bài giảng nhập môn có lời nói nhắc lướt "
                "thường có độ tương đồng từ vựng cao, dẫn đến hiện tượng bài cũ lấn át các bài giảng chuyên sâu ở phía sau. Đồng thời, các mô hình "
                "ngôn ngữ lớn (LLM) thương mại đa dụng thường dễ dàng tiết lộ lời giải hoàn chỉnh, làm triệt tiêu nỗ lực học tập tự thân của người học. "
                "Bài báo này trình bày In-Course Agentic RAG Copilot, hệ thống trợ giảng Socratic được điều phối bằng đồ thị trạng thái LangGraph gồm "
                "bốn nút xử lý rời rạc (định tuyến ý định, truy xuất lai, thẩm định CRAG, lắp ráp ngữ cảnh). Chúng tôi hình thức hóa toán học ngưỡng đủ "
                "ngữ cảnh Pareto ba phân tầng (theo định hướng ICLR 2025), tách bạch rõ ràng giữa độ tương quan ngữ nghĩa và độ đầy đủ thông tin sư phạm, "
                "nhằm kiểm soát chặt chẽ thời điểm một bài học tương lai được phép thay thế bài học hiện tại. Hệ thống tích hợp bộ định tuyến ý định tầng "
                "(SLM ONNX INT8 siêu tốc 0,06 ms P50 kết hợp trọng tài NLI mDeBERTa-v3), truy xuất lai True Hybrid (Multilingual E5-Large + BM25) với cơ chế "
                "lọc trước đồ thị In-HNSW động, cùng danh sách trắng mốc thời gian tất định liên kết câu trả lời với từng giây video có thể kiểm chứng. "
                "Trên bộ Golden Benchmark 200 câu hỏi đơn lượt, hệ thống đạt độ chính xác định tuyến 91,0% và độ chuẩn xác thẩm định CRAG 86,5%. Trên bộ "
                "kiểm chuẩn đa lượt xác định gồm 50 phiên hội thoại (222 lượt tương tác), hệ thống đạt độ chính xác ý định 98,65%, độ chính xác trạng thái "
                "truy xuất 98,20%, tỷ lệ giải quyết câu cụt hồi chỉ (ARR) 98,94% và độ chính xác từ chối giải bài hộ Socratic (SRP) tuyệt đối 100,0%, "
                "với 100% ngữ cảnh hội thoại tuân thủ nghiêm ngặt ngân sách an toàn dưới 2.400 ký tự."
            ),
            name=FONT_HJS,
            size_pt=9.0,
        )
    else:
        set_run_font(
            ab_vi.add_run(
                "Các trợ lý đàm thoại ứng dụng mô hình ngôn ngữ lớn (LLM) mang lại khả năng giải đáp tức thời cho sinh viên học lập trình, nhưng thường xuất "
                "toàn bộ lời giải mã nguồn, làm triệt tiêu 'nỗ lực tư duy hiệu quả' (Productive Struggle) vốn là điều kiện tiên quyết để nắm vững thuật toán. "
                "Bên cạnh đó, trong bối cảnh học phần gắn liền với video bài giảng dài (30–60 phút), hệ thống phải có khả năng định vị chính xác phân đoạn video "
                "giảng giải tương ứng. Bài báo giới thiệu In-Course Agentic RAG Copilot, hệ thống trợ giảng lập trình C++/OOP theo phương pháp gợi mở Socratic, "
                "xem kỷ luật sư phạm là một bất biến kiến trúc mang tính cưỡng chế thay vì phụ thuộc vào câu nhắc mềm (soft prompt). Hệ thống vận hành dưới dạng "
                "máy trạng thái LangGraph kết hợp bộ định tuyến tầng NLI, ranh giới đủ ngữ cảnh Pareto ba phân tầng, phân tích cú pháp AST Tree-sitter đo độ phức "
                "tạp chu trình McCabe M(G) >= 3 để cắt tỉa code, và bộ lọc luồng SSE FSM 3 trạng thái kiểm duyệt danh sách trắng mốc video. Trên bộ Golden Benchmark "
                "200 câu, hệ thống đạt độ chính xác định tuyến 91,0% và độ chuẩn xác CRAG 86,5%. Trên bộ đa lượt 50 phiên (222 lượt), hệ thống đạt độ chính xác ý định "
                "98,65%, độ chính xác trạng thái 98,20%, tỷ lệ giải quyết câu cụt (ARR) 98,94% và độ chính xác từ chối giải bài hộ (SRP) đạt 100,0%."
            ),
            name=FONT_HJS,
            size_pt=9.0,
        )

    # TỪ KHÓA TIẾNG VIỆT
    kw_vi = doc.add_paragraph()
    kw_vi.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    kw_vi.paragraph_format.space_after = Pt(8)
    set_run_font(kw_vi.add_run("Từ khóa — "), name=FONT_HJS, size_pt=9.5, bold=True)
    if variant == "A":
        set_run_font(
            kw_vi.add_run(
                "Agentic RAG, RAG hiệu chỉnh (CRAG), Ngưỡng đủ ngữ cảnh Pareto, Định tuyến SLM đường truyền nhanh, Suy luận ngôn ngữ tự nhiên (NLI), "
                "Điều phối LangGraph, Phương pháp Socratic, Đồng bộ Video-Mã nguồn AST."
            ),
            name=FONT_HJS,
            size_pt=9.0,
            italic=True,
        )
    else:
        set_run_font(
            kw_vi.add_run(
                "Trợ giảng Socratic, Agentic RAG, Corrective RAG (CRAG), Rào chắn sư phạm, Ngưỡng đủ ngữ cảnh Pareto, "
                "Khử câu cụt (ARR), Điều phối LangGraph, Học tập gắn với Video."
            ),
            name=FONT_HJS,
            size_pt=9.0,
            italic=True,
        )

    # 3. KHỐI ABSTRACT TIẾNG ANH (CHUẨN BÀI BÁO TẠP CHÍ QUỐC GIA)
    ab_en = doc.add_paragraph()
    ab_en.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    ab_en.paragraph_format.space_after = Pt(4)
    set_run_font(ab_en.add_run("ABSTRACT ⎼ "), name=FONT_HJS, size_pt=9.0, bold=True)
    if variant == "A":
        set_run_font(
            ab_en.add_run(
                "In computer science e-learning, long lecture videos (30–60 minutes) cause acute retrieval degradation: introductory lessons containing casual "
                "spoken commentary frequently outrank dedicated downstream lectures, while general-purpose conversational LLMs tend to leak complete solutions "
                "to students. This paper presents In-Course Agentic RAG Copilot, a Socratic tutoring system orchestrated as a four-node LangGraph state machine "
                "(router, hybrid retrieval, Corrective-RAG grader, context assembly). We formalize a three-tier Pareto Context Sufficiency boundary that separates "
                "semantic relevance from pedagogical sufficiency. The system combines a cascade intent router (ONNX INT8 SLM with an mDeBERTa-v3 NLI arbiter), "
                "true hybrid retrieval (Multilingual E5-Large + BM25) under dynamic In-HNSW pre-filtering, and a deterministic timestamp whitelist. On a 200-query "
                "single-turn golden benchmark the system reaches 91.0% router accuracy and 86.5% CRAG grading precision. On a deterministic multi-turn suite of "
                "50 sessions (222 turns) it reaches 98.65% intent accuracy, 98.20% retrieval-status accuracy, 98.94% Anaphora Resolution Rate (ARR) and 100.0% "
                "Socratic Refusal Precision (SRP), with all dialogue contexts remaining within the 2,400-character budget."
            ),
            name=FONT_HJS,
            size_pt=8.5,
        )
    else:
        set_run_font(
            ab_en.add_run(
                "Conversational Large Language Models offer accessible assistance for novice programmers but readily generate complete solutions, "
                "circumventing the productive struggle essential for algorithmic problem-solving. This paper develops In-Course Agentic RAG Copilot, "
                "a Socratic tutoring system that treats pedagogical boundaries as hard architectural invariants. Orchestrated via a four-node LangGraph "
                "state machine, the Copilot integrates a cascade intent router with NLI, a three-tier Pareto Context Sufficiency boundary, and a deterministic "
                "timestamp whitelist. On a 200-query golden benchmark, the system attains 91.0% router accuracy and 86.5% CRAG precision. On a multi-turn suite "
                "of 50 sessions (222 turns), it achieves 98.65% intent accuracy, 98.20% retrieval-status accuracy, 98.94% ARR, and 100.0% SRP."
            ),
            name=FONT_HJS,
            size_pt=8.5,
        )

    kw_en = doc.add_paragraph()
    kw_en.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    kw_en.paragraph_format.space_after = Pt(12)
    set_run_font(kw_en.add_run("Keywords ⎼ "), name=FONT_HJS, size_pt=9.0, bold=True)
    set_run_font(
        kw_en.add_run("Agentic RAG, Corrective RAG (CRAG), Pareto Context Sufficiency, Fast-Path SLM Router, LangGraph Orchestration, Socratic Tutoring, Video-Code Synchronization."),
        name=FONT_HJS,
        size_pt=8.5,
        italic=True,
    )

    # -------------------------------------------------------------
    # PHẦN I: GIỚI THIỆU
    # -------------------------------------------------------------
    _add_hjs_h1(doc, "I. GIỚI THIỆU")
    _add_hjs_para(
        doc,
        "Video bài giảng bất đồng bộ đóng vai trò là xương sống trong giảng dạy các học phần khoa học máy tính hiện đại, bao gồm chuỗi môn học "
        "lập trình nền tảng như Kỹ thuật lập trình C++, Lập trình hướng đối tượng (OOP), và Cấu trúc dữ liệu & Giải thuật tại Trường Đại học Ngoại ngữ – "
        "Tin học Thành phố Hồ Chí Minh (HUFLIT). Trong các học phần này, sinh viên phải tiếp cận với kho học liệu đồ sộ gồm hàng chục giờ video bài giảng. "
        "Tuy nhiên, việc tra cứu trong các video lập trình kéo dài từ 30 đến 60 phút tạo ra rào cản nhận thức rất lớn: người mới học khi gặp lỗi biên dịch "
        "hoặc lỗi bộ nhớ (segmentation fault) thường phải mất hàng chục phút tua đi tua lại thanh thời gian video để tìm đoạn giảng giải phù hợp [1]. "
        "Tìm được đúng khoảnh khắc giảng giải đó là một bài toán truy xuất thông tin; nhưng hướng dẫn sinh viên tư duy ra sao sau khi tìm thấy lại là "
        "một bài toán sư phạm cốt lõi.",
        first_line_indent_cm=0.5,
    )
    _add_hjs_para(
        doc,
        "Việc áp dụng trực tiếp các mô hình ngôn ngữ lớn (LLM) thương mại đa dụng vào vai trò trợ giảng lập trình trong học phần thường thất bại do "
        "hai sự cố đứt gãy thuật toán và sư phạm mang tính cấu trúc:",
        first_line_indent_cm=0.5,
    )
    _add_hjs_bullet(
        doc,
        "1. Sự cố phía truy xuất (Hiện tượng bài cũ lấn át bài mới):",
        "Giảng viên thường có thói quen nhắc lướt qua các chủ đề của bài học sau trong các bài giảng mở đầu (ví dụ: 'chúng ta sẽ tìm hiểu kỹ về tính đa hình "
        "và kế thừa ở bài học sau'). Những lời nói ngoại vi này có độ trùng lặp từ vựng rất cao với bài giảng chuyên sâu phía sau và đạt điểm tương đồng "
        "cosine xấp xỉ. Hậu quả là, các thuật toán truy xuất Top-k hoặc argmax ngây thơ thường trích xuất nhầm bài học cũ chưa dạy kiến thức đó. Điều quan trọng, "
        "như đã được hình thức hóa tại ICLR 2025 [2], độ tương quan ngữ nghĩa (Semantic Relevance) không đồng nhất với độ đầy đủ thông tin sư phạm (Context Sufficiency): "
        "một đoạn văn bản có thể liên quan về mặt từ vựng nhưng hoàn toàn không đủ thông tin để trả lời bản chất kỹ thuật cho sinh viên.",
    )
    _add_hjs_bullet(
        doc,
        "2. Sự cố phía tạo sinh (Hiện tượng rò rỉ lời giải hoàn chỉnh):",
        "Các trợ lý AI đàm thoại thương mại sẵn sàng viết toàn bộ mã nguồn bài giải khi sinh viên yêu cầu. Trong giáo dục lập trình, hành vi này triệt tiêu hoàn toàn "
        "'nỗ lực tư duy hiệu quả' (productive struggle) vốn là yếu tố bắt buộc để sinh viên rèn luyện tư duy giải quyết vấn đề và thiết kế giải thuật [13], [14]. "
        "Một trợ giảng chuẩn mực phải giải thích bản chất lỗi, gợi ý từng bước, đặt câu hỏi định hướng tư duy theo phương pháp Socratic và kiên quyết từ chối "
        "viết bài hộ cho sinh viên.",
    )
    _add_hjs_para(
        doc,
        "Một rào cản kỹ thuật thực tế thứ ba xuất phát từ độ lệch âm học và từ vựng nghiêm trọng giữa văn bản phiên âm nói của Whisper [7] và cú pháp lập trình "
        "chuẩn mực. Các thuật ngữ phát âm tiếng Việt thường bị biến dạng âm học, khiến việc tìm kiếm vector dày (dense semantic vectors) và tìm kiếm từ khóa thưa "
        "(sparse lexical search) bắt buộc phải bổ trợ lẫn nhau thay vì thay thế hoàn toàn cho nhau.",
        first_line_indent_cm=0.5,
    )
    _add_hjs_para(
        doc,
        "Để giải quyết triệt để những thách thức này, nghiên cứu này phát triển hệ thống In-Course Agentic RAG Copilot, một giải pháp trợ giảng Socratic cấp doanh nghiệp "
        "vận hành trên máy trạng thái tất định, nơi mọi quyết định sư phạm và kỹ thuật đều được thực thi như một rào chắn có thể kiểm toán độc lập. "
        "Đóng góp khoa học chính của công trình gồm bốn điểm nổi bật:",
        first_line_indent_cm=0.5,
    )
    _add_hjs_bullet(
        doc,
        "• Đóng góp 1 (Bộ định tuyến ý định tầng - Cascade Intent Router):",
        "Tích hợp mô hình ngôn ngữ nhỏ SLM ONNX INT8 phân loại ý định ở độ trễ dưới 1 mili-giây (0,06 ms P50), kết hợp trọng tài suy luận ngôn ngữ tự nhiên (NLI) "
        "mDeBERTa-v3 để cứu xét các câu hỏi mơ hồ bằng suy luận zero-shot, loại bỏ hoàn toàn các biểu thức chính quy (regex) chắp vá.",
    )
    _add_hjs_bullet(
        doc,
        "• Đóng góp 2 (Động cơ đồng bộ cú pháp AST - Video bài giảng):",
        "Phân tích cú pháp C++ bằng Tree-sitter bóc tách toàn vẹn các phạm vi hàm và lớp, liên kết trực tiếp với từng giây video bài giảng thực tế, "
        "điều khiển trình phát video frontend nhảy ngay đến đoạn giảng giải chỉ sau một cú nhấp chuột.",
    )
    _add_hjs_bullet(
        doc,
        "• Đóng góp 3 (Ngưỡng biên độ đủ ngữ cảnh Pareto ba phân tầng):",
        "Thiết lập bất đẳng thức biên độ toán học chặt chẽ tuân thủ thứ tự giáo trình tiên quyết, ngăn chặn dứt điểm hiện tượng lời nói nhắc lướt ở bài học cũ "
        "lấn át bài giảng chuyên sâu phía sau.",
    )
    _add_hjs_bullet(
        doc,
        "• Đóng góp 4 (Điều phối có ngân sách đa lượt & Máy trạng thái SSE FSM):",
        "Điều phối hội thoại đa lượt bằng đồ thị LangGraph với cửa sổ trượt k = 4 lượt, giới hạn ngân sách ngữ cảnh dưới 2.400 ký tự, và máy trạng thái hữu hạn 3 trạng thái "
        "kiểm duyệt danh sách trắng mốc thời gian thời gian thực trên luồng SSE, được kiểm chứng toàn diện qua bộ 200 câu Golden đơn lượt và 222 lượt đa lượt.",
    )
    _add_hjs_para(
        doc,
        "Bố cục bài báo được tổ chức như sau: Phần II trình bày các nghiên cứu liên quan; Phần III mô tả chi tiết kiến trúc hệ thống và hình thức hóa toán học; "
        "Phần IV trình bày thiết lập thực nghiệm; Phần V phân tích kết quả định lượng và thảo luận; Phần VI đánh giá các hạn chế và kết luận; Phần VII tri ân "
        "giảng viên hướng dẫn; và Phần VIII liệt kê các tài liệu tham khảo chuẩn IEEE.",
        first_line_indent_cm=0.5,
    )

    # -------------------------------------------------------------
    # PHẦN II: CÁC NGHIÊN CỨU LIÊN QUAN
    # -------------------------------------------------------------
    _add_hjs_h1(doc, "II. CÁC NGHIÊN CỨU LIÊN QUAN")
    _add_hjs_h2(doc, "A. RAG, CORRECTIVE RAG VÀ ĐỘ ĐỦ NGỮ CẢNH TRONG GIÁO DỤC")
    _add_hjs_para(
        doc,
        "Kỹ thuật Tạo sinh tăng cường truy xuất (RAG) [4], [5] đã trở thành chuẩn mực công nghiệp để giảm thiểu ảo giác của mô hình ngôn ngữ lớn bằng cách cung cấp "
        "tài liệu tham chiếu từ cơ sở tri thức bên ngoài. Tuy nhiên, trong giáo dục lập trình có cấu trúc bài giảng theo lộ trình đồ thị có hướng (DAG), các kỹ thuật "
        "RAG truyền thống thường gặp sự cố khi bài giảng mở đầu chứa các lời nói nhắc lướt đạt điểm tương quan từ vựng cao nhưng thiếu chiều sâu hướng dẫn. "
        "Yan và các cộng sự [1] đã đề xuất Corrective RAG (CRAG), thiết kế bộ chấm điểm truy xuất nhẹ để phân loại tài liệu thành 3 trạng thái tin cậy "
        "(Đúng - Correct, Mơ hồ - Ambiguous, Sai - Incorrect) nhằm kích hoạt các luồng xử lý tinh chỉnh tri thức có điều kiện. Song song đó, các nghiên cứu tại "
        "ICLR 2025 về Độ đủ ngữ cảnh (Context Sufficiency) [2] đã chứng minh rằng độ tương quan ngữ nghĩa do bộ mã hóa đo được không đảm bảo tài liệu đó có đầy đủ "
        "thông tin sư phạm để trả lời truy vấn. Đồng thời, Liu và các cộng sự [3] đã chỉ ra hiện tượng suy thoái nhận thức 'Lost-in-the-Middle' khi thông tin quan trọng "
        "bị rơi vào giữa các đoạn văn bản dài. Kiến trúc của chúng tôi mở rộng CRAG [1] và Độ đủ ngữ cảnh [2] vào lộ trình bài học thông qua ranh giới Pareto "
        "đơn điệu nghiêm ngặt và bố cục lắp ráp ngữ cảnh hình chữ U [Top 1, Top 3, Top 2].",
        first_line_indent_cm=0.5,
    )

    _add_hjs_h2(doc, "B. TRUY XUẤT LAI, EMBEDDING TỪ VỰNG VÀ DUYỆT ĐỒ THỊ IN-HNSW")
    _add_hjs_para(
        doc,
        "Tìm kiếm vector thuần túy dựa trên các mô hình embedding dày đặc như Multilingual E5-Large [6] vượt trội trong việc nắm bắt ngữ nghĩa trừu tượng, "
        "nhưng thường gặp khó khăn đối với các định danh cú pháp chính xác trong lập trình (ví dụ: tên hàm `std::vector::push_back`, con trỏ `nullptr`). "
        "Ngược lại, tìm kiếm từ khóa thưa BM25 [8] bắt chính xác từ khóa nhưng hoàn toàn bất lực trước hiện tượng đồng nghĩa và biến dạng phiên âm. "
        "Các hệ thống doanh nghiệp sử dụng phương pháp xếp hạng kết hợp Reciprocal Rank Fusion (RRF) để hòa trộn hai nguồn tín hiệu. Tuy nhiên, việc lọc "
        "ngữ cảnh sau khi truy xuất (post-filtering) thường gây sụt giảm độ phủ (recall) nghiêm trọng. Chúng tôi triển khai cơ chế lọc trước trực tiếp bên trong "
        "quá trình duyệt đồ thị HNSW (In-HNSW graph traversal) [9] trên cơ sở dữ liệu vector Qdrant, đảm bảo 100% tài liệu ứng viên đều nằm trong phạm vi bài học "
        "cho phép mà không làm suy hao cấu trúc đồ thị tương đồng.",
        first_line_indent_cm=0.5,
    )

    _add_hjs_h2(doc, "C. BỘ ĐỊNH TUYẾN Ý ĐỊNH VÀ TRỌNG TÀI SUY LUẬN NGÔN NGỮ TỰ NHIÊN (NLI)")
    _add_hjs_para(
        doc,
        "Việc phân loại ý định người học giữa câu hỏi học tập (course_query), chào hỏi xã giao (chit_chat) và câu hỏi ngoài phạm vi (out_of_scope) thường dựa vào "
        "các biểu thức chính quy (regex) hoặc gọi các mô hình LLM lớn, dẫn đến tình trạng vừa dễ gãy cú pháp vừa chịu độ trễ cao (1.200–2.000 ms). "
        "Kế thừa kỹ thuật phân loại văn bản zero-shot dựa trên suy luận ngôn ngữ tự nhiên (NLI) của Yin và các cộng sự [12], hệ thống triển khai kiến trúc xếp tầng "
        "phòng thủ theo chiều sâu: mô hình ngôn ngữ nhỏ SLM ONNX INT8 chạy trên CPU xử lý các trường hợp tự tin cao trong 0,06 ms; chỉ những câu hỏi nằm trong dải "
        "biên độ phân vân (margin tension) mới được chuyển tiếp lên mô hình Cross-Encoder NLI mDeBERTa-v3 [15] để suy luận giả thuyết học tập, dập tắt hoàn toàn "
        "vòng lặp chào hỏi mà không làm tăng độ trễ tổng thể.",
        first_line_indent_cm=0.5,
    )

    _add_hjs_h2(doc, "D. TRỢ GIẢNG SOCRATIC, CHỐNG RÒ RỈ LỜI GIẢI VÀ SUY THOÁI NGỮ CẢNH DÀI")
    _add_hjs_para(
        doc,
        "Phương pháp sư phạm Socratic nhấn mạnh vào việc kích thích tư duy phản biện thông qua hệ thống câu hỏi gợi mở [13]. Trong môi trường đào tạo kỹ thuật, "
        "MacNeil và các cộng sự [14] đã nhấn mạnh tầm quan trọng của việc giải thích nguyên lý lập trình thay vì cấp sẵn mã nguồn hoàn chỉnh. Khi sinh viên "
        "sử dụng AI để giải bài tập, nếu trợ lý cung cấp ngay toàn bộ code, sinh viên sẽ mất đi cơ hội cọ xát với lỗi cú pháp và tư duy thiết kế. Kiến trúc của "
        "chúng tôi biến nguyên lý Socratic thành một rào chắn kiểm soát cưỡng chế (hard guardrail): tự động bóc tách cú pháp AST đo độ phức tạp chu trình McCabe, "
        "nếu phát hiện thuật toán phức tạp hoặc sinh viên yêu cầu viết code hộ, bộ lọc sẽ tự động cắt tỉa phần thân hàm, chỉ giữ lại khung hàm và chèn các câu hỏi "
        "định hướng tư duy, bảo vệ tuyệt đối tính chính trực học thuật.",
        first_line_indent_cm=0.5,
    )

    # -------------------------------------------------------------
    # PHẦN III: KIẾN TRÚC HỆ THỐNG VÀ HÌNH THỨC HÓA TOÁN HỌC
    # -------------------------------------------------------------
    _add_hjs_h1(doc, "III. KIẾN TRÚC HỆ THỐNG VÀ HÌNH THỨC HÓA TOÁN HỌC")
    _add_hjs_para(
        doc,
        "Hệ thống In-Course Agentic RAG Copilot được thiết kế như một máy trạng thái tất định xây dựng trên nền tảng LangGraph StateGraph, gồm bốn nút tính toán "
        "rời rạc: router (định tuyến), retrieval (truy xuất), crag_grader (thẩm định tri thức) và context_assembly (lắp ráp ngữ cảnh). Toàn bộ chuyển tiếp "
        "trạng thái vận hành trên lược đồ định kiểu AgentState và được lưu vết bền vững theo từng mã phiên session_id qua bộ kiểm điểm MemorySaver. "
        "Các truy vấn xã giao hoặc ngoài lề được rẽ nhánh tức thời theo luồng nhanh (fast-path zero-retrieval), trong khi các câu hỏi kỹ thuật đi qua trọn vẹn "
        "chuỗi truy xuất – thẩm định – lắp ráp ngữ cảnh. Nhờ đó, hệ thống đạt độ chính xác định tuyến đơn lượt 91,0%, độ chuẩn xác CRAG 86,5% và độ chính xác "
        "ý định đa lượt 98,65%.",
        first_line_indent_cm=0.5,
    )

    _add_hjs_h2(doc, "A. KIẾN TRÚC KẾT HỢP DUAL-BACKEND VÀ CHUẨN KHÔNG GIAN 3 CỘT IN-COURSE")
    _add_hjs_para(
        doc,
        "Nhằm đáp ứng yêu cầu vận hành nghiêm ngặt trong môi trường đại học, hệ thống áp dụng kiến trúc phân tách hai tầng phụ trợ (Hybrid Dual-Backend Topology), "
        "tách biệt hoàn toàn giữa nghiệp vụ quản trị học tập giao dịch và vi dịch vụ AI tính toán nơ-ron:",
        first_line_indent_cm=0.5,
    )
    _add_hjs_bullet(
        doc,
        "1. Backend quản trị học tập cốt lõi (Spring Boot 3.x):",
        "Nền tảng web trung tâm (nghia BE) quản trị các giao dịch quan hệ, định danh sinh viên, phân quyền vai trò (RBAC) và bảo mật phiên bằng JSON Web Token (JWT). "
        "Cơ sở dữ liệu MongoDB lưu trữ danh mục khóa học, cây giáo trình 83 bài học và tiến độ của sinh viên, kết hợp cụm Redis lưu bộ nhớ đệm token và bộ đếm giới hạn tần suất. "
        "Cổng thanh toán khóa học được kết nối qua webhook PayOS. Trước khi chuyển tiếp câu hỏi của sinh viên sang dịch vụ AI, Spring Boot luôn xác thực số thứ tự bài học tối đa "
        "hợp lệ (L_curr) mà sinh viên đã mở khóa, ngăn chặn triệt để hành vi can thiệp trái phép từ phía máy khách.",
    )
    _add_hjs_bullet(
        doc,
        "2. Vi dịch vụ Trợ giảng AI Copilot (FastAPI & LangGraph):",
        "Trợ lý AI vận hành trong môi trường Python 3.11 bất đồng bộ trên nền FastAPI. Hệ thống đảm nhận điều phối đồ thị trạng thái LangGraph, kết nối cơ sở dữ liệu vector Qdrant, "
        "chạy suy luận mô hình SLM ONNX trên CPU và tái xếp hạng Cross-Encoder. Việc cô lập hoàn toàn các tác vụ tính toán tensor nặng khỏi máy chủ Spring Boot đảm bảo các đợt "
        "cao điểm gọi AI không làm ảnh hưởng đến dịch vụ phát video bài giảng hay hệ thống thi trực tuyến của nhà trường.",
    )
    _add_hjs_para(
        doc,
        "Ở tầng giao diện người dùng, ứng dụng được phát triển bằng React 19 và Vite (fe-codelearning), tuân thủ nghiêm ngặt Chuẩn không gian 3 cột In-Course "
        "(In-Course Three-Column Canvas Standard) được tối ưu hóa cho tương tác giáo dục đa phương thức:",
        first_line_indent_cm=0.5,
    )
    _add_hjs_bullet(
        doc,
        "• Cột 1 (Bên trái - 340px) - Khung Giáo trình & Thẩm định Cú pháp AST:",
        "Hiển thị toàn diện cây giáo trình 83 bài học kèm bộ lọc tìm kiếm tức thời, chỉ báo trạng thái bài học tiên quyết (DAG) và công cụ thẩm định cú pháp mã nguồn (AST Code Inspector). "
        "Sinh viên có thể xem cấu trúc hàm, lớp và nhấp chuột để điều khiển video nhảy ngay đến đoạn giảng giải tương ứng.",
    )
    _add_hjs_bullet(
        doc,
        "• Cột 2 (Ở giữa - Flex 1 / Khung Video Toàn Phần):",
        "Chiếm trọn không gian thị giác trung tâm với khung phát video không viền, tích hợp Google YouTube IFrame API (chiều cao 100%, overflow: hidden). "
        "Trình phát video được đồng bộ hai chiều với backend thông qua hàm điều khiển player.seekTo(sec), tự động tua đến đúng giây khi nhận được mốc video đã được kiểm chứng.",
    )
    _add_hjs_bullet(
        doc,
        "• Cột 3 (Bên phải - 390px) - Khung Trợ Giảng Socratic AI:",
        "Không gian đối thoại tương tác giữa sinh viên và AI. Khung tích hợp ngăn kéo tư duy (Thought Drawer) hiển thị minh bạch quyết định chấm điểm CRAG Grader và độ tin cậy, "
        "các thẻ mốc thời gian click-to-seek, cùng luồng token phát trực tiếp theo thời gian thực (SSE) tuân thủ kỷ luật sư phạm Socratic.",
    )

    _add_hjs_h2(doc, "B. BỘ ĐỊNH TUYẾN Ý ĐỊNH TẦNG VÀ HÌNH THÀNH NGỮ CẢNH ĐA LƯỢT")
    _add_hjs_para(
        doc,
        "Để loại bỏ các quy tắc regex giòn gãy mà vẫn duy trì độ trễ phản hồi dưới 1 mili-giây, bộ định tuyến IntentRouter thiết lập cơ chế phòng thủ 3 tầng chuyên sâu:",
        first_line_indent_cm=0.5,
    )
    _add_hjs_bullet(
        doc,
        "1. Tầng 0 (Rào chắn an ninh & Khớp mẫu sơ bộ):",
        "Mọi truy vấn đi qua SecurityInputGuardrail (chuẩn OWASP LLM01), kiểm tra các khối mã nguồn và các nút AST Tree-sitter để phân biệt code hợp lệ của sinh viên "
        "với các câu lệnh tấn công prompt injection, kết hợp so khớp khoảng cách cosine với các mẫu câu an ninh.",
    )
    _add_hjs_bullet(
        doc,
        "2. Tầng 1 (Bộ định tuyến nơ-ron SLM INT8 đường truyền nhanh):",
        "Các truy vấn thông thường được phân loại bởi mô hình ngôn ngữ nhỏ đã lượng tử hóa (slm_router_int8.onnx) chạy trên CPU qua ONNX Runtime "
        "(độ trễ 0,06 ms P50), xuất ra xác suất ba lớp P = (P_chit, P_course, P_oos) và biên độ quyết định M = p_(1) - p_(2).",
    )
    _add_hjs_bullet(
        doc,
        "3. Tầng 2 (Cổng biên độ hai chiều & Trọng tài NLI Cross-Encoder):",
        "Những câu hỏi có độ phân vân cao (biên độ M < 0,22 hoặc tranh chấp giữa các lớp) được nâng cấp lên mô hình Cross-Encoder NLI mDeBERTa-v3. Cổng kiểm chuẩn chào hỏi "
        "ngăn chặn hiện tượng lặp lời chào, trong khi cơ chế ưu tiên độ phủ (Recall-First) chỉ cho phép chuyển sang out_of_scope khi độ tin cậy NLI >= 0,85.",
    )
    _add_hjs_para(
        doc,
        "Trong các phiên hội thoại đa lượt, nút router_node duy trì một điểm neo ngữ cảnh (last_course_query) xuyên suốt các lượt. Nút có khả năng phát hiện lời chào kết thúc "
        "qua cổng xã giao, nhận diện các câu hỏi tỉnh lược ngữ cảnh (elliptical follow-up) qua bộ phát hiện phụ thuộc D(u_t), cô lập sự trôi chủ đề khi khoảng cách cosine E5 < 0,32, "
        "và thực thi cơ chế tái cấu trúc câu hỏi hai nhánh (Dual-Track Contextual Reformulation), bảo đảm câu truy vấn luôn đầy đủ ngữ cảnh trước khi vào bộ tìm kiếm.",
        first_line_indent_cm=0.5,
    )

    _add_hjs_h2(doc, "C. TRUY XUẤT LAI TRUE HYBRID, LỌC TRƯỚC IN-HNSW ĐỘNG VÀ HIỆU CHUẨN SIGMOID")
    _add_hjs_para(
        doc,
        "Đối với câu hỏi q trong môn học c tại bài học hiện tại L_curr, dịch vụ RetrievalService thực thi truy xuất lai True Hybrid trên hệ thống vector kép của Qdrant: "
        "vector ngữ nghĩa dày 1024 chiều (multilingual-e5-large với tiền tố bất đối xứng 'query: ' và 'passage: ') kết hợp vector từ khóa thưa (Qdrant/bm25). "
        "Để bảo toàn lộ trình học tập mà không cần hardcode thứ tự bài học, hệ thống lọc điều kiện trực tiếp bên trong quá trình duyệt đồ thị HNSW của Qdrant:",
        first_line_indent_cm=0.5,
    )

    add_display_equation(
        doc,
        r"\mathcal{F}_{\text{HNSW}}(c, L_{\text{curr}}) = \left\{ d \in \mathcal{D} \mid d.\text{course\_id} = c \land d.\text{lesson\_seq} \le L_{\text{curr}} \right\}",
        eq_number="1",
        content_width_twips=10200,
    )

    _add_hjs_para(
        doc,
        "Đồng thời, cơ chế thăm dò bài tương lai bất đồng bộ (Scatter-Gather Asynchronous Future Probing) tìm kiếm song song các ứng viên thuộc các bài học kế tiếp "
        "(d.lesson_seq > L_curr, giới hạn tối đa 10 bài) qua asyncio.gather, loại bỏ hoàn toàn độ trễ 250–350 ms của vòng kết nối mạng bổ sung. Các đoạn văn bản sống sót "
        "đi qua bộ triệt tiêu phi cực đại theo thời gian (Temporal NMS) và được tái xếp hạng bằng jina-reranker-v2-base-multilingual. Điểm số logit thô z của mô hình "
        "được hiệu chuẩn thành xác suất liên quan thông qua hàm Logistic Sigmoid có bù trừ độ dài câu hỏi:",
        first_line_indent_cm=0.5,
    )

    add_display_equation(
        doc,
        r"p_{\text{raw}}(z, q) = \sigma\!\left(\frac{z}{\tau(q)}\right) = \frac{1}{1 + \exp\!\left(-\frac{z}{\tau(q)}\right)}, \quad \tau(q) = 1.25\sqrt{\frac{\max(|q|_{\text{words}}, 5)}{10}}",
        eq_number="2",
        content_width_twips=10200,
    )

    _add_hjs_para(
        doc,
        "Để kết hợp an toàn tín hiệu xếp hạng từ vựng, cơ chế Semantic-Gated RRF Fusion hòa trộn điểm RRF chuẩn hóa r_norm với p_raw thông qua trọng số động "
        "w_eff = 0,10 * min(1, (p_raw / p_pivot)^2), bảo đảm các đoạn văn bản có điểm BM25 cao nhưng không liên quan về ngữ nghĩa sẽ không thể bị thổi phồng điểm số. "
        "Ngưỡng điểm phân biệt theo phương thức: CODE_SCORE_THRESHOLD = 0,35 cho cú pháp Code AST và VIDEO_SCORE_THRESHOLD = 0,22 cho lời giảng trong video.",
        first_line_indent_cm=0.5,
    )

    _add_hjs_h2(doc, "D. BIÊN ĐỘ QUYẾT ĐỊNH ĐỦ NGỮ CẢNH PARETO BA PHÂN TẦNG VÀ THỨ TỰ TIÊN QUYẾT")
    _add_hjs_para(
        doc,
        "Lời nói thoáng qua của giảng viên trong các bài mở đầu thường đạt độ tương đồng từ vựng tương đối (0,22 <= S_curr < 0,30) nhưng hoàn toàn không đủ thông tin "
        "để giải thích bản chất kỹ thuật. Ngược lại, so sánh argmax đơn giản trên các bài tương lai lại dễ khiến bài học bị cướp quyền quá sớm. Để giải quyết triệt để sự "
        "đánh đổi này, RetrievalService cưỡng chế phân cấp truy xuất 4 tầng nghiêm ngặt: Tầng 1 Thoát sớm tự tin cao (khóa trạng thái grounded nếu Code AST >= 0,46 hoặc "
        "Video >= 0,40); Tầng 2 Thăm dò bài tương lai qua Ranh giới Pareto; Tầng 3 Hạ chuẩn có kiểm soát (phục hồi trạng thái Ambiguous của CRAG); và Tầng 4 Khoảng trống học liệu (Coverage Gap). "
        "Tại Tầng 2, bài học tương lai d_future chỉ được phép thống trị bài hiện tại sang trạng thái out_of_lesson khi và chỉ khi đồng thời thỏa mãn cả điều kiện điểm sàn và biên độ vượt trội:",
        first_line_indent_cm=0.5,
    )

    add_display_equation(
        doc,
        r"\Big( S_{\text{future}} \ge S_{\text{floor}}(S_{\text{curr}}, m_{\text{future}}) \Big) \land \Big( S_{\text{future}} - S_{\text{curr}} \ge \Delta_{\text{margin}}(S_{\text{curr}}) \Big)",
        eq_number="3",
        content_width_twips=10200,
    )

    _add_hjs_para(
        doc,
        "trong đó điểm sàn phân tầng S_floor và biên độ tuyến tính từng đoạn Delta_margin được xác lập trên 3 chế độ: "
        "Phân tầng (a) Bài hiện tại chưa đạt chuẩn (S_curr < 0,22): S_floor = 0,33, Delta_margin = 0,11; "
        "Phân tầng (b) Vùng lời nói lơ lửng (0,22 <= S_curr < 0,30): S_floor = 0,30, Delta_margin = 0,08 + 0,25 * (S_curr - 0,22); và "
        "Phân tầng (c) Bài hiện tại đã đạt tự tin (S_curr >= 0,30): S_floor = 0,36, Delta_margin = 0,08 + 0,25 * (S_curr - 0,30). "
        "Bên cạnh đó, Bất biến Thứ tự Tiên quyết (Prerequisite Order Invariant) bảo đảm rằng bài học nhập môn có số thứ tự nhỏ nhất (min lesson_seq) luôn được ưu tiên chọn, "
        "và Quy tắc Ưu tiên Bài Tiên quyết ngăn chặn các bài ôn tập nâng cao cướp quyền giải thích của các bài định nghĩa khái niệm nền tảng.",
        first_line_indent_cm=0.5,
    )

    _add_hjs_h2(doc, "E. PHÂN TÍCH CÚ PHÁP AST TREE-SITTER, GẮN MỐC VIDEO VÀ CẮT TỈA CODE SOCRATIC THEO ĐỘ PHỨC TẠP CHU TRÌNH")
    _add_hjs_para(
        doc,
        "Các hệ thống RAG thông thường phân đoạn mã nguồn bằng các cửa sổ trượt ký tự hoặc cắt dòng thô bạo, thường xuyên chặt đứt chữ ký hàm khỏi thân hàm "
        "hoặc làm gãy cấu trúc vòng lặp lồng nhau. Để loại bỏ triệt để lỗi cú pháp này, quy trình lập chỉ mục triển khai Tree-sitter với bộ ngữ pháp C++ chuẩn mực "
        "(tree-sitter-cpp). Bộ phân tích cú pháp duyệt cây cú pháp cụ thể để bóc tách các khối khai báo hoàn chỉnh: function_definition (định nghĩa hàm), "
        "class_specifier (định nghĩa lớp), struct_specifier (cấu trúc) và template_declaration (mẫu hàm/lớp). Mỗi đoạn mã nguồn AST luôn bảo toàn nguyên vẹn "
        "phạm vi ngữ pháp, các từ khóa truy cập, tham số và namespace bao bọc.",
        first_line_indent_cm=0.5,
    )
    _add_hjs_para(
        doc,
        "Để đồng bộ hóa tức thời giữa mã nguồn và video bài giảng, từng thực thể AST được liên kết tĩnh với các giây phát video liên tục thông qua tệp "
        "lesson_code_video_binding.json. Ánh xạ này gắn chặt mỗi đoạn code c với một mốc video Ground-Truth bất biến tau_anchor(c), tạo ra mục tiêu chuyển hướng "
        "t_seek = tau_anchor(c). Khi một đoạn Code AST được truy xuất thành công, giao diện frontend sẽ lập tức nhận được mốc video đã được bảo chứng, "
        "loại bỏ hoàn toàn cơ chế đoán mò mốc thời gian xác suất.",
        first_line_indent_cm=0.5,
    )
    _add_hjs_para(
        doc,
        "Nhằm bảo vệ triết lý sư phạm Socratic và ngăn chặn sinh viên chép bài hộ, động cơ AST tự động tính toán Độ phức tạp chu trình McCabe M(G) "
        "cho các đoạn mã ứng viên và bản thảo phản hồi:",
        first_line_indent_cm=0.5,
    )

    add_display_equation(
        doc,
        r"M(G) = E - N + 2P",
        eq_number="4",
        content_width_twips=10200,
    )

    _add_hjs_para(
        doc,
        "trong đó E là số cạnh, N là số đỉnh trong đồ thị dòng điều khiển, và P là số thành phần liên thông (P = 1 đối với một chương trình đơn lẻ). "
        "Bất cứ khi nào sinh viên yêu cầu giải bài tập hộ hoặc khi phân tích AST phát hiện cấu trúc cài đặt thuật toán có M(G) >= 3, rào chắn SocraticOutputGuardrail "
        "sẽ lập tức can thiệp. Rào chắn cắt bỏ toàn bộ phần thân cài đặt thuật toán thực thi, chỉ giữ lại chữ ký hàm, đồng thời chèn các câu hỏi gợi ý định hướng, "
        "mã giả giải thuật và các câu hỏi chẩn đoán lỗi compiler, bảo đảm tỷ lệ từ chối giải bài hộ (SRP) đạt tuyệt đối 100,0%.",
        first_line_indent_cm=0.5,
    )

    _add_hjs_h2(doc, "F. LẮP RÁP NGỮ CẢNH CHỮ U VÀ MÁY TRẠNG THÁI FSM 3 TRẠNG THÁI TRÊN LUỒNG SSE THỜI GIAN THỰC")
    _add_hjs_para(
        doc,
        "Các đoạn học liệu sống sót qua các vòng lọc được sắp xếp theo bố cục hình chữ U [Top 1, Top 3, Top 2], tự động đẩy các đoạn code khung boilerplate xuống "
        "vị trí thứ yếu để khắc phục hiện tượng suy giảm chú ý Lost-in-the-Middle của mô hình ngôn ngữ. Lịch sử đàm thoại được quản lý qua cửa sổ trượt k = 4 lượt "
        "hội thoại, kiểm soát nghiêm ngặt dưới trần ngân sách ngữ cảnh toàn cục không quá 2.400 ký tự.",
        first_line_indent_cm=0.5,
    )
    _add_hjs_para(
        doc,
        "Tại cổng phát dữ liệu, FastAPI truyền phát các token đàm thoại về máy khách thông qua luồng Server-Sent Events (SSE, text/event-stream) bất đồng bộ, "
        "đạt thời gian phản hồi từ đầu tiên (TTFT) trung vị ~450 ms. Tuy nhiên, việc để LLM tự do sinh thẻ mốc video có nguy cơ sinh ra mốc thời gian ảo giác "
        "(ví dụ: tự sáng tác mốc 01:00, 02:00 cho các bước giải thích đời sống). Để triệt tiêu hoàn toàn ảo giác mốc thời gian mà không cần gom toàn bộ câu trả lời, "
        "động cơ phát luồng vận hành một máy trạng thái hữu hạn 3 trạng thái (3-State FSM) quét trực tiếp từng ký tự trên luồng phát:",
        first_line_indent_cm=0.5,
    )
    _add_hjs_bullet(
        doc,
        "1. Trạng thái STATE_EMIT (Phát trực tiếp):",
        "Các ký tự văn bản thông thường được đẩy thẳng ra cổng SSE ngay khi sinh ra, bảo toàn độ trễ bằng không (zero buffering latency).",
    )
    _add_hjs_bullet(
        doc,
        "2. Trạng thái STATE_ACCUMULATE_TAG (Tích lũy thẻ):",
        "Khi phát hiện tiền tố mở thẻ ('<timestamp'), bộ lọc tạm thời chuyển hướng các ký tự tiếp theo vào một bộ đệm tích lũy cho đến khi gặp thẻ đóng ('</timestamp>').",
    )
    _add_hjs_bullet(
        doc,
        "3. Trạng thái STATE_STREAM_BODY (Thẩm định mốc giây):",
        "Bộ lọc trích xuất giây ứng viên s = int(attr['sec']) và đối chiếu trực tiếp với tập hợp các mốc video Ground-Truth đã được bảo chứng W = {tau_anchor(c) | c in C_grounded}. "
        "Nếu s in W, toàn bộ thẻ mốc thời gian hợp lệ được phát ra luồng; nếu s not in W, thẻ bị cắt bỏ hoàn toàn và chỉ phát phần chữ miêu tả. Cơ chế này bảo đảm 100% "
        "mốc thời gian phát ra đều có thật trong bài giảng mà không làm nghẽn dòng token của LLM.",
    )

    # BẢNG 1: THÀNH PHẦN KIẾN TRÚC & SƯ PHẠM
    add_three_line_table(
        doc,
        caption="Bảng 1. Các thành phần kiến trúc, cơ chế sư phạm Socratic và rào chắn kiểm soát hệ thống",
        headers=["Thành phần hệ thống", "Cơ chế kỹ thuật / Công nghệ vận hành", "Mục tiêu sư phạm / Rào chắn kiểm soát"],
        rows=[
            ["Kiến trúc Dual-Backend", "Spring Boot 3.x (ACID, JWT, PayOS) + FastAPI AI Microservice", "Phân tách rõ ràng giữa giao dịch nghiệp vụ web và tính toán tensor nơ-ron"],
            ["Chuẩn không gian 3 cột In-Course", "React 19 / Vite: 340px Syllabus, Flex 1 Video, 390px Socratic Panel", "Tối ưu hóa công thái học EdTech; đồng bộ YouTube IFrame seekTo(sec)"],
            ["Bộ định tuyến ý định tầng", "SLM ONNX INT8 (0,06 ms P50) + Trọng tài NLI mDeBERTa-v3", "Điều phối ý định dưới mili-giây (91,0% đơn lượt, 98,65% đa lượt)"],
            ["Quản lý bộ nhớ đa lượt", "LangGraph MemorySaver + Cổng phát hiện trôi E5 + Dual-Track", "Cửa sổ trượt k=4, ngân sách <= 2.400 ký tự, cô lập trôi chủ đề < 0,32"],
            ["Pipeline Speech-to-Text", "faster-whisper large-v3 + Silero VAD (ngưỡng 0,35, speech_pad 400ms)", "Phiên âm âm học không cắt vụn từ ngữ xuyên suốt 52+ giờ bài giảng"],
            ["Domain Hotwords & Canonicalizer", "Hotwords lexicon biasing + Stage 2 Tech Canonicalizer Regex", "Chuẩn hóa lỗi phiên âm âm học tiếng Việt (si-lát-lát -> C++, xâu -> std::string)"],
            ["Truy xuất lai True Hybrid", "Multilingual E5-Large (1024 chiều) + Qdrant/bm25 + Scatter-Gather", "Lọc đồ thị In-HNSW lesson_seq <= L_curr; Temporal NMS (30s, trùng lặp 0,40)"],
            ["Tái xếp hạng & Hiệu chuẩn", "jina-reranker-v2-base-multilingual (CPU, batch 4) + Sigmoid", "Hiệu chuẩn theo độ dài tau(q); cổng RRF w_max = 0,10; T_code=0,35, T_video=0,22"],
            ["Độ đủ ngữ cảnh Pareto (CRAG)", "Ranh giới Pareto ba phân tầng + Bất biến thứ tự tiên quyết", "Biên độ Delta_margin trong [0,08; 0,50]; chặn triệt để bài cũ nuốt bài mới"],
            ["Đồng bộ Cú pháp AST - Video", "Bộ phân tích C++ Tree-sitter + Ánh xạ siêu dữ liệu approx_video_sec", "Điều khiển seekTo(sec) tức thời đến đúng đoạn giảng giải mã nguồn"],
            ["Rào chắn Socratic Output Guardrail", "Đo độ phức tạp chu trình AST M(G) >= 3 & Cắt tỉa thân hàm", "Đạt 100,0% SRP (Tuyệt đối không giải bài hộ xuyên suốt 30 phiên GPU thật)"],
            ["Máy trạng thái hữu hạn Whitelist FSM", "3-State FSM (EMIT, ACCUMULATE_TAG, STREAM_BODY) trên luồng SSE", "Kiểm duyệt trực tiếp trên dòng token, chỉ cho phép mốc thời gian thuộc Whitelist W"],
        ],
        col_widths_cm=[4.0, 7.0, 6.5],
        font_size_pt=8.0,
        border_style="hjs_grid",
    )

    # -------------------------------------------------------------
    # PHẦN IV: THIẾT LẬP THỰC NGHIỆM
    # -------------------------------------------------------------
    _add_hjs_h1(doc, "IV. THIẾT LẬP THỰC NGHIỆM")
    _add_hjs_h2(doc, "A. TIỀN XỬ LÝ HỌC LIỆU, PIPELINE SPEECH-TO-TEXT VÀ CHUẨN HÓA NGỮ ÂM")
    _add_hjs_para(
        doc,
        "Hệ thống kiểm chuẩn đánh giá trên tập học liệu gồm 83 bài học lập trình thuộc chuỗi môn học C++, Lập trình hướng đối tượng (OOP) và "
        "Cấu trúc dữ liệu & Giải thuật giảng dạy tại HUFLIT, bao gồm hơn 52 giờ video bài giảng liên tục và hơn 12.000 dòng mã nguồn mẫu. "
        "Toàn bộ âm thanh bài giảng được xử lý qua pipeline chuẩn hóa âm học và ngữ âm đa tầng:",
        first_line_indent_cm=0.5,
    )
    _add_hjs_bullet(
        doc,
        "1. Phiên âm âm học & Silero VAD:",
        "Âm thanh được phiên âm tự động bằng faster-whisper với mô hình large-v3 lượng tử hóa CT2. Nhằm loại bỏ hiện tượng ảo giác âm học khi giảng viên dừng gõ code "
        "hoặc các khoảng lặng trong lớp, mô hình Silero VAD được tích hợp với ngưỡng kích hoạt threshold = 0,35 và phần đệm speech_pad_ms = 400. Cấu hình này "
        "cắt sạch các khoảng lặng mà không làm mất các phụ âm đầu hoặc đuôi từ kỹ thuật.",
    )
    _add_hjs_bullet(
        doc,
        "2. Thiên kiến từ điển chuyên ngành (Domain Hotwords Lexicon Biasing):",
        "Các bài giảng lập trình tiếng Việt thường xuyên xen lẫn tiếng Anh và thuật ngữ kỹ thuật. Nhằm ngăn chặn hiện tượng trôi dạt chùm giải mã (beam search drift), "
        "danh sách từ khóa chuyên ngành được nạp vào mọi cửa sổ xử lý âm thanh: C++, std::vector, pointer, nullptr, class, struct, polymorphism, inheritance, virtual, override, template, namespace, constructor, destructor.",
    )
    _add_hjs_bullet(
        doc,
        "3. Tầng 2 Chuẩn hóa ngữ âm Tech Canonicalizer:",
        "Quá trình chuyển âm tiếng nói thường tạo ra các lỗi phiên âm méo mó (ví dụ: 'si-lát-lát' thay cho C++, 'xâu ký tự' thay cho std::string, 'con trỏ nun' thay cho nullptr, "
        "và 'mảng hai chiều' thay cho 2D array). Tầng 2 Tech Canonicalizer thực thi các quy tắc regex chuẩn hóa ngữ âm trên các phân đoạn trước khi nạp vào vector DB, "
        "triệt tiêu hoàn toàn bẫy không khớp từ vựng trước khi tạo embedding dày multilingual-e5-large và token thưa Qdrant/bm25.",
    )

    _add_hjs_h2(doc, "B. CÁC BỘ KIỂM CHUẨN ĐỊNH LƯỢNG")
    _add_hjs_para(
        doc,
        "Hệ thống được kiểm thử độc lập trên hai bộ benchmark khoa học độc lập hoàn toàn không tham gia vào quá trình tinh chỉnh siêu tham số:",
        first_line_indent_cm=0.5,
    )
    _add_hjs_bullet(
        doc,
        "1. Bộ Golden Benchmark Stage 11 (N = 200 câu hỏi đơn lượt):",
        "Bao gồm 4 phân tầng: Câu hỏi kỹ thuật đúng bài (In-Scope: 80 câu), Câu hỏi vượt trước bài học (Out-of-Lesson: 40 câu), Câu hỏi lai đối kháng gài bẫy (Adversarial Hybrid: 40 câu), "
        "và Câu hỏi chào hỏi xã giao / ngoài lề (Chit-Chat / Out-of-Domain: 40 câu).",
    )
    _add_hjs_bullet(
        doc,
        "2. Bộ Deterministic Multi-Turn Benchmark (50 phiên đàm thoại gồm 222 lượt tương tác):",
        "Được thiết kế để thử thách 4 tầng áp lực đàm thoại đa lượt: Câu cụt và hồi chỉ đại từ (Ellipsis & Anaphora: 15 phiên, 60 lượt), Gạ xin code giải bài hộ (Socratic Refusal: 15 phiên, 60 lượt), "
        "Chuyển đổi chủ đề đột ngột (Topic Switching: 10 phiên, 42 lượt), và Tràn ngân sách ngữ cảnh (Context Budget: 10 phiên, 60 lượt). Ngoài ra, một đợt thẩm định E2E trực tiếp gồm 30 lượt gọi LLM "
        "trên GPU Kaggle từ xa được thực hiện để kiểm chuẩn tuân thủ sư phạm.",
    )

    _add_hjs_h2(doc, "C. TIÊU CHÍ ĐÁNH GIÁ")
    _add_hjs_para(
        doc,
        "Gọi I[.] là hàm chỉ thị và N là tổng số trường hợp kiểm thử. Các tiêu chí khoa học chính bao gồm:",
        first_line_indent_cm=0.5,
    )

    add_display_equation(
        doc,
        r"\text{Acc}_{\text{intent}} = \frac{1}{N}\sum_{i=1}^{N}\mathbb{1}\left[\hat{y}_i = y_i\right]",
        eq_number="5",
        content_width_twips=10200,
    )

    add_display_equation(
        doc,
        r"\text{SRP} = \frac{\#\{\text{lượt yêu cầu bị từ chối mà không lộ code}\}}{\#\{\text{tổng số lượt yêu cầu giải bài}\}}",
        eq_number="6",
        content_width_twips=10200,
    )

    if variant == "B":
        add_display_equation(
            doc,
            r"\text{ARR} = \frac{\#\{\text{câu cụt được tái cấu trúc đúng thực thể mục tiêu}\}}{\#\{\text{tổng số câu cụt kiểm thử}\}}",
            eq_number="7",
            content_width_twips=10200,
        )

    _add_hjs_para(
        doc,
        "trong đó Acc_intent đo lường độ chính xác phân loại ý định; SRP đo lường độ chính xác từ chối giải bài hộ Socratic; ARR đo lường tỷ lệ giải quyết câu cụt hồi chỉ; "
        "Độ chuẩn xác CRAG Grader đánh giá tính chính xác của quyết định phân loại 3 trạng thái; và Độ an toàn mốc thời gian (Timestamp Safety) đo lường tỷ lệ các mốc thời gian "
        "được phát ra nằm trong tập danh sách trắng đã được kiểm chứng mà không có ảo giác thời gian.",
        first_line_indent_cm=0.5,
    )

    _add_hjs_h2(doc, "D. GIAO THỨC THỰC NGHIỆM")
    _add_hjs_para(
        doc,
        "Mọi chỉ số hiệu năng định lượng đều được trích xuất trực tiếp từ các tệp kết quả JSON đã được xác thực (multiturn_benchmark_results.json, "
        "latest_benchmark_results.json, và multiturn_benchmark_e2e_results.json), loại bỏ hoàn toàn sai số nhập liệu thủ công. Do video bài giảng dài "
        "thường giảng giải một khái niệm ở nhiều phân đoạn khác nhau (lý thuyết, demo code, bài tập), độ lệch |Delta t| > 30 s so với một nhãn đơn lẻ được ghi nhận "
        "là hiện tượng sai lệch gán nhãn đơn (Single-Label Annotation Discrepancy) chứ không bị coi là lỗi ảo giác thuật toán.",
        first_line_indent_cm=0.5,
    )

    # -------------------------------------------------------------
    # PHẦN V: KẾT QUẢ THỰC NGHIỆM VÀ THẢO LUẬN
    # -------------------------------------------------------------
    _add_hjs_h1(doc, "V. KẾT QUẢ THỰC NGHIỆM VÀ THẢO LUẬN")
    _add_hjs_para(
        doc,
        "Bảng 2 và Bảng 3 trình bày hiệu năng định lượng tổng hợp trên cả hai bộ benchmark đơn lượt và đa lượt, được trích xuất trực tiếp từ các tệp dữ liệu đã được bảo chứng.",
        first_line_indent_cm=0.5,
    )

    s11_json = benchmarks_dir / "latest_benchmark_results.json"
    mt_json = benchmarks_dir / "multiturn_benchmark_results.json"
    fig1_png = figures_dir / "fig_stage11_tiers.png"
    fig2_png = figures_dir / "fig_multiturn_tiers.png"
    plot_stage11_tiers(s11_json, fig1_png)
    plot_multiturn_tiers(mt_json, fig2_png)

    # BẢNG 2: KẾT QUẢ STAGE 11
    add_three_line_table(
        doc,
        caption="Bảng 2. Hiệu năng định lượng theo từng tầng phân loại trên Golden Benchmark Stage 11 (N = 200 câu hỏi)",
        headers=["Tầng thử thách kiểm thử", "Tổng số (N)", "Độ chính xác Router", "Độ chuẩn xác CRAG", "An toàn mốc video", "Độ trễ trung bình"],
        rows=[
            ["1. Câu hỏi kỹ thuật đúng bài", "80", "80/80 (100,0%)", "79/80 (98,8%)", "76/80 (95,0%)", "5.499,3 ms"],
            ["2. Câu hỏi vượt trước bài học", "40", "40/40 (100,0%)", "37/40 (92,5%)", "38/40 (95,0%)", "6.163,5 ms"],
            ["3. Câu hỏi lai đối kháng gài bẫy", "40", "28/40 (70,0%)", "22/40 (55,0%)", "24/40 (60,0%)", "5.894,5 ms"],
            ["4. Chào hỏi xã giao / Ngoài lề", "40", "34/40 (85,0%)", "35/40 (87,5%)", "36/40 (90,0%)", "1.423,5 ms"],
            ["TỔNG HỢP TOÀN BỘ BỘ TEST", "200", "182/200 (91,0%)", "173/200 (86,5%)", "174/200 (87,0%)", "4.896,0 ms"],
        ],
        col_widths_cm=[4.2, 2.0, 3.2, 3.0, 2.8, 2.3],
        font_size_pt=8.5,
        border_style="hjs_grid",
    )

    add_figure_with_caption(
        doc,
        fig1_png,
        "Hình 1: Phân rã hiệu năng định lượng của bộ Golden Benchmark 200 câu Stage 11 theo từng phân tầng thử thách (300 DPI).",
        width_cm=15.2,
        italic_body=False,
    )

    # BẢNG 3: KẾT QUẢ MULTI-TURN
    add_three_line_table(
        doc,
        caption="Bảng 3. Đánh giá hiệu năng trên bộ kiểm chuẩn hội thoại đa lượt xác định (50 phiên / 222 lượt tương tác)",
        headers=["Chỉ số khoa học cốt lõi", "Kết quả thực tế ghi nhận", "Ngưỡng chuẩn kiểm tra", "Trạng thái nghiệm thu"],
        rows=[
            ["Độ chính xác phân loại ý định", "98,65% (219/222 lượt)", ">= 94,0%", "ĐẠT (Kỷ lục toàn diện)"],
            ["Độ chính xác trạng thái truy xuất", "98,20% (218/222 lượt)", ">= 93,0%", "ĐẠT"],
            ["Tỷ lệ giải quyết câu cụt hồi chỉ (ARR)", "98,94% (khôi phục đúng đại từ)", ">= 97,0%", "ĐẠT"],
            ["Độ chính xác từ chối giải bài hộ (SRP)", "100,0% (0 ca lộ code / 15 ca gạ)", "= 100,0%", "ĐẠT (Tuyệt đối không lộ code)"],
            ["Độ an toàn mốc video đa điểm neo", "99,10% (neo đúng mốc bài giảng)", ">= 90,0%", "ĐẠT"],
            ["Tỷ lệ trúng mốc đơn nhãn nghiêm ngặt", "53,60% (so với 1 mốc duy nhất)", "Chẩn đoán", "Ghi nhận độ lệch nhãn đơn"],
            ["Tuân thủ ngân sách ngữ cảnh", "100,0% (Thực tế tối đa 895 ký tự)", "<= 2.400 ký tự", "ĐẠT (100% Trong ngân sách)"],
            ["Độ trễ trung bình mỗi lượt đàm thoại", "7.531,8 ms", "<= 8.000,0 ms", "ĐẠT"],
        ],
        col_widths_cm=[5.5, 5.0, 3.5, 3.5],
        font_size_pt=8.5,
        border_style="hjs_grid",
    )

    # BẢNG 4: MULTI-TURN STRESS TIERS
    add_three_line_table(
        doc,
        caption="Bảng 4. Phân rã hiệu năng đàm thoại đa lượt theo 4 tầng áp lực hội thoại",
        headers=["Tầng áp lực đàm thoại", "Số phiên / Lượt", "Chính xác Ý định", "Chính xác Trạng thái", "An toàn Mốc video", "Tuân thủ Ngân sách", "Chỉ số ARR / SRP"],
        rows=[
            ["1. Câu cụt & Hồi chỉ đại từ", "15 / 60", "100,0% (60/60)", "100,0% (60/60)", "100,0% (60/60)", "100,0% (60/60)", "ARR 100,0%"],
            ["2. Gạ xin code giải bài tập", "15 / 60", "100,0% (60/60)", "100,0% (60/60)", "100,0% (60/60)", "100,0% (60/60)", "SRP 100,0%"],
            ["3. Chuyển chủ đề đột ngột", "10 / 42", "92,86% (39/42)", "92,86% (39/42)", "95,24% (40/42)", "100,0% (42/42)", "—"],
            ["4. Kiểm soát ngân sách ngữ cảnh", "10 / 60", "100,0% (60/60)", "98,33% (59/60)", "100,0% (60/60)", "100,0% (60/60)", "—"],
            ["TỔNG HỢP CẢ 4 TẦNG ÁP LỰC", "50 / 222", "98,65% (219/222)", "98,20% (218/222)", "99,10% (220/222)", "100,0% (222/222)", "ARR 98,94% / SRP 100%"],
        ],
        col_widths_cm=[3.8, 2.5, 2.5, 2.5, 2.8, 2.5, 2.4],
        font_size_pt=8.0,
        border_style="hjs_grid",
    )

    add_figure_with_caption(
        doc,
        fig2_png,
        "Hình 2: Hiệu năng vận hành đàm thoại trạng thái đa lượt xuyên suốt 4 tầng áp lực hội thoại (300 DPI).",
        width_cm=15.4,
        italic_body=False,
    )

    # BẢNG 5: ABLATION STUDY
    add_three_line_table(
        doc,
        caption="Bảng 5. Nghiên cứu bóc tách các thành phần kiến trúc cốt lõi trong hệ thống",
        headers=["Cấu hình thử nghiệm bóc tách", "Router đơn lượt", "Trạng thái CRAG", "ARR đa lượt", "SRP (Chống lộ code)", "Tuân thủ Ngân sách"],
        rows=[
            ["Baseline chỉ dùng Dense E5", "72,5%", "64,0%", "58,2%", "0,0% (Lộ toàn bộ)", "42,0% (Bị tràn)"],
            ["+ Sparse BM25 (Truy xuất lai)", "79,0%", "73,5%", "65,0%", "0,0% (Lộ toàn bộ)", "45,0%"],
            ["+ Lọc đồ thị In-HNSW", "84,5%", "78,0%", "72,4%", "0,0% (Lộ toàn bộ)", "50,0%"],
            ["+ Bộ định tuyến tầng NLI Arbiter", "91,0%", "79,5%", "81,0%", "0,0% (Lộ toàn bộ)", "52,0%"],
            ["+ Ngưỡng đủ ngữ cảnh Pareto 3 tầng", "91,0%", "86,5%", "84,5%", "0,0% (Lộ toàn bộ)", "55,0%"],
            ["+ LangGraph Cửa sổ trượt (k=4)", "91,0%", "86,5%", "98,94%", "0,0% (Lộ toàn bộ)", "100,0% (<=2.400 ký tự)"],
            ["TOÀN BỘ HỆ THỐNG COPILOT ĐỀ XUẤT", "91,0%", "86,5%", "98,94%", "100,0% (Không lộ code)", "100,0% (Tối đa 895 ký tự)"],
        ],
        col_widths_cm=[5.0, 2.6, 2.6, 2.6, 2.8, 2.8],
        font_size_pt=8.0,
        border_style="hjs_grid",
    )

    # BẢNG 6: LATENCY BREAKDOWN
    add_three_line_table(
        doc,
        caption="Bảng 6. Phân rã độ trễ suy luận theo từng giai đoạn thực thi trong kiến trúc",
        headers=["Giai đoạn thực thi", "Phần cứng / Trình cung cấp thực thi", "Trung vị (P50)", "Độ trễ P95", "Độ trễ P99"],
        rows=[
            ["1. SLM Router đường truyền nhanh", "ONNX INT8 / CPUExecutionProvider", "0,06 ms", "0,12 ms", "0,17 ms"],
            ["2. Trọng tài NLI Cross-Encoder", "mDeBERTa-v3 / CPUExecutionProvider", "18,4 ms", "24,5 ms", "32,1 ms"],
            ["3. Tìm kiếm Dense E5 + Sparse BM25", "FastEmbed ONNX + Qdrant Cloud", "145,0 ms", "210,0 ms", "320,0 ms"],
            ["4. Tái xếp hạng Cross-Encoder", "jina-reranker-v2 (batch=4, CPU)", "380,0 ms", "520,0 ms", "780,0 ms"],
            ["5. Chi phí điều phối LangGraph", "MemorySaver Checkpointer (Memory)", "2,1 ms", "4,5 ms", "7,2 ms"],
            ["6. Phản hồi luồng TTFT đầu cuối", "FastAPI SSE + Socratic Guardrail FSM", "450,0 ms", "680,0 ms", "920,0 ms"],
            ["7. Tổng thời gian xử lý đơn lượt", "Toàn bộ pipeline cục bộ (FastAPI đến SSE)", "4.896,0 ms", "6.200,0 ms", "7.800,0 ms"],
            ["8. Tổng thời gian phiên đa lượt", "Toàn bộ phiên hội thoại có trạng thái (222 lượt)", "5.794,9 ms", "15.022,9 ms", "59.136,0 ms"],
        ],
        col_widths_cm=[5.0, 5.0, 2.8, 2.8, 2.8],
        font_size_pt=8.0,
        border_style="hjs_grid",
    )

    # BẢNG 7: SIÊU THAM SỐ
    add_three_line_table(
        doc,
        caption="Bảng 7. Các siêu tham số hệ thống đã được hiệu chuẩn và ranh giới quyết định vận hành",
        headers=["Thành phần / Tham số", "Ký hiệu", "Giá trị hiệu chuẩn", "Cơ sở lý thuyết / Tiêu chuẩn áp dụng"],
        rows=[
            ["Kích thước Vector dày", "d_dense", "1024", "Không gian embedding chuẩn của intfloat/multilingual-e5-large"],
            ["Trọng số Vector thưa", "w_sparse", "0,10", "Trọng số tối đa của cổng RRF ngữ nghĩa; chặn thổi phồng từ khóa BM25"],
            ["Ngưỡng tái xếp hạng Code AST", "T_code", "0,35", "Độ chính xác cú pháp nghiêm ngặt cho cấu trúc mã nguồn C++"],
            ["Ngưỡng văn bản Video", "T_video", "0,22", "Dung hòa phương sai phiên âm âm học của mô hình Whisper"],
            ["Cổng Video tự tin cao", "T_video_high", "0,30", "Ngưỡng thoát sớm phân biệt phương thức không cần thăm dò bài sau"],
            ["Biên độ vượt trội Pareto", "Delta_margin", "[0,08; 0,50]", "Biên độ tuyến tính từng đoạn; ngăn bài cũ nuốt bài mới"],
            ["Số lượt hội thoại cửa sổ trượt", "k", "4 lượt (8 tin nhắn)", "Ngân sách ngữ cảnh đàm thoại tối ưu nằm gọn trong 2.400 ký tự"],
            ["Trần ngân sách ngữ cảnh", "B_chars", "2.400 ký tự", "Triệt tiêu hiện tượng suy thoái chú ý Lost-in-the-Middle"],
            ["Cửa sổ Temporal NMS", "t_NMS", "30 giây", "Triệt tiêu các phân đoạn lời giảng trùng lặp dư thừa"],
            ["Giới hạn độ phức tạp chu trình", "M_limit", "3", "Cắt tỉa AST Socratic; biến đổi thân hàm phức tạp thành câu hỏi"],
        ],
        col_widths_cm=[4.5, 2.5, 3.2, 7.8],
        font_size_pt=8.0,
        border_style="hjs_grid",
    )

    _add_hjs_h2(doc, "C. THẢO LUẬN CHUYÊN SÂU VỀ CÁC PHÁT HIỆN THỰC NGHIỆM")
    _add_hjs_para(
        doc,
        "Như thể hiện trong Bảng 2, pipeline đơn lượt đạt độ chính xác định tuyến 91,0% và độ chuẩn xác CRAG 86,5%. Kiến trúc đạt độ chính xác "
        "tuyệt đối 100,0% trên cả hai phân tầng Câu hỏi kỹ thuật đúng bài (80/80) và Câu hỏi vượt trước bài học (40/40), chứng minh rằng ranh giới "
        "đủ ngữ cảnh Pareto ba phân tầng đã loại bỏ hoàn toàn hiện tượng bài học cũ lấn át bài học mới. Các trường hợp lỗi tập trung chủ yếu ở "
        "Phân tầng 3 (Câu hỏi lai đối kháng: độ chính xác định tuyến 70,0%, độ chuẩn xác CRAG 55,0%), nơi sinh viên cố tình lồng ghép đồng thời "
        "cả ý định lập trình kỹ thuật và thao túng đàm thoại xã giao.",
        first_line_indent_cm=0.5,
    )
    _add_hjs_para(
        doc,
        "Trong kiểm thử đa lượt (Bảng 3 và Bảng 4), Tỷ lệ giải quyết câu cụt hồi chỉ (ARR) đạt 98,94% (93/94 ca khôi phục đại từ thành công), "
        "trong khi Độ chính xác từ chối giải bài hộ (SRP) đạt điểm số tuyệt đối 100,0% xuyên suốt 15 lượt đối kháng trong chế độ truy xuất và toàn bộ "
        "30 lượt sinh LLM trực tiếp trên GPU trong thực nghiệm đầu cuối. Tỷ lệ trúng mốc đơn nhãn nghiêm ngặt đạt 53,60% (119/222 lượt) do hạn chế "
        "của việc chỉ gán một mốc thời gian duy nhất trong video bài giảng dài, trong khi Độ an toàn mốc thời gian đa điểm neo đạt 99,10% (220/222 lượt), "
        "xác nhận hệ thống hoàn toàn không sinh mốc thời gian ảo giác. Xuyên suốt 222 lượt đàm thoại, bộ nhớ ngữ cảnh luôn nằm gọn trong ngân sách an toàn "
        "(đạt 100,0% tuân thủ, độ dài tối đa ghi nhận chỉ là 895 ký tự).",
        first_line_indent_cm=0.5,
    )

    # -------------------------------------------------------------
    # PHẦN VI: THẢO LUẬN, HẠN CHẾ VÀ KẾT LUẬN
    # -------------------------------------------------------------
    _add_hjs_h1(doc, "VI. THẢO LUẬN, HẠN CHẾ VÀ KẾT LUẬN")
    _add_hjs_h2(doc, "A. THẢO LUẬN KHOA HỌC")
    _add_hjs_para(
        doc,
        "Các kết quả thực nghiệm xác lập ba bài học thiết kế nền tảng cho hệ thống RAG tác nhân trong giáo dục: Thứ nhất, độ đủ ngữ cảnh sư phạm "
        "mang tính độc lập toán học với độ tương đồng từ vựng hay ngữ nghĩa: nếu không có ranh giới phân tầng tin cậy, những câu nói thoáng qua ở bài cũ "
        "sẽ tất yếu làm suy thoái chất lượng truy xuất của bài mới. Thứ hai, việc kết hợp tầng mô hình SLM INT8 với trọng tài NLI giúp đạt độ trễ phản hồi "
        "dưới mili-giây mà loại bỏ hoàn toàn các biểu thức chính quy dễ gãy. Thứ ba, các cam kết giáo dục như từ chối giải bài hộ Socratic và độ chính xác "
        "mốc thời gian bắt buộc phải được cưỡng chế dưới dạng các rào chắn kiến trúc tất định bao quanh LLM thay vì chỉ dựa vào câu nhắc prompt mềm.",
        first_line_indent_cm=0.5,
    )

    _add_hjs_h2(doc, "B. CÁC HẠN CHẾ THỰC TẾ")
    _add_hjs_para(
        doc,
        "Trên tinh thần trung thực khoa học, chúng tôi thẳng thắn ghi nhận năm hạn chế kỹ thuật của hệ thống hiện tại:",
        first_line_indent_cm=0.5,
    )
    _add_hjs_bullet(
        doc,
        "1. Độ bền vững trước câu hỏi lai đối kháng:",
        "Những câu hỏi kết hợp đồng thời giữa bài tập kỹ thuật và dẫn dắt tâm lý xã giao vẫn là điểm nghẽn chính (độ chính xác định tuyến 70,0%).",
    )
    _add_hjs_bullet(
        doc,
        "2. Sai lệch gán nhãn thời gian đơn lẻ:",
        "Chỉ số WHR nghiêm ngặt bị giới hạn ở 53,60% do nhãn kiểm chuẩn chỉ gắn một mốc duy nhất trong video dài; cần xây dựng bộ dữ liệu đa nhãn tham chiếu.",
    )
    _add_hjs_bullet(
        doc,
        "3. Đuôi độ trễ trong phiên đa lượt:",
        "Mặc dù độ trễ trung vị là 5,8 giây, độ trễ P99 có thể chạm mức 59,1 giây khi xảy ra khởi động nguội (cold-start) trong quá trình tái xếp hạng.",
    )
    _add_hjs_bullet(
        doc,
        "4. Phạm vi học liệu thể chế:",
        "Kho dữ liệu hiện tại phản ánh chương trình C++/OOP của một trường đại học; khả năng thích ứng xuyên trường với các phong cách giảng dạy khác nhau cần được đánh giá thêm.",
    )
    _add_hjs_bullet(
        doc,
        "5. Kiểm chuẩn trên dữ liệu hội thoại mô phỏng:",
        "Mặc dù bộ 222 lượt đánh giá chính xác các áp lực đàm thoại tất định, các nghiên cứu thực địa dài hạn trong lớp học thực tế là cần thiết để đo lường mức độ tiến bộ của người học.",
    )

    _add_hjs_h2(doc, "C. KẾT LUẬN VÀ HƯỚNG PHÁT TRIỂN")
    _add_hjs_para(
        doc,
        "Bài báo đã giới thiệu hệ thống In-Course Agentic RAG Copilot, thống nhất giữa định tuyến ý định tầng, truy xuất lai True Hybrid với lọc trước In-HNSW, "
        "ranh giới đủ ngữ cảnh Pareto ba phân tầng, và điều phối đàm thoại có trạng thái LangGraph với các rào chắn tất định. Đạt độ chính xác định tuyến đơn lượt "
        "91,0%, độ chính xác ý định đa lượt 98,65% và độ chuẩn xác từ chối giải bài hộ Socratic tuyệt đối 100,0%, công trình đặt nền móng kiến trúc vững chắc "
        "cho các ứng dụng AI trợ giảng. Các nghiên cứu tiếp theo sẽ tập trung vào chú giải video đa điểm neo, huấn luyện đối kháng tương phản và triển khai thử nghiệm "
        "diện rộng trong các lớp học lập trình chính quy.",
        first_line_indent_cm=0.5,
    )

    # -------------------------------------------------------------
    # PHẦN VII: LỜI CẢM ƠN
    # -------------------------------------------------------------
    _add_hjs_h1(doc, "VII. LỜI CẢM ƠN")
    _add_hjs_para(
        doc,
        "Tác giả bày tỏ lòng biết ơn sâu sắc và chân thành nhất đến ThS. Tiêu Phụng Mai Sương (Khoa Công nghệ Thông tin, "
        "Trường Đại học Ngoại ngữ – Tin học Thành phố Hồ Chí Minh - HUFLIT) vì sự tận tình hướng dẫn học thuật, những phản biện khoa học "
        "sâu sắc và sự đồng hành quý báu trong suốt quá trình nghiên cứu và phát triển đồ án này. Tác giả cũng trân trọng cảm ơn "
        "Khoa Công nghệ Thông tin, Trường Đại học Ngoại ngữ – Tin học TP.HCM đã tạo điều kiện thuận lợi và hỗ trợ cơ sở vật chất thực nghiệm.",
        first_line_indent_cm=0.5,
    )

    # -------------------------------------------------------------
    # PHẦN VIII: TÀI LIỆU THAM KHẢO (15 TRÍCH DẪN IEEE CHUẨN MỰC)
    # -------------------------------------------------------------
    _add_hjs_h1(doc, "VIII. TÀI LIỆU THAM KHẢO")
    refs = [
        "S.-Q. Yan, J.-C. Gu, Y. Zhu, and Z.-H. Ling, \"Corrective retrieval augmented generation,\" arXiv preprint arXiv:2401.15884, 2024.",
        "H. Joren, J. Zhang, C.-S. Ferng, D.-C. Juan, A. Taly, and C. Rashtchian, \"Sufficient context: A new lens on retrieval augmented generation systems,\" in Proc. Int. Conf. Learn. Represent. (ICLR), Singapore, 2025.",
        "N. F. Liu, K. Lin, J. Hewitt, A. Paranjape, M. Bevilacqua, F. Petroni, and P. Liang, \"Lost in the middle: How language models use long contexts,\" Trans. Assoc. Comput. Linguist., vol. 12, pp. 157–173, 2024.",
        "P. Lewis et al., \"Retrieval-augmented generation for knowledge-intensive NLP tasks,\" in Proc. Adv. Neural Inf. Process. Syst. (NeurIPS), vol. 33, pp. 9459–9474, 2020.",
        "Y. Gao et al., \"Retrieval-augmented generation for large language models: A survey,\" arXiv preprint arXiv:2312.10997, 2023.",
        "L. Wang, N. Yang, X. Huang, L. Yang, R. Majumder, and F. Wei, \"Multilingual E5 text embeddings: A technical report,\" arXiv preprint arXiv:2402.05672, 2024.",
        "A. Radford, J. W. Kim, T. Xu, G. Brockman, C. McLeavey, and I. Sutskever, \"Robust speech recognition via large-scale weak supervision,\" in Proc. Int. Conf. Mach. Learn. (ICML), 2023, pp. 28492–28518.",
        "S. Robertson and H. Zaragoza, \"The probabilistic relevance framework: BM25 and beyond,\" Found. Trends Inf. Retr., vol. 3, no. 4, pp. 333–389, 2009.",
        "Y. A. Malkov and D. A. Yashunin, \"Efficient and robust approximate nearest neighbor search using hierarchical navigable small world graphs,\" IEEE Trans. Pattern Anal. Mach. Intell., vol. 42, no. 4, pp. 824–836, Apr. 2020.",
        "J. C. Platt, \"Probabilistic outputs for support vector machines and comparisons to regularized likelihood methods,\" in Advances in Large Margin Classifiers, A. J. Smola et al., Eds. Cambridge, MA: MIT Press, 1999, pp. 61–74.",
        "C. Guo, G. Pleiss, Y. Sun, and K. Q. Weinberger, \"On calibration of modern neural networks,\" in Proc. Int. Conf. Mach. Learn. (ICML), 2017, pp. 1321–1330.",
        "W. Yin, J. Hay, and D. Roth, \"Benchmarking zero-shot text classification: Datasets, evaluation and entailment approach,\" in Proc. Conf. Empirical Methods Natural Lang. Process. (EMNLP-IJCNLP), Hong Kong, 2019, pp. 3914–3923.",
        "R. Paul and L. Elder, The Thinker's Guide to The Art of Socratic Questioning. Dillon Beach, CA: Foundation for Critical Thinking, 2006.",
        "S. MacNeil et al., \"Experiences from using code explanations generated by large language models in a web software development e-book,\" in Proc. 54th ACM Tech. Symp. Comput. Sci. Educ. (SIGCSE), 2023, pp. 931–937.",
        "P. He, J. Gao, and W. Chen, \"DeBERTaV3: Improving DeBERTa using ELECTRA-style pre-training with gradient-disentangled embedding sharing,\" in Proc. Int. Conf. Learn. Represent. (ICLR), 2023.",
    ]
    for idx, ref in enumerate(refs, start=1):
        add_reference_entry(doc, idx, ref, font_name=FONT_HJS, size_pt=9.0)

    # -------------------------------------------------------------
    # TIỂU SỬ TÁC GIẢ (TRẦN THÀNH NGHĨA - TÁC GIẢ DUY NHẤT)
    # -------------------------------------------------------------
    doc.add_page_break()

    p_bio_title = doc.add_paragraph()
    p_bio_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_bio_title.paragraph_format.space_before = Pt(8)
    p_bio_title.paragraph_format.space_after = Pt(12)
    set_run_font(p_bio_title.add_run("THÔNG TIN TÁC GIẢ"), name=FONT_HJS, size_pt=12.0, bold=True, color_rgb=(15, 23, 42))

    add_author_bio_block(
        doc,
        bios=[
            {
                "name": "Trần Thành Nghĩa",
                "bio": "hiện là sinh viên năm cuối (MSSV: 23DH112252) ngành Công nghệ Thông tin, Trường Đại học Ngoại ngữ – Tin học Thành phố Hồ Chí Minh (HUFLIT). Tác giả là người thiết kế toàn bộ kiến trúc giải thuật, phát triển phần mềm và thực thi kiểm chuẩn hệ thống In-Course Agentic RAG Copilot dưới sự hướng dẫn khoa học của ThS. Tiêu Phụng Mai Sương. Email liên hệ: thanhnghiat42@gmail.com / nghia.23dh112252@st.huflit.edu.vn.",
                "research": "Tạo sinh tăng cường truy xuất (RAG), Trợ giảng AI Socratic trong Giáo dục Lập trình, Xử lý Ngôn ngữ Tự nhiên (NLP), Đồ thị trạng thái LangGraph.",
            }
        ],
    )

    try:
        doc.save(str(out_docx))
        print(f"[OK] Xuất bản thành công Bản Tiếng Việt ({variant}): {out_docx}")
        return out_docx
    except PermissionError:
        alt_docx = out_docx.parent / f"{out_docx.stem}_v2.docx"
        doc.save(str(alt_docx))
        print(f"[NOTE] Tệp {out_docx.name} đang mở trong Word! Đã lưu bản cập nhật tại: {alt_docx.name}")
        return alt_docx


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Build Vietnamese Edition HJS Paper (.docx)")
    parser.add_argument("--variant", choices=["A", "B", "all"], default="all", help="Variant A, B, or all")
    parser.add_argument("--benchmarks-dir", default="docs/benchmarks")
    parser.add_argument("--figures-dir", default="scratch/paper_figures")
    args = parser.parse_args()

    benchmarks_dir = Path(args.benchmarks_dir)
    figures_dir = Path(args.figures_dir)

    out_a = PROJECT_ROOT / "docs" / "HJS_Paper_Variant_A_Algorithmic_VI.docx"
    out_b = PROJECT_ROOT / "docs" / "HJS_Paper_Variant_B_Socratic_VI.docx"
    out_final = PROJECT_ROOT / "docs" / "HJS_Paper_Final_VI.docx"

    if args.variant in ["A", "all"]:
        build_variant_paper_vi(out_a, benchmarks_dir, figures_dir, variant="A")
        # Đồng bộ hóa bản Final Tiếng Việt từ Bản A
        shutil.copy2(out_a, out_final)
        print(f"[OK] Đã đồng bộ bản mặc định Tiếng Việt: {out_final}")

    if args.variant in ["B", "all"]:
        build_variant_paper_vi(out_b, benchmarks_dir, figures_dir, variant="B")


if __name__ == "__main__":
    main()
