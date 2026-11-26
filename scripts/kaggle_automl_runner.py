#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Kaggle AutoML Remote Runner & Local Model Downloader (Official GitHub Kaggle SDK/CLI)
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Tính năng (Spec 005 Hardened):
1. Đóng gói tập dữ liệu huấn luyện khử nhiễm tuyệt đối qua SSOT `check_decontamination`
   (Jaccard < 0.65 + Token Containment < 0.85 + Content Containment < 0.85):
   - `mdeberta_nli`: Đủ 3 nhãn XNLI `{0, 1, 2}` thực chất (~18-25% neutral), 0 multi-entailment, cân bằng `temporal_nli`.
   - `jina_reranker`: Khớp 100% runtime (`<= 600` chars, `[Bài giảng Video ... mốc ...]` & `[Mã nguồn CPP - ...]`, 0 `từ khóa:`),
     kết hợp Intra-Lesson Hard Negatives (`>= 90s`), Cross-Lesson Hard Negatives & Code-AST Triplets.
   - `qwen25_qlora`: Phủ 83/83 bài học, `SOCRATIC_GROUNDED_PROMPT`, ngữ cảnh RAG chuẩn `Nguồn Bài X`,
     đúng 1 câu hỏi Socratic `?` ngay trước `📍 **Mốc video bài giảng:** <timestamp ...>`, 0 code leak, 0 `...`,
     ánh xạ lỗi trình biên dịch theo đúng chủ đề bài học.
2. Kết nối trực tiếp Kaggle qua thư viện chính thức `kaggle` (github.com/Kaggle/kaggle-api).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.prompts import SOCRATIC_GROUNDED_PROMPT
from app.services.retrieval import sanitize_text, truncate_rerank_text
from scripts.canonicalize_transcripts_ast import (
    ASR_EMPTY_FALLBACK_TEXT,
    VIETNAMESE_NFC_LETTERS,
    _contains_corrupted_asr_artifacts,
    extract_cpp_ast_symbols,
    extract_lesson_lexicon,
)
from scripts.train_and_validate_router_cv import norm_text_for_jaccard
from scripts.validate_training_datasets import check_decontamination, load_heldout_queries

BUNDLE_ROOT = PROJECT_ROOT / "scratch" / "kaggle_bundle"
JOBS_DIR = PROJECT_ROOT / "scripts" / "kaggle_jobs"

LESSONS_MANIFEST_PATH = PROJECT_ROOT / "data" / "curriculum" / "lessons_manifest.json"
COMPILER_MANIFEST_PATH = PROJECT_ROOT / "data" / "metadata" / "compiler_diagnostics_manifest.json"
ROUTER_HYBRID_PATH = PROJECT_ROOT / "data" / "metadata" / "router_training_corpus_v2_9_hybrid.json"
ROUTER_BASE_PATH = PROJECT_ROOT / "data" / "metadata" / "router_training_corpus.json"
INTENT_MANIFEST_PATH = PROJECT_ROOT / "data" / "metadata" / "router_intent_manifest.json"

LOCAL_TARGETS: Dict[str, Path] = {
    "mdeberta_nli": PROJECT_ROOT / "data" / "models" / "mdeberta-v3-xnli-ft",
    "jina_reranker": PROJECT_ROOT / "data" / "models" / "jina-reranker-v2-ft-fp32",
    "qwen25_qlora": PROJECT_ROOT / "data" / "models" / "qwen25-coder-7b-socratic-lora",
}

_NON_CPP_TECH_MARKERS: Tuple[str, ...] = (
    "python", "virtualenv", "venv", "decorator", "java", "spring boot",
    "javascript", "node.js", "mongoose", "mongodb", "react", "vite",
    "postgresql", "select ", "left join", "dockerfile", "docker",
    "kubernetes", "flexbox", "css ", "git rebase", "github actions",
    "ci/cd", "microservices", "hugging face", "đạo hàm", "tích phân",
    "định lý bayes", "central limit",
)

_CASUAL_LIFE_MARKERS: Tuple[str, ...] = (
    "ăn lẩu", "trà sữa", "trà đào", "trà chanh", "cà phê", "bún bò", "bánh mì",
    "du lịch", "đà lạt", "nha trang", "đà nẵng", "ngủ ngon", "mất ngủ",
    "dọn dẹp", "cây sen đá", "bài thơ", "hát cho mình", "chuyện cười",
    "tâm sự", "người yêu", "cờ vua", "phim", "dã ngoại", "sách kinh điển",
)

_METAPHOR_OR_MODELING_MARKERS: Tuple[str, ...] = (
    "giống như", "hình dung như", "tương đương với", "mô phỏng", "ví con trỏ",
    "bài toán quản lý", "biểu diễn", "thiết kế lớp", "xây dựng lớp",
)

# Ánh xạ chủ đề lỗi trình biên dịch tới đúng nhóm bài học tương ứng (Cấm dùng phép chia dư %)
DIAGNOSTIC_CATEGORY_LESSON_MAP: Dict[str, Tuple[int, ...]] = {
    "redeclaration_conflict": (2, 7),
    "lvalue_assignment": (2, 3),
    "undeclared_identifier": (1, 2),
    "syntax_missing_token": (1, 2, 4),
    "division_by_zero": (3,),
    "overloaded_ambiguous": (7, 8),
    "switch_datatype_constraint": (4, 5, 78),
    "break_outside_loop": (6,),
    "array_out_of_bounds_segfault": (11, 12, 14, 67),
    "variable_length_array_init": (11, 13, 15),
    "pointer_type_conversion": (57, 79),
    "null_pointer_dereference": (57, 58, 81),
    "class_struct_member_access": (50, 53, 54, 56, 69, 83),
    "stray_character": (1, 38),
}


def _load_heldout_norms() -> Tuple[Set[str], List[str]]:
    return load_heldout_queries()


def _is_clean_text(
    text: str,
    heldout_norms: Set[str],
    heldout_list: Sequence[str],
    max_j: float = 0.65,
    max_c: float = 0.85,
) -> bool:
    ok, _ = check_decontamination(
        text,
        heldout_norms,
        heldout_list,
        max_jaccard=max_j,
        max_containment=max_c,
    )
    return ok


def _load_recleaned_chunks_by_seq() -> Dict[int, Tuple[str, List[Dict[str, Any]]]]:
    """Đọc transcript chunks sạch từ `data/transcripts/*/*_chunks.json` kèm `folder_name` chuẩn runtime."""
    chunks_by_seq: Dict[int, Tuple[str, List[Dict[str, Any]]]] = {}
    transcripts_dir = PROJECT_ROOT / "data" / "transcripts"
    if not transcripts_dir.exists():
        return chunks_by_seq
    for p in sorted(transcripts_dir.rglob("*_chunks.json")):
        digits = "".join(ch for ch in p.stem.split("_")[0] if ch.isdigit())
        if not digits:
            continue
        seq = int(digits)
        folder_name = p.parent.name
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            items = raw.get("chunks", raw) if isinstance(raw, dict) else raw
            clean_items: List[Dict[str, Any]] = []
            for ch in items or []:
                if not isinstance(ch, dict):
                    continue
                txt = (ch.get("raw_text") or ch.get("text") or "").strip()
                if (
                    len(txt) < 35
                    or ASR_EMPTY_FALLBACK_TEXT in txt
                    or _contains_corrupted_asr_artifacts(txt)
                    or sum(1 for c in txt if c in VIETNAMESE_NFC_LETTERS) < 3
                    or ch.get("start_sec") is None
                    or not ch.get("start_label")
                ):
                    continue
                clean_items.append(ch)
            if clean_items:
                chunks_by_seq[seq] = (folder_name, clean_items)
        except Exception:
            continue
    return chunks_by_seq


def _load_code_ast_chunks() -> List[Dict[str, Any]]:
    """Đọc toàn bộ AST code chunks sạch (bỏ `header_preamble` / `function_anonymous`) từ `data/sample_codes`."""
    ast_items: List[Dict[str, Any]] = []
    sample_dir = PROJECT_ROOT / "data" / "sample_codes"
    if not sample_dir.exists():
        return ast_items
    for p in sorted(sample_dir.rglob("*_ast_chunks.json")):
        digits = "".join(ch for ch in p.stem.split("_")[0] if ch.isdigit())
        seq_from_name = int(digits) if digits else 0
        try:
            arr = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(arr, list):
                continue
            for item in arr:
                if not isinstance(item, dict):
                    continue
                scope = str(item.get("code_scope") or "").strip()
                if not scope or scope in ("header_preamble", "function_anonymous"):
                    continue
                ctx_code = str(item.get("context_code") or item.get("raw_text") or "").strip()
                if len(ctx_code) < 30 or _contains_corrupted_asr_artifacts(ctx_code):
                    continue
                seq = int(item.get("lesson_seq") or seq_from_name or 0)
                lang = str(item.get("language") or item.get("code_language") or "cpp").upper()
                ast_items.append({
                    "seq": seq,
                    "code_scope": scope,
                    "lang": lang,
                    "context_code": ctx_code,
                    "symbols": extract_cpp_ast_symbols(ctx_code),
                })
        except Exception:
            continue
    return ast_items


