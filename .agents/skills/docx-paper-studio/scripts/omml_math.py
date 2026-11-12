"""
Convert LaTeX math expressions into native Microsoft Word OMML (<m:oMath> / <m:oMathPara>)
for embedding directly inside python-docx Paragraphs (no raw $...$ leaks).
"""

from __future__ import annotations

import logging
from typing import Optional

import latex2mathml.converter
import mathml2omml
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Pt
from docx.text.paragraph import Paragraph

logger = logging.getLogger(__name__)

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def latex_to_omml_xml(latex_expr: str) -> str:
    """
    Convert a raw LaTeX expression (without surrounding $ or $$) into an <m:oMath> XML string.
    """
    clean_tex = latex_expr.strip()
    if clean_tex.startswith("$$") and clean_tex.endswith("$$"):
        clean_tex = clean_tex[2:-2].strip()
    elif clean_tex.startswith("$") and clean_tex.endswith("$"):
        clean_tex = clean_tex[1:-1].strip()

    mathml_str = latex2mathml.converter.convert(clean_tex)
    omml_str = mathml2omml.convert(mathml_str)

    # Ensure xmlns:m and xmlns:w namespaces exist for lxml parse_xml
    if "xmlns:m=" not in omml_str:
        omml_str = omml_str.replace(
            "<m:oMath",
            f'<m:oMath xmlns:m="{MATH_NS}" xmlns:w="{WORD_NS}"',
            1,
        )
    elif "xmlns:w=" not in omml_str:
        omml_str = omml_str.replace(
            "<m:oMath",
            f'<m:oMath xmlns:w="{WORD_NS}"',
            1,
        )
    return omml_str


def add_inline_equation(paragraph: Paragraph, latex_expr: str, font_name: str = "Cambria Math", font_size_pt: float = 11.0) -> bool:
    """
    Append an inline native Word equation (<m:oMath>) to an existing python-docx Paragraph.
    Falls back to italic plain text only if conversion fails unexpectedly.
    """
    try:
        omml_str = latex_to_omml_xml(latex_expr)
        omath_el = parse_xml(omml_str)
        # Apply rPr font styling inside <m:r> elements when missing
        for r_el in omath_el.findall(f".//{{{MATH_NS}}}r"):
            if r_el.find(f"{{{WORD_NS}}}rPr") is None:
                rpr = parse_xml(
                    f'<w:rPr {nsdecls("w")}>'
                    f'<w:rFonts w:ascii="{font_name}" w:hAnsi="{font_name}"/>'
                    f'<w:sz w:val="{int(font_size_pt * 2)}"/>'
                    f'<w:szCs w:val="{int(font_size_pt * 2)}"/>'
                    f"</w:rPr>"
                )
                r_el.insert(0, rpr)
        paragraph._p.append(omath_el)
        return True
    except Exception as exc:
        logger.warning(f"OMML inline conversion failed for '{latex_expr}': {exc}")
        run = paragraph.add_run(latex_expr)
        run.italic = True
        run.font.size = Pt(font_size_pt)
        return False


def add_display_equation(
    doc,
    latex_expr: str,
    eq_number: Optional[str] = None,
    space_before_pt: float = 6.0,
    space_after_pt: float = 6.0,
    content_width_twips: int = 9072,
) -> Paragraph:
    """
    Add a centered display equation (<m:oMathPara>) with optional right-aligned equation number '(1)'.
    Uses a borderless 3-column layout table when eq_number is given so the formula stays centered
    while '(1)' sits cleanly flush-right, matching IEEE/Springer/HJS typesetting.
    """
    if eq_number:
        tbl = doc.add_table(rows=1, cols=3)
        tbl.autofit = False
        # Clear all table borders
        tblPr = tbl._tbl.tblPr
        borders = parse_xml(
            f'<w:tblBorders {nsdecls("w")}>'
            '<w:top w:val="none"/><w:left w:val="none"/><w:bottom w:val="none"/>'
            '<w:right w:val="none"/><w:insideH w:val="none"/><w:insideV w:val="none"/>'
            "</w:tblBorders>"
        )
        tblPr.append(borders)

        side_w = int(content_width_twips * 0.12)
        mid_w = content_width_twips - (2 * side_w)
        widths = [side_w, mid_w, side_w]

        row = tbl.rows[0]
        # Prevent row split
        trPr = row._tr.get_or_add_trPr()
        trPr.append(parse_xml(f'<w:cantSplit {nsdecls("w")}/>'))

        for idx, w_twips in enumerate(widths):
            cell = row.cells[idx]
            tcPr = cell._tc.get_or_add_tcPr()
            tcPr.append(parse_xml(f'<w:tcW {nsdecls("w")} w:w="{w_twips}" w:type="dxa"/>'))
            tcPr.append(parse_xml(f'<w:vAlign {nsdecls("w")} w:val="center"/>'))

        # Middle cell: equation
        p_eq = row.cells[1].paragraphs[0]
        p_eq.alignment = 1  # CENTER
        p_eq.paragraph_format.space_before = Pt(space_before_pt)
        p_eq.paragraph_format.space_after = Pt(space_after_pt)
        try:
            omath_el = parse_xml(latex_to_omml_xml(latex_expr))
            omath_para = OxmlElement("m:oMathPara")
            omath_para.append(omath_el)
            p_eq._p.append(omath_para)
        except Exception as exc:
            logger.warning(f"OMML display conversion failed for '{latex_expr}': {exc}")
            r = p_eq.add_run(latex_expr)
            r.italic = True

        # Right cell: equation number
        p_num = row.cells[2].paragraphs[0]
        p_num.alignment = 2  # RIGHT
        p_num.paragraph_format.space_before = Pt(space_before_pt)
        p_num.paragraph_format.space_after = Pt(space_after_pt)
        num_label = eq_number if eq_number.startswith("(") else f"({eq_number})"
        r_num = p_num.add_run(num_label)
        r_num.font.name = "Times New Roman"
        r_num.font.size = Pt(11)
        return p_eq

    # Unnumbered centered display equation
    p = doc.add_paragraph()
    p.alignment = 1  # CENTER
    p.paragraph_format.space_before = Pt(space_before_pt)
    p.paragraph_format.space_after = Pt(space_after_pt)
    try:
        omath_el = parse_xml(latex_to_omml_xml(latex_expr))
        omath_para = OxmlElement("m:oMathPara")
        omath_para.append(omath_el)
        p._p.append(omath_para)
    except Exception as exc:
        logger.warning(f"OMML display conversion failed for '{latex_expr}': {exc}")
        r = p.add_run(latex_expr)
        r.italic = True
    return p

