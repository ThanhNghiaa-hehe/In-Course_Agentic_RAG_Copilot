"""
Telemetry Critic & Diagnostic Service cho Playground Sessions.
In-Course Agentic RAG Copilot - Tác giả: Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Cung cấp:
1. Phân tích kiểm toán tự động từng lượt đối thoại (Turn-by-turn Diagnostic):
   - Ranh giới mã nguồn Socratic (chống lộ #include, int main, giải bài hộ).
   - Thẩm định mốc video <timestamp> (đối chiếu Whitelist bảo chứng).
   - Kiểm tra định tuyến ý định (Router) và truy xuất CRAG.
   - Đo lường độ trễ (TTFT) và tốc độ sinh token.
2. Xuất log tự động ra thư mục logs/playground_debug/ dưới dạng JSON & Markdown Report.
3. Trả về cấu trúc nhận xét đánh giá chi tiết để hiển thị tức thời trên Playground UI.
"""

import json
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from markdown_it import MarkdownIt
from tree_sitter import Parser, Language
import tree_sitter_cpp as tscpp

from app.config import settings
from app.agent.guardrails import (
    extract_prose_outside_code_and_footer,
    normalize_user_input,
)
from app.agent.router import get_intent_router
from app.services.curriculum import get_curriculum_service
from app.services.chat import (
    _is_forbidden_closing_sentence,
    _load_forbidden_closing_prefixes,
    _split_prose_sentences,
    has_trailing_socratic_question,
    is_echo_only_prose,
)

CPP_LANGUAGE = Language(tscpp.language())
_CPP_PARSER = Parser(CPP_LANGUAGE)
_MD_PARSER = MarkdownIt()


class TimestampTagExtractor(HTMLParser):
    """Bộ bóc tách thẻ XML <timestamp> thuần AST/Event-driven, triệt tiêu 100% regex."""
    def __init__(self):
        super().__init__()
        self.tags: List[Tuple[str, str]] = []
        self._active_sec: Optional[str] = None
        self._active_text: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        if tag == "timestamp":
            attr_dict = dict(attrs)
            if "sec" in attr_dict and attr_dict["sec"] is not None:
                self._active_sec = str(attr_dict["sec"])
                self._active_text = []

    def handle_data(self, data: str):
        if self._active_sec is not None:
            self._active_text.append(data)

    def handle_endtag(self, tag: str):
        if tag == "timestamp" and self._active_sec is not None:
            label = "".join(self._active_text).strip()
            self.tags.append((self._active_sec, label))
            self._active_sec = None
            self._active_text = []


def _strip_timestamp_tags_plain(text: str) -> str:
    """Loại bỏ hoàn toàn các phần tử <timestamp ...>...</timestamp> bằng quét chuỗi thuần túy (Zero Regex)."""
    if not text or "<timestamp" not in text.lower():
        return text
    work = text
    while True:
        low = work.lower()
        start_idx = low.find("<timestamp")
        if start_idx == -1:
            break
        close_idx = low.find("</timestamp>", start_idx)
        if close_idx != -1:
            work = work[:start_idx] + work[close_idx + len("</timestamp>"):]
        else:
            gt_idx = work.find(">", start_idx)
            if gt_idx != -1:
                work = work[:start_idx] + work[gt_idx + 1:]
            else:
                work = work[:start_idx]
                break
    return work


