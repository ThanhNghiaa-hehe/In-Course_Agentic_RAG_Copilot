"""
Reusable HJS (HUFLIT Journal of Science) & Enterprise Academic DOCX Building Blocks.
Uses python-docx + lxml with Vietnamese UTF-8 Times New Roman typography,
Three-Line Booktabs tables, keep_with_next invariants, and multi-column section control.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Inches, Mm, Pt, RGBColor


FONT_HJS = "Cambria"
FONT_THESIS = "Times New Roman"


def set_run_font(
    run,
    name: str = FONT_HJS,
    size_pt: float = 10.0,
    bold: bool = False,
    italic: bool = False,
    color_rgb: Optional[tuple[int, int, int]] = None,
):
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)
    rfonts.set(qn("w:eastAsia"), name)
    run.font.size = Pt(size_pt)
    run.bold = bold
    run.italic = italic
    if color_rgb:
        run.font.color.rgb = RGBColor(*color_rgb)
    return run


def create_hjs_document(
    preset: str = "hjs_journal",
    margin_top_cm: Optional[float] = None,
    margin_bottom_cm: Optional[float] = None,
    margin_left_cm: Optional[float] = None,
    margin_right_cm: Optional[float] = None,
    font_size_pt: Optional[float] = None,
    font_name: Optional[str] = None,
) -> Document:
    """
    Initialize a Document using verified presets:
    - 'hjs_journal': Matches HJS@MTF-GCN_R3.pdf (US Letter 215.9x279.4mm, Cambria 10pt)
    - 'thesis_a4': Vietnamese HUFLIT Thesis standard (A4 210x297mm, Times New Roman 11pt)
    """
    doc = Document()
    sec = doc.sections[0]
    if preset == "thesis_a4":
        sec.page_width = Mm(210)
        sec.page_height = Mm(297)
        sec.top_margin = Cm(margin_top_cm or 2.0)
        sec.bottom_margin = Cm(margin_bottom_cm or 2.0)
        sec.left_margin = Cm(margin_left_cm or 2.5)
        sec.right_margin = Cm(margin_right_cm or 2.0)
        active_font = font_name or FONT_THESIS
        active_size = font_size_pt or 11.0
    else:
        sec.page_width = Mm(215.9)
        sec.page_height = Mm(279.4)
        sec.top_margin = Cm(margin_top_cm or 1.9)
        sec.bottom_margin = Cm(margin_bottom_cm or 1.9)
        sec.left_margin = Cm(margin_left_cm or 1.8)
        sec.right_margin = Cm(margin_right_cm or 1.8)
        active_font = font_name or FONT_HJS
        active_size = font_size_pt or 10.0

    sec.different_first_page_header_footer = True

    normal = doc.styles["Normal"]
    normal.font.name = active_font
    rpr = normal._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    rfonts.set(qn("w:ascii"), active_font)
    rfonts.set(qn("w:hAnsi"), active_font)
    rfonts.set(qn("w:eastAsia"), active_font)
    normal.font.size = Pt(active_size)
    normal.paragraph_format.line_spacing = 1.15
    normal.paragraph_format.space_after = Pt(4)

    # Configure Native Word Heading 1/2/3 styles for Navigation Pane & TOC support
    h_specs = {
        "Heading 1": (12.0 if preset != "thesis_a4" else 13.0, True, False, (15, 23, 42)),
        "Heading 2": (10.0 if preset != "thesis_a4" else 12.0, True, preset != "thesis_a4", (30, 41, 59)),
        "Heading 3": (10.0 if preset != "thesis_a4" else 11.0, True, True, (51, 65, 85)),
    }
    for s_name, (sz, is_b, is_i, rgb) in h_specs.items():
        if s_name in doc.styles:
            st = doc.styles[s_name]
            st.font.name = active_font
            st.font.size = Pt(sz)
            st.font.bold = is_b
            st.font.italic = is_i
            st.font.color.rgb = RGBColor(*rgb)
            st.paragraph_format.keep_with_next = True
            srpr = st.element.get_or_add_rPr()
            srfonts = srpr.find(qn("w:rFonts"))
            if srfonts is None:
                srfonts = OxmlElement("w:rFonts")
                srpr.insert(0, srfonts)
            srfonts.set(qn("w:ascii"), active_font)
            srfonts.set(qn("w:hAnsi"), active_font)
            srfonts.set(qn("w:eastAsia"), active_font)

    return doc


def add_hjs_journal_headers(
    doc: Document,
    running_title: str,
    author_names: str,
    journal_name: str = "HUFLIT Journal of Science",
    right_tab_twips: int = 10200,
) -> None:
    """
    Configure authentic 3-mode HUFLIT Journal of Science headers matching HJS@MTF-GCN_R3.pdf:
    - Page 1: Centered journal title + thin horizontal rule underneath
    - Even pages (2, 4, 6...): Page number left + uppercase paper title right
    - Odd pages (3, 5, 7...): Author names left + page number right
    """
    doc.settings.odd_and_even_pages_header_footer = True
    sec = doc.sections[0]
    sec.different_first_page_header_footer = True
    sec.header_distance = Cm(0.85)

    # 1) Page 1 banner with thin horizontal bottom rule
    p1 = sec.first_page_header.paragraphs[0]
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p1.paragraph_format.space_after = Pt(4)
    p1.paragraph_format.line_spacing = 1.0
    set_run_font(p1.add_run(journal_name), name="Book Antiqua", size_pt=8.0, color_rgb=(51, 65, 85))
    p1._p.get_or_add_pPr().append(
        parse_xml(
            f'<w:pBdr {nsdecls("w")}>'
            '<w:bottom w:val="single" w:sz="4" w:space="4" w:color="334155"/>'
            "</w:pBdr>"
        )
    )

    # 2) Even pages (2, 4, 6...): PAGE left + UPPERCASE TITLE right
    p_even = sec.even_page_header.paragraphs[0]
    p_even.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p_even.paragraph_format.space_after = Pt(2)
    p_even._p.get_or_add_pPr().append(
        parse_xml(f'<w:tabs {nsdecls("w")}><w:tab w:val="right" w:pos="{right_tab_twips}"/></w:tabs>')
    )
    p_even._p.append(parse_xml(r'<w:fldSimple %s w:instr="PAGE"/>' % nsdecls("w")))
    set_run_font(
        p_even.add_run(f"\t{running_title.upper()}"),
        name=FONT_HJS,
        size_pt=8.0,
        color_rgb=(51, 65, 85),
    )

    # 3) Odd pages (3, 5, 7...): Author names left + PAGE right
    p_odd = sec.header.paragraphs[0]
    p_odd.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p_odd.paragraph_format.space_after = Pt(2)
    p_odd._p.get_or_add_pPr().append(
        parse_xml(f'<w:tabs {nsdecls("w")}><w:tab w:val="right" w:pos="{right_tab_twips}"/></w:tabs>')
    )
    set_run_font(
        p_odd.add_run(f"{author_names}\t"),
        name=FONT_HJS,
        size_pt=8.5,
        color_rgb=(51, 65, 85),
    )
    p_odd._p.append(parse_xml(r'<w:fldSimple %s w:instr="PAGE"/>' % nsdecls("w")))


def set_section_columns(section, num_cols: int = 2, space_cm: float = 0.6) -> None:
    """Set number of columns (1 or 2) on a python-docx section."""
    sectPr = section._sectPr
    cols = sectPr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols")
        sectPr.append(cols)
    cols.set(qn("w:num"), str(num_cols))
    cols.set(qn("w:space"), str(int(space_cm * 567)))  # 1 cm ≈ 567 dxa


def add_continuous_section(doc: Document, num_cols: int = 1, space_cm: float = 0.6):
    """Switch column layout smoothly on the same page using a continuous section break."""
    new_sec = doc.add_section(WD_SECTION.CONTINUOUS)
    set_section_columns(new_sec, num_cols=num_cols, space_cm=space_cm)
    return new_sec


def add_page_number_footer(section, left_text: str = "") -> None:
    """Add right-aligned PAGE / NUMPAGES field in footer and optional journal header note."""
    footer = section.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if not left_text else WD_ALIGN_PARAGRAPH.LEFT
    if left_text:
        r_left = p.add_run(f"{left_text}   |   Trang ")
        set_run_font(r_left, size_pt=9.0, italic=True, color_rgb=(100, 116, 139))

    fld1 = parse_xml(r'<w:fldSimple %s w:instr="PAGE"/>' % nsdecls("w"))
    p._p.append(fld1)
    r_sep = p.add_run(" / ")
    set_run_font(r_sep, size_pt=9.0, color_rgb=(100, 116, 139))
    fld2 = parse_xml(r'<w:fldSimple %s w:instr="NUMPAGES"/>' % nsdecls("w"))
    p._p.append(fld2)


def add_academic_heading(
    doc: Document,
    text: str,
    level: int = 1,
    size_pt: Optional[float] = None,
    centered: bool = False,
    italic: Optional[bool] = None,
    font_name: str = FONT_HJS,
):
    """
    Add a numbered academic heading using native Word Heading 1/2/3 styles
    (enabling Navigation Pane, Outline View, and automatic TOC) with keep_with_next=True.
    """
    clamped_level = min(max(level, 1), 3)
    style_name = f"Heading {clamped_level}"
    p = doc.add_paragraph(style=style_name if style_name in doc.styles else None)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if centered else WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.keep_with_next = True
    if clamped_level == 1:
        p.paragraph_format.space_before = Pt(11)
        p.paragraph_format.space_after = Pt(4)
        sz = size_pt or 12.0
        is_italic = False if italic is None else italic
        r = p.add_run(text)
        set_run_font(r, name=font_name, size_pt=sz, bold=True, italic=is_italic, color_rgb=(15, 23, 42))
    elif clamped_level == 2:
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(3)
        sz = size_pt or 10.0
        is_italic = True if italic is None else italic
        r = p.add_run(text)
        set_run_font(r, name=font_name, size_pt=sz, bold=True, italic=is_italic, color_rgb=(30, 41, 59))
    else:
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(2)
        sz = size_pt or 10.0
        is_italic = True if italic is None else italic
        r = p.add_run(text)
        set_run_font(r, name=font_name, size_pt=sz, bold=True, italic=is_italic, color_rgb=(51, 65, 85))
    return p


def replace_heading_text(docx_path: str | Path, old_text: str, new_text: str) -> int:
    """
    Programmatically update a heading's text inside an existing .docx without human-in-the-loop,
    preserving its native Heading style, font, alignment, and surrounding XML.
    Returns count of replaced headings.
    """
    p = Path(docx_path)
    doc = Document(str(p))
    updated = 0
    for para in doc.paragraphs:
        st_name = para.style.name if para.style else ""
        if st_name.startswith("Heading") or old_text.strip() in para.text:
            if para.text.strip() == old_text.strip():
                if para.runs:
                    para.runs[0].text = new_text
                    for extra in para.runs[1:]:
                        extra.text = ""
                else:
                    para.text = new_text
                updated += 1
    if updated > 0:
        doc.save(str(p))
    return updated


def add_body_paragraph(
    doc: Document,
    text: str,
    justify: bool = True,
    first_line_indent_cm: float = 0.5,
    size_pt: float = 11.0,
):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY if justify else WD_ALIGN_PARAGRAPH.LEFT
    if first_line_indent_cm > 0:
        p.paragraph_format.first_line_indent = Cm(first_line_indent_cm)
    p.paragraph_format.line_spacing = 1.15
    p.paragraph_format.space_after = Pt(4)
    if text:
        r = p.add_run(text)
        set_run_font(r, size_pt=size_pt)
    return p


def add_three_line_table(
    doc: Document,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    col_widths_cm: Optional[Sequence[float]] = None,
    caption: Optional[str] = None,
    font_size_pt: float = 9.5,
    align_cols: Optional[Sequence[WD_ALIGN_PARAGRAPH]] = None,
    border_style: str = "booktabs",
    font_name: str = FONT_HJS,
):
    """
    Create an academic table with tblHeader, cantSplit, and keep_with_next header rows:
    - border_style='booktabs': IEEE 3-line horizontal rules + shaded header (default)
    - border_style='hjs_grid': Authentic HUFLIT Journal of Science (HJS@MTF-GCN_R3.pdf)
      full thin grid borders, plain white background, and 'Table X. <italic title>' caption
    """
    if caption:
        cap_p = doc.add_paragraph()
        cap_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap_p.paragraph_format.keep_with_next = True
        cap_p.paragraph_format.space_before = Pt(6)
        cap_p.paragraph_format.space_after = Pt(3)
        if border_style == "hjs_grid" and "." in caption:
            prefix, rest = caption.split(".", 1)
            set_run_font(cap_p.add_run(f"{prefix}."), name=font_name, size_pt=9.5, bold=False)
            set_run_font(cap_p.add_run(rest), name=font_name, size_pt=9.5, italic=True)
        elif ":" in caption:
            prefix, rest = caption.split(":", 1)
            set_run_font(cap_p.add_run(f"{prefix}:"), name=font_name, size_pt=10.0, bold=True)
            set_run_font(cap_p.add_run(rest), name=font_name, size_pt=10.0, italic=True)
        else:
            set_run_font(cap_p.add_run(caption), name=font_name, size_pt=10.0, bold=True)

    num_cols = len(headers)
    tbl = doc.add_table(rows=1 + len(rows), cols=num_cols)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False

    tblPr = tbl._tbl.tblPr
    if border_style == "hjs_grid":
        tblPr.append(
            parse_xml(
                f'<w:tblBorders {nsdecls("w")}>'
                '<w:top w:val="single" w:sz="4" w:space="0" w:color="334155"/>'
                '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="334155"/>'
                '<w:left w:val="single" w:sz="4" w:space="0" w:color="334155"/>'
                '<w:right w:val="single" w:sz="4" w:space="0" w:color="334155"/>'
                '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="334155"/>'
                '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="334155"/>'
                "</w:tblBorders>"
            )
        )
    else:
        tblPr.append(
            parse_xml(
                f'<w:tblBorders {nsdecls("w")}>'
                '<w:top w:val="single" w:sz="12" w:space="0" w:color="0F172A"/>'
                '<w:bottom w:val="single" w:sz="12" w:space="0" w:color="0F172A"/>'
                '<w:left w:val="none"/><w:right w:val="none"/>'
                '<w:insideH w:val="none"/><w:insideV w:val="none"/>'
                "</w:tblBorders>"
            )
        )

    def _style_cell(cell, text: str, is_header: bool, col_idx: int):
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        tcPr = cell._tc.get_or_add_tcPr()
        if col_widths_cm and col_idx < len(col_widths_cm):
            w_dxa = int(col_widths_cm[col_idx] * 567)
            tcPr.append(parse_xml(f'<w:tcW {nsdecls("w")} w:w="{w_dxa}" w:type="dxa"/>'))
        tcPr.append(
            parse_xml(
                f'<w:tcMar {nsdecls("w")}>'
                '<w:top w:w="60" w:type="dxa"/><w:bottom w:w="60" w:type="dxa"/>'
                '<w:left w:w="90" w:type="dxa"/><w:right w:w="90" w:type="dxa"/>'
                "</w:tcMar>"
            )
        )
        if is_header and border_style != "hjs_grid":
            tcPr.append(parse_xml(f'<w:shd {nsdecls("w")} w:fill="F1F5F9"/>'))
            tcPr.append(
                parse_xml(
                    f'<w:tcBorders {nsdecls("w")}>'
                    '<w:bottom w:val="single" w:sz="6" w:space="0" w:color="334155"/>'
                    "</w:tcBorders>"
                )
            )

        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.05
        if is_header:
            p.paragraph_format.keep_with_next = True
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT if border_style == "hjs_grid" and col_idx == 0 else WD_ALIGN_PARAGRAPH.CENTER
        elif align_cols and col_idx < len(align_cols):
            p.alignment = align_cols[col_idx]
        else:
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT if col_idx == 0 else WD_ALIGN_PARAGRAPH.CENTER

        r = p.add_run(str(text))
        set_run_font(r, name=font_name, size_pt=font_size_pt, bold=is_header, color_rgb=(15, 23, 42))

    # Header row
    hdr_row = tbl.rows[0]
    hdr_trPr = hdr_row._tr.get_or_add_trPr()
    hdr_trPr.append(parse_xml(f'<w:tblHeader {nsdecls("w")}/>'))
    hdr_trPr.append(parse_xml(f'<w:cantSplit {nsdecls("w")}/>'))
    for c_idx, h_text in enumerate(headers):
        _style_cell(hdr_row.cells[c_idx], h_text, is_header=True, col_idx=c_idx)

    # Data rows
    for r_idx, row_vals in enumerate(rows):
        row = tbl.rows[1 + r_idx]
        trPr = row._tr.get_or_add_trPr()
        trPr.append(parse_xml(f'<w:cantSplit {nsdecls("w")}/>'))
        for c_idx, val in enumerate(row_vals):
            _style_cell(row.cells[c_idx], val, is_header=False, col_idx=c_idx)

    sp = doc.add_paragraph()
    sp.paragraph_format.space_before = Pt(0)
    sp.paragraph_format.space_after = Pt(4)
    return tbl


def add_figure_with_caption(
    doc: Document,
    image_path: str | Path,
    caption: str,
    width_cm: float = 15.5,
    italic_body: bool = False,
    font_name: str = FONT_HJS,
):
    """Insert a centered high-DPI figure with keep_with_next=True and formatted caption below."""
    img_p = doc.add_paragraph()
    img_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    img_p.paragraph_format.keep_with_next = True
    img_p.paragraph_format.space_before = Pt(6)
    img_p.paragraph_format.space_after = Pt(2)
    run = img_p.add_run()
    run.add_picture(str(image_path), width=Cm(width_cm))

    cap_p = doc.add_paragraph()
    cap_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap_p.paragraph_format.space_after = Pt(6)
    if ":" in caption:
        prefix, rest = caption.split(":", 1)
        set_run_font(cap_p.add_run(f"{prefix}:"), name=font_name, size_pt=10.0, bold=True)
        set_run_font(cap_p.add_run(rest), name=font_name, size_pt=10.0, italic=italic_body)
    else:
        set_run_font(cap_p.add_run(caption), name=font_name, size_pt=10.0, italic=italic_body)
    return img_p, cap_p


def add_reference_entry(
    doc: Document,
    ref_num: int,
    citation_text: str,
    font_name: str = FONT_HJS,
    size_pt: float = 9.5,
):
    """Add an IEEE-style hanging-indent reference entry matching HJS page 7-8."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.left_indent = Cm(0.85)
    p.paragraph_format.first_line_indent = Cm(-0.85)
    p.paragraph_format.line_spacing = 1.1
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.tab_stops.add_tab_stop(Cm(0.85))
    set_run_font(p.add_run(f"[{ref_num}]\t{citation_text}"), name=font_name, size_pt=size_pt)
    return p


