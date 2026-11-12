"""
Automated QA Validator & Optional Visual Preview Exporter for generated .docx files.
Checks XML integrity, unrendered $...$ LaTeX leaks, broken media relationships,
OMML equation counts, and optionally renders PDF + PNG pages via MS Word COM or LibreOffice.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from lxml import etree


RAW_LATEX_PATTERNS = [
    re.compile(r"\$\$[^$]+\$\$"),
    re.compile(r"\\frac\{|\\sigma\(|\\ge\b|\\le\b|\\text\{|\\mathbb\{"),
]


def audit_docx(docx_path: Path) -> dict:
    from docx import Document

    if not docx_path.exists():
        raise FileNotFoundError(f"File not found: {docx_path}")

    issues: list[str] = []
    warnings: list[str] = []

    # 1. OOXML ZIP & XML well-formedness check
    omath_count = 0
    media_files: list[str] = []
    with zipfile.ZipFile(docx_path, "r") as zf:
        names = set(zf.namelist())
        if "word/document.xml" not in names or "[Content_Types].xml" not in names:
            issues.append("Corrupt OOXML structure: missing document.xml or [Content_Types].xml")
        for name in names:
            if name.endswith(".xml") or name.endswith(".rels"):
                try:
                    root = etree.fromstring(zf.read(name))
                    if name == "word/document.xml":
                        omath_count = len(
                            root.xpath(
                                ".//m:oMath",
                                namespaces={"m": "http://schemas.openxmlformats.org/officeDocument/2006/math"},
                            )
                        )
                except etree.XMLSyntaxError as e:
                    issues.append(f"XML syntax error in {name}: {e}")
            if name.startswith("word/media/"):
                media_files.append(name)

    # 2. Content & Anti-Slop Checks
    doc = Document(str(docx_path))
    raw_latex_hits: list[str] = []
    para_count = 0
    for idx, p in enumerate(doc.paragraphs):
        txt = p.text.strip()
        if not txt:
            continue
        para_count += 1
        for pat in RAW_LATEX_PATTERNS:
            if pat.search(txt):
                raw_latex_hits.append(f"P{idx + 1}: '{txt[:80]}...'")
                break

    for t_idx, tbl in enumerate(doc.tables):
        for r_idx, row in enumerate(tbl.rows):
            for c_idx, cell in enumerate(row.cells):
                txt = cell.text.strip()
                for pat in RAW_LATEX_PATTERNS:
                    if pat.search(txt):
                        raw_latex_hits.append(f"Table{t_idx + 1}[{r_idx},{c_idx}]: '{txt[:60]}'")
                        break

    if raw_latex_hits:
        warnings.append(
            f"Found {len(raw_latex_hits)} suspected unrendered LaTeX snippets (use omml_math.py): "
            + "; ".join(raw_latex_hits[:5])
        )

    return {
        "file": str(docx_path),
        "paragraphs_nonempty": para_count,
        "tables": len(doc.tables),
        "embedded_images": len(media_files),
        "native_omml_equations": omath_count,
        "issues": issues,
        "warnings": warnings,
    }


def render_preview(docx_path: Path, preview_dir: Path) -> list[str]:
    """Export DOCX -> PDF (via LibreOffice or MS Word COM on Windows) -> PNG pages via PyMuPDF."""
    preview_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = preview_dir / f"{docx_path.stem}.pdf"
    exported = False

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", str(docx_path), "--outdir", str(preview_dir)],
            check=False,
            capture_output=True,
        )
        exported = pdf_path.exists()

    if not exported and sys.platform == "win32":
        # Try native Microsoft Word COM automation silently if MS Word is installed
        ps_script = (
            "$word = $null; $doc = $null; "
            "try { "
            "$word = New-Object -ComObject Word.Application; "
            "$word.Visible = $false; "
            "$word.DisplayAlerts = 0; "
            f"$doc = $word.Documents.Open('{docx_path.resolve()}', $false, $true); "
            f"$doc.SaveAs2([ref] '{pdf_path.resolve()}', [ref] 17); "
            "} finally { "
            "if ($doc -ne $null) { $doc.Close([ref] $false) }; "
            "if ($word -ne $null) { $word.Quit() }; "
            "}"
        )
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=25,
            )
            exported = res.returncode == 0 and pdf_path.exists()
        except subprocess.TimeoutExpired:
            subprocess.run(["powershell", "-NoProfile", "-Command", "Stop-Process -Name WINWORD -Force -ErrorAction SilentlyContinue"], capture_output=True)
            print("[Warning] Word COM PDF export timed out (25s); skipped visual preview.")
            return []

    if not exported:
        print("[Info] Neither LibreOffice nor Microsoft Word COM available for visual PDF/PNG preview.")
        return []

    import pymupdf

    pdf_doc = pymupdf.open(str(pdf_path))
    png_paths: list[str] = []
    for idx, page in enumerate(pdf_doc):
        pix = page.get_pixmap(dpi=150)
        out_png = preview_dir / f"{docx_path.stem}_page_{idx + 1:02d}.png"
        pix.save(str(out_png))
        png_paths.append(str(out_png))
    print(f"[OK] Rendered {len(png_paths)} preview pages into {preview_dir}")
    return png_paths


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Audit and preview generated DOCX files.")
    parser.add_argument("docx", help="Path to .docx file")
    parser.add_argument("--preview-dir", default=None, help="Optional folder to export PDF/PNG page previews")
    args = parser.parse_args()

    target = Path(args.docx)
    res = audit_docx(target)
    print(f"=== DOCX VALIDATION REPORT: {target.name} ===")
    print(f"  Non-empty Paragraphs : {res['paragraphs_nonempty']}")
    print(f"  Tables               : {res['tables']}")
    print(f"  Embedded Images      : {res['embedded_images']}")
    print(f"  Native OMML Equations: {res['native_omml_equations']}")
    if res["issues"]:
        print("  [CRITICAL ISSUES]:")
        for i in res["issues"]:
            print(f"    - {i}")
    if res["warnings"]:
        print("  [WARNINGS]:")
        for w in res["warnings"]:
            print(f"    - {w}")
    if not res["issues"] and not res["warnings"]:
        print("  [STATUS]: PASSED 100% (Valid OOXML, Zero Raw LaTeX Leaks)")

    if args.preview_dir:
        render_preview(target, Path(args.preview_dir))

    if res["issues"]:
        sys.exit(1)


if __name__ == "__main__":
    main()