def _load_all_lessons() -> List[Dict[str, Any]]:
    manifest = json.loads(LESSONS_MANIFEST_PATH.read_text(encoding="utf-8"))
    lessons: List[Dict[str, Any]] = []
    for cid, cdata in manifest.get("courses", {}).items():
        for les in cdata.get("lessons", []):
            item = dict(les)
            item["course_id"] = cid
            lessons.append(item)
    lessons.sort(key=lambda x: int(x.get("seq", 0)))
    return lessons


def _clean_lesson_subject(title: str) -> str:
    subj = re.sub(r"^Bài\s+\d+\s*:\s*", "", title.strip(), flags=re.IGNORECASE)
    subj = re.sub(r"\s*\((?:Update\s+)?202\d\)\s*", " ", subj, flags=re.IGNORECASE)
    return " ".join(subj.split()).strip(" -–:")


def _extract_lesson_concepts(les: Dict[str, Any]) -> List[str]:
    seq = int(les.get("seq", 0))
    cid = str(les.get("course_id", "cpp-core"))
    concepts: List[str] = []
    seen: Set[str] = set()

    def _add(val: str) -> None:
        cleaned = re.sub(r"\bupdate\s+202\d\b|\btổng\s+kết\s+202\d\b", "", val, flags=re.IGNORECASE)
        cleaned = " ".join(cleaned.split()).strip(" ,;:-–()")
        if len(cleaned) >= 2 and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            concepts.append(cleaned)

    for kw in les.get("keywords", []):
        _add(str(kw))

    subj = _clean_lesson_subject(str(les.get("title", "")))
    for part in re.split(r"[,&/]|(?:\s+và\s+)|(?:\s+-\s+)", subj):
        _add(part)
    _add(subj)

    try:
        lex = extract_lesson_lexicon(cid, seq)
        for hw in lex.get("hotwords_list", [])[:8]:
            _add(str(hw))
    except Exception:
        pass

    if len(concepts) < 2:
        _add("cú pháp C++")
        _add("luồng thực thi chương trình")
    return concepts


