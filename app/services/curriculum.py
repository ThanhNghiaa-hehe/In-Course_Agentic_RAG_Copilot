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

logger = logging.getLogger("uvicorn.error")

MANIFEST_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "curriculum" / "lessons_manifest.json"
BINDING_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "metadata" / "lesson_code_video_binding.json"

NAVIGATION_INTENT_TRIGGERS = [
    "bài nào", "chọn bài nào", "học bài nào", "bài mấy", "bài bao nhiêu",
    "trong playlist", "trong lộ trình", "lộ trình học", "ở bài nào",
    "xem bài nào", "học ở đâu", "bài số mấy", "tìm bài", "playlist này"
]

OVERVIEW_QUERY_PATTERNS = [
    r"học\s+gì",
    r"sẽ\s+học\s+gì",
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


class CurriculumService:
    """
    Dịch vụ quản trị giáo trình và phân giải điều hướng bài học in-RAM (< 1ms).
    """

    def __init__(self, manifest_path: Path = MANIFEST_PATH, binding_path: Path = BINDING_PATH):
        self.manifest_path = manifest_path
        self.binding_path = binding_path
        self._courses: Dict[str, Any] = {}
        self._all_lessons: List[Dict[str, Any]] = []
        self._bindings: Dict[str, int] = {}
        self._load_manifest()
        self._load_bindings()

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

    def is_navigation_query(self, prompt: str) -> bool:
        """
        Nhận diện xem học viên có đang đặt câu hỏi điều hướng lộ trình / playlist
        hoặc hỏi về tổng quan nội dung của bài học hay không.
        """
        norm_prompt = _normalize_text(prompt)
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
        ts_list = [{"sec": 1, "label": "00:01", "title": "Mở đầu bài học"}]
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

        # 3. Khớp theo từ khóa kỹ thuật (Keyword matching)
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

        # Kiểm tra xem có phải hỏi tổng quan nội dung bài học hay không
        if self.is_overview_query(prompt):
            return self._build_lesson_overview_response(lesson, current_lesson_seq)

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
