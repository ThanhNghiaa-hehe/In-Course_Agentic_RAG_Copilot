---
name: docx-paper-studio
description: Complete Microsoft Word (.docx) creation, OOXML template editing, native OMML math equation rendering, 300-DPI figure embedding, and HJS academic journal formatting suite (Claude Code docx skill parity for Windows + Python).
---

# DOCX & Academic Paper Studio Skill

Professional suite for creating, editing, inspecting, and validating publication-grade Microsoft Word (`.docx`) documents, specifically tailored for **HUFLIT Journal of Science (HJS)** manuscripts, technical reports, and thesis deliverables — matching Claude Code's `docx` workflow on Windows without external cloud dependencies.

---

## Core Capabilities & Script Toolkit

All helper scripts live inside `.agents/skills/docx-paper-studio/scripts/` and run inside the workspace `.venv`:

| Script | Capability | When to Use |
| :--- | :--- | :--- |
| [inspect_reference.py](file:///d:/In_Course_Agentic_RAG_Copilot/.agents/skills/docx-paper-studio/scripts/inspect_reference.py) | Extracts page dimensions, margins, fonts, font sizes, section headings, and table counts from `.pdf` or `.docx` reference papers. | Always run first on a journal sample (e.g., `HJS@MTF-GCN_R3.pdf`) or official `.docx` template before generating a manuscript. |
| [docx_helpers.py](file:///d:/In_Course_Agentic_RAG_Copilot/.agents/skills/docx-paper-studio/scripts/docx_helpers.py) | Reusable `python-docx` building blocks: dual presets (`"hjs_journal"` matching `HJS@MTF-GCN_R3.pdf` with 3-mode First/Even/Odd headers, bottom rule, Cambria 10pt, Native `Heading 1/2/3`, `hjs_grid` white-grid tables, hanging-indent IEEE references, Author Bio grid; and `"thesis_a4"` A4 + Times New Roman 11pt + `booktabs` tables). | Import when assembling papers, daily reports, or defense dossiers from Python. |
| [omml_math.py](file:///d:/In_Course_Agentic_RAG_Copilot/.agents/skills/docx-paper-studio/scripts/omml_math.py) | Converts LaTeX formulas (`\sigma(z) = \frac{1}{1+e^{-z}}`) into **Native Word Equations (OMML)** via `latex2mathml` + `mathml2omml`, supporting both inline math and numbered display equations `(1)`, `(2)`. | Use for **every mathematical formula**. Never dump raw `$...$` LaTeX strings into Word text. |
| [ooxml_editor.py](file:///d:/In_Course_Agentic_RAG_Copilot/.agents/skills/docx-paper-studio/scripts/ooxml_editor.py) | Unpacks `.docx` into clean indented XML (`unpack`), lists tracked changes/comments (`comments`), validates XML well-formedness (`validate`), and repacks back into `.docx` (`pack`). | Use when performing surgical edits, preserving complex template XML, or reviewing advisor comments in `.docx` drafts. |
| [hjs_benchmark_charts.py](file:///d:/In_Course_Agentic_RAG_Copilot/.agents/skills/docx-paper-studio/scripts/hjs_benchmark_charts.py) | Generates 300-DPI grouped bar charts directly from `latest_benchmark_results.json` & `multiturn_benchmark_results.json` (0% hardcoded metrics). | Use before assembling the Results section of the HJS paper. |
| [validate_docx.py](file:///d:/In_Course_Agentic_RAG_Copilot/.agents/skills/docx-paper-studio/scripts/validate_docx.py) | Audits generated `.docx` for raw unrendered `$...$` leaks, empty table cells, broken media links, XML validity, and optionally exports PDF/PNG page previews via MS Word COM or LibreOffice. | **Mandatory** final gate before delivering any `.docx` file to the user or journal. |

---

## Decision Tree: Choosing the Right Workflow

1. **Creating a brand-new paper or report (e.g. HJS manuscript from benchmark JSONs):**
   - Step 1: Inspect the target template/sample (`inspect_reference.py`).
   - Step 2: Generate `300 DPI` charts with `matplotlib` directly from `docs/benchmarks/*.json` (never hardcode fabricated numbers).
   - Step 3: Build `.docx` using `docx_helpers.py` + `omml_math.py` (bind JSON metrics dynamically in Python).
   - Step 4: Run `validate_docx.py` and visually check rendered pages if PDF/PNG export is available.

2. **Editing an existing `.docx` template or advisor-reviewed draft (preserving exact styles/comments):**
   - For simple placeholder replacement or appending sections: load directly with `python-docx`.
   - For preserving Word tracked changes, custom XML shapes, or complex multi-column headers: use `ooxml_editor.py unpack` $\rightarrow$ edit `word/document.xml` cleanly $\rightarrow$ `ooxml_editor.py pack`.

3. **Adding JavaScript/Node `docx-js` workflow (optional parity):**
   - `node.exe` and `npm.ps1` are available on this system; if a task requires `docx-js`, install locally in a scratch folder (`npm install docx`) rather than polluting the Python repo root.

---

## Strict Quality Invariants (Anti-Slop Document Rules)

1. **Zero Raw LaTeX Leaks:** Every equation must be rendered as native Word OMML (`omml_math.py`), not plain `$x + y$` or `$$...$$` text.
2. **Zero Manual Number Transcription:** Paper tables and inline metrics must read directly from verified JSON artifacts (`docs/benchmarks/latest_benchmark_results.json`, `multiturn_benchmark_results.json`, `multiturn_benchmark_e2e_results.json`).
3. **Academic Table Hygiene:**
   - Set explicit column widths (`w:gridCol` + cell `w:tcW`).
   - Enable `tblHeader` on header rows so multi-page tables repeat headers automatically.
   - Set `cantSplit` on every table row so rows never tear across page breaks.
   - Use **Three-Line Academic Borders** (top 1.5pt, header-bottom 0.75pt, table-bottom 1.5pt; no heavy vertical grid lines).
4. **Keep-With-Next Headings & Captions:** All headings (`Heading 1/2/3`) must have `keep_with_next = True`; figure paragraphs must have `keep_with_next = True` before their `"Hình X:"` caption, and table captions (`"Bảng X:"`) must have `keep_with_next = True` before the table.
5. **High-DPI Figures:** Embed plots at **300 DPI** with legible `Times New Roman` / sans-serif labels matching document body size (`9–10pt` scaled) and clean Slate/Indigo academic palettes (`#1e293b`, `#4f46e5`, `#0ea5e9`, `#10b981`).
6. **Author Invariant:** Sinh viên thực hiện: **Trần Thành Nghĩa** (MSSV: `23DH112252`), Khoa Công nghệ Thông tin, Trường Đại học Ngoại ngữ - Tin học TP.HCM (**HUFLIT**).

---

## Quick Usage Examples

```powershell
# 1. Inspect reference PDF structure (margins, fonts, headings)
.\.venv\Scripts\python.exe .agents\skills\docx-paper-studio\scripts\inspect_reference.py "c:\Users\Admin\Downloads\HJS@MTF-GCN_R3.pdf"

# 2. Unpack / Inspect / Repack an existing .docx via OOXML
.\.venv\Scripts\python.exe .agents\skills\docx-paper-studio\scripts\ooxml_editor.py unpack paper.docx scratch\unpacked_paper
.\.venv\Scripts\python.exe .agents\skills\docx-paper-studio\scripts\ooxml_editor.py comments paper.docx
.\.venv\Scripts\python.exe .agents\skills\docx-paper-studio\scripts\ooxml_editor.py pack scratch\unpacked_paper paper_edited.docx

# 3. Validate a generated .docx (+ optional PDF/PNG preview if Word/LibreOffice exists)
.\.venv\Scripts\python.exe .agents\skills\docx-paper-studio\scripts\validate_docx.py docs\paper_draft.docx --preview-dir scratch\preview
```