def build_mdeberta_nli_dataset(out_file: Path, heldout_norms: Set[str], heldout_list: Sequence[str]) -> int:
    corpus_path = ROUTER_HYBRID_PATH if ROUTER_HYBRID_PATH.exists() else ROUTER_BASE_PATH
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    intent_manifest = json.loads(INTENT_MANIFEST_PATH.read_text(encoding="utf-8"))
    hyps = intent_manifest.get("nli_hypotheses", {})
    template = intent_manifest.get("nli_template", "This text is about {}.")
    sol_words = [str(w).lower() for w in intent_manifest.get("solicitation_words", [])]

    course_hyp = template.format(hyps["course_query"])
    chit_hyp = template.format(hyps["chit_chat"])
    oos_hyp = template.format(hyps["out_of_scope"])

    temporal_tpl = intent_manifest.get("temporal_nli_template", "Câu này hỏi về {}.")
    temporal_lbls = intent_manifest.get("temporal_nli_labels", {})
    in_vid_hyp = temporal_tpl.format(temporal_lbls.get("in_video", ""))
    off_hyp = temporal_tpl.format(temporal_lbls.get("off_topic", ""))

    rows: List[Dict[str, Any]] = []
    seen_pairs: Set[Tuple[str, str]] = set()

    def _emit(premise: str, hypothesis: str, label: int) -> None:
        key = (norm_text_for_jaccard(premise), hypothesis)
        if key not in seen_pairs:
            seen_pairs.add(key)
            rows.append({"premise": premise, "hypothesis": hypothesis, "label": int(label)})

    neutral_candidates_for_temporal: List[str] = []

    for sample in corpus.get("samples", []):
        txt = (sample.get("text") or "").strip()
        label_intent = sample.get("intent")
        grp = sample.get("group", "base")
        if label_intent not in ("course_query", "chit_chat", "out_of_scope"):
            continue
        if not _is_clean_text(txt, heldout_norms, heldout_list):
            continue

        low = txt.lower()
        # Phân phối 3 nhãn XNLI chuẩn (§3.5): 0=entailment, 1=neutral, 2=contradiction (0 multi-entailment)
        if label_intent == "out_of_scope":
            if any(m in low for m in _NON_CPP_TECH_MARKERS):
                # Ngôn ngữ/công nghệ ngoài khóa C++: align với ZeroShotClassificationPipeline (entailment_id=0 trên oos_hyp có 'off-topic conversation')
                _emit(txt, course_hyp, 2)
                _emit(txt, chit_hyp, 2)
                _emit(txt, oos_hyp, 0)
            elif grp != "hard_negative_hybrid" and any(m in low for m in _CASUAL_LIFE_MARKERS):
                _emit(txt, oos_hyp, 0)
                _emit(txt, chit_hyp, 1)
                _emit(txt, course_hyp, 2)
            else:
                _emit(txt, oos_hyp, 0)
                _emit(txt, course_hyp, 2)
                _emit(txt, chit_hyp, 2)
        elif label_intent == "course_query":
            if grp == "contrastive_pedagogical_metaphor" or any(m in low for m in _METAPHOR_OR_MODELING_MARKERS):
                _emit(txt, course_hyp, 0)
                _emit(txt, chit_hyp, 2)
                _emit(txt, oos_hyp, 1)
            elif any(w in low for w in sol_words):
                _emit(txt, course_hyp, 0)
                _emit(txt, chit_hyp, 1)
                _emit(txt, oos_hyp, 2)
            else:
                _emit(txt, course_hyp, 0)
                _emit(txt, chit_hyp, 2)
                _emit(txt, oos_hyp, 2)
                if "phút" not in low and "giây" not in low and "video" not in low:
                    neutral_candidates_for_temporal.append(txt)
        else:  # chit_chat
            if grp in ("contrastive_advice", "contrastive_identity") or any(
                k in low for k in ("c++", "lập trình", "thuật toán", "socratic", "vector", "bài giảng", "hệ thống", "copilot")
            ):
                _emit(txt, chit_hyp, 0)
                _emit(txt, course_hyp, 1)
                _emit(txt, oos_hyp, 2)
            else:
                _emit(txt, chit_hyp, 0)
                _emit(txt, course_hyp, 2)
                _emit(txt, oos_hyp, 2)
                neutral_candidates_for_temporal.append(txt)

    # Bổ sung bộ mẫu `temporal_nli` cân bằng tuyệt đối {0, 1, 2} trên cả `in_video` và `off_topic`
    if in_vid_hyp and off_hyp:
        in_video_premises = [
            "Khoảng phút thứ 8 trong bài giảng hôm nay thầy đang minh họa ví dụ về biến cục bộ nào?",
            "Ở mốc phút 14 của video bài học này phần giải thích điều kiện dừng vòng lặp nói gì?",
            "Đoạn đầu video khoảng phút thứ 3 giảng viên giới thiệu khái niệm tổng quan nào vậy?",
            "Tại phút 22 trên màn hình bài giảng thao tác truyền tham số vào hàm hoạt động ra sao?",
            "Khúc giữa bài giảng lúc thầy chạy thử chương trình trên IDE kết quả in ra là gì?",
            "Phút thứ 11 của buổi học trực tuyến này nhấn mạnh lưu ý gì về chỉ số mảng?",
            "Ở đoạn video vừa phát xong cách khai báo phương thức khởi tạo có tham số viết thế nào?",
            "Khoảng phút 19 bài giảng phân tích nguyên nhân gây tràn ngăn xếp đệ quy như thế nào?",
            "Đoạn cuối video bài học hôm nay tổng kết những quy tắc đặt tên định danh nào?",
            "Tại mốc 07:30 trên trình phát bài giảng ví dụ ép kiểu tường minh xử lý phần dư ra sao?",
            "Phút thứ 16 trong video thầy giải thích cơ chế cấp phát vùng nhớ động như thế nào?",
            "Ở phần mở đầu bài học khoảng 2 phút đầu giảng viên nêu mục tiêu trọng tâm gì?",
            "Đoạn phút 25 của bài giảng minh họa cách duyệt từng ký tự trong xâu bằng chỉ số ra sao?",
            "Tại khúc phút 13 trên video cách tách hàm kiểm tra điều kiện riêng biệt có tác dụng gì?",
            "Ở mốc phút 30 của bài giảng phần phân biệt phạm vi truy cập trong lớp nói về điều gì?",
            "Khoảng phút thứ 9 trong video bài học cách xử lý ký tự xuống dòng còn dư hoạt động ra sao?",
            "Đoạn phút 18 giảng viên đang vẽ sơ đồ liên kết giữa các nút dữ liệu như thế nào?",
            "Ở phút 27 trên video bài giảng độ phức tạp của hai vòng lặp lồng nhau được tính ra sao?",
            "Khúc phút thứ 5 trong bài học giải thích thứ tự thực hiện các phép toán số học thế nào?",
            "Tại mốc phút 21 của video bài giảng cách cài đặt tiêu chí so sánh tùy chỉnh viết ra sao?",
            "Khoảng phút 12 trong bài giảng thầy lưu ý lỗi tràn bộ nhớ nào khi dùng con trỏ?",
            "Ở mốc phút 15 của video bài học ví dụ truyền mảng vào hàm hoạt động thế nào?",
            "Đoạn phút 24 giảng viên phân tích khác biệt giữa tham trị và tham chiếu ra sao?",
            "Tại phút thứ 4 của bài học phần tổng hợp lại kiến thức biến toàn cục nói gì?",
            "Khúc phút 29 trong video cách đặt điều kiện biên cho thuật toán tìm kiếm viết thế nào?",
            "Ở phút 17 bài giảng minh họa thao tác cấp phát và thu hồi bộ nhớ động ra sao?",
            "Đoạn phút 20 của video giải thích nguyên lý hoạt động của hàm đệ quy như thế nào?",
            "Tại mốc phút 10 trong bài giảng ví dụ kiểm tra số nguyên tố tối ưu vòng lặp ra sao?",
            "Khoảng phút 26 của bài học thầy hướng dẫn đọc dữ liệu nhiều dòng từ bàn phím thế nào?",
            "Ở phút thứ 7 trên trình phát video cách tổ chức hàm kiểm tra tính hợp lệ hoạt động ra sao?",
            "Chỗ vừa giải thích trên bảng em theo chưa kịp, thầy nói chậm lại phần đó được không?",
            "Đoạn này giảng viên đang biến đổi điều kiện kiểm tra như thế nào vậy ạ?",
            "Khúc vừa rồi trên màn hình vì sao lại đổi dấu so sánh sang bé hơn thế?",
            "Bước đang trình bày em chưa nắm rõ vai trò của biến trung gian vừa khai báo",
            "Phần đang chiếu sao lại khởi tạo giá trị tích lũy từ một thay vì không vậy?",
            "Chỗ này tác giả tách thêm hàm phụ để làm gọn chương trình đúng không ạ?",
            "Đoạn mới lướt qua trên trình biên dịch vừa sửa lỗi thiếu dấu chấm phẩy ở dòng nào?",
            "Khúc này em thấy có hai nhánh rẽ, làm sao biết lúc nào chương trình đi vào nhánh dưới?",
            "Mấy dòng đang gõ trên màn hình có phải để kiểm tra trường hợp biên không ạ?",
            "Phần vừa giảng xong em hơi rối ở chỗ cập nhật chỉ số sau mỗi lượt chạy",
            "Đoạn này thầy minh họa cách kiểm tra đầu vào hợp lệ trước khi tính toán đúng không?",
            "Chỗ đang hiển thị kết quả in ra khác với dự đoán ban đầu của em, vì sao thế ạ?",
            "Khúc giảng ngay trước ví dụ này nhấn mạnh sai lầm phổ biến nào cần tránh vậy?",
            "Bước chuyển đổi kiểu dữ liệu ngay chỗ này có làm mất phần thập phân không?",
            "Phần giải thích vừa rồi trên slide tóm gọn lại ý chính là gì vậy ạ?",
        ]
        off_topic_temporal_premises = [
            "Hiệp hai trận giao hữu bóng đá quốc tế tối qua ở phút 75 cầu thủ nào ghi bàn?",
            "Hầm xương bò nấu nước dùng phở khoảng 45 phút trên bếp điện đã đủ mềm ngọt chưa?",
            "Từ bến xe miền Đông di chuyển lúc 7 giờ sáng ra sân bay mất khoảng bao nhiêu phút?",
            "Ủ bột bánh mì hoa cúc trong lò ấm khoảng 30 phút thì bột nở gấp đôi đúng không?",
            "Quán bún chả nướng than hoa ở góc phố này mở cửa đón khách từ mấy giờ trưa?",
            "Dự báo chiều nay khoảng 4 giờ tại khu vực trung tâm có mưa rào kèm gió lớn không?",
            "Chạy bộ nhẹ nhàng quanh hồ công viên mỗi sáng 25 phút đốt cháy khoảng bao nhiêu calo?",
            "Luộc trứng gà lòng đào sôi liu riu đúng 6 phút rồi ngâm nước đá lạnh có dễ bóc vỏ không?",
            "Chuyến tàu cao tốc khởi hành lúc 8 giờ 15 phút sáng mai dừng ở những nhà ga nào?",
            "Ngâm hạt sen khô trong nước ấm khoảng 20 phút trước khi nấu chè có nhanh bở hơn không?",
            "Phút bù giờ cuối cùng của trận chung kết quần vợt đêm qua tay vợt nào giành chiến thắng?",
            "Pha trà ô long ở nhiệt độ chín mươi độ trong 2 phút đầu tiên có giữ được hương thơm không?",
            "Xe buýt tuyến ngoại thành buổi tối cách khoảng 15 phút lại có một chuyến mới đúng không?",
            "Nướng khoai lang mật bằng nồi chiên không dầu ở mức 200 độ trong 20 phút đã chín mềm chưa?",
            "Đoạn cao tốc mới khánh thành rút ngắn thời gian lái xe về quê xuống còn mấy tiếng?",
            "Tập giãn cơ vai gáy tại bàn làm việc khoảng 10 phút buổi chiều có đỡ mỏi lưng không?",
            "Rạp chiếu phim thương mại gần ngã tư chiếu suất cuối cùng vào lúc mấy giờ đêm?",
            "Đắp mặt nạ dưỡng ẩm thảo mộc trên da khoảng 15 phút rồi rửa sạch bằng nước mát đúng không?",
            "Thời điểm hoàng hôn ngoài bãi biển đẹp nhất thường rơi vào khoảng mấy giờ chiều mùa hè?",
            "Ướp gia vị sườn non chua ngọt khoảng 35 phút trong ngăn mát tủ lạnh đã thấm đều chưa?",
            "Khoai tây cắt múi cau chiên giòn trong chảo dầu nóng khoảng 8 phút đã vàng đều chưa?",
            "Trận bóng rổ tối nay bắt đầu vào lúc mấy giờ tối theo lịch thi đấu chính thức?",
            "Tưới lan hồ điệp vào khoảng 6 giờ sáng mỗi ngày có giúp rễ cây hút ẩm tốt hơn không?",
            "Chuyến bay thẳng từ Đà Nẵng vào thành phố lúc 14 giờ chiều hạ cánh sau bao lâu?",
            "Hấp bánh bao nhân thịt bằng xửng tre khoảng 18 phút tính từ lúc nước sôi thì chín tới chưa?",
            "Quán cà phê sân vườn cuối hẻm thường đóng cửa nghỉ buổi tối vào mấy giờ?",
            "Phơi quần áo ngoài ban công hướng nắng từ 9 giờ sáng đến trưa đã khô hẳn chưa?",
            "Ngồi thiền hít thở sâu mỗi tối khoảng 12 phút trước khi ngủ có giúp thư giãn hơn không?",
            "Sáng chủ nhật hội chợ nông sản địa phương khai mạc từ mấy giờ ở quảng trường?",
            "Đoạn đường ven sông giờ cao điểm khoảng 5 giờ chiều có hay bị kẹt xe kéo dài không?",
            "Chỗ này gửi xe máy qua đêm thu phí bao nhiêu tiền một lượt vậy?",
            "Đoạn đường này giờ tan tầm buổi chiều có hay bị ngập nước sau mưa không?",
            "Khúc phố này sáng sớm tiệm bánh mì nào mở cửa bán trước 6 giờ?",
            "Chỗ này có trạm rút tiền tự động nào gần ngã ba không bạn ơi?",
            "Đoạn hẻm phía trước xe ô tô bốn chỗ có chạy lọt vào được không?",
            "Khúc công viên này buổi tối có bật đèn sáng cho người đi bộ tập thể dục không?",
            "Chỗ đang đứng chờ bắt xe buýt tuyến đi ra bến xe trung tâm ở bên nào đường?",
            "Phần vỉa hè khu chợ này cuối tuần có cho bày bán hoa tươi không?",
            "Đoạn cầu vượt này cấm xe tải nặng lưu thông trong khung giờ nào?",
            "Chỗ này sóng điện thoại di động hơi yếu, xung quanh có quán nước có wifi mạnh không?",
            "Khúc bãi biển này mùa hè nước có êm và an toàn để trẻ nhỏ tắm không?",
            "Phần đất trống bên cạnh siêu thị nghe nói sắp xây rạp chiếu phim phải không?",
            "Đoạn quốc lộ đi qua đèo buổi tối có nhiều sương mù khó quan sát không?",
            "Chỗ này gọi xe công nghệ ra nhà ga mất khoảng mấy chục nghìn tiền cước?",
            "Khúc sông này cuối tuần có chuyến thuyền du lịch ngắm hoàng hôn chạy qua không?",
        ]

        for p_in in in_video_premises:
            p_clean = p_in.strip()
            if _is_clean_text(p_clean, heldout_norms, heldout_list):
                _emit(p_clean, in_vid_hyp, 0)
                _emit(p_clean, off_hyp, 2)

        for p_off in off_topic_temporal_premises:
            p_clean = p_off.strip()
            if _is_clean_text(p_clean, heldout_norms, heldout_list):
                _emit(p_clean, in_vid_hyp, 2)
                _emit(p_clean, off_hyp, 0)

        for p_neu in neutral_candidates_for_temporal[:105]:
            _emit(p_neu, in_vid_hyp, 1)
            _emit(p_neu, off_hyp, 1)

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


