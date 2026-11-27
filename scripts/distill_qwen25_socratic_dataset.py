#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Teacher Distillation SFT v2 Dataset Builder (Gemini 3.5 / 3.1 Flash-Lite)
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Sinh tập dữ liệu Socratic SFT chất lượng cao cho Qwen2.5-Coder-7B-Instruct trên đủ 83/83 bài học:
- Đọc ngữ cảnh transcript sạch + đoạn AST Code tham khảo (tước #include / int main()).
- Dùng Teacher LLM (ưu tiên `gemini-3.5-flash-lite`, fallback `gemini-3.1-flash-lite`) với xoay vòng
  đa API key bất đồng bộ (asyncio) qua endpoint OpenAI-compatible của Google AI Studio.
- Kiểm định từng mẫu ngay lúc sinh bằng Spec 005 Hardened Quality Gates:
  0% rò rỉ held-out, 0% `#include`/`int main()`, 0% ngoại ngữ Trung/Tây Ban Nha,
  0% dấu `...`, 100% khớp `<timestamp>` Whitelist của từng bài học, chuẩn kết thúc Socratic `?`.
"""

import argparse
import asyncio
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import httpx
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.agent.prompts import SOCRATIC_GROUNDED_PROMPT  # noqa: E402
from scripts.canonicalize_transcripts_ast import (  # noqa: E402
    ASR_EMPTY_FALLBACK_TEXT,
    VIETNAMESE_NFC_LETTERS,
    _contains_corrupted_asr_artifacts,
)
from scripts.e2e_matrix_harness import detect_foreign_language_leak  # noqa: E402
from scripts.validate_training_datasets import (  # noqa: E402
    FULL_CODE_LEAK_PATTERNS,
    INTENT_MANIFEST_PATH,
    LESSONS_MANIFEST_PATH,
    check_decontamination,
    load_heldout_queries,
    load_valid_lesson_timestamps,
    _check_socratic_assistant_structure,
    _normalize_opening_prefix,
)

GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
TEACHER_MODELS: Tuple[str, ...] = (
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
)
DEFAULT_OUT_PATH = PROJECT_ROOT / "data" / "training" / "qwen25_socratic_distilled_v2.jsonl"

ARCHETYPES: Tuple[Dict[str, str], ...] = (
    {
        "id": "concept_grounding",
        "name": "Giải thích khái niệm bám sát bài giảng",
        "instruction": (
            "Sinh viên hỏi một thắc mắc tự nhiên, cụ thể về bản chất kiến thức C++ hoặc khái niệm "
            "được nhắc trực tiếp trong đoạn bài giảng này (ví dụ: tại sao, cơ chế hoạt động, sự khác nhau). "
            "Trợ giảng giải thích trực diện, chính xác kỹ thuật C++ bằng 2-3 ý cô đọng bám sát ngữ cảnh, "
            "không viết khung chữ mẫu sáo rỗng, và kết thúc bằng 1 câu hỏi gợi mở Socratic cụ thể (?)."
        ),
    },
    {
        "id": "socratic_debug",
        "name": "Chẩn đoán lỗi tư duy / code snippet ngắn",
        "instruction": (
            "Sinh viên nêu một lỗi logic, lỗi biên dịch hoặc 1-2 dòng code C++ ngắn đang viết sai "
            "liên quan chủ đề bài này và hỏi vì sao sai / tại sao kết quả bị lệch. "
            "Trợ giảng chỉ ra chính xác nguyên nhân gốc rễ trong tư duy hoặc cú pháp C++ đó "
            "(tuyệt đối KHÔNG viết lại chương trình đầy đủ có #include hay int main()), hướng dẫn cách "
            "tự kiểm tra, và kết thúc bằng 1 câu hỏi Socratic dẫn dắt học viên tự sửa (?)."
        ),
    },
    {
        "id": "soft_refusal_scaffolding",
        "name": "Từ chối mềm xin full code + gợi ý mã giả 2-3 dòng",
        "instruction": (
            "Sinh viên năn nỉ hoặc yêu cầu trợ giảng viết luôn toàn bộ chương trình/hàm C++ hoàn chỉnh "
            "để nộp bài liên quan tới đoạn bài giảng này. "
            "Trợ giảng từ chối nhẹ nhàng theo tinh thần Socratic (không giảng đạo dài dòng), giải thích luồng "
            "xử lý cốt lõi và đưa tối đa 1 khung mã giả hoặc skeleton 2-3 dòng kèm `// TODO` "
            "(CẤM TUYỆT ĐỐI `#include`, `int main(`, `void main(`), cuối cùng đặt 1 câu hỏi Socratic (?)."
        ),
    },
    {
        "id": "elaboration_pitfall",
        "name": "Làm rõ phần khó hiểu bằng ví dụ nhỏ cụ thể",
        "instruction": (
            "Sinh viên nói đoạn kiến thức này hơi khó hình dung hoặc hỏi lưu ý dễ sai kèm ví dụ nhỏ. "
            "Trợ giảng minh họa bằng một ví dụ số/biến cụ thể nhỏ (3-4 giá trị rõ ràng, không dùng code hoàn chỉnh) "
            "bám sát nội dung bài giảng, chỉ ra 1 lỗi biên dễ mắc và hỏi lại học viên dự đoán kết quả (?)."
        ),
    },
    {
        "id": "summary_overview",
        "name": "Tóm tắt trọng tâm đoạn video bài học",
        "instruction": (
            "Sinh viên hỏi tóm tắt ngắn gọn ý chính hoặc điểm mấu chốt cần nhớ của phần bài học này. "
            "Trợ giảng tổng hợp 2-3 gạch đầu dòng ngắn gọn, chính xác nội dung C++ trong đoạn bài giảng "
            "(không chung chung), và kết thúc bằng 1 câu hỏi kiểm tra khả năng vận dụng (?)."
        ),
    },
)


def _collect_gemini_keys() -> List[str]:
    env_file = PROJECT_ROOT / ".env"
    file_env = dotenv_values(env_file) if env_file.exists() else {}
    merged = {**file_env, **os.environ}
    seen: Set[str] = set()
    keys: List[str] = []
    raw_multi = str(merged.get("GEMINI_API_KEYS") or "")
    raw_single = str(merged.get("GEMINI_API_KEY") or "")
    for part in raw_multi.split(",") + [raw_single]:
        k = part.strip().strip('"').strip("'")
        if k and k not in seen:
            seen.add(k)
            keys.append(k)
    return keys


def _load_lessons() -> List[Dict[str, Any]]:
    data = json.loads(LESSONS_MANIFEST_PATH.read_text(encoding="utf-8"))
    lessons: List[Dict[str, Any]] = []
    for cid, cval in (data.get("courses") or {}).items():
        items = cval.get("lessons", cval) if isinstance(cval, dict) else cval
        for item in items:
            seq = item.get("seq") or item.get("lesson_seq")
            if seq is None:
                continue
            lessons.append(
                {
                    "seq": int(seq),
                    "course_id": cid,
                    "title": str(item.get("title") or f"Bài {seq}"),
                    "keywords": item.get("keywords") or [],
                    "video_chapters": item.get("video_chapters") or [],
                }
            )
    lessons.sort(key=lambda x: x["seq"])
    return lessons


def _load_clean_transcript_segments(
    lessons: Sequence[Dict[str, Any]],
    valid_ts_by_lesson: Dict[int, Dict[int, str]],
) -> Dict[int, List[Dict[str, Any]]]:
    by_seq: Dict[int, List[Dict[str, Any]]] = {}
    transcripts_dir = PROJECT_ROOT / "data" / "transcripts"
    if transcripts_dir.exists():
        for p in sorted(transcripts_dir.rglob("*_chunks.json")):
            digits = "".join(ch for ch in p.stem.split("_")[0] if ch.isdigit())
            if not digits:
                continue
            seq = int(digits)
            valid_map = valid_ts_by_lesson.get(seq, {})
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                items = raw.get("chunks", raw) if isinstance(raw, dict) else raw
            except Exception:
                continue
            good: List[Dict[str, Any]] = []
            for ch in items or []:
                if not isinstance(ch, dict):
                    continue
                sec = ch.get("start_sec")
                lbl = str(ch.get("start_label") or "")
                txt = (ch.get("raw_text") or ch.get("text") or "").strip()
                if (
                    sec is None
                    or int(sec) not in valid_map
                    or valid_map[int(sec)] != lbl
                    or len(txt) < 40
                    or ASR_EMPTY_FALLBACK_TEXT in txt
                    or _contains_corrupted_asr_artifacts(txt)
                    or sum(1 for c in txt if c in VIETNAMESE_NFC_LETTERS) < 5
                ):
                    continue
                good.append({"sec": int(sec), "label": lbl, "summary": txt})
            if good:
                by_seq[seq] = good

    for les in lessons:
        seq = int(les["seq"])
        valid_map = valid_ts_by_lesson.get(seq, {})
        existing = by_seq.get(seq, [])
        seen_secs = {int(x["sec"]) for x in existing}
        for ch in les.get("video_chapters") or []:
            sec = ch.get("sec")
            lbl = str(ch.get("label") or "")
            summ = str(ch.get("summary") or "").strip()
            if (
                sec is not None
                and int(sec) in valid_map
                and valid_map[int(sec)] == lbl
                and int(sec) not in seen_secs
                and summ
            ):
                existing.append({"sec": int(sec), "label": lbl, "summary": summ})
                seen_secs.add(int(sec))
        by_seq[seq] = existing
    return by_seq


def _load_sanitized_code_snippets() -> Dict[int, str]:
    snippets: Dict[int, str] = {}
    sample_dir = PROJECT_ROOT / "data" / "sample_codes"
    if not sample_dir.exists():
        return snippets
    for p in sorted(sample_dir.rglob("*_ast_chunks.json")):
        digits = "".join(ch for ch in p.stem.split("_")[0] if ch.isdigit())
        if not digits:
            continue
        seq = int(digits)
        try:
            arr = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for item in arr if isinstance(arr, list) else []:
            if not isinstance(item, dict):
                continue
            scope = str(item.get("code_scope") or "").strip()
            if not scope or scope in ("header_preamble", "function_anonymous", "function_main"):
                continue
            code = str(item.get("context_code") or item.get("raw_text") or "").strip()
            filtered_lines = [
                ln
                for ln in code.splitlines()
                if not ln.strip().lower().startswith(("#include", "using namespace"))
            ]
            body = "\n".join(filtered_lines).strip()
            if len(body) >= 25 and "#include" not in body.lower() and "int main" not in body.lower():
                snippets[seq] = body[:220]
                break
    return snippets


def _truncate_clean(text: str, max_chars: int = 340) -> str:
    clean = " ".join((text or "").replace("...", " ").replace("…", " ").split())
    if len(clean) <= max_chars:
        return clean
    cut = clean[: max_chars - 1].rsplit(" ", 1)[0].rstrip(",;:. ")
    return cut


def _pick_spaced_segments(segments: Sequence[Dict[str, Any]], k: int, offset: int = 0) -> List[Dict[str, Any]]:
    if not segments:
        return []
    n = len(segments)
    chosen: List[Dict[str, Any]] = []
    for i in range(k):
        idx = (offset + (i * max(1, n // max(1, k)))) % n
        chosen.append(segments[idx])
    return chosen


def _normalize_generated_prose(raw_prose: str) -> str:
    txt = (raw_prose or "").strip()
    footer_idx = txt.find("📍")
    if footer_idx != -1:
        txt = txt[:footer_idx].strip()
    ts_idx = txt.lower().find("<timestamp")
    if ts_idx != -1 and txt.lower().endswith("</timestamp>"):
        txt = txt[:ts_idx].strip()
    txt = txt.replace("...", ".").replace("…", ".")
    lines = [ln.rstrip() for ln in txt.splitlines() if ln.strip()]
    txt = "\n\n".join(lines).strip()
    if txt and not txt.endswith("?"):
        txt = txt.rstrip(".! ") + "?"
    return txt


def _load_forbidden_closing_prefixes() -> List[str]:
    manifest = json.loads(INTENT_MANIFEST_PATH.read_text(encoding="utf-8"))
    return [
        str(p).strip().lower()
        for p in manifest.get("forbidden_closing_prefixes", [])
        if str(p).strip()
    ]


class KeyPool:
    def __init__(self, keys: Sequence[str]) -> None:
        self._keys = list(keys)
        self._idx = 0
        self._lock = asyncio.Lock()

    async def next_key(self) -> str:
        async with self._lock:
            k = self._keys[self._idx % len(self._keys)]
            self._idx += 1
            return k


def _validate_candidate(
    *,
    seq: int,
    sec: int,
    lbl: str,
    clean_excerpt: str,
    student_q: str,
    prose: str,
    heldout_norms: Set[str],
    heldout_queries: Sequence[str],
    valid_ts_by_lesson: Dict[int, Dict[int, str]],
    forbidden_closing_prefixes: Sequence[str],
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    sq = " ".join((student_q or "").replace("...", " ").replace("…", " ").split())
    if len(sq) < 15 or len(sq) > 260:
        return False, f"student_q_len={len(sq)}", None

    ok_decontam, reason = check_decontamination(
        sq,
        heldout_norms,
        heldout_queries,
        max_jaccard=0.65,
        max_containment=0.85,
    )
    if not ok_decontam:
        return False, f"decontam:{reason}", None

    clean_prose = _normalize_generated_prose(prose)
    if len(clean_prose) < 110:
        return False, f"prose_too_short={len(clean_prose)}", None
    if clean_prose.count("?") > 2:
        return False, "too_many_question_marks", None
    if detect_foreign_language_leak(clean_prose):
        return False, "foreign_language_leak", None

    low_prose = clean_prose.lower()
    if any(pat in low_prose for pat in FULL_CODE_LEAK_PATTERNS):
        return False, "full_code_leak", None

    user_content = (
        f"[CÂU HỎI THẮC MẮC CỦA HỌC VIÊN]\n"
        f"{sq}\n\n"
        f"[NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC]\n"
        f"Nguồn Bài {seq} (mốc <timestamp sec=\"{sec}\">{lbl}</timestamp>): {clean_excerpt}"
    )
    assistant_content = (
        f"{clean_prose}\n\n"
        f"📍 **Mốc video bài giảng:** <timestamp sec=\"{sec}\">{lbl}</timestamp>"
    )

    if (len(user_content) + len(assistant_content)) > 2000:
        return False, f"over_len={len(user_content) + len(assistant_content)}", None
    if "..." in assistant_content or "…" in assistant_content:
        return False, "ellipsis_detected", None
    if valid_ts_by_lesson.get(seq, {}).get(sec) != lbl:
        return False, "invalid_timestamp_whitelist", None
    if not _check_socratic_assistant_structure(assistant_content, forbidden_closing_prefixes):
        return False, "socratic_structure_failed", None

    row = {
        "lesson_seq": seq,
        "archetype": "",
        "messages": [
            {"role": "system", "content": SOCRATIC_GROUNDED_PROMPT},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ],
    }
    return True, "ok", row


async def distill_single_slot(
    *,
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
    key_pool: KeyPool,
    lesson: Dict[str, Any],
    seg: Dict[str, Any],
    archetype: Dict[str, str],
    archetype_idx: int,
    ast_snippet: str,
    heldout_norms: Set[str],
    heldout_queries: Sequence[str],
    valid_ts_by_lesson: Dict[int, Dict[int, str]],
    forbidden_closing_prefixes: Sequence[str],
    stats: Dict[str, int],
) -> Optional[Dict[str, Any]]:
    seq = int(lesson["seq"])
    sec = int(seg["sec"])
    lbl = str(seg["label"])
    clean_excerpt = _truncate_clean(seg["summary"], max_chars=330)
    kws = ", ".join(str(k) for k in (lesson.get("keywords") or [])[:6])
    code_hint = f"\nCode mẫu trích từ AST bài này (tham khảo):\n{ast_snippet}" if ast_snippet else ""

    sys_msg = (
        "Bạn là Chuyên gia Thiết kế Dữ liệu Sư phạm Socratic cho khóa học C++.\n"
        "Hãy tạo ĐÚNG 1 cặp hội thoại JSON (`student_question`, `assistant_prose`) tiếng Việt tự nhiên, "
        "chính xác về C++ và bám sát ngữ cảnh bài học bên dưới.\n"
        "QUY TẮC BẮT BUỘC:\n"
        "1. `assistant_prose` KHÔNG ĐƯỢC bắt đầu bằng 'Chào bạn', 'Xin chào', 'Chào em'.\n"
        "2. KHÔNG BAO GIỜ viết `#include`, `int main(`, `void main(`, hay lời giải C++ hoàn chỉnh; "
        "chỉ được dùng tối đa 2-3 dòng mã giả hoặc skeleton có `// TODO` nếu cần.\n"
        "3. KHÔNG dùng dấu ba chấm `...` hoặc `…`; KHÔNG dùng chữ Hán hay dấu `¿`/`¡`.\n"
        "4. Kết thúc `assistant_prose` bằng ĐÚNG 1 câu hỏi gợi mở Socratic cụ thể kết thúc bằng `?` "
        "(CẤM câu sáo rỗng 'Bạn đã hiểu chưa?', 'Chúc bạn học tốt', 'Nếu còn thắc mắc...').\n"
        "5. KHÔNG tự thêm thẻ `<timestamp>` hay dòng `📍 **Mốc video bài giảng:**` vào `assistant_prose` "
        "(hệ thống sẽ tự gắn mốc chuẩn xác sau). Độ dài `assistant_prose` từ 220 đến 650 ký tự.\n"
        "6. Đa dạng hóa câu mở đầu theo đúng vấn đề C++ đang hỏi, TUYỆT ĐỐI tránh lặp khuôn sáo."
    )
    user_msg = (
        f"Bài {seq} [{lesson['course_id']}]: {lesson['title']}\n"
        f"Từ khóa: {kws or 'C++'}\n"
        f"Trích đoạn transcript mốc {lbl}:\n\"{clean_excerpt}\"{code_hint}\n\n"
        f"Yêu cầu dạng tình huống ({archetype['id']}): {archetype['instruction']}\n\n"
        "Trả về JSON đúng schema: "
        '{"student_question": "...", "assistant_prose": "..."}'
    )

    last_err = "unknown"
    for attempt in range(3):
        model_name = TEACHER_MODELS[min(attempt, len(TEACHER_MODELS) - 1)]
        api_key = await key_pool.next_key()
        async with sem:
            try:
                resp = await client.post(
                    f"{GEMINI_OPENAI_BASE_URL.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": sys_msg},
                            {"role": "user", "content": user_msg},
                        ],
                        "temperature": 0.65 if attempt == 0 else 0.45,
                        "max_tokens": 550,
                        "response_format": {"type": "json_object"},
                    },
                    timeout=35.0,
                )
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_err = f"http_{resp.status_code}_{model_name}"
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                if resp.status_code != 200:
                    last_err = f"http_{resp.status_code}_{model_name}"
                    continue
                payload = resp.json()
                raw_content = str(payload["choices"][0]["message"].get("content") or "").strip()
                parsed = json.loads(raw_content)
                sq = str(parsed.get("student_question") or "").strip()
                prose = str(parsed.get("assistant_prose") or "").strip()
            except Exception as exc:
                last_err = f"{type(exc).__name__}"
                await asyncio.sleep(1.0)
                continue

        ok, reason, row = _validate_candidate(
            seq=seq,
            sec=sec,
            lbl=lbl,
            clean_excerpt=clean_excerpt,
            student_q=sq,
            prose=prose,
            heldout_norms=heldout_norms,
            heldout_queries=heldout_queries,
            valid_ts_by_lesson=valid_ts_by_lesson,
            forbidden_closing_prefixes=forbidden_closing_prefixes,
        )
        if ok and row is not None:
            row["archetype"] = archetype["id"]
            row["teacher_model"] = model_name
            stats[f"model:{model_name}"] = stats.get(f"model:{model_name}", 0) + 1
            return row
        last_err = reason

    stats["failed"] = stats.get("failed", 0) + 1
    print(f"   [WARN] L{seq:02d} [{archetype['id']}] failed after 3 attempts: {last_err}", flush=True)
    return None


async def async_main(args: argparse.Namespace) -> int:
    keys = _collect_gemini_keys()
    if not keys:
        print("[ERROR] Thiếu GEMINI_API_KEYS / GEMINI_API_KEY trong .env!", flush=True)
        return 2

    lessons = _load_lessons()
    valid_ts_by_lesson = load_valid_lesson_timestamps()
    segments_by_seq = _load_clean_transcript_segments(lessons, valid_ts_by_lesson)
    code_snippets = _load_sanitized_code_snippets()
    heldout_norms, heldout_queries = load_heldout_queries()
    forbidden_closing_prefixes = _load_forbidden_closing_prefixes()

    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    existing_rows: List[Dict[str, Any]] = []
    done_slots: Set[Tuple[int, str]] = set()
    if args.resume and out_path.exists():
        for ln in out_path.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            existing_rows.append(r)
            done_slots.add((int(r["lesson_seq"]), str(r.get("archetype") or "")))

    samples_per_lesson = max(1, min(len(ARCHETYPES), int(args.samples_per_lesson)))
    rng = random.Random(args.seed)
    tasks_spec: List[Tuple[Dict[str, Any], Dict[str, Any], Dict[str, str], int, str]] = []

    for idx, les in enumerate(lessons):
        seq = int(les["seq"])
        segs = segments_by_seq.get(seq) or []
        if not segs:
            raise RuntimeError(f"Lesson {seq} has zero valid transcript/chapter segments!")
        chosen_segs = _pick_spaced_segments(segs, samples_per_lesson, offset=idx % len(segs))
        for a_idx in range(samples_per_lesson):
            arch = ARCHETYPES[a_idx]
            if (seq, arch["id"]) in done_slots:
                continue
            ast_snip = code_snippets.get(seq, "") if a_idx in (1, 2) else ""
            tasks_spec.append((les, chosen_segs[a_idx], arch, a_idx, ast_snip))

    rng.shuffle(tasks_spec)
    print(
        f"[Distill v2] Lessons={len(lessons)} | Keys={len(keys)} | Models={TEACHER_MODELS} | "
        f"AlreadyDone={len(existing_rows)} | RemainingSlots={len(tasks_spec)}",
        flush=True,
    )

    key_pool = KeyPool(keys)
    sem = asyncio.Semaphore(min(int(args.concurrency), max(1, len(keys))))
    stats: Dict[str, int] = {}

    if not tasks_spec:
        all_rows = existing_rows
    else:
        async with httpx.AsyncClient(timeout=40.0) as client:
            coros = [
                distill_single_slot(
                    sem=sem,
                    client=client,
                    key_pool=key_pool,
                    lesson=les,
                    seg=seg,
                    archetype=arch,
                    archetype_idx=a_idx,
                    ast_snippet=ast_snip,
                    heldout_norms=heldout_norms,
                    heldout_queries=heldout_queries,
                    valid_ts_by_lesson=valid_ts_by_lesson,
                    forbidden_closing_prefixes=forbidden_closing_prefixes,
                    stats=stats,
                )
                for (les, seg, arch, a_idx, ast_snip) in tasks_spec
            ]
            generated: List[Dict[str, Any]] = list(existing_rows)
            completed = 0
            for fut in asyncio.as_completed(coros):
                res = await fut
                completed += 1
                if res is not None:
                    generated.append(res)
                if completed % 25 == 0 or completed == len(coros):
                    print(
                        f"   [Progress] {completed}/{len(coros)} slots | ValidTotal={len(generated)} | Stats={stats}",
                        flush=True,
                    )
            all_rows = generated

    all_rows.sort(key=lambda r: (int(r["lesson_seq"]), str(r.get("archetype") or "")))
    with open(out_path, "w", encoding="utf-8") as f:
        for r in all_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    user_openings = {_normalize_opening_prefix(r["messages"][1]["content"].replace("[CÂU HỎI THẮC MẮC CỦA HỌC VIÊN]", "").split("\n[NGỮ CẢNH")[0]) for r in all_rows}
    asst_openings = {_normalize_opening_prefix(r["messages"][2]["content"]) for r in all_rows}
    covered = {int(r["lesson_seq"]) for r in all_rows}
    print(
        f"\n[Distill v2 COMPLETE] Saved {len(all_rows)} rows -> {out_path}\n"
        f"  - Lessons covered: {len(covered)}/83\n"
        f"  - Unique user openings: {len(user_openings)}\n"
        f"  - Unique assistant openings: {len(asst_openings)}\n"
        f"  - Model breakdown: {stats}",
        flush=True,
    )
    return 0 if len(covered) >= 83 and len(all_rows) >= 160 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Distill Qwen2.5-Coder-7B Socratic SFT v2 dataset via Gemini Flash-Lite.")
    parser.add_argument("--samples-per-lesson", type=int, default=4)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUT_PATH))
    args = parser.parse_args()
    sys.exit(asyncio.run(async_main(args)))


if __name__ == "__main__":
    main()
