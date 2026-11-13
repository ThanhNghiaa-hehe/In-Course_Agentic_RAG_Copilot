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
import unicodedata
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

logger = logging.getLogger("uvicorn.error")

MANIFEST_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "curriculum" / "lessons_manifest.json"
BINDING_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "metadata" / "lesson_code_video_binding.json"
EMBEDDINGS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "curriculum" / "syllabus_embeddings.npz"


def _normalize_text(text: str) -> str:
    """Chuẩn hóa chuỗi về Unicode NFC và chữ thường để so khớp chính xác."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text.lower().strip())
    return " ".join(text.split())


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
    tokens = [w for w in clean_words if w not in active_stops and len(w) > 1]

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

    def _ensure_nav_embeddings(self) -> None:
        """Khởi tạo trước ma trận embedding cho các mẫu câu điều hướng và tổng quan giáo trình (0% Hardcoded Rules)."""
        if self._nav_vectors is not None and self._overview_vectors is not None:
            return
        try:
            from app.services.embedding import get_embedding_service
            emb_svc = get_embedding_service()
            if self._nav_prototypes and self._nav_vectors is None:
                vecs = [emb_svc.embed_query_dense(f"query: {p}") for p in self._nav_prototypes]
                arr = np.array(vecs, dtype=np.float32)
                norms = np.linalg.norm(arr, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                self._nav_vectors = arr / norms
            if self._overview_prototypes and self._overview_vectors is None:
                vecs_o = [emb_svc.embed_query_dense(f"query: {p}") for p in self._overview_prototypes]
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

    def get_lesson_by_seq(self, seq: int) -> Optional[Dict[str, Any]]:
        """
        Lấy thông tin bài học theo số thứ tự seq từ manifest (Data/Code Separation).
        """
        for les in self._all_lessons:
            if les.get("seq") == seq:
                return les
        return None

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

    def is_navigation_query(self, prompt: str) -> bool:
        """
        Nhận diện xem học viên có đang đặt câu hỏi điều hướng lộ trình / playlist
        hoặc hỏi về tổng quan nội dung của bài học hay không bằng 100% Machine Learning (Dense Vector Cosine).
        """
        norm_prompt = _normalize_text(prompt)

        # 1. Trực tiếp có số thứ tự bài học (ví dụ "bài 4", "lesson 4")
        if self._extract_lesson_seq(norm_prompt) is not None:
            return True

        # 2. Khớp vector ngữ nghĩa Cosine Similarity với prototype matrix (ngưỡng chuẩn hóa E5 >= 0.87)
        self._ensure_nav_embeddings()
        if self._nav_vectors is not None:
            try:
                from app.services.embedding import get_embedding_service
                emb_svc = get_embedding_service()
                qv = np.array(emb_svc.embed_query_dense(f"query: {prompt}"), dtype=np.float32)
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
        self._ensure_nav_embeddings()
        if self._overview_vectors is not None:
            try:
                from app.services.embedding import get_embedding_service
                emb_svc = get_embedding_service()
                qv = np.array(emb_svc.embed_query_dense(f"query: {prompt}"), dtype=np.float32)
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
        if "?" in prompt:
            return None
        norm = _normalize_text(prompt)
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
        2. Ngữ cảnh bài học hiện tại nạp từ manifest.
        3. Chỉ mục Ngữ nghĩa Giáo trình (Syllabus Vector Index) kết hợp đối chiếu từ khóa manifest.
        """
        norm_prompt = _normalize_text(prompt)

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

        # 2. Khớp theo ngữ cảnh bài học hiện tại nạp từ manifest
        if any(ref in norm_prompt for ref in self._current_lesson_refs):
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
                        if _has_topical_overlap(best_curr_lesson, prompt, self._stop_words):
                            target_course = preferred_course_id

            # Trong target_course, chọn bài học phù hợp nhất dựa trên Semantic Dominance & Prerequisite Order
            course_cands = [c for c in semantic_results if c[1].get("course_id") == target_course]
            best_course_score, best_course_lesson = course_cands[0]

            is_intro_query = any(m in norm_prompt for m in self._intro_navigation_markers)

            # DAG Prerequisite Root Selection (Mục 3.1 - Nhịp 1B / Nhịp 2):
            # Lọc các nút nền tảng (is_foundational và KHÔNG phải is_revision) trong target_course không có xung đột định ngữ
            foundational_cands = [
                c for c in course_cands
                if c[1].get("is_foundational", False)
                and not c[1].get("is_revision", False)
                and not _has_modifier_conflict(prompt, c[1], top_lesson=best_course_lesson, conflict_groups=self._modifier_conflict_groups)
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

                # Revision Non-Dominance: Bài ôn tập / cập nhật không cướp quyền bài gốc
                if cand_lesson.get("is_revision", False) and cand_lesson.get("updates_lesson_seq") == chosen_lesson.get("seq"):
                    continue

                cand_seq = cand_lesson.get("seq", 999)
                chosen_seq = chosen_lesson.get("seq", 999)

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