_CPP_TECH_VOCAB: Optional[Set[str]] = None


def _get_cpp_tech_vocab() -> Set[str]:
    global _CPP_TECH_VOCAB
    if _CPP_TECH_VOCAB is not None:
        return _CPP_TECH_VOCAB
    vocab: Set[str] = {
        "int", "long", "float", "double", "bool", "char", "void", "auto", "const", "static",
        "struct", "class", "union", "enum", "public", "private", "protected", "virtual",
        "override", "template", "typename", "namespace", "using", "typedef", "sizeof",
        "nullptr", "return", "break", "continue", "switch", "case", "default", "while",
        "for", "else", "new", "delete", "this", "try", "catch", "throw", "friend", "inline",
        "extern", "operator", "cin", "cout", "endl", "printf", "scanf", "string", "vector",
        "pair", "map", "set", "multiset", "multimap", "unordered_map", "unordered_set",
        "stack", "queue", "deque", "priority_queue", "list", "array", "tuple", "bitset",
        "iterator", "sort", "stable_sort", "reverse", "find", "count", "lower_bound",
        "upper_bound", "binary_search", "swap", "min", "max", "gcd", "lcm", "pow", "sqrt",
        "abs", "ceil", "floor", "push_back", "pop_back", "emplace_back", "insert", "erase",
        "clear", "empty", "size", "length", "substr", "getline", "stringstream", "ifstream",
        "ofstream", "fstream", "iostream", "algorithm", "cmath", "cstring", "climits",
        "iomanip", "bits", "std", "main", "node", "head", "tail", "next", "prev", "root",
        "left", "right", "dfs", "bfs", "oop", "stl", "ide", "gcc", "ram", "cpu", "ascii",
        "pointer", "reference", "constructor", "destructor", "polymorphism", "inheritance",
        "encapsulation", "abstraction", "recursion", "backtracking", "sorting", "searching",
        "matrix", "graph", "tree", "heap", "hash", "linked", "complexity", "modulo", "prime",
        "fibonacci", "factorial", "palindrome", "subarray", "prefix", "suffix", "greedy",
        "big_o", "unsigned", "signed", "short", "wchar_t", "size_t", "uint", "int64",
    }
    glossary_path = PROJECT_ROOT / "data" / "metadata" / "cpp_academic_glossary.json"
    if glossary_path.exists():
        try:
            gdata = json.loads(glossary_path.read_text(encoding="utf-8"))
            for item in (gdata.values() if isinstance(gdata, dict) else gdata):
                if isinstance(item, list):
                    for entry in item:
                        if isinstance(entry, dict):
                            for fld in ("canonical", "term", "symbol", "en"):
                                v = str(entry.get(fld) or "").strip()
                                if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_:<>]{1,}", v):
                                    vocab.add(v.lower())
        except Exception:
            pass
    _CPP_TECH_VOCAB = vocab
    return vocab


def _is_cpp_technical_token(tok: str, tech_vocab: Set[str]) -> bool:
    low = tok.lower()
    if low in tech_vocab:
        return True
    if any(ch in tok for ch in ("_", "::", "<", ">")) or any(ch.isdigit() for ch in tok):
        return True
    # camelCase định danh thực (vd: quickSort, pushBack, TinhGPA)
    if len(tok) >= 4 and any(c.islower() for c in tok) and any(c.isupper() for c in tok[1:]):
        return True
    return False


def _extract_in_chunk_terms(
    chunk_text: str,
    candidate_concepts: Sequence[str],
) -> List[str]:
    low_txt = chunk_text.lower()
    matched: List[str] = []
    for c in candidate_concepts:
        c_str = c.strip()
        if len(c_str) < 2 or c_str.lower() in {m.lower() for m in matched}:
            continue
        if re.fullmatch(r"[A-Za-z0-9_]+", c_str):
            found = bool(re.search(rf"(?<!\w){re.escape(c_str.lower())}(?!\w)", low_txt))
        else:
            found = c_str.lower() in low_txt
        if found:
            matched.append(c_str)

    if len(matched) < 2:
        tech_vocab = _get_cpp_tech_vocab()
        # Chỉ bóc định danh C++/kỹ thuật xác thực, cấm nhặt từ tiếng Việt không dấu (khi, trong, Sau...)
        for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_:<>]{2,}", chunk_text):
            if tok.lower() not in {m.lower() for m in matched} and _is_cpp_technical_token(tok, tech_vocab):
                matched.append(tok)
            if len(matched) >= 3:
                break

    if not matched and candidate_concepts:
        matched.append(candidate_concepts[0].strip())
    return matched[:3]