def _strip_code_fences(text: str) -> str:
    """Tách bỏ các khối mã nguồn fenced (``` ... ```) bằng duyệt dòng thuần túy (Zero Regex)."""
    if not text:
        return ""
    out_lines: List[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if stripped.count("```") == 1:
                in_fence = not in_fence
            continue
        if not in_fence:
            out_lines.append(line)
    return "\n".join(out_lines)


def _extract_timestamp_tags(response_text: str) -> List[Tuple[str, str]]:
    """
    Bóc tách danh sách (sec_str, label) của mọi thẻ <timestamp> ngoài khối code fence.
    Quét từng cụm <timestamp ...>...</timestamp> vào HTMLParser để toán tử '<' của C++ ở dòng trước
    không làm nhiễu trạng thái parser (Zero Regex).
    """
    non_fenced = _strip_code_fences(response_text)
    if not non_fenced or "<timestamp" not in non_fenced.lower():
        return []

    tags: List[Tuple[str, str]] = []
    cursor = 0
    low = non_fenced.lower()
    close_tok = "</timestamp>"
    while True:
        start_idx = low.find("<timestamp", cursor)
        if start_idx == -1:
            break
        close_idx = low.find(close_tok, start_idx)
        if close_idx == -1:
            break
        end_pos = close_idx + len(close_tok)
        snippet = non_fenced[start_idx:end_pos]
        parser = TimestampTagExtractor()
        parser.feed(snippet)
        tags.extend(parser.tags)
        cursor = end_pos
    return tags


def _extract_prose_before_timestamp_footer(response_text: str) -> str:
    """
    Trích xuất văn bản ngôn ngữ tự nhiên của trợ giảng TRƯỚC dòng footer '📍 **Mốc video bài giảng:**',
    loại bỏ hoàn toàn:
    1. Khối mã nguồn fenced / indented code_block.
    2. Biểu thức inline code `...` (chặn toán tử 3 ngôi `a ? b : c` giả mạo câu hỏi Socratic).
    3. URL query parameters ('?'), thẻ HTML <timestamp> và dòng footer '📍 Mốc video bài giảng:'.
    """
    return extract_prose_outside_code_and_footer(response_text)


def _inspect_cpp_code_ast(code: str) -> Tuple[bool, bool]:
    """
    Phân tích cú pháp AST mã nguồn C++ qua Tree-sitter:
    - has_include: Phát hiện chỉ thị #include (preproc_include).
    - has_main: Phát hiện định nghĩa hàm main() thực thi (function_declarator -> main).
    """
    try:
        tree = _CPP_PARSER.parse(bytes(code, "utf8"))
        has_include = False
        has_main = False

        def _has_main_declarator(decl_node) -> bool:
            if decl_node.type == "function_declarator":
                for sub in decl_node.children:
                    if sub.type == "identifier" and sub.text.decode("utf8") == "main":
                        return True
            for sub in decl_node.children:
                if sub.type != "compound_statement" and _has_main_declarator(sub):
                    return True
            return False

        def traverse(node):
            nonlocal has_include, has_main
            if node.type == "preproc_include":
                has_include = True
            elif node.type == "function_definition":
                if _has_main_declarator(node):
                    has_main = True
            for child in node.children:
                traverse(child)

        traverse(tree.root_node)
        return has_include, has_main
    except Exception:
        # Dự phòng phân tích dòng thuần túy nếu Tree-sitter lỗi
        has_inc = any(line.strip().startswith("#") and "include" in line for line in code.splitlines())
        has_m = any("main(" in line.replace(" ", "") for line in code.splitlines() if not line.strip().startswith("//"))
        return has_inc, has_m

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = PROJECT_ROOT / "logs" / "playground_debug"


def _ensure_logs_dir() -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return LOGS_DIR


class TelemetryCriticService:
    """
    Dịch vụ kiểm toán tự động & Phê bình chất lượng phiên đối thoại Socratic AI.
    """

    def analyze_turn(
        self,
        entry: Dict[str, Any],
        prev_entry: Optional[Dict[str, Any]] = None,
        had_prior_course_query: bool = False,
        anchor_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Kiểm toán chi tiết 1 turn đối thoại (Zero Self-Flattery, Multi-Turn Intent Fidelity & Zero Magic Numbers)."""
        turn_num = entry.get("turn", 1)
        prompt = entry.get("prompt", "")
        clean_prompt = normalize_user_input(prompt)
        response_text = entry.get("response_text", "")
        latency = entry.get("latency", {})
        ttft_ms = latency.get("ttft_ms", 0)
        total_ms = latency.get("total_ms", 0)
        tokens_per_sec = latency.get("tokens_per_sec", 0.0)

        router = entry.get("router", {})
        intent = router.get("intent", "unknown")
        used_fast_path = router.get("used_fast_path", False)

        crag = entry.get("crag", {})
        retrieval_status = crag.get("retrieval_status", "unknown")
        target_lesson_seq = crag.get("target_lesson_seq")

        suggested_ts = entry.get("timestamps", [])
        sources = entry.get("sources", [])

        violations = []
        warnings = []
        merits = []

        score = 100

        # 1. Kiểm tra ranh giới mã nguồn Socratic qua Markdown AST & Tree-sitter C++ AST (Zero Magic Numbers)
        md_tokens = _MD_PARSER.parse(response_text)
        code_blocks = [t.content for t in md_tokens if t.type in ("fence", "code_block")]
        total_code_lines = 0
        has_include_in_code = False
        has_main_in_code = False

        for block in code_blocks:
            lines = [l for l in block.strip().split("\n") if l.strip()]
            num_lines = len(lines)
            total_code_lines += num_lines

            inc, main_fn = _inspect_cpp_code_ast(block)
            if inc:
                has_include_in_code = True
            if main_fn:
                has_main_in_code = True

        if has_include_in_code:
            violations.append("Vi phạm ranh giới mã nguồn: Xuất hiện chỉ thị khai báo thư viện `#include` trong khối mã nguồn hoàn chỉnh.")
            score -= settings.CRITIC_INCLUDE_VIOLATION_PENALTY
        if has_main_in_code:
            violations.append("Vi phạm nghiêm trọng ranh giới Socratic: Khối mã nguồn chứa hàm `main()` thực thi, giải bài tập thay vì định hướng tư duy.")
            score -= settings.CRITIC_MAIN_VIOLATION_PENALTY

        if total_code_lines > settings.MAX_CODE_ILLUSTRATION_LINES:
            warnings.append(
                f"Khối mã nguồn minh họa khá dài ({total_code_lines} dòng > {settings.MAX_CODE_ILLUSTRATION_LINES} dòng). "
                f"Nên ưu tiên dùng Mã giả (Pseudocode) hoặc đoạn code khuyết."
            )
        elif total_code_lines > 0 and not has_main_in_code and not has_include_in_code:
            merits.append("Minh họa cú pháp ngắn gọn, tuân thủ nguyên tắc không giải bài hộ.")

        # Kiểm tra câu hỏi gợi mở Socratic trên phần văn bản tự nhiên TRƯỚC footer '📍 Mốc video bài giảng:'
        # (Loại trừ cả fenced code, inline code `a ? b : c`, câu kết sáo rỗng & câu chỉ nhại lại đề)
        prose_before_footer = _extract_prose_before_timestamp_footer(response_text)
        closing_prefixes = _load_forbidden_closing_prefixes()
        has_forbidden_closer = any(
            _is_forbidden_closing_sentence(sent, closing_prefixes)
            for sent in _split_prose_sentences(prose_before_footer)
        )
        is_echo_only = (
            intent == "course_query"
            and is_echo_only_prose(prose_before_footer, clean_prompt)
        )
        if has_forbidden_closer:
            warnings.append("Phát hiện câu kết sáo rỗng (forbidden_closing_prefixes) trong phản hồi.")
            score -= 10
        if is_echo_only:
            warnings.append("Phản hồi chỉ nhại lại câu hỏi của học viên mà thiếu giải thích bản chất.")
            score -= 20

        has_question = has_trailing_socratic_question(response_text, user_prompt=clean_prompt)
        if has_question:
            merits.append("Có đặt câu hỏi gợi mở định hướng tư duy (Socratic Questioning).")
        elif intent == "course_query":
            warnings.append("Thiếu câu hỏi gợi mở ở cuối câu trả lời để kích thích học viên tự suy luận.")
            score -= settings.CRITIC_MISSING_QUESTION_PENALTY

        # 2. Kiểm toán thẻ Timestamp Video qua HTMLParser AST (Zero Regex)
        ts_tags = _extract_timestamp_tags(response_text)
        whitelist_secs = set()
        for t in suggested_ts:
            if isinstance(t, dict) and t.get("sec") is not None and not isinstance(t.get("sec"), bool):
                try:
                    whitelist_secs.add(int(t["sec"]))
                except (ValueError, TypeError):
                    pass

        unverified_ts = []
        for sec_str, label in ts_tags:
            try:
                sec_val = int(sec_str)
                if sec_val not in whitelist_secs:
                    unverified_ts.append(f"{label} ({sec_val}s)")
            except ValueError:
                unverified_ts.append(f"{label} ({sec_str}s)")

        if unverified_ts:
            warnings.append(f"Mốc thời gian không nằm trong Whitelist nguồn xác thực: {', '.join(unverified_ts)}.")
            score -= settings.CRITIC_UNVERIFIED_TS_PENALTY
        elif ts_tags:
            merits.append(f"Trích xuất thành công {len(ts_tags)} mốc video chuẩn xác từ nguồn bài giảng.")

        # Kiểm tra độ trễ phản hồi
        if ttft_ms > settings.CRITIC_LATENCY_THRESHOLD_MS and not used_fast_path:
            warnings.append(f"Độ trễ TTFT cao ({ttft_ms}ms > {settings.CRITIC_LATENCY_THRESHOLD_MS}ms).")
            score -= settings.CRITIC_HIGH_LATENCY_PENALTY

        router_svc = get_intent_router()
        curr_svc = get_curriculum_service()

        # Kiểm toán 1 (PC-02): False Student Attribution Check
        attr_prefixes = [
            str(p).strip().lower()
            for p in (router_svc._manifest_data.get("forbidden_attribution_prefixes") or ())
            if str(p).strip()
        ]
        if attr_prefixes and len(clean_prompt.split()) <= 12:
            from app.services.chat import _is_analogy_verification_query_text
            if not _is_analogy_verification_query_text(clean_prompt):
                prose_start_low = prose_before_footer.lstrip(" \t\r\n*-•\"'“”").lower()
                if any(
                    prose_start_low.startswith(ap)
                    and (len(prose_start_low) == len(ap) or prose_start_low[len(ap)] in " \t,.:;!?")
                    for ap in attr_prefixes
                ):
                    warnings.append(
                        "Ảo giác gán ghép lời học viên (False Student Attribution): "
                        "Trợ giảng tự nhận học viên đã mô tả kiến thức trong tài liệu tham khảo."
                    )
                    score -= 15

        # Kiểm toán 2 (PC-02): Cross-Lesson Context Drift Check
        raw_entry_seq = entry.get("lesson_seq")
        entry_lesson_seq_chk = (
            raw_entry_seq if isinstance(raw_entry_seq, int) and not isinstance(raw_entry_seq, bool) else None
        )
        explicit_seq_chk = curr_svc._extract_lesson_seq(clean_prompt.lower()) if clean_prompt else None
        if (
            intent == "course_query"
            and retrieval_status == "grounded"
            and entry_lesson_seq_chk is not None
            and explicit_seq_chk is None
        ):
            src_seqs = [
                int(s.get("lesson_seq"))
                for s in (sources or [])
                if isinstance(s, dict) and s.get("lesson_seq") is not None and not isinstance(s.get("lesson_seq"), bool)
            ]
            ts_seqs = [
                int(t.get("lesson_seq"))
                for t in (suggested_ts or [])
                if isinstance(t, dict) and t.get("lesson_seq") is not None and not isinstance(t.get("lesson_seq"), bool)
            ]
            has_src_drift = bool(src_seqs) and all(seq != entry_lesson_seq_chk for seq in src_seqs)
            has_ts_drift = (not src_seqs) and bool(ts_seqs) and all(seq != entry_lesson_seq_chk for seq in ts_seqs)
            if has_src_drift or has_ts_drift:
                warnings.append(
                    f"Trôi ngữ cảnh liên bài (Cross-Lesson Context Drift): "
                    f"Học viên đang ở Bài {entry_lesson_seq_chk} nhưng toàn bộ nguồn/mốc video trích xuất thuộc bài khác."
                )
                score -= 15

        # Kiểm toán 3 (PC-01, M4): Out-of-Lesson Timestamp-Source Lesson Parity Check
        if retrieval_status == "out_of_lesson" and suggested_ts:
            mismatch_source = (
                target_lesson_seq is not None
                and any(
                    int(s.get("lesson_seq")) != int(target_lesson_seq)
                    for s in (sources or [])
                    if isinstance(s, dict) and s.get("lesson_seq") is not None and not isinstance(s.get("lesson_seq"), bool)
                )
            )
            if (not sources) or mismatch_source:
                warnings.append(
                    "Bất đối xứng dữ liệu nguồn (Timestamp-Source Lesson Parity Violation): "
                    "Nguồn học liệu của out_of_lesson bị thiếu hoặc không khớp với target_lesson_seq."
                )
                score -= 10

        # Kiểm toán 4 (PC-06): Unresolved Curriculum Navigation & Degraded RRF Fallback Check
        is_nav_logged = router.get("is_curriculum_navigation")
        skip_nav_logged = bool(crag.get("skip_nav_rerank", False))
        scoring_src = crag.get("scoring_source")
        nav_src_seqs = [
            int(s.get("lesson_seq"))
            for s in (sources or [])
            if isinstance(s, dict) and s.get("lesson_seq") is not None and not isinstance(s.get("lesson_seq"), bool)
        ]
        if (
            intent == "course_query"
            and retrieval_status == "grounded"
            and is_nav_logged is True
            and entry_lesson_seq_chk is not None
            and explicit_seq_chk is None
            and not curr_svc.has_current_lesson_reference(clean_prompt)
            and not curr_svc.is_overview_query(clean_prompt)
            and (skip_nav_logged or scoring_src == "nav_verified_rrf")
            and bool(nav_src_seqs)
            and all(seq == entry_lesson_seq_chk for seq in nav_src_seqs)
        ):
            warnings.append(
                "Điều hướng lộ trình chưa được giải quyết bằng Cross-Encoder (Unresolved Curriculum Navigation): "
                "Câu hỏi tìm bài học bị khóa ở bài hiện tại bằng lối tắt RRF."
            )
            score -= 15

        if scoring_src == "rrf_fallback_degraded":
            warnings.append(
                "Chế độ suy giảm Cross-Encoder (Degraded RRF Fallback): "
                "Điểm tin cậy được tính từ RRF thuần do Cross-Encoder không khả dụng."
            )
            score -= 5

        # 3. Đánh giá Router & Multi-Turn Intent Fidelity (Zero Self-Flattery, đồng bộ toán học với router_node)
        is_pure_soc, _ = router_svc.is_pure_social(clean_prompt)

        is_intent_hijacked = False
        is_topic_intruded = False
        multi_turn_intent_fidelity = 1.0

        if intent == "chit_chat":
            prev_intent = prev_entry.get("router", {}).get("intent") if prev_entry else None
            is_continuing_course = (had_prior_course_query or prev_intent == "course_query")
            is_ack, _ = router_svc.is_social_acknowledgment(clean_prompt)
            lower_clean = clean_prompt.lower()
            has_solicitation = any(w in lower_clean for w in getattr(router_svc, "_solicitation_words", ()))
            sim_sys = router_svc.get_system_identity_similarity(clean_prompt)
            is_sys_identity = (sim_sys >= 0.88) and (not has_solicitation)

            # Chuyển trạng thái Markov bất hợp lệ (đang học tập bị ép về chit_chat nhưng không thuộc nhóm xã giao/tiếp thu/danh tính)
            if is_continuing_course and not is_pure_soc and not is_ack and not is_sys_identity:
                is_intent_hijacked = True
        elif intent == "course_query":
            # Trường hợp 3: Topic Intrusion Hijacking (Reverse Intent Hijacking)
            # Câu hỏi ngoài lề hoặc xã giao bị ép phân loại thành course_query và kích hoạt RAG
            standalone_clf = router_svc.classify(clean_prompt)
            if standalone_clf.intent in ("chit_chat", "out_of_scope"):
                is_nav_res = router_svc.is_curriculum_navigation(clean_prompt)
                is_nav = is_nav_res[0] if isinstance(is_nav_res, tuple) else bool(is_nav_res)

                slm_probs = router_svc._get_slm_probs(clean_prompt)
                p_oos = float(slm_probs[2]) if slm_probs is not None else 0.0

                entry_course_id = entry.get("course_id") if isinstance(entry.get("course_id"), str) else None
                raw_les_seq = entry.get("lesson_seq")
                entry_lesson_seq = (
                    raw_les_seq if isinstance(raw_les_seq, int) and not isinstance(raw_les_seq, bool) else None
                )

                norm_lower = normalize_user_input(clean_prompt, lowercase=True, preserve_newlines=False)
                explicit_seq = curr_svc._extract_lesson_seq(norm_lower)
                has_manifest_curr_ref = any(
                    ref in norm_lower for ref in getattr(curr_svc, "_current_lesson_refs", ())
                )
                is_explicit_lesson_ref = (
                    (explicit_seq is not None or has_manifest_curr_ref)
                    and (p_oos < 0.75)
                    and (not is_pure_soc)
                )
                is_overview = (
                    (p_oos < 0.75)
                    and (not is_pure_soc)
                    and curr_svc.is_overview_query(clean_prompt)
                )

                # Đồng bộ toán học với router_node Bước 3b (In-Video Temporal NLI & SLM Gate)
                time_ref = curr_svc.extract_video_time_reference(clean_prompt)
                is_in_video_time_ref = (time_ref is not None and explicit_seq is None)
                is_valid_in_video_temporal = False
                nli_temporal_rejected = False
                if is_in_video_time_ref:
                    if p_oos < 0.75 and not is_pure_soc:
                        is_in_vid, _ = router_svc._nli_arbiter.verify_in_video_temporal_query(clean_prompt)
                        if is_in_vid:
                            is_valid_in_video_temporal = True
                        else:
                            nli_temporal_rejected = True
                    else:
                        nli_temporal_rejected = True

                # Kiểm tra truy vấn phân vân đa chủ đề / cạnh tranh bài học trong giáo trình
                is_ambiguous_curriculum = False
                if p_oos < 0.75 and not is_pure_soc and not nli_temporal_rejected:
                    try:
                        amb_res = curr_svc.find_ambiguous_candidates(
                            clean_prompt,
                            current_lesson_seq=entry_lesson_seq,
                            preferred_course_id=entry_course_id,
                        )
                        is_ambiguous_curriculum = bool(amb_res.get("is_ambiguous", False))
                    except Exception:
                        is_ambiguous_curriculum = False

                # Kiểm tra câu hỏi nối tiếp phụ thuộc ngữ cảnh (Context-Dependent Follow-up)
                effective_anchor = normalize_user_input(anchor_query) if anchor_query else None
                if not effective_anchor and prev_entry and prev_entry.get("router", {}).get("intent") == "course_query":
                    effective_anchor = normalize_user_input(prev_entry.get("prompt", "")) or None

                is_dep = router_svc.is_context_dependent(clean_prompt, anchor_query=effective_anchor)
                is_valid_context_dep = False
                if is_dep and not is_pure_soc and not nli_temporal_rejected:
                    if p_oos < 0.75:
                        is_valid_context_dep = True
                    elif effective_anchor:
                        ctx_clf, _ = router_svc.classify_contextual(clean_prompt, effective_anchor)
                        is_valid_context_dep = bool(ctx_clf.is_course_query)

                if not (
                    is_nav
                    or is_overview
                    or is_explicit_lesson_ref
                    or is_valid_in_video_temporal
                    or is_ambiguous_curriculum
                    or is_valid_context_dep
                ):
                    is_topic_intruded = True

        if is_intent_hijacked:
            multi_turn_intent_fidelity = 0.0
            violations.append(
                "Vi phạm Multi-Turn Intent Fidelity (Conversational Hijacking): "
                "Câu hỏi học tập/nối tiếp bị phân loại nhầm thành chit_chat, cuốn học viên vào vòng lặp chào hỏi."
            )
            score -= settings.CRITIC_HIJACKING_PENALTY
            score = max(0, min(20, score))  # Ràng buộc bắt buộc: Lượt bị cướp luồng không vượt quá 20/100
        elif is_topic_intruded:
            multi_turn_intent_fidelity = 0.0
            violations.append(
                "Vi phạm Multi-Turn Intent Fidelity (Topic Intrusion Hijacking): "
                "Câu hỏi ngoài lề/xã giao bị ép phân loại thành course_query và kích hoạt RAG không phù hợp."
            )
            score -= settings.CRITIC_TOPIC_INTRUSION_PENALTY
            score = max(0, min(25, score))  # Ràng buộc bắt buộc: Khống chế trần điểm lượt <= 25/100
        else:
            if used_fast_path and intent in ("chit_chat", "out_of_scope", "confirm_navigation"):
                merits.append(f"Kích hoạt Fast-Path Zero-Compute thành công (< {total_ms}ms), tối ưu tài nguyên và độ trễ phản hồi.")
            score = max(0, min(100, score))

        # Tóm tắt nhận xét
        critique_parts = []
        if violations:
            critique_parts.append(f"❌ Cần sửa: {'; '.join(violations)}")
        if warnings:
            critique_parts.append(f"⚠️ Lưu ý: {'; '.join(warnings)}")
        if merits:
            critique_parts.append(f"✅ Ưu điểm: {'; '.join(merits)}")
        if not critique_parts:
            critique_parts.append("Phản hồi đạt chuẩn chất lượng bình thường.")

        return {
            "turn": turn_num,
            "prompt": prompt,
            "intent": intent,
            "retrieval_status": retrieval_status,
            "target_lesson_seq": target_lesson_seq,
            "used_fast_path": used_fast_path,
            "is_intent_hijacked": is_intent_hijacked,
            "is_topic_intruded": is_topic_intruded,
            "is_echo_only": is_echo_only,
            "multi_turn_intent_fidelity": multi_turn_intent_fidelity,
            "latency": {
                "ttft_ms": ttft_ms,
                "total_ms": total_ms,
                "tokens_per_sec": tokens_per_sec
            },
            "socratic_compliance": len(violations) == 0,
            "socratic_violations": violations,
            "warnings": warnings,
            "merits": merits,
            "turn_score": score,
            "critique_summary": " | ".join(critique_parts)
        }

    def analyze_session(
        self,
        session_id: str,
        course_id: str,
        lesson_seq: int,
        turns: List[Dict[str, Any]],
        client_timestamp: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Kiểm toán toàn diện toàn bộ phiên đối thoại (Session Holistic Critique).
        Phát hiện Greeting Loop Incident và ép điểm phiên <= 35 khi đứt gãy luồng học tập liên tiếp.
        """
        turn_critiques = []
        hijacked_turns = []
        had_prior_course_query = False
        prev_entry = None
        last_course_query: Optional[str] = None
        active_course_id: Optional[str] = course_id
        active_lesson_seq: Optional[int] = lesson_seq

        for turn in turns:
            turn_course_id = turn.get("course_id") or active_course_id
            raw_turn_seq = turn.get("lesson_seq")
            turn_lesson_seq = (
                raw_turn_seq
                if isinstance(raw_turn_seq, int) and not isinstance(raw_turn_seq, bool)
                else active_lesson_seq
            )

            # Reset mỏ neo ngữ cảnh khi học viên chuyển bài học hoặc khóa học mới
            if (
                (active_lesson_seq is not None and turn_lesson_seq != active_lesson_seq)
                or (active_course_id and turn_course_id != active_course_id)
            ):
                last_course_query = None

            turn_payload = dict(turn)
            if "course_id" not in turn_payload and turn_course_id:
                turn_payload["course_id"] = turn_course_id
            if "lesson_seq" not in turn_payload and turn_lesson_seq is not None:
                turn_payload["lesson_seq"] = turn_lesson_seq

            tc = self.analyze_turn(
                turn_payload,
                prev_entry=prev_entry,
                had_prior_course_query=had_prior_course_query,
                anchor_query=last_course_query,
            )
            turn_critiques.append(tc)
            if tc.get("is_intent_hijacked") or tc.get("is_topic_intruded"):
                hijacked_turns.append(tc["turn"])
            if (
                turn.get("router", {}).get("intent") == "course_query"
                or tc.get("intent") == "course_query"
            ) and not tc.get("is_topic_intruded"):
                had_prior_course_query = True
                clean_q = normalize_user_input(turn.get("prompt", ""))
                if clean_q:
                    last_course_query = clean_q
            elif tc.get("intent") == "confirm_navigation":
                last_course_query = None

            active_course_id = turn_course_id
            active_lesson_seq = turn_lesson_seq
            prev_entry = turn_payload

        total_turns = len(turn_critiques)

        if total_turns == 0:
            return {
                "session_id": session_id,
                "course_id": course_id,
                "lesson_seq": lesson_seq,
                "total_turns": 0,
                "overall_health_score": 100,
                "rating_label": "CHƯA CÓ DỮ LIỆU (EMPTY SESSION)",
                "socratic_compliance_rate": 100.0,
                "intent_fidelity_rate": 100.0,
                "hijacked_turns": [],
                "avg_ttft_ms": 0,
                "fast_path_count": 0,
                "grounded_count": 0,
                "coverage_gap_count": 0,
                "turn_critiques": [],
                "critique_markdown": "# Báo cáo phiên rỗng: Chưa có lượt đối thoại nào.",
                "summary": "Chưa có lượt đối thoại nào được ghi nhận."
            }

        compliant_turns = sum(1 for tc in turn_critiques if tc["socratic_compliance"])
        compliance_rate = round((compliant_turns / total_turns) * 100, 1)

        fidelity_turns = sum(1 for tc in turn_critiques if tc.get("multi_turn_intent_fidelity", 1.0) == 1.0)
        intent_fidelity_rate = round((fidelity_turns / total_turns) * 100, 1)

        avg_score = round(sum(tc["turn_score"] for tc in turn_critiques) / total_turns)
        avg_ttft = round(sum(tc["latency"]["ttft_ms"] for tc in turn_critiques) / total_turns)

        fast_path_count = sum(1 for tc in turn_critiques if tc["used_fast_path"])
        grounded_count = sum(1 for tc in turn_critiques if tc["retrieval_status"] == "grounded")
        coverage_gap_count = sum(1 for tc in turn_critiques if tc["retrieval_status"] == "coverage_gap")

        # Đánh giá tổng quát & Greeting Loop Incident Detector
        num_hijacks = len(hijacked_turns)
        if num_hijacks >= 2:
            # Biến cố Greeting Loop: Học viên bị kẹt vào vòng lặp chào hỏi liên tiếp
            avg_score = min(avg_score, settings.CRITIC_MAX_SESSION_SCORE_ON_GREETING_LOOP)  # <= 35
            rating_label = "CẦN TINH CHỈNH KHẨN CẤP (GREETING LOOP / INTENT DRIFT)"
            rating_badge = "🔴"
        elif num_hijacks == 1:
            avg_score = min(avg_score, 65)
            rating_label = "CẦN TINH CHỈNH (CONVERSATIONAL HIJACKING DETECTED)"
            rating_badge = "🔴"
        elif avg_score >= 90:
            rating_label = "XUẤT SẮC (SOTA PRODUCTION QUALITY)"
            rating_badge = "🟢"
        elif avg_score >= 75:
            rating_label = "ĐẠT CHUẨN SƯ PHẠM (GOOD COMPLIANCE)"
            rating_badge = "🟡"
        else:
            rating_label = "CẦN TINH CHỈNH (NEEDS TUNING)"
            rating_badge = "🔴"

        # Sinh Markdown Report
        ts_now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        md_lines = [
            f"# Báo Cáo Kiểm Toán & Đánh Giá Phiên Đối Thoại Playground",
            f"> Hệ thống: In-Course Agentic RAG Copilot | Tác giả: Trần Thành Nghĩa (HUFLIT)",
            f"",
            f"- **Session ID:** `{session_id}`",
            f"- **Khóa học:** `{course_id}` | **Bài học hiện tại:** `Bài {lesson_seq}`",
            f"- **Thời điểm kiểm toán:** `{ts_now}`",
            f"- **Tổng số lượt (Turns):** `{total_turns}` lượt",
            f"",
            f"### Đánh Giá Tổng Thể: {rating_badge} {rating_label}",
            f"",
            f"| Chỉ số kiểm chuẩn | Kết quả thực nghiệm | Đánh giá kỹ thuật |",
            f"| :--- | :---: | :--- |",
            f"| **Điểm chất lượng phiên (Health Score)** | **{avg_score} / 100** | {'Tối ưu' if avg_score >= 85 else 'Có điểm cần cải thiện'} |",
            f"| **Chỉ số Multi-Turn Intent Fidelity** | **{intent_fidelity_rate}%** ({total_turns - num_hijacks}/{total_turns} lượt) | {'Không đứt gãy luồng học tập' if num_hijacks == 0 else f'Phát hiện {num_hijacks} lượt bị cướp luồng (Greeting Loop / Hijacking)'} |",
            f"| **Tỷ lệ tuân thủ Socratic** | **{compliance_rate}%** | {f'{compliant_turns}/{total_turns} lượt đạt chuẩn không giải hộ' if compliance_rate >= 80 else 'Có lượt vi phạm sinh code hoàn chỉnh'} |",
            f"| **Độ trễ TTFT trung bình** | **{avg_ttft} ms** | {'Rất nhanh (Fast-path / Stream)' if avg_ttft < 1500 else 'Bình thường (LLM Inference)'} |",
            f"| **Tỷ lệ kích hoạt Fast-Path** | **{fast_path_count}/{total_turns}** | Giảm tải gọi GPU/LLM không cần thiết |",
            f"",
            f"---",
            f"## Chi Tiết Kiểm Toán Từng Lượt Đối Thoại (Turn-by-Turn Diagnostic)",
            f""
        ]

        for tc in turn_critiques:
            t_num = tc["turn"]
            p = tc["prompt"]
            intent = tc["intent"]
            r_status = tc["retrieval_status"]
            t_score = tc["turn_score"]
            lat = tc["latency"]
            s_check = "✅ Đạt chuẩn" if tc["socratic_compliance"] else "❌ Vi phạm"
            if tc.get("is_intent_hijacked"):
                h_flag = " | 🚨 **Đứt gãy ý định (Hijacked)**"
            elif tc.get("is_topic_intruded"):
                h_flag = " | 🚨 **Xâm nhập chủ đề ngoài lề (Topic Intrusion)**"
            else:
                h_flag = ""

            md_lines.append(f"### Lượt #{t_num}: \"{p}\"")
            md_lines.append(f"- **Điểm lượt:** `{t_score}/100` | **Tuân thủ Socratic:** {s_check}{h_flag}")
            md_lines.append(f"- **Ý định:** `{intent}` (Fast-Path: `{tc['used_fast_path']}`) | **CRAG:** `{r_status}`")
            md_lines.append(f"- **Độ trễ:** TTFT `{lat['ttft_ms']}ms` | Tổng `{lat['total_ms']}ms` ({lat['tokens_per_sec']} tok/s)")

            if tc["socratic_violations"]:
                for v in tc["socratic_violations"]:
                    md_lines.append(f"  - ❌ **Vi phạm:** {v}")
            if tc["warnings"]:
                for w in tc["warnings"]:
                    md_lines.append(f"  - ⚠️ **Cảnh báo:** {w}")
            if tc["merits"]:
                for m in tc["merits"]:
                    md_lines.append(f"  - ✅ **Điểm cộng:** {m}")
            md_lines.append("")

        md_lines.append("---")
        md_lines.append("## Khuyến Nghị Kỹ Thuật & Tối Ưu Hóa Tiếp Theo")
        if num_hijacks > 0:
            md_lines.append(f"- **Multi-Turn Intent Router:** Khắc phục triệt để {num_hijacks} lượt đứt gãy luồng học tập, đảm bảo câu hỏi tiếp nối mang ngữ cảnh học thuật không bị chuyển thành chit_chat.")
        if compliance_rate < 100:
            md_lines.append("- **Socratic Guardrail:** Siết chặt hơn nữa quy tắc cấm hàm `main()` và `#include` trong System Prompt.")
        if avg_ttft > 3000:
            md_lines.append("- **Độ trễ:** Xem xét tinh chỉnh nhiệt độ mô hình hoặc tăng cường Fast-Path cho các câu hỏi phổ biến.")
        if fast_path_count > 0:
            md_lines.append("- **Fast-Path:** Tiếp tục duy trì và mở rộng chỉ mục ngữ nghĩa giáo trình (Syllabus Vector Index) để phân giải tức thời.")
        md_lines.append("- **Lưu trữ:** Tệp log JSON đầy đủ được lưu tại thư mục `logs/playground_debug/` phục vụ quy trình đánh giá RLHF / DPO.")

        critique_markdown = "\n".join(md_lines)

        return {
            "session_id": session_id,
            "course_id": course_id,
            "lesson_seq": lesson_seq,
            "total_turns": total_turns,
            "overall_health_score": avg_score,
            "rating_label": rating_label,
            "socratic_compliance_rate": compliance_rate,
            "intent_fidelity_rate": intent_fidelity_rate,
            "hijacked_turns": hijacked_turns,
            "avg_ttft_ms": avg_ttft,
            "fast_path_count": fast_path_count,
            "grounded_count": grounded_count,
            "coverage_gap_count": coverage_gap_count,
            "turn_critiques": turn_critiques,
            "critique_markdown": critique_markdown,
            "summary": f"Phiên {total_turns} lượt đạt {avg_score}/100 điểm ({rating_label}). Tuân thủ Socratic: {compliance_rate}%. Multi-Turn Intent Fidelity: {intent_fidelity_rate}%. TTFT trung bình: {avg_ttft}ms."
        }

    def export_and_critique_session(
        self,
        session_id: str,
        course_id: str,
        lesson_seq: int,
        turns: List[Dict[str, Any]],
        client_timestamp: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Xuất log tự động ra thư mục logs/playground_debug/ và sinh nhận xét đánh giá.
        """
        logs_dir = _ensure_logs_dir()
        timestamp_clean = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_sid = "".join(c for c in session_id if c.isalnum() or c in ("_", "-")) or "session"
        
        # 1. Chạy đánh giá kiểm toán
        analysis = self.analyze_session(
            session_id=session_id,
            course_id=course_id,
            lesson_seq=lesson_seq,
            turns=turns,
            client_timestamp=client_timestamp
        )

        # 2. Đóng gói payload JSON đầy đủ
        session_export_payload = {
            "metadata": {
                "session_id": session_id,
                "course_id": course_id,
                "lesson_seq": lesson_seq,
                "exported_at": datetime.now().isoformat(),
                "total_turns": len(turns),
                "health_score": analysis["overall_health_score"],
                "socratic_compliance_rate": analysis["socratic_compliance_rate"],
                "avg_ttft_ms": analysis["avg_ttft_ms"],
                "summary": analysis["summary"]
            },
            "critique": {
                "overall_health_score": analysis["overall_health_score"],
                "rating_label": analysis["rating_label"],
                "socratic_compliance_rate": analysis["socratic_compliance_rate"],
                "avg_ttft_ms": analysis["avg_ttft_ms"],
                "turn_critiques": analysis["turn_critiques"]
            },
            "turns": turns
        }

        # 3. Ghi ra tệp JSON
        json_filename = f"session_{safe_sid}_{timestamp_clean}.json"
        json_path = logs_dir / json_filename
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(session_export_payload, f, ensure_ascii=False, indent=2)

        # 4. Ghi ra tệp Markdown Critique
        md_filename = f"session_{safe_sid}_{timestamp_clean}_critique.md"
        md_path = logs_dir / md_filename
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(analysis["critique_markdown"])

        relative_json_path = f"logs/playground_debug/{json_filename}"
        relative_md_path = f"logs/playground_debug/{md_filename}"

        return {
            "status": "success",
            "message": f"Đã lưu log thành công vào {relative_json_path} và sinh nhận xét đánh giá tại {relative_md_path}!",
            "file_path": str(json_path.resolve()),
            "relative_path": relative_json_path,
            "critique_file_path": str(md_path.resolve()),
            "relative_critique_path": relative_md_path,
            "session_id": session_id,
            "total_turns": len(turns),
            "overall_health_score": analysis["overall_health_score"],
            "rating_label": analysis["rating_label"],
            "socratic_compliance_rate": analysis["socratic_compliance_rate"],
            "avg_ttft_ms": analysis["avg_ttft_ms"],
            "summary": analysis["summary"],
            "critique_markdown": analysis["critique_markdown"],
            "turn_critiques": analysis["turn_critiques"]
        }


# Singleton instance
_telemetry_critic_service: Optional[TelemetryCriticService] = None

def get_telemetry_critic_service() -> TelemetryCriticService:
    global _telemetry_critic_service
    if _telemetry_critic_service is None:
        _telemetry_critic_service = TelemetryCriticService()
    return _telemetry_critic_service

