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
import re
import unicodedata
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

logger = logging.getLogger("uvicorn.error")

MANIFEST_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "curriculum" / "lessons_manifest.json"
BINDING_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "metadata" / "lesson_code_video_binding.json"
EMBEDDINGS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "curriculum" / "syllabus_embeddings.npz"

NAVIGATION_INTENT_TRIGGERS = [
    "bài nào", "bài học nào", "chọn bài nào", "học bài nào", "bài mấy", "bài bao nhiêu",
    "trong playlist", "trong lộ trình", "lộ trình học", "ở bài nào",
    "xem bài nào", "học ở đâu", "bài số mấy", "tìm bài", "playlist này",
    "học bài gì", "hôm nay học gì", "hôm nay học bài gì", "bài này học gì",
    "hôm nay chúng ta học", "chúng ta học bài gì", "giảng dạy", "dạy ở đâu"
]

OVERVIEW_QUERY_PATTERNS = [
    r"học\s+(?:\w+\s+)?gì",
    r"sẽ\s+học\s+(?:\w+\s+)?gì",
    r"hôm\s+nay\s+(?:chúng\s+ta\s+)?học",
    r"nội\s+dung\s+(?:của\s+)?bài",
    r"nói\s+về\s+(?:gì|cái\s+gì)",
    r"dạy\s+(?:gì|về\s+gì)",
    r"tổng\s+quan\s+bài",
    r"mục\s+tiêu\s+bài",
    r"tìm\s+hiểu\s+(?:gì|về\s+gì)",
    r"có\s+những\s+gì",
    r"chủ\s+đề\s+bài"
]


