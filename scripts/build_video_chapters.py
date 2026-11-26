"""
Sinh mục lục phân đoạn video (video_chapters) cho toàn bộ 83 bài học trong data/curriculum/lessons_manifest.json.
Nguồn dữ liệu:
- data/transcripts/*/*_chunks.json
- data/metadata/lesson_code_video_binding.json

Chạy bằng: .venv\\Scripts\\python.exe scripts/build_video_chapters.py
"""

import json
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PROJECT_ROOT / "data" / "curriculum" / "lessons_manifest.json"
BINDING_PATH = PROJECT_ROOT / "data" / "metadata" / "lesson_code_video_binding.json"
TRANSCRIPTS_DIR = PROJECT_ROOT / "data" / "transcripts"

VIET_DIACRITIC_CHARS = set(
    "ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩị"
    "òóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ"
    "ĂÂĐÊÔƠƯÀÁẢÃẠẰẮẲẴẶẦẤẨẪẬÈÉẺẼẸỀẾỂỄỆÌÍỈĨỊ"
    "ÒÓỎÕỌỒỐỔỖỘỜỚỞỠỢÙÚỦŨỤỪỨỬỮỰỲÝỶỸỴ"
)

CPP_WHITELIST_TERMS = {
    "c++", "cpp", "int", "float", "double", "char", "bool", "void", "long", "short",
    "const", "static", "struct", "class", "public", "private", "protected", "friend",
    "return", "if", "else", "switch", "case", "break", "continue", "for", "while", "do",
    "cin", "cout", "endl", "main", "string", "vector", "pair", "set", "multiset",
    "map", "multimap", "unordered_map", "unordered_set", "stack", "queue", "deque",
    "priority_queue", "sort", "binary", "search", "lower_bound", "upper_bound",
    "iterator", "pointer", "node", "linked", "list", "constructor", "destructor",
    "operator", "overload", "oop", "this", "typedef", "define", "include", "iostream",
    "cmath", "algorithm", "gcd", "swap", "array", "matrix", "prefix", "sum",
    "sliding", "window", "two", "pointers", "bitwise", "recursion", "backtracking",
    "ide", "compiler", "big", "o(n)", "o(1)", "o(logn)", "function", "prototype",
}

FILLER_OPENERS = (
    "ok ", "ok,", "ok?", "rồi ", "rồi,", "thì ", "như thế này", "như vậy ",
    "được không nhỉ", "đúng không", "các bạn ", "mình ", "chúng ta ",
)


def format_mm_ss(sec: int) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60:02d}:{sec % 60:02d}"


def is_allowed_char(ch: str) -> bool:
    code = ord(ch)
    if ch in "\n\r\t ":
        return True
    if 0x20 <= code <= 0x7E:
        return True
    if ch in VIET_DIACRITIC_CHARS:
        return True
    if ch in "–—‘’“”…":
        return True
    # Cho phép Latin Extended bổ sung (0x00C0..0x024F, 0x1E00..0x1EFF) thuộc tiếng Việt
    if (0x00C0 <= code <= 0x024F) or (0x1E00 <= code <= 0x1EFF):
        return True
    return False


