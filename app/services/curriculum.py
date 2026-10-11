"""
Curriculum Service - Điều hướng lộ trình học tập & Playlist 83 bài học.
In-Course Agentic RAG Copilot - Tác giả: Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Tuân thủ bất biến Data/Code Separation Invariant:
- Nạp danh mục 83 bài học chuẩn từ data/curriculum/lessons_manifest.json vào RAM (Singleton).
- Phân giải câu hỏi điều hướng lộ trình (Fast-Path < 1ms) không qua LLM:
  Ví dụ: "em muốn học vòng lặp thì chọn bài nào trong playlist này..."
"""

import json
import logging
import unicodedata
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("uvicorn.error")

MANIFEST_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "curriculum" / "lessons_manifest.json"

NAVIGATION_INTENT_TRIGGERS = [
    "bài nào", "chọn bài nào", "học bài nào", "bài mấy", "bài bao nhiêu",
    "trong playlist", "trong lộ trình", "lộ trình học", "ở bài nào",
    "xem bài nào", "học ở đâu", "bài số mấy", "tìm bài", "playlist này"
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

    def __init__(self, manifest_path: Path = MANIFEST_PATH):
        self.manifest_path = manifest_path
        self._courses: Dict[str, Any] = {}
        self._all_lessons: List[Dict[str, Any]] = []
        self._load_manifest()

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

    def is_navigation_query(self, prompt: str) -> bool:
        """
        Nhận diện xem học viên có đang đặt câu hỏi điều hướng lộ trình / playlist hay không.
        """
        norm_prompt = _normalize_text(prompt)
        return any(trigger in norm_prompt for trigger in NAVIGATION_INTENT_TRIGGERS)

    def find_lesson_for_query(
        self,
        prompt: str,
        preferred_course_id: Optional[str] = None
    ) -> Optional[Tuple[Dict[str, Any], str]]:
        """
        Tìm kiếm bài học phù hợp nhất dựa trên từ khóa khái niệm kỹ thuật trong câu hỏi.
        Trả về Tuple: (lesson_dict, matched_keyword).
        """
        norm_prompt = _normalize_text(prompt)

        # Ưu tiên các bài học thuộc course_id hiện tại nếu có
        candidate_lessons = self._all_lessons
        if preferred_course_id and preferred_course_id in self._courses:
            # Sắp xếp các bài của preferred_course lên đầu
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
                # Kiểm tra khớp từ khóa đầy đủ
                if norm_kw and norm_kw in norm_prompt:
                    # Ưu tiên từ khóa dài và đặc thù hơn (ví dụ "mảng 2 chiều" hơn "mảng")
                    if len(norm_kw) > max_kw_len:
                        max_kw_len = len(norm_kw)
                        best_match = lesson
                        best_kw = kw

        if best_match:
            return best_match, best_kw

        return None

    def generate_navigation_response(
        self,
        prompt: str,
        current_lesson_seq: int,
        course_id: str
    ) -> Optional[str]:
        """
        Sinh câu trả lời Socratic thân thiện, hướng dẫn học viên chọn đúng bài học trong playlist.
        """
        match_result = self.find_lesson_for_query(prompt, preferred_course_id=course_id)
        if not match_result:
            return None

        lesson, matched_kw = match_result
        target_seq = lesson.get("seq")
        target_title = lesson.get("title")

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
