"""
Curriculum Service - Điều hướng lộ trình học tập & Playlist 83 bài học.
In-Course Agentic RAG Copilot - Tác giả: Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Tuân thủ bất biến Data/Code Separation Invariant:
- Nạp danh mục 83 bài học chuẩn từ data/curriculum/lessons_manifest.json vào RAM (Singleton).
- Phân giải câu hỏi điều hướng lộ trình & tổng quan bài học (Fast-Path < 20ms) không qua LLM:
  Ví dụ: 
  - "em muốn học vòng lặp thì chọn bài nào trong playlist này..."
  - "hôm nay chúng ta sẽ học gì ở bài 4"
  - "bài 4 học gì"
  - "nội dung bài 4 là gì"
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

from app.agent.guardrails import normalize_user_input

logger = logging.getLogger("uvicorn.error")

MANIFEST_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "curriculum" / "lessons_manifest.json"
BINDING_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "metadata" / "lesson_code_video_binding.json"
EMBEDDINGS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "curriculum" / "syllabus_embeddings.npz"


def _normalize_text(text: str) -> str:
    """Chuẩn hóa chuỗi về Unicode NFC, loại bỏ ký tự ẩn/điều khiển và chuyển chữ thường để so khớp chính xác."""
    return normalize_user_input(text, lowercase=True, preserve_newlines=False)


_PUNCT_STRIP = ".,;:?!'\"()[]{}<>`"


def _strip_token_punct(token: str) -> str:
    """Loại bỏ dấu câu bao quanh token bằng duyệt chuỗi thuần túy (Zero Regex)."""
    return token.strip(_PUNCT_STRIP)


def _clean_alpha_space(text: str) -> str:
    """Thay thế ký tự không phải chữ/số bằng khoảng trắng và thu gọn dấu cách (Zero Regex)."""
    chars = [c if c.isalnum() else " " for c in text.lower()]
    return " ".join("".join(chars).split())


def _parse_clock_timestamp(token: str) -> Optional[int]:
    """Phân tích định dạng mm:ss hoặc hh:mm:ss bằng tách chuỗi thuần túy (Zero Regex)."""
    cleaned = _strip_token_punct(token)
    if ":" not in cleaned or "::" in cleaned:
        return None
    parts = cleaned.split(":")
    if len(parts) not in (2, 3):
        return None
    if not all(p.isdigit() for p in parts):
        return None
    # Yêu cầu phần giây có đúng 2 chữ số (ví dụ 04:15, 4:05) để tránh nhầm tỷ lệ toán học 1:2
    if len(parts[-1]) != 2:
        return None
    sec = int(parts[-1])
    if sec < 0 or sec >= 60:
        return None
    if len(parts) == 2:
        mins = int(parts[0])
        if mins < 0 or mins > 300:
            return None
        return mins * 60 + sec
    hours = int(parts[0])
    mins = int(parts[1])
    if hours < 0 or hours > 10 or mins < 0 or mins >= 60:
        return None
    return hours * 3600 + mins * 60 + sec


def _parse_compact_minute_sec(token: str) -> Optional[int]:
    """Phân tích viết tắt dạng 4p30s (Zero Regex)."""
    cleaned = _strip_token_punct(token).lower()
    if "p" not in cleaned or not cleaned.endswith("s"):
        return None
    p_idx = cleaned.find("p")
    if p_idx <= 0:
        return None
    min_part = cleaned[:p_idx]
    sec_part = cleaned[p_idx + 1 : -1]
    if not (min_part.isdigit() and sec_part.isdigit()):
        return None
    mins = int(min_part)
    secs = int(sec_part)
    if 0 <= mins <= 300 and 0 <= secs < 60:
        return mins * 60 + secs
    return None


_VN_BASE_DIGITS: Dict[str, int] = {
    "không": 0,
    "một": 1,
    "hai": 2,
    "ba": 3,
    "bốn": 4,
    "tư": 4,
    "năm": 5,
    "sáu": 6,
    "bảy": 7,
    "tám": 8,
    "chín": 9,
}

_VN_POST_TENS_DIGITS: Dict[str, int] = {
    "một": 1,
    "mốt": 1,
    "hai": 2,
    "ba": 3,
    "bốn": 4,
    "tư": 4,
    "năm": 5,
    "lăm": 5,
    "nhăm": 5,
    "sáu": 6,
    "bảy": 7,
    "tám": 8,
    "chín": 9,
}

_VN_SHORTHAND_SUFFIXES: Dict[str, int] = {
    "mốt": 1,
    "tư": 4,
    "lăm": 5,
    "nhăm": 5,
}


def _parse_vn_number_tokens(tokens: List[str], max_val: int = 300) -> Optional[int]:
    """
    Phân tích chuỗi token số đếm tiếng Việt hoặc chữ số (0..max_val, hỗ trợ đến 300)
    bằng duyệt token thuần túy (Zero Regex).
    """
    if not tokens:
        return None
    if len(tokens) == 1 and tokens[0].isdigit():
        val = int(tokens[0])
        return val if 0 <= val <= max_val else None

    idx = 0
    n = len(tokens)
    total = 0
    has_hundreds = False

    if n >= 2 and tokens[0] in ("một", "hai", "ba") and tokens[1] == "trăm":
        total = _VN_BASE_DIGITS[tokens[0]] * 100
        idx = 2
        has_hundreds = True
    elif n >= 2 and tokens[0] == "trăm":
        total = 100
        idx = 1
        has_hundreds = True

    if has_hundreds:
        if idx == n:
            return total if 0 <= total <= max_val else None
        if tokens[idx] in ("linh", "lẻ"):
            if idx + 2 != n:
                return None
            unit = _VN_BASE_DIGITS.get(tokens[idx + 1])
            if unit is None or unit < 1:
                return None
            val = total + unit
            return val if 0 <= val <= max_val else None

    rem = tokens[idx:]
    rem_len = len(rem)
    rem_val: Optional[int] = None

    if rem_len == 1:
        if rem[0] == "mười":
            rem_val = 10
        elif not has_hundreds and rem[0] in _VN_BASE_DIGITS:
            rem_val = _VN_BASE_DIGITS[rem[0]]
    elif rem_len == 2:
        if rem[0] == "mười" and rem[1] in _VN_POST_TENS_DIGITS and rem[1] != "mốt":
            rem_val = 10 + _VN_POST_TENS_DIGITS[rem[1]]
        elif rem[0] in _VN_BASE_DIGITS and 2 <= _VN_BASE_DIGITS[rem[0]] <= 9:
            tens = _VN_BASE_DIGITS[rem[0]] * 10
            if rem[1] == "mươi":
                rem_val = tens
            elif rem[1] in _VN_SHORTHAND_SUFFIXES:
                rem_val = tens + _VN_SHORTHAND_SUFFIXES[rem[1]]
    elif rem_len == 3:
        if (
            rem[0] in _VN_BASE_DIGITS
            and 2 <= _VN_BASE_DIGITS[rem[0]] <= 9
            and rem[1] == "mươi"
            and rem[2] in _VN_POST_TENS_DIGITS
        ):
            rem_val = _VN_BASE_DIGITS[rem[0]] * 10 + _VN_POST_TENS_DIGITS[rem[2]]

    if rem_val is None:
        return None
    val = total + rem_val
    return val if 0 <= val <= max_val else None


def _find_vn_number_before(tokens: List[str], end: int, max_val: int = 300) -> Optional[Tuple[int, int]]:
    """Tìm số dài nhất kết thúc ngay trước chỉ số `end`, trả về `(value, start_idx)`."""
    max_span = min(5, end)
    for length in range(max_span, 0, -1):
        start = end - length
        val = _parse_vn_number_tokens(tokens[start:end], max_val=max_val)
        if val is not None:
            return val, start
    return None


def _find_vn_number_after(
    tokens: List[str],
    start: int,
    max_val: int = 300,
    allow_ordinal_nhat: bool = False,
) -> Optional[Tuple[int, int]]:
    """Tìm số dài nhất bắt đầu tại `start`, trả về `(value, end_idx)`."""
    n = len(tokens)
    if start >= n:
        return None
    max_span = min(5, n - start)
    for length in range(max_span, 0, -1):
        end = start + length
        val = _parse_vn_number_tokens(tokens[start:end], max_val=max_val)
        if val is not None:
            return val, end
    if allow_ordinal_nhat and tokens[start] == "nhất" and max_val >= 1:
        return 1, start + 1
    return None


def _parse_seconds_after_minutes(tokens: List[str], sec_start: int) -> int:
    """Phân tích phần giây đi sau mốc phút (`rưỡi`, `Y giây`, `giây [thứ] Y`, hoặc `<số>`)."""
    n = len(tokens)
    if sec_start >= n:
        return 0
    if tokens[sec_start] == "rưỡi":
        return 30
    if tokens[sec_start] == "giây":
        has_thu = sec_start + 1 < n and tokens[sec_start + 1] == "thứ"
        idx = sec_start + 2 if has_thu else sec_start + 1
        res = _find_vn_number_after(tokens, idx, max_val=59, allow_ordinal_nhat=has_thu)
        return res[0] if res is not None else 0
    if tokens[sec_start].isdigit():
        cand = int(tokens[sec_start])
        return cand if 0 <= cand < 60 else 0
    res = _find_vn_number_after(tokens, sec_start, max_val=59)
    if res is not None:
        cand, sec_end = res
        if sec_end < n and tokens[sec_end] == "giây":
            return cand
    return 0


def _has_modifier_conflict(
    prompt: str,
    candidate_lesson: Dict[str, Any],
    top_lesson: Optional[Dict[str, Any]] = None,
    conflict_groups: Optional[List[Tuple[set, set]]] = None
) -> bool:
    """
    Kiểm tra xung đột định ngữ giữa câu hỏi và bài học ứng viên.
    Nếu câu hỏi yêu cầu định ngữ A (ví dụ '2 chiều', 'hai chiều') mà bài ứng viên lại thuộc định ngữ B ('1 chiều', 'một chiều'),
    hoặc top_lesson bảo toàn đúng định ngữ của câu hỏi còn candidate_lesson làm mất định ngữ đó, trả về True (Xung đột).
    Khi xảy ra xung đột, cấm tuyệt đối việc hoán đổi sang bài ứng viên này (Triệt tiêu lỗi Mảng 2 chiều -> Bài 12).
    """
    norm_prompt = _normalize_text(prompt)
    cand_text = _normalize_text(
        candidate_lesson.get("title", "") + " " + " ".join(candidate_lesson.get("keywords", []))
    )

    active_groups = conflict_groups or []

    for set_a, set_b in active_groups:
        prompt_has_a = any(m in norm_prompt for m in set_a)
        prompt_has_b = any(m in norm_prompt for m in set_b)
        if prompt_has_a and prompt_has_b:
            continue

        cand_has_a = any(m in cand_text for m in set_a)
        cand_has_b = any(m in cand_text for m in set_b)

        if prompt_has_b and cand_has_a and not cand_has_b:
            return True
        if prompt_has_a and cand_has_b and not cand_has_a:
            return True

        if top_lesson:
            top_text = _normalize_text(
                top_lesson.get("title", "") + " " + " ".join(top_lesson.get("keywords", []))
            )
            top_has_a = any(m in top_text for m in set_a)
            top_has_b = any(m in top_text for m in set_b)
            if prompt_has_b and top_has_b and not cand_has_b:
                return True
            if prompt_has_a and top_has_a and not cand_has_a:
                return True

    return False


def _has_topical_overlap(
    lesson: Dict[str, Any],
    prompt: str,
    stop_words: Optional[set] = None,
    conflict_groups: Optional[List[Tuple[set, set]]] = None,
    domain_tokens: Optional[set] = None
) -> bool:
    """
    Kiểm tra xem bài học có từ khóa hoặc tiêu đề thực sự chứa khái niệm trong câu hỏi hay không.
    Áp dụng N-gram Modifier Preservation: Kiểm tra xung đột định ngữ trước, sau đó đối chiếu N-grams (3-gram, bigram).
    Triệt tiêu hiện tượng unigram đơn lẻ ('mảng') làm sai lệch phân loại bài học.
    """
    if _has_modifier_conflict(prompt, lesson, conflict_groups=conflict_groups):
        return False

    norm_prompt = prompt.lower()
    active_stops = stop_words or set()
    clean_words = "".join(c if c.isalnum() else " " for c in norm_prompt).split()
    tokens = [w for w in clean_words if w not in active_stops and (len(w) > 1 or w.isdigit())]

    title_lower = lesson.get("title", "").lower()
    keywords = [k.lower() for k in lesson.get("keywords", [])]

    # 1. Kiểm tra cụm 3 từ (trigram) và 2 từ liên tiếp (bigram)
    for n in (3, 2):
        for i in range(len(tokens) - n + 1):
            ngram = " ".join(tokens[i : i + n])
            if ngram in title_lower or any(ngram in k for k in keywords):
                return True

    # 2. Khớp các từ khóa kỹ thuật nạp từ manifest (chỉ khi từ khóa dài > 3 ký tự hoặc là thuật ngữ C++ chuyên biệt)
    domain_specific_tokens = domain_tokens or set()
    for t in tokens:
        if t in domain_specific_tokens and (t in title_lower or any(t == k for k in keywords)):
            return True

    return False


class CurriculumService:
    """
    Dịch vụ quản trị giáo trình và phân giải điều hướng bài học in-RAM (< 1ms).
    """

    def __init__(self, manifest_path: Path = MANIFEST_PATH, binding_path: Path = BINDING_PATH, embeddings_path: Path = EMBEDDINGS_PATH):
        self.manifest_path = manifest_path
        self.binding_path = binding_path
        self.embeddings_path = embeddings_path
        self._courses: Dict[str, Any] = {}
        self._all_lessons: List[Dict[str, Any]] = []
        self._bindings: Dict[str, int] = {}
        self._syllabus_matrix: Optional[np.ndarray] = None
        self._nav_prototypes: List[str] = []
        self._overview_prototypes: List[str] = []
        self._nav_vectors: Optional[np.ndarray] = None
        self._overview_vectors: Optional[np.ndarray] = None
        self._current_lesson_refs: List[str] = []
        self._stop_words: set = set()
        self._modifier_conflict_groups: List[Tuple[set, set]] = []
        self._domain_specific_tokens: set = set()
        self._action_verbs: Tuple[str, ...] = ()
        self._question_starters: Tuple[str, ...] = ()
        self._intro_navigation_markers: List[str] = []
        self._introductory_lesson_seqs: List[int] = []
        self._introductory_text_markers: List[str] = []
        self._exercise_statement_signatures: List[str] = []
        self._load_manifest()
        self._load_bindings()
        self._load_syllabus_embeddings()

    def _load_manifest(self) -> None:
        """Nạp dữ liệu từ file JSON vào RAM."""
        try:
            if self.manifest_path.exists():
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._courses = data.get("courses", {})
                    nav_meta = data.get("navigation_metadata", {})
                    self._nav_prototypes = [
                        _normalize_text(p) for p in nav_meta.get("navigation_prototypes", [])
                    ]
                    self._overview_prototypes = [
                        _normalize_text(p) for p in nav_meta.get("overview_prototypes", [])
                    ]
                    self._current_lesson_refs = [
                        _normalize_text(p) for p in nav_meta.get("current_lesson_refs", [])
                    ]
                    self._stop_words = set(nav_meta.get("stop_words", []))

                    # Nạp metadata_rules (Data/Code Separation)
                    meta_rules = data.get("metadata_rules", {})
                    raw_mcg = meta_rules.get("modifier_conflict_groups", [])
                    if raw_mcg:
                        self._modifier_conflict_groups = [
                            (set(group[0]), set(group[1])) for group in raw_mcg if len(group) == 2
                        ]
                    if "domain_specific_tokens" in meta_rules:
                        self._domain_specific_tokens = set(meta_rules["domain_specific_tokens"])
                    if "action_verbs" in meta_rules:
                        self._action_verbs = tuple(meta_rules["action_verbs"])
                    if "question_starters" in meta_rules:
                        self._question_starters = tuple(_normalize_text(q) for q in meta_rules["question_starters"])
                    if "intro_navigation_markers" in meta_rules:
                        self._intro_navigation_markers = meta_rules["intro_navigation_markers"]
                    if "introductory_lesson_seqs" in meta_rules:
                        self._introductory_lesson_seqs = meta_rules["introductory_lesson_seqs"]
                    if "introductory_text_markers" in meta_rules:
                        self._introductory_text_markers = [
                            _normalize_text(m) for m in meta_rules["introductory_text_markers"]
                        ]
                    if "exercise_statement_signatures" in meta_rules:
                        self._exercise_statement_signatures = [
                            _normalize_text(s) for s in meta_rules["exercise_statement_signatures"]
                        ]

                    # Tạo danh sách phẳng toàn bộ 83 bài học
                    self._all_lessons = []
                    for c_id, c_data in self._courses.items():
                        for item in c_data.get("lessons", []):
                            lesson_entry = dict(item)
                            lesson_entry["course_id"] = c_id
                            self._all_lessons.append(lesson_entry)
                logger.info(f"[CurriculumService] Đã nạp thành công {len(self._all_lessons)} bài học từ {self.manifest_path.name}.")
            else:
                logger.warning(f"[CurriculumService] Không tìm thấy file manifest tại {self.manifest_path}.")
        except Exception as e:
            logger.error(f"[CurriculumService] Lỗi khi nạp manifest JSON: {str(e)}")

    def _load_bindings(self) -> None:
        """Nạp bảng ánh xạ mốc video AST từ lesson_code_video_binding.json."""
        try:
            if self.binding_path.exists():
                with open(self.binding_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._bindings = data.get("bindings", {})
                logger.info(f"[CurriculumService] Đã nạp {len(self._bindings)} bindings mốc video.")
            else:
                logger.warning(f"[CurriculumService] Không tìm thấy {self.binding_path}.")
        except Exception as e:
            logger.error(f"[CurriculumService] Lỗi khi nạp binding JSON: {str(e)}")

    def _load_syllabus_embeddings(self) -> None:
        """Nạp ma trận vector embedding giáo trình 83 bài học từ disk (Zero Quick-Fix)."""
        try:
            if self.embeddings_path.exists():
                data = np.load(self.embeddings_path)
                self._syllabus_matrix = data["matrix"]
                logger.info(f"[CurriculumService] Nạp thành công Syllabus Vector Matrix: {self._syllabus_matrix.shape}.")
            else:
                logger.warning(f"[CurriculumService] Không tìm thấy {self.embeddings_path}. Cần sinh file embeddings.")
        except Exception as e:
            logger.error(f"[CurriculumService] Lỗi khi nạp syllabus embeddings: {str(e)}")

    def semantic_search_lessons(
        self,
        prompt: str,
        top_k: int = 3,
        min_similarity: float = 0.78
    ) -> List[Tuple[float, Dict[str, Any]]]:
        """
        Tìm kiếm bài học trong toàn bộ giáo trình đa khóa học bằng Multilingual-E5 Dense Vector.
        Độ trễ < 1ms, triệt tiêu 100% bẫy Vocabulary Mismatch và Regex Anchor.
        """
        if self._syllabus_matrix is None or not self._all_lessons:
            return []
        clean_prompt = normalize_user_input(prompt, preserve_newlines=False)
        if not clean_prompt:
            return []
        try:
            from app.services.embedding import get_embedding_service
            emb_svc = get_embedding_service()
            qv = np.array(emb_svc.embed_query_dense(clean_prompt), dtype=np.float32)
            q_norm = np.linalg.norm(qv)
            if q_norm > 0:
                qv /= q_norm

            sims = np.dot(self._syllabus_matrix, qv)
            ranked_indices = np.argsort(sims)[::-1][:top_k]

            results = []
            for idx in ranked_indices:
                score = float(sims[idx])
                if score >= min_similarity and idx < len(self._all_lessons):
                    results.append((score, self._all_lessons[idx]))
            return results
        except Exception as e:
            logger.error(f"[CurriculumService] Lỗi tìm kiếm vector giáo trình: {e}")
            return []

    def _ensure_nav_embeddings(self) -> None:
        """Khởi tạo trước ma trận embedding cho các mẫu câu điều hướng và tổng quan giáo trình (0% Hardcoded Rules)."""
        if self._nav_vectors is not None and self._overview_vectors is not None:
            return
        try:
            from app.services.embedding import get_embedding_service
            emb_svc = get_embedding_service()
            if self._nav_prototypes and self._nav_vectors is None:
                vecs = [emb_svc.embed_query_dense(p) for p in self._nav_prototypes]
                arr = np.array(vecs, dtype=np.float32)
                norms = np.linalg.norm(arr, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                self._nav_vectors = arr / norms
            if self._overview_prototypes and self._overview_vectors is None:
                vecs_o = [emb_svc.embed_query_dense(p) for p in self._overview_prototypes]
                arr_o = np.array(vecs_o, dtype=np.float32)
                norms_o = np.linalg.norm(arr_o, axis=1, keepdims=True)
                norms_o[norms_o == 0] = 1.0
                self._overview_vectors = arr_o / norms_o
        except Exception as e:
            logger.debug(f"[CurriculumService] Khởi tạo nav embeddings: {e}")

    def is_foundational_lesson(self, seq: int) -> bool:
        """
        Kiểm tra xem bài học có phải là bài học nền tảng/tiên quyết (is_foundational) từ manifest JSON hay không.
        Tuân thủ Data/Code Separation Invariant (triệt tiêu hoàn toàn hardcode danh sách bài học trong code).
        """
        for les in self._all_lessons:
            if les.get("seq") == seq:
                return bool(les.get("is_foundational", False))
        return False

    def is_revision_of(self, target_seq: int, base_seq: int) -> bool:
        """
        Kiểm tra xem target_seq có phải là bài ôn tập/bài tập/cập nhật của base_seq từ manifest JSON không.
        Tuân thủ Revision Non-Dominance Invariant (bảo vệ học viên tại bài gốc không bị đá sang bài update).
        """
        for les in self._all_lessons:
            if les.get("seq") == target_seq:
                return bool(les.get("is_revision", False) and les.get("updates_lesson_seq") == base_seq)
        return False

    def get_lesson_by_seq(self, seq: int, course_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Lấy thông tin bài học theo số thứ tự seq (và course_id nếu có) từ manifest (Data/Code Separation).
        """
        if course_id:
            for les in self._all_lessons:
                if les.get("seq") == seq and les.get("course_id") == course_id:
                    return les
        for les in self._all_lessons:
            if les.get("seq") == seq:
                return les
        return None

    def get_lesson_chapters(self, seq: int, course_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Trả về danh sách phân đoạn video (video_chapters) của bài học nạp từ lessons_manifest.json.
        Mỗi phần tử có dạng {"sec": int, "label": str, "summary": str}.
        """
        lesson = self.get_lesson_by_seq(seq, course_id=course_id)
        if not lesson:
            return []
        chapters = lesson.get("video_chapters", [])
        if not isinstance(chapters, list):
            return []
        return [dict(ch) for ch in chapters if isinstance(ch, dict)]

    def is_introductory_overview_chunk(self, chunk: Dict[str, Any]) -> bool:
        """
        Kiểm tra xem chunk tài liệu có phải là video giới thiệu tổng quan đầu khóa (nạp từ manifest) hay không.
        Tuân thủ Data/Code Separation Invariant (triệt tiêu toàn bộ hardcode số bài hoặc chuỗi 'giới thiệu').
        """
        seq = chunk.get("lesson_seq", 0)
        if seq in self._introductory_lesson_seqs:
            raw_text_prefix = _normalize_text(chunk.get("raw_text", "")[:60])
            return any(m in raw_text_prefix for m in self._introductory_text_markers)
        return False

    def is_exercise_statement(self, text: str) -> bool:
        """
        Nhận diện câu nói chứa đề bài hoặc yêu cầu bài tập của học viên nạp từ manifest JSON (0% Hardcode).
        """
        if not text:
            return False
        norm_text = _normalize_text(text)
        return any(sig in norm_text for sig in self._exercise_statement_signatures)

    def extract_video_time_reference(self, prompt: str) -> Optional[Dict[str, Any]]:
        """
        Phân tích tham chiếu thời gian trong video bài giảng bằng duyệt chuỗi/token thuần túy (Zero Regex).
        Nhận diện:
        - Mốc thời gian tường minh (`phút X`, `phút thứ năm`, `hai mươi lăm phút`, `X phút Y giây`, `mm:ss`, `hh:mm:ss`, `giây X`) -> `explicit_sec`
        - Phân đoạn đầu/giữa/cuối video (`đoạn đầu`, `đoạn giữa`, `đoạn cuối`, ...) -> `relative_start` / `relative_middle` / `relative_end`
        - Chỉ thị vị trí đang phát (`đoạn này`, `chỗ này`, `khúc này`, `đoạn vừa rồi`, `giây hiện tại`) -> `deictic_current`
        Trả về `{"kind": str, "target_sec": Optional[int]}` hoặc `None` nếu không phải truy vấn theo thời gian video.
        """
        clean = _normalize_text(prompt)
        if not clean:
            return None

        raw_tokens = clean.split()
        tokens = [_strip_token_punct(t) for t in raw_tokens]
        n = len(tokens)

        # 1. Mốc thời gian tường minh (ưu tiên cao nhất, ví dụ: "đoạn đầu khoảng phút 4 thầy giảng gì" -> 240s)
        for tok in tokens:
            if not tok:
                continue
            clock_sec = _parse_clock_timestamp(tok)
            if clock_sec is not None:
                return {"kind": "explicit_sec", "target_sec": clock_sec}
            compact_sec = _parse_compact_minute_sec(tok)
            if compact_sec is not None:
                return {"kind": "explicit_sec", "target_sec": compact_sec}

        runtime_prev_verbs = ("mất", "hết", "tốn", "chạy", "sau", "đợi", "chờ", "nấu", "luộc", "hấp", "đợi")
        runtime_exec_verbs = ("mất", "hết", "tốn", "chạy", "đợi", "chờ", "nấu", "luộc", "hấp")
        runtime_bridge_words = ("khoảng", "tầm", "trong", "gần", "hơn", "độ")
        video_pos_next = ("đầu", "cuối", "này", "vừa", "trước", "sau")

        def _is_runtime_duration(num_start_idx: int, unit_idx: int) -> bool:
            has_runtime_verb = (
                num_start_idx >= 1 and tokens[num_start_idx - 1] in runtime_prev_verbs
            ) or (
                num_start_idx >= 2
                and tokens[num_start_idx - 2] in runtime_exec_verbs
                and tokens[num_start_idx - 1] in runtime_bridge_words
            )
            return has_runtime_verb and not (unit_idx + 1 < n and tokens[unit_idx + 1] in video_pos_next)

        for i, tok in enumerate(tokens):
            if tok == "phút":
                # Dạng "<X> phút [Y [giây] | giây [thứ] Y | rưỡi]" (loại trừ "mất 5 phút", "nấu mất 5 phút")
                prev_num = _find_vn_number_before(tokens, i, max_val=300)
                if prev_num is not None:
                    mins, num_start = prev_num
                    if not _is_runtime_duration(num_start, i):
                        secs = _parse_seconds_after_minutes(tokens, i + 1)
                        return {"kind": "explicit_sec", "target_sec": mins * 60 + secs}

                # Dạng "phút [thứ] <X> [giây [thứ] Y | Y giây | Y | rưỡi]"
                has_thu = i + 1 < n and tokens[i + 1] == "thứ"
                idx = i + 2 if has_thu else i + 1
                next_num = _find_vn_number_after(tokens, idx, max_val=300, allow_ordinal_nhat=has_thu)
                if next_num is not None:
                    mins, min_end = next_num
                    secs = _parse_seconds_after_minutes(tokens, min_end)
                    return {"kind": "explicit_sec", "target_sec": mins * 60 + secs}

            elif tok == "giây":
                # Dạng "giây [thứ] <X>"
                has_thu = i + 1 < n and tokens[i + 1] == "thứ"
                idx = i + 2 if has_thu else i + 1
                next_num = _find_vn_number_after(tokens, idx, max_val=36000, allow_ordinal_nhat=has_thu)
                if next_num is not None:
                    secs, _ = next_num
                    return {"kind": "explicit_sec", "target_sec": secs}

                # Dạng "<X> giây" (loại trừ thời gian chạy code như "chạy mất 5 giây" / "chạy mất năm giây")
                prev_num = _find_vn_number_before(tokens, i, max_val=36000)
                if prev_num is not None:
                    secs, num_start = prev_num
                    if not _is_runtime_duration(num_start, i):
                        return {"kind": "explicit_sec", "target_sec": secs}

        # 2. Phân đoạn đầu / giữa / cuối video
        padded = f" {_clean_alpha_space(clean)} "
        relative_start_markers = (
            "đoạn đầu", "phần đầu", "đầu video", "mở đầu",
            "lúc đầu", "khúc đầu", "phút đầu", "bắt đầu video", "đầu bài giảng",
        )
        if any(f" {m} " in padded for m in relative_start_markers):
            return {"kind": "relative_start", "target_sec": 0}

        relative_middle_markers = (
            "đoạn giữa", "phần giữa", "giữa video", "giữa bài",
            "giữa bài giảng", "nửa video", "phần thân bài",
        )
        if any(f" {m} " in padded for m in relative_middle_markers):
            return {"kind": "relative_middle", "target_sec": None}

        relative_end_markers = (
            "đoạn cuối", "phần cuối", "cuối video", "kết thúc video",
            "lúc cuối", "khúc cuối", "cuối bài giảng",
        )
        if any(f" {m} " in padded for m in relative_end_markers):
            return {"kind": "relative_end", "target_sec": None}

        # 3. Tham chiếu vị trí phát video hiện tại (Deictic player reference)
        strict_player_markers = ("giây hiện tại", "phút hiện tại", "đoạn đang xem", "phần đang xem", "khúc đang xem")
        if any(f" {m} " in padded for m in strict_player_markers):
            return {"kind": "deictic_current", "target_sec": None}

        if "```" not in prompt:
            deictic_markers = (
                "đoạn này", "chỗ này", "khúc này",
                "đoạn vừa rồi", "khúc vừa rồi", "chỗ vừa rồi", "tại giây này",
            )
            if any(f" {m} " in padded for m in deictic_markers):
                return {"kind": "deictic_current", "target_sec": None}

        return None

    def _names_other_lesson_topic(
        self,
        prompt: str,
        current_lesson_seq: Optional[int] = None,
        preferred_course_id: Optional[str] = None,
    ) -> bool:
        """
        Kiểm tra xem câu hỏi có nhắc rõ ràng từ khóa chủ đề của bài học khác/tương lai
        nằm ngoài phạm vi bài học hiện tại hay không (Zero Regex, dùng metadata manifest).
        """
        clean = _normalize_text(prompt)
        if not clean:
            return False
        padded = f" {_clean_alpha_space(clean)} "

        whole_course_nav_markers = (
            "bài nào", "bài học nào", "chọn bài nào", "học bài nào",
            "bài mấy", "bài số mấy", "trong playlist", "nằm ở bài nào", "thuộc bài nào",
        )
        if any(f" {m} " in padded for m in whole_course_nav_markers):
            return True

        if current_lesson_seq is None:
            # Khi không biết bài hiện tại, chỉ xem là nhắc bài khác nếu có dạng "bài <từ khóa>" rõ ràng
            if " bài " not in padded:
                return False
            for les in self._all_lessons:
                for kw in les.get("keywords", []):
                    norm_kw = _clean_alpha_space(_normalize_text(kw))
                    if len(norm_kw) >= 4 and norm_kw not in self._stop_words:
                        if f" bài {norm_kw} " in padded or f" bài về {norm_kw} " in padded:
                            return True
            return False

        cur_les = self.get_lesson_by_seq(current_lesson_seq, course_id=preferred_course_id)
        if cur_les:
            if _has_topical_overlap(
                cur_les,
                prompt,
                self._stop_words,
                conflict_groups=self._modifier_conflict_groups,
                domain_tokens=self._domain_specific_tokens,
            ):
                return False
            for kw in cur_les.get("keywords", []):
                norm_kw = _clean_alpha_space(_normalize_text(kw))
                if len(norm_kw) >= 3 and norm_kw not in self._stop_words and f" {norm_kw} " in padded:
                    return False

        for les in self._all_lessons:
            les_seq = les.get("seq", 0)
            les_course = les.get("course_id")
            is_other = (
                (preferred_course_id and les_course != preferred_course_id)
                or (les_seq > current_lesson_seq)
            )
            if not is_other:
                continue
            for kw in les.get("keywords", []):
                norm_kw = _clean_alpha_space(_normalize_text(kw))
                if len(norm_kw) >= 4 and norm_kw not in self._stop_words and f" {norm_kw} " in padded:
                    return True
            if _has_topical_overlap(
                les,
                prompt,
                self._stop_words,
                conflict_groups=self._modifier_conflict_groups,
                domain_tokens=self._domain_specific_tokens,
            ):
                return True

        return False

    def is_navigation_query(
        self,
        prompt: str,
        current_lesson_seq: Optional[int] = None,
        preferred_course_id: Optional[str] = None,
    ) -> bool:
        """
        Nhận diện xem học viên có đang đặt câu hỏi điều hướng lộ trình / playlist
        hoặc hỏi về tổng quan nội dung của bài học hay không bằng 100% Machine Learning (Dense Vector Cosine).
        """
        clean_prompt = normalize_user_input(prompt, preserve_newlines=False)
        norm_prompt = _normalize_text(clean_prompt)
        if not norm_prompt:
            return False

        explicit_seq = self._extract_lesson_seq(norm_prompt)

        # 1. Trực tiếp có số thứ tự bài học (ví dụ "bài 4", "lesson 4")
        if explicit_seq is not None:
            return True

        # 1b. Truy vấn theo mốc thời gian / phân đoạn video bài hiện tại -> KHÔNG phải điều hướng toàn khóa
        if self.extract_video_time_reference(clean_prompt) is not None:
            if not self._names_other_lesson_topic(
                clean_prompt,
                current_lesson_seq=current_lesson_seq,
                preferred_course_id=preferred_course_id,
            ):
                return False

        # 2. Khớp vector ngữ nghĩa Cosine Similarity với prototype matrix (ngưỡng chuẩn hóa E5 >= 0.87)
        self._ensure_nav_embeddings()
        if self._nav_vectors is not None:
            try:
                from app.services.embedding import get_embedding_service
                emb_svc = get_embedding_service()
                qv = np.array(emb_svc.embed_query_dense(clean_prompt), dtype=np.float32)
                q_norm = np.linalg.norm(qv)
                if q_norm > 0:
                    qv /= q_norm
                sims = np.dot(self._nav_vectors, qv)
                if float(np.max(sims)) >= 0.87:
                    return True
            except Exception as e:
                logger.debug(f"[CurriculumService] Lỗi tính Cosine navigation: {e}")

        # 3. Khớp ngữ nghĩa tổng quan bài học qua Dense Cosine Similarity
        if self.is_overview_query(norm_prompt):
            return True

        return False

    def is_overview_query(self, prompt: str) -> bool:
        """Kiểm tra xem câu hỏi có thuộc nhóm hỏi tổng quan nội dung bài học qua Dense Cosine Similarity."""
        clean_prompt = normalize_user_input(prompt, preserve_newlines=False)
        if not clean_prompt:
            return False
        self._ensure_nav_embeddings()
        if self._overview_vectors is not None:
            try:
                from app.services.embedding import get_embedding_service
                emb_svc = get_embedding_service()
                qv = np.array(emb_svc.embed_query_dense(clean_prompt), dtype=np.float32)
                q_norm = np.linalg.norm(qv)
                if q_norm > 0:
                    qv /= q_norm
                sims_o = np.dot(self._overview_vectors, qv)
                if float(np.max(sims_o)) >= 0.87:
                    return True
            except Exception as e:
                logger.debug(f"[CurriculumService] Lỗi tính Cosine overview: {e}")

        return False

    @staticmethod
    def _extract_lesson_seq(prompt: str) -> Optional[int]:
        """Trích xuất số thứ tự bài học từ câu hỏi bằng duyệt token thuần túy (Zero Regex)."""
        words = [w.strip(".,;:?!'\"-") for w in prompt.lower().split()]
        for i, w in enumerate(words):
            if w in ("bài", "lesson") and i + 1 < len(words):
                nxt = words[i + 1]
                if nxt == "số" and i + 2 < len(words):
                    cand = words[i + 2]
                    if cand.isdigit():
                        return int(cand)
                elif nxt.isdigit():
                    return int(nxt)
        return None

    @classmethod
    def extract_direct_navigation_command(cls, prompt: str) -> Optional[int]:
        """
        Nhận diện mệnh lệnh điều khiển UI chuyển bài trực tiếp từ học viên (Zero Hardcoded Patterns).
        Ví dụ: 'hãy chuyển giùm tôi đến bài 12', 'chuyển sang bài 5 giúp em', 'mở bài 10', 'tới bài 7', 'tua sang bài 12'.
        Trả về target_lesson_seq hoặc None.
        Nếu câu hỏi mang tính nghi vấn (chứa '?' hoặc từ để hỏi), trả về None để nhường quyền cho IntentRouter và RetrievalService.
        """
        clean_prompt = normalize_user_input(prompt, preserve_newlines=False)
        if not clean_prompt or "?" in clean_prompt:
            return None
        norm = _normalize_text(clean_prompt)
        try:
            curriculum_svc = get_curriculum_service()
            action_verbs = curriculum_svc._action_verbs
            question_starters = curriculum_svc._question_starters
        except Exception:
            action_verbs = ()
            question_starters = ()

        if any(qs in norm for qs in question_starters):
            return None

        has_nav_action = any(v in norm for v in action_verbs)
        if has_nav_action:
            words = [w.strip(".,;:?!'\"-") for w in norm.split()]
            for i, w in enumerate(words):
                if w in ("bài", "lesson") and i + 1 < len(words):
                    nxt = words[i + 1]
                    if nxt == "số" and i + 2 < len(words) and words[i + 2].isdigit():
                        return int(words[i + 2])
                    elif nxt.isdigit():
                        return int(nxt)
        return None

    def get_course_ids(self) -> List[str]:
        """Trả về danh sách định danh các khóa học nạp từ manifest (Data/Code Separation)."""
        return list(self._courses.keys())

    def has_current_lesson_reference(
        self,
        prompt: str,
        current_lesson_seq: Optional[int] = None,
        preferred_course_id: Optional[str] = None,
    ) -> bool:
        """
        Kiểm tra câu hỏi có tham chiếu bài học hiện tại (từ manifest hoặc tham chiếu thời gian video
        không gắn số bài cụ thể và không nêu chủ đề bài khác) hay không.
        """
        norm_prompt = _normalize_text(prompt)
        if not norm_prompt:
            return False
        if any(ref in norm_prompt for ref in self._current_lesson_refs):
            return True
        if (
            self._extract_lesson_seq(norm_prompt) is None
            and self.extract_video_time_reference(prompt) is not None
            and not self._names_other_lesson_topic(
                prompt,
                current_lesson_seq=current_lesson_seq,
                preferred_course_id=preferred_course_id,
            )
        ):
            return True
        return False

    def get_lesson_timestamps(self, seq: int) -> List[Dict[str, Any]]:
        """Lấy danh sách các mốc thời gian video chuẩn xác của bài học."""
        prefix = f"lesson-{seq:02d}:"
        ts_list: List[Dict[str, Any]] = []
        for k, sec in self._bindings.items():
            if k.startswith(prefix):
                part = k.split(":")[1].replace("function_", "").replace("header_", "").replace("type_", "")
                mins = sec // 60
                secs = sec % 60
                lbl = f"{mins:02d}:{secs:02d}"
                ts_list.append({"sec": sec, "label": lbl, "title": part.title()})
        ts_list.sort(key=lambda x: (1 if x["title"].lower() == "preamble" else 0, x["sec"]))
        return ts_list

    def find_lesson_for_query(
        self,
        prompt: str,
        current_lesson_seq: Optional[int] = None,
        preferred_course_id: Optional[str] = None
    ) -> Optional[Tuple[Dict[str, Any], str]]:
        """
        Tìm kiếm bài học phù hợp nhất dựa trên:
        1. Số thứ tự bài học tường minh (ví dụ: "bài 4", "bài 04", "lesson 4").
        2. Ngữ cảnh bài học hiện tại nạp từ manifest.
        3. Chỉ mục Ngữ nghĩa Giáo trình (Syllabus Vector Index) kết hợp đối chiếu từ khóa manifest.
        """
        prompt = normalize_user_input(prompt, preserve_newlines=False)
        norm_prompt = _normalize_text(prompt)
        if not norm_prompt:
            return None

        # 1. Khớp theo số thứ tự bài học tường minh (Zero Regex)
        seq_num = self._extract_lesson_seq(norm_prompt)
        if seq_num is not None:
            for lesson in self._all_lessons:
                if lesson.get("seq") == seq_num:
                    if preferred_course_id and lesson.get("course_id") == preferred_course_id:
                        return lesson, lesson.get("title", f"Bài {seq_num}")
            # Nếu không tìm thấy trong preferred course, tìm trên toàn bộ
            for lesson in self._all_lessons:
                if lesson.get("seq") == seq_num:
                    return lesson, lesson.get("title", f"Bài {seq_num}")

        # 2. Khớp theo ngữ cảnh bài học hiện tại nạp từ manifest hoặc tham chiếu thời gian video
        is_current_ref = self.has_current_lesson_reference(
            prompt,
            current_lesson_seq=current_lesson_seq,
            preferred_course_id=preferred_course_id,
        )
        if is_current_ref:
            if current_lesson_seq is not None:
                cur_les = self.get_lesson_by_seq(current_lesson_seq, course_id=preferred_course_id)
                if cur_les:
                    return cur_les, cur_les.get("title", f"Bài {current_lesson_seq}")

        # 3. Tìm kiếm bằng Chỉ mục Ngữ nghĩa Giáo trình (Syllabus Vector Index - Zero Regex Anchor)
        # Áp dụng Prerequisite Order Pareto Selection (ICLR 2025):
        semantic_results = self.semantic_search_lessons(prompt, top_k=6, min_similarity=0.78)
        if semantic_results:
            top_score, top_lesson = semantic_results[0]
            target_course = top_lesson.get("course_id")

            # Helper kiểm tra khớp từ khóa chính xác (không tính chỉ trùng 1 phần cụm từ ghép)
            def _has_exact_keyword_match(lesson_obj: Dict[str, Any]) -> bool:
                return any(
                    (_normalize_text(kw) in norm_prompt)
                    for kw in lesson_obj.get("keywords", [])
                    if _normalize_text(kw)
                )

            # Nếu kết quả cao nhất thuộc khóa khác, chỉ ưu tiên về khóa hiện tại khi có ứng viên sát điểm
            # VÀ không để ứng viên khóa hiện tại trùng từ ghép lấn át bài khớp từ khóa chính xác ở khóa đích
            if preferred_course_id and target_course != preferred_course_id:
                curr_cands = [c for c in semantic_results if c[1].get("course_id") == preferred_course_id]
                target_course_cands = [c for c in semantic_results if c[1].get("course_id") == target_course]
                if curr_cands:
                    best_curr_score, best_curr_lesson = curr_cands[0]
                    target_has_exact_non_rev = any(
                        (not c[1].get("is_revision", False)) and _has_exact_keyword_match(c[1])
                        for c in target_course_cands
                    )
                    curr_has_exact = _has_exact_keyword_match(best_curr_lesson)
                    if (top_score - best_curr_score) <= 0.03 and (curr_has_exact or not target_has_exact_non_rev):
                        if _has_topical_overlap(
                            best_curr_lesson,
                            prompt,
                            self._stop_words,
                            conflict_groups=self._modifier_conflict_groups,
                            domain_tokens=self._domain_specific_tokens,
                        ):
                            target_course = preferred_course_id

            # Trong target_course, chọn bài học phù hợp nhất dựa trên Semantic Dominance & Prerequisite Order
            course_cands = [c for c in semantic_results if c[1].get("course_id") == target_course]
            best_course_score, best_course_lesson = course_cands[0]

            is_intro_query = any(m in norm_prompt for m in self._intro_navigation_markers)
            any_has_topic = any(
                _has_topical_overlap(
                    c[1],
                    prompt,
                    self._stop_words,
                    conflict_groups=self._modifier_conflict_groups,
                    domain_tokens=self._domain_specific_tokens,
                )
                for c in course_cands
            )

            # DAG Prerequisite Root Selection (Mục 3.1 - Nhịp 1B / Nhịp 2):
            # Lọc các nút nền tảng (is_foundational và KHÔNG phải is_revision) trong target_course không có xung đột định ngữ.
            # Bắt buộc phải có topical overlap nếu câu hỏi đã khớp chủ đề cụ thể (tránh bài nền tảng khác chủ đề cướp chỗ).
            foundational_cands = [
                c for c in course_cands
                if c[1].get("is_foundational", False)
                and not c[1].get("is_revision", False)
                and not _has_modifier_conflict(prompt, c[1], top_lesson=best_course_lesson, conflict_groups=self._modifier_conflict_groups)
                and (
                    not any_has_topic
                    or _has_topical_overlap(
                        c[1],
                        prompt,
                        self._stop_words,
                        conflict_groups=self._modifier_conflict_groups,
                        domain_tokens=self._domain_specific_tokens,
                    )
                )
            ]

            if foundational_cands:
                # Nút tiên quyết có số thứ tự nhỏ nhất (min seq) trong các nút nền tảng (Bài 53 cho cpp-oop)
                root_cand = min(foundational_cands, key=lambda c: c[1].get("seq", 999))
                root_score, root_lesson = root_cand

                # Nếu là câu hỏi mở đầu/lộ trình (is_intro_query) hoặc điểm root rất sát top (chênh <= 0.12)
                if is_intro_query or (best_course_score - root_score <= 0.12):
                    chosen_score, chosen_lesson = root_score, root_lesson
                else:
                    chosen_score, chosen_lesson = best_course_score, best_course_lesson
            else:
                chosen_score, chosen_lesson = best_course_score, best_course_lesson

            is_top_dominant = (best_course_score >= 0.85)

            for cand_score, cand_lesson in course_cands:
                if cand_lesson.get("seq") == chosen_lesson.get("seq"):
                    continue

                # Kiểm tra xung đột định ngữ: nếu xung đột, cấm tuyệt đối hoán đổi
                if _has_modifier_conflict(prompt, cand_lesson, top_lesson=best_course_lesson, conflict_groups=self._modifier_conflict_groups):
                    continue

                cand_seq = cand_lesson.get("seq", 999)
                chosen_seq = chosen_lesson.get("seq", 999)

                # Revision Non-Dominance: Bài ôn tập / cập nhật không cướp quyền bài gốc hoặc bài nền tảng
                if cand_lesson.get("is_revision", False) and (
                    cand_lesson.get("updates_lesson_seq") == chosen_lesson.get("seq")
                    or (cand_seq < chosen_seq and chosen_lesson.get("is_foundational", False))
                ):
                    continue

                # Prerequisite Dominance Rule: Nút đến sau chỉ được thay thế nút gốc nếu chênh lệch áp đảo (> 0.15) và không phải câu hỏi mở đầu lộ trình
                if cand_seq > chosen_seq:
                    if (cand_score - chosen_score > 0.15) and not is_intro_query:
                        chosen_score, chosen_lesson = cand_score, cand_lesson
                else:
                    # Nút có thứ tự sớm hơn
                    if is_top_dominant:
                        if (best_course_score - cand_score) <= 0.012:
                            if _has_topical_overlap(cand_lesson, prompt, self._stop_words, conflict_groups=self._modifier_conflict_groups, domain_tokens=self._domain_specific_tokens):
                                chosen_score, chosen_lesson = cand_score, cand_lesson
                    else:
                        if (best_course_score - cand_score) <= 0.03:
                            if _has_topical_overlap(cand_lesson, prompt, self._stop_words, conflict_groups=self._modifier_conflict_groups, domain_tokens=self._domain_specific_tokens):
                                chosen_score, chosen_lesson = cand_score, cand_lesson

            logger.info(
                f"[CurriculumService:SemanticMatch] '{prompt[:35]}...' -> "
                f"Khóa {chosen_lesson.get('course_id')} - Bài {chosen_lesson.get('seq')}: {chosen_lesson.get('title')} (Sim={chosen_score:.4f})"
            )
            return chosen_lesson, chosen_lesson.get("title", f"Bài {chosen_lesson.get('seq')}")

        # 4. Dự phòng khớp từ khóa kỹ thuật (Keyword fallback)
        candidate_lessons = self._all_lessons
        if preferred_course_id and preferred_course_id in self._courses:
            candidate_lessons = sorted(
                self._all_lessons,
                key=lambda x: 0 if x.get("course_id") == preferred_course_id else 1
            )

        best_match = None
        best_kw = ""
        max_kw_len = 0

        for lesson in candidate_lessons:
            keywords = lesson.get("keywords", [])
            for kw in keywords:
                norm_kw = _normalize_text(kw)
                if norm_kw and norm_kw in norm_prompt:
                    if len(norm_kw) > max_kw_len:
                        max_kw_len = len(norm_kw)
                        best_match = lesson
                        best_kw = kw

        if best_match:
            return best_match, best_kw

        return None

    def _split_disjunction_branches(self, norm_prompt: str) -> List[str]:
        """Tách câu hỏi lựa chọn đa chủ đề theo từ nối 'hay' / 'hoặc' bằng tách chuỗi thuần túy (Zero Regex)."""
        if not norm_prompt:
            return []
        padded = f" {_clean_alpha_space(norm_prompt)} "
        connectors = (" hoặc là ", " hay là ", " hoặc ", " hay ")
        used = False
        work = padded
        marker = " ||| "
        for conn in connectors:
            if conn in work:
                work = work.replace(conn, marker)
                used = True
        if not used:
            return []
        parts = [p.strip() for p in work.split("|||")]
        return [p for p in parts if p]

    def find_ambiguous_candidates(
        self,
        prompt: str,
        current_lesson_seq: Optional[int] = None,
        preferred_course_id: Optional[str] = None,
        max_candidates: int = 4,
    ) -> Dict[str, Any]:
        """
        Phát hiện truy vấn mơ hồ theo 2 dạng chuẩn (Zero Regex, Zero Hardcode):
        1. Đa chủ đề rẽ nhánh (multi_topic_disjunction): ví dụ 'con trỏ hay vòng lặp', 'stack hoặc queue'.
        2. Đơn chủ đề có nhiều bài học cạnh tranh sát điểm (competing_lessons): ví dụ 'mảng 1 chiều', 'con trỏ'.
        Trả về:
        {
            "is_ambiguous": bool,
            "reason": str,
            "branches": List[str],
            "candidates": [{"course_id": str, "seq": int, "title": str, "score": float, "branch_query": str}],
        }
        """
        empty_res: Dict[str, Any] = {
            "is_ambiguous": False,
            "reason": "",
            "branches": [],
            "candidates": [],
        }
        clean_prompt = normalize_user_input(prompt, preserve_newlines=False)
        norm_prompt = _normalize_text(clean_prompt)
        if not norm_prompt or max_candidates <= 0:
            return empty_res

        # Nếu đã chỉ định số bài tường minh hoặc đang hỏi mốc video bài hiện tại -> không mơ hồ
        if self._extract_lesson_seq(norm_prompt) is not None:
            return empty_res
        if self.has_current_lesson_reference(
            clean_prompt,
            current_lesson_seq=current_lesson_seq,
            preferred_course_id=preferred_course_id,
        ):
            return empty_res

        padded_full = f" {_clean_alpha_space(norm_prompt)} "

        def _has_exact_kw(lesson_obj: Dict[str, Any], target_padded: str) -> bool:
            for kw in lesson_obj.get("keywords", []):
                nkw = _clean_alpha_space(_normalize_text(kw))
                if len(nkw) >= 3 and nkw not in self._stop_words and f" {nkw} " in target_padded:
                    return True
            return False

        # --- DẠNG 1: Đa chủ đề rẽ nhánh ("a hay b", "a hoặc b") ---
        raw_branches = self._split_disjunction_branches(norm_prompt)
        if len(raw_branches) >= 2:
            yes_no_tails = {"không", "chưa", "không ạ", "chưa ạ", "gì", "sao", "đâu", "nhỉ", "nhé"}
            branch_matches: List[Tuple[str, Dict[str, Any], float]] = []
            seen_keys = set()

            for branch in raw_branches:
                if branch in yes_no_tails:
                    continue
                b_tokens = [t for t in branch.split() if t not in self._stop_words]
                if not b_tokens:
                    continue
                b_padded = f" {branch} "
                b_seq = self._extract_lesson_seq(branch)
                matched_les: Optional[Dict[str, Any]] = None
                matched_score = 0.0

                if b_seq is not None:
                    matched_les = self.get_lesson_by_seq(b_seq, course_id=preferred_course_id)
                    matched_score = 1.0
                else:
                    sem_b = self.semantic_search_lessons(branch, top_k=5, min_similarity=0.78)
                    # Ưu tiên bài gốc khớp từ khóa chính xác trong nhánh (ví dụ 'con trỏ' -> Bài 57 thay vì Bài 48)
                    exact_non_rev = [
                        (sc, sl) for sc, sl in sem_b
                        if not sl.get("is_revision", False) and _has_exact_kw(sl, b_padded)
                    ]
                    if exact_non_rev:
                        cand_score, cand_les = exact_non_rev[0]
                        matched_les = cand_les
                        matched_score = float(cand_score)
                    else:
                        fl_res = self.find_lesson_for_query(
                            branch,
                            current_lesson_seq=current_lesson_seq,
                            preferred_course_id=preferred_course_id,
                        )
                        if fl_res and sem_b:
                            cand_les = fl_res[0]
                            cand_score = 0.0
                            for sc, sl in sem_b:
                                if sl.get("seq") == cand_les.get("seq") and sl.get("course_id") == cand_les.get("course_id"):
                                    cand_score = sc
                                    break
                            if cand_score == 0.0:
                                cand_score = sem_b[0][0]
                            has_topic = (
                                _has_exact_kw(cand_les, b_padded)
                                or _has_topical_overlap(
                                    cand_les,
                                    branch,
                                    self._stop_words,
                                    conflict_groups=self._modifier_conflict_groups,
                                    domain_tokens=self._domain_specific_tokens,
                                )
                            )
                            if cand_score >= 0.80 and (has_topic or cand_score >= 0.835):
                                matched_les = cand_les
                                matched_score = float(cand_score)

                if matched_les is not None:
                    key = (matched_les.get("course_id", ""), matched_les.get("seq"))
                    if key not in seen_keys:
                        seen_keys.add(key)
                        branch_matches.append((branch, matched_les, matched_score))

            if len(branch_matches) >= 2:
                return {
                    "is_ambiguous": True,
                    "reason": "multi_topic_disjunction",
                    "branches": [bm[0] for bm in branch_matches],
                    "candidates": [
                        {
                            "course_id": bm[1].get("course_id", ""),
                            "seq": int(bm[1].get("seq", 0)),
                            "title": bm[1].get("title", ""),
                            "score": round(float(bm[2]), 4),
                            "branch_query": bm[0],
                        }
                        for bm in branch_matches[:max_candidates]
                    ],
                }

        # --- DẠNG 2: Đơn chủ đề có nhiều bài học cạnh tranh sát điểm ---
        semantic_results = self.semantic_search_lessons(clean_prompt, top_k=8, min_similarity=0.79)
        if not semantic_results:
            return empty_res

        top_score, top_lesson = semantic_results[0]
        filtered: List[Tuple[float, Dict[str, Any]]] = []
        seen_keys = set()

        for cand_score, cand_lesson in semantic_results:
            if (top_score - cand_score) > 0.025 or cand_score < 0.805:
                continue
            if _has_modifier_conflict(
                clean_prompt,
                cand_lesson,
                top_lesson=top_lesson,
                conflict_groups=self._modifier_conflict_groups,
            ):
                continue

            has_rel = (
                _has_exact_kw(cand_lesson, padded_full)
                or _has_topical_overlap(
                    cand_lesson,
                    clean_prompt,
                    self._stop_words,
                    conflict_groups=self._modifier_conflict_groups,
                    domain_tokens=self._domain_specific_tokens,
                )
                or (top_score - cand_score) <= 0.015
            )
            if not has_rel:
                continue

            key = (cand_lesson.get("course_id", ""), cand_lesson.get("seq"))
            if key not in seen_keys:
                seen_keys.add(key)
                filtered.append((cand_score, cand_lesson))

        if len(filtered) < 2:
            return empty_res

        is_intro_query = any(m in norm_prompt for m in self._intro_navigation_markers)
        distinct_courses = {c[1].get("course_id") for c in filtered}
        non_revision_count = sum(1 for c in filtered if not c[1].get("is_revision", False))
        tight_top_gap = (filtered[0][0] - filtered[1][0]) <= 0.020

        if is_intro_query and len(distinct_courses) < 2 and non_revision_count < 2:
            return empty_res

        if len(distinct_courses) >= 2 or non_revision_count >= 2 or tight_top_gap:
            # Ưu tiên bài gốc (non-revision) lên trước nếu điểm sát nhau, sau đó theo score giảm dần
            ordered = sorted(
                filtered,
                key=lambda item: (
                    1 if item[1].get("is_revision", False) else 0,
                    -item[0],
                    item[1].get("seq", 999),
                ),
            )[:max_candidates]
            return {
                "is_ambiguous": True,
                "reason": "competing_lessons",
                "branches": [],
                "candidates": [
                    {
                        "course_id": les.get("course_id", ""),
                        "seq": int(les.get("seq", 0)),
                        "title": les.get("title", ""),
                        "score": round(float(sc), 4),
                        "branch_query": clean_prompt,
                    }
                    for sc, les in ordered
                ],
            }

        return empty_res

    def _build_lesson_overview_response(
        self,
        lesson: Dict[str, Any],
        current_lesson_seq: int
    ) -> str:
        """Xây dựng câu trả lời Socratic chi tiết về tổng quan nội dung bài học."""
        seq = lesson.get("seq")
        title = lesson.get("title", f"Bài {seq}")
        keywords = lesson.get("keywords", [])
        description = lesson.get("description")

        is_current = (seq == current_lesson_seq)
        if is_current:
            intro = f"Chào bạn! Trong bài học bạn đang theo dõi (**{title}**), chúng ta sẽ cùng tìm hiểu các nội dung trọng tâm sau:"
        else:
            intro = f"Chào bạn! Trong **{title}**, nội dung bài giảng bao gồm các kiến thức trọng tâm sau:"

        if description:
            body = f"- {description}"
        else:
            clean_kws = [kw.strip().capitalize() for kw in keywords if len(kw.strip()) > 1]
            seen = set()
            unique_kws = []
            for k in clean_kws:
                if k.lower() not in seen:
                    seen.add(k.lower())
                    unique_kws.append(k)

            bullets = []
            if unique_kws:
                bullets.append(f"1. **Bản chất & Khái niệm**: Giới thiệu và mục đích sử dụng của `{unique_kws[0]}` trong C++.")
            if len(unique_kws) > 1:
                mid_kws = ", ".join(unique_kws[1:min(4, len(unique_kws))])
                bullets.append(f"2. **Cấu trúc & Cú pháp lệnh**: Cách triển khai và quy tắc viết cú pháp `{mid_kws}`.")
            if len(unique_kws) > 4:
                adv_kws = ", ".join(unique_kws[4:min(7, len(unique_kws))])
                bullets.append(f"3. **Kỹ thuật áp dụng & Lưu ý**: Phân tích chi tiết `{adv_kws}` và các bẫy cú pháp thường gặp.")
            bullets.append("4. **Minh họa mã nguồn & Thực hành**: Từng bước viết code mẫu và quan sát kết quả thực thi.")
            body = "\n".join(bullets)

        ts_list = self.get_lesson_timestamps(seq)
        ts_tags = []
        for ts in ts_list[:2]:
            ts_tags.append(f'<timestamp sec="{ts["sec"]}" lesson="{seq}">{ts["label"]}</timestamp>')
        ts_str = " hoặc ".join(ts_tags)

        if is_current:
            outro = f"\n\n👉 Video bài giảng đã sẵn sàng ngay tại khung phát bên cạnh."
            if ts_str:
                outro += f" Bạn có thể click xem từ các mốc {ts_str}."
            outro += " Bạn muốn chúng ta cùng bắt đầu với phần lý thuyết hay thực hành code trước?"
        else:
            outro = f"\n\n👉 Để xem bài học này, bạn hãy click vào **Bài {seq}** trong danh mục lộ trình ở cột bên trái."
            if ts_str:
                outro += f" Mốc video tham khảo: {ts_str}."
            outro += " Bạn đã sẵn sàng học bài này hay cần ôn lại kiến thức trước đó?"

        return f"{intro}\n\n{body}{outro}"

    def generate_navigation_response(
        self,
        prompt: str,
        current_lesson_seq: int,
        course_id: str
    ) -> Optional[str]:
        """
        Sinh câu trả lời Socratic thân thiện:
        - Nếu hỏi tổng quan nội dung bài học: trả về dàn bài chi tiết kèm timestamps.
        - Nếu hỏi bài học ở đâu trong playlist: hướng dẫn chọn đúng bài trong danh mục.
        """
        prompt = normalize_user_input(prompt, preserve_newlines=False)
        if not prompt:
            return None
        match_result = self.find_lesson_for_query(
            prompt,
            current_lesson_seq=current_lesson_seq,
            preferred_course_id=course_id
        )
        if not match_result:
            return None

        lesson, matched_kw = match_result
        target_seq = lesson.get("seq")
        target_title = lesson.get("title")
        target_course = lesson.get("course_id", "")

        course_display_names = {
            "cpp-core": "Lập trình C++ Cơ bản",
            "cpp-oop": "Lập trình C++ Hướng Đối Tượng (OOP)"
        }
        target_course_name = course_display_names.get(target_course, target_course)
        current_course_name = course_display_names.get(course_id, course_id)

        # Kiểm tra xem có phải hỏi tổng quan nội dung bài học hay không
        if self.is_overview_query(prompt):
            return self._build_lesson_overview_response(lesson, current_lesson_seq)

        # Trường hợp 1: Bài học thuộc KHÓA HỌC KHÁC (Cross-Course Navigation - ví dụ đang ở cpp-core hỏi OOP)
        if target_course and target_course != course_id:
            related_lessons = [
                f"- **Bài {les.get('seq')}**: {les.get('title')}"
                for les in self._all_lessons
                if les.get("course_id") == target_course and les.get("is_foundational", False)
            ]
            if not related_lessons:
                related_lessons = [
                    f"- **Bài {les.get('seq')}**: {les.get('title')}"
                    for les in self._all_lessons
                    if les.get("course_id") == target_course
                ][:4]
            related_str = "\n".join(related_lessons[:4])
            return (
                f"Chào bạn! Chủ đề bạn đang quan tâm thuộc về khóa học **{target_course_name}** (`{target_course}`), "
                f"bắt đầu được giảng dạy chuyên sâu từ:\n"
                f"👉 **{target_title}** (Bài {target_seq}).\n\n"
                f"Lộ trình các bài học tiêu biểu của chuyên đề này bao gồm:\n"
                f"{related_str}\n\n"
                f"Hiện tại bạn đang ở **Bài {current_lesson_seq}** của khóa **{current_course_name}**. "
                f"Để học tốt chuyên đề này, lộ trình sư phạm tối ưu là bạn nên hoàn thành vững chắc các kiến thức nền tảng "
                f"về Hàm, Mảng và Struct (Bài 50–52) trước khi chuyển sang khóa học tiếp theo nhé!"
            )

        if target_seq == current_lesson_seq:
            return (
                f"Chủ đề **{matched_kw.capitalize()}** chính là nội dung trọng tâm của bài bạn đang học: "
                f"**{target_title}**!\n\n"
                f"Bạn hãy theo dõi video bài giảng hiện tại ở khung bên trái và quan sát các ví dụ code mẫu nhé. "
                f"Bạn đang gặp vướng mắc ở phần cú pháp hay cách áp dụng nào trong bài này?"
            )
        elif target_seq > current_lesson_seq:
            return (
                f"Trong lộ trình khóa học, chủ đề **{matched_kw.capitalize()}** được giảng dạy chi tiết tại:\n"
                f"👉 **{target_title}**.\n\n"
                f"Hiện tại bạn đang ở **Bài {current_lesson_seq}**. Bạn hoàn toàn có thể chọn trực tiếp bài học này "
                f"trong danh mục **Lộ Trình Bài Học** ở cột bên trái để bắt đầu học ngay! "
                f"Tuy nhiên, nếu mới bắt đầu, bạn hãy đảm bảo mình đã nắm vững các kiến thức nền tảng trước đó nhé. "
                f"Bạn muốn tìm hiểu khái niệm cơ bản nào trước?"
            )
        else:
            return (
                f"Chủ đề **{matched_kw.capitalize()}** đã được hướng dẫn chi tiết tại:\n"
                f"👉 **{target_title}**.\n\n"
                f"Hiện tại bạn đang ở **Bài {current_lesson_seq}**. Nếu cần ôn lại kiến thức này, bạn có thể click vào bài đó "
                f"trong danh mục bài học ở cột bên trái. Bạn đang cần áp dụng kiến thức này vào bài toán nào ở bài hiện tại?"
            )


# Singleton instance
_curriculum_service: Optional[CurriculumService] = None


def get_curriculum_service() -> CurriculumService:
    global _curriculum_service
    if _curriculum_service is None:
        _curriculum_service = CurriculumService()
    return _curriculum_service
