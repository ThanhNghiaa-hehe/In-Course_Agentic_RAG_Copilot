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
import threading
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


def load_asr_phonetic_glossary(glossary_path: Path = GLOSSARY_PATH) -> Dict[str, List[Dict[str, Any]]]:
    """Đọc bảng quy chuẩn lỗi đồng âm Whisper tách riêng khỏi runtime prompt."""
    if not glossary_path.exists():
        return {}
    with open(glossary_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    raw = data.get("asr_phonetic_glossary", {})
    return raw if isinstance(raw, dict) else {}


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
    has_arr_kw = bool(
        ast_symbols.get("structs")
        or any(k in haystack for k in ("mảng", "array", "xâu", "chuỗi", "string", "struct", "bản ghi", "vector", "ký tự"))
    )

    category_triggers = {
        "object_oriented_programming": has_class_ast or course_id == "cpp-oop",
        "sorting_algorithms": has_sort_kw,
        "searching_algorithms": has_search_kw,
        "memory_and_pointers": has_ptr_kw,
        "arrays_and_strings": has_arr_kw,
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
            # Với OOP hoặc sorting/searching/pointer/arrays, lấy mục khớp trực tiếp hoặc toàn bộ nhóm khi trigger bật
            if (
                token_hit
                or (cat == "object_oriented_programming" and has_class_ast)
                or (cat == "arrays_and_strings" and has_arr_kw)
                or (cat_triggered and any(w in haystack for w in en.lower().split() if len(w) >= 4))
            ):
                seen_en.add(en.lower())
                matched.append(entry)
    return matched


def _match_asr_phonetic_entries(
    course_id: str,
    title: str,
    keywords: List[str],
    ast_symbols: Dict[str, List[str]],
    phonetic_glossary: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Chọn các mục đồng âm Whisper phù hợp với khóa học và bài học."""
    haystack_parts = [course_id, title] + keywords
    for vals in ast_symbols.values():
        haystack_parts.extend(vals)
    haystack = unicodedata.normalize("NFC", " ".join(haystack_parts)).lower()

    is_oop_or_stl = course_id == "cpp-oop" or any(
        k in haystack for k in ("oop", "class", "struct", "stl", "set", "map", "vector", "iterator", "operator", "euler", "phi")
    )
    is_ptr_or_arr = any(
        k in haystack for k in ("con trỏ", "pointer", "mảng", "array", "xâu", "chuỗi", "string", "struct", "cấp phát", "ma trận")
    )
    is_sort_or_algo = course_id == "cpp-core" or any(
        k in haystack for k in ("sắp xếp", "sort", "trộn", "chọn", "merge", "quick", "bubble", "selection", "insertion", "tìm kiếm", "thuật toán")
    )

    selected_cats = ["general_cpp", "operators_and_control"]
    if is_ptr_or_arr or course_id == "cpp-core":
        selected_cats.append("pointers_and_arrays")
    if is_sort_or_algo:
        selected_cats.append("sorting_and_algorithms")
    if is_oop_or_stl:
        selected_cats.append("oop_and_stl")

    entries: List[Dict[str, Any]] = []
    for cat in selected_cats:
        for item in phonetic_glossary.get(cat, []):
            if isinstance(item, dict) and item.get("asr_noise"):
                entries.append(item)
    return entries


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
    phonetic_glossary = load_asr_phonetic_glossary(glossary_path)
    phonetic_matches = _match_asr_phonetic_entries(resolved_cid, title, keywords, merged_ast, phonetic_glossary)

    forbidden_noise_map: List[Tuple[str, str]] = []
    seen_noise = set()
    for g in glossary_matches:
        target = f"{g.get('vi', '')} ({g.get('en', '')})".strip()
        for bad in g.get("forbidden_translations", []) or []:
            b_clean = unicodedata.normalize("NFC", str(bad)).strip().lower()
            if b_clean and b_clean not in seen_noise:
                seen_noise.add(b_clean)
                forbidden_noise_map.append((b_clean, target))
    for p in phonetic_matches:
        target = str(p.get("canonical", "")).strip()
        for bad in p.get("asr_noise", []) or []:
            b_clean = unicodedata.normalize("NFC", str(bad)).strip().lower()
            if b_clean and b_clean not in seen_noise:
                seen_noise.add(b_clean)
                forbidden_noise_map.append((b_clean, target))

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
    if phonetic_matches:
        phonetic_lines = [
            f"- Nhầm ASR [{', '.join(p['asr_noise'][:14])}] -> chuẩn ngữ cảnh: {p['canonical']}"
            for p in phonetic_matches
        ]
        prompt_sections.append("Lỗi đồng âm Whisper cần cảnh giác (CHỈ sửa khi khớp ngữ cảnh bài):\n" + "\n".join(phonetic_lines))
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
        "asr_phonetic_entries": phonetic_matches,
        "forbidden_noise_map": forbidden_noise_map,
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


VIETNAMESE_NFC_LETTERS: Set[str] = set(
    "àáảãạăằắẳẵặâầấẩẫậđèéẻẽẹêềếểễệìíỉĩị"
    "òóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ"
    "ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬĐÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊ"
    "ÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ"
)
assert len(VIETNAMESE_NFC_LETTERS) == 134, f"Expected 134 Vietnamese NFC letters, got {len(VIETNAMESE_NFC_LETTERS)}"

ASR_EMPTY_FALLBACK_TEXT = "[Đoạn thao tác mã nguồn C++ trên màn hình]"

_SAFE_NON_ASCII_PUNCT: Set[str] = {"–", "—", "•", "…", "“", "”", "‘", "’"}

_FOREIGN_LATIN_FOLD_MAP: Dict[str, str] = {
    "ı": "i",
    "İ": "I",
    "ł": "l",
    "Ł": "L",
    "ø": "o",
    "Ø": "O",
    "ß": "ss",
    "æ": "ae",
    "Æ": "AE",
    "œ": "oe",
    "Œ": "OE",
    "ð": "d",
    "Ð": "D",
    "þ": "th",
    "Þ": "Th",
}

_SUBSCRIPT_SUPERSCRIPT_MAP: Dict[str, str] = {
    "₀": "0",
    "₁": "1",
    "₂": "2",
    "₃": "3",
    "₄": "4",
    "₅": "5",
    "₆": "6",
    "₇": "7",
    "₈": "8",
    "₉": "9",
    "⁰": "0",
    "¹": "1",
    "²": "2",
    "³": "3",
    "⁴": "4",
    "⁵": "5",
    "⁶": "6",
    "⁷": "7",
    "⁸": "8",
    "⁹": "9",
}

_ALLOWED_UNACCENTED_VN_OR_CPP: Set[str] = {
    "cho", "ta", "la", "va", "co", "khi", "trong", "nhu", "hay", "con", "thi", "roi",
    "nam", "em", "anh", "cac", "ban", "bai", "ham", "mang", "so", "ok",
    "int", "long", "short", "float", "double", "char", "bool", "void", "auto", "const",
    "static", "struct", "class", "public", "private", "protected", "virtual", "friend",
    "inline", "template", "typename", "using", "namespace", "std", "return", "if", "else",
    "switch", "case", "default", "for", "while", "do", "break", "continue", "new", "delete",
    "nullptr", "null", "true", "false", "sizeof", "typedef", "cin", "cout", "endl",
    "getline", "iostream", "iomanip", "cmath", "cstring", "algorithm", "string", "vector",
    "set", "multiset", "map", "multimap", "unordered_set", "unordered_map", "pair", "stack",
    "queue", "priority_queue", "deque", "list", "sort", "swap", "min", "max", "abs", "sqrt",
    "pow", "gcd", "lcm", "main", "include", "bits", "stdc", "cpp", "ctrl",
    "line", "node", "input", "output", "index", "size", "length", "push", "pop", "back",
    "front", "begin", "end", "insert", "erase", "find", "count", "first", "second",
    "binary", "search", "merge", "quick", "bubble", "selection", "insertion", "matrix",
    "tree", "graph", "heap", "object", "constructor", "destructor", "iterator", "function",
    "method", "variable", "loop", "code", "run", "test", "debug", "compile", "error",
    "file", "data", "type", "value", "key", "sum", "ans", "res", "tmp", "temp", "cnt",
    "len", "pos", "idx", "cur", "prev", "next", "head", "tail", "left", "right", "mid",
    "low", "high", "row", "col", "root", "leaf", "edge", "path", "dist", "cost", "dp",
    "bfs", "dfs", "bit", "byte", "ram", "cpu", "ide", "oop", "stl", "dsa", "gpa", "id",
    "name", "age", "score", "student", "stream", "ignore", "printf", "scanf", "plus",
    "minus", "mod", "div", "and", "or", "not", "xor", "step", "part", "check", "print",
    "read", "write", "open", "close", "copy", "move", "add", "sub", "mul", "init",
    "clear", "empty", "top", "val", "num", "str", "arr", "vec", "mat", "ptr", "ref",
    "obj", "cls", "func", "arg", "param", "ret", "var", "def", "inc", "dec", "lim",
    "cap", "mem", "buf", "start", "stop", "done", "pass", "fail", "base", "child",
    "parent", "super", "this", "self", "get", "set", "has", "is", "to", "in", "out",
    "up", "down", "avg", "prod", "diff", "rem", "quo", "exp", "log", "sin", "cos",
    "tan", "ceil", "floor", "round", "reverse", "unique", "lower", "upper", "bound",
    "split", "join", "trim", "strip", "push_back", "pop_back", "emplace_back",
    "make_pair", "size_t", "uint", "override", "extern", "enum", "union", "define",
    "fstream", "sstream", "cstdlib", "cstdio", "ctime", "climits", "cctype", "numeric",
    "functional", "utility", "memory", "tuple", "bitset", "regex", "chrono", "hpp",
    "exe", "txt", "csv", "json", "xml", "html", "css", "sql", "http", "api", "url",
    "gcc", "gpp", "clang", "mingw", "dev", "vscode", "codeblocks", "github", "git",
    "linux", "windows", "mac", "os", "ascii", "utf", "eof", "nan", "inf", "tle", "mle",
    "rte", "wa", "ac", "ce", "pe", "oj", "io", "stdin", "stdout", "stderr", "alt",
    "shift", "tab", "enter", "esc", "del", "ins", "home", "space", "click", "scroll",
    "save", "build", "clean", "edit", "view", "help", "menu", "window", "screen",
    "folder", "dir", "abc", "xyz", "foo", "bar", "baz", "yes", "no", "hi", "hello",
    "bye", "note", "tip", "demo", "example", "sample", "quiz", "lab", "doc", "docs",
    "spec", "plan", "task", "job", "log", "info", "warn", "err", "trace",
}

_CORRUPTED_ASR_CHAR_RE = re.compile(
    r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3000-\u30ff"
    r"\uac00-\ud7af\u1100-\u11ff\u3130-\u318f\u0400-\u04ff"
    r"\u0370-\u03ff\u1f00-\u1fff\u0590-\u05ff\u0600-\u06ff"
    r"\u0900-\u0dff\u0e00-\u0e7f\uff00-\uffef\ufffd"
    r"\u202a-\u202e\u2066-\u2069\u2080-\u20cf\u2190-\u22ff"
    r"\u25a0-\u27bf\ufe00-\ufe0f\u00bc-\u00be\u00d7"
    r"\U0001f000-\U0001faff]"
)
_REPEATED_CHAR_NOISE_RE = re.compile(r"([A-Za-z])\1{5,}")
_SPACED_SINGLE_LETTER_LOOP_RE = re.compile(r"(?i)(?<!\w)([a-z])(?:\s*[,;.]?\s*\1){3,}(?!\w)")
_REPEATED_WORD_LOOP_RE = re.compile(r"(?i)(?<![\w+])([^\W\d_]{2,})(?:(?:\s*[,;]\s*|\s+)\1){2,}(?![\w+])")
_REPEATED_PHRASE_LOOP_RE = re.compile(r"(?i)(?<!\w)([a-z0-9_]+\s+[a-z0-9_]+)(?:\s*[,;]\s*\1){2,}(?!\w)")
_YOUTUBE_HALLUCINATION_RE = re.compile(
    r"(?i)[^.!?\n]*\b(?:if you have any question|leave feedback in comments|thanks for watching|"
    r"thank you for watching|please subscribe|like and subscribe|don't forget to subscribe|"
    r"remember our sources|in this video,?\s+i would like to|i would like to show you|"
    r"many of you have requested this part|you should check this part|i will do it quickly|"
    r"welcome to my channel)[^.!?\n]*[.!?]?"
)


def _contains_cjk_or_hangul(text: str) -> bool:
    """Kiểm tra ký tự ảo giác CJK, Kana, Hangul hoặc replacement character."""
    for ch in text:
        code = ord(ch)
        if (
            (0x4E00 <= code <= 0x9FFF)       # CJK Unified Ideographs
            or (0x3400 <= code <= 0x4DBF)    # CJK Extension A
            or (0x20000 <= code <= 0x2A6DF)  # CJK Extension B
            or (0xF900 <= code <= 0xFAFF)    # CJK Compatibility Ideographs
            or (0x3000 <= code <= 0x30FF)    # CJK Punctuation, Hiragana & Katakana
            or (0xAC00 <= code <= 0xD7AF)    # Hangul Syllables
            or (0x1100 <= code <= 0x11FF)    # Hangul Jamo
            or (0x3130 <= code <= 0x318F)    # Hangul Compatibility Jamo
            or code == 0xFFFD                # Unicode replacement char
        ):
            return True
    return False


def _has_foreign_or_corrupted_codepoint(text: str) -> bool:
    """Kiểm tra ký tự ngoài ASCII + 134 chữ cái tiếng Việt NFC + dấu câu chuẩn."""
    norm = unicodedata.normalize("NFC", text)
    for ch in norm:
        if ord(ch) > 127 and ch not in VIETNAMESE_NFC_LETTERS and ch not in _SAFE_NON_ASCII_PUNCT:
            return True
    return False


def _is_pure_ascii_whisper_hallucination(text: str) -> bool:
    """Phát hiện chuỗi ảo giác tiếng Anh / ASCII vô nghĩa của Whisper khi video im lặng gõ code."""
    norm = unicodedata.normalize("NFC", text or "").strip()
    if not norm or ASR_EMPTY_FALLBACK_TEXT in norm:
        return False
    # Không đánh dấu nhầm mã nguồn C++ thật (chứa block {}, chỉ thị #include, header [Mã nguồn ...] hoặc kết thúc ';')
    if any(tok in norm for tok in ("{", "}", "#include", "[Mã nguồn")) or norm.endswith(";"):
        return False
    vn_count = sum(1 for ch in norm if ch in VIETNAMESE_NFC_LETTERS)
    if vn_count >= 3:
        return False
    if norm.count("->") >= 4 and vn_count < 3:
        return True
    if vn_count > 0:
        return False

    alpha_words = re.findall(r"[A-Za-z]{2,}", norm)
    if len(alpha_words) < 2:
        return False
    foreign_en_words = [w for w in alpha_words if w.lower() not in _ALLOWED_UNACCENTED_VN_OR_CPP]
    ratio = len(foreign_en_words) / len(alpha_words)
    if len(alpha_words) >= 3 and len(foreign_en_words) >= 2 and ratio >= 0.45:
        return True
    if len(alpha_words) >= 2 and len(norm) < 35 and len(foreign_en_words) >= 1 and ratio >= 0.50:
        return True
    return False


def _is_non_latin_foreign_script_codepoint(code: int) -> bool:
    return (
        (0x0370 <= code <= 0x05FF)      # Greek, Cyrillic, Armenian, Hebrew
        or (0x0600 <= code <= 0x0DFF)   # Arabic, Syriac, Indic, Devanagari, Gujarati, Tamil
        or (0x0E00 <= code <= 0x137F)   # Thai, Lao, Tibetan, Myanmar, Georgian, Hangul Jamo, Ethiopic
        or (0x1F00 <= code <= 0x1FFF)   # Greek Extended
        or (0x202A <= code <= 0x202E)   # Bidi controls
        or (0x2066 <= code <= 0x2069)   # Bidi isolates
        or (0x20A0 <= code <= 0x20CF)   # Currency symbols
        or (0x2190 <= code <= 0x22FF)   # Arrows & Mathematical operators
        or (0x25A0 <= code <= 0x27BF)   # Geometric shapes, Misc symbols, Dingbats
        or (0x3000 <= code <= 0x30FF)   # CJK Punctuation, Hiragana, Katakana
        or (0x3130 <= code <= 0x318F)   # Hangul Compatibility Jamo
        or (0x3400 <= code <= 0x4DBF)   # CJK Extension A
        or (0x4E00 <= code <= 0x9FFF)   # CJK Unified Ideographs
        or (0xAC00 <= code <= 0xD7AF)   # Hangul Syllables
        or (0xF900 <= code <= 0xFAFF)   # CJK Compatibility Ideographs
        or (0xFE00 <= code <= 0xFE0F)   # Variation Selectors
        or (0xFF00 <= code <= 0xFFEF)   # Halfwidth & Fullwidth Forms
        or code == 0xFFFD               # Replacement character
        or (0x1F000 <= code <= 0x1FAFF) # Emoji & Pictographs
        or (0x20000 <= code <= 0x2FA1F) # CJK Extensions B..F
    )


def _is_mixed_multilingual_whisper_gibberish(text: str) -> bool:
    """Phát hiện đoạn ảo giác tiếng Anh/đa ngữ Whisper trộn lẫn 1–2 chữ tiếng Việt rời rạc."""
    norm = unicodedata.normalize("NFC", text or "").strip()
    if not norm or ASR_EMPTY_FALLBACK_TEXT in norm:
        return False
    if any(tok in norm for tok in ("{", "}", "#include", "[Mã nguồn")) or norm.endswith(";"):
        return False
    words = re.findall(r"[A-Za-zÀ-ỹ0-9_]+", norm)
    if len(words) < 10:
        return False
    non_cpp_en = [
        w for w in words
        if w.isascii() and w.isalpha() and len(w) >= 3 and w.lower() not in _ALLOWED_UNACCENTED_VN_OR_CPP
    ]
    vn_words = [w for w in words if any(ch in VIETNAMESE_NFC_LETTERS for ch in w)]
    return (
        len(non_cpp_en) >= 5
        and (len(non_cpp_en) / len(words)) >= 0.30
        and (len(vn_words) / len(words)) < 0.25
    )


def _contains_corrupted_asr_artifacts(text: str) -> bool:
    """Phát hiện ký tự ngoại lai, dấu Latin ngoại lai, Emoji, lặp rác hoặc ảo giác tiếng Anh/đa ngữ Whisper."""
    if not text:
        return False
    return (
        _contains_cjk_or_hangul(text)
        or bool(_CORRUPTED_ASR_CHAR_RE.search(text))
        or _has_foreign_or_corrupted_codepoint(text)
        or bool(_REPEATED_CHAR_NOISE_RE.search(text))
        or bool(_SPACED_SINGLE_LETTER_LOOP_RE.search(text))
        or bool(_REPEATED_WORD_LOOP_RE.search(text))
        or bool(_REPEATED_PHRASE_LOOP_RE.search(text))
        or bool(_YOUTUBE_HALLUCINATION_RE.search(text))
        or _is_pure_ascii_whisper_hallucination(text)
        or _is_mixed_multilingual_whisper_gibberish(text)
    )


def _sanitize_corrupted_asr_artifacts(text: str) -> str:
    """Loại bỏ tất định ký tự ngoại lai, dấu Latin lạ, Emoji, lặp rác và ảo giác tiếng Anh/đa ngữ ASR (bảo toàn 134 chữ NFC tiếng Việt)."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFC", text)
    norm = _YOUTUBE_HALLUCINATION_RE.sub(" ", norm)
    if _is_pure_ascii_whisper_hallucination(norm) or _is_mixed_multilingual_whisper_gibberish(norm):
        return ""

    cleaned_chars: List[str] = []
    for ch in norm:
        code = ord(ch)
        if code <= 127 or ch in VIETNAMESE_NFC_LETTERS or ch in _SAFE_NON_ASCII_PUNCT:
            cleaned_chars.append(ch)
        elif ch == "→":
            cleaned_chars.append("->")
        elif ch == "×":
            cleaned_chars.append("*")
        elif ch in _SUBSCRIPT_SUPERSCRIPT_MAP:
            cleaned_chars.append(_SUBSCRIPT_SUPERSCRIPT_MAP[ch])
        elif ch in _FOREIGN_LATIN_FOLD_MAP:
            cleaned_chars.append(_FOREIGN_LATIN_FOLD_MAP[ch])
        elif _is_non_latin_foreign_script_codepoint(code):
            cleaned_chars.append(" ")
        elif unicodedata.category(ch).startswith("L"):
            decomposed = unicodedata.normalize("NFD", ch)
            ascii_base = "".join(
                c for c in decomposed
                if not unicodedata.category(c).startswith("M") and ord(c) <= 127 and c.isalpha()
            )
            cleaned_chars.append(ascii_base if ascii_base else " ")
        else:
            cleaned_chars.append(" ")

    stripped = "".join(cleaned_chars)
    stripped = _REPEATED_CHAR_NOISE_RE.sub(" ", stripped)
    stripped = _SPACED_SINGLE_LETTER_LOOP_RE.sub(" ", stripped)
    for _ in range(3):
        next_s = _REPEATED_WORD_LOOP_RE.sub(r"\1", stripped)
        next_s = _REPEATED_PHRASE_LOOP_RE.sub(r"\1", next_s)
        if next_s == stripped:
            break
        stripped = next_s

    collapsed = " ".join(stripped.split())
    while ",," in collapsed:
        collapsed = collapsed.replace(",,", ",")
    collapsed = collapsed.strip(" ,;:")
    if _is_pure_ascii_whisper_hallucination(collapsed) or _is_mixed_multilingual_whisper_gibberish(collapsed):
        return ""
    return collapsed


def _non_punct_tokens(text: str) -> List[str]:
    """Tách token bỏ dấu câu (giữ chữ tiếng Việt có dấu, chữ số, '+', '_')."""
    norm = unicodedata.normalize("NFC", text).lower()
    cleaned_chars = [
        " " if (unicodedata.category(ch).startswith("P") and ch != "_") else ch
        for ch in norm
    ]
    return [tok for tok in "".join(cleaned_chars).split() if tok]


def validate_canonical_chunk(
    original_text: str,
    candidate_text: str,
    *,
    targeted: bool = False,
) -> Tuple[bool, str]:
    """
    Strict Integrity Guardrail cho chunk sau hiệu đính LLM:
    - Không rỗng, không rò rỉ JSON wrapper, không tự chèn LaTeX $...$
    - Không ảo giác CJK / Hangul / replacement char
    - Pass 1 (`targeted=False`): len [0.82, 1.18], wc [0.80, 1.20], Jaccard >= 0.55
    - Pass 2 (`targeted=True`): len [0.74, 1.18], wc [0.70, 1.20], Jaccard >= 0.55
    - Kiểm tra cục bộ 2 nửa chunk (>= 18 tokens): min(h1_jaccard, h2_jaccard) >= 0.35 chống bịa đoạn đầu/cuối.
    """
    orig = unicodedata.normalize("NFC", (original_text or "")).strip()
    cand = unicodedata.normalize("NFC", (candidate_text or "")).strip()

    if not cand:
        return False, "empty_output"
    if not orig:
        return False, "empty_original"
    if _contains_cjk_or_hangul(cand) or _contains_corrupted_asr_artifacts(cand):
        return False, "cjk_or_hangul_hallucination"
    if (cand.lstrip().startswith(("{", "[")) and not orig.lstrip().startswith(("{", "["))) or (
        '"chunk_id"' in cand and '"chunk_id"' not in orig
    ):
        return False, "json_wrapper_leakage"
    if "$" in cand and "$" not in orig:
        return False, "latex_syntax_injection"

    # Khi bản gốc chứa rác CJK/Hangul/FFFD/lặp ký tự, đối chiếu tỷ lệ trên bản đã bóc rác để tránh từ chối nhầm khi xóa rác
    orig_had_asr_garbage = _contains_corrupted_asr_artifacts(orig)
    orig_basis = _sanitize_corrupted_asr_artifacts(orig) if orig_had_asr_garbage else orig
    if not orig_basis:
        orig_basis = orig

    min_len = 0.74 if (targeted or orig_had_asr_garbage) else 0.82
    max_len = 1.18
    min_wc = 0.70 if (targeted or orig_had_asr_garbage) else 0.80
    max_wc = 1.20
    min_jaccard = 0.55

    len_ratio = len(cand) / max(len(orig_basis), 1)
    if len_ratio < min_len or len_ratio > max_len:
        return False, f"length_ratio_out_of_bounds:{len_ratio:.3f}"

    orig_words = orig_basis.split()
    cand_words = cand.split()
    wc_ratio = len(cand_words) / max(len(orig_words), 1)
    if wc_ratio < min_wc or wc_ratio > max_wc:
        return False, f"word_count_ratio_out_of_bounds:{wc_ratio:.3f}"

    orig_tokens = _non_punct_tokens(orig_basis)
    cand_tokens = _non_punct_tokens(cand)
    if not orig_tokens or not cand_tokens:
        return False, "no_non_punct_tokens"

    orig_set = set(orig_tokens)
    cand_set = set(cand_tokens)
    union_set = orig_set | cand_set
    jaccard = len(orig_set & cand_set) / len(union_set) if union_set else 0.0
    if jaccard < min_jaccard:
        return False, f"low_context_retention:{jaccard:.3f}"

    # Anti-localized hallucination check: chia chunk dài thành 2 hoặc 3 phân đoạn đều nhau, cấm bịa trọn đoạn đầu/giữa/cuối
    if len(orig_tokens) >= 18 and len(cand_tokens) >= 10:
        n_segs = 3 if len(orig_tokens) >= 27 and len(cand_tokens) >= 18 else 2
        min_seg_req = 0.30 if targeted else 0.35
        seg_scores: List[float] = []
        o_len = len(orig_tokens)
        c_len = len(cand_tokens)
        for s_idx in range(n_segs):
            o_a = (s_idx * o_len) // n_segs
            o_b = ((s_idx + 1) * o_len) // n_segs
            c_a = max(0, ((s_idx * c_len) // n_segs) - 2)
            c_b = min(c_len, (((s_idx + 1) * c_len) // n_segs) + 2)
            o_seg = set(orig_tokens[o_a:o_b])
            c_seg = set(cand_tokens[c_a:c_b])
            if o_seg and c_seg:
                seg_scores.append(len(o_seg & c_seg) / len(o_seg | c_seg))
        if seg_scores and min(seg_scores) < min_seg_req:
            return False, f"localized_hallucination_or_rewrite:min_seg={min(seg_scores):.2f}"

    return True, "ok"


def build_correction_prompt(
    chunks_batch: Sequence[Dict[str, Any]],
    lexicon: Dict[str, Any],
    *,
    targeted_hints: Optional[Dict[str, str]] = None,
    neighbor_contexts: Optional[Dict[str, Dict[str, str]]] = None,
) -> Tuple[str, str]:
    """Tạo (system_prompt, user_prompt) ép LLM chỉ sửa lỗi nghe nhầm thuật ngữ ASR."""
    system_prompt = (
        "Bạn là bộ hiệu đính thuật ngữ kỹ thuật C++ và thuật ngữ học thuật cho bản phiên âm (ASR transcript) bài giảng tiếng Việt.\n"
        "QUY TẮC BẮT BUỘC (VI PHẠM SẼ BỊ HỦY):\n"
        "1. CHỈ sửa các lỗi nghe nhầm âm thanh (phonetic/ASR typos) của từ khóa C++, tên lớp/hàm/phương thức, hoặc từ tiếng Việt học thuật bị nhận dạng đồng âm sai "
        "(ví dụ: 'Assets Modifier' -> 'Access Modifier', 'si cộng cộng' -> 'C++', 'xì in' -> 'cin', 'xì out' -> 'cout', 'mạng một chiều' -> 'mảng một chiều', 'kính UV' -> 'chu vi', 'phát bại trị' -> 'giá trị', 'cộng cộng a' -> '++a'). "
        "KHÔNG tự ý đổi các từ tiếng Việt vốn ĐÃ ĐÚNG ngữ cảnh (ví dụ 'lên mạng tìm tài liệu' thì giữ nguyên 'mạng').\n"
        "2. TUYỆT ĐỐI KHÔNG tóm tắt, KHÔNG viết lại câu, KHÔNG chèn LaTeX ($...$), KHÔNG dịch lời giảng tiếng Việt sang tiếng Anh, KHÔNG bịa thêm hoặc xóa ý hay xóa tên biến/hàm.\n"
        "3. Thay thế từ lỗi đúng vị trí gốc. Giữ nguyên văn phong nói, độ dài và cấu trúc câu gốc.\n"
        "4. Nếu một đoạn âm thanh quá nhiễu hoặc chứa tên/từ rời rạc không thể đối chiếu chắc chắn từ âm thanh gốc (như 'Frozen', 'Franklin', 'intORDER'), GIỮ NGUYÊN đoạn đó; CẤM tự bịa/đoán câu lệnh C++ hay con số mới.\n"
        "5. Trả về DUY NHẤT JSON object phẳng dạng {\"<chunk_id>\": \"<văn bản đã hiệu đính>\", ...}, không kèm giải thích hay bọc thêm khóa `chunk_id` lồng nhau."
    )

    payload_items = []
    for idx, c in enumerate(chunks_batch):
        cid = str(c.get("chunk_id") or f"idx_{idx}")
        item: Dict[str, Any] = {
            "chunk_id": cid,
            "start_label": c.get("start_label", ""),
            "text": str(c.get("raw_text") or c.get("text") or ""),
        }
        if targeted_hints and cid in targeted_hints:
            item["supervisor_hint"] = targeted_hints[cid]
        if neighbor_contexts and cid in neighbor_contexts:
            nb = neighbor_contexts[cid]
            if nb.get("prev"):
                item["prev_context_readonly"] = nb["prev"][:160]
            if nb.get("next"):
                item["next_context_readonly"] = nb["next"][:160]
        payload_items.append(item)

    user_prompt = (
        "=== NGỮ CẢNH TỪ VỰNG BÀI HỌC (VISUAL-PROXY LEXICON) ===\n"
        f"{lexicon.get('lexicon_prompt', '')}\n\n"
        "=== DANH SÁCH CHUNK CẦN HIỆU ĐÍNH THUẬT NGỮ ===\n"
        f"{json.dumps(payload_items, ensure_ascii=False, indent=2)}\n\n"
        "Hãy trả về JSON object ánh xạ đúng từng `chunk_id` sang văn bản đã sửa lỗi ASR (CHỈ xuất khóa `chunk_id` và `text` đã sửa, KHÔNG copy prev/next context vào output)."
    )
    return system_prompt, user_prompt


GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_DEFAULT_MODEL = "gemini-3.5-flash-lite"
GEMINI_SUPERVISOR_MODEL = "gemini-3.1-flash-lite"
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
        "json_mode": bool(use_gemini),
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


_RATE_LIMIT_LOCK = threading.Lock()
_KEY_NEXT_ALLOWED: Dict[Tuple[str, str], float] = {}
_KEY_429_STREAK: Dict[Tuple[str, str], int] = {}
_COOLDOWN_LADDER_SEC: Tuple[float, ...] = (12.0, 30.0, 90.0, 300.0)


def _reserve_key_wait(model_name: str, api_key: str, rpm_per_key: float) -> float:
    """Đặt chỗ slot thời gian an toàn cho mỗi cặp (model, key) để không vượt trần 15 RPM."""
    if not rpm_per_key or rpm_per_key <= 0:
        return 0.0
    interval = 60.0 / float(rpm_per_key)
    bucket = (str(model_name), str(api_key))
    with _RATE_LIMIT_LOCK:
        now = time.monotonic()
        next_ok = max(now, _KEY_NEXT_ALLOWED.get(bucket, now))
        _KEY_NEXT_ALLOWED[bucket] = next_ok + interval
        return max(0.0, next_ok - now)


def _penalize_key_cooldown(model_name: str, api_key: str, cooldown_sec: float = 12.0) -> None:
    bucket = (str(model_name), str(api_key))
    with _RATE_LIMIT_LOCK:
        now = time.monotonic()
        streak = _KEY_429_STREAK.get(bucket, 0)
        escalated = _COOLDOWN_LADDER_SEC[min(streak, len(_COOLDOWN_LADDER_SEC) - 1)]
        _KEY_429_STREAK[bucket] = streak + 1
        eff_cd = max(float(cooldown_sec), escalated)
        _KEY_NEXT_ALLOWED[bucket] = max(_KEY_NEXT_ALLOWED.get(bucket, now), now + eff_cd)


def _reset_key_streak(model_name: str, api_key: str) -> None:
    bucket = (str(model_name), str(api_key))
    with _RATE_LIMIT_LOCK:
        _KEY_429_STREAK.pop(bucket, None)


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
    """Sync OpenAI-compatible LLM caller hỗ trợ xoay vòng đa khóa + Rate Limiter per-key."""
    from openai import OpenAI

    cfg = dict(llm_cfg) if llm_cfg else _get_llm_client_kwargs(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
    )
    eff_timeout = float(cfg.get("timeout", timeout))
    rpm_per_key = float(cfg.get("rpm_per_key", 0.0))
    use_json_mode = bool(cfg.get("json_mode", False))
    keys: List[str] = list(cfg.get("api_keys") or ([cfg["api_key"]] if cfg.get("api_key") else ["ollama"]))
    start_idx = next(_KEY_ROTATION_COUNTER) % len(keys)
    max_attempts = max(4, len(keys) * 2)

    last_err: Optional[Exception] = None
    for attempt in range(max_attempts):
        active_key = keys[(start_idx + attempt) % len(keys)]
        wait_sec = _reserve_key_wait(cfg["model"], active_key, rpm_per_key)
        if wait_sec > 0:
            time.sleep(wait_sec)
        try:
            client = OpenAI(base_url=cfg["base_url"], api_key=active_key, timeout=eff_timeout, max_retries=0)
            req_kwargs: Dict[str, Any] = {
                "model": cfg["model"],
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
            }
            if use_json_mode:
                req_kwargs["response_format"] = {"type": "json_object"}
            try:
                resp = client.chat.completions.create(**req_kwargs)
            except Exception as rf_exc:
                if use_json_mode and "response_format" in str(rf_exc).lower():
                    req_kwargs.pop("response_format", None)
                    resp = client.chat.completions.create(**req_kwargs)
                else:
                    raise
            _reset_key_streak(cfg["model"], active_key)
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            last_err = exc
            if attempt + 1 < max_attempts and _is_retryable_llm_error(exc):
                _penalize_key_cooldown(cfg["model"], active_key, cooldown_sec=12.0)
                time.sleep(min(8.0, 1.5 * (attempt + 1)))
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
    """Async OpenAI-compatible LLM caller hỗ trợ xoay vòng đa khóa + Rate Limiter per-key."""
    from openai import AsyncOpenAI

    cfg = dict(llm_cfg) if llm_cfg else _get_llm_client_kwargs(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
    )
    eff_timeout = float(cfg.get("timeout", timeout))
    rpm_per_key = float(cfg.get("rpm_per_key", 0.0))
    use_json_mode = bool(cfg.get("json_mode", False))
    keys: List[str] = list(cfg.get("api_keys") or ([cfg["api_key"]] if cfg.get("api_key") else ["ollama"]))
    start_idx = next(_KEY_ROTATION_COUNTER) % len(keys)
    max_attempts = max(4, len(keys) * 2)

    last_err: Optional[Exception] = None
    for attempt in range(max_attempts):
        active_key = keys[(start_idx + attempt) % len(keys)]
        wait_sec = _reserve_key_wait(cfg["model"], active_key, rpm_per_key)
        if wait_sec > 0:
            await asyncio.sleep(wait_sec)
        try:
            async with AsyncOpenAI(base_url=cfg["base_url"], api_key=active_key, timeout=eff_timeout, max_retries=0) as client:
                req_kwargs: Dict[str, Any] = {
                    "model": cfg["model"],
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                }
                if use_json_mode:
                    req_kwargs["response_format"] = {"type": "json_object"}
                try:
                    resp = await client.chat.completions.create(**req_kwargs)
                except Exception as rf_exc:
                    if use_json_mode and "response_format" in str(rf_exc).lower():
                        req_kwargs.pop("response_format", None)
                        resp = await client.chat.completions.create(**req_kwargs)
                    else:
                        raise
            _reset_key_streak(cfg["model"], active_key)
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            last_err = exc
            if attempt + 1 < max_attempts and _is_retryable_llm_error(exc):
                _penalize_key_cooldown(cfg["model"], active_key, cooldown_sec=12.0)
                await asyncio.sleep(min(8.0, 1.5 * (attempt + 1)))
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
        if "chunk_id" in parsed and isinstance(parsed.get("text") or parsed.get("raw_text"), str):
            cid_single = str(parsed["chunk_id"]).strip()
            txt_single = str(parsed.get("text") or parsed.get("raw_text") or "")
            if cid_single in batch_ids:
                mapping[cid_single] = txt_single
            elif len(batch_ids) == 1:
                mapping[batch_ids[0]] = txt_single
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
        # Chặn rò rỉ JSON wrapper bị lỗi cú pháp; chỉ cho phép plain text nếu không bắt đầu bằng { hoặc [
        stripped_head = cleaned.lstrip()
        if not stripped_head.startswith(("{", "[")) and '"chunk_id"' not in cleaned[:80]:
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


def _resolve_target_indices(
    total: int,
    limit: Optional[int],
    target_indices: Optional[Sequence[int]],
) -> List[int]:
    if target_indices is None:
        active_count = total if limit is None else min(total, max(0, int(limit)))
        return list(range(active_count))
    idxs = sorted({int(i) for i in target_indices if 0 <= int(i) < total})
    if limit is not None:
        idxs = idxs[:max(0, int(limit))]
    return idxs


def canonicalize_lesson_chunks(
    chunks: Sequence[Dict[str, Any]],
    lexicon: Dict[str, Any],
    *,
    llm_fn: Optional[Callable[..., str]] = None,
    batch_size: int = 5,
    limit: Optional[int] = None,
    target_indices: Optional[Sequence[int]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Hiệu đính danh sách chunk transcript theo batch (sync) với Integrity Guardrail.
    Tất cả metadata (`start_sec`, `end_sec`, `chunk_id`, `start_label`, `end_label`) được bảo toàn tuyệt đối.
    """
    caller = llm_fn or default_openai_llm_fn
    safe_batch_size = max(1, int(batch_size))
    total = len(chunks)
    active_indices = _resolve_target_indices(total, limit, target_indices)

    stats: Dict[str, Any] = {
        "total_chunks": total,
        "processed_chunks": len(active_indices),
        "updated": 0,
        "unchanged": 0,
        "rejected": 0,
        "errors": 0,
        "rejection_reasons": [],
        "changes": [],
    }

    result_chunks: List[Dict[str, Any]] = [dict(c) for c in chunks]
    for start in range(0, len(active_indices), safe_batch_size):
        idx_group = active_indices[start:start + safe_batch_size]
        batch = [chunks[i] for i in idx_group]
        nb_map = None
        if target_indices is not None:
            nb_map = {
                str(chunks[i].get("chunk_id") or f"idx_{pos}"): _build_pass2_neighbor_context(chunks, i)
                for pos, i in enumerate(idx_group)
            }
        sys_prompt, usr_prompt = build_correction_prompt(batch, lexicon, neighbor_contexts=nb_map)
        try:
            raw_resp = _invoke_sync_llm(caller, sys_prompt, usr_prompt)
            cand_map = _parse_llm_batch_response(raw_resp, batch)
        except Exception as exc:
            stats["errors"] += 1
            stats["rejection_reasons"].append({"chunk_id": f"batch_{start}", "reason": f"llm_error:{exc}"})
            cand_map = {}

        updated_batch = _apply_batch_candidates(batch, cand_map, stats)
        for orig_i, new_ch in zip(idx_group, updated_batch):
            result_chunks[orig_i] = new_ch

    return result_chunks, stats


async def canonicalize_lesson_chunks_async(
    chunks: Sequence[Dict[str, Any]],
    lexicon: Dict[str, Any],
    *,
    llm_fn: Optional[Callable[..., Awaitable[str]]] = None,
    batch_size: int = 5,
    limit: Optional[int] = None,
    max_concurrency: int = 3,
    target_indices: Optional[Sequence[int]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Phiên bản async chạy song song có giới hạn concurrency cho OpenAI-compatible endpoint."""
    caller = llm_fn or async_openai_llm_fn
    safe_batch_size = max(1, int(batch_size))
    total = len(chunks)
    active_indices = _resolve_target_indices(total, limit, target_indices)
    sem = asyncio.Semaphore(max(1, int(max_concurrency)))

    idx_groups: List[List[int]] = [
        active_indices[start:start + safe_batch_size]
        for start in range(0, len(active_indices), safe_batch_size)
    ]

    async def _run_one(b_idx: int, idx_group: List[int]) -> Tuple[int, Dict[str, str], Optional[str]]:
        batch = [chunks[i] for i in idx_group]
        nb_map = None
        if target_indices is not None:
            nb_map = {
                str(chunks[i].get("chunk_id") or f"idx_{pos}"): _build_pass2_neighbor_context(chunks, i)
                for pos, i in enumerate(idx_group)
            }
        sys_prompt, usr_prompt = build_correction_prompt(batch, lexicon, neighbor_contexts=nb_map)
        async with sem:
            try:
                raw_resp = await _invoke_async_llm(caller, sys_prompt, usr_prompt)
                return b_idx, _parse_llm_batch_response(raw_resp, batch), None
            except Exception as exc:
                return b_idx, {}, str(exc)

    batch_results = await asyncio.gather(*[_run_one(i, g) for i, g in enumerate(idx_groups)])

    stats: Dict[str, Any] = {
        "total_chunks": total,
        "processed_chunks": len(active_indices),
        "updated": 0,
        "unchanged": 0,
        "rejected": 0,
        "errors": 0,
        "rejection_reasons": [],
        "changes": [],
    }
    result_chunks: List[Dict[str, Any]] = [dict(c) for c in chunks]
    for b_idx, cand_map, err in sorted(batch_results, key=lambda x: x[0]):
        idx_group = idx_groups[b_idx]
        batch = [chunks[i] for i in idx_group]
        if err:
            stats["errors"] += 1
            stats["rejection_reasons"].append({"chunk_id": f"batch_{b_idx}", "reason": f"llm_error:{err}"})
        updated_batch = _apply_batch_candidates(batch, cand_map, stats)
        for orig_i, new_ch in zip(idx_group, updated_batch):
            result_chunks[orig_i] = new_ch

    return result_chunks, stats


_STANDARD_UPPER_ALLOWLIST = {
    "C++", "OOP", "IDE", "RAM", "CPU", "GPU", "STL", "AST", "API", "SQL", "DNA", "ASCII", "UTF",
    "EOF", "NULL", "TRUE", "FALSE", "FIFO", "LIFO", "DFS", "BFS", "GCD", "LCM", "DP", "O",
    "OK", "GPA", "ID", "AI", "IT", "DSA", "AC", "WA", "TLE", "MLE", "RTE", "CE", "PE",
    "AB", "ABC", "XYZ", "PTR", "IO", "UI", "UX", "OS", "DB", "HTTP", "HTTPS", "REST",
    "JSON", "XML", "HTML", "CSS", "PHP", "JS", "TS", "RUN", "POS", "NEG", "MAX", "MIN",
    "SUM", "AVG", "CNT", "LEN", "IDX", "TMP", "ANS", "RES", "NUM", "STR", "ARR", "VEC",
    "MAT", "MOD", "DIV", "XOR", "AND", "OR", "NOT", "BIT", "HEX", "BIN", "DEC", "OCT",
    "INT", "CHAR", "BOOL", "VOID", "AUTO", "ENUM", "MAIN", "ENDL", "COUT", "CIN", "STD",
    "CPP", "GCC", "EXE", "CMD", "CLI", "GUI", "URL", "URI", "IP", "DNS", "TCP", "UDP",
    "SSH", "GIT", "VS", "DEV", "PC", "WIN", "MAC", "LN", "LOG", "SIN", "COS", "TAN",
    "ABS", "POW", "SQRT",
}
_VALID_CPP_DOT_MEMBERS = {
    "ignore", "getline", "get", "peek", "clear", "sync", "eof", "fail", "good", "bad",
    "first", "second", "begin", "end", "rbegin", "rend", "size", "length", "empty",
    "push", "pop", "top", "front", "back", "insert", "erase", "find", "count",
    "lower", "upper", "at", "data", "resize", "reserve", "assign", "append", "substr",
    "compare", "swap", "sort", "reverse", "unique", "merge", "splice", "remove",
    "next", "prev", "val", "key", "left", "right", "name", "age", "gpa", "id",
    "ma", "ten", "diem", "h", "hpp", "cpp", "c", "txt", "in", "out", "exe",
    "mp4", "json", "csv", "py",
}
_SUSPICIOUS_ACRONYM_RE = re.compile(r"\b(?:[A-Z]{2,6}|[a-z]{2,12}\.[a-z]{2,6})\b")


def _extract_protected_ast_tokens(lexicon: Dict[str, Any]) -> List[str]:
    """Lấy các tên định danh C++ AST quan trọng (len >= 4) cần bảo toàn nếu đã xuất hiện ở bản gốc."""
    ast_s = lexicon.get("ast_symbols") or {}
    raw: List[str] = []
    for key in ("classes", "structs", "functions", "methods", "access_specifiers", "headers"):
        for val in ast_s.get(key, []) or []:
            tok = str(val).strip()
            # Bỏ phần prefix scope hoặc :: lấy tên lõi nếu cần
            if "::" in tok:
                tok = tok.split("::")[-1].strip()
            if len(tok) >= 4 and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", tok):
                raw.append(tok)
    return _dedupe_preserve_order(raw)


def _find_missing_ast_tokens(orig_text: str, cand_text: str, protected_tokens: Sequence[str]) -> List[str]:
    missing: List[str] = []
    for tok in protected_tokens:
        pat = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(tok)}(?![A-Za-z0-9_])")
        if pat.search(orig_text) and not pat.search(cand_text):
            missing.append(tok)
    return missing


def _scan_residual_forbidden_noise(
    text: str,
    forbidden_noise_map: Sequence[Tuple[str, str]],
) -> List[Tuple[str, str]]:
    """Quét cụm từ đồng âm ASR còn sót theo biên từ Unicode."""
    if not text or not forbidden_noise_map:
        return []
    norm_text = unicodedata.normalize("NFC", text).lower()
    hits: List[Tuple[str, str]] = []
    for bad_phrase, target in forbidden_noise_map:
        if not bad_phrase:
            continue
        pat = re.compile(rf"(?<!\w){re.escape(bad_phrase)}(?!\w)")
        if pat.search(norm_text):
            hits.append((bad_phrase, target))
    return hits


def _is_suspicious_acronym_chunk(text: str, lexicon: Dict[str, Any]) -> Optional[str]:
    """Phát hiện token viết hoa lạ hoặc cụm có dấu chấm giống header/tên biến bị ASR ghép sai (ví dụ: UV, CL, BNA, mat.hat)."""
    if not text:
        return None
    ast_lower = {h.lower() for h in lexicon.get("hotwords_list", [])}
    for m in _SUSPICIOUS_ACRONYM_RE.finditer(text):
        tok = m.group(0)
        if tok.upper() in _STANDARD_UPPER_ALLOWLIST:
            continue
        if tok.lower() in ast_lower:
            continue
        if "." in tok:
            rhs = tok.rsplit(".", 1)[-1].lower()
            if rhs in _VALID_CPP_DOT_MEMBERS:
                continue
        return tok
    return None


def find_flagged_chunk_indices(
    chunks: Sequence[Dict[str, Any]],
    lexicon: Dict[str, Any],
) -> List[int]:
    """Trả về danh sách index đã sắp xếp của các chunk còn lỗi đồng âm, rác ASR hoặc acronym nghi vấn."""
    forbidden_map = lexicon.get("forbidden_noise_map") or []
    flagged: List[int] = []
    for idx, ch in enumerate(chunks):
        txt = str(ch.get("raw_text") or ch.get("text") or "").strip()
        if not txt or ASR_EMPTY_FALLBACK_TEXT in txt:
            continue
        if (
            _contains_corrupted_asr_artifacts(txt)
            or _scan_residual_forbidden_noise(txt, forbidden_map)
            or _is_suspicious_acronym_chunk(txt, lexicon)
        ):
            flagged.append(idx)
    return flagged


def run_supervisor_layer_a(
    orig_chunks: Sequence[Dict[str, Any]],
    candidate_chunks: Sequence[Dict[str, Any]],
    lexicon: Dict[str, Any],
    *,
    pass1_stats: Optional[Dict[str, Any]] = None,
    active_limit: Optional[int] = None,
    target_indices: Optional[Sequence[int]] = None,
) -> Dict[str, Any]:
    """
    Supervisor Layer A (Deterministic, 0 LLM cost):
    1. Kiểm tra bất biến metadata (chunk_id, start_sec, end_sec, start_label, end_label, count).
    2. Kiểm tra bảo toàn AST symbol nếu bản gốc có chứa định danh C++ mà bản sửa vô tình làm mất.
    3. Quét các từ đồng âm Whisper còn sót trong `forbidden_noise_map` + token viết hoa/dấu chấm bất thường.
    4. Gom danh sách chunk bị guardrail Pass 1 từ chối để chuyển Pass 2 retry đơn lẻ.
    """
    total = len(orig_chunks)
    iter_indices = _resolve_target_indices(total, active_limit, target_indices)
    working = [dict(c) for c in candidate_chunks]
    if len(working) != total:
        # Khôi phục an toàn hoàn toàn nếu số lượng chunk bị thay đổi
        working = [dict(c) for c in orig_chunks]
        return {
            "chunks": working,
            "metadata_reverts": total,
            "ast_loss_flags": [],
            "recheck_hints": {},
            "modified_indices": [],
            "suspicious_unchanged_indices": [],
            "pass1_rejected_indices": list(iter_indices),
        }

    protected_ast = _extract_protected_ast_tokens(lexicon)
    forbidden_map = lexicon.get("forbidden_noise_map") or []

    rejected_cids = {
        str(item.get("chunk_id"))
        for item in (pass1_stats or {}).get("rejection_reasons", [])
        if item.get("chunk_id") and not str(item.get("chunk_id")).startswith("batch_")
    }

    metadata_reverts = 0
    ast_loss_flags: List[Dict[str, Any]] = []
    recheck_hints: Dict[int, str] = {}
    modified_indices: List[int] = []
    suspicious_unchanged_indices: List[int] = []
    pass1_rejected_indices: List[int] = []

    for idx in iter_indices:
        orig = orig_chunks[idx]
        cand = working[idx]
        cid = str(orig.get("chunk_id") or f"idx_{idx}")

        # 1. Metadata immutability
        meta_keys = ("chunk_id", "start_sec", "end_sec", "start_label", "end_label")
        if any(cand.get(k) != orig.get(k) for k in meta_keys):
            working[idx] = dict(orig)
            metadata_reverts += 1
            recheck_hints[idx] = "metadata_reverted_retry"
            continue

        orig_text = unicodedata.normalize("NFC", str(orig.get("raw_text") or orig.get("text") or "")).strip()
        cand_text = unicodedata.normalize("NFC", str(cand.get("raw_text") or cand.get("text") or "")).strip()

        if cand_text != orig_text:
            modified_indices.append(idx)
            # 2. AST retention check
            missing_ast = _find_missing_ast_tokens(orig_text, cand_text, protected_ast)
            if missing_ast:
                ast_loss_flags.append({"idx": idx, "chunk_id": cid, "missing_symbols": missing_ast})
                recheck_hints[idx] = f"Khôi phục & bảo toàn định danh AST bị mất: {', '.join(missing_ast)}"
        else:
            if cid in rejected_cids:
                pass1_rejected_indices.append(idx)
                recheck_hints[idx] = "Pass 1 bị guardrail từ chối (chú ý sửa tối giản, tránh tóm tắt/mất chữ)"

        # 3. Quét ký tự rác ASR + cụm từ cấm/đồng âm Whisper còn sót trên cand_text
        if _contains_corrupted_asr_artifacts(cand_text):
            existing = recheck_hints.get(idx, "")
            recheck_hints[idx] = (existing + "; " if existing else "") + "Chứa ký tự ảo giác CJK/Hangul/FFFD/lặp rác ASR cần bóc sạch"
            if cand_text == orig_text:
                suspicious_unchanged_indices.append(idx)

        hits = _scan_residual_forbidden_noise(cand_text, forbidden_map)
        suspicious_tok = _is_suspicious_acronym_chunk(cand_text, lexicon)
        if hits:
            hint_parts = [f"'{bad}' -> có thể là {tgt}" for bad, tgt in hits[:3]]
            existing = recheck_hints.get(idx, "")
            recheck_hints[idx] = (existing + "; " if existing else "") + "Nghi đồng âm: " + "; ".join(hint_parts)
            if cand_text == orig_text:
                suspicious_unchanged_indices.append(idx)
        elif suspicious_tok and cand_text == orig_text:
            recheck_hints.setdefault(idx, f"Kiểm tra token bất thường '{suspicious_tok}' xem có phải lỗi ASR không")
            suspicious_unchanged_indices.append(idx)

    return {
        "chunks": working,
        "metadata_reverts": metadata_reverts,
        "ast_loss_flags": ast_loss_flags,
        "recheck_hints": recheck_hints,
        "modified_indices": modified_indices,
        "suspicious_unchanged_indices": _dedupe_int_order(suspicious_unchanged_indices),
        "pass1_rejected_indices": _dedupe_int_order(pass1_rejected_indices),
    }


def _dedupe_int_order(items: Sequence[int]) -> List[int]:
    seen = set()
    out: List[int] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def build_supervisor_b_prompt(
    audit_items: Sequence[Dict[str, Any]],
    lexicon: Dict[str, Any],
) -> Tuple[str, str]:
    """Tạo prompt cho Cross-Model AI Supervisor Layer B (gemini-3.1-flash-lite) kiểm tra hallucination & lỗi sót."""
    system_prompt = (
        "Bạn là Giám sát viên Độc lập (Cross-Model QA Auditor) kiểm tra chất lượng hiệu đính transcript bài giảng C++.\n"
        "NGUYÊN TẮC TỐI THƯỢNG: CHỐNG ẢO GIÁC & CHỐNG BỊA ĐẶT NGỮ CẢNH.\n"
        "- Nếu `mode == 'diff'` (so sánh `before` vs `after`):\n"
        "  * Trả `REVERT` NGAY LẬP TỨC nếu gặp BẤT KỲ dấu hiệu nào sau đây:\n"
        "    1) `after` tự bịa câu lệnh/từ khóa C++ không có căn cứ âm thanh từ `before` (ví dụ 'energia/Frozen/Franklin' bị biến thành 'cout/getline/cin.ignore', hay 'intORDER/post id' bị đoán thành 'float, double, char').\n"
        "    2) `after` thay đổi sai các con số (ví dụ đổi '14' thành '4'), chèn LaTeX (`$2^8$`), làm mất tên biến/class/hàm C++, hoặc xóa/tóm tắt mất ý gốc.\n"
        "    3) `after` sửa nhầm từ tiếng Việt vốn ĐÃ ĐÚNG ngữ cảnh (ví dụ 'lên mạng tìm' bị đổi thành 'lên mảng tìm').\n"
        "  * Trả `RECHECK` nếu `after` không bịa ý nhưng VẪN còn lỗi nghe nhầm Whisper rõ ràng (ghi ngắn gọn ở `hint`).\n"
        "  * Trả `APPROVED` CHỈ KHI mọi thay đổi đều khớp âm thanh học thuật và giữ nguyên 100% ngữ nghĩa.\n"
        "- Nếu `mode == 'unchanged'` (kiểm tra chunk chưa sửa có đang bỏ sót lỗi Whisper hay không):\n"
        "  * Trả `RECHECK` kèm `hint` CHỈ KHI phát hiện rõ lỗi nghe nhầm ASR kỹ thuật/học thuật (ví dụ 'kính UV' -> 'chu vi', 'phát bại trị' -> 'giá trị', 'cộng cộng a' -> '++a', 'mạng A' -> 'mảng A', 'nôn' -> 'null').\n"
        "  * Trả `APPROVED` nếu câu đã tự nhiên, đúng ngữ cảnh.\n"
        "ĐỊNH DẠNG ĐẦU RA: Trả về DUY NHẤT JSON object dạng:\n"
        "{\"<chunk_id>\": {\"verdict\": \"APPROVED|REVERT|RECHECK\", \"hint\": \"<ngắn gọn hoặc rỗng>\"}, ...}"
    )

    user_prompt = (
        "=== NGỮ CẢNH BÀI HỌC ===\n"
        f"Tiêu đề: {lexicon.get('title', '')} | Từ khóa: {', '.join(lexicon.get('keywords', []))}\n"
        f"{lexicon.get('lexicon_prompt', '')}\n\n"
        "=== DANH SÁCH CẦN GIÁM SÁT ===\n"
        f"{json.dumps(list(audit_items), ensure_ascii=False, indent=2)}"
    )
    return system_prompt, user_prompt


def _parse_supervisor_b_response(
    raw_response: str,
    valid_chunk_ids: Sequence[str],
) -> Dict[str, Dict[str, str]]:
    """Parse chặt phản hồi từ Supervisor Layer B, chỉ chấp nhận APPROVED | REVERT | RECHECK."""
    cleaned = _strip_markdown_fences(raw_response)
    if not cleaned:
        return {}
    valid_set = set(valid_chunk_ids)
    allowed_verdicts = {"APPROVED", "REVERT", "RECHECK"}

    parsed: Any = None
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        s_obj, e_obj = cleaned.find("{"), cleaned.rfind("}")
        s_arr, e_arr = cleaned.find("["), cleaned.rfind("]")
        for a, b in ((s_obj, e_obj), (s_arr, e_arr)):
            if a != -1 and b > a:
                try:
                    parsed = json.loads(cleaned[a:b + 1])
                    break
                except json.JSONDecodeError:
                    continue

    verdicts: Dict[str, Dict[str, str]] = {}
    if isinstance(parsed, dict):
        if "results" in parsed and isinstance(parsed["results"], (dict, list)):
            parsed = parsed["results"]
        elif "verdicts" in parsed and isinstance(parsed["verdicts"], (dict, list)):
            parsed = parsed["verdicts"]

    if isinstance(parsed, dict):
        for cid, info in parsed.items():
            if cid not in valid_set:
                continue
            if isinstance(info, dict):
                v = str(info.get("verdict", "")).strip().upper()
                hint = str(info.get("hint") or info.get("reason") or "").strip()
            elif isinstance(info, str):
                v = info.strip().upper()
                hint = ""
            else:
                continue
            if v in allowed_verdicts:
                verdicts[cid] = {"verdict": v, "hint": hint}
    elif isinstance(parsed, list):
        for item in parsed:
            if not isinstance(item, dict):
                continue
            cid = str(item.get("chunk_id") or "").strip()
            v = str(item.get("verdict", "")).strip().upper()
            hint = str(item.get("hint") or item.get("reason") or "").strip()
            if cid in valid_set and v in allowed_verdicts:
                verdicts[cid] = {"verdict": v, "hint": hint}
    return verdicts


def _collect_supervisor_b_audit_items(
    orig_chunks: Sequence[Dict[str, Any]],
    working_chunks: Sequence[Dict[str, Any]],
    layer_a_res: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Gom các diff đã sửa + các chunk unchanged nghi vấn để Supervisor B rà soát."""
    items: List[Dict[str, Any]] = []
    cid_to_idx: Dict[str, int] = {}
    recheck_hints: Dict[int, str] = layer_a_res.get("recheck_hints", {})
    ast_flag_map = {f["idx"]: f["missing_symbols"] for f in layer_a_res.get("ast_loss_flags", [])}

    for idx in layer_a_res.get("modified_indices", []):
        orig_txt = str(orig_chunks[idx].get("raw_text") or orig_chunks[idx].get("text") or "")
        cand_txt = str(working_chunks[idx].get("raw_text") or working_chunks[idx].get("text") or "")
        cid = str(orig_chunks[idx].get("chunk_id") or f"idx_{idx}")
        cid_to_idx[cid] = idx
        entry: Dict[str, Any] = {
            "chunk_id": cid,
            "mode": "diff",
            "before": orig_txt,
            "after": cand_txt,
        }
        flags = []
        if idx in ast_flag_map:
            flags.append(f"lost_ast:{','.join(ast_flag_map[idx])}")
        if idx in recheck_hints:
            flags.append(recheck_hints[idx])
        if flags:
            entry["layer_a_flags"] = " | ".join(flags)
        items.append(entry)

    for idx in layer_a_res.get("suspicious_unchanged_indices", []):
        cid = str(orig_chunks[idx].get("chunk_id") or f"idx_{idx}")
        if cid in cid_to_idx:
            continue
        cid_to_idx[cid] = idx
        txt = str(working_chunks[idx].get("raw_text") or working_chunks[idx].get("text") or "")
        items.append(
            {
                "chunk_id": cid,
                "mode": "unchanged",
                "text": txt,
                "layer_a_flags": recheck_hints.get(idx, ""),
            }
        )
    return items, cid_to_idx


def _apply_supervisor_b_verdicts(
    orig_chunks: Sequence[Dict[str, Any]],
    working_chunks: List[Dict[str, Any]],
    verdicts: Dict[str, Dict[str, str]],
    cid_to_idx: Dict[str, int],
    layer_a_res: Dict[str, Any],
) -> Dict[str, Any]:
    reverted_cids: List[str] = []
    recheck_indices: List[int] = list(layer_a_res.get("pass1_rejected_indices", []))
    recheck_hints: Dict[int, str] = dict(layer_a_res.get("recheck_hints", {}))

    # Nếu Layer B phản hồi thiếu 1 chunk bị mất AST symbol, vẫn cẩn trọng đưa vào Pass 2 kiểm tra
    ast_loss_idx = {f["idx"] for f in layer_a_res.get("ast_loss_flags", [])}

    for idx in layer_a_res.get("suspicious_unchanged_indices", []):
        cid = str(orig_chunks[idx].get("chunk_id") or f"idx_{idx}")
        v_info = verdicts.get(cid)
        if v_info is None:
            # Nếu Supervisor B không phản hồi (lỗi mạng/parse), vẫn giữ flags Layer A để Pass 2 xem xét
            recheck_indices.append(idx)
        elif v_info["verdict"] == "RECHECK":
            recheck_indices.append(idx)
            if v_info.get("hint"):
                recheck_hints[idx] = v_info["hint"]

    for cid, v_info in verdicts.items():
        idx = cid_to_idx.get(cid)
        if idx is None:
            continue
        verdict = v_info["verdict"]
        if verdict == "REVERT":
            working_chunks[idx] = dict(orig_chunks[idx])
            reverted_cids.append(cid)
            # Đã revert vì chống hallucination/trôi nghĩa -> không đẩy Pass 2 nếu không phải lỗi AST
        elif verdict == "RECHECK":
            if cid not in reverted_cids:
                recheck_indices.append(idx)
                if v_info.get("hint"):
                    recheck_hints[idx] = v_info["hint"]

    for idx in ast_loss_idx:
        cid = str(orig_chunks[idx].get("chunk_id") or f"idx_{idx}")
        v_info = verdicts.get(cid)
        if v_info is None:
            # Layer B lỗi: khôi phục bản gốc thay vì mạo hiểm giữ bản mất symbol AST
            working_chunks[idx] = dict(orig_chunks[idx])
            reverted_cids.append(cid)

    return {
        "reverted_cids": reverted_cids,
        "recheck_indices": [i for i in _dedupe_int_order(recheck_indices) if str(orig_chunks[i].get("chunk_id") or f"idx_{i}") not in reverted_cids],
        "recheck_hints": recheck_hints,
    }


async def run_supervisor_layer_b_audit_async(
    orig_chunks: Sequence[Dict[str, Any]],
    working_chunks: Sequence[Dict[str, Any]],
    layer_a_res: Dict[str, Any],
    lexicon: Dict[str, Any],
    *,
    sup_llm_fn: Callable[..., Awaitable[str]],
    batch_size: int = 10,
    max_concurrency: int = 3,
) -> Dict[str, Any]:
    working = [dict(c) for c in working_chunks]
    items, cid_to_idx = _collect_supervisor_b_audit_items(orig_chunks, working, layer_a_res)
    if not items:
        return {
            "chunks": working,
            "audited": 0,
            "approved": 0,
            "reverted_cids": [],
            "recheck_indices": _dedupe_int_order(layer_a_res.get("pass1_rejected_indices", [])),
            "recheck_hints": dict(layer_a_res.get("recheck_hints", {})),
            "errors": 0,
        }

    sem = asyncio.Semaphore(max(1, int(max_concurrency)))
    step = max(1, int(batch_size))
    batches = [items[i:i + step] for i in range(0, len(items), step)]

    async def _run_sup(b: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, str]], Optional[str]]:
        sys_p, usr_p = build_supervisor_b_prompt(b, lexicon)
        cids = [x["chunk_id"] for x in b]
        async with sem:
            try:
                raw = await _invoke_async_llm(sup_llm_fn, sys_p, usr_p)
                return _parse_supervisor_b_response(raw, cids), None
            except Exception as exc:
                return {}, str(exc)

    res_list = await asyncio.gather(*[_run_sup(b) for b in batches])
    all_verdicts: Dict[str, Dict[str, str]] = {}
    sup_errors = 0
    for v_map, err in res_list:
        if err:
            sup_errors += 1
        all_verdicts.update(v_map)

    applied = _apply_supervisor_b_verdicts(orig_chunks, working, all_verdicts, cid_to_idx, layer_a_res)
    approved_cnt = sum(1 for v in all_verdicts.values() if v.get("verdict") == "APPROVED")
    return {
        "chunks": working,
        "audited": len(items),
        "approved": approved_cnt,
        "reverted_cids": applied["reverted_cids"],
        "recheck_indices": applied["recheck_indices"],
        "recheck_hints": applied["recheck_hints"],
        "errors": sup_errors,
    }


def run_supervisor_layer_b_audit(
    orig_chunks: Sequence[Dict[str, Any]],
    working_chunks: Sequence[Dict[str, Any]],
    layer_a_res: Dict[str, Any],
    lexicon: Dict[str, Any],
    *,
    sup_llm_fn: Callable[..., str],
    batch_size: int = 10,
) -> Dict[str, Any]:
    working = [dict(c) for c in working_chunks]
    items, cid_to_idx = _collect_supervisor_b_audit_items(orig_chunks, working, layer_a_res)
    if not items:
        return {
            "chunks": working,
            "audited": 0,
            "approved": 0,
            "reverted_cids": [],
            "recheck_indices": _dedupe_int_order(layer_a_res.get("pass1_rejected_indices", [])),
            "recheck_hints": dict(layer_a_res.get("recheck_hints", {})),
            "errors": 0,
        }

    step = max(1, int(batch_size))
    all_verdicts: Dict[str, Dict[str, str]] = {}
    sup_errors = 0
    for i in range(0, len(items), step):
        b = items[i:i + step]
        sys_p, usr_p = build_supervisor_b_prompt(b, lexicon)
        cids = [x["chunk_id"] for x in b]
        try:
            raw = _invoke_sync_llm(sup_llm_fn, sys_p, usr_p)
            all_verdicts.update(_parse_supervisor_b_response(raw, cids))
        except Exception:
            sup_errors += 1

    applied = _apply_supervisor_b_verdicts(orig_chunks, working, all_verdicts, cid_to_idx, layer_a_res)
    approved_cnt = sum(1 for v in all_verdicts.values() if v.get("verdict") == "APPROVED")
    return {
        "chunks": working,
        "audited": len(items),
        "approved": approved_cnt,
        "reverted_cids": applied["reverted_cids"],
        "recheck_indices": applied["recheck_indices"],
        "recheck_hints": applied["recheck_hints"],
        "errors": sup_errors,
    }


def _build_pass2_neighbor_context(chunks: Sequence[Dict[str, Any]], idx: int) -> Dict[str, str]:
    prev_txt = ""
    next_txt = ""
    if idx > 0:
        prev_txt = str(chunks[idx - 1].get("raw_text") or chunks[idx - 1].get("text") or "")
    if idx + 1 < len(chunks):
        next_txt = str(chunks[idx + 1].get("raw_text") or chunks[idx + 1].get("text") or "")
    return {"prev": prev_txt, "next": next_txt}


def _apply_pass2_single_candidate(
    orig_chunk: Dict[str, Any],
    current_chunk: Dict[str, Any],
    cand_text: Optional[str],
    protected_ast: Sequence[str],
    pass2_stats: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(current_chunk)
    cid = str(orig_chunk.get("chunk_id") or "")
    base_text = str(current_chunk.get("raw_text") or current_chunk.get("text") or "")
    orig_text = str(orig_chunk.get("raw_text") or orig_chunk.get("text") or "")

    if not cand_text:
        return out
    cand_norm = unicodedata.normalize("NFC", cand_text).strip()
    base_norm = unicodedata.normalize("NFC", base_text).strip()
    if cand_norm == base_norm:
        return out

    # Validate với orig_text để bảo toàn ngữ nghĩa gốc; cho phép targeted=True cho ca co cụm phiên âm
    is_valid, reason = validate_canonical_chunk(orig_text, cand_norm, targeted=True)
    if not is_valid:
        pass2_stats["pass2_rejected"] += 1
        pass2_stats["rejection_reasons"].append({"chunk_id": f"{cid}[pass2]", "reason": reason})
        return out

    missing_ast = _find_missing_ast_tokens(orig_text, cand_norm, protected_ast)
    if missing_ast:
        pass2_stats["pass2_rejected"] += 1
        pass2_stats["rejection_reasons"].append(
            {"chunk_id": f"{cid}[pass2]", "reason": f"lost_ast_symbol:{','.join(missing_ast)}"}
        )
        return out

    out["raw_text"] = cand_norm
    if "text" in out:
        out["text"] = cand_norm
    pass2_stats["pass2_fixed"] += 1
    pass2_stats["changes"].append(
        {
            "chunk_id": cid,
            "start_sec": orig_chunk.get("start_sec"),
            "before": base_text,
            "after": cand_norm,
            "pass": 2,
        }
    )
    return out


async def canonicalize_lesson_two_pass_async(
    chunks: Sequence[Dict[str, Any]],
    lexicon: Dict[str, Any],
    *,
    llm_fn: Optional[Callable[..., Awaitable[str]]] = None,
    supervisor_llm_fn: Optional[Callable[..., Awaitable[str]]] = None,
    batch_size: int = 8,
    limit: Optional[int] = None,
    max_concurrency: int = 4,
    enable_supervisor: bool = True,
    target_indices: Optional[Sequence[int]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Smart 2-Pass + 2-Layer Supervisor pipeline (Async)."""
    caller = llm_fn or async_openai_llm_fn
    sup_caller = supervisor_llm_fn or caller

    # Pass 1
    pass1_chunks, stats = await canonicalize_lesson_chunks_async(
        chunks,
        lexicon,
        llm_fn=caller,
        batch_size=batch_size,
        limit=limit,
        max_concurrency=max_concurrency,
        target_indices=target_indices,
    )
    active_limit_arg = None if target_indices is not None else stats["processed_chunks"]

    # Layer A (Deterministic)
    layer_a = run_supervisor_layer_a(
        chunks,
        pass1_chunks,
        lexicon,
        pass1_stats=stats,
        active_limit=active_limit_arg,
        target_indices=target_indices,
    )
    working = layer_a["chunks"]

    # Layer B (Cross-Model AI Auditor)
    if enable_supervisor:
        layer_b = await run_supervisor_layer_b_audit_async(
            chunks,
            working,
            layer_a,
            lexicon,
            sup_llm_fn=sup_caller,
            max_concurrency=max(1, min(3, max_concurrency)),
        )
        working = layer_b["chunks"]
        recheck_indices = layer_b["recheck_indices"]
        recheck_hints = layer_b["recheck_hints"]
        sup_reverted = layer_b["reverted_cids"]
        sup_audited = layer_b["audited"]
        sup_errors = layer_b["errors"]
    else:
        recheck_indices = _dedupe_int_order(
            list(layer_a["pass1_rejected_indices"]) + list(layer_a["suspicious_unchanged_indices"])
        )
        recheck_hints = dict(layer_a["recheck_hints"])
        sup_reverted = []
        sup_audited = 0
        sup_errors = 0

    # Pass 2 Targeted Refinement (batch_size=1 + neighbor context + targeted validation)
    pass2_stats: Dict[str, Any] = {
        "pass2_attempted": len(recheck_indices),
        "pass2_fixed": 0,
        "pass2_rejected": 0,
        "rejection_reasons": [],
        "changes": [],
    }
    if recheck_indices:
        protected_ast = _extract_protected_ast_tokens(lexicon)
        sem = asyncio.Semaphore(max(1, int(max_concurrency)))

        async def _run_pass2_idx(target_idx: int) -> Tuple[int, Optional[str], Optional[str]]:
            target_chunk = working[target_idx]
            cid = str(target_chunk.get("chunk_id") or f"idx_{target_idx}")
            hints_map = {cid: recheck_hints[target_idx]} if target_idx in recheck_hints else None
            nb_map = {cid: _build_pass2_neighbor_context(working, target_idx)}
            sys_p, usr_p = build_correction_prompt(
                [target_chunk],
                lexicon,
                targeted_hints=hints_map,
                neighbor_contexts=nb_map,
            )
            async with sem:
                try:
                    raw_r = await _invoke_async_llm(caller, sys_p, usr_p)
                    cand_m = _parse_llm_batch_response(raw_r, [target_chunk])
                    return target_idx, cand_m.get(cid), None
                except Exception as exc:
                    return target_idx, None, str(exc)

        p2_res = await asyncio.gather(*[_run_pass2_idx(i) for i in recheck_indices])
        for target_idx, cand_txt, err in p2_res:
            if err:
                stats["errors"] += 1
                pass2_stats["rejection_reasons"].append({"chunk_id": f"pass2_{target_idx}", "reason": f"llm_error:{err}"})
                continue
            working[target_idx] = _apply_pass2_single_candidate(
                chunks[target_idx],
                working[target_idx],
                cand_txt,
                protected_ast,
                pass2_stats,
            )

    # Final Layer A metadata immutability check before finalizing
    final_check = run_supervisor_layer_a(
        chunks,
        working,
        lexicon,
        active_limit=active_limit_arg,
        target_indices=target_indices,
    )
    final_chunks = final_check["chunks"]

    # Recount actual changes relative to original chunks
    eval_indices = _resolve_target_indices(len(chunks), active_limit_arg, target_indices)
    net_changes = []
    for idx in eval_indices:
        orig_txt = unicodedata.normalize("NFC", str(chunks[idx].get("raw_text") or chunks[idx].get("text") or "")).strip()
        fin_txt = unicodedata.normalize("NFC", str(final_chunks[idx].get("raw_text") or final_chunks[idx].get("text") or "")).strip()
        if fin_txt != orig_txt:
            net_changes.append(
                {
                    "chunk_id": final_chunks[idx].get("chunk_id"),
                    "start_sec": final_chunks[idx].get("start_sec"),
                    "before": orig_txt,
                    "after": fin_txt,
                }
            )

    stats.update(
        {
            "updated": len(net_changes),
            "unchanged": len(eval_indices) - len(net_changes),
            "changes": net_changes,
            "supervisor_audited": sup_audited,
            "supervisor_reverted": len(sup_reverted),
            "supervisor_reverted_cids": sup_reverted,
            "supervisor_errors": sup_errors,
            "metadata_reverts": layer_a["metadata_reverts"] + final_check["metadata_reverts"],
            "pass2_attempted": pass2_stats["pass2_attempted"],
            "pass2_fixed": pass2_stats["pass2_fixed"],
            "pass2_rejected": pass2_stats["pass2_rejected"],
            "rejection_reasons": stats["rejection_reasons"] + pass2_stats["rejection_reasons"],
        }
    )
    return final_chunks, stats


def canonicalize_lesson_two_pass(
    chunks: Sequence[Dict[str, Any]],
    lexicon: Dict[str, Any],
    *,
    llm_fn: Optional[Callable[..., str]] = None,
    supervisor_llm_fn: Optional[Callable[..., str]] = None,
    batch_size: int = 8,
    limit: Optional[int] = None,
    enable_supervisor: bool = True,
    target_indices: Optional[Sequence[int]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Smart 2-Pass + 2-Layer Supervisor pipeline (Sync)."""
    caller = llm_fn or default_openai_llm_fn
    sup_caller = supervisor_llm_fn or caller

    pass1_chunks, stats = canonicalize_lesson_chunks(
        chunks,
        lexicon,
        llm_fn=caller,
        batch_size=batch_size,
        limit=limit,
        target_indices=target_indices,
    )
    active_limit_arg = None if target_indices is not None else stats["processed_chunks"]
    layer_a = run_supervisor_layer_a(
        chunks,
        pass1_chunks,
        lexicon,
        pass1_stats=stats,
        active_limit=active_limit_arg,
        target_indices=target_indices,
    )
    working = layer_a["chunks"]

    if enable_supervisor:
        layer_b = run_supervisor_layer_b_audit(
            chunks,
            working,
            layer_a,
            lexicon,
            sup_llm_fn=sup_caller,
        )
        working = layer_b["chunks"]
        recheck_indices = layer_b["recheck_indices"]
        recheck_hints = layer_b["recheck_hints"]
        sup_reverted = layer_b["reverted_cids"]
        sup_audited = layer_b["audited"]
        sup_errors = layer_b["errors"]
    else:
        recheck_indices = _dedupe_int_order(
            list(layer_a["pass1_rejected_indices"]) + list(layer_a["suspicious_unchanged_indices"])
        )
        recheck_hints = dict(layer_a["recheck_hints"])
        sup_reverted = []
        sup_audited = 0
        sup_errors = 0

    pass2_stats: Dict[str, Any] = {
        "pass2_attempted": len(recheck_indices),
        "pass2_fixed": 0,
        "pass2_rejected": 0,
        "rejection_reasons": [],
        "changes": [],
    }
    if recheck_indices:
        protected_ast = _extract_protected_ast_tokens(lexicon)
        for target_idx in recheck_indices:
            target_chunk = working[target_idx]
            cid = str(target_chunk.get("chunk_id") or f"idx_{target_idx}")
            hints_map = {cid: recheck_hints[target_idx]} if target_idx in recheck_hints else None
            nb_map = {cid: _build_pass2_neighbor_context(working, target_idx)}
            sys_p, usr_p = build_correction_prompt(
                [target_chunk],
                lexicon,
                targeted_hints=hints_map,
                neighbor_contexts=nb_map,
            )
            try:
                raw_r = _invoke_sync_llm(caller, sys_p, usr_p)
                cand_m = _parse_llm_batch_response(raw_r, [target_chunk])
                working[target_idx] = _apply_pass2_single_candidate(
                    chunks[target_idx],
                    working[target_idx],
                    cand_m.get(cid),
                    protected_ast,
                    pass2_stats,
                )
            except Exception as exc:
                stats["errors"] += 1
                pass2_stats["rejection_reasons"].append({"chunk_id": f"pass2_{target_idx}", "reason": f"llm_error:{exc}"})

    final_check = run_supervisor_layer_a(
        chunks,
        working,
        lexicon,
        active_limit=active_limit_arg,
        target_indices=target_indices,
    )
    final_chunks = final_check["chunks"]

    eval_indices = _resolve_target_indices(len(chunks), active_limit_arg, target_indices)
    net_changes = []
    for idx in eval_indices:
        orig_txt = unicodedata.normalize("NFC", str(chunks[idx].get("raw_text") or chunks[idx].get("text") or "")).strip()
        fin_txt = unicodedata.normalize("NFC", str(final_chunks[idx].get("raw_text") or final_chunks[idx].get("text") or "")).strip()
        if fin_txt != orig_txt:
            net_changes.append(
                {
                    "chunk_id": final_chunks[idx].get("chunk_id"),
                    "start_sec": final_chunks[idx].get("start_sec"),
                    "before": orig_txt,
                    "after": fin_txt,
                }
            )

    stats.update(
        {
            "updated": len(net_changes),
            "unchanged": len(eval_indices) - len(net_changes),
            "changes": net_changes,
            "supervisor_audited": sup_audited,
            "supervisor_reverted": len(sup_reverted),
            "supervisor_reverted_cids": sup_reverted,
            "supervisor_errors": sup_errors,
            "metadata_reverts": layer_a["metadata_reverts"] + final_check["metadata_reverts"],
            "pass2_attempted": pass2_stats["pass2_attempted"],
            "pass2_fixed": pass2_stats["pass2_fixed"],
            "pass2_rejected": pass2_stats["pass2_rejected"],
            "rejection_reasons": stats["rejection_reasons"] + pass2_stats["rejection_reasons"],
        }
    )
    return final_chunks, stats


def find_transcript_targets(
    course_id: Optional[str] = None,
    lesson_seq: Optional[int] = None,
    transcripts_dir: Path = TRANSCRIPTS_DIR,
    *,
    start_lesson: Optional[int] = None,
    end_lesson: Optional[int] = None,
    lesson_seqs: Optional[Sequence[int]] = None,
) -> List[Dict[str, Any]]:
    """Quét các file `*_chunks.json` trong `data/transcripts/` và gắn metadata chuẩn."""
    if not transcripts_dir.exists():
        return []

    seq_filter_set = {int(x) for x in lesson_seqs} if lesson_seqs else None
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
        if seq_filter_set is not None and seq not in seq_filter_set:
            continue
        if start_lesson is not None and seq < int(start_lesson):
            continue
        if end_lesson is not None and seq > int(end_lesson):
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


class QdrantSyncResources:
    """Lazy-loaded singleton cache cho FastEmbed & QdrantClient trong 1 phiên CLI (tránh load lại 83 lần)."""

    def __init__(
        self,
        dense_model: Any = None,
        sparse_model: Any = None,
        qdrant: Any = None,
    ) -> None:
        self._dense_model = dense_model
        self._sparse_model = sparse_model
        self._qdrant = qdrant

    @property
    def dense_model(self) -> Any:
        if self._dense_model is None:
            from app.services.embedding import get_embedding_service
            self._dense_model = get_embedding_service().dense_model
        return self._dense_model

    def switch_dense_to_cpu(self) -> Any:
        """Chuyển mô hình Dense E5 sang CPUExecutionProvider khi GPU 4GB VRAM bị tràn (OOM)."""
        from fastembed import TextEmbedding

        self._dense_model = None
        self._dense_model = TextEmbedding(
            model_name=settings.EMBEDDING_MODEL_NAME,
            providers=["CPUExecutionProvider"],
            threads=4,
        )
        return self._dense_model

    @property
    def sparse_model(self) -> Any:
        if self._sparse_model is None:
            from app.services.embedding import get_embedding_service
            self._sparse_model = get_embedding_service().sparse_model
        return self._sparse_model

    @property
    def qdrant(self) -> Any:
        if self._qdrant is None:
            from qdrant_client import QdrantClient
            self._qdrant = QdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY,
                timeout=settings.QDRANT_TIMEOUT,
            )
        return self._qdrant


def upsert_lesson_chunks_to_qdrant(
    chunks: Sequence[Dict[str, Any]],
    course_id: str,
    lesson_id: str,
    lesson_seq: int,
    folder_name: str,
    *,
    resources: Optional[QdrantSyncResources] = None,
) -> int:
    """Idempotent UUIDv5 Qdrant upsert với Dense E5 ('passage: ', micro-batch 8 + CPU OOM fallback) + Sparse BM25."""
    if not chunks:
        return 0

    from qdrant_client.http import models

    res = resources if resources is not None else QdrantSyncResources()
    dense_model = res.dense_model
    sparse_model = res.sparse_model
    qdrant = res.qdrant

    texts = [str(c.get("raw_text") or c.get("text") or "") for c in chunks]
    passage_texts = [f"passage: {t}" for t in texts]
    dense_embeddings: List[Any] = []
    for s in range(0, len(passage_texts), 8):
        batch_txts = passage_texts[s:s + 8]
        try:
            dense_embeddings.extend(list(dense_model.embed(batch_txts)))
        except Exception as exc:
            err_low = str(exc).lower()
            if any(k in err_low for k in ("out of memory", "cuda", "cudnn")):
                print(
                    f"[QdrantSync] Cảnh báo VRAM CUDA ({lesson_id}): tự động fallback Dense E5 sang CPU cho các batch còn lại.",
                    flush=True,
                )
                dense_model = res.switch_dense_to_cpu()
                dense_embeddings.extend(list(dense_model.embed(batch_txts)))
            else:
                raise
    sparse_embeddings = list(sparse_model.embed(texts))

    points = []
    for i, c in enumerate(chunks):
        sp = sparse_embeddings[i]
        deterministic_key = f"{course_id}_{lesson_id}_chunk_{c['start_sec']}_{c['end_sec']}"
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, deterministic_key))
        dense_vec = dense_embeddings[i].tolist() if hasattr(dense_embeddings[i], "tolist") else list(dense_embeddings[i])
        sp_indices = sp.indices.tolist() if hasattr(sp.indices, "tolist") else list(sp.indices)
        sp_values = sp.values.tolist() if hasattr(sp.values, "tolist") else list(sp.values)
        points.append(
            models.PointStruct(
                id=point_id,
                vector={
                    "dense": dense_vec,
                    "sparse": models.SparseVector(
                        indices=sp_indices,
                        values=sp_values,
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

    for s in range(0, len(points), 100):
        qdrant.upsert(collection_name=settings.QDRANT_COLLECTION_NAME, points=points[s:s + 100])
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


def load_reclean_checkpoint(checkpoint_path: Optional[Path]) -> Dict[str, Any]:
    if checkpoint_path is None or not checkpoint_path.exists():
        return {"lessons": {}}
    try:
        data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("lessons"), dict):
            return data
    except Exception:
        pass
    return {"lessons": {}}


def save_reclean_checkpoint(checkpoint_path: Optional[Path], data: Dict[str, Any]) -> None:
    if checkpoint_path is None:
        return
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = checkpoint_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(checkpoint_path)


def _parse_lessons_arg(raw_lessons: Optional[str]) -> Optional[List[int]]:
    if not raw_lessons:
        return None
    out: List[int] = []
    for part in str(raw_lessons).replace(";", ",").split(","):
        p = part.strip()
        if p.isdigit():
            out.append(int(p))
    return out or None


def get_qdrant_video_transcript_count(resources: Optional[QdrantSyncResources] = None) -> int:
    """Đếm chính xác số point `content_type == 'video_transcript'` hiện có trên Qdrant Cloud."""
    from qdrant_client.http import models

    res = resources if resources is not None else QdrantSyncResources()
    cnt_resp = res.qdrant.count(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        count_filter=models.Filter(
            must=[models.FieldCondition(key="content_type", match=models.MatchValue(value="video_transcript"))]
        ),
        exact=True,
    )
    return int(getattr(cnt_resp, "count", 0))


def run_canonicalization_cli(args: argparse.Namespace) -> int:
    parsed_lessons = _parse_lessons_arg(getattr(args, "lessons", None))
    targets = find_transcript_targets(
        course_id=args.course,
        lesson_seq=args.lesson,
        start_lesson=getattr(args, "start_lesson", None),
        end_lesson=getattr(args, "end_lesson", None),
        lesson_seqs=parsed_lessons,
    )
    if not targets:
        print("[WARN] Không tìm thấy file *_chunks.json phù hợp bộ lọc.", flush=True)
        return 0

    dry_run = not args.apply
    use_two_pass = bool(getattr(args, "two_pass", False))
    use_supervisor = bool(getattr(args, "supervisor", False))
    if use_supervisor and not use_two_pass:
        use_two_pass = True
    targeted_only = bool(getattr(args, "targeted_only", False))
    sync_qdrant_all = bool(getattr(args, "sync_qdrant_all", False))
    do_sync_qdrant = bool(getattr(args, "sync_qdrant", False)) or sync_qdrant_all

    llm_cfg = _get_llm_client_kwargs(
        use_gemini=bool(getattr(args, "gemini", False)),
        base_url=getattr(args, "llm_base_url", None),
        api_key=getattr(args, "llm_api_key", None),
        model=getattr(args, "llm_model", None),
        timeout=float(getattr(args, "timeout", 60.0)),
    )
    sup_model = getattr(args, "supervisor_model", None) or GEMINI_SUPERVISOR_MODEL
    sup_cfg = _get_llm_client_kwargs(
        use_gemini=bool(getattr(args, "gemini", False)),
        base_url=getattr(args, "llm_base_url", None),
        api_key=getattr(args, "llm_api_key", None),
        model=sup_model if getattr(args, "gemini", False) else (getattr(args, "llm_model", None) or sup_model),
        timeout=float(getattr(args, "timeout", 60.0)),
    )
    rpm_per_key_arg = getattr(args, "rpm_per_key", None)
    eff_rpm_per_key = float(rpm_per_key_arg) if rpm_per_key_arg is not None else (8.0 if getattr(args, "gemini", False) else 0.0)
    llm_cfg["rpm_per_key"] = eff_rpm_per_key
    sup_cfg["rpm_per_key"] = eff_rpm_per_key
    max_concurrency = max(1, int(getattr(args, "max_concurrency", 3)))
    llm_reachable = _is_llm_endpoint_reachable(base_url=llm_cfg["base_url"]) if dry_run else True

    def _cli_sync_llm(sys_p: str, usr_p: str) -> str:
        return default_openai_llm_fn(sys_p, usr_p, timeout=llm_cfg["timeout"], llm_cfg=llm_cfg)

    async def _cli_async_llm(sys_p: str, usr_p: str) -> str:
        return await async_openai_llm_fn(sys_p, usr_p, timeout=llm_cfg["timeout"], llm_cfg=llm_cfg)

    def _cli_sync_sup(sys_p: str, usr_p: str) -> str:
        return default_openai_llm_fn(sys_p, usr_p, timeout=sup_cfg["timeout"], llm_cfg=sup_cfg)

    async def _cli_async_sup(sys_p: str, usr_p: str) -> str:
        return await async_openai_llm_fn(sys_p, usr_p, timeout=sup_cfg["timeout"], llm_cfg=sup_cfg)

    ckpt_path = Path(args.checkpoint_file) if getattr(args, "checkpoint_file", None) else None
    ckpt_data = load_reclean_checkpoint(ckpt_path) if (not dry_run and ckpt_path) else {"lessons": {}}
    resume_mode = bool(getattr(args, "resume", False))

    qdrant_resources = QdrantSyncResources() if (not dry_run and do_sync_qdrant) else None

    mode_label = "DRY-RUN" if dry_run else "APPLY"
    sup_label = f" | Supervisor: {sup_cfg['model']}" if use_supervisor else ""
    pass_label = "2-Pass" if use_two_pass else "1-Pass"
    scope_label = " | Targeted-Only" if targeted_only else ""
    print("=" * 76, flush=True)
    print(
        f" AST CANONICALIZER [{mode_label} | {pass_label}{scope_label}] | Targets: {len(targets)} lessons | "
        f"Batch size: {args.batch_size} | Model: {llm_cfg['model']}{sup_label}",
        flush=True,
    )
    print("=" * 76, flush=True)

    if dry_run and not llm_reachable:
        print(
            f"[DRY-RUN OFFLINE PLAN] LLM endpoint ({llm_cfg['base_url']}) is unreachable. "
            "Generating deterministic dry-run plan without external calls or mutations.",
            flush=True,
        )

    remaining_budget: Optional[int] = args.limit
    updated_seqs: List[int] = []
    all_target_seqs: List[int] = []
    total_updated = 0
    total_rejected = 0
    total_pass2_fixed = 0
    total_sup_reverted = 0
    total_meta_reverts = 0
    total_qdrant_points = 0
    total_flagged_chunks = 0

    for t in targets:
        if remaining_budget is not None and remaining_budget <= 0:
            break

        cid = t["course_id"]
        seq = t["lesson_seq"]
        lid = t["lesson_id"]
        path: Path = t["path"]
        ckpt_key = f"{cid}:{lid}"
        all_target_seqs.append(seq)

        if not dry_run and resume_mode and ckpt_data["lessons"].get(ckpt_key, {}).get("status") == "DONE":
            print(f"  - [{cid}] {lid}: [SKIP checkpoint DONE]", flush=True)
            continue

        chunks = json.loads(path.read_text(encoding="utf-8"))
        lexicon = extract_lesson_lexicon(cid, seq)
        lesson_limit = remaining_budget if remaining_budget is not None else None
        t_indices = find_flagged_chunk_indices(chunks, lexicon) if targeted_only else None
        if t_indices is not None:
            total_flagged_chunks += len(t_indices)

        if dry_run and not llm_reachable:
            base_cnt = len(t_indices) if t_indices is not None else len(chunks)
            planned_cnt = base_cnt if lesson_limit is None else min(base_cnt, lesson_limit)
            batches_cnt = (planned_cnt + max(1, args.batch_size) - 1) // max(1, args.batch_size)
            flag_str = f", flagged={len(t_indices)}" if t_indices is not None else ""
            print(
                f"  - [{cid}] {lid} ({path.name}): total_chunks={len(chunks)}{flag_str}, "
                f"planned_chunks={planned_cnt}, batches={batches_cnt}, "
                f"ast={lexicon['has_ast']}, hotwords={len(lexicon['hotwords_list'])}, "
                f"phonetic_rules={len(lexicon.get('asr_phonetic_entries', []))}",
                flush=True,
            )
            if chunks and planned_cnt > 0:
                sample_batch = [chunks[i] for i in (t_indices[:2] if t_indices else range(min(2, planned_cnt)))]
                sys_p, usr_p = build_correction_prompt(sample_batch, lexicon)
                print(
                    f"    sample_prompt_chars=(sys={len(sys_p)}, usr={len(usr_p)}) | top_hotwords={lexicon['hotwords_list'][:8]}",
                    flush=True,
                )
            if remaining_budget is not None:
                remaining_budget -= planned_cnt
            continue

        if t_indices is not None and len(t_indices) == 0:
            new_chunks = [dict(c) for c in chunks]
            stats = {
                "total_chunks": len(chunks),
                "processed_chunks": 0,
                "updated": 0,
                "unchanged": 0,
                "rejected": 0,
                "errors": 0,
                "changes": [],
            }
            print(f"  - [{cid}] {lid}: [SKIP targeted-only: 0/{len(chunks)} flagged]", flush=True)
        elif use_two_pass:
            if args.async_mode:
                new_chunks, stats = asyncio.run(
                    canonicalize_lesson_two_pass_async(
                        chunks,
                        lexicon,
                        llm_fn=_cli_async_llm,
                        supervisor_llm_fn=_cli_async_sup,
                        batch_size=args.batch_size,
                        limit=lesson_limit,
                        max_concurrency=max_concurrency,
                        enable_supervisor=use_supervisor,
                        target_indices=t_indices,
                    )
                )
            else:
                new_chunks, stats = canonicalize_lesson_two_pass(
                    chunks,
                    lexicon,
                    llm_fn=_cli_sync_llm,
                    supervisor_llm_fn=_cli_sync_sup,
                    batch_size=args.batch_size,
                    limit=lesson_limit,
                    enable_supervisor=use_supervisor,
                    target_indices=t_indices,
                )
        else:
            if args.async_mode:
                new_chunks, stats = asyncio.run(
                    canonicalize_lesson_chunks_async(
                        chunks,
                        lexicon,
                        llm_fn=_cli_async_llm,
                        batch_size=args.batch_size,
                        limit=lesson_limit,
                        max_concurrency=max_concurrency,
                        target_indices=t_indices,
                    )
                )
            else:
                new_chunks, stats = canonicalize_lesson_chunks(
                    chunks,
                    lexicon,
                    llm_fn=_cli_sync_llm,
                    batch_size=args.batch_size,
                    limit=lesson_limit,
                    target_indices=t_indices,
                )

        if remaining_budget is not None:
            remaining_budget -= stats["processed_chunks"]

        total_updated += stats["updated"]
        total_rejected += stats["rejected"]
        total_pass2_fixed += stats.get("pass2_fixed", 0)
        total_sup_reverted += stats.get("supervisor_reverted", 0)
        total_meta_reverts += stats.get("metadata_reverts", 0)

        if stats["processed_chunks"] > 0:
            extra_info = ""
            if use_two_pass:
                extra_info = (
                    f", pass2=({stats.get('pass2_fixed', 0)}/{stats.get('pass2_attempted', 0)}), "
                    f"sup_audit={stats.get('supervisor_audited', 0)}, sup_reverted={stats.get('supervisor_reverted', 0)}, "
                    f"meta_reverts={stats.get('metadata_reverts', 0)}"
                )
            print(
                f"  - [{cid}] {lid}: processed={stats['processed_chunks']}/{stats['total_chunks']}, "
                f"updated={stats['updated']}, unchanged={stats['unchanged']}, "
                f"rejected={stats['rejected']}, errors={stats['errors']}{extra_info}",
                flush=True,
            )
            for chg in stats["changes"][:3]:
                print(f"    * {chg['chunk_id']} ({chg['start_sec']}s): {chg['before'][:70]} -> {chg['after'][:70]}", flush=True)

        pts = 0
        if not dry_run:
            if stats["updated"] > 0:
                tmp_json = path.with_suffix(".tmp")
                tmp_json.write_text(json.dumps(new_chunks, ensure_ascii=False, indent=2), encoding="utf-8")
                tmp_json.replace(path)
                updated_seqs.append(seq)
            if do_sync_qdrant and (stats["updated"] > 0 or sync_qdrant_all):
                pts = upsert_lesson_chunks_to_qdrant(
                    new_chunks,
                    course_id=cid,
                    lesson_id=lid,
                    lesson_seq=seq,
                    folder_name=t["folder_name"],
                    resources=qdrant_resources,
                )
                total_qdrant_points += pts
            if ckpt_path is not None:
                is_clean_done = stats["errors"] == 0 and stats.get("supervisor_errors", 0) == 0
                ckpt_data["lessons"][ckpt_key] = {
                    "status": "DONE" if is_clean_done else "PARTIAL_ERROR",
                    "updated": stats["updated"],
                    "errors": stats["errors"],
                    "supervisor_errors": stats.get("supervisor_errors", 0),
                    "pass2_fixed": stats.get("pass2_fixed", 0),
                    "supervisor_reverted": stats.get("supervisor_reverted", 0),
                    "qdrant_upserted": pts,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                save_reclean_checkpoint(ckpt_path, ckpt_data)
            if stats["errors"] >= 3 and stats["updated"] == 0:
                print(
                    f"[STOP-QUOTA] Bài {lid} gặp {stats['errors']} lỗi LLM liên tiếp (nhiều khả năng hết RPD/quota ngày). "
                    "Tạm dừng cụm an toàn để giữ checkpoint --resume.",
                    flush=True,
                )
                break

    if dry_run:
        if targeted_only:
            print(f"[DRY-RUN] Complete. total_flagged_chunks={total_flagged_chunks}. Zero files modified.", flush=True)
        else:
            print("[DRY-RUN] Complete. Zero files modified in data/, zero Qdrant upserts.", flush=True)
    else:
        chapter_seqs = all_target_seqs if (args.refresh_chapters and sync_qdrant_all) else updated_seqs
        if args.refresh_chapters and chapter_seqs:
            refreshed = refresh_video_chapters_for_lessons(chapter_seqs)
            print(f"[APPLY] Refreshed video_chapters for {refreshed} lessons in {MANIFEST_PATH}", flush=True)
        print(
            f"[APPLY] Complete. lessons_modified={len(updated_seqs)}, "
            f"chunks_updated={total_updated}, pass2_fixed={total_pass2_fixed}, "
            f"sup_reverted={total_sup_reverted}, meta_reverts={total_meta_reverts}, "
            f"guardrail_rejected={total_rejected}, qdrant_upserted={total_qdrant_points}",
            flush=True,
        )
        if do_sync_qdrant and qdrant_resources is not None:
            try:
                q_count = get_qdrant_video_transcript_count(qdrant_resources)
                local_total = sum(
                    len(json.loads(item["path"].read_text(encoding="utf-8")))
                    for item in find_transcript_targets()
                )
                print(f"[QDRANT PARITY] exact_count={q_count} vs local_chunks={local_total}", flush=True)
            except Exception as q_exc:
                print(f"[QDRANT PARITY] Warning: không thể kiểm đếm Qdrant exact_count ({q_exc})", flush=True)
    return 0


def run_repair_asr_artifacts_cli(args: argparse.Namespace) -> int:
    """Rửa sạch tất định các chunk dính CJK/Hangul/Cyrillic/FFFD/chuỗi lặp rác và đồng bộ Qdrant + video_chapters."""
    lesson_seqs = _parse_lessons_arg(getattr(args, "lessons", None))
    targets = find_transcript_targets(
        course_id=args.course,
        lesson_seq=args.lesson,
        start_lesson=args.start_lesson,
        end_lesson=args.end_lesson,
        lesson_seqs=lesson_seqs,
    )
    if not targets:
        print("[WARN] Không tìm thấy file *_chunks.json phù hợp bộ lọc.")
        return 1

    apply_changes = bool(getattr(args, "apply", False))
    sync_qdrant = bool(getattr(args, "sync_qdrant", False))
    refresh_chapters = bool(getattr(args, "refresh_chapters", False))
    sync_resources = QdrantSyncResources() if (apply_changes and sync_qdrant) else None

    total_chunks_repaired = 0
    repaired_lessons: List[int] = []
    total_qdrant_points = 0

    for item in targets:
        path = Path(item["path"])
        chunks = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(chunks, list):
            continue

        lesson_changed = 0
        changed_chunks_only: List[Dict[str, Any]] = []
        updated_chunks: List[Dict[str, Any]] = []
        for ch in chunks:
            new_ch = dict(ch)
            orig_txt = str(new_ch.get("raw_text") or new_ch.get("text") or "")
            if _contains_corrupted_asr_artifacts(orig_txt):
                cleaned_txt = _sanitize_corrupted_asr_artifacts(orig_txt)
                if not cleaned_txt or (
                    len(cleaned_txt) < 15
                    and not any(c in VIETNAMESE_NFC_LETTERS for c in cleaned_txt)
                    and not any(ch.isdigit() for ch in cleaned_txt)
                ):
                    cleaned_txt = ASR_EMPTY_FALLBACK_TEXT
                if cleaned_txt != orig_txt:
                    new_ch["raw_text"] = cleaned_txt
                    if "text" in new_ch:
                        new_ch["text"] = cleaned_txt
                    lesson_changed += 1
                    changed_chunks_only.append(new_ch)
            updated_chunks.append(new_ch)

        if lesson_changed == 0:
            continue

        total_chunks_repaired += lesson_changed
        repaired_lessons.append(int(item["lesson_seq"]))
        print(
            f"[ASR-Repair] {item['course_id']}/{item['lesson_id']}: "
            f"cleaned={lesson_changed}/{len(updated_chunks)} chunks (apply={apply_changes})",
            flush=True,
        )

        if apply_changes:
            tmp_json = path.with_suffix(".tmp.json")
            tmp_json.write_text(json.dumps(updated_chunks, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_json.replace(path)
            if sync_qdrant and sync_resources is not None and changed_chunks_only:
                total_qdrant_points += upsert_lesson_chunks_to_qdrant(
                    changed_chunks_only,
                    item["course_id"],
                    item["lesson_id"],
                    item["lesson_seq"],
                    item["folder_name"],
                    resources=sync_resources,
                )

    refreshed_chapters = 0
    if apply_changes and refresh_chapters:
        all_seqs = sorted({int(item["lesson_seq"]) for item in targets})
        refreshed_chapters = refresh_video_chapters_for_lessons(all_seqs)

    print(
        f"[ASR-Repair DONE] lessons_modified={len(repaired_lessons)}, "
        f"chunks_repaired={total_chunks_repaired}, qdrant_upserted={total_qdrant_points}, "
        f"chapters_refreshed={refreshed_chapters}"
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
        "--repair-asr-artifacts",
        action="store_true",
        default=False,
        help="Deterministically sanitize chunks with CJK/Hangul/Cyrillic/FFFD/repeated-char Whisper noise.",
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
        "--sync-qdrant-all",
        action="store_true",
        default=False,
        help="With --apply, upsert ALL targeted lessons to Qdrant (even if Stage 2 made 0 new edits, ensuring Stage 1 edits are synced).",
    )
    parser.add_argument(
        "--targeted-only",
        action="store_true",
        default=False,
        help="Send only flagged chunks (residual ASR homophones, gibberish, suspicious acronyms) with neighbor context to LLM.",
    )
    parser.add_argument(
        "--refresh-chapters",
        action="store_true",
        default=False,
        help="With --apply, refresh video_chapters in lessons_manifest.json for modified lessons.",
    )
    parser.add_argument("--course", type=str, default=None, help="Filter by course_id (e.g., cpp-core, cpp-oop).")
    parser.add_argument("--lesson", type=int, default=None, help="Filter by lesson_seq (1..83).")
    parser.add_argument("--lessons", type=str, default=None, help="Comma-separated lesson_seqs (e.g., 2,3,4,5,53,57).")
    parser.add_argument("--start-lesson", type=int, default=None, help="Filter lesson_seq >= start_lesson.")
    parser.add_argument("--end-lesson", type=int, default=None, help="Filter lesson_seq <= end_lesson.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum total chunks to process.")
    parser.add_argument("--batch-size", type=int, default=5, help="Chunks per LLM batch request (default: 5).")
    parser.add_argument("--async-mode", action="store_true", default=False, help="Use AsyncOpenAI batched caller.")
    parser.add_argument("--two-pass", action="store_true", default=False, help="Enable Pass 1 + Layer A + Targeted Pass 2.")
    parser.add_argument("--supervisor", action="store_true", default=False, help="Enable Cross-Model AI Supervisor Layer B (implies --two-pass).")
    parser.add_argument(
        "--supervisor-model",
        type=str,
        default=GEMINI_SUPERVISOR_MODEL,
        help=f"Model for Supervisor Layer B (default: {GEMINI_SUPERVISOR_MODEL}).",
    )
    parser.add_argument("--checkpoint-file", type=str, default=None, help="Optional JSON checkpoint file for resume support.")
    parser.add_argument("--resume", action="store_true", default=False, help="Skip lessons marked DONE in --checkpoint-file.")
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
    parser.add_argument("--rpm-per-key", type=float, default=None, help="Throttle requests/minute per key (default with --gemini: 8.0, 0 disables).")
    parser.add_argument("--timeout", type=float, default=60.0, help="Per-batch LLM request timeout in seconds (default: 60.0).")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.audit_hotwords:
        return run_audit_hotwords(course_id=args.course, lesson_seq=args.lesson)

    if args.repair_asr_artifacts:
        return run_repair_asr_artifacts_cli(args)

    # Safe by default: nếu không truyền --apply thì luôn chạy dry-run
    if not args.apply and not args.dry_run:
        args.dry_run = True

    return run_canonicalization_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