def sanitize_transcript_text(text: str) -> str:
    """Loại bỏ ký tự CJK, Hangul, ký tự toán học lạ, replacement char và thu gọn khoảng trắng."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFC", text)
    cleaned_chars = [ch if is_allowed_char(ch) else " " for ch in norm]
    collapsed = " ".join("".join(cleaned_chars).split())
    # Loại bỏ các dấu phẩy/chấm lặp lại bất thường
    while ",," in collapsed:
        collapsed = collapsed.replace(",,", ",")
    while "  " in collapsed:
        collapsed = collapsed.replace("  ", " ")
    return collapsed.strip(" ,.;:-")


def is_garbage_segment(text: str) -> bool:
    """Phát hiện đoạn Whisper ảo giác (toàn từ tiếng Anh rời rạc vô nghĩa khi video im lặng gõ code)."""
    if not text or "[Đoạn thao tác mã nguồn" in text:
        return True
    words = [w.strip(".,;:?!'\"()[]{}").lower() for w in text.split()]
    words = [w for w in words if w]
    if len(words) < 4:
        return True

    viet_words = sum(1 for w in words if any(c in VIET_DIACRITIC_CHARS for c in w))
    cpp_words = sum(1 for w in words if w in CPP_WHITELIST_TERMS)
    comma_count = text.count(",")

    viet_ratio = viet_words / len(words)
    # Rác Whisper điển hình: rất nhiều dấu phẩy liệt kê từ rời rạc, hầu như không có dấu tiếng Việt
    if comma_count >= 5 and viet_ratio < 0.18:
        return True
    if viet_ratio < 0.12 and cpp_words < 2:
        return True
    return False


def score_chunk_quality(raw_text: str, lesson_keywords: List[str]) -> float:
    """Chấm điểm độ sạch và mức độ giàu thông tin chuyên môn của chunk transcript."""
    clean = sanitize_transcript_text(raw_text)
    if not clean or is_garbage_segment(clean):
        return -10.0

    words = [w.strip(".,;:?!'\"()[]{}").lower() for w in clean.split()]
    words = [w for w in words if w]
    if not words:
        return -10.0

    viet_words = sum(1 for w in words if any(c in VIET_DIACRITIC_CHARS for c in w))
    viet_ratio = viet_words / len(words)
    cpp_hits = sum(1 for w in words if w in CPP_WHITELIST_TERMS)

    lower_clean = clean.lower()
    kw_hits = 0
    for kw in lesson_keywords:
        nkw = unicodedata.normalize("NFC", kw).lower().strip()
        if len(nkw) >= 3 and nkw in lower_clean:
            kw_hits += 1

    # Phạt nhẹ nếu mở đầu bằng lặp từ hoặc quá nhiều dấu hỏi đệm
    penalty = 0.0
    if lower_clean.count("ok") >= 3:
        penalty += 0.5
    if clean.count(",") >= 8 and viet_ratio < 0.30:
        penalty += 1.5

    return (viet_ratio * 3.0) + min(kw_hits, 4) * 1.2 + min(cpp_hits, 4) * 0.4 - penalty


def extract_clean_snippet(
    raw_text: str,
    lesson_keywords: List[str],
    max_len: int = 110,
) -> str:
    """Rút trích 1 câu/mệnh đề tiếng Việt sạch, tự nhiên nhất từ raw_text."""
    clean = sanitize_transcript_text(raw_text)
    if not clean or is_garbage_segment(clean):
        return ""

    # Tách ứng viên câu theo dấu kết thúc tự nhiên
    candidates: List[str] = []
    buf: List[str] = []
    for ch in clean:
        buf.append(ch)
        if ch in ".?!":
            seg = "".join(buf).strip(" .,;:?!-")
            if len(seg) >= 24:
                candidates.append(seg)
            buf = []
    tail = "".join(buf).strip(" .,;:?!-")
    if len(tail) >= 24:
        candidates.append(tail)

    if not candidates:
        candidates = [clean]

    best_seg = ""
    best_sc = -999.0
    for seg in candidates:
        if is_garbage_segment(seg):
            continue
        # Loại bỏ các câu hỏi đệm ngắn không mang thông tin
        seg_low = seg.lower()
        if seg_low.startswith(("ok không", "được không", "hiểu chưa")):
            continue
        sc = score_chunk_quality(seg, lesson_keywords)
        # Ưu tiên độ dài vừa phải (35..110 ký tự)
        if 35 <= len(seg) <= 120:
            sc += 0.8
        if sc > best_sc:
            best_sc = sc
            best_seg = seg

    if not best_seg:
        return ""

    # Cắt gọn ở ranh giới từ nếu vượt quá max_len
    if len(best_seg) > max_len:
        cut = best_seg[:max_len]
        last_space = cut.rfind(" ")
        if last_space > max_len // 2:
            cut = cut[:last_space]
        best_seg = cut.rstrip(" ,.;:-") + "..."

    # Viết hoa chữ cái đầu
    if best_seg and best_seg[0].islower():
        best_seg = best_seg[0].upper() + best_seg[1:]
    return best_seg


def format_binding_label(binding_key_suffix: str) -> str:
    """Chuyển tên symbol AST thành mô tả rõ nghĩa cho học viên."""
    s = binding_key_suffix
    if s == "header_preamble":
        return "Khai báo thư viện & cấu trúc mở đầu chương trình"
    if s == "type_class_specifier":
        return "Định nghĩa Class, thuộc tính và phạm vi truy cập"
    if s == "function_main":
        return "Cài đặt và chạy thử nghiệm trong hàm main()"
    if s.startswith("function_operator"):
        op_name = s[len("function_") :]
        return f"Nạp chồng toán tử ({op_name})"
    if s.startswith("function_"):
        fn_name = s[len("function_") :]
        return f"Cài đặt hàm / phương thức `{fn_name}`"
    if s.startswith("type_"):
        tp_name = s[len("type_") :]
        return f"Định nghĩa kiểu dữ liệu `{tp_name}`"
    return f"Minh họa thành phần `{s}`"


def load_transcript_map() -> Dict[int, List[Dict[str, Any]]]:
    """Đọc toàn bộ 83 file *_chunks.json và lập chỉ mục theo lesson_seq (1..83)."""
    result: Dict[int, List[Dict[str, Any]]] = {}
    for path in sorted(TRANSCRIPTS_DIR.rglob("*_chunks.json")):
        name = path.name
        if not name.startswith("lesson-"):
            continue
        seq_str = name[len("lesson-") :].split("_", 1)[0]
        if not seq_str.isdigit():
            continue
        seq = int(seq_str)
        with open(path, "r", encoding="utf-8") as f:
            chunks = json.load(f)
        if isinstance(chunks, list):
            chunks.sort(key=lambda c: int(c.get("start_sec", 0)))
            result[seq] = chunks
    return result


def load_bindings_by_lesson() -> Dict[int, List[Tuple[int, str]]]:
    """Đọc lesson_code_video_binding.json và gom theo lesson_seq."""
    grouped: Dict[int, List[Tuple[int, str]]] = {}
    if not BINDING_PATH.exists():
        return grouped
    with open(BINDING_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    for k, sec in data.get("bindings", {}).items():
        if not k.startswith("lesson-") or ":" not in k:
            continue
        prefix, suffix = k.split(":", 1)
        seq_str = prefix[len("lesson-") :]
        if not seq_str.isdigit():
            continue
        seq = int(seq_str)
        grouped.setdefault(seq, []).append((int(sec), suffix))
    for seq in grouped:
        # Ưu tiên symbol đặc thù trước main/preamble khi trùng giây
        grouped[seq].sort(
            key=lambda x: (
                x[0],
                1 if x[1] in ("header_preamble", "function_main") else 0,
                x[1],
            )
        )
    return grouped


def build_chapters_for_lesson(
    lesson: Dict[str, Any],
    chunks: List[Dict[str, Any]],
    bindings: List[Tuple[int, str]],
) -> List[Dict[str, Any]]:
    """Sinh 5-8 chapter đại diện cho 1 bài học, sạch hoàn toàn CJK/Whisper garbage."""
    if not chunks:
        return []

    seq = int(lesson.get("seq", 0))
    title = str(lesson.get("title", f"Bài {seq}"))
    keywords = [str(k) for k in lesson.get("keywords", []) if isinstance(k, str)]
    duration = max(int(chunks[-1].get("end_sec", 0)), int(chunks[-1].get("start_sec", 0)), 60)

    n_chunks = len(chunks)
    if n_chunks < 20:
        target_count = 5
    elif n_chunks < 50:
        target_count = 6
    elif n_chunks < 100:
        target_count = 7
    else:
        target_count = 8

    min_gap = max(45, duration // (target_count + 3))

    # Map nhanh: với mỗi target_sec, tìm chunk sạch nhất lân cận
    def _pick_best_chunk_near(target_sec: int, window: int) -> Optional[Dict[str, Any]]:
        near = [
            ch for ch in chunks
            if abs(int(ch.get("start_sec", 0)) - target_sec) <= window
        ]
        if not near:
            near = chunks
        best_ch = None
        best_score = -999.0
        for ch in near:
            sc = score_chunk_quality(ch.get("raw_text", ""), keywords)
            dist_penalty = abs(int(ch.get("start_sec", 0)) - target_sec) / max(window, 1) * 0.6
            total = sc - dist_penalty
            if total > best_score:
                best_score = total
                best_ch = ch
        return best_ch

    selected_points: List[Tuple[int, str]] = []  # (sec, summary)

    def _is_too_close(sec: int) -> bool:
        return any(abs(sec - s) < min_gap for s, _ in selected_points)

    # 1. Điểm mở đầu (00:00 hoặc chunk đầu tiên)
    first_chunk = chunks[0] if chunks and not is_garbage_segment(sanitize_transcript_text(chunks[0].get("raw_text", ""))) else _pick_best_chunk_near(0, window=60)
    first_snippet = extract_clean_snippet(first_chunk.get("raw_text", "") if first_chunk else "", keywords)
    intro_summary = (
        f"Mở đầu bài học: {first_snippet}"
        if first_snippet and len(first_snippet) <= 85
        else (first_snippet or f"Giới thiệu mục tiêu {title}")
    )
    selected_points.append((0, intro_summary))

    # 2. Neo các mốc Code AST đặc thù (bỏ qua header_preamble gần 0s, tránh dồn sát nhau)
    specific_bindings = [
        (sec, suf) for sec, suf in bindings
        if suf != "header_preamble" and sec >= 60
    ]
    for b_sec, b_suf in specific_bindings:
        if len(selected_points) >= target_count - 1:
            break
        if b_sec > duration or _is_too_close(b_sec):
            continue
        desc = format_binding_label(b_suf)
        near_ch = _pick_best_chunk_near(b_sec, window=60)
        snip = extract_clean_snippet(near_ch.get("raw_text", "") if near_ch else "", keywords, max_len=70)
        summary = f"{desc} — {snip}" if snip else desc
        if len(summary) > 120:
            summary = summary[:117].rstrip(" ,.;:-") + "..."
        selected_points.append((b_sec, summary))

    # 3. Chia đều các khoảng thời gian còn thiếu để phủ trọn video
    slot_indices = range(1, target_count)
    for idx in slot_indices:
        if len(selected_points) >= target_count:
            break
        ideal_sec = int((duration * idx) / target_count)
        if _is_too_close(ideal_sec):
            continue
        window = max(90, duration // (target_count * 2))
        best_ch = _pick_best_chunk_near(ideal_sec, window=window)
        if not best_ch:
            continue
        ch_sec = int(best_ch.get("start_sec", ideal_sec))
        if _is_too_close(ch_sec):
            ch_sec = ideal_sec
        snip = extract_clean_snippet(best_ch.get("raw_text", ""), keywords, max_len=110)
        if not snip:
            # Dự phòng từ chủ đề bài học khi phân đoạn im lặng gõ code
            kw_hint = ", ".join(keywords[:3]) if keywords else title
            snip = f"Thực hành và minh họa mã nguồn về {kw_hint}"
        selected_points.append((ch_sec, snip))

    # Nếu vẫn chưa đủ target_count (do các điểm gần nhau), lấy thêm các chunk sạch còn trống
    if len(selected_points) < target_count:
        step = max(1, len(chunks) // (target_count + 1))
        for i in range(step, len(chunks), max(1, step // 2)):
            if len(selected_points) >= target_count:
                break
            ch = chunks[i]
            ch_sec = int(ch.get("start_sec", 0))
            if any(abs(ch_sec - s) < 30 for s, _ in selected_points):
                continue
            snip = extract_clean_snippet(ch.get("raw_text", ""), keywords, max_len=110)
            if not snip:
                kw_hint = ", ".join(keywords[:3]) if keywords else title
                snip = f"Triển khai ví dụ và phân tích {kw_hint}"
            selected_points.append((ch_sec, snip))

    # Sắp xếp tăng dần theo sec, đảm bảo sec duy nhất và không vượt quá target_count
    selected_points.sort(key=lambda x: x[0])
    chapters: List[Dict[str, Any]] = []
    seen_secs = set()
    for sec, summary in selected_points:
        if sec in seen_secs:
            continue
        seen_secs.add(sec)
        clean_sum = sanitize_transcript_text(summary)
        if not clean_sum:
            clean_sum = f"Nội dung {title} tại {format_mm_ss(sec)}"
        chapters.append(
            {
                "sec": int(sec),
                "label": format_mm_ss(sec),
                "summary": clean_sum,
            }
        )
        if len(chapters) >= 8:
            break

    return chapters


def main() -> int:
    if not MANIFEST_PATH.exists():
        print(f"ERROR: Missing manifest at {MANIFEST_PATH}", file=sys.stderr)
        return 1

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    transcripts = load_transcript_map()
    bindings = load_bindings_by_lesson()

    total_lessons = 0
    for course_id, course_data in manifest.get("courses", {}).items():
        for lesson in course_data.get("lessons", []):
            seq = int(lesson.get("seq", 0))
            chunks = transcripts.get(seq, [])
            lesson_bindings = bindings.get(seq, [])
            chapters = build_chapters_for_lesson(lesson, chunks, lesson_bindings)
            lesson["video_chapters"] = chapters
            total_lessons += 1

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Updated video_chapters for {total_lessons} lessons in {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
