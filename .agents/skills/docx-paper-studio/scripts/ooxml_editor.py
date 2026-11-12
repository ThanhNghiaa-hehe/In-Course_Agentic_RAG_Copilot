"""
OOXML Unpack / Comments Extractor / XML Validator / Pack utility for .docx files.
Provides Claude Code parity for surgical template & tracked-changes editing.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path
from lxml import etree


def unpack_docx(docx_path: Path, out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(docx_path, "r") as zf:
        zf.extractall(out_dir)

    # Pretty-print XML files for easy inspection and editing
    xml_count = 0
    for xml_file in out_dir.rglob("*.xml"):
        try:
            parser = etree.XMLParser(remove_blank_text=False)
            tree = etree.parse(str(xml_file), parser)
            tree.write(str(xml_file), xml_declaration=True, encoding="UTF-8", pretty_print=True)
            xml_count += 1
        except Exception:
            pass
    for rel_file in out_dir.rglob("*.rels"):
        try:
            tree = etree.parse(str(rel_file))
            tree.write(str(rel_file), xml_declaration=True, encoding="UTF-8", pretty_print=True)
            xml_count += 1
        except Exception:
            pass
    print(f"[OK] Unpacked {docx_path.name} -> {out_dir} ({xml_count} XML/rels formatted)")


def validate_unpacked_dir(src_dir: Path) -> list[str]:
    errors: list[str] = []
    if not (src_dir / "[Content_Types].xml").exists():
        errors.append("Missing [Content_Types].xml")
    if not (src_dir / "word" / "document.xml").exists():
        errors.append("Missing word/document.xml")

    for pattern in ("*.xml", "*.rels"):
        for f in src_dir.rglob(pattern):
            try:
                etree.parse(str(f))
            except etree.XMLSyntaxError as e:
                errors.append(f"XML syntax error in {f.relative_to(src_dir)}: {e}")
    return errors


def pack_docx(src_dir: Path, out_docx: Path) -> None:
    errors = validate_unpacked_dir(src_dir)
    if errors:
        print("[ERROR] Cannot pack invalid OOXML directory:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    out_docx.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_docx, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(src_dir.rglob("*")):
            if file_path.is_file():
                arcname = file_path.relative_to(src_dir).as_posix()
                zf.write(file_path, arcname)
    print(f"[OK] Packed {src_dir} -> {out_docx}")


def extract_comments(docx_path: Path) -> None:
    with zipfile.ZipFile(docx_path, "r") as zf:
        if "word/comments.xml" not in zf.namelist():
            print(f"[Info] No comments found in {docx_path.name}")
            return
        xml_bytes = zf.read("word/comments.xml")
    root = etree.fromstring(xml_bytes)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    comments = root.findall(".//w:comment", ns)
    print(f"=== COMMENTS IN {docx_path.name} ({len(comments)}) ===")
    for c in comments:
        cid = c.get(f"{{{ns['w']}}}id", "?")
        author = c.get(f"{{{ns['w']}}}author", "Unknown")
        date = c.get(f"{{{ns['w']}}}date", "")
        text = "".join(c.xpath(".//w:t/text()", namespaces=ns))
        print(f"  [#{cid} | {author} | {date}]: {text}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="OOXML toolkit for DOCX documents.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_unpack = sub.add_parser("unpack")
    p_unpack.add_argument("docx")
    p_unpack.add_argument("out_dir")

    p_pack = sub.add_parser("pack")
    p_pack.add_argument("src_dir")
    p_pack.add_argument("out_docx")

    p_val = sub.add_parser("validate")
    p_val.add_argument("src_dir")

    p_com = sub.add_parser("comments")
    p_com.add_argument("docx")

    args = parser.parse_args()
    if args.cmd == "unpack":
        unpack_docx(Path(args.docx), Path(args.out_dir))
    elif args.cmd == "pack":
        pack_docx(Path(args.src_dir), Path(args.out_docx))
    elif args.cmd == "validate":
        errs = validate_unpacked_dir(Path(args.src_dir))
        if errs:
            print("[FAIL]", "\n".join(errs))
            sys.exit(1)
        print("[OK] All OOXML parts valid.")
    elif args.cmd == "comments":
        extract_comments(Path(args.docx))


if __name__ == "__main__":
    main()

