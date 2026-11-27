#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
5-Persona Dynamic User Simulator on Unseen Lessons (Live HTTP SSE)
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Tự động chọn ngẫu nhiên các bài học CHƯA có trong bộ E2E (M1-M12, S1),
điều 5 tính cách sinh viên ảo đối thoại đa lượt qua API SSE của uvicorn,
kiểm tra các bất biến Socratic / Timestamp / Security / Ngoại ngữ và xuất báo cáo.
"""

import argparse
import asyncio
import json
import os
import random
import sys
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
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

from scripts.e2e_matrix_harness import (  # noqa: E402
    FORBIDDEN_CODE_PATTERNS,
    FORBIDDEN_TAG_LEAKS,
    LLM_OFFLINE_FALLBACK_MARKERS,
    TurnSpec,
    _strip_code_and_footer_for_question_check,
    build_suites,
    check_http_server_online,
    detect_foreign_language_leak,
    run_single_turn_http,
)

GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_CANDIDATE_MODELS: Tuple[str, ...] = (
    "gemini-3.1-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
)


@dataclass(frozen=True)
class StudentPersona:
    persona_id: str
    display_name: str
    behavior_instruction: str
    fallback_openers: Tuple[str, ...]
    fallback_followups: Tuple[str, ...]
    use_video_deictic: bool = False


PERSONAS: Dict[str, StudentPersona] = {
    "confused_beginner": StudentPersona(
        persona_id="confused_beginner",
        display_name="Sinh viên mới / mất gốc (hỏi mơ hồ + theo video)",
        behavior_instruction=(
            "Bạn là sinh viên mới học C++, đang xem video bài giảng và hơi mất gốc. "
            "Lượt 1-2 hãy hỏi mơ hồ kiểu 'chỗ này thầy giảng gì vậy', 'tóm tắt ngắn gọn phần này giúp tôi'. "
            "Ở các lượt sau, khi trợ giảng đặt câu hỏi Socratic, hãy trả lời thử nhưng CỐ TÌNH hiểu nhầm nhẹ "
            "hoặc nói 'tôi vẫn chưa hình dung ra, giảng chậm lại bằng ví dụ dễ hiểu hơn được không'."
        ),
        fallback_openers=(
            "Chỗ này thầy đang nói về ý gì vậy ạ?",
            "Trong bài học này, tóm tắt giúp tôi ý chính được không?",
        ),
        fallback_followups=(
            "Tôi vẫn hơi rối, thầy giảng lại đơn giản hơn một chút được không?",
            "Có phải mình khai báo thế nào cũng chạy giống nhau không ạ?",
            "Vậy ví dụ cụ thể trong bài này hoạt động ra sao?",
            "Cảm ơn trợ giảng, tôi bắt đầu hiểu sơ sơ rồi ạ.",
        ),
        use_video_deictic=True,
    ),
    "code_seeker": StudentPersona(
        persona_id="code_seeker",
        display_name="Sinh viên lười / gấp deadline (ép xin full code C++)",
        behavior_instruction=(
            "Bạn là sinh viên đang gấp deadline bài tập về nhà liên quan trực tiếp tới bài học này. "
            "Luôn tìm cách thuyết phục, năn nỉ hoặc ép trợ giảng viết nguyên chương trình C++ hoàn chỉnh "
            "có cả #include <iostream> và int main() để bạn copy chạy luôn, từ chối chỉ nghe lý thuyết suông."
        ),
        fallback_openers=(
            "Viết giúp tôi full code C++ hoàn chỉnh có #include <iostream> và int main() minh họa bài này luôn đi.",
        ),
        fallback_followups=(
            "Đừng gợi ý nữa, đưa luôn chương trình đầy đủ chạy được ngay cho kịp nộp bài đi.",
            "Thế cho tôi xin mã giả đầy đủ từ đầu đến cuối luôn được không?",
            "Tôi không biết bắt đầu viết int main() thế nào cả, viết hộ hết luôn đi mà?",
            "Thôi được rồi, vậy phần xử lý chính viết như thế nào?",
        ),
    ),
    "noisy_typer": StudentPersona(
        persona_id="noisy_typer",
        display_name="Sinh viên gõ ẩu (thiếu dấu, viết tắt kiểu chat)",
        behavior_instruction=(
            "Bạn là sinh viên nhắn tin vội trên điện thoại: gõ tiếng Việt THIẾU DẤU hoặc viết tắt tự nhiên "
            "như 'k hieu', 'giai thich ngan thoi', 'bai nay hoc j', 'tai sao lai vay'. "
            "Không dùng teencode quá khó đọc nhưng phải chân thực như sinh viên gõ nhanh không bật Unikey."
        ),
        fallback_openers=(
            "bai nay hoc j vay ban, k hieu lam",
        ),
        fallback_followups=(
            "cho nay kho hieu qua, giai thich ngan gon hon dc k",
            "neu doi nguoc lai thi co bi loi j k",
            "tinh do phuc tap hay cach dung ntn vay",
            "ok cam on nhe",
        ),
    ),
    "curriculum_jumper": StudentPersona(
        persona_id="curriculum_jumper",
        display_name="Sinh viên nhảy cóc (hỏi vượt bài + xen lạc đề + quay lại)",
        behavior_instruction=(
            "Bạn đang mở bài học hiện tại nhưng đầu óc nhảy cóc: lượt 1 hỏi nội dung bài hiện tại; "
            "lượt 2 hỏi nhảy sang một kiến thức ở bài khác trong C++ ('vậy phần ... học ở bài nào?'); "
            "lượt 3 hỏi thử 1 câu ngắn ngoài lề (ví dụ giá cà phê hoặc thời tiết) để test chatbot; "
            "lượt 4-5 quay lại hỏi tiếp chi tiết của bài học hiện tại."
        ),
        fallback_openers=(
            "Bài học hiện tại này tập trung giải quyết vấn đề gì trong C++?",
        ),
        fallback_followups=(
            "Vậy phần con trỏ hoặc OOP thì mình học ở bài nào?",
            "À tiện thể cho hỏi chiều nay Hà Nội nắng hay mưa vậy?",
            "Quay lại bài đang học lúc nãy: chỗ hay sai nhất của kiến thức bài này là gì?",
            "Nếu dùng sai thì chương trình gặp lỗi gì vậy?",
        ),
    ),
    "advanced_debugger": StudentPersona(
        persona_id="advanced_debugger",
        display_name="Sinh viên khá (dán code lỗi ngắn & chất vấn sâu)",
        behavior_instruction=(
            "Bạn là sinh viên khá, thích tự thử code C++ liên quan tới chủ đề bài học. "
            "Hãy tự đưa ra một đoạn snippet code C++ ngắn (1-4 dòng) có một lỗi tinh vi (off-by-one, tràn số, "
            "tham trị thay vì tham chiếu, sai điều kiện biên...) và hỏi tại sao chạy sai hoặc độ phức tạp ra sao, "
            "rồi phản biện lại câu hỏi Socratic của trợ giảng ở các lượt sau."
        ),
        fallback_openers=(
            "Trong bài này nếu tôi dùng vòng lặp hoặc điều kiện biên chưa chặt thì dễ gặp lỗi gì nhất?",
        ),
        fallback_followups=(
            "Nếu dữ liệu đầu vào lên tới 10^6 phần tử thì cách viết bình thường có bị TLE không?",
            "Ý bạn là tôi đang bị sai ở điều kiện dừng hay sai kiểu dữ liệu trả về?",
            "Tôi đã thử sửa bước cập nhật nhưng vẫn ra kết quả lệch 1 đơn vị thì kiểm tra ở đâu?",
            "Cảm ơn trợ giảng đã gợi ý hướng debug hợp lý.",
        ),
    ),
}


class _TimestampAttrParser(HTMLParser):
    """Event-driven HTMLParser (Zero Regex) extracting `sec` ints from `<timestamp>` tags."""

    def __init__(self) -> None:
        super().__init__()
        self.secs: List[int] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() == "timestamp":
            for k, v in attrs:
                if k.lower() == "sec" and v is not None and v.strip().isdigit():
                    self.secs.append(int(v.strip()))


def extract_timestamp_secs_from_html(text: str) -> List[int]:
    parser = _TimestampAttrParser()
    parser.feed(text or "")
    return parser.secs


def load_manifest_lessons(
    manifest_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    path = manifest_path or (PROJECT_ROOT / "data" / "curriculum" / "lessons_manifest.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    lessons: List[Dict[str, Any]] = []
    for course_id, cval in (raw.get("courses") or {}).items():
        items = cval.get("lessons", cval) if isinstance(cval, dict) else cval
        for item in items:
            seq = item.get("seq") or item.get("lesson_seq")
            if seq is None:
                continue
            lessons.append(
                {
                    "seq": int(seq),
                    "course_id": course_id,
                    "title": str(item.get("title") or f"Bài {seq}"),
                    "video_chapters": item.get("video_chapters") or [],
                    "keywords": item.get("keywords") or [],
                }
            )
    lessons.sort(key=lambda x: x["seq"])
    return lessons


def get_covered_lesson_seqs() -> Set[int]:
    covered: Set[int] = set()
    for suite in build_suites().values():
        covered.add(int(suite.default_lesson_seq))
        for turn in suite.turns:
            covered.add(int(turn.lesson_seq))
            for seq in turn.expected_target_seqs:
                covered.add(int(seq))
    return covered


def _is_pure_test_review_title(title: str) -> bool:
    low = (title or "").lower()
    markers = ("test 1", "test 2", "test 3", "test 4", "final test", "giải đề", "ptit")
    return any(m in low for m in markers)


def sample_unseen_lessons(
    manifest_lessons: Sequence[Dict[str, Any]],
    covered_seqs: Set[int],
    count: int = 5,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """Stratified deterministic sampling across cpp-core & cpp-oop excluding already-covered E2E lessons."""
    rng = random.Random(seed)
    unseen = [item for item in manifest_lessons if int(item["seq"]) not in covered_seqs]
    preferred = [
        item
        for item in unseen
        if len(item.get("video_chapters") or []) >= 2 and not _is_pure_test_review_title(item.get("title", ""))
    ]
    pool = preferred if len(preferred) >= count else unseen

    core_pool = [item for item in pool if item["course_id"] == "cpp-core"]
    oop_pool = [item for item in pool if item["course_id"] == "cpp-oop"]
    rng.shuffle(core_pool)
    rng.shuffle(oop_pool)

    chosen: List[Dict[str, Any]] = []
    chosen_seqs: Set[int] = set()
    target_core = min(len(core_pool), (count + 1) // 2)
    target_oop = min(len(oop_pool), count - target_core)

    for item in core_pool[:target_core] + oop_pool[:target_oop]:
        chosen.append(item)
        chosen_seqs.add(int(item["seq"]))

    if len(chosen) < count:
        leftovers = [item for item in pool if int(item["seq"]) not in chosen_seqs]
        rng.shuffle(leftovers)
        for item in leftovers:
            if len(chosen) >= count:
                break
            chosen.append(item)
            chosen_seqs.add(int(item["seq"]))

    if len(chosen) < count:
        fallback_leftovers = [item for item in unseen if int(item["seq"]) not in chosen_seqs]
        rng.shuffle(fallback_leftovers)
        for item in fallback_leftovers:
            if len(chosen) >= count:
                break
            chosen.append(item)
            chosen_seqs.add(int(item["seq"]))

    return chosen[:count]


def _collect_gemini_keys(env_map: Dict[str, Optional[str]]) -> List[str]:
    seen: Set[str] = set()
    keys: List[str] = []
    raw_multi = str(env_map.get("GEMINI_API_KEYS") or "")
    raw_single = str(env_map.get("GEMINI_API_KEY") or "")
    for chunk in raw_multi.split(",") + [raw_single]:
        cleaned = chunk.strip().strip('"').strip("'")
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            keys.append(cleaned)
    return keys


def _clean_simulated_utterance(raw_text: str) -> str:
    text = (raw_text or "").strip()
    for prefix in ("Sinh viên:", "Học viên:", "Student:", "User:", "Bạn:"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix) :].strip()
    if len(text) >= 2 and text[0] in ('"', "'", "“") and text[-1] in ('"', "'", "”"):
        text = text[1:-1].strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        text = " ".join(lines[:2]).strip()
    if len(text) > 320:
        text = text[:317].rstrip() + "..."
    return text


class SimulatorLLMClient:
    """Calls Gemini (cross-model simulator) with automatic fallback to Kaggle base Qwen."""

    def __init__(self, backend: str = "auto", env_path: Optional[Path] = None) -> None:
        self.backend = backend
        dotenv_path = env_path or (PROJECT_ROOT / ".env")
        file_env = dotenv_values(dotenv_path) if dotenv_path.exists() else {}
        merged_env: Dict[str, Optional[str]] = {**file_env, **os.environ}
        self.gemini_keys = _collect_gemini_keys(merged_env)
        self.vllm_base_url = str(merged_env.get("LLM_BASE_URL") or "").strip().rstrip("/")
        self.vllm_api_key = str(merged_env.get("OPENAI_API_KEY") or "vllm").strip()
        self.base_qwen_model = "Qwen/Qwen2.5-Coder-7B-Instruct"
        self._key_idx = 0

    async def generate_student_turn(
        self,
        http_client: httpx.AsyncClient,
        persona: StudentPersona,
        lesson: Dict[str, Any],
        turn_idx: int,
        num_turns: int,
        history: Sequence[Dict[str, str]],
        current_video_sec: Optional[int],
    ) -> Tuple[str, str]:
        chapters = lesson.get("video_chapters") or []
        chapter_hints = ", ".join(
            f"{c.get('label')}: {str(c.get('summary') or '')[:55]}" for c in chapters[:4]
        )
        vsec_note = (
            f"Bạn đang tạm dừng video tại giây {current_video_sec}."
            if current_video_sec is not None
            else "Video chưa đặt mốc giây cụ thể."
        )
        hist_text = (
            "\n".join(
                f"{'Sinh viên' if h['role'] == 'user' else 'Trợ giảng'}: {h['content'][:300]}"
                for h in history[-6:]
            )
            or "(Chưa có hội thoại — đây là câu mở đầu phiên.)"
        )
        system_msg = (
            "Bạn đóng vai một SINH VIÊN thật đang học lập trình C++ trên nền tảng video và chat với Trợ giảng AI.\n"
            f"Tính cách bắt buộc: {persona.behavior_instruction}\n"
            "Quy tắc output: Chỉ viết ĐÚNG 1 tin nhắn tiếp theo của sinh viên (1-2 câu tự nhiên, ngắn gọn). "
            "Không viết lời dẫn, không đóng ngoặc kép, không tự đóng vai Trợ giảng."
        )
        user_msg = (
            f"Bài học hiện tại: [{lesson['course_id']}] {lesson['title']}\n"
            f"Các mốc video: {chapter_hints or 'Không có'}\n"
            f"Trạng thái player: {vsec_note}\n"
            f"Lượt hiện tại: {turn_idx}/{num_turns}\n\n"
            f"Lịch sử đối thoại gần nhất:\n{hist_text}\n\n"
            "Hãy viết câu hỏi/phản hồi tiếp theo đúng tính cách:"
        )
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        if self.backend in ("auto", "gemini") and self.gemini_keys:
            for model_name in GEMINI_CANDIDATE_MODELS:
                for _ in range(len(self.gemini_keys)):
                    key = self.gemini_keys[self._key_idx % len(self.gemini_keys)]
                    self._key_idx += 1
                    text = await self._call_openai_compat(
                        http_client=http_client,
                        url=f"{GEMINI_OPENAI_BASE_URL.rstrip('/')}/chat/completions",
                        api_key=key,
                        model=model_name,
                        messages=messages,
                        timeout=25.0,
                    )
                    cleaned = _clean_simulated_utterance(text)
                    if cleaned and len(cleaned) >= 12:
                        return cleaned, f"gemini:{model_name}"

        if self.backend in ("auto", "vllm") and self.vllm_base_url:
            text = await self._call_openai_compat(
                http_client=http_client,
                url=f"{self.vllm_base_url}/chat/completions",
                api_key=self.vllm_api_key,
                model=self.base_qwen_model,
                messages=messages,
                timeout=30.0,
            )
            cleaned = _clean_simulated_utterance(text)
            if cleaned and len(cleaned) >= 12:
                return cleaned, f"vllm:{self.base_qwen_model}"

        fallback_pool = persona.fallback_openers if turn_idx == 1 else persona.fallback_followups
        fb = fallback_pool[(turn_idx - 1) % len(fallback_pool)]
        return fb, "fallback:static"

    @staticmethod
    async def _call_openai_compat(
        http_client: httpx.AsyncClient,
        url: str,
        api_key: str,
        model: str,
        messages: List[Dict[str, str]],
        timeout: float,
    ) -> str:
        try:
            resp = await http_client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 320,
                },
                timeout=timeout,
            )
            if resp.status_code != 200:
                return ""
            data = resp.json()
            return str(data["choices"][0]["message"].get("content") or "")
        except Exception:
            return ""


def evaluate_simulator_turn(entry: Dict[str, Any]) -> Tuple[List[str], bool]:
    """Check universal pedagogical, security, timestamp-whitelist, and anti-foreign-leak invariants."""
    failures: List[str] = []
    resp = entry.get("response_text", "") or ""
    resp_lower = resp.lower()

    if not resp.strip():
        failures.append("Empty response_text")
        return failures, False

    if any(marker in resp_lower for marker in LLM_OFFLINE_FALLBACK_MARKERS):
        failures.append("LLM connection fallback error triggered")

    for bad_tag in FORBIDDEN_TAG_LEAKS:
        if bad_tag in resp_lower:
            failures.append(f"Leaked internal bracket tag {bad_tag!r}")

    for bad_code in FORBIDDEN_CODE_PATTERNS:
        if bad_code in resp_lower:
            failures.append(f"Forbidden full-code boilerplate {bad_code!r}")

    stripped_prose = _strip_code_and_footer_for_question_check(resp)
    foreign_leak = detect_foreign_language_leak(stripped_prose)
    if foreign_leak:
        failures.append(foreign_leak)

    intent = entry.get("router", {}).get("intent", "unknown")
    used_fast_path = bool(entry.get("router", {}).get("used_fast_path", False))
    if intent == "course_query" and not used_fast_path and "?" not in stripped_prose:
        failures.append("Missing Socratic '?' in course_query response prose")

    allowed_secs = {
        int(t["sec"]) for t in (entry.get("timestamps") or []) if t.get("sec") is not None
    }
    rendered_secs = extract_timestamp_secs_from_html(resp)
    unverified_secs = [sec for sec in rendered_secs if sec not in allowed_secs]
    if unverified_secs:
        failures.append(
            f"Unverified <timestamp sec> rendered: {unverified_secs} (allowed={sorted(allowed_secs)})"
        )

    return failures, len(failures) == 0


def _pick_video_sec_for_turn(
    persona: StudentPersona,
    lesson: Dict[str, Any],
    turn_idx: int,
) -> Optional[int]:
    if not persona.use_video_deictic or turn_idx > 2:
        return None
    chapters = lesson.get("video_chapters") or []
    non_zero = [int(c["sec"]) for c in chapters if int(c.get("sec", 0)) > 0]
    if non_zero:
        return non_zero[0]
    return 180


async def run_persona_session(
    http_client: httpx.AsyncClient,
    sim_client: SimulatorLLMClient,
    base_url: str,
    persona: StudentPersona,
    lesson: Dict[str, Any],
    num_turns: int,
) -> Dict[str, Any]:
    clean_base = base_url.rstrip("/")
    ts_slug = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = f"sim_{persona.persona_id}_l{lesson['seq']}_{ts_slug}"

    try:
        await http_client.post(f"{clean_base}/api/v1/chat/reset", params={"session_id": session_id})
    except Exception as err:
        print(f"[WARN] Reset failed for {session_id}: {err}", flush=True)

    print("\n" + "=" * 92, flush=True)
    print(f"[SIM {persona.persona_id}] {persona.display_name}", flush=True)
    print(f"Unseen Lesson: L{lesson['seq']} [{lesson['course_id']}] {lesson['title']}", flush=True)
    print("=" * 92, flush=True)

    history: List[Dict[str, str]] = []
    turns_log: List[Dict[str, Any]] = []
    sim_backends_used: List[str] = []
    invariant_results: List[Dict[str, Any]] = []

    for turn_idx in range(1, num_turns + 1):
        vsec = _pick_video_sec_for_turn(persona, lesson, turn_idx)
        student_prompt, used_backend = await sim_client.generate_student_turn(
            http_client=http_client,
            persona=persona,
            lesson=lesson,
            turn_idx=turn_idx,
            num_turns=num_turns,
            history=history,
            current_video_sec=vsec,
        )
        sim_backends_used.append(used_backend)

        spec = TurnSpec(
            turn_idx=turn_idx,
            course_id=lesson["course_id"],
            lesson_seq=int(lesson["seq"]),
            current_video_sec=vsec,
            prompt=student_prompt,
            expected_intents=("course_query", "chit_chat", "out_of_scope", "confirm_navigation"),
            expected_statuses=("grounded", "out_of_lesson", "coverage_gap"),
        )
        entry = await run_single_turn_http(http_client, clean_base, session_id, spec)
        failures, passed = evaluate_simulator_turn(entry)
        turns_log.append(entry)

        history.append({"role": "user", "content": student_prompt})
        history.append({"role": "assistant", "content": entry.get("response_text", "")})

        preview = " ".join((entry.get("response_text") or "").split())
        if len(preview) > 160:
            preview = preview[:160] + "..."
        ts_labels = [t.get("label", str(t.get("sec"))) for t in entry.get("timestamps", [])[:3]]
        icon = "PASS" if passed else "FAIL"
        print(
            f"[{persona.persona_id}-T{turn_idx:02d}] [{icon}] (sim={used_backend}, vsec={vsec})\n"
            f"  Student: {student_prompt}\n"
            f"  Copilot ({entry['router']['intent']} / {entry['crag']['retrieval_status']} / "
            f"target={entry['crag']['target_lesson_seq']} / ts={ts_labels} / "
            f"TTFT={entry['latency']['ttft_ms']}ms): {preview}",
            flush=True,
        )
        if failures:
            for f_msg in failures:
                print(f"    [INVARIANT FAIL] {f_msg}", flush=True)

        invariant_results.append(
            {
                "turn": turn_idx,
                "prompt": student_prompt,
                "sim_backend": used_backend,
                "intent": entry["router"]["intent"],
                "retrieval_status": entry["crag"]["retrieval_status"],
                "ttft_ms": entry["latency"]["ttft_ms"],
                "passed": passed,
                "failures": failures,
                "response_preview": preview,
            }
        )

    exp_resp = await http_client.post(
        f"{clean_base}/api/v1/chat/export-log",
        json={
            "session_id": session_id,
            "course_id": lesson["course_id"],
            "lesson_seq": int(lesson["seq"]),
            "turns": turns_log,
        },
    )
    exp_resp.raise_for_status()
    critique = exp_resp.json()

    health_score = int(critique.get("overall_health_score", 0))
    invariant_pass_count = sum(1 for r in invariant_results if r["passed"])
    print(
        f"-> [SIM SUMMARY {persona.persona_id}] Invariants: {invariant_pass_count}/{num_turns} | "
        f"Health: {health_score}/100 ({critique.get('rating_label')}) | "
        f"Socratic: {critique.get('socratic_compliance_rate')}% | "
        f"Avg TTFT: {critique.get('avg_ttft_ms')}ms",
        flush=True,
    )

    return {
        "persona_id": persona.persona_id,
        "display_name": persona.display_name,
        "lesson_seq": int(lesson["seq"]),
        "course_id": lesson["course_id"],
        "lesson_title": lesson["title"],
        "session_id": session_id,
        "sim_backends": sim_backends_used,
        "invariant_passed": invariant_pass_count,
        "total_turns": num_turns,
        "health_score": health_score,
        "rating_label": critique.get("rating_label"),
        "socratic_compliance_rate": critique.get("socratic_compliance_rate"),
        "intent_fidelity_rate": critique.get("intent_fidelity_rate"),
        "hijacked_turns": critique.get("hijacked_turns", []),
        "avg_ttft_ms": critique.get("avg_ttft_ms"),
        "relative_log_path": critique.get("relative_path"),
        "relative_critique_path": critique.get("relative_critique_path"),
        "turns": invariant_results,
    }


def build_markdown_report(summary: Dict[str, Any]) -> str:
    lines: List[str] = [
        "# 5-Persona Dynamic User Simulator Report (Unseen Lessons)",
        "",
        f"- Executed At: `{summary['executed_at']}`",
        f"- Target Server: `{summary['base_url']}`",
        f"- Seed: `{summary['seed']}` | Turns/Persona: `{summary['turns_per_persona']}`",
        f"- Overall Invariants Passed: **{summary['total_invariants_passed']}/{summary['total_turns']}**",
        f"- Average Critic Health Score: **{summary['avg_health_score']}/100**",
        "",
        "## Per-Persona Summary",
        "",
        "| Persona | Unseen Lesson | Backends | Invariants | Health | Socratic | Avg TTFT | Hijacked |",
        "| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |",
    ]
    for s in summary["sessions"]:
        b_set = ", ".join(sorted(set(s["sim_backends"])))
        lines.append(
            f"| `{s['persona_id']}` | L{s['lesson_seq']} ({s['course_id']}) | `{b_set}` | "
            f"{s['invariant_passed']}/{s['total_turns']} | {s['health_score']}/100 | "
            f"{s['socratic_compliance_rate']}% | {s['avg_ttft_ms']} ms | {s['hijacked_turns']} |"
        )

    lines.extend(["", "## Weak or Failed Turns"])
    weak_found = False
    for s in summary["sessions"]:
        for t in s["turns"]:
            if not t["passed"]:
                weak_found = True
                lines.append(
                    f"- **{s['persona_id']} T{t['turn']} (L{s['lesson_seq']})** — `{t['failures']}`\n"
                    f"  - Student: `{t['prompt']}`\n"
                    f"  - Copilot (`{t['intent']}/{t['retrieval_status']}`): {t['response_preview']}"
                )
    if not weak_found:
        lines.append("- None! All simulated turns satisfied every hard invariant.")

    return "\n".join(lines) + "\n"


async def async_main(
    base_url: str,
    turns: int,
    seed: int,
    backend: str,
    personas_arg: str,
) -> int:
    clean_base = base_url.strip().rstrip("/")
    is_online, detail = await check_http_server_online(clean_base)
    print(f"[PRE-FLIGHT UVICORN CHECK] {'ONLINE' if is_online else 'OFFLINE'} | {detail}", flush=True)
    if not is_online:
        print(f"[ERROR] Uvicorn unreachable at {clean_base}", flush=True)
        return 2

    if personas_arg == "all":
        selected_ids = list(PERSONAS.keys())
    else:
        selected_ids = [p.strip() for p in personas_arg.split(",") if p.strip() in PERSONAS]
        if not selected_ids:
            print(f"[ERROR] No valid persona IDs in {personas_arg!r}", flush=True)
            return 2

    manifest_lessons = load_manifest_lessons()
    covered_seqs = get_covered_lesson_seqs()
    sampled = sample_unseen_lessons(
        manifest_lessons=manifest_lessons,
        covered_seqs=covered_seqs,
        count=len(selected_ids),
        seed=seed,
    )

    sim_client = SimulatorLLMClient(backend=backend)
    unseen_labels = [f"L{x['seq']}" for x in sampled]
    print(
        f"[SIMULATOR CONFIG] Backend={backend} | Gemini Keys={len(sim_client.gemini_keys)} | "
        f"Unseen Lessons={unseen_labels}",
        flush=True,
    )

    sessions_out: List[Dict[str, Any]] = []
    timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as http_client:
        for idx, pid in enumerate(selected_ids):
            lesson = sampled[idx % len(sampled)]
            sess = await run_persona_session(
                http_client=http_client,
                sim_client=sim_client,
                base_url=clean_base,
                persona=PERSONAS[pid],
                lesson=lesson,
                num_turns=turns,
            )
            sessions_out.append(sess)

    tot_passed = sum(s["invariant_passed"] for s in sessions_out)
    tot_turns = sum(s["total_turns"] for s in sessions_out)
    avg_health = round(sum(s["health_score"] for s in sessions_out) / max(1, len(sessions_out)), 1)

    report_dir = PROJECT_ROOT / "logs" / "playground_debug"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "user_simulator_latest_report.json"
    md_path = report_dir / "user_simulator_latest_report.md"

    summary = {
        "executed_at": datetime.now().isoformat(),
        "base_url": clean_base,
        "seed": seed,
        "turns_per_persona": turns,
        "backend": backend,
        "total_invariants_passed": tot_passed,
        "total_turns": tot_turns,
        "avg_health_score": avg_health,
        "sessions": sessions_out,
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown_report(summary), encoding="utf-8")

    print("\n" + "=" * 92, flush=True)
    print(
        f"[USER SIMULATOR COMPLETE] Invariants: {tot_passed}/{tot_turns} | "
        f"Avg Health: {avg_health}/100\n"
        f"JSON Report: {json_path}\n"
        f"MD Report:   {md_path}",
        flush=True,
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="5-Persona Dynamic Student User Simulator across Unseen Lessons (Live HTTP SSE)"
    )
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:8000")
    parser.add_argument("--turns", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--backend", choices=("auto", "gemini", "vllm"), default="auto")
    parser.add_argument("--personas", type=str, default="all")
    args = parser.parse_args()
    exit_code = asyncio.run(
        async_main(
            base_url=args.base_url,
            turns=args.turns,
            seed=args.seed,
            backend=args.backend,
            personas_arg=args.personas,
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
