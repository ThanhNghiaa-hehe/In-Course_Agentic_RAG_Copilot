"""
Data-Centric Offline Transcript Canonicalizer & Visual-Proxy Hotword Generator.
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Tính năng:
1. Per-Lesson Visual-Proxy Lexicon Extractor:
   - Đọc `data/curriculum/lessons_manifest.json` (title, keywords, video_chapters).
   - Bóc tách symbol & scope C++ thực tế từ `data/sample_codes/*` bằng Tree-sitter C++.
   - Kết hợp từ điển học thuật `data/metadata/cpp_academic_glossary.json`.
   - Sinh `hotwords_list` (dùng cho `faster-whisper` MP3 transcription) và `lexicon_prompt` (dùng cho LLM post-correction).
2. Context-Aware LLM Post-Correction + Strict Integrity Guardrail:
   - Chỉ sửa lỗi phiên âm ASR/phonetic của thuật ngữ kỹ thuật; cấm tóm tắt, viết lại hoặc ảo giác CJK/Hangul.
   - Guardrail fail tự động fallback về `original_text`.
3. CLI an toàn mặc định (`--audit-hotwords`, `--dry-run`, `--apply [--sync-qdrant] [--refresh-chapters]`).
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import itertools
import json
import os
import re
import socket
import sys
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import tree_sitter
import tree_sitter_cpp as tscpp

from app.config import settings

MANIFEST_PATH = PROJECT_ROOT / "data" / "curriculum" / "lessons_manifest.json"
SAMPLE_CODES_DIR = PROJECT_ROOT / "data" / "sample_codes"
GLOSSARY_PATH = PROJECT_ROOT / "data" / "metadata" / "cpp_academic_glossary.json"
TRANSCRIPTS_DIR = PROJECT_ROOT / "data" / "transcripts"

BASE_COURSE_HOTWORDS: Dict[str, List[str]] = {
    "cpp-core": [
        "C++", "include", "iostream", "namespace", "std", "cin", "cout",
        "endl", "main", "int", "float", "double", "char", "bool", "void",
        "string", "vector", "array", "struct", "pointer", "return",
    ],
    "cpp-oop": [
        "C++", "OOP", "class", "object", "struct", "private", "public",
        "protected", "Access Modifier", "Encapsulation", "Constructor",
        "Destructor", "Inheritance", "Polymorphism", "Abstraction",
        "this", "friend", "static", "virtual", "override", "operator",
        "getter", "setter", "istream", "ostream", "cin", "cout", "endl",
    ],
}

# Các thuật ngữ kỹ thuật ánh xạ trực tiếp từ nút cú pháp C++ AST (không phụ thuộc câu hỏi cụ thể)
AST_CONCEPT_HOTWORDS: Dict[str, List[str]] = {
    "access_specifier": ["Access Modifier", "private", "public", "protected", "Encapsulation"],
    "class_specifier": ["class", "object", "attribute", "method"],
    "struct_specifier": ["struct", "field"],
    "destructor_name": ["Destructor"],
    "operator_name": ["operator overloading"],
    "friend_declaration": ["friend function", "friend class"],
    "static_storage": ["static", "static member"],
    "base_class_clause": ["Inheritance"],
    "virtual_specifier": ["virtual", "Polymorphism", "override"],
    "pointer_declarator": ["pointer"],
    "reference_declarator": ["reference"],
    "array_declarator": ["array", "mảng", "mảng một chiều", "chỉ số mảng"],
    "template_declaration": ["template"],
}

# Thuật ngữ tiếng Anh kỹ thuật phổ biến trong comment giáo trình C++
COMMENT_TECH_PATTERNS: Tuple[str, ...] = (
    "Access modifier", "Encapsulation", "Inheritance", "Polymorphism", "Abstraction",
    "Constructor", "Destructor", "Static variable", "Static method", "Static class",
    "Static constructor", "Friend function", "Friend class", "this pointer",
    "setter", "getter", "attribute", "method", "behavior", "object", "class",
    "comparator", "operator overloading", "overriding", "virtual", "private",
    "public", "protected", "pointer", "reference", "namespace", "template",
)

_CPP_LANGUAGE = tree_sitter.Language(tscpp.language())
_CPP_PARSER = tree_sitter.Parser(_CPP_LANGUAGE)


def _dedupe_preserve_order(items: Sequence[str]) -> List[str]:
    """Loại bỏ trùng lặp (case-insensitive cho ASCII/Unicode NFC) nhưng giữ thứ tự ưu tiên."""
    seen = set()
    result: List[str] = []
    for raw in items:
        item = unicodedata.normalize("NFC", str(raw or "")).strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def load_manifest(manifest_path: Path = MANIFEST_PATH) -> Dict[str, Any]:
    """Đọc file lessons_manifest.json."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_glossary(glossary_path: Path = GLOSSARY_PATH) -> Dict[str, List[Dict[str, Any]]]:
    """Đọc từ điển thuật ngữ học thuật C++."""
    if not glossary_path.exists():
        return {}
    with open(glossary_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("glossary", {})


def iter_manifest_lessons(manifest: Optional[Dict[str, Any]] = None) -> List[Tuple[str, Dict[str, Any]]]:
    """Liệt kê toàn bộ (course_id, lesson_dict) theo thứ tự trong manifest."""
    data = manifest if manifest is not None else load_manifest()
    rows: List[Tuple[str, Dict[str, Any]]] = []
    for cid, cdata in data.get("courses", {}).items():
        for lesson in cdata.get("lessons", []):
            rows.append((cid, lesson))
    return rows


def find_lesson_in_manifest(
    course_id: Optional[str],
    lesson_seq: int,
    manifest: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Tìm bài học theo (course_id, lesson_seq); fallback tìm theo seq nếu course_id trống."""
    data = manifest if manifest is not None else load_manifest()
    courses = data.get("courses", {})
    if course_id and course_id in courses:
        for lesson in courses[course_id].get("lessons", []):
            if int(lesson.get("seq", -1)) == int(lesson_seq):
                return course_id, lesson

    for cid, cdata in courses.items():
        for lesson in cdata.get("lessons", []):
            if int(lesson.get("seq", -1)) == int(lesson_seq):
                return cid, lesson

    raise KeyError(f"Lesson seq={lesson_seq} (course={course_id}) not found in {MANIFEST_PATH}")


def _extract_declarator_info(node: tree_sitter.Node, source_bytes: bytes) -> Dict[str, str]:
    """Đi xuyên qua pointer/reference/function declarator để lấy tên hàm/phương thức/toán tử."""
    info: Dict[str, str] = {"name": "", "qualified": "", "kind": "function"}

    def _walk_decl(n: tree_sitter.Node) -> None:
        ntype = n.type
        if ntype == "qualified_identifier":
            text = source_bytes[n.start_byte:n.end_byte].decode("utf-8", errors="ignore").strip()
            info["qualified"] = text
            parts = text.split("::")
            info["name"] = parts[-1].strip()
            if info["name"].startswith("~"):
                info["kind"] = "destructor"
            elif info["name"].startswith("operator"):
                info["kind"] = "operator"
            else:
                info["kind"] = "method"
            return
        if ntype == "destructor_name":
            text = source_bytes[n.start_byte:n.end_byte].decode("utf-8", errors="ignore").strip()
            info["name"] = text
            info["kind"] = "destructor"
            return
        if ntype == "operator_name":
            text = source_bytes[n.start_byte:n.end_byte].decode("utf-8", errors="ignore").strip()
            info["name"] = " ".join(text.split())
            info["kind"] = "operator"
            return
        if ntype in ("identifier", "field_identifier"):
            text = source_bytes[n.start_byte:n.end_byte].decode("utf-8", errors="ignore").strip()
            if not info["name"]:
                info["name"] = text
            return
        for child in n.children:
            if child.type == "parameter_list":
                continue
            _walk_decl(child)

    _walk_decl(node)
    return info


def extract_cpp_ast_symbols(source_text: str) -> Dict[str, List[str]]:
    """
    Bóc tách các ký hiệu & phạm vi C++ thực tế bằng Tree-sitter C++:
    - classes, structs, functions, methods, operators, fields
    - access_specifiers, headers, scopes, concept_hints
    """
    if not source_text or not source_text.strip():
        return {
            "classes": [],
            "structs": [],
            "functions": [],
            "methods": [],
            "operators": [],
            "fields": [],
            "access_specifiers": [],
            "headers": [],
            "scopes": [],
            "concept_hints": [],
        }

    source_bytes = source_text.encode("utf-8", errors="ignore")
    tree = _CPP_PARSER.parse(source_bytes)

    classes: List[str] = []
    structs: List[str] = []
    functions: List[str] = []
    methods: List[str] = []
    operators: List[str] = []
    fields: List[str] = []
    access_specifiers: List[str] = []
    headers: List[str] = []
    scopes: List[str] = []
    concept_hints: List[str] = []

    def _node_text(n: tree_sitter.Node) -> str:
        return source_bytes[n.start_byte:n.end_byte].decode("utf-8", errors="ignore").strip()

    def _collect_comments_hints(text: str) -> None:
        low = text.lower()
        for pat in COMMENT_TECH_PATTERNS:
            if pat.lower() in low:
                concept_hints.append(pat)

    def _walk(node: tree_sitter.Node, enclosing_type: Optional[str] = None) -> None:
        ntype = node.type

        if ntype == "preproc_include":
            raw_inc = _node_text(node)
            for child in node.children:
                if child.type in ("system_lib_string", "string_literal"):
                    hdr = _node_text(child).strip("<>\"' ")
                    if hdr:
                        headers.append(hdr)
                        scopes.append(f"header:{hdr}")
            if not headers and "<" in raw_inc:
                hdr = raw_inc.split("<", 1)[-1].split(">", 1)[0].strip()
                if hdr:
                    headers.append(hdr)
            return

        if ntype in ("class_specifier", "struct_specifier"):
            type_name = ""
            has_body = False
            for child in node.children:
                if child.type == "type_identifier":
                    type_name = _node_text(child)
                elif child.type == "field_declaration_list":
                    has_body = True
                elif child.type == "base_class_clause":
                    concept_hints.extend(AST_CONCEPT_HOTWORDS["base_class_clause"])
                    for sub in child.children:
                        if sub.type == "type_identifier":
                            base_name = _node_text(sub)
                            if base_name:
                                classes.append(base_name)
            if type_name:
                if ntype == "class_specifier":
                    classes.append(type_name)
                    if has_body:
                        scopes.append(f"class:{type_name}")
                        concept_hints.extend(AST_CONCEPT_HOTWORDS["class_specifier"])
                else:
                    structs.append(type_name)
                    if has_body:
                        scopes.append(f"struct:{type_name}")
                        concept_hints.extend(AST_CONCEPT_HOTWORDS["struct_specifier"])
            for child in node.children:
                _walk(child, enclosing_type=type_name or enclosing_type)
            return

        if ntype == "access_specifier":
            spec = _node_text(node).rstrip(":").strip()
            if spec in ("private", "public", "protected"):
                access_specifiers.append(spec)
            concept_hints.extend(AST_CONCEPT_HOTWORDS["access_specifier"])
            return

        if ntype == "storage_class_specifier":
            if _node_text(node) == "static":
                concept_hints.extend(AST_CONCEPT_HOTWORDS["static_storage"])
            return

        if ntype == "virtual":
            concept_hints.extend(AST_CONCEPT_HOTWORDS["virtual_specifier"])
            return

        if ntype == "friend_declaration":
            concept_hints.extend(AST_CONCEPT_HOTWORDS["friend_declaration"])
            for child in node.children:
                _walk(child, enclosing_type=enclosing_type)
            return

        if ntype == "template_declaration":
            concept_hints.extend(AST_CONCEPT_HOTWORDS["template_declaration"])

        if ntype == "pointer_declarator":
            concept_hints.extend(AST_CONCEPT_HOTWORDS["pointer_declarator"])
        elif ntype == "reference_declarator":
            concept_hints.extend(AST_CONCEPT_HOTWORDS["reference_declarator"])
        elif ntype == "array_declarator":
            concept_hints.extend(AST_CONCEPT_HOTWORDS["array_declarator"])

        if ntype == "field_declaration":
            # Có thể là khai báo thuộc tính hoặc prototype phương thức trong class/struct
            has_func_decl = any(c.type == "function_declarator" or "function_declarator" in _node_text(c) for c in node.children if c.type in ("function_declarator", "reference_declarator", "pointer_declarator"))
            for child in node.children:
                if child.type == "function_declarator" or (child.type in ("reference_declarator", "pointer_declarator")):
                    dinfo = _extract_declarator_info(child, source_bytes)
                    if dinfo["kind"] == "operator" and dinfo["name"]:
                        operators.append(dinfo["name"])
                        concept_hints.extend(AST_CONCEPT_HOTWORDS["operator_name"])
                    elif dinfo["kind"] == "destructor" and dinfo["name"]:
                        methods.append(dinfo["name"])
                        concept_hints.extend(AST_CONCEPT_HOTWORDS["destructor_name"])
                    elif dinfo["name"] and has_func_decl:
                        if enclosing_type:
                            methods.append(f"{enclosing_type}::{dinfo['name']}")
                        methods.append(dinfo["name"])
                elif child.type == "field_identifier" and not has_func_decl:
                    fname = _node_text(child)
                    if len(fname) >= 2:
                        fields.append(fname)
                elif child.type == "storage_class_specifier" and _node_text(child) == "static":
                    concept_hints.extend(AST_CONCEPT_HOTWORDS["static_storage"])
            return

        if ntype == "function_definition":
            decl_node = None
            for child in node.children:
                if child.type in ("function_declarator", "pointer_declarator", "reference_declarator"):
                    decl_node = child
                    break
            if decl_node is not None:
                dinfo = _extract_declarator_info(decl_node, source_bytes)
                if dinfo["qualified"]:
                    methods.append(dinfo["qualified"])
                    scopes.append(f"method:{dinfo['qualified']}")
                    if dinfo["name"]:
                        methods.append(dinfo["name"])
                    if dinfo["kind"] == "destructor":
                        concept_hints.extend(AST_CONCEPT_HOTWORDS["destructor_name"])
                    elif dinfo["kind"] == "operator":
                        operators.append(dinfo["name"])
                        concept_hints.extend(AST_CONCEPT_HOTWORDS["operator_name"])
                elif dinfo["kind"] == "operator" and dinfo["name"]:
                    operators.append(dinfo["name"])
                    scopes.append(f"operator:{dinfo['name']}")
                    concept_hints.extend(AST_CONCEPT_HOTWORDS["operator_name"])
                elif dinfo["kind"] == "destructor" and dinfo["name"]:
                    methods.append(dinfo["name"])
                    scopes.append(f"destructor:{dinfo['name']}")
                    concept_hints.extend(AST_CONCEPT_HOTWORDS["destructor_name"])
                elif dinfo["name"]:
                    if enclosing_type:
                        qual = f"{enclosing_type}::{dinfo['name']}"
                        methods.append(qual)
                        methods.append(dinfo["name"])
                        scopes.append(f"method:{qual}")
                    else:
                        functions.append(dinfo["name"])
                        scopes.append(f"function:{dinfo['name']}")
            for child in node.children:
                _walk(child, enclosing_type=enclosing_type)
            return

        if ntype == "comment":
            _collect_comments_hints(_node_text(node))
            return

        for child in node.children:
            _walk(child, enclosing_type=enclosing_type)

    _walk(tree.root_node)

    return {
        "classes": _dedupe_preserve_order(classes),
        "structs": _dedupe_preserve_order(structs),
        "functions": _dedupe_preserve_order(functions),
        "methods": _dedupe_preserve_order(methods),
        "operators": _dedupe_preserve_order(operators),
        "fields": _dedupe_preserve_order(fields),
        "access_specifiers": _dedupe_preserve_order(access_specifiers),
        "headers": _dedupe_preserve_order(headers),
        "scopes": _dedupe_preserve_order(scopes),
        "concept_hints": _dedupe_preserve_order(concept_hints),
    }


def discover_lesson_code_files(
    course_id: Optional[str],
    lesson_seq: int,
    sample_codes_dir: Path = SAMPLE_CODES_DIR,
) -> List[Path]:
    """Tìm các file .cpp và *_ast_chunks.json tương ứng với bài học."""
    if not sample_codes_dir.exists():
        return []

    seq_patterns = (f"lesson_{lesson_seq:02d}", f"lesson_{lesson_seq}")
    search_dirs: List[Path] = []
    if course_id and (sample_codes_dir / course_id).is_dir():
        search_dirs.append(sample_codes_dir / course_id)
    for sub in sorted(sample_codes_dir.iterdir()):
        if sub.is_dir() and sub not in search_dirs:
            search_dirs.append(sub)

    matched: List[Path] = []
    seen = set()
    for directory in search_dirs:
        for p in sorted(directory.iterdir()):
            if not p.is_file():
                continue
            stem = p.name
            is_match = any(
                stem == f"{pat}.cpp" or stem == f"{pat}_ast_chunks.json"
                for pat in seq_patterns
            )
            if is_match and p.resolve() not in seen:
                seen.add(p.resolve())
                matched.append(p)
    return matched


def _match_glossary_terms(
    course_id: str,
    title: str,
    keywords: List[str],
    ast_symbols: Dict[str, List[str]],
    glossary: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Khớp các mục từ điển học thuật C++ liên quan nhất tới bài học & AST."""
    haystack_parts = [course_id, title] + keywords
    for vals in ast_symbols.values():
        haystack_parts.extend(vals)
    haystack = unicodedata.normalize("NFC", " ".join(haystack_parts)).lower()

    has_class_ast = bool(
        ast_symbols.get("classes")
        or ast_symbols.get("access_specifiers")
        or any(k in haystack for k in ("oop", "class", "object", "hướng đối tượng", "kế thừa", "đa hình", "đóng gói", "trừu tượng", "constructor", "destructor"))
    )
    has_sort_kw = any(k in haystack for k in ("sắp xếp", "sort", "bubble", "selection", "insertion", "quick", "merge"))
    has_search_kw = any(k in haystack for k in ("tìm kiếm", "search", "binary", "linear", "nhị phân", "tuần tự"))
    has_ptr_kw = any(k in haystack for k in ("con trỏ", "pointer", "tham chiếu", "reference", "cấp phát động", "new", "delete", "2 chiều", "hai chiều", "ma trận"))

    category_triggers = {
        "object_oriented_programming": has_class_ast or course_id == "cpp-oop",
        "sorting_algorithms": has_sort_kw,
        "searching_algorithms": has_search_kw,
        "memory_and_pointers": has_ptr_kw,
    }

    matched: List[Dict[str, Any]] = []
    seen_en = set()
    for cat, entries in glossary.items():
        cat_triggered = category_triggers.get(cat, False)
        for entry in entries:
            en = str(entry.get("en", "")).strip()
            vi = str(entry.get("vi", "")).strip()
            if not en or en.lower() in seen_en:
                continue
            token_hit = (en.lower() in haystack) or (vi.lower() in haystack)
            # Với OOP hoặc sorting/searching/pointer, chỉ lấy mục khớp trực tiếp hoặc toàn bộ nhóm OOP khi bài là OOP chính thức
            if token_hit or (cat == "object_oriented_programming" and has_class_ast) or (cat_triggered and any(w in haystack for w in en.lower().split() if len(w) >= 4)):
                seen_en.add(en.lower())
                matched.append(entry)
    return matched


def extract_lesson_lexicon(
    course_id: str,
    lesson_seq: int,
    *,
    manifest_path: Path = MANIFEST_PATH,
    sample_codes_dir: Path = SAMPLE_CODES_DIR,
    glossary_path: Path = GLOSSARY_PATH,
) -> Dict[str, Any]:
    """
    Per-Lesson Visual-Proxy Lexicon Extractor.
    Tổng hợp từ vựng bài học từ:
      1. `lessons_manifest.json` (title, keywords, video_chapters)
      2. `data/sample_codes/*` (file `.cpp` & `*_ast_chunks.json` qua Tree-sitter C++)
      3. `data/metadata/cpp_academic_glossary.json`
    Trả về dict chứa `hotwords_list`, `lexicon_prompt`, `ast_symbols`, `glossary_terms`, v.v.
    """
    manifest = load_manifest(manifest_path)
    resolved_cid, lesson = find_lesson_in_manifest(course_id, lesson_seq, manifest)
    glossary = load_glossary(glossary_path)

    title = unicodedata.normalize("NFC", str(lesson.get("title", f"Bài {lesson_seq}"))).strip()
    keywords = [unicodedata.normalize("NFC", str(k)).strip() for k in lesson.get("keywords", []) if str(k).strip()]
    video_chapters = list(lesson.get("video_chapters", []))

    code_files = discover_lesson_code_files(resolved_cid, lesson_seq, sample_codes_dir=sample_codes_dir)
    merged_ast: Dict[str, List[str]] = {
        "classes": [],
        "structs": [],
        "functions": [],
        "methods": [],
        "operators": [],
        "fields": [],
        "access_specifiers": [],
        "headers": [],
        "scopes": [],
        "concept_hints": [],
    }

    cpp_files = [p for p in code_files if p.suffix == ".cpp"]
    ast_json_files = [p for p in code_files if p.name.endswith("_ast_chunks.json")]

    # Ưu tiên parse trực tiếp file .cpp đầy đủ (có cả comment sư phạm của giảng viên); bổ sung từ *_ast_chunks.json nếu chưa có .cpp
    for cf in cpp_files:
        src = cf.read_text(encoding="utf-8", errors="ignore")
        parsed = extract_cpp_ast_symbols(src)
        for key, vals in parsed.items():
            merged_ast[key].extend(vals)

    for jf in ast_json_files:
        try:
            chunks = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            chunks = []
        if isinstance(chunks, list):
            for ch in chunks:
                c_scope = str(ch.get("code_scope", "")).strip()
                if c_scope and c_scope != "function_anonymous":
                    merged_ast["scopes"].append(c_scope)
                f_name = str(ch.get("func_name", "")).strip()
                if f_name and f_name != "anonymous":
                    merged_ast["functions"].append(f_name)
                raw_code = str(ch.get("raw_text", "") or ch.get("context_code", ""))
                if raw_code and not cpp_files:
                    parsed = extract_cpp_ast_symbols(raw_code)
                    for key, vals in parsed.items():
                        merged_ast[key].extend(vals)

    for key in merged_ast:
        merged_ast[key] = _dedupe_preserve_order(merged_ast[key])

    glossary_matches = _match_glossary_terms(resolved_cid, title, keywords, merged_ast, glossary)

    # Xây dựng danh sách hotwords theo thứ tự ưu tiên cao -> thấp
    raw_hotwords: List[str] = []
    # 1. Ký hiệu AST đặc thù của bài học
    raw_hotwords.extend(merged_ast["classes"])
    raw_hotwords.extend(merged_ast["structs"])
    raw_hotwords.extend(merged_ast["access_specifiers"])
    raw_hotwords.extend(merged_ast["concept_hints"])
    raw_hotwords.extend(merged_ast["operators"])
    raw_hotwords.extend(merged_ast["methods"])
    raw_hotwords.extend(merged_ast["functions"])
    raw_hotwords.extend(merged_ast["headers"])
    # 2. Từ khóa học thuật từ glossary
    for g in glossary_matches:
        if g.get("en"):
            raw_hotwords.append(str(g["en"]))
        if g.get("vi"):
            raw_hotwords.append(str(g["vi"]))
    # 3. Keywords trong lessons_manifest
    raw_hotwords.extend(keywords)
    # 4. Nền tảng khóa học
    raw_hotwords.extend(BASE_COURSE_HOTWORDS.get(resolved_cid, BASE_COURSE_HOTWORDS["cpp-core"]))

    hotwords_list = _dedupe_preserve_order(raw_hotwords)

    # Xây dựng lexicon_prompt dùng chung cho cả Whisper & LLM Post-Correction
    chapter_topics = [
        f"{ch.get('label', '00:00')}: {str(ch.get('summary', '')).strip()}"
        for ch in video_chapters[:8]
        if str(ch.get("summary", "")).strip()
    ]
    glossary_lines = [
        f"- {g['en']} = {g['vi']}"
        + (f" (KHÔNG dịch thành: {', '.join(g['forbidden_translations'])})" if g.get("forbidden_translations") else "")
        for g in glossary_matches
    ]

    prompt_sections = [
        f"Bài học: [{resolved_cid}] {title}",
        f"Từ khóa giáo trình: {', '.join(keywords) if keywords else '(không có)'}",
    ]
    if any(merged_ast[k] for k in ("classes", "structs", "methods", "functions", "operators", "access_specifiers", "concept_hints")):
        ast_lines = []
        if merged_ast["classes"]:
            ast_lines.append(f"  - Classes: {', '.join(merged_ast['classes'])}")
        if merged_ast["structs"]:
            ast_lines.append(f"  - Structs: {', '.join(merged_ast['structs'])}")
        if merged_ast["access_specifiers"]:
            ast_lines.append(f"  - Access Specifiers: {', '.join(merged_ast['access_specifiers'])}")
        if merged_ast["methods"]:
            ast_lines.append(f"  - Methods: {', '.join(merged_ast['methods'][:20])}")
        if merged_ast["functions"]:
            ast_lines.append(f"  - Functions: {', '.join(merged_ast['functions'][:15])}")
        if merged_ast["operators"]:
            ast_lines.append(f"  - Operators: {', '.join(merged_ast['operators'])}")
        if merged_ast["headers"]:
            ast_lines.append(f"  - Headers: {', '.join(merged_ast['headers'])}")
        if merged_ast["concept_hints"]:
            ast_lines.append(f"  - Code Concept Hints: {', '.join(merged_ast['concept_hints'][:20])}")
        prompt_sections.append("Ký hiệu C++ AST thực tế:\n" + "\n".join(ast_lines))

    if glossary_lines:
        prompt_sections.append("Từ điển thuật ngữ C++ chuẩn:\n" + "\n".join(glossary_lines))
    if chapter_topics:
        prompt_sections.append("Mục lục phân đoạn tham chiếu:\n  " + "\n  ".join(chapter_topics))
    prompt_sections.append(f"Hotwords ưu tiên: {', '.join(hotwords_list[:45])}")

    lexicon_prompt = "\n".join(prompt_sections)

    return {
        "course_id": resolved_cid,
        "lesson_seq": int(lesson_seq),
        "lesson_id": f"lesson-{int(lesson_seq):02d}",
        "title": title,
        "keywords": keywords,
        "video_chapters": video_chapters,
        "ast_files": [str(p) for p in code_files],
        "has_ast": bool(code_files),
        "ast_symbols": merged_ast,
        "glossary_terms": glossary_matches,
        "hotwords_list": hotwords_list,
        "hotwords_str": ", ".join(hotwords_list),
        "lexicon_prompt": lexicon_prompt,
    }


def extract_lesson_hotwords(
    course_id: str,
    lesson_seq: int,
    max_hotwords: int = 40,
    **kwargs: Any,
) -> str:
    """Trả về chuỗi `hotwords` chuẩn cho `faster-whisper` (`model.transcribe(..., hotwords=...)`)."""
    lexicon = extract_lesson_lexicon(course_id, lesson_seq, **kwargs)
    return ", ".join(lexicon["hotwords_list"][:max(1, int(max_hotwords))])


def _contains_cjk_or_hangul(text: str) -> bool:
    """Kiểm tra ký tự ảo giác CJK, Kana, Hangul hoặc replacement character."""
    for ch in text:
        code = ord(ch)
        if (
            (0x4E00 <= code <= 0x9FFF)       # CJK Unified Ideographs
            or (0x3400 <= code <= 0x4DBF)    # CJK Extension A
            or (0x20000 <= code <= 0x2A6DF)  # CJK Extension B
            or (0xF900 <= code <= 0xFAFF)    # CJK Compatibility Ideographs
            or (0x3040 <= code <= 0x30FF)    # Hiragana & Katakana
            or (0xAC00 <= code <= 0xD7AF)    # Hangul Syllables
            or (0x1100 <= code <= 0x11FF)    # Hangul Jamo
            or (0x3130 <= code <= 0x318F)    # Hangul Compatibility Jamo
            or code == 0xFFFD                # Unicode replacement char
        ):
            return True
    return False


def _non_punct_tokens(text: str) -> List[str]:
    """Tách token bỏ dấu câu (giữ chữ tiếng Việt có dấu, chữ số, '+', '_')."""
    norm = unicodedata.normalize("NFC", text).lower()
    cleaned_chars = [
        " " if (unicodedata.category(ch).startswith("P") and ch != "_") else ch
        for ch in norm
    ]
    return [tok for tok in "".join(cleaned_chars).split() if tok]


def validate_canonical_chunk(original_text: str, candidate_text: str) -> Tuple[bool, str]:
    """
    Strict Integrity Guardrail cho chunk sau hiệu đính LLM:
    - Không rỗng
    - Không ảo giác CJK / Hangul / replacement char
    - Tỷ lệ độ dài ký tự: 0.82 <= len(cand) / max(len(orig), 1) <= 1.18
    - Tỷ lệ số từ: 0.80 <= wc(cand) / max(wc(orig), 1) <= 1.20
    - Độ bảo toàn ngữ cảnh phi dấu câu (token Jaccard) >= 0.55
    """
    orig = unicodedata.normalize("NFC", (original_text or "")).strip()
    cand = unicodedata.normalize("NFC", (candidate_text or "")).strip()

    if not cand:
        return False, "empty_output"
    if not orig:
        return False, "empty_original"
    if _contains_cjk_or_hangul(cand):
        return False, "cjk_or_hangul_hallucination"

    len_ratio = len(cand) / max(len(orig), 1)
    if len_ratio < 0.82 or len_ratio > 1.18:
        return False, f"length_ratio_out_of_bounds:{len_ratio:.3f}"

    orig_words = orig.split()
    cand_words = cand.split()
    wc_ratio = len(cand_words) / max(len(orig_words), 1)
    if wc_ratio < 0.80 or wc_ratio > 1.20:
        return False, f"word_count_ratio_out_of_bounds:{wc_ratio:.3f}"

    orig_tokens = _non_punct_tokens(orig)
    cand_tokens = _non_punct_tokens(cand)
    if not orig_tokens or not cand_tokens:
        return False, "no_non_punct_tokens"

    orig_set = set(orig_tokens)
    cand_set = set(cand_tokens)
    union_set = orig_set | cand_set
    jaccard = len(orig_set & cand_set) / len(union_set) if union_set else 0.0
    if jaccard < 0.55:
        return False, f"low_context_retention:{jaccard:.3f}"

    return True, "ok"


def build_correction_prompt(
    chunks_batch: Sequence[Dict[str, Any]],
    lexicon: Dict[str, Any],
) -> Tuple[str, str]:
    """Tạo (system_prompt, user_prompt) ép LLM chỉ sửa lỗi nghe nhầm thuật ngữ ASR."""
    system_prompt = (
        "Bạn là bộ hiệu đính thuật ngữ kỹ thuật C++ cho bản phiên âm (ASR transcript) bài giảng tiếng Việt.\n"
        "QUY TẮC BẮT BUỘC (VI PHẠM SẼ BỊ HỦY):\n"
        "1. CHỈ sửa các lỗi nghe nhầm âm thanh (phonetic/ASR typos) của từ khóa C++, tên lớp/hàm/phương thức, hoặc thuật ngữ lập trình "
        "(ví dụ: 'Assets Modifier' -> 'Access Modifier', 'si cộng cộng' -> 'C++', 'xì in' -> 'cin', 'xì out' -> 'cout', 'class selector' -> 'class vector').\n"
        "2. TUYỆT ĐỐI KHÔNG tóm tắt, KHÔNG viết lại câu, KHÔNG dịch lời giảng tiếng Việt sang tiếng Anh, KHÔNG thêm hoặc xóa ý.\n"
        "3. Thay thế từ lỗi đúng 1-đối-1 theo âm tiết gốc (ví dụ: 'mạng' -> 'mảng', KHÔNG tự ý mở rộng 'mạng' thành 'mảng một chiều' nếu câu gốc chỉ nói 'mạng'). Giữ nguyên văn phong nói, độ dài và cấu trúc câu gốc (độ dài thay đổi <= 15%).\n"
        "4. Trả về DUY NHẤT JSON object dạng {\"<chunk_id>\": \"<văn bản đã hiệu đính>\", ...}, không kèm giải thích ngoài JSON."
    )

    payload_items = [
        {
            "chunk_id": str(c.get("chunk_id") or f"idx_{idx}"),
            "start_label": c.get("start_label", ""),
            "text": str(c.get("raw_text") or c.get("text") or ""),
        }
        for idx, c in enumerate(chunks_batch)
    ]

    user_prompt = (
        "=== NGỮ CẢNH TỪ VỰNG BÀI HỌC (VISUAL-PROXY LEXICON) ===\n"
        f"{lexicon.get('lexicon_prompt', '')}\n\n"
        "=== DANH SÁCH CHUNK CẦN HIỆU ĐÍNH THUẬT NGỮ ===\n"
        f"{json.dumps(payload_items, ensure_ascii=False, indent=2)}\n\n"
        "Hãy trả về JSON object ánh xạ đúng từng `chunk_id` sang văn bản đã sửa lỗi ASR."
    )
    return system_prompt, user_prompt


GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_DEFAULT_MODEL = "gemini-3.5-flash-lite"
_KEY_ROTATION_COUNTER = itertools.count()


def _read_env_key(key_name: str) -> Optional[str]:
    val = os.getenv(key_name) or getattr(settings, key_name, None)
    if val:
        return str(val).strip()
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        try:
            from dotenv import dotenv_values
            d_vals = dotenv_values(env_path)
            if d_vals.get(key_name):
                return str(d_vals[key_name]).strip()
        except Exception:
            pass
        try:
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == key_name:
                    clean_v = v.strip().strip("\"'")
                    if clean_v:
                        return clean_v
        except Exception:
            pass
    return None


def _parse_key_pool(*raw_sources: Optional[str]) -> List[str]:
    """Tách danh sách khóa API (phân tách bởi dấu phẩy hoặc khoảng trắng), khử trùng lặp và giữ nguyên thứ tự."""
    pool: List[str] = []
    seen = set()
    for src in raw_sources:
        if not src:
            continue
        for part in str(src).replace(";", ",").split(","):
            for token in part.strip().strip("\"'").split():
                clean_k = token.strip().strip("\"'")
                if clean_k and clean_k not in seen:
                    seen.add(clean_k)
                    pool.append(clean_k)
    return pool


def _get_llm_client_kwargs(
    *,
    use_gemini: bool = False,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    if use_gemini:
        resolved_base_url = base_url or GEMINI_OPENAI_BASE_URL
        resolved_model = model or GEMINI_DEFAULT_MODEL
        if api_key:
            resolved_keys = _parse_key_pool(api_key)
        else:
            resolved_keys = _parse_key_pool(
                _read_env_key("GEMINI_API_KEYS"),
                _read_env_key("GEMINI_API_KEY"),
                _read_env_key("GOOGLE_API_KEY"),
            )
        if not resolved_keys:
            raise ValueError(
                "Thiếu GEMINI_API_KEYS / GEMINI_API_KEY cho cờ --gemini (truyền qua --llm-api-key hoặc cấu hình trong .env)."
            )
        resolved_api_key = resolved_keys[0]
    else:
        resolved_base_url = base_url or getattr(settings, "LLM_BASE_URL", "http://127.0.0.1:11434/v1")
        resolved_model = model or getattr(settings, "LLM_MODEL_NAME", "qwen2.5")
        if api_key:
            resolved_keys = _parse_key_pool(api_key)
            resolved_api_key = resolved_keys[0] if resolved_keys else api_key
        else:
            resolved_api_key = (
                getattr(settings, "LLM_API_KEY", None)
                or getattr(settings, "OPENAI_API_KEY", None)
                or _read_env_key("LLM_API_KEY")
                or _read_env_key("OPENAI_API_KEY")
                or "ollama"
            )
            resolved_keys = [resolved_api_key]
    return {
        "base_url": resolved_base_url,
        "api_key": resolved_api_key,
        "api_keys": resolved_keys,
        "model": resolved_model,
        "timeout": float(timeout),
    }


def _is_retryable_llm_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code in (429, 500, 502, 503, 504):
        return True
    cls_name = exc.__class__.__name__.lower()
    if any(k in cls_name for k in ("ratelimit", "timeout", "connection", "internalserver")):
        return True
    msg = str(exc).lower()
    return any(k in msg for k in ("429", "rate limit", "resource_exhausted", "quota", "timed out", "timeout"))


def default_openai_llm_fn(
    system_prompt: str,
    user_prompt: str,
    *,
    timeout: float = 60.0,
    llm_cfg: Optional[Dict[str, Any]] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Sync OpenAI-compatible LLM caller hỗ trợ xoay vòng đa khóa (Multi-Key Round-Robin & Retry)."""
    from openai import OpenAI

    cfg = dict(llm_cfg) if llm_cfg else _get_llm_client_kwargs(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
    )
    eff_timeout = float(cfg.get("timeout", timeout))
    keys: List[str] = list(cfg.get("api_keys") or ([cfg["api_key"]] if cfg.get("api_key") else ["ollama"]))
    start_idx = next(_KEY_ROTATION_COUNTER) % len(keys)
    max_attempts = max(3, len(keys) * 2)

    last_err: Optional[Exception] = None
    for attempt in range(max_attempts):
        active_key = keys[(start_idx + attempt) % len(keys)]
        try:
            client = OpenAI(base_url=cfg["base_url"], api_key=active_key, timeout=eff_timeout, max_retries=0)
            resp = client.chat.completions.create(
                model=cfg["model"],
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            last_err = exc
            if attempt + 1 < max_attempts and _is_retryable_llm_error(exc):
                time.sleep(min(6.0, 0.75 * (attempt + 1)))
                continue
            raise
    if last_err is not None:
        raise last_err
    return ""


async def async_openai_llm_fn(
    system_prompt: str,
    user_prompt: str,
    *,
    timeout: float = 60.0,
    llm_cfg: Optional[Dict[str, Any]] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Async OpenAI-compatible LLM caller hỗ trợ xoay vòng đa khóa (Multi-Key Round-Robin & Retry)."""
    from openai import AsyncOpenAI

    cfg = dict(llm_cfg) if llm_cfg else _get_llm_client_kwargs(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
    )
    eff_timeout = float(cfg.get("timeout", timeout))
    keys: List[str] = list(cfg.get("api_keys") or ([cfg["api_key"]] if cfg.get("api_key") else ["ollama"]))
    start_idx = next(_KEY_ROTATION_COUNTER) % len(keys)
    max_attempts = max(3, len(keys) * 2)

    last_err: Optional[Exception] = None
    for attempt in range(max_attempts):
        active_key = keys[(start_idx + attempt) % len(keys)]
        try:
            client = AsyncOpenAI(base_url=cfg["base_url"], api_key=active_key, timeout=eff_timeout, max_retries=0)
            resp = await client.chat.completions.create(
                model=cfg["model"],
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            last_err = exc
            if attempt + 1 < max_attempts and _is_retryable_llm_error(exc):
                await asyncio.sleep(min(6.0, 0.75 * (attempt + 1)))
                continue
            raise
    if last_err is not None:
        raise last_err
    return ""


def _strip_markdown_fences(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("```"):
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1:]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


def _parse_llm_batch_response(
    raw_response: str,
    batch: Sequence[Dict[str, Any]],
) -> Dict[str, str]:
    """Giải mã phản hồi JSON (hoặc plain text cho batch=1) thành map {chunk_id: candidate_text}."""
    cleaned = _strip_markdown_fences(raw_response)
    if not cleaned:
        return {}

    batch_ids = [str(c.get("chunk_id") or f"idx_{idx}") for idx, c in enumerate(batch)]
    parsed: Any = None
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # Thử trích JSON object/array nằm giữa text nếu model có thêm lời dẫn
        start_obj = cleaned.find("{")
        end_obj = cleaned.rfind("}")
        if start_obj != -1 and end_obj > start_obj:
            try:
                parsed = json.loads(cleaned[start_obj:end_obj + 1])
            except json.JSONDecodeError:
                parsed = None

    mapping: Dict[str, str] = {}
    if isinstance(parsed, dict):
        if "chunks" in parsed and isinstance(parsed["chunks"], list):
            parsed = parsed["chunks"]
        elif "results" in parsed and isinstance(parsed["results"], dict):
            parsed = parsed["results"]

    if isinstance(parsed, dict):
        for idx, cid in enumerate(batch_ids):
            if cid in parsed and isinstance(parsed[cid], str):
                mapping[cid] = parsed[cid]
            elif str(idx) in parsed and isinstance(parsed[str(idx)], str):
                mapping[cid] = parsed[str(idx)]
    elif isinstance(parsed, list):
        for idx, item in enumerate(parsed):
            if idx >= len(batch_ids):
                break
            if isinstance(item, dict):
                cid = str(item.get("chunk_id") or batch_ids[idx])
                txt = item.get("text") or item.get("raw_text") or ""
                if isinstance(txt, str):
                    mapping[cid] = txt
            elif isinstance(item, str):
                mapping[batch_ids[idx]] = item
    elif len(batch_ids) == 1:
        mapping[batch_ids[0]] = cleaned

    return mapping


def _invoke_sync_llm(llm_fn: Callable[..., str], system_prompt: str, user_prompt: str) -> str:
    try:
        sig = inspect.signature(llm_fn)
        positional = [
            p for p in sig.parameters.values()
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        has_varargs = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values())
        if len(positional) == 1 and not has_varargs:
            return llm_fn(user_prompt)
    except (TypeError, ValueError):
        pass
    return llm_fn(system_prompt, user_prompt)


async def _invoke_async_llm(
    llm_fn: Callable[..., Any],
    system_prompt: str,
    user_prompt: str,
) -> str:
    res = _invoke_sync_llm(llm_fn, system_prompt, user_prompt)
    if inspect.isawaitable(res):
        return await res
    return res


def _apply_batch_candidates(
    batch: Sequence[Dict[str, Any]],
    candidates_map: Dict[str, str],
    stats: Dict[str, Any],
) -> List[Dict[str, Any]]:
    updated_batch: List[Dict[str, Any]] = []
    for idx, orig_chunk in enumerate(batch):
        chunk = dict(orig_chunk)
        cid = str(chunk.get("chunk_id") or f"idx_{idx}")
        orig_text = str(chunk.get("raw_text") or chunk.get("text") or "")
        cand_text = candidates_map.get(cid)

        if cand_text is None:
            stats["unchanged"] += 1
            updated_batch.append(chunk)
            continue

        cand_norm = unicodedata.normalize("NFC", cand_text).strip()
        orig_norm = unicodedata.normalize("NFC", orig_text).strip()
        if cand_norm == orig_norm:
            stats["unchanged"] += 1
            updated_batch.append(chunk)
            continue

        is_valid, reason = validate_canonical_chunk(orig_text, cand_text)
        if is_valid:
            chunk["raw_text"] = cand_norm
            if "text" in chunk:
                chunk["text"] = cand_norm
            stats["updated"] += 1
            stats["changes"].append(
                {
                    "chunk_id": cid,
                    "start_sec": chunk.get("start_sec"),
                    "before": orig_text,
                    "after": cand_norm,
                }
            )
        else:
            stats["rejected"] += 1
            stats["rejection_reasons"].append({"chunk_id": cid, "reason": reason})
        updated_batch.append(chunk)
    return updated_batch


def canonicalize_lesson_chunks(
    chunks: Sequence[Dict[str, Any]],
    lexicon: Dict[str, Any],
    *,
    llm_fn: Optional[Callable[..., str]] = None,
    batch_size: int = 5,
    limit: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Hiệu đính danh sách chunk transcript theo batch (sync) với Integrity Guardrail.
    Tất cả metadata (`start_sec`, `end_sec`, `chunk_id`, `start_label`, `end_label`) được bảo toàn tuyệt đối.
    """
    caller = llm_fn or default_openai_llm_fn
    safe_batch_size = max(1, int(batch_size))
    total = len(chunks)
    active_count = total if limit is None else min(total, max(0, int(limit)))

    stats: Dict[str, Any] = {
        "total_chunks": total,
        "processed_chunks": active_count,
        "updated": 0,
        "unchanged": 0,
        "rejected": 0,
        "errors": 0,
        "rejection_reasons": [],
        "changes": [],
    }

    result_chunks: List[Dict[str, Any]] = []
    for start in range(0, active_count, safe_batch_size):
        batch = chunks[start:min(start + safe_batch_size, active_count)]
        sys_prompt, usr_prompt = build_correction_prompt(batch, lexicon)
        try:
            raw_resp = _invoke_sync_llm(caller, sys_prompt, usr_prompt)
            cand_map = _parse_llm_batch_response(raw_resp, batch)
        except Exception as exc:
            stats["errors"] += 1
            stats["rejection_reasons"].append({"chunk_id": f"batch_{start}", "reason": f"llm_error:{exc}"})
            cand_map = {}

        result_chunks.extend(_apply_batch_candidates(batch, cand_map, stats))

    if active_count < total:
        for tail_chunk in chunks[active_count:]:
            result_chunks.append(dict(tail_chunk))

    return result_chunks, stats


async def canonicalize_lesson_chunks_async(
    chunks: Sequence[Dict[str, Any]],
    lexicon: Dict[str, Any],
    *,
    llm_fn: Optional[Callable[..., Awaitable[str]]] = None,
    batch_size: int = 5,
    limit: Optional[int] = None,
    max_concurrency: int = 3,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Phiên bản async chạy song song có giới hạn concurrency cho OpenAI-compatible endpoint."""
    caller = llm_fn or async_openai_llm_fn
    safe_batch_size = max(1, int(batch_size))
    total = len(chunks)
    active_count = total if limit is None else min(total, max(0, int(limit)))
    sem = asyncio.Semaphore(max(1, int(max_concurrency)))

    batches: List[Sequence[Dict[str, Any]]] = [
        chunks[start:min(start + safe_batch_size, active_count)]
        for start in range(0, active_count, safe_batch_size)
    ]

    async def _run_one(b_idx: int, batch: Sequence[Dict[str, Any]]) -> Tuple[int, Dict[str, str], Optional[str]]:
        sys_prompt, usr_prompt = build_correction_prompt(batch, lexicon)
        async with sem:
            try:
                raw_resp = await _invoke_async_llm(caller, sys_prompt, usr_prompt)
                return b_idx, _parse_llm_batch_response(raw_resp, batch), None
            except Exception as exc:
                return b_idx, {}, str(exc)

    batch_results = await asyncio.gather(*[_run_one(i, b) for i, b in enumerate(batches)])

    stats: Dict[str, Any] = {
        "total_chunks": total,
        "processed_chunks": active_count,
        "updated": 0,
        "unchanged": 0,
        "rejected": 0,
        "errors": 0,
        "rejection_reasons": [],
        "changes": [],
    }
    result_chunks: List[Dict[str, Any]] = []
    for b_idx, cand_map, err in sorted(batch_results, key=lambda x: x[0]):
        if err:
            stats["errors"] += 1
            stats["rejection_reasons"].append({"chunk_id": f"batch_{b_idx}", "reason": f"llm_error:{err}"})
        result_chunks.extend(_apply_batch_candidates(batches[b_idx], cand_map, stats))

    if active_count < total:
        for tail_chunk in chunks[active_count:]:
            result_chunks.append(dict(tail_chunk))

    return result_chunks, stats


def find_transcript_targets(
    course_id: Optional[str] = None,
    lesson_seq: Optional[int] = None,
    transcripts_dir: Path = TRANSCRIPTS_DIR,
) -> List[Dict[str, Any]]:
    """Quét các file `*_chunks.json` trong `data/transcripts/` và gắn metadata chuẩn."""
    if not transcripts_dir.exists():
        return []

    targets: List[Dict[str, Any]] = []
    for path in sorted(transcripts_dir.rglob("*_chunks.json")):
        rel_parts = path.resolve().relative_to(transcripts_dir.resolve()).parts
        cid = rel_parts[0] if len(rel_parts) >= 2 and rel_parts[0] in ("cpp-core", "cpp-oop") else "cpp-core"
        folder_name = rel_parts[1] if len(rel_parts) >= 2 else rel_parts[0]
        match_seq = re.search(r"lesson-(\d+)", path.name, re.IGNORECASE)
        if not match_seq:
            continue
        seq = int(match_seq.group(1))
        if course_id and cid != course_id:
            continue
        if lesson_seq is not None and seq != int(lesson_seq):
            continue
        targets.append(
            {
                "course_id": cid,
                "lesson_seq": seq,
                "lesson_id": f"lesson-{seq:02d}",
                "folder_name": folder_name,
                "path": path,
            }
        )
    targets.sort(key=lambda x: (x["lesson_seq"], x["course_id"]))
    return targets


def _is_llm_endpoint_reachable(timeout: float = 1.2, base_url: Optional[str] = None) -> bool:
    """Kiểm tra nhanh kết nối TCP tới LLM_BASE_URL (hoặc base_url override) để `--dry-run` không bị treo khi offline."""
    target_url = base_url or getattr(settings, "LLM_BASE_URL", "")
    parsed = urlparse(target_url)
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def upsert_lesson_chunks_to_qdrant(
    chunks: Sequence[Dict[str, Any]],
    course_id: str,
    lesson_id: str,
    lesson_seq: int,
    folder_name: str,
) -> int:
    """Idempotent UUIDv5 Qdrant upsert với Dense E5 ('passage: ') + Sparse BM25."""
    if not chunks:
        return 0

    from fastembed import SparseTextEmbedding, TextEmbedding
    from qdrant_client import QdrantClient
    from qdrant_client.http import models

    dense_model = TextEmbedding(settings.EMBEDDING_MODEL_NAME)
    sparse_model = SparseTextEmbedding(settings.SPARSE_MODEL_NAME)
    qdrant = QdrantClient(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY,
        timeout=settings.QDRANT_TIMEOUT,
    )

    texts = [str(c.get("raw_text") or c.get("text") or "") for c in chunks]
    dense_embeddings = list(dense_model.embed([f"passage: {t}" for t in texts]))
    sparse_embeddings = list(sparse_model.embed(texts))

    points = []
    for i, c in enumerate(chunks):
        sp = sparse_embeddings[i]
        deterministic_key = f"{course_id}_{lesson_id}_chunk_{c['start_sec']}_{c['end_sec']}"
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, deterministic_key))
        points.append(
            models.PointStruct(
                id=point_id,
                vector={
                    "dense": dense_embeddings[i].tolist(),
                    "sparse": models.SparseVector(
                        indices=sp.indices.tolist(),
                        values=sp.values.tolist(),
                    ),
                },
                payload={
                    "course_id": course_id,
                    "lesson_id": lesson_id,
                    "lesson_seq": int(lesson_seq),
                    "content_type": "video_transcript",
                    "start_sec": int(c["start_sec"]),
                    "end_sec": int(c["end_sec"]),
                    "start_label": c.get("start_label", ""),
                    "end_label": c.get("end_label", ""),
                    "raw_text": texts[i],
                    "video_title": f"{folder_name}.mp4",
                },
            )
        )

    qdrant.upsert(collection_name=settings.QDRANT_COLLECTION_NAME, points=points)
    return len(points)


def refresh_video_chapters_for_lessons(updated_seqs: Sequence[int]) -> int:
    """Tái sinh `video_chapters` cho các bài học đã hiệu đính trong `lessons_manifest.json`."""
    if not updated_seqs:
        return 0
    from scripts.build_video_chapters import (
        build_chapters_for_lesson,
        load_bindings_by_lesson,
        load_transcript_map,
    )

    seq_set = {int(s) for s in updated_seqs}
    manifest = load_manifest(MANIFEST_PATH)
    transcripts = load_transcript_map()
    bindings = load_bindings_by_lesson()

    refreshed = 0
    for _, cdata in manifest.get("courses", {}).items():
        for lesson in cdata.get("lessons", []):
            seq = int(lesson.get("seq", -1))
            if seq not in seq_set:
                continue
            lesson["video_chapters"] = build_chapters_for_lesson(
                lesson,
                transcripts.get(seq, []),
                bindings.get(seq, []),
            )
            refreshed += 1

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return refreshed


def run_audit_hotwords(
    course_id: Optional[str] = None,
    lesson_seq: Optional[int] = None,
) -> int:
    """Kiểm tra & in báo cáo lexicon + hotwords cho toàn bộ 83 bài học (không gọi API ngoài)."""
    manifest = load_manifest(MANIFEST_PATH)
    lessons = iter_manifest_lessons(manifest)

    filtered = [
        (cid, l)
        for cid, l in lessons
        if (not course_id or cid == course_id)
        and (lesson_seq is None or int(l.get("seq", -1)) == int(lesson_seq))
    ]

    ast_count = 0
    manifest_only_count = 0
    hw_counts: List[int] = []
    course_counts: Dict[str, int] = {}
    sample_reports: List[Dict[str, Any]] = []

    for cid, l in filtered:
        seq = int(l.get("seq", 0))
        lex = extract_lesson_lexicon(cid, seq)
        course_counts[cid] = course_counts.get(cid, 0) + 1
        hw_len = len(lex["hotwords_list"])
        hw_counts.append(hw_len)
        if lex["has_ast"]:
            ast_count += 1
        else:
            manifest_only_count += 1
        if seq in (1, 2, 11, 53, 54, 56, 69, 83) or lesson_seq is not None:
            sample_reports.append(lex)

    print("=" * 76)
    print(" AUDIT HOTWORDS & VISUAL-PROXY LEXICON (OFFLINE - ZERO EXTERNAL CALLS)")
    print("=" * 76)
    print(f"Total lessons audited : {len(filtered)} (Courses: {course_counts})")
    print(f"With C++ AST sources  : {ast_count}")
    print(f"Manifest+Glossary only: {manifest_only_count}")
    if hw_counts:
        avg_hw = sum(hw_counts) / len(hw_counts)
        print(f"Hotwords per lesson   : min={min(hw_counts)}, avg={avg_hw:.1f}, max={max(hw_counts)}")
        empty_hw = sum(1 for c in hw_counts if c == 0)
        print(f"Hotword readiness     : {len(hw_counts) - empty_hw}/{len(hw_counts)} lessons ready (empty={empty_hw})")

    print("-" * 76)
    for lex in sample_reports:
        ast_s = lex["ast_symbols"]
        print(
            f"[{lex['course_id']}] {lex['lesson_id']} | {lex['title']}\n"
            f"  has_ast={lex['has_ast']} | classes={ast_s['classes']} | access={ast_s['access_specifiers']}\n"
            f"  methods={ast_s['methods'][:6]} | glossary={len(lex['glossary_terms'])} | hotwords({len(lex['hotwords_list'])})={lex['hotwords_list'][:12]}"
        )
    print("=" * 76)
    return 0


def run_canonicalization_cli(args: argparse.Namespace) -> int:
    targets = find_transcript_targets(course_id=args.course, lesson_seq=args.lesson)
    if not targets:
        print("[WARN] Không tìm thấy file *_chunks.json phù hợp bộ lọc.")
        return 0

    dry_run = not args.apply
    llm_cfg = _get_llm_client_kwargs(
        use_gemini=bool(getattr(args, "gemini", False)),
        base_url=getattr(args, "llm_base_url", None),
        api_key=getattr(args, "llm_api_key", None),
        model=getattr(args, "llm_model", None),
        timeout=float(getattr(args, "timeout", 60.0)),
    )
    max_concurrency = max(1, int(getattr(args, "max_concurrency", 3)))
    llm_reachable = _is_llm_endpoint_reachable(base_url=llm_cfg["base_url"]) if dry_run else True

    def _cli_sync_llm(sys_p: str, usr_p: str) -> str:
        return default_openai_llm_fn(sys_p, usr_p, timeout=llm_cfg["timeout"], llm_cfg=llm_cfg)

    async def _cli_async_llm(sys_p: str, usr_p: str) -> str:
        return await async_openai_llm_fn(sys_p, usr_p, timeout=llm_cfg["timeout"], llm_cfg=llm_cfg)

    mode_label = "DRY-RUN" if dry_run else "APPLY"
    print("=" * 76)
    print(
        f" AST CANONICALIZER [{mode_label}] | Targets: {len(targets)} lessons | "
        f"Batch size: {args.batch_size} | Model: {llm_cfg['model']}"
    )
    print("=" * 76)

    if dry_run and not llm_reachable:
        print(
            f"[DRY-RUN OFFLINE PLAN] LLM endpoint ({llm_cfg['base_url']}) is unreachable. "
            "Generating deterministic dry-run plan without external calls or mutations."
        )

    remaining_budget: Optional[int] = args.limit
    updated_seqs: List[int] = []
    total_updated = 0
    total_rejected = 0
    total_qdrant_points = 0

    for t in targets:
        if remaining_budget is not None and remaining_budget <= 0:
            break

        cid = t["course_id"]
        seq = t["lesson_seq"]
        lid = t["lesson_id"]
        path: Path = t["path"]

        chunks = json.loads(path.read_text(encoding="utf-8"))
        lexicon = extract_lesson_lexicon(cid, seq)
        lesson_limit = remaining_budget if remaining_budget is not None else None

        if dry_run and not llm_reachable:
            planned_cnt = len(chunks) if lesson_limit is None else min(len(chunks), lesson_limit)
            batches_cnt = (planned_cnt + max(1, args.batch_size) - 1) // max(1, args.batch_size)
            print(
                f"  - [{cid}] {lid} ({path.name}): total_chunks={len(chunks)}, "
                f"planned_chunks={planned_cnt}, batches={batches_cnt}, "
                f"ast={lexicon['has_ast']}, hotwords={len(lexicon['hotwords_list'])}"
            )
            if chunks and planned_cnt > 0:
                sys_p, usr_p = build_correction_prompt(chunks[:min(2, planned_cnt)], lexicon)
                print(f"    sample_prompt_chars=(sys={len(sys_p)}, usr={len(usr_p)}) | top_hotwords={lexicon['hotwords_list'][:8]}")
            if remaining_budget is not None:
                remaining_budget -= planned_cnt
            continue

        if args.async_mode:
            new_chunks, stats = asyncio.run(
                canonicalize_lesson_chunks_async(
                    chunks,
                    lexicon,
                    llm_fn=_cli_async_llm,
                    batch_size=args.batch_size,
                    limit=lesson_limit,
                    max_concurrency=max_concurrency,
                )
            )
        else:
            new_chunks, stats = canonicalize_lesson_chunks(
                chunks,
                lexicon,
                llm_fn=_cli_sync_llm,
                batch_size=args.batch_size,
                limit=lesson_limit,
            )

        if remaining_budget is not None:
            remaining_budget -= stats["processed_chunks"]

        total_updated += stats["updated"]
        total_rejected += stats["rejected"]
        print(
            f"  - [{cid}] {lid}: processed={stats['processed_chunks']}/{stats['total_chunks']}, "
            f"updated={stats['updated']}, unchanged={stats['unchanged']}, "
            f"rejected={stats['rejected']}, errors={stats['errors']}"
        )
        for chg in stats["changes"][:3]:
            print(f"    * {chg['chunk_id']} ({chg['start_sec']}s): {chg['before'][:70]} -> {chg['after'][:70]}")

        if not dry_run and stats["updated"] > 0:
            with open(path, "w", encoding="utf-8") as wf:
                json.dump(new_chunks, wf, ensure_ascii=False, indent=2)
            updated_seqs.append(seq)
            if args.sync_qdrant:
                pts = upsert_lesson_chunks_to_qdrant(
                    new_chunks,
                    course_id=cid,
                    lesson_id=lid,
                    lesson_seq=seq,
                    folder_name=t["folder_name"],
                )
                total_qdrant_points += pts

    if dry_run:
        print("[DRY-RUN] Complete. Zero files modified in data/, zero Qdrant upserts.")
    else:
        if args.refresh_chapters and updated_seqs:
            refreshed = refresh_video_chapters_for_lessons(updated_seqs)
            print(f"[APPLY] Refreshed video_chapters for {refreshed} lessons in {MANIFEST_PATH}")
        print(
            f"[APPLY] Complete. lessons_modified={len(updated_seqs)}, "
            f"chunks_updated={total_updated}, guardrail_rejected={total_rejected}, "
            f"qdrant_upserted={total_qdrant_points}"
        )
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Data-Centric Offline Transcript Canonicalizer & Visual-Proxy Hotword Generator"
    )
    parser.add_argument(
        "--audit-hotwords",
        action="store_true",
        default=False,
        help="Inspect all 83 lessons and print AST/manifest lexicon + hotword readiness (zero external calls).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview canonicalization (or deterministic dry-run plan if offline) without mutating data/ or Qdrant.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Write canonicalized *_chunks.json preserving start_sec, end_sec, chunk_id metadata.",
    )
    parser.add_argument(
        "--sync-qdrant",
        action="store_true",
        default=False,
        help="With --apply, perform idempotent UUIDv5 Qdrant upsert for modified lessons.",
    )
    parser.add_argument(
        "--refresh-chapters",
        action="store_true",
        default=False,
        help="With --apply, refresh video_chapters in lessons_manifest.json for modified lessons.",
    )
    parser.add_argument("--course", type=str, default=None, help="Filter by course_id (e.g., cpp-core, cpp-oop).")
    parser.add_argument("--lesson", type=int, default=None, help="Filter by lesson_seq (1..83).")
    parser.add_argument("--limit", type=int, default=None, help="Maximum total chunks to process.")
    parser.add_argument("--batch-size", type=int, default=5, help="Chunks per LLM batch request (default: 5).")
    parser.add_argument("--async-mode", action="store_true", default=False, help="Use AsyncOpenAI batched caller.")
    parser.add_argument(
        "--gemini",
        action="store_true",
        default=False,
        help="Use Google Gemini OpenAI-compatible API (gemini-3.5-flash-lite) with GEMINI_API_KEYS/GEMINI_API_KEY rotation without altering .env LLM_BASE_URL.",
    )
    parser.add_argument("--llm-base-url", type=str, default=None, help="Override OpenAI-compatible base_url for this offline run.")
    parser.add_argument("--llm-api-key", type=str, default=None, help="Override API key for this offline run (never logged).")
    parser.add_argument("--llm-model", type=str, default=None, help="Override model name for this offline run.")
    parser.add_argument("--max-concurrency", type=int, default=3, help="Max concurrent async batch requests (default: 3).")
    parser.add_argument("--timeout", type=float, default=60.0, help="Per-batch LLM request timeout in seconds (default: 60.0).")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.audit_hotwords:
        return run_audit_hotwords(course_id=args.course, lesson_seq=args.lesson)

    # Safe by default: nếu không truyền --apply thì luôn chạy dry-run
    if not args.apply and not args.dry_run:
        args.dry_run = True

    return run_canonicalization_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
