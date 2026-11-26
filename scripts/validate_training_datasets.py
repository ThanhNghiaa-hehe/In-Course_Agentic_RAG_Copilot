#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Unified Dataset Cleaning & 5-Gate Preflight Validator (All 4 Fine-Tune Models)
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Kiểm chứng & làm sạch đồng thời dữ liệu huấn luyện của cả 4 mô hình trước khi train:
  1. SLM Intent Router (`router_training_corpus_v2_9_hybrid.json`)
  2. mDeBERTa-v3 NLI Arbiter (`scratch/kaggle_bundle/mdeberta_nli/dataset/mdeberta_nli_train.jsonl`)
  3. Jina Reranker v2 (`scratch/kaggle_bundle/jina_reranker/dataset/jina_reranker_train.jsonl`)
  4. Qwen2.5-Coder-7B Socratic QLoRA (`scratch/kaggle_bundle/qwen25_qlora/dataset/qwen25_socratic_train.jsonl`)

5 Cổng Kiểm Toán Bắt Buộc (Spec 005 Hardened):
  - Gate 1: SSOT Anti-Leakage / Triple Decontamination (Exact + Jaccard < 0.65 + Token Containment < 0.85 + Content Containment < 0.85)
  - Gate 2: Exact Duplicate Conflict + Class Balance + E5 Cosine Intra-Corpus Conflict + Audit Sync
  - Gate 3: mDeBERTa 3-Way XNLI Distribution ({0, 1, 2} >= 12%), Manifest Hypothesis Parity, Zero Multi-Entailment & Temporal Balance
  - Gate 4: Jina Runtime Format Parity (<= 600 chars, zero `từ khóa:` shortcut, Intra-Lesson & Code-AST Triplets, Zero Garbled Unicode)
  - Gate 5: Qwen2.5 Socratic Contract (83/83 lessons, `SOCRATIC_GROUNDED_PROMPT`, RAG Context, Per-Lesson Timestamp Parity, `?` before `📍`, Zero Code Leak, Zero `...`) + Merge-Safe Report
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.prompts import SOCRATIC_GROUNDED_PROMPT
from scripts.canonicalize_transcripts_ast import (
    ASR_EMPTY_FALLBACK_TEXT,
    _contains_corrupted_asr_artifacts,
)
from scripts.train_and_validate_router_cv import jaccard_similarity, norm_text_for_jaccard

LESSONS_MANIFEST_PATH = PROJECT_ROOT / "data" / "curriculum" / "lessons_manifest.json"
BINDING_MANIFEST_PATH = PROJECT_ROOT / "data" / "metadata" / "lesson_code_video_binding.json"
INTENT_MANIFEST_PATH = PROJECT_ROOT / "data" / "metadata" / "router_intent_manifest.json"
GLOSSARY_MANIFEST_PATH = PROJECT_ROOT / "data" / "metadata" / "cpp_academic_glossary.json"
SLM_MERGED_PATH = PROJECT_ROOT / "data" / "metadata" / "router_training_corpus_v2_9_hybrid.json"
SLM_BASE_PATH = PROJECT_ROOT / "data" / "metadata" / "router_training_corpus.json"
BUNDLE_ROOT = PROJECT_ROOT / "scratch" / "kaggle_bundle"
REPORTS_DIR = PROJECT_ROOT / "docs" / "benchmarks"

BENCHMARK_PATH = PROJECT_ROOT / "tests" / "data" / "benchmark_golden_dataset.json"
OOD_PATH = PROJECT_ROOT / "tests" / "data" / "ood_stress_test_dataset.json"
MULTITURN_PATH = PROJECT_ROOT / "tests" / "data" / "multiturn_benchmark_dataset.json"

ALL_MODELS: Tuple[str, ...] = ("slm_router", "mdeberta_nli", "jina_reranker", "qwen25_qlora")

TIMESTAMP_RE = re.compile(r'<timestamp\s+sec="(\d+)"(?:\s+lesson="\d+")?>(\d{2,3}:\d{2})</timestamp>')
JINA_VIDEO_HEADER_RE = re.compile(r"^\[Bài giảng Video (.+?) mốc (\d{2,3}):(\d{2})\]$")
JINA_CODE_HEADER_RE = re.compile(r"^\[Mã nguồn ([A-Za-z0-9_+]+) - (.+?)\]$")
LESSON_PREFIX_STRIP_RE = re.compile(
    r"(?i)^(?:trong\s+|ở\s+|tại\s+|về\s+|học\s+|phần\s+|khi\s+học\s+|em\s+đang\s+học\s+)?"
    r"bài(?:\s+học)?\s+\d+(?:\s*[:\-–]\s*[^,.\n?]+)?[\s,.:;-]*"
)

FULL_CODE_LEAK_PATTERNS: Tuple[str, ...] = (
    "#include",
    "using namespace std",
    "int main",
    "void main",
    "signed main",
    "return 0;",
    "cin >>",
    "cout <<",
    "```cpp",
    "```c++",
)

VIETNAMESE_FUNCTION_WORDS: Set[str] = {
    "la", "là", "gì", "gi", "thế", "nào", "như", "ra", "sao", "tại", "vì", "khi",
    "trong", "của", "cho", "với", "và", "hay", "hoặc", "nhưng", "mà", "thì", "để",
    "có", "không", "được", "phải", "cần", "nên", "sẽ", "đã", "đang", "vừa", "mới",
    "rất", "quá", "lắm", "hơn", "nhất", "các", "những", "một", "hai", "mỗi", "mọi",
    "này", "đó", "đấy", "kia", "đây", "ấy", "đâu", "bao", "nhiêu", "mấy",
    "em", "mình", "tôi", "bạn", "thầy", "cô", "anh", "chị", "bot", "copilot",
    "ơi", "ạ", "nhé", "nha", "nhỉ", "hả", "vậy", "chứ", "luôn", "ngay", "ở",
    "từ", "đến", "tới", "qua", "theo", "về", "bằng", "do", "bởi", "nếu", "khiến",
}