def add_author_bio_block(
    doc: Document,
    bios: Sequence[dict[str, str]],
    font_name: str = FONT_HJS,
):
    """
    Add a 2-column borderless Author Biography + Portrait placeholder block
    at the end of the paper matching page 8 of HJS@MTF-GCN_R3.pdf.
    Each item in bios: {'name': ..., 'bio': ..., 'research': ..., 'photo_path': optional}
    """
    if not bios:
        return None
    tbl = doc.add_table(rows=1, cols=min(2, len(bios)))
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    tblPr = tbl._tbl.tblPr
    tblPr.append(
        parse_xml(
            f'<w:tblBorders {nsdecls("w")}>'
            '<w:top w:val="none"/><w:left w:val="none"/><w:bottom w:val="none"/>'
            '<w:right w:val="none"/><w:insideH w:val="none"/><w:insideV w:val="none"/>'
            "</w:tblBorders>"
        )
    )
    row = tbl.rows[0]
    row._tr.get_or_add_trPr().append(parse_xml(f'<w:cantSplit {nsdecls("w")}/>'))

    for idx, author in enumerate(bios[:2]):
        outer_cell = row.cells[idx]
        outer_tcPr = outer_cell._tc.get_or_add_tcPr()
        outer_tcPr.append(parse_xml(f'<w:tcW {nsdecls("w")} w:w="5100" w:type="dxa"/>'))
        p0 = outer_cell.paragraphs[0]
        p0.paragraph_format.space_before = Pt(4)
        p0.paragraph_format.space_after = Pt(2)
        photo_path = author.get("photo_path")
        if photo_path and Path(photo_path).exists():
            p0.add_run().add_picture(str(photo_path), width=Cm(2.4))
            p_bio = outer_cell.add_paragraph()
        else:
            set_run_font(
                p0.add_run("[Ảnh chân dung 3x4 cm] "),
                name=font_name,
                size_pt=8.5,
                italic=True,
                color_rgb=(100, 116, 139),
            )
            p_bio = outer_cell.add_paragraph()

        p_bio.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p_bio.paragraph_format.space_after = Pt(2)
        p_bio.paragraph_format.line_spacing = 1.08
        set_run_font(p_bio.add_run(author.get("name", "") + " "), name=font_name, size_pt=9.0, bold=True)
        set_run_font(p_bio.add_run(author.get("bio", "")), name=font_name, size_pt=9.0)

        if author.get("research"):
            p_res = outer_cell.add_paragraph()
            p_res.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p_res.paragraph_format.space_after = Pt(2)
            set_run_font(
                p_res.add_run(f"Hướng nghiên cứu chính: {author['research']}"),
                name=font_name,
                size_pt=9.0,
            )
    return tbl