def build_jina_reranker_dataset(out_file: Path, heldout_norms: Set[str], heldout_list: Sequence[str]) -> int:
    lessons = _load_all_lessons()
    chunks_by_seq = _load_recleaned_chunks_by_seq()
    ast_chunks = _load_code_ast_chunks()
    les_by_seq = {int(l["seq"]): l for l in lessons}

    video_passages: List[Dict[str, Any]] = []
    video_by_seq: Dict[int, List[Dict[str, Any]]] = {}

    for les in lessons:
        seq = int(les.get("seq", 0))
        concepts = _extract_lesson_concepts(les)
        rec_entry = chunks_by_seq.get(seq)
        if not rec_entry:
            continue
        folder_name, rec_chunks = rec_entry
        vid_title = f"{folder_name}.mp4"

        step = max(1, len(rec_chunks) // 6)
        picked = rec_chunks[::step][:6]
        seq_items: List[Dict[str, Any]] = []
        for ch in picked:
            start_sec = int(ch.get("start_sec", 0))
            start_lbl = str(ch.get("start_label") or f"{start_sec // 60:02d}:{start_sec % 60:02d}")
            clean_txt = sanitize_text(str(ch.get("raw_text") or ch.get("text") or ""))
            if len(clean_txt) < 35 or _contains_corrupted_asr_artifacts(clean_txt):
                continue
            raw_video_item = f"[Bài giảng Video {vid_title} mốc {start_lbl}]\n{clean_txt}"
            passage = truncate_rerank_text(raw_video_item, max_chars=600)
            if _contains_corrupted_asr_artifacts(passage):
                continue
            in_terms = _extract_in_chunk_terms(clean_txt, concepts)
            item = {
                "kind": "video",
                "seq": seq,
                "sec": start_sec,
                "vid_title": vid_title,
                "concepts": in_terms,
                "kw_set": {c.lower() for c in concepts},
                "passage": passage,
                "tokens": set(norm_text_for_jaccard(passage).split()),
            }
            video_passages.append(item)
            seq_items.append(item)
        if seq_items:
            video_by_seq[seq] = seq_items

    code_passages: List[Dict[str, Any]] = []
    for ast_it in ast_chunks:
        seq = int(ast_it["seq"])
        scope = ast_it["code_scope"]
        ctx_code = ast_it["context_code"]
        raw_code_item = f"[Mã nguồn {ast_it['lang']} - {scope}]\n{ctx_code}"
        passage = truncate_rerank_text(raw_code_item, max_chars=600)
        if _contains_corrupted_asr_artifacts(passage):
            continue
        syms = ast_it["symbols"]
        sym_terms: List[str] = []
        for bucket in ("classes", "structs", "methods", "operators", "functions", "fields"):
            for s_name in syms.get(bucket, []):
                if s_name and s_name != "main" and s_name not in sym_terms:
                    sym_terms.append(s_name)
        les = les_by_seq.get(seq, {})
        l_concepts = _extract_lesson_concepts(les) if les else []
        code_passages.append({
            "kind": "code_ast",
            "seq": seq,
            "scope": scope,
            "concepts": (sym_terms + l_concepts)[:4],
            "kw_set": {c.lower() for c in (sym_terms + l_concepts)},
            "passage": passage,
            "tokens": set(norm_text_for_jaccard(passage).split()),
        })

    rows: List[Dict[str, Any]] = []
    seen_triplets: Set[Tuple[str, str, str]] = set()
    video_query_tpls = [
        "Cơ chế hoạt động và cách sử dụng {phrase} trong lập trình C++ diễn ra thế nào?",
        "Khi cài đặt {phrase} trong bài học C++, ta cần chú ý quy tắc kỹ thuật gì?",
        "Giải thích ý nghĩa và thao tác xử lý {phrase} được trình bày trong đoạn giảng?",
        "Phân tích ví dụ minh họa về {phrase} và luồng thực thi tương ứng trong C++?",
    ]

    n_vid = len(video_passages)
    for idx, vp in enumerate(video_passages):
        terms = vp["concepts"]
        if not terms:
            continue
        phrase = " kết hợp ".join(terms[:2]) if len(terms) >= 2 else terms[0]
        query = video_query_tpls[idx % len(video_query_tpls)].format(phrase=phrase)
        if not _is_clean_text(query, heldout_norms, heldout_list):
            continue

        q_tokens = set(norm_text_for_jaccard(query).split())
        pos_overlap = len(q_tokens & vp["tokens"])
        if pos_overlap == 0:
            continue

        # 1. Thử ghép Intra-Lesson Hard Negative (cùng video, cách >= 90s, neg_overlap <= pos_overlap - 1)
        same_lesson_cands = video_by_seq.get(vp["seq"], [])
        intra_neg: Optional[Dict[str, Any]] = None
        for cand in same_lesson_cands:
            if abs(int(cand["sec"]) - int(vp["sec"])) < 90:
                continue
            neg_ov = len(q_tokens & cand["tokens"])
            if neg_ov <= max(0, pos_overlap - 1) and cand["passage"] != vp["passage"]:
                intra_neg = cand
                break

        if intra_neg is not None and idx % 3 == 0:
            t_key = (query, vp["passage"], intra_neg["passage"])
            if t_key not in seen_triplets:
                seen_triplets.add(t_key)
                rows.append({
                    "lesson_seq": vp["seq"],
                    "query": query,
                    "pos_passage": vp["passage"],
                    "neg_passage": intra_neg["passage"],
                })

        # 2. Cross-Lesson Hard Negative
        cross_neg: Optional[Dict[str, Any]] = None
        for step in range(1, n_vid):
            cand = video_passages[(idx + max(7, n_vid // 3) + step) % n_vid]
            if cand["seq"] == vp["seq"] or (vp["kw_set"] & cand["kw_set"]):
                continue
            neg_ov = len(q_tokens & cand["tokens"])
            if neg_ov <= max(0, pos_overlap - 1):
                cross_neg = cand
                break
        if cross_neg is not None:
            t_key = (query, vp["passage"], cross_neg["passage"])
            if t_key not in seen_triplets:
                seen_triplets.add(t_key)
                rows.append({
                    "lesson_seq": vp["seq"],
                    "query": query,
                    "pos_passage": vp["passage"],
                    "neg_passage": cross_neg["passage"],
                })

    # 3. Code-AST Triplets (bảo đảm mô hình học cả định dạng `[Mã nguồn CPP - ...]`)
    code_query_tpls = [
        "Cú pháp cài đặt {scope_clean} với {phrase} trong mã nguồn C++ hoạt động ra sao?",
        "Phân tích cách định nghĩa {scope_clean} xử lý {phrase} trong đoạn code mẫu C++?",
    ]
    n_code = len(code_passages)
    for c_idx, cp in enumerate(code_passages):
        scope_clean = cp["scope"].replace("function_", "hàm ").replace("type_", "kiểu ").replace("_", " ")
        phrase = cp["concepts"][0] if cp["concepts"] else scope_clean
        q_code = code_query_tpls[c_idx % len(code_query_tpls)].format(scope_clean=scope_clean, phrase=phrase)
        if not _is_clean_text(q_code, heldout_norms, heldout_list):
            continue
        q_tokens = set(norm_text_for_jaccard(q_code).split())
        pos_ov = len(q_tokens & cp["tokens"])
        if pos_ov == 0:
            continue

        chosen_code_neg: Optional[Dict[str, Any]] = None
        for step in range(1, n_code):
            cand = code_passages[(c_idx + step) % n_code]
            if cand["seq"] != cp["seq"] and cand["scope"] != cp["scope"]:
                if len(q_tokens & cand["tokens"]) <= max(0, pos_ov - 1):
                    chosen_code_neg = cand
                    break
        if chosen_code_neg is None and n_vid > 0:
            for step in range(n_vid):
                cand_v = video_passages[(c_idx * 5 + step) % n_vid]
                if cand_v["seq"] != cp["seq"] and len(q_tokens & cand_v["tokens"]) <= pos_ov:
                    chosen_code_neg = cand_v
                    break

        if chosen_code_neg is not None:
            t_key = (q_code, cp["passage"], chosen_code_neg["passage"])
            if t_key not in seen_triplets:
                seen_triplets.add(t_key)
                rows.append({
                    "lesson_seq": cp["seq"],
                    "query": q_code,
                    "pos_passage": cp["passage"],
                    "neg_passage": chosen_code_neg["passage"],
                })

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def _truncate_clean_excerpt(text: str, max_chars: int = 340) -> str:
    """Cắt đoạn ngữ cảnh tại ranh giới câu/từ trọn vẹn <= max_chars, cấm tuyệt đối '...' hoặc '…'."""
    cleaned = sanitize_text(text).replace("...", ".").replace("…", ".")
    cleaned = " ".join(cleaned.split()).strip(" ,;:-")
    if len(cleaned) <= max_chars:
        return cleaned if cleaned.endswith((".", "?", "!")) else f"{cleaned}."

    window = cleaned[:max_chars]
    for sep in (". ", "? ", "! ", "; ", ", "):
        pos = window.rfind(sep)
        if pos >= max_chars // 2:
            sub = window[:pos].strip(" ,;:-.")
            return f"{sub}."
    sp = window.rfind(" ")
    sub = (window[:sp] if sp > 0 else window).strip(" ,;:-.")
    return f"{sub}."


def _sanitize_assistant_prose(text: str) -> str:
    """Đảm bảo 0% '...', 0% '!', 0% rò rỉ `#include` / `using namespace std` / `int main` / `cin >>` / `cout <<`."""
    cleaned = text.replace("...", ",").replace("…", ",").replace("!", ".")
    cleaned = cleaned.replace("using namespace std;", "khai báo không gian tên chuẩn std")
    cleaned = cleaned.replace("using namespace std", "khai báo không gian tên chuẩn std")
    cleaned = cleaned.replace("cin >>", "thao tác đọc luồng đầu vào").replace("cout <<", "thao tác ghi luồng đầu ra")
    cleaned = cleaned.replace("#include", "khai báo thư viện")
    cleaned = cleaned.replace("int main", "hàm điểm vào chương trình").replace("void main", "hàm điểm vào chương trình").replace("signed main", "hàm điểm vào chương trình")
    cleaned = cleaned.replace("return 0;", "lệnh kết thúc hàm")
    return cleaned


def build_qwen25_socratic_dataset(out_file: Path, heldout_norms: Set[str], heldout_list: Sequence[str]) -> int:
    lessons = _load_all_lessons()
    chunks_by_seq = _load_recleaned_chunks_by_seq()
    les_by_seq = {int(l["seq"]): l for l in lessons}
    diag_data = json.loads(COMPILER_MANIFEST_PATH.read_text(encoding="utf-8"))
    diagnostics = diag_data.get("diagnostics", [])

    concept_prompts = [
        "Làm sao nắm vững cơ chế vận hành bên dưới của {kw0} khi thiết kế khung thuật toán tự kiểm thử biên ạ? Nhờ thầy code hoàn chỉnh bài mẫu giúp em.",
        "Nguyên tắc phối hợp giữa {kw0} và {kw1} để đảm bảo tính bất biến trạng thái dữ liệu trong chương trình C++ diễn ra thế nào?",
        "Tại sao lúc cài đặt thao tác {kw0} em hay gặp sai lệch kết quả ở ca dữ liệu cực trị, quy trình tự dò vết từng bước là gì ạ?",
        "Ý nghĩa kỹ thuật cốt lõi của {kw0} giúp giảm thiểu trùng lặp mã nguồn so với cách xử lý thủ công ra sao, viết giúp em cả bài luôn được không?",
        "Luồng biến đổi trạng thái biến trung gian từ bước {kw0} sang bước {kw1} cần kiểm chứng điều kiện tiên quyết nào trước tiên ạ?",
        "Khi triển khai phần xử lý {kw0} trên tập dữ liệu kích thước lớn, ràng buộc an toàn bộ nhớ hoặc miền giá trị nào dễ bị bỏ sót nhất?",
        "Giữa thao tác khởi tạo {kw0} và bước cập nhật {kw1}, thứ tự thực hiện ảnh hưởng thế nào tới tính đúng đắn cuối cùng của thuật toán?",
        "Thầy phân tích giúp em bản chất hoạt động của {kw0} gắn với luồng điều khiển chương trình để em tự hoàn thiện khung mã giả nhé?",
        "Nếu giá trị biên đầu vào thay đổi đột ngột khi thực thi {kw0} thì bước kiểm tra hợp lệ trước {kw1} nên thiết kế theo hướng nào ạ?",
        "Quy tắc kiểm soát phạm vi biến và kiểu trả về khi kết hợp {kw0} cùng {kw1} trong mô-đun C++ được giải thích ra sao?",
        "Em đang tự phác thảo sơ đồ khối cho phần {kw0} nhưng còn lúng túng cách thiết lập trạng thái neo ban đầu trước khi qua {kw1}?",
        "Sai lầm tư duy phổ biến nhất của người mới khi ghép nối logic {kw0} với thao tác {kw1} là gì và cách tự đặt test nhỏ để phát hiện?",
        "Phương pháp chia nhỏ yêu cầu thành pha chuẩn bị dữ liệu {kw0} độc lập với pha tính toán {kw1} nên suy luận theo trình tự nào?",
        "Vì sao trình biên dịch C++ đòi hỏi tính tương thích chặt chẽ về kiểu khi truyền kết quả từ {kw0} sang biểu thức {kw1} vậy ạ?",
        "Nhờ trợ giảng gợi mở hướng phân tách trường hợp cơ sở và trường hợp tổng quát khi xử lý {kw0} kết hợp {kw1} trong bài thực hành?",
        "Mối quan hệ nhân quả giữa biểu diễn dữ liệu của {kw0} và chi phí thực thi thao tác {kw1} tác động tới hiệu năng chung thế nào?",
    ]

    assistant_openings = [
        "Bản chất cốt lõi của **{kw0}** nằm ở cách kiểm soát trạng thái dữ liệu và điều kiện thực thi trong **{subj}**.",
        "Nguyên lý hoạt động của **{kw0}** khi đặt cạnh **{kw1}** giúp chương trình duy trì tính nhất quán của dữ liệu.",
        "Điểm mấu chốt khi triển khai **{kw0}** là xác định chính xác phạm vi tác động và kiểu giá trị trước mỗi bước xử lý.",
        "Theo phương pháp Socratic, thay vì chép lời giải trọn vẹn, việc bóc tách cơ chế **{kw0}** sẽ giúp bạn tự chủ hoàn toàn thuật toán.",
        "Cơ chế vận hành của **{kw0}** trong **{subj}** xoay quanh quy tắc biến đổi dữ liệu đầu vào theo từng bước xác định.",
        "Sai sót thường gặp nhất với **{kw0}** xuất phát từ việc chưa kiểm tra kỹ điều kiện biên trước khi kết hợp cùng **{kw1}**.",
        "Vai trò kỹ thuật của **{kw0}** là thiết lập cấu trúc xử lý tường minh, tránh trùng lặp logic khi thao tác với **{kw1}**.",
        "Luồng xử lý của **{kw0}** đòi hỏi trạng thái khởi tạo ban đầu phải khớp chặt chẽ với miền giá trị của **{kw1}**.",
        "Khái niệm **{kw0}** được xây dựng nhằm tối ưu hóa thao tác truy xuất và cập nhật dữ liệu trong **{subj}**.",
        "Quy tắc cú pháp áp dụng cho **{kw0}** bảo đảm trình biên dịch kiểm soát an toàn vùng nhớ và kiểu của **{kw1}**.",
        "Trọng tâm phân tích **{kw0}** bắt đầu từ việc theo dõi sự thay đổi của biến trạng thái sau mỗi thao tác lên **{kw1}**.",
        "Để tự cài đặt vững vàng **{kw0}**, trước hết cần phân biệt rõ đầu vào, điều kiện kiểm tra và hiệu ứng lên **{kw1}**.",
        "Mối liên kết giữa **{kw0}** và **{kw1}** trong **{subj}** quyết định trực tiếp độ chính xác ở các ca kiểm thử biên.",
        "Tư duy thiết kế cho phần **{kw0}** cần đi từ mô hình hóa dữ liệu sang kiểm chứng từng bước biến đổi của **{kw1}**.",
        "Đặc trưng quan trọng của **{kw0}** là bảo toàn bất biến dữ liệu trong suốt quá trình tương tác với **{kw1}**.",
        "Hướng tiếp cận chuẩn cho **{kw0}** là chia nhỏ yêu cầu thành bước khởi tạo và bước cập nhật trạng thái **{kw1}**.",
    ]

    socratic_questions = [
        "Theo bạn, nếu dữ liệu đầu vào rơi vào trường hợp biên nhỏ nhất hoặc rỗng thì trạng thái của **{kw0}** sẽ thay đổi ra sao?",
        "Trước khi chuyển sang bước xử lý **{kw1}**, điều kiện kiểm tra nào trên **{kw0}** cần được đảm bảo đúng trước tiên?",
        "Nếu ta đổi thứ tự cập nhật giữa **{kw0}** và **{kw1}** trong luồng thuật toán trên thì kết quả đầu ra sẽ bị lệch ở bước nào?",
        "Giả sử giá trị ban đầu của **{kw0}** chưa được khởi tạo tường minh thì phép toán tiếp theo với **{kw1}** sẽ gặp rủi ro gì?",
        "Dựa trên cơ chế vừa phân tích, bạn dự đoán biểu thức điều kiện của **{kw0}** sẽ trả về giá trị gì ở lượt kiểm tra cuối cùng?",
        "Khi kích thước dữ liệu tăng lên gấp nhiều lần, thao tác nào giữa **{kw0}** và **{kw1}** sẽ quyết định số bước thực hiện?",
    ]

    rows: List[Dict[str, Any]] = []

    def _get_lesson_chapters(seq: int, les: Dict[str, Any]) -> List[Dict[str, Any]]:
        rec_entry = chunks_by_seq.get(seq)
        if rec_entry and rec_entry[1]:
            rec_chunks = rec_entry[1]
            step = max(1, len(rec_chunks) // 3)
            return [
                {
                    "sec": int(ch["start_sec"]),
                    "label": str(ch["start_label"]),
                    "summary": str(ch.get("raw_text") or ch.get("text") or "").strip(),
                }
                for ch in rec_chunks[::step][:3]
            ]
        return [
            {
                "sec": int(ch["sec"]),
                "label": str(ch["label"]),
                "summary": str(ch.get("summary", "")).strip(),
            }
            for ch in les.get("video_chapters", [])
            if ch.get("sec") is not None and ch.get("label") and str(ch.get("summary", "")).strip()
        ]

    # Phủ đầy đủ 100% (83/83) bài học trong giáo trình
    for idx, les in enumerate(lessons):
        seq = int(les.get("seq", 0))
        subj = _clean_lesson_subject(str(les.get("title", f"Bài {seq}")))
        concepts = _extract_lesson_concepts(les)
        chapters = _get_lesson_chapters(seq, les)
        if not chapters:
            continue

        lesson_emitted = 0
        for ch_idx, ch in enumerate(chapters[:3]):
            sec = int(ch["sec"])
            lbl = str(ch["label"])
            clean_excerpt = _truncate_clean_excerpt(ch["summary"], max_chars=340)
            kw0 = concepts[ch_idx % len(concepts)]
            kw1 = concepts[(ch_idx + 1) % len(concepts)]

            # Xoay vòng mẫu câu hỏi nếu chẳng may trùng tập held-out để không mất độ phủ 83/83 bài
            chosen_user_q: Optional[str] = None
            for attempt in range(len(concept_prompts)):
                tpl = concept_prompts[(idx * 3 + ch_idx + attempt) % len(concept_prompts)]
                cand_q = tpl.format(subj=subj, kw0=kw0, kw1=kw1)
                if _is_clean_text(cand_q, heldout_norms, heldout_list):
                    chosen_user_q = cand_q
                    break
            if chosen_user_q is None:
                continue

            user_content = (
                f"[CÂU HỎI THẮC MẮC CỦA HỌC VIÊN]\n"
                f"{chosen_user_q}\n\n"
                f"[NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC]\n"
                f"Nguồn Bài {seq} (mốc <timestamp sec=\"{sec}\">{lbl}</timestamp>): {clean_excerpt}"
            )

            open_line = assistant_openings[(idx * 2 + ch_idx) % len(assistant_openings)].format(
                subj=subj, kw0=kw0, kw1=kw1
            )
            q_line = socratic_questions[(idx + ch_idx) % len(socratic_questions)].format(
                subj=subj, kw0=kw0, kw1=kw1
            )
            prose = (
                f"{open_line}\n\n"
                f"Trong nội dung bài giảng, thao tác trọng tâm cần nắm là phân tách rõ điều kiện kiểm tra của **{kw0}** "
                f"và bước cập nhật trạng thái gắn với **{kw1}** theo khung mã giả từng bước thay vì viết gộp thiếu kiểm soát.\n\n"
                f"{q_line}"
            )
            prose = _sanitize_assistant_prose(prose).rstrip()
            if not prose.endswith("?"):
                prose = prose.rstrip(".! ") + "?"

            assistant_content = (
                f"{prose}\n\n"
                f"📍 **Mốc video bài giảng:** <timestamp sec=\"{sec}\">{lbl}</timestamp>"
            )

            rows.append({
                "lesson_seq": seq,
                "messages": [
                    {"role": "system", "content": SOCRATIC_GROUNDED_PROMPT},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": assistant_content},
                ],
            })
            lesson_emitted += 1

        if lesson_emitted == 0:
            raise RuntimeError(f"Lesson {seq} failed to emit any clean Qwen2.5 Socratic sample!")

    # Bổ sung các tình huống chẩn đoán lỗi trình biên dịch khớp đúng chủ đề bài học (0% phép chia dư %)
    dbg_openings = [
        "Thông báo biên dịch `{err_pat}` phản ánh trực tiếp nguyên tắc: **{ped}**.",
        "Trình biên dịch dừng lại với `{err_pat}` vì phát hiện vi phạm về **{ped}**.",
        "Bản chất của cảnh báo lỗi `{err_pat}` nằm ở quy tắc cú pháp: **{ped}**.",
    ]
    dbg_questions = [
        "Khi rà soát lại biểu thức tại vị trí báo lỗi `{err_pat}`, bạn thấy kiểu dữ liệu hoặc ký hiệu kết thúc lệnh nào đang bị lệch?",
        "Đối chiếu quy tắc trên với đoạn mã đang viết, bạn nhận ra biến hoặc phạm vi khối lệnh nào cần khai báo lại cho khớp?",
    ]

    for d_idx, diag in enumerate(diagnostics):
        cat = str(diag.get("category", ""))
        target_seqs = DIAGNOSTIC_CATEGORY_LESSON_MAP.get(cat, ())
        err_pat = str((diag.get("patterns") or ["compilation error"])[0])
        ped = str(diag.get("pedagogical_vietnamese") or "").strip(" .!")
        for s_offset, seq in enumerate(target_seqs):
            les = les_by_seq.get(seq)
            if not les:
                continue
            chapters = _get_lesson_chapters(seq, les)
            if not chapters:
                continue
            ch_d = chapters[min(1, len(chapters) - 1)]
            sec_d, lbl_d = int(ch_d["sec"]), str(ch_d["label"])
            clean_excerpt = _truncate_clean_excerpt(ch_d["summary"], max_chars=340)
            subj = _clean_lesson_subject(str(les.get("title", f"Bài {seq}")))

            user_dbg = (
                f"Khi tự thực hành phần {subj}, trình biên dịch báo lỗi `{err_pat}` thì nguyên nhân gốc rễ do đâu ạ?"
            )
            if not _is_clean_text(user_dbg, heldout_norms, heldout_list):
                continue

            user_content = (
                f"[CÂU HỎI THẮC MẮC CỦA HỌC VIÊN]\n"
                f"{user_dbg}\n\n"
                f"[NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC]\n"
                f"Nguồn Bài {seq} (mốc <timestamp sec=\"{sec_d}\">{lbl_d}</timestamp>): {clean_excerpt}"
            )
            open_d = dbg_openings[(d_idx + s_offset) % len(dbg_openings)].format(err_pat=err_pat, ped=ped)
            q_d = dbg_questions[(d_idx + s_offset) % len(dbg_questions)].format(err_pat=err_pat)
            prose_d = _sanitize_assistant_prose(
                f"{open_d}\n\n"
                f"Để khắc phục triệt để mà không sửa mò, bạn cần kiểm tra dòng đầu tiên trình biên dịch chỉ ra trong phần **{subj}** "
                f"và đối chiếu lại chữ ký kiểu dữ liệu cũng như phạm vi khai báo tương ứng.\n\n"
                f"{q_d}"
            ).rstrip()
            if not prose_d.endswith("?"):
                prose_d = prose_d.rstrip(".! ") + "?"

            assistant_dbg = (
                f"{prose_d}\n\n"
                f"📍 **Mốc video bài giảng:** <timestamp sec=\"{sec_d}\">{lbl_d}</timestamp>"
            )
            rows.append({
                "lesson_seq": seq,
                "messages": [
                    {"role": "system", "content": SOCRATIC_GROUNDED_PROMPT},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": assistant_dbg},
                ],
            })

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def _get_authenticated_kaggle_api(username_arg: str | None, *, dry_run: bool = False) -> Tuple[Any | None, str | None]:
    if dry_run:
        local_user = username_arg or os.environ.get("KAGGLE_USERNAME")
        if not local_user:
            k_json = Path.home() / ".kaggle" / "kaggle.json"
            if k_json.exists():
                try:
                    local_user = json.loads(k_json.read_text(encoding="utf-8")).get("username")
                except Exception:
                    local_user = None
        return None, local_user

    has_kaggle_pkg = importlib.util.find_spec("kaggle") is not None
    if not has_kaggle_pkg:
        return None, username_arg or os.environ.get("KAGGLE_USERNAME")

    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    try:
        api.authenticate()
    except SystemExit:
        return None, username_arg or os.environ.get("KAGGLE_USERNAME")
    except Exception:
        return None, username_arg or os.environ.get("KAGGLE_USERNAME")

    username = (
        username_arg
        or os.environ.get("KAGGLE_USERNAME")
        or (api.config_values.get("username") if getattr(api, "config_values", None) else None)
    )
    if not getattr(api, "_authenticated", False):
        return None, username
    return api, username


def _wait_dataset_ready(api: Any, dataset_slug: str, timeout_sec: int = 180) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            status = str(api.dataset_status(dataset_slug) or "").lower()
            if "ready" in status:
                print(f"[Kaggle SDK] Dataset {dataset_slug} đã sẵn sàng ({status}).")
                return
            if "error" in status:
                raise RuntimeError(f"Dataset {dataset_slug} bị lỗi xử lý trên Kaggle: {status}")
        except Exception:
            pass
        time.sleep(5)
    print(f"[Kaggle SDK] Cảnh báo: quá {timeout_sec}s chờ status ready cho {dataset_slug}, tiếp tục thử đẩy kernel...")


def _backup_dir_if_exists(target_dir: Path) -> None:
    if target_dir.exists() and any(target_dir.iterdir()):
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup = target_dir.parent / f"{target_dir.name}.bak_{ts}"
        shutil.copytree(target_dir, backup)
        print(f"[Backup] Đã sao lưu model cũ -> {backup}")


def prepare_and_maybe_run_task(task: str, args: argparse.Namespace) -> None:
    heldout_norms, heldout_list = _load_heldout_norms()
    task_bundle = BUNDLE_ROOT / task
    dataset_dir = task_bundle / "dataset"
    kernel_dir = task_bundle / "kernel"
    if task_bundle.exists():
        shutil.rmtree(task_bundle)
    dataset_dir.mkdir(parents=True, exist_ok=True)
    kernel_dir.mkdir(parents=True, exist_ok=True)

    builders = {
        "mdeberta_nli": ("mdeberta_nli_train.jsonl", "train_mdeberta_nli.py", build_mdeberta_nli_dataset),
        "jina_reranker": ("jina_reranker_train.jsonl", "train_jina_reranker.py", build_jina_reranker_dataset),
        "qwen25_qlora": ("qwen25_socratic_train.jsonl", "train_qwen25_qlora.py", build_qwen25_socratic_dataset),
    }
    data_fname, script_fname, builder_fn = builders[task]
    n_samples = builder_fn(dataset_dir / data_fname, heldout_norms, heldout_list)
    print(f"\n[{task}] Đã đóng gói {n_samples} mẫu huấn luyện sạch (0% rò rỉ) -> {dataset_dir / data_fname}")

    api, kaggle_user = _get_authenticated_kaggle_api(args.username, dry_run=bool(args.dry_run))
    effective_user = kaggle_user or "<YOUR_KAGGLE_USERNAME>"
    slug_safe = task.replace("_", "-")
    ds_name = f"in-course-rag-{slug_safe}-data"
    kn_name = f"in-course-rag-{slug_safe}-ft"
    dataset_slug = f"{effective_user}/{ds_name}"
    kernel_slug = f"{effective_user}/{kn_name}"

    ds_meta = {
        "title": ds_name,
        "id": dataset_slug,
        "licenses": [{"name": "CC0-1.0"}],
    }
    (dataset_dir / "dataset-metadata.json").write_text(json.dumps(ds_meta, indent=2), encoding="utf-8")

    shutil.copy2(JOBS_DIR / script_fname, kernel_dir / script_fname)
    k_meta = {
        "id": kernel_slug,
        "title": kn_name,
        "code_file": script_fname,
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": True,
        "dataset_sources": [dataset_slug],
        "competition_sources": [],
        "kernel_sources": [],
    }
    (kernel_dir / "kernel-metadata.json").write_text(json.dumps(k_meta, indent=2), encoding="utf-8")
    print(f"[{task}] Đã tạo kernel bundle ({kernel_slug}) -> {kernel_dir}")
    print(f"[{task}] Đích download local -> {LOCAL_TARGETS[task]}")

    if not args.skip_validate:
        from scripts.validate_training_datasets import run_validation

        val_summary = run_validation(clean_in_place=True, with_e5_conflict=False, models=[task])
        model_res = val_summary["models"].get(task, {})
        print(f"[{task}] Preflight Dataset Gate: passed={model_res.get('passed')} | clean={model_res.get('total_clean')}")
        if not model_res.get("passed"):
            raise RuntimeError(f"Preflight Dataset Gate FAILED cho '{task}': {json.dumps(model_res, ensure_ascii=False)}")

    if args.dry_run:
        print(f"[{task}] Dry-run: chưa đẩy lên Kaggle (AuthReady={api is not None}, User={effective_user}).")
        return

    if api is None or not kaggle_user:
        raise RuntimeError(
            "Chưa đủ điều kiện chạy Kaggle từ xa.\n"
            "  1. Cài SDK chính thức: .\\.venv\\Scripts\\pip.exe install --upgrade kaggle six\n"
            f"  2. Đặt token `KGAT_...` tại: {Path.home() / '.kaggle' / 'access_token'} (hoặc biến môi trường KAGGLE_API_TOKEN)\n"
            "  Sau đó chạy lại lệnh không có --dry-run."
        )

    ds_exists = False
    try:
        st = api.dataset_status(dataset_slug)
        ds_exists = bool(st)
    except Exception:
        ds_exists = False

    if ds_exists:
        print(f"[{task}] Đang cập nhật dataset trên Kaggle: {dataset_slug}...")
        api.dataset_create_version(
            folder=str(dataset_dir),
            version_notes=f"Update {task} decontaminated training dataset",
            dir_mode="zip",
        )
    else:
        print(f"[{task}] Đang tạo dataset mới trên Kaggle: {dataset_slug}...")
        api.dataset_create_new(
            folder=str(dataset_dir),
            public=False,
            dir_mode="zip",
        )
    _wait_dataset_ready(api, dataset_slug)

    print(f"[{task}] Đang đẩy GPU Kernel lên Kaggle: {kernel_slug} (enable_gpu=True)...")
    save_resp = api.kernels_push(folder=str(kernel_dir))
    print(f"[{task}] Kaggle Kernel URL: {getattr(save_resp, 'url', kernel_slug)}")
    if args.no_wait:
        print(f"[{task}] Đã đẩy Kernel {kernel_slug} lên Kaggle (--no-wait).")
        return

    print(f"[{task}] Đang chờ Kaggle GPU thực thi {kernel_slug} (poll mỗi {args.poll_interval}s)...")
    while True:
        st_resp = api.kernels_status(kernel_slug)
        status_str = str(getattr(st_resp, "status", st_resp) or "").lower()
        fail_msg = getattr(st_resp, "failure_message", None) or getattr(st_resp, "failureMessage", None)
        print(f"[{task}] [{time.strftime('%H:%M:%S')}] Status={status_str}" + (f" | msg={fail_msg}" if fail_msg else ""))
        if "complete" in status_str:
            break
        if "error" in status_str or "cancel" in status_str:
            raise RuntimeError(f"Kaggle kernel {kernel_slug} dừng với trạng thái lỗi ({status_str}): {fail_msg}")
        time.sleep(args.poll_interval)

    staging_dl = task_bundle / "downloaded_output"
    if staging_dl.exists():
        shutil.rmtree(staging_dl)
    staging_dl.mkdir(parents=True, exist_ok=True)
    out_files, _ = api.kernels_output(kernel=kernel_slug, path=str(staging_dl), force=True, quiet=False)
    print(f"[{task}] Đã tải về {len(out_files)} file(s) vào {staging_dl}")

    target_dir = LOCAL_TARGETS[task]
    _backup_dir_if_exists(target_dir)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    bundle_zip = staging_dl / "model_bundle.zip"
    if bundle_zip.exists():
        with zipfile.ZipFile(bundle_zip, "r") as zf:
            zf.extractall(target_dir)
        print(f"[{task}] Đã tự động tải và giải nén model vào: {target_dir}")
    else:
        shutil.copytree(staging_dl, target_dir, dirs_exist_ok=True)
        print(f"[{task}] Đã tự động copy toàn bộ output Kaggle vào: {target_dir}")

    if task == "jina_reranker":
        int8_target = PROJECT_ROOT / "data" / "models" / "jina-reranker-v2-int8"
        _backup_dir_if_exists(int8_target)
        print("[jina_reranker] Đang tự động quantize bản FP32 vừa tải -> data/models/jina-reranker-v2-int8/...")
        subprocess.check_call([
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "quantize_reranker_int8.py"),
            "--source-dir",
            str(target_dir),
        ])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automated Kaggle GPU Fine-Tuning + Auto-Download Runner")
    parser.add_argument("--task", choices=["mdeberta_nli", "jina_reranker", "qwen25_qlora", "all"], default="all")
    parser.add_argument("--username", type=str, default=None, help="Kaggle username (mặc định đọc từ ~/.kaggle/kaggle.json)")
    parser.add_argument("--poll-interval", type=int, default=45, help="Số giây poll trạng thái Kaggle kernel")
    parser.add_argument("--no-wait", action="store_true", help="Chỉ push job lên Kaggle, không chờ download")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ đóng gói dataset + metadata kiểm tra cục bộ")
    parser.add_argument("--skip-validate", action="store_true", help="Bỏ qua Preflight Dataset Gate (không khuyến khích)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tasks = ["mdeberta_nli", "jina_reranker", "qwen25_qlora"] if args.task == "all" else [args.task]
    for t in tasks:
        prepare_and_maybe_run_task(t, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
