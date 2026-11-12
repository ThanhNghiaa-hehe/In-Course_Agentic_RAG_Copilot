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
    return doc


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


def add_academic_heading(doc: Document, text: str, level: int = 1, size_pt: Optional[float] = None):
    """Add numbered academic heading with keep_with_next=True."""
    p = doc.add_paragraph()
    p.paragraph_format.keep_with_next = True
    if level == 1:
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(4)
        sz = size_pt or 12.0
        r = p.add_run(text)
        set_run_font(r, size_pt=sz, bold=True, color_rgb=(15, 23, 42))
    elif level == 2:
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(3)
        sz = size_pt or 11.0
        r = p.add_run(text)
        set_run_font(r, size_pt=sz, bold=True, color_rgb=(30, 41, 59))
    else:
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(2)
        sz = size_pt or 11.0
        r = p.add_run(text)
        set_run_font(r, size_pt=sz, bold=True, italic=True, color_rgb=(51, 65, 85))
    return p


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
):
    """
    Create an IEEE/HJS booktabs-style Three-Line Table:
    - Optional bold caption above table with keep_with_next=True
    - Top rule 1.5pt, header-bottom rule 0.75pt, bottom rule 1.5pt, no vertical lines
    - Repeats header across page breaks (tblHeader) and prevents row splitting (cantSplit)
    """
    if caption:
        cap_p = doc.add_paragraph()
        cap_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap_p.paragraph_format.keep_with_next = True
        cap_p.paragraph_format.space_before = Pt(6)
        cap_p.paragraph_format.space_after = Pt(3)
        if ":" in caption:
            prefix, rest = caption.split(":", 1)
            set_run_font(cap_p.add_run(f"{prefix}:"), size_pt=10.0, bold=True)
            set_run_font(cap_p.add_run(rest), size_pt=10.0, italic=True)
        else:
            set_run_font(cap_p.add_run(caption), size_pt=10.0, bold=True)

    num_cols = len(headers)
    tbl = doc.add_table(rows=1 + len(rows), cols=num_cols)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False

    # Global Three-Line Borders: top & bottom 12 (1.5pt), no vertical/inner borders by default
    tblPr = tbl._tbl.tblPr
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
        # Comfortable cell padding
        tcPr.append(
            parse_xml(
                f'<w:tcMar {nsdecls("w")}>'
                '<w:top w:w="70" w:type="dxa"/><w:bottom w:w="70" w:type="dxa"/>'
                '<w:left w:w="90" w:type="dxa"/><w:right w:w="90" w:type="dxa"/>'
                "</w:tcMar>"
            )
        )
        if is_header:
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
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif align_cols and col_idx < len(align_cols):
            p.alignment = align_cols[col_idx]
        else:
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT if col_idx == 0 else WD_ALIGN_PARAGRAPH.CENTER

        r = p.add_run(str(text))
        set_run_font(r, size_pt=font_size_pt, bold=is_header, color_rgb=(15, 23, 42))

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
        set_run_font(cap_p.add_run(f"{prefix}:"), size_pt=10.0, bold=True)
        set_run_font(cap_p.add_run(rest), size_pt=10.0, italic=True)
    else:
        set_run_font(cap_p.add_run(caption), size_pt=10.0, italic=True)
    return img_p, cap_p