_HELDOUT_TOKEN_CACHE: Dict[Tuple[int, int], List[Tuple[Set[str], Set[str]]]] = {}


def _tokenize_raw_and_content(text: str) -> Tuple[Set[str], Set[str]]:
    nt = norm_text_for_jaccard(text)
    raw_set = set(nt.split()) if nt else set()
    content_set = {tok for tok in raw_set if tok not in VIETNAMESE_FUNCTION_WORDS and len(tok) >= 2}
    return raw_set, content_set


def _get_cached_heldout_tokens(heldout_queries: Sequence[str]) -> List[Tuple[Set[str], Set[str]]]:
    key = (id(heldout_queries), len(heldout_queries))
    cached = _HELDOUT_TOKEN_CACHE.get(key)
    if cached is not None:
        return cached
    tokenized = [_tokenize_raw_and_content(hq) for hq in heldout_queries]
    if len(_HELDOUT_TOKEN_CACHE) > 8:
        _HELDOUT_TOKEN_CACHE.clear()
    _HELDOUT_TOKEN_CACHE[key] = tokenized
    return tokenized


def load_heldout_queries() -> Tuple[Set[str], List[str]]:
    queries: List[str] = []
    for path in (BENCHMARK_PATH, OOD_PATH):
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    q = (item.get("query") or item.get("prompt") or "").strip()
                    if q:
                        queries.append(q)
    if MULTITURN_PATH.exists():
        mt = json.loads(MULTITURN_PATH.read_text(encoding="utf-8"))
        sessions = mt.get("sessions", mt) if isinstance(mt, dict) else mt
        if isinstance(sessions, list):
            for sess in sessions:
                for t in sess.get("turns", []):
                    q = (
                        t.get("user_prompt")
                        or t.get("query")
                        or t.get("user_query")
                        or t.get("prompt")
                        or ""
                    ).strip()
                    if q:
                        queries.append(q)
    return {norm_text_for_jaccard(q) for q in queries}, queries


def check_decontamination_detailed(
    text: str,
    heldout_norms: Set[str],
    heldout_queries: Sequence[str],
    max_jaccard: float = 0.65,
    max_containment: float = 0.85,
) -> Tuple[bool, float, str]:
    """
    SSOT Decontamination Gate (§3.3 Spec 005):
    Chặn đồng thời 4 hình thái rò rỉ dữ liệu kiểm chuẩn:
      1. Exact normalized match
      2. Jaccard overlap >= 0.65
      3. Raw Token Containment >= 0.85
      4. Content-Token Containment >= 0.85 (khi cả 2 vế có >= 4 từ nội dung)
    """
    nt = norm_text_for_jaccard(text)
    if not nt or nt in heldout_norms:
        return False, 1.0, "exact_match"

    t_raw, t_content = _tokenize_raw_and_content(text)
    if not t_raw:
        return False, 1.0, "empty_tokens"

    max_j = 0.0
    for h_raw, h_content in _get_cached_heldout_tokens(heldout_queries):
        if not h_raw:
            continue
        inter = len(t_raw & h_raw)
        if inter == 0:
            continue
        union = len(t_raw | h_raw)
        j = inter / union
        if j > max_j:
            max_j = j
        if j >= max_jaccard:
            return False, round(j, 4), "jaccard_overlap"

        c_raw = inter / min(len(t_raw), len(h_raw))
        if c_raw >= max_containment:
            return False, round(c_raw, 4), "token_containment"

        if len(t_content) >= 4 and len(h_content) >= 4:
            c_inter = len(t_content & h_content)
            if c_inter > 0:
                c_cont = c_inter / min(len(t_content), len(h_content))
                if c_cont >= max_containment:
                    return False, round(c_cont, 4), "content_containment"

    return True, round(max_j, 4), "ok"


def check_decontamination(
    text: str,
    heldout_norms: Set[str],
    heldout_queries: Sequence[str],
    max_jaccard: float = 0.65,
    max_containment: float = 0.85,
) -> Tuple[bool, float]:
    ok, score, _ = check_decontamination_detailed(
        text,
        heldout_norms,
        heldout_queries,
        max_jaccard=max_jaccard,
        max_containment=max_containment,
    )
    return ok, score


def load_valid_lesson_timestamps() -> Dict[int, Dict[int, str]]:
    """
    Trả về ánh xạ mốc thời gian hợp lệ theo từng bài học: `lesson_seq -> {sec: "MM:SS"}`,
    hợp nhất từ `lessons_manifest.json`, `data/transcripts/*/*_chunks.json` và `lesson_code_video_binding.json`.
    """
    by_lesson: Dict[int, Dict[int, str]] = defaultdict(dict)
    if LESSONS_MANIFEST_PATH.exists():
        manifest = json.loads(LESSONS_MANIFEST_PATH.read_text(encoding="utf-8"))
        for cid_data in manifest.get("courses", {}).values():
            for les in cid_data.get("lessons", []):
                seq = int(les.get("seq", 0))
                if seq <= 0:
                    continue
                for ch in les.get("video_chapters", []):
                    sec = ch.get("sec")
                    lbl = ch.get("label")
                    if sec is not None and lbl:
                        by_lesson[seq][int(sec)] = str(lbl)

    transcripts_dir = PROJECT_ROOT / "data" / "transcripts"
    if transcripts_dir.exists():
        for chunk_path in sorted(transcripts_dir.rglob("*_chunks.json")):
            digits = "".join(c for c in chunk_path.stem.split("_")[0] if c.isdigit())
            if not digits:
                continue
            seq = int(digits)
            try:
                raw = json.loads(chunk_path.read_text(encoding="utf-8"))
                items = raw.get("chunks", raw) if isinstance(raw, dict) else raw
                if isinstance(items, list):
                    for ch in items:
                        sec = ch.get("start_sec")
                        lbl = ch.get("start_label")
                        if sec is not None and lbl:
                            by_lesson[seq][int(sec)] = str(lbl)
            except Exception:
                continue

    if BINDING_MANIFEST_PATH.exists():
        try:
            bdata = json.loads(BINDING_MANIFEST_PATH.read_text(encoding="utf-8"))
            for key, sec_val in (bdata.get("bindings") or {}).items():
                lesson_part = str(key).split(":", 1)[0]
                digits = "".join(c for c in lesson_part if c.isdigit())
                if digits and sec_val is not None:
                    seq = int(digits)
                    sec_i = int(sec_val)
                    by_lesson[seq].setdefault(sec_i, f"{sec_i // 60:02d}:{sec_i % 60:02d}")
        except Exception:
            pass

    return dict(by_lesson)


