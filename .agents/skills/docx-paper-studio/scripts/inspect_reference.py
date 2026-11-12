"""
Inspect reference .pdf or .docx journal papers (margins, fonts, font sizes, headings, page count)
so generated manuscripts match the exact target format (e.g. HJS@MTF-GCN_R3.pdf).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import sys


def inspect_pdf(pdf_path: Path) -> dict:
    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    pages_info = []
    font_counter: Counter[tuple[str, float]] = Counter()
    headings_guess = []

    for idx, page in enumerate(doc):
        rect = page.rect
        d = page.get_text("dict")
        page_fonts = Counter()
        for block in d.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                line_text = "".join(sp.get("text", "") for sp in line.get("spans", [])).strip()
                for sp in line.get("spans", []):
                    fname = sp.get("font", "")
                    fsize = round(float(sp.get("size", 0.0)), 1)
                    text = sp.get("text", "").strip()
                    if text:
                        font_counter[(fname, fsize)] += len(text)
                        page_fonts[(fname, fsize)] += len(text)
                if line_text and any(sp.get("flags", 0) & 16 or sp.get("size", 0) >= 11.5 for sp in line.get("spans", [])):
                    if len(line_text) < 120:
                        headings_guess.append({"page": idx + 1, "text": line_text})

        pages_info.append(
            {
                "page": idx + 1,
                "width_pt": round(rect.width, 1),
                "height_pt": round(rect.height, 1),
                "width_mm": round(rect.width * 0.352778, 1),
                "height_mm": round(rect.height * 0.352778, 1),
            }
        )

    return {
        "file": str(pdf_path),
        "type": "pdf",
        "page_count": len(doc),
        "first_page_dimensions": pages_info[0] if pages_info else None,
        "top_fonts_by_chars": [
            {"font": k[0], "size_pt": k[1], "chars": v} for k, v in font_counter.most_common(15)
        ],
        "candidate_headings": headings_guess[:60],
    }


def inspect_docx(docx_path: Path) -> dict:
    from docx import Document

    doc = Document(str(docx_path))
    sections = []
    for i, s in enumerate(doc.sections):
        sections.append(
            {
                "section": i + 1,
                "width_mm": round(s.page_width.mm, 1),
                "height_mm": round(s.page_height.mm, 1),
                "top_cm": round(s.top_margin.cm, 2),
                "bottom_cm": round(s.bottom_margin.cm, 2),
                "left_cm": round(s.left_margin.cm, 2),
                "right_cm": round(s.right_margin.cm, 2),
            }
        )

    headings = [
        {"style": p.style.name, "text": p.text.strip()}
        for p in doc.paragraphs
        if p.text.strip() and ("Heading" in p.style.name or len(p.text.strip()) < 100)
    ][:60]

    return {
        "file": str(docx_path),
        "type": "docx",
        "sections": sections,
        "paragraph_count": len(doc.paragraphs),
        "table_count": len(doc.tables),
        "sample_paragraphs_and_headings": headings,
    }


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Inspect PDF or DOCX reference layout.")
    parser.add_argument("path", help="Path to .pdf or .docx file")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"[Error] File not found: {target}")
        sys.exit(1)

    if target.suffix.lower() == ".pdf":
        report = inspect_pdf(target)
    elif target.suffix.lower() == ".docx":
        report = inspect_docx(target)
    else:
        print(f"[Error] Unsupported format: {target.suffix}")
        sys.exit(1)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(f"=== REFERENCE INSPECTION: {target.name} ===")
    if report["type"] == "pdf":
        dims = report["first_page_dimensions"]
        print(f"Pages: {report['page_count']} | Size: {dims['width_mm']} x {dims['height_mm']} mm")
        print("\nTop Fonts (by character count):")
        for f in report["top_fonts_by_chars"]:
            print(f"  - {f['font']} @ {f['size_pt']}pt ({f['chars']} chars)")
        print("\nCandidate Headings / Bold Lines (first 40):")
        for h in report["candidate_headings"][:40]:
            print(f"  [P{h['page']}] {h['text']}")
    else:
        print(f"Paragraphs: {report['paragraph_count']} | Tables: {report['table_count']}")
        print("Sections:", json.dumps(report["sections"], indent=2))
        print("\nHeadings / Sample Paragraphs:")
        for h in report["sample_paragraphs_and_headings"][:40]:
            print(f"  [{h['style']}] {h['text']}")


if __name__ == "__main__":
    main()