def _normalize_text(text: str) -> str:
    """Chuẩn hóa chuỗi về Unicode NFC và chữ thường để so khớp chính xác."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text.lower().strip())
    return " ".join(text.split())


def _has_topical_overlap(lesson: Dict[str, Any], prompt: str) -> bool:
    """
    Kiểm tra xem bài học có từ khóa hoặc tiêu đề thực sự chứa khái niệm trong câu hỏi hay không.
    Ngăn chặn bài học chung chung (như Bài 1 hoặc Bài 43 Stack) cướp quyền của bài học chuyên sâu.
    """
    norm_prompt = prompt.lower()
    stop_words = {
        "học", "bài", "nào", "ở", "đâu", "cho", "tôi", "em", "muốn", "thì", "chọn", 
        "trong", "playlist", "này", "khóa", "có", "phần", "dạy", "không", "gì", "là", 
        "về", "các", "những", "của", "được", "sẽ", "đến", "mới", "lập", "trình", "dữ", "liệu"
    }
    tokens = [w for w in re.findall(r"\w+", norm_prompt) if w not in stop_words and len(w) > 1]
    
    title_lower = lesson.get("title", "").lower()
    keywords = [k.lower() for k in lesson.get("keywords", [])]
    
    # Kiểm tra cụm 2 từ liên tiếp (bigram)
    for i in range(len(tokens) - 1):
        bigram = f"{tokens[i]} {tokens[i+1]}"
        if bigram in title_lower or any(bigram in k for k in keywords):
            return True
            
    # Kiểm tra các từ khóa kỹ thuật then chốt
    technical_keys = {
        "vòng", "lặp", "loop", "for", "while", "class", "oop", "struct", "mảng", "array", 
        "hàm", "function", "con", "trỏ", "pointer", "đối", "tượng", "vector", "string", 
        "chuỗi", "xâu", "đệ", "quy", "sắp", "xếp", "sort", "tìm", "kiếm", "search"
    }
    for t in tokens:
        if t in technical_keys:
            if t in title_lower or any(t in k for k in keywords):
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
        try:
            from app.services.embedding import get_embedding_service
            emb_svc = get_embedding_service()
            qv = np.array(emb_svc.embed_query_dense(f"query: {prompt}"), dtype=np.float32)
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

    def is_navigation_query(self, prompt: str) -> bool:
        """
        Nhận diện xem học viên có đang đặt câu hỏi điều hướng lộ trình / playlist
        hoặc hỏi về tổng quan nội dung của bài học hay không.
        """
        norm_prompt = _normalize_text(prompt)

        # 1. Các mẫu câu hỏi cấu trúc ngữ pháp tự nhiên về bài học / giáo trình
        nav_patterns = [
            r"bài\s*(?:học\s*)?(?:nào|mấy|bao\s*nhiêu|gì|số\s*mấy)",
            r"(?:học|dạy|tìm\s*hiểu|giảng\s*dạy)\s+.*(?:ở\s*đâu|chỗ\s*nào|bài\s*nào|bài\s*mấy|chương\s*nào|phần\s*nào|khi\s*nào|bao\s*giờ)",
            r"(?:ở\s*đâu|chỗ\s*nào|khi\s*nào|bao\s*giờ)\s*(?:mới\s*)?(?:học|dạy|có)",
            r"(?:khóa\s*học|giáo\s*trình|lộ\s*trình|playlist|danh\s*mục)\s*(?:có\s*)?.*(?:dạy|học|phần\s*nào|bài\s*nào|chương\s*nào|không)",
            r"(?:thuộc|nằm\s*ở|nằm\s*trong)\s*(?:bài|chương|khóa|phần)\s*nào",
            r"(?:tìm|xem)\s*(?:bài|video|chuyên\s*đề)",
            r"chủ\s*đề\s+.*(?:ở\s*đâu|bài\s*nào|bài\s*mấy)",
            r"có\s+dạy\s+.*(?:ở\s*đâu|bài\s*nào|không)"
        ]
        if any(re.search(pat, norm_prompt) for pat in nav_patterns):
            return True

        if any(trigger in norm_prompt for trigger in NAVIGATION_INTENT_TRIGGERS):
            return True
        return any(re.search(pat, norm_prompt) for pat in OVERVIEW_QUERY_PATTERNS)

    def is_overview_query(self, prompt: str) -> bool:
        """Kiểm tra xem câu hỏi có thuộc nhóm hỏi tổng quan nội dung bài học hay không."""
        norm_prompt = _normalize_text(prompt)
        return any(re.search(pat, norm_prompt) for pat in OVERVIEW_QUERY_PATTERNS)

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
        2. Ngữ cảnh bài học hiện tại (ví dụ: "bài này", "hôm nay", "bài hiện tại").
        3. Khớp từ khóa khái niệm kỹ thuật (ví dụ: "vòng lặp" -> Bài 6).
        """
        norm_prompt = _normalize_text(prompt)

        # 1. Khớp theo số thứ tự bài học tường minh
        match_seq = re.search(r"\bbài\s*(?:số\s*)?(\d+)\b|\blesson\s*(\d+)\b", norm_prompt)
        if match_seq:
            seq_num = int(match_seq.group(1) or match_seq.group(2))
            for lesson in self._all_lessons:
                if lesson.get("seq") == seq_num:
                    if preferred_course_id and lesson.get("course_id") == preferred_course_id:
                        return lesson, lesson.get("title", f"Bài {seq_num}")
            # Nếu không tìm thấy trong preferred course, tìm trên toàn bộ
            for lesson in self._all_lessons:
                if lesson.get("seq") == seq_num:
                    return lesson, lesson.get("title", f"Bài {seq_num}")

        # 2. Khớp theo ngữ cảnh bài học hiện tại nếu người dùng hỏi "bài này", "hôm nay"
        if any(ref in norm_prompt for ref in ["bài này", "bài hiện tại", "hôm nay", "video này", "tiết này"]):
            if current_lesson_seq is not None:
                for lesson in self._all_lessons:
                    if lesson.get("seq") == current_lesson_seq:
                        return lesson, lesson.get("title", f"Bài {current_lesson_seq}")

        # 3. Tìm kiếm bằng Chỉ mục Ngữ nghĩa Giáo trình (Syllabus Vector Index - Zero Regex Anchor)
        # Áp dụng Prerequisite Order Pareto Selection (ICLR 2025):
        semantic_results = self.semantic_search_lessons(prompt, top_k=6, min_similarity=0.78)
        if semantic_results:
            top_score, top_lesson = semantic_results[0]
            target_course = top_lesson.get("course_id")

            # Nếu kết quả cao nhất thuộc khóa khác, kiểm tra xem khóa hiện tại có ứng viên tương đương không
            if preferred_course_id and target_course != preferred_course_id:
                curr_cands = [c for c in semantic_results if c[1].get("course_id") == preferred_course_id]
                if curr_cands:
                    best_curr_score, best_curr_lesson = curr_cands[0]
                    # Điểm rất sát (chênh <= 0.03) và có topical overlap thực sự với câu hỏi
                    if (top_score - best_curr_score) <= 0.03:
                        if _has_topical_overlap(best_curr_lesson, prompt):
                            target_course = preferred_course_id

            # Trong target_course, chọn bài học lý thuyết tiên quyết:
            course_cands = [c for c in semantic_results if c[1].get("course_id") == target_course]
            best_course_score, best_course_lesson = course_cands[0]
            
            chosen_score, chosen_lesson = best_course_score, best_course_lesson
            for cand_score, cand_lesson in course_cands[1:]:
                # Chỉ xem xét bài đến trước nếu điểm cực sát (chênh <= 0.02)
                if best_course_score - cand_score <= 0.02:
                    if cand_lesson.get("seq", 999) < chosen_lesson.get("seq", 999):
                        if _has_topical_overlap(cand_lesson, prompt):
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