def _has_garbled_unicode(text: str) -> bool:
    return _contains_corrupted_asr_artifacts(text)


def _load_asr_homophone_terms() -> List[str]:
    if not GLOSSARY_MANIFEST_PATH.exists():
        return []
    try:
        gdata = json.loads(GLOSSARY_MANIFEST_PATH.read_text(encoding="utf-8"))
        terms: List[str] = []
        for group_items in (gdata.get("asr_phonetic_glossary") or {}).values():
            if not isinstance(group_items, list):
                continue
            for entry in group_items:
                for bad in entry.get("asr_noise", []):
                    b = str(bad).strip().lower()
                    if len(b) >= 4:
                        terms.append(b)
        return sorted(set(terms))
    except Exception:
        return []


def _load_intent_manifest() -> Dict[str, Any]:
    if not INTENT_MANIFEST_PATH.exists():
        return {}
    try:
        return json.loads(INTENT_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_lesson_keywords_map() -> Dict[str, Set[str]]:
    manifest = json.loads(LESSONS_MANIFEST_PATH.read_text(encoding="utf-8"))
    title_to_kws: Dict[str, Set[str]] = {}
    for cid_data in manifest.get("courses", {}).values():
        for les in cid_data.get("lessons", []):
            title = (les.get("title") or "").strip()
            kws = {str(k).strip().lower() for k in les.get("keywords", []) if str(k).strip()}
            if title:
                title_to_kws[title] = kws
    return title_to_kws


def validate_slm_corpus(
    *,
    heldout_norms: Set[str],
    heldout_queries: Sequence[str],
    max_jaccard: float = 0.65,
    max_containment: float = 0.85,
    with_e5_conflict: bool = False,
    e5_conflict_threshold: float = 0.87,
    clean_in_place: bool = False,
    corpus_path: Optional[Path] = None,
) -> Dict[str, Any]:
    path = corpus_path or (SLM_MERGED_PATH if SLM_MERGED_PATH.exists() else SLM_BASE_PATH)
    if not path.exists():
        return {"model": "slm_router", "passed": False, "error": f"Thiếu file {path}"}

    data = json.loads(path.read_text(encoding="utf-8"))
    samples = data.get("samples", [])
    seen_norm_to_intent: Dict[str, str] = {}
    clean_rows: List[Dict[str, Any]] = []
    leaked_rows: List[Dict[str, Any]] = []
    exact_dup_conflicts: List[Dict[str, Any]] = []
    duplicate_count = 0

    for s in samples:
        txt = (s.get("text") or "").strip()
        intent = s.get("intent") or ""
        nt = norm_text_for_jaccard(txt)
        if not txt or not intent:
            continue
        if nt in seen_norm_to_intent:
            prev_intent = seen_norm_to_intent[nt]
            if prev_intent != intent:
                exact_dup_conflicts.append({
                    "sim": 1.0,
                    "jaccard": 1.0,
                    "reason": "exact_duplicate_label_conflict",
                    "a_intent": prev_intent,
                    "b_intent": intent,
                    "text": txt[:80],
                })
                if clean_in_place:
                    clean_rows = [r for r in clean_rows if norm_text_for_jaccard(r.get("text", "")) != nt]
            else:
                duplicate_count += 1
            continue

        ok, score, reason = check_decontamination_detailed(
            txt,
            heldout_norms,
            heldout_queries,
            max_jaccard=max_jaccard,
            max_containment=max_containment,
        )
        if not ok:
            leaked_rows.append({"text": txt[:90], "intent": intent, "score": score, "reason": reason})
            continue

        seen_norm_to_intent[nt] = intent
        clean_rows.append(s)

    def _scan_conflicts(
        rows: List[Dict[str, Any]],
        sim_matrix: Optional[np.ndarray],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Set[int]]:
        f_list: List[Dict[str, Any]] = []
        c_list: List[Dict[str, Any]] = []
        drops: Set[int] = set()
        n = len(rows)
        for i in range(n):
            for j in range(i + 1, n):
                if rows[i]["intent"] == rows[j]["intent"]:
                    continue
                jac = jaccard_similarity(rows[i]["text"], rows[j]["text"])
                cos = float(sim_matrix[i, j]) if sim_matrix is not None else 0.0
                if jac >= 0.72 or (sim_matrix is not None and cos >= 0.93):
                    f_list.append({
                        "sim": round(cos, 4),
                        "jaccard": round(jac, 4),
                        "a_intent": rows[i]["intent"],
                        "a_group": rows[i].get("group", "base"),
                        "a_text": rows[i]["text"][:80],
                        "b_intent": rows[j]["intent"],
                        "b_group": rows[j].get("group", "base"),
                        "b_text": rows[j]["text"][:80],
                    })
                    if rows[j].get("group", "base") != "base":
                        drops.add(j)
                    elif rows[i].get("group", "base") != "base":
                        drops.add(i)
                    else:
                        drops.add(j)
                elif sim_matrix is not None and cos >= e5_conflict_threshold:
                    c_list.append({
                        "sim": round(cos, 4),
                        "jaccard": round(jac, 4),
                        "a_intent": rows[i]["intent"],
                        "a_text": rows[i]["text"][:75],
                        "b_intent": rows[j]["intent"],
                        "b_text": rows[j]["text"][:75],
                    })
        return f_list, c_list, drops

    sim_mat_full: Optional[np.ndarray] = None
    if with_e5_conflict and clean_rows:
        from app.services.embedding import get_embedding_service

        emb = get_embedding_service()
        vecs = np.array([emb.embed_query_dense(r["text"]) for r in clean_rows], dtype=np.float32)
        vecs = vecs / np.maximum(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-9)
        sim_mat_full = np.dot(vecs, vecs.T)

    fatal_conflicts, cone_overlaps, drop_indices = _scan_conflicts(clean_rows, sim_mat_full)
    if clean_in_place and drop_indices:
        keep_mask = [idx for idx in range(len(clean_rows)) if idx not in drop_indices]
        clean_rows = [clean_rows[idx] for idx in keep_mask]
        if sim_mat_full is not None:
            sim_mat_full = sim_mat_full[np.ix_(keep_mask, keep_mask)]
        fatal_conflicts, cone_overlaps, _ = _scan_conflicts(clean_rows, sim_mat_full)

    if not clean_in_place and exact_dup_conflicts:
        fatal_conflicts = exact_dup_conflicts + fatal_conflicts

    dist = dict(Counter(r["intent"] for r in clean_rows))
    counts = list(dist.values()) or [1]
    imbalance_ratio = round(max(counts) / max(1, min(counts)), 2)

    if clean_in_place:
        data["samples"] = clean_rows
        if isinstance(data.get("audit"), dict):
            data["audit"]["total_clean_samples"] = len(clean_rows)
            data["audit"]["class_distribution"] = dist
            data["audit"]["leaked_rejected_count"] = len(leaked_rows)
            data["audit"]["fatal_conflict_count"] = len(fatal_conflicts)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    audit_obj = data.get("audit")
    audit_synced = True
    if isinstance(audit_obj, dict) and "total_clean_samples" in audit_obj:
        audit_synced = (
            int(audit_obj.get("total_clean_samples", -1)) == len(clean_rows)
            and (clean_in_place or len(samples) == len(clean_rows))
        )

    passed = (
        len(clean_rows) >= 300
        and len(leaked_rows) == 0
        and imbalance_ratio <= 2.30
        and len(fatal_conflicts) == 0
        and len(exact_dup_conflicts) == 0
        and audit_synced
    )
    return {
        "model": "slm_router",
        "path": str(path),
        "total_in": len(samples),
        "total_clean": len(clean_rows),
        "duplicates_removed": duplicate_count,
        "exact_duplicate_conflict_count": len(exact_dup_conflicts),
        "audit_synced": bool(audit_synced),
        "leaked_count": len(leaked_rows),
        "leaked_preview": leaked_rows[:5],
        "class_distribution": dist,
        "imbalance_ratio": imbalance_ratio,
        "fatal_conflict_count": len(fatal_conflicts),
        "fatal_conflicts_preview": fatal_conflicts[:5],
        "e5_cone_overlap_count": len(cone_overlaps),
        "e5_cone_overlap_preview": cone_overlaps[:5],
        "passed": bool(passed),
    }


def validate_mdeberta_jsonl(
    *,
    heldout_norms: Set[str],
    heldout_queries: Sequence[str],
    max_jaccard: float = 0.65,
    max_containment: float = 0.85,
    clean_in_place: bool = False,
    dataset_path: Optional[Path] = None,
) -> Dict[str, Any]:
    path = dataset_path or (BUNDLE_ROOT / "mdeberta_nli" / "dataset" / "mdeberta_nli_train.jsonl")
    if not path.exists():
        return {"model": "mdeberta_nli", "passed": False, "error": f"Chưa tìm thấy {path} (hãy chạy bundle generator trước)"}

    intent_manifest = _load_intent_manifest()
    nli_tpl = intent_manifest.get("nli_template", "This text is about {}.")
    hyps_cfg = intent_manifest.get("nli_hypotheses", {})
    main_hypotheses: Set[str] = {
        nli_tpl.format(hyps_cfg[k])
        for k in ("course_query", "chit_chat", "out_of_scope")
        if k in hyps_cfg
    }
    temporal_tpl = intent_manifest.get("temporal_nli_template", "Câu này hỏi về {}.")
    temporal_cfg = intent_manifest.get("temporal_nli_labels", {})
    in_video_hyp = temporal_tpl.format(temporal_cfg.get("in_video", "")) if temporal_cfg.get("in_video") else ""
    off_topic_hyp = temporal_tpl.format(temporal_cfg.get("off_topic", "")) if temporal_cfg.get("off_topic") else ""
    temporal_hypotheses: Set[str] = {h for h in (in_video_hyp, off_topic_hyp) if h}
    allowed_hypotheses: Set[str] = main_hypotheses | temporal_hypotheses

    raw_rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    clean_rows: List[Dict[str, Any]] = []
    leaked = 0
    bad_schema = 0
    bad_hypothesis_count = 0
    seen_pairs: Set[Tuple[str, str]] = set()
    dup = 0

    for r in raw_rows:
        prem = (r.get("premise") or "").strip()
        hyp = (r.get("hypothesis") or "").strip()
        lbl = r.get("label")
        if not prem or not hyp or isinstance(lbl, bool) or lbl not in (0, 1, 2):
            bad_schema += 1
            continue
        if allowed_hypotheses and hyp not in allowed_hypotheses:
            bad_hypothesis_count += 1
            continue
        pair_key = (norm_text_for_jaccard(prem), hyp)
        if pair_key in seen_pairs:
            dup += 1
            continue
        ok, _ = check_decontamination(
            prem,
            heldout_norms,
            heldout_queries,
            max_jaccard=max_jaccard,
            max_containment=max_containment,
        )
        if not ok:
            leaked += 1
            continue
        seen_pairs.add(pair_key)
        clean_rows.append(r)

    # Kiểm tra multi-entailment trên 3 giả thuyết chính (mỗi premise tối đa 1 nhãn 0)
    main_by_prem: Dict[str, List[int]] = defaultdict(list)
    for r in clean_rows:
        if r["hypothesis"] in main_hypotheses:
            main_by_prem[norm_text_for_jaccard(r["premise"])].append(int(r["label"]))

    multi_entailment_premises = {
        nt_p for nt_p, lbls in main_by_prem.items() if sum(1 for x in lbls if x == 0) >= 2
    }
    multi_entailment_count = len(multi_entailment_premises)
    if clean_in_place and multi_entailment_premises:
        clean_rows = [
            r for r in clean_rows
            if not (r["hypothesis"] in main_hypotheses and norm_text_for_jaccard(r["premise"]) in multi_entailment_premises)
        ]

    if clean_in_place:
        with open(path, "w", encoding="utf-8") as f:
            for r in clean_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    lbl_dist = dict(Counter(int(r["label"]) for r in clean_rows))
    total_n = max(1, len(clean_rows))
    has_all_3_labels = all(lbl_dist.get(k, 0) > 0 for k in (0, 1, 2))
    neutral_ratio = round(lbl_dist.get(1, 0) / total_n, 4)
    min_lbl_ratio = round(min(lbl_dist.get(k, 0) / total_n for k in (0, 1, 2)), 4) if clean_rows else 0.0
    lbl_counts = [lbl_dist.get(k, 0) for k in (0, 1, 2)]
    lbl_imbalance_ratio = round(max(lbl_counts) / max(1, min(lbl_counts)), 2) if has_all_3_labels else 999.0

    # Kiểm tra cân bằng temporal_nli trên cả 2 giả thuyết in_video & off_topic
    temporal_imbalance_count = 0
    temporal_stats: Dict[str, Dict[int, int]] = {}
    for t_name, t_hyp in (("in_video", in_video_hyp), ("off_topic", off_topic_hyp)):
        if not t_hyp:
            continue
        t_rows = [r for r in clean_rows if r["hypothesis"] == t_hyp]
        t_cnt = dict(Counter(int(r["label"]) for r in t_rows))
        temporal_stats[t_name] = t_cnt
        if not t_rows or any(t_cnt.get(k, 0) == 0 for k in (0, 1, 2)):
            temporal_imbalance_count += 1
            continue
        c0, c2 = t_cnt.get(0, 0), t_cnt.get(2, 0)
        if max(c0, c2) / max(1, min(c0, c2)) > 3.0:
            temporal_imbalance_count += 1

    effective_multi_ent = 0 if clean_in_place else multi_entailment_count
    passed = (
        len(clean_rows) >= 500
        and leaked == 0
        and bad_schema == 0
        and bad_hypothesis_count == 0
        and effective_multi_ent == 0
        and temporal_imbalance_count == 0
        and has_all_3_labels
        and min_lbl_ratio >= 0.12
        and lbl_imbalance_ratio <= 4.0
    )
    return {
        "model": "mdeberta_nli",
        "path": str(path),
        "total_in": len(raw_rows),
        "total_clean": len(clean_rows),
        "duplicates_removed": dup,
        "leaked_count": leaked,
        "bad_schema_count": bad_schema,
        "bad_hypothesis_count": bad_hypothesis_count,
        "multi_entailment_count": multi_entailment_count,
        "temporal_imbalance_count": temporal_imbalance_count,
        "temporal_distribution": temporal_stats,
        "label_distribution": lbl_dist,
        "neutral_ratio": neutral_ratio,
        "min_label_ratio": min_lbl_ratio,
        "label_imbalance_ratio": lbl_imbalance_ratio,
        "passed": bool(passed),
    }


def _parse_jina_passage_header(passage: str) -> Optional[Tuple[str, str, Any]]:
    lines = passage.splitlines()
    if len(lines) < 2 or not "\n".join(lines[1:]).strip():
        return None
    header = lines[0].strip()
    m_vid = JINA_VIDEO_HEADER_RE.match(header)
    if m_vid:
        vid_title = m_vid.group(1).strip().lower()
        sec = int(m_vid.group(2)) * 60 + int(m_vid.group(3))
        return ("video", vid_title, sec)
    m_code = JINA_CODE_HEADER_RE.match(header)
    if m_code:
        lang = m_code.group(1).strip().lower()
        scope = m_code.group(2).strip()
        return ("code_ast", lang, scope)
    return None


def validate_jina_jsonl(
    *,
    heldout_norms: Set[str],
    heldout_queries: Sequence[str],
    max_jaccard: float = 0.65,
    max_containment: float = 0.85,
    clean_in_place: bool = False,
    dataset_path: Optional[Path] = None,
) -> Dict[str, Any]:
    path = dataset_path or (BUNDLE_ROOT / "jina_reranker" / "dataset" / "jina_reranker_train.jsonl")
    if not path.exists():
        return {"model": "jina_reranker", "passed": False, "error": f"Chưa tìm thấy {path}"}

    homophone_terms = _load_asr_homophone_terms()
    raw_rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    clean_rows: List[Dict[str, Any]] = []
    leaked = 0
    bad_triplets = 0
    over_max_chars_count = 0
    header_shortcut_count = 0
    false_negatives = 0
    synthetic_passages = 0
    garbled_count = 0
    intra_lesson_negative_count = 0
    code_ast_triplet_count = 0
    asr_homophone_warnings = 0

    for r in raw_rows:
        q = (r.get("query") or "").strip()
        pos = (r.get("pos_passage") or "").strip()
        neg = (r.get("neg_passage") or "").strip()
        if not q or not pos or not neg or pos == neg:
            bad_triplets += 1
            continue
        if len(pos) > 600 or len(neg) > 600:
            over_max_chars_count += 1
            bad_triplets += 1
            continue

        pos_first = pos.splitlines()[0].lower() if pos else ""
        neg_first = neg.splitlines()[0].lower() if neg else ""
        if "từ khóa:" in pos_first or "từ khóa:" in neg_first:
            header_shortcut_count += 1
            continue

        if (
            "Thông báo hệ thống Socratic:" in pos
            or "Thông báo hệ thống Socratic:" in neg
            or ASR_EMPTY_FALLBACK_TEXT in pos
            or ASR_EMPTY_FALLBACK_TEXT in neg
        ):
            synthetic_passages += 1
            continue

        if _has_garbled_unicode(pos) or _has_garbled_unicode(neg):
            garbled_count += 1
            continue

        pos_hdr = _parse_jina_passage_header(pos)
        neg_hdr = _parse_jina_passage_header(neg)
        if pos_hdr is None or neg_hdr is None:
            bad_triplets += 1
            continue

        ok, _ = check_decontamination(
            q,
            heldout_norms,
            heldout_queries,
            max_jaccard=max_jaccard,
            max_containment=max_containment,
        )
        if not ok:
            leaked += 1
            continue

        is_intra_lesson = False
        if pos_hdr[0] == "video" and neg_hdr[0] == "video" and pos_hdr[1] == neg_hdr[1]:
            if abs(int(pos_hdr[2]) - int(neg_hdr[2])) < 60:
                false_negatives += 1
                continue
            is_intra_lesson = True
        elif pos_hdr[0] == "code_ast" and neg_hdr[0] == "code_ast" and pos_hdr[2] == neg_hdr[2]:
            false_negatives += 1
            continue

        q_tokens = set(norm_text_for_jaccard(q).split())
        pos_tokens = set(norm_text_for_jaccard(pos).split())
        neg_tokens = set(norm_text_for_jaccard(neg).split())
        pos_overlap = len(q_tokens & pos_tokens)
        neg_overlap = len(q_tokens & neg_tokens)
        max_allowed_neg_overlap = pos_overlap if is_intra_lesson else (pos_overlap + 1)
        if neg_overlap > max_allowed_neg_overlap:
            false_negatives += 1
            continue

        if is_intra_lesson:
            intra_lesson_negative_count += 1
        if pos_hdr[0] == "code_ast" or neg_hdr[0] == "code_ast":
            code_ast_triplet_count += 1

        if homophone_terms:
            combined_low = f"{pos.lower()}\n{neg.lower()}"
            if any(term in combined_low for term in homophone_terms):
                asr_homophone_warnings += 1

        clean_rows.append(r)

    if clean_in_place:
        with open(path, "w", encoding="utf-8") as f:
            for r in clean_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    passed = (
        len(clean_rows) >= 200
        and leaked == 0
        and bad_triplets == 0
        and over_max_chars_count == 0
        and header_shortcut_count == 0
        and false_negatives == 0
        and synthetic_passages == 0
        and garbled_count == 0
        and intra_lesson_negative_count >= 1
        and code_ast_triplet_count >= 1
    )
    return {
        "model": "jina_reranker",
        "path": str(path),
        "total_in": len(raw_rows),
        "total_clean": len(clean_rows),
        "leaked_count": leaked,
        "bad_triplets_count": bad_triplets,
        "over_600_chars_count": over_max_chars_count,
        "header_shortcut_count": header_shortcut_count,
        "false_negative_count": false_negatives,
        "synthetic_passage_count": synthetic_passages,
        "garbled_unicode_count": garbled_count,
        "intra_lesson_negative_count": intra_lesson_negative_count,
        "code_ast_triplet_count": code_ast_triplet_count,
        "asr_homophone_warnings": asr_homophone_warnings,
        "passed": bool(passed),
    }


def _extract_qwen_student_query(user_msg: str) -> str:
    txt = user_msg
    for marker in ("\n[NGỮ CẢNH", "[NGỮ CẢNH", "\n[LƯU Ý", "[LƯU Ý"):
        idx = txt.find(marker)
        if idx != -1:
            txt = txt[:idx]
            break
    txt = txt.replace("[CÂU HỎI THẮC MẮC CỦA HỌC VIÊN]", "").strip()
    return txt


def _normalize_opening_prefix(text: str) -> str:
    cleaned = LESSON_PREFIX_STRIP_RE.sub("", text.strip())
    words = cleaned.split()[:4]
    return " ".join(words).lower()


def _check_socratic_assistant_structure(
    asst_msg: str,
    forbidden_closing_prefixes: Sequence[str],
) -> bool:
    low = asst_msg.strip().lower()
    if low.startswith(("chào bạn", "xin chào", "chào em", "hi bạn")):
        return False

    footer_marker = "📍 **Mốc video bài giảng:**"
    if footer_marker not in asst_msg:
        return False

    prose_part, footer_part = asst_msg.split(footer_marker, 1)
    prose_clean = prose_part.strip()
    footer_clean = footer_part.strip()
    if not prose_clean or not footer_clean.startswith("<timestamp") or "?" in footer_clean:
        return False
    if not prose_clean.endswith("?") or prose_clean.endswith("!"):
        return False
    if "nhé!" in prose_clean.lower() or "nha!" in prose_clean.lower():
        return False

    # Kiểm tra các câu cuối không vi phạm forbidden_closing_prefixes
    raw_sentences = [
        seg.strip(" \t\r\n*-•1234567890.)")
        for seg in re.split(r"(?<=[.!?])\s+|\n+", prose_clean)
        if seg.strip()
    ]
    if not raw_sentences:
        return False
    for sent in raw_sentences:
        s_low = sent.lower()
        if any(s_low.startswith(pref) for pref in forbidden_closing_prefixes):
            return False

    # Câu cuối cùng ngay trước footer phải kết thúc bằng '?' và chỉ có đúng 1 câu hỏi ở lượt chốt
    if not raw_sentences[-1].endswith("?"):
        return False
    return True


def validate_qwen25_jsonl(
    *,
    heldout_norms: Set[str],
    heldout_queries: Sequence[str],
    max_jaccard: float = 0.65,
    max_containment: float = 0.85,
    clean_in_place: bool = False,
    dataset_path: Optional[Path] = None,
) -> Dict[str, Any]:
    path = dataset_path or (BUNDLE_ROOT / "qwen25_qlora" / "dataset" / "qwen25_socratic_train.jsonl")
    if not path.exists():
        return {"model": "qwen25_qlora", "passed": False, "error": f"Chưa tìm thấy {path}"}

    valid_ts_by_lesson = load_valid_lesson_timestamps()
    intent_manifest = _load_intent_manifest()
    forbidden_closing_prefixes = [
        str(p).strip().lower()
        for p in intent_manifest.get("forbidden_closing_prefixes", [])
        if str(p).strip()
    ]

    raw_rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    clean_rows: List[Dict[str, Any]] = []
    leaked = 0
    bad_schema = 0
    bad_system_prompt_count = 0
    missing_or_invalid_ts = 0
    bad_socratic_ending = 0
    truncation_count = 0
    code_leak_count = 0
    user_prefixes: Set[str] = set()
    assistant_prefixes: Set[str] = set()
    covered_lessons: Set[int] = set()

    for r in raw_rows:
        msgs = r.get("messages")
        if not isinstance(msgs, list) or len(msgs) != 3:
            bad_schema += 1
            continue
        sys_msg = msgs[0].get("content", "") if msgs[0].get("role") == "system" else ""
        user_msg = msgs[1].get("content", "") if msgs[1].get("role") == "user" else ""
        asst_msg = msgs[2].get("content", "") if msgs[2].get("role") == "assistant" else ""

        if sys_msg != SOCRATIC_GROUNDED_PROMPT:
            bad_system_prompt_count += 1
            bad_schema += 1
            continue

        max_total_chars = len(SOCRATIC_GROUNDED_PROMPT) + 2050
        if (
            not user_msg.strip()
            or not asst_msg.strip()
            or (len(user_msg) + len(asst_msg)) > 2050
            or sum(len(m.get("content", "")) for m in msgs) > max_total_chars
        ):
            bad_schema += 1
            continue

        if "[NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC]" not in user_msg:
            bad_schema += 1
            continue

        ctx_seqs = [int(x) for x in re.findall(r"Nguồn Bài\s+(\d+)", user_msg)]
        if not ctx_seqs:
            bad_schema += 1
            continue
        lesson_seq = ctx_seqs[0]
        if r.get("lesson_seq") is not None and int(r["lesson_seq"]) != lesson_seq:
            bad_schema += 1
            continue

        student_q = _extract_qwen_student_query(user_msg)
        if not student_q:
            bad_schema += 1
            continue

        ok, _ = check_decontamination(
            student_q,
            heldout_norms,
            heldout_queries,
            max_jaccard=max_jaccard,
            max_containment=max_containment,
        )
        if not ok:
            leaked += 1
            continue

        if "..." in asst_msg or "…" in asst_msg:
            truncation_count += 1
            continue

        asst_low = asst_msg.lower()
        if any(pat in asst_low for pat in FULL_CODE_LEAK_PATTERNS):
            code_leak_count += 1
            continue

        ts_matches = TIMESTAMP_RE.findall(asst_msg)
        user_ts_set = set(TIMESTAMP_RE.findall(user_msg))
        lesson_valid_map = valid_ts_by_lesson.get(lesson_seq, {})
        if not ts_matches or any(
            int(sec) not in lesson_valid_map
            or lesson_valid_map[int(sec)] != lbl
            or (sec, lbl) not in user_ts_set
            for sec, lbl in ts_matches
        ):
            missing_or_invalid_ts += 1
            continue

        if not _check_socratic_assistant_structure(asst_msg, forbidden_closing_prefixes):
            bad_socratic_ending += 1
            continue

        u_open = _normalize_opening_prefix(student_q)
        a_open = _normalize_opening_prefix(asst_msg)
        if u_open:
            user_prefixes.add(u_open)
        if a_open:
            assistant_prefixes.add(a_open)
        covered_lessons.add(lesson_seq)
        clean_rows.append(r)

    if clean_in_place:
        with open(path, "w", encoding="utf-8") as f:
            for r in clean_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    passed = (
        len(clean_rows) >= 160
        and leaked == 0
        and bad_schema == 0
        and bad_system_prompt_count == 0
        and missing_or_invalid_ts == 0
        and bad_socratic_ending == 0
        and truncation_count == 0
        and code_leak_count == 0
        and len(user_prefixes) >= 12
        and len(assistant_prefixes) >= 12
        and len(covered_lessons) >= 83
    )
    return {
        "model": "qwen25_qlora",
        "path": str(path),
        "total_in": len(raw_rows),
        "total_clean": len(clean_rows),
        "lessons_covered": len(covered_lessons),
        "leaked_count": leaked,
        "bad_schema_count": bad_schema,
        "bad_system_prompt_count": bad_system_prompt_count,
        "invalid_timestamp_count": missing_or_invalid_ts,
        "bad_socratic_ending_count": bad_socratic_ending,
        "truncation_count": truncation_count,
        "code_leak_count": code_leak_count,
        "unique_user_openings": len(user_prefixes),
        "unique_assistant_openings": len(assistant_prefixes),
        "passed": bool(passed),
    }


def run_validation(
    *,
    clean_in_place: bool = False,
    with_e5_conflict: bool = False,
    models: Optional[List[str]] = None,
    reports_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    heldout_norms, heldout_queries = load_heldout_queries()
    selected = set(models) if models else set(ALL_MODELS)
    results: Dict[str, Any] = {}

    if "slm_router" in selected:
        results["slm_router"] = validate_slm_corpus(
            heldout_norms=heldout_norms,
            heldout_queries=heldout_queries,
            with_e5_conflict=with_e5_conflict,
            clean_in_place=clean_in_place,
        )
    if "mdeberta_nli" in selected:
        results["mdeberta_nli"] = validate_mdeberta_jsonl(
            heldout_norms=heldout_norms,
            heldout_queries=heldout_queries,
            clean_in_place=clean_in_place,
        )
    if "jina_reranker" in selected:
        results["jina_reranker"] = validate_jina_jsonl(
            heldout_norms=heldout_norms,
            heldout_queries=heldout_queries,
            clean_in_place=clean_in_place,
        )
    if "qwen25_qlora" in selected:
        results["qwen25_qlora"] = validate_qwen25_jsonl(
            heldout_norms=heldout_norms,
            heldout_queries=heldout_queries,
            clean_in_place=clean_in_place,
        )

    out_dir = reports_dir or REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    json_out = out_dir / "dataset_validation_report.json"
    md_out = out_dir / "dataset_validation_report.md"

    merged_models: Dict[str, Any] = {}
    if selected != set(ALL_MODELS) and json_out.exists():
        try:
            existing = json.loads(json_out.read_text(encoding="utf-8"))
            if isinstance(existing.get("models"), dict):
                merged_models.update(existing["models"])
        except Exception:
            pass
    merged_models.update(results)

    ordered_models: Dict[str, Any] = {}
    for m_key in ALL_MODELS:
        if m_key in merged_models:
            ordered_models[m_key] = merged_models[m_key]
    for m_key, m_val in merged_models.items():
        if m_key not in ordered_models:
            ordered_models[m_key] = m_val

    all_passed = all(
        m_key in ordered_models and bool(ordered_models[m_key].get("passed"))
        for m_key in ALL_MODELS
    )
    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "clean" if clean_in_place else "validate",
        "with_e5_conflict": with_e5_conflict,
        "heldout_queries_checked": len(heldout_queries),
        "all_passed": all_passed,
        "models": ordered_models,
    }

    json_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "# BÁO CÁO KIỂM CHỨNG & LÀM SẠCH DATASET (4 MÔ HÌNH FINE-TUNE)",
        f"- **Thời điểm:** `{summary['timestamp']}` | **Chế độ:** `{summary['mode']}` | **E5 Conflict Check:** `{with_e5_conflict}`",
        f"- **Số câu held-out kiểm tra khử nhiễm:** `{len(heldout_queries)}` | **Trạng thái chung:** `{'PASS' if all_passed else 'FAIL'}`",
        "",
        "| Mô hình | Tổng vào | Sạch đầu ra | Rò rỉ test | Trạng thái | Ghi chú chi tiết |",
        "|---|---:|---:|---:|---|---|",
    ]
    for m_name, res in ordered_models.items():
        if "error" in res:
            md_lines.append(f"| `{m_name}` | 0 | 0 | 0 | **FAIL** | {res['error']} |")
            continue
        notes = []
        if "imbalance_ratio" in res:
            notes.append(
                f"Ratio={res['imbalance_ratio']}x, FatalConflict={res.get('fatal_conflict_count', 0)}, "
                f"DupConflict={res.get('exact_duplicate_conflict_count', 0)}, "
                f"E5ConeOverlap={res.get('e5_cone_overlap_count', 0)}"
            )
        if "false_negative_count" in res:
            notes.append(
                f"FN={res['false_negative_count']}, Over600={res.get('over_600_chars_count', 0)}, "
                f"Shortcut={res.get('header_shortcut_count', 0)}, IntraNeg={res.get('intra_lesson_negative_count', 0)}, "
                f"AST={res.get('code_ast_triplet_count', 0)}, Garbled={res.get('garbled_unicode_count', 0)}"
            )
        if "invalid_timestamp_count" in res:
            notes.append(
                f"Lessons={res.get('lessons_covered', 0)}/83, BadTS={res['invalid_timestamp_count']}, "
                f"BadSocratic={res.get('bad_socratic_ending_count', 0)}, CodeLeak={res['code_leak_count']}, "
                f"Trunc={res.get('truncation_count', 0)}, Openings={res['unique_user_openings']}/{res.get('unique_assistant_openings', 0)}"
            )
        if "label_distribution" in res:
            notes.append(
                f"Labels={res['label_distribution']}, Neutral={res.get('neutral_ratio', 0)}, "
                f"MultiEnt={res.get('multi_entailment_count', 0)}, TempImb={res.get('temporal_imbalance_count', 0)}"
            )
        md_lines.append(
            f"| `{m_name}` | {res.get('total_in', 0)} | {res.get('total_clean', 0)} | {res.get('leaked_count', 0)} | "
            f"**{'PASS' if res.get('passed') else 'FAIL'}** | {'; '.join(notes)} |"
        )
    md_out.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate and clean fine-tuning datasets for all 4 models")
    parser.add_argument("--mode", choices=["validate", "clean"], default="clean")
    parser.add_argument("--with-e5", action="store_true", help="Quét ma trận Cosine E5 phát hiện câu xung đột nhãn nội bộ")
    parser.add_argument("--models", nargs="*", default=None, help="Danh sách model cần kiểm chứng")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = run_validation(
        clean_in_place=(args.mode == "clean"),
        with_e5_conflict=args.with_e5,
        models=args.models,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
