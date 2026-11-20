import asyncio
import json
import logging
import uuid
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from typing import AsyncGenerator, Dict, Any, List, Optional, Tuple
from markdown_it import MarkdownIt
from openai import AsyncOpenAI

from app.config import settings
from app.services.curriculum import get_curriculum_service, CurriculumService
from app.services.chat_graph import get_chat_graph, commit_assistant_turn, reset_session_state
from app.agent.router import get_intent_router
from app.agent.guardrails import (
    extract_prose_outside_code_and_footer,
    get_session_rate_limiter,
    normalize_user_input,
)
from app.schemas.chat import ChatRequest, SuggestedTimestamp, StreamMetadataEvent

logger = logging.getLogger("uvicorn.error")

# ==============================================================================
# TRI-LAYER ANTI-CJK TOKEN LEAKAGE GUARDRAIL (TẦNG 2 - BACKEND STREAMING)
# ==============================================================================
CJK_REPLACEMENTS = {
    "大约从": "khoảng từ ",
    "大约": "khoảng ",
    "从": "từ ",
    "到": " đến ",
    "浮点数": "số thực",
    "整数": "số nguyên",
    "常量": "hằng số",
    "变量": "biến",
    "指针": "con trỏ",
    "引用": "tham chiếu",
    "。": ". ",
    "（": " (",
    "）": ") ",
    "：": ": ",
    "、": ", "
}

def is_cjk_char(c: str) -> bool:
    """Kiểm tra ký tự thuộc khối CJK (Trung/Hàn/dấu câu CJK) dựa trên khoảng Unicode (Zero Regex)."""
    code = ord(c)
    return (
        (0x4E00 <= code <= 0x9FFF) or
        (0x3400 <= code <= 0x4DBF) or
        (0xF900 <= code <= 0xFAFF) or
        (0x3000 <= code <= 0x303F)
    )


def sanitize_cjk_tokens(text: str) -> str:
    """
    Bắt và loại trừ 100% token chữ Hán hoặc dấu câu CJK từ mô hình Qwen 2.5 Coder (Zero Regex).
    """
    if not text:
        return text
    for zh, vi in CJK_REPLACEMENTS.items():
        if zh in text:
            text = text.replace(zh, vi)
    if any(is_cjk_char(c) for c in text):
        text = "".join(c for c in text if not is_cjk_char(c))
    return text


class TimestampWhitelistHTMLParser(HTMLParser):
    """
    Bộ phân tích cú pháp HTML event-driven chuẩn W3C (Zero Regex) để lọc thẻ <timestamp>.
    Chỉ giữ lại thẻ có thuộc tính sec nằm trong Whitelist valid_secs.
    """
    def __init__(self, valid_secs: set):
        super().__init__()
        self.valid_secs = valid_secs
        self.result: List[str] = []
        self.in_timestamp = False
        self.is_valid = False
        self.tag_attrs: str = ""

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        if tag == "timestamp":
            self.in_timestamp = True
            attr_dict = dict(attrs)
            sec_str = attr_dict.get("sec", "")
            if sec_str and sec_str.isdigit() and int(sec_str) in self.valid_secs:
                self.is_valid = True
                attr_text = " ".join(f'{k}="{v}"' for k, v in attrs if v is not None)
                self.tag_attrs = f" {attr_text}" if attr_text else ""
            else:
                self.is_valid = False
                self.tag_attrs = ""
        else:
            attr_text = (" " + " ".join(f'{k}="{v}"' for k, v in attrs if v is not None)) if attrs else ""
            self.result.append(f"<{tag}{attr_text}>")

    def handle_endtag(self, tag: str):
        if tag == "timestamp":
            if self.is_valid:
                self.result.append("</timestamp>")
            self.in_timestamp = False
            self.is_valid = False
            self.tag_attrs = ""
        else:
            self.result.append(f"</{tag}>")

    def handle_data(self, data: str):
        if self.in_timestamp:
            if self.is_valid:
                if self.tag_attrs:
                    self.result.append(f"<timestamp{self.tag_attrs}>")
                    self.tag_attrs = ""
                self.result.append(data)
        else:
            self.result.append(data)


def clean_dangling_timestamp_artifacts(text: str) -> str:
    """
    Làm sạch dấu phân tách '|' lơ lửng và dòng '📍 **Mốc video bài giảng:**' rỗng
    sau khi các thẻ <timestamp> không hợp lệ bị lọc bỏ (Zero Regex).
    """
    if not text:
        return text

    lines = text.split("\n")
    cleaned_lines: List[str] = []
    in_code_fence = False

    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith("```"):
            in_code_fence = not in_code_fence
            cleaned_lines.append(line)
            continue

        if in_code_fence:
            cleaned_lines.append(line)
            continue

        if "Mốc video bài giảng" in line:
            marker_idx = line.find("Mốc video bài giảng")
            colon_idx = line.find(":", marker_idx)
            if colon_idx != -1:
                end_header = colon_idx + 1
                while end_header < len(line) and line[end_header] == "*":
                    end_header += 1
                header_part = line[:end_header]
                rest_part = line[end_header:]
                valid_parts = [p.strip() for p in rest_part.split("|") if p.strip(" -•,;")]
                if not valid_parts:
                    continue
                cleaned_lines.append(f"{header_part.rstrip()} {' | '.join(valid_parts)}")
                continue

        is_md_table_row = (
            stripped_line.startswith("|")
            and stripped_line.endswith("|")
            and len(stripped_line) >= 2
        )
        if "|" in line and not is_md_table_row:
            leading_ws_len = len(line) - len(line.lstrip(" \t"))
            leading_ws = line[:leading_ws_len]
            work = line[leading_ws_len:]

            if "||" not in work:
                raw_parts = work.split("|")
                cleaned_parts: List[str] = []
                for idx_p, part in enumerate(raw_parts):
                    if idx_p == 0:
                        cleaned_parts.append(part.rstrip())
                    elif part.strip():
                        cleaned_parts.append(part.strip())

                if len(cleaned_parts) == 1:
                    work = cleaned_parts[0]
                else:
                    first = cleaned_parts[0]
                    rest = cleaned_parts[1:]
                    if first.endswith(":") and rest:
                        work = f"{first} {' | '.join(rest)}"
                    elif not first and rest:
                        work = " | ".join(rest)
                    elif rest:
                        work = " | ".join([first] + rest)
                    else:
                        work = first

            while ": |" in work or ":|" in work:
                work = work.replace(": | ", ": ").replace(": |", ": ").replace(":|", ": ")

            if work.rstrip().endswith("|"):
                work = work.rstrip(" |\t")

            if not work.strip():
                continue

            cleaned_lines.append(f"{leading_ws}{work}")
            continue

        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n\n", "\n\n")
    return cleaned.rstrip()


def sanitize_timestamp_tags(text: str, valid_secs: set) -> str:
    """
    Deterministic Timestamp Whitelist Guardrail (Zero Regex):
    Loại bỏ triệt để các thẻ <timestamp sec="X"> không nằm trong danh mục Whitelist được bảo chứng.
    - Nếu valid_secs rỗng hoặc không có thẻ: Loại bỏ toàn bộ thẻ <timestamp>, giữ lại nội dung trơn.
    - Nếu valid_secs có phần tử: Bắt buộc sec phải thuộc valid_secs.
    """
    if not text:
        return text
    if "<timestamp" not in text:
        if "Mốc video bài giảng" in text or "|" in text:
            return clean_dangling_timestamp_artifacts(text)
        return text

    parser = TimestampWhitelistHTMLParser(valid_secs)
    try:
        parser.feed(text)
        cleaned = "".join(parser.result)
        return clean_dangling_timestamp_artifacts(cleaned)
    except Exception as e:
        logger.warning(f"[sanitize_timestamp_tags] Lỗi HTML parser: {e}. Trả về văn bản gốc.")
        return clean_dangling_timestamp_artifacts(text)


class StreamingTimestampSanitizer:
    """
    Máy trạng thái hữu hạn (FSM) 3 trạng thái kiểm chuẩn thẻ Timestamp thời gian thực trong luồng SSE:
    - Trạng thái EMIT: Phát trực tiếp các token văn bản thông thường. Khi gặp ký tự '<' có thể là thẻ mở, chuyển sang ACCUMULATE_TAG.
    - Trạng thái ACCUMULATE_TAG: Đệm toàn bộ thẻ mở <timestamp sec="X">. Bóc tách sec và đối chiếu Whitelist valid_secs.
    - Trạng thái STREAM_BODY: Thu thập nhãn hiển thị bên trong cho tới khi gặp </timestamp>.
      Nếu sec in valid_secs: giữ lại thẻ hoàn chỉnh <timestamp sec="X">label</timestamp>.
      Nếu sec not in valid_secs hoặc thẻ bị lỗi/cắt cụt: triệt tiêu thẻ, chỉ phát nhãn hiển thị.
    Hoàn toàn không dùng heuristic xả buffer len > 150.
    """
    STATE_EMIT = "EMIT"
    STATE_ACCUMULATE_TAG = "ACCUMULATE_TAG"
    STATE_STREAM_BODY = "STREAM_BODY"

    def __init__(self, valid_secs: set):
        self.valid_secs = valid_secs
        self.state = self.STATE_EMIT
        self.buffer = ""
        self.tag_open = ""
        self.is_valid_sec = False
        self.body_buffer = ""
        self._just_dropped_tag = False
        self.pending_separator = ""
        self._after_timestamp = False
        self._has_emitted_valid_tag_on_line = False

    def _emit_plain_segment(self, seg: str, out: List[str]) -> None:
        if not seg and not self.pending_separator:
            return
        combined = self.pending_separator + seg
        self.pending_separator = ""

        if "\n" in combined:
            self._has_emitted_valid_tag_on_line = False
            self._after_timestamp = False
            self._just_dropped_tag = False

        stripped_len = len(combined.rstrip(" |\t"))
        prefix = combined[:stripped_len]
        trailing_sep = combined[stripped_len:]

        if prefix:
            out.append(prefix)
            self._after_timestamp = False
            self._just_dropped_tag = False

        if trailing_sep:
            if "|" in trailing_sep or self._after_timestamp or self._just_dropped_tag:
                self.pending_separator = trailing_sep
            else:
                out.append(trailing_sep)

    def process(self, token: str) -> List[str]:
        self.buffer += token
        out: List[str] = []

        while self.buffer:
            if self.state == self.STATE_EMIT:
                if self._just_dropped_tag and not self._has_emitted_valid_tag_on_line:
                    if all(c in " |" for c in self.buffer):
                        if "|" in self.buffer:
                            self.buffer = ""
                            self._just_dropped_tag = False
                            if "|" in self.pending_separator:
                                self.pending_separator = ""
                        break
                    elif self.buffer.lstrip(" ").startswith("|"):
                        idx = self.buffer.find("|")
                        self.buffer = self.buffer[idx + 1:].lstrip(" ")
                        self._just_dropped_tag = False
                        if "|" in self.pending_separator:
                            self.pending_separator = ""
                        continue
                    else:
                        self._just_dropped_tag = False

                lt_idx = self.buffer.find("<")
                if lt_idx == -1:
                    self._emit_plain_segment(self.buffer, out)
                    self.buffer = ""
                    break
                elif lt_idx > 0:
                    self._emit_plain_segment(self.buffer[:lt_idx], out)
                    self.buffer = self.buffer[lt_idx:]

                # Buffer bắt đầu bằng '<'
                if "<timestamp".startswith(self.buffer):
                    # Đang khớp một phần của '<timestamp', chờ thêm token
                    break
                elif self.buffer.startswith("<timestamp"):
                    self.state = self.STATE_ACCUMULATE_TAG
                else:
                    # Ký tự '<' thông thường không phải thẻ timestamp (ví dụ i < n hoặc template <T>)
                    self._emit_plain_segment(self.buffer[0], out)
                    self.buffer = self.buffer[1:]

            elif self.state == self.STATE_ACCUMULATE_TAG:
                gt_idx = self.buffer.find(">")
                if gt_idx == -1:
                    # Chưa đóng thẻ mở, chờ thêm token
                    break

                full_open_tag = self.buffer[:gt_idx + 1]
                self.buffer = self.buffer[gt_idx + 1:]

                # Bóc tách thuộc tính sec không dùng regex
                sec_val = None
                sec_idx = full_open_tag.find("sec=")
                if sec_idx != -1:
                    val_part = full_open_tag[sec_idx + 4:].lstrip(" \"'")
                    digits = []
                    for c in val_part:
                        if c.isdigit():
                            digits.append(c)
                        else:
                            break
                    if digits:
                        sec_val = int("".join(digits))

                if sec_val is not None:
                    self.is_valid_sec = (sec_val in self.valid_secs)
                    self.tag_open = full_open_tag
                else:
                    self.is_valid_sec = False
                    self.tag_open = ""

                self.body_buffer = ""
                self.state = self.STATE_STREAM_BODY

            elif self.state == self.STATE_STREAM_BODY:
                close_tag = "</timestamp>"
                close_idx = self.buffer.find(close_tag)
                if close_idx != -1:
                    body = self.body_buffer + self.buffer[:close_idx]
                    self.buffer = self.buffer[close_idx + len(close_tag):]

                    if self.is_valid_sec:
                        if self.pending_separator:
                            if self._just_dropped_tag and not self._has_emitted_valid_tag_on_line and "|" in self.pending_separator:
                                if self.pending_separator.startswith(" "):
                                    out.append(" ")
                            else:
                                out.append(self.pending_separator)
                            self.pending_separator = ""
                        out.append(f"{self.tag_open}{body}{close_tag}")
                        self._has_emitted_valid_tag_on_line = True
                        self._after_timestamp = True
                        self._just_dropped_tag = False
                    else:
                        if "|" in self.pending_separator:
                            self.pending_separator = ""
                        self._just_dropped_tag = True
                        self._after_timestamp = True

                    # Reset trạng thái về EMIT
                    self.tag_open = ""
                    self.body_buffer = ""
                    self.is_valid_sec = False
                    self.state = self.STATE_EMIT
                else:
                    # Tìm tiền tố dài nhất của </timestamp> ở cuối buffer để tránh bị cắt vụn
                    matched_prefix_len = 0
                    for p_len in range(min(len(self.buffer), len(close_tag) - 1), 0, -1):
                        if close_tag.startswith(self.buffer[-p_len:]):
                            matched_prefix_len = p_len
                            break

                    if matched_prefix_len > 0:
                        safe_chunk = self.buffer[:-matched_prefix_len]
                        self.body_buffer += safe_chunk
                        self.buffer = self.buffer[-matched_prefix_len:]
                    else:
                        self.body_buffer += self.buffer
                        self.buffer = ""
                    break

        return out

    def flush(self) -> List[str]:
        out: List[str] = []
        if self.state == self.STATE_STREAM_BODY:
            # Thẻ bị cắt cụt trước khi có </timestamp>: triệt tiêu hoàn toàn (không phát nhãn văn bản thô)
            pass
        elif self.state == self.STATE_ACCUMULATE_TAG:
            # Thẻ mở bị cắt cụt: triệt tiêu hoàn toàn thẻ mở lỗi
            pass
        elif self.state == self.STATE_EMIT:
            if self.buffer:
                self._emit_plain_segment(self.buffer, out)
                self.buffer = ""
            if self.pending_separator:
                is_dangling_pipe = "|" in self.pending_separator and (
                    self._after_timestamp or self._just_dropped_tag or self._has_emitted_valid_tag_on_line
                )
                is_dropped_ws = self._just_dropped_tag and all(c in " |\t" for c in self.pending_separator)
                if not is_dangling_pipe and not is_dropped_ws:
                    out.append(self.pending_separator)
                self.pending_separator = ""

        self.buffer = ""
        self.body_buffer = ""
        self.tag_open = ""
        self.is_valid_sec = False
        self._just_dropped_tag = False
        self.pending_separator = ""
        self._after_timestamp = False
        self._has_emitted_valid_tag_on_line = False
        self.state = self.STATE_EMIT
        return out


class StreamingCodeSanitizer:
    """
    Máy trạng thái hữu hạn theo dòng (Line-Oriented FSM Guardrail) loại bỏ 100% rò rỉ mã nguồn bị cấm
    (#include, using namespace std, int main) trên luồng token SSE (0% Regex 'import re').
    Bảo toàn độ trễ TTFT với zero runtime overhead và giữ nguyên tính hợp lệ cặp ngoặc { }.
    """
    SINGLE_LINE_FORBIDDEN_PREFIXES = (
        "#include",
        "using namespace std",
    )
    MAIN_LINE_PREFIXES = (
        "int main(",
        "int main (",
        "void main(",
        "void main (",
        "signed main(",
        "signed main (",
    )
    FORBIDDEN_LINE_PREFIXES = SINGLE_LINE_FORBIDDEN_PREFIXES + MAIN_LINE_PREFIXES
    STUB_LINE = "// [Khung chương trình cơ sở do học viên tự thiết lập]\n"

    def __init__(self):
        self.line_buffer = ""
        self._line_already_emitted = False
        self.is_suppressing_line = False
        self.suppressing_main_header = False
        self.awaiting_main_brace = False
        self._just_consumed_main_open_brace = False
        self.in_main_body = False
        self.main_brace_depth = 0
        self.in_code_fence = False
        self.fence_brace_depth = 0
        self.has_inserted_stub = False
        self._main_header_had_semicolon = False
        self._in_string = False
        self._in_char = False
        self._escape = False
        self._in_line_comment = False
        self._in_block_comment = False
        self._prev_char = ""

    def _reset_lexer_state(self) -> None:
        self._in_string = False
        self._in_char = False
        self._escape = False
        self._in_line_comment = False
        self._in_block_comment = False
        self._prev_char = ""

    def _reset_block_state(self) -> None:
        self.has_inserted_stub = False
        self.awaiting_main_brace = False
        self._just_consumed_main_open_brace = False
        self.in_main_body = False
        self.main_brace_depth = 0
        self.fence_brace_depth = 0
        self._main_header_had_semicolon = False
        self._reset_lexer_state()

    def _advance_lexer(self, char: str) -> Optional[str]:
        if char == "\n":
            self._in_line_comment = False
            self._escape = False
            self._prev_char = ""
            return None
        if self._in_line_comment:
            return None
        if self._in_block_comment:
            if self._prev_char == "*" and char == "/":
                self._in_block_comment = False
                self._prev_char = ""
                return None
            self._prev_char = char
            return None
        if self._in_string:
            if self._escape:
                self._escape = False
            elif char == "\\":
                self._escape = True
            elif char == '"':
                self._in_string = False
            self._prev_char = char
            return None
        if self._in_char:
            if self._escape:
                self._escape = False
            elif char == "\\":
                self._escape = True
            elif char == "'":
                self._in_char = False
            self._prev_char = char
            return None

        if char == '"':
            self._in_string = True
            self._prev_char = char
            return None
        if char == "'":
            self._in_char = True
            self._prev_char = char
            return None
        if self._prev_char == "/" and char == "/":
            self._in_line_comment = True
            self._prev_char = ""
            return None
        if self._prev_char == "/" and char == "*":
            self._in_block_comment = True
            self._prev_char = ""
            return None

        self._prev_char = char
        if char in ("{", "}", ";"):
            return char
        return None

    def _filter_and_track_char(self, char: str) -> str:
        if self.in_main_body:
            tok = self._advance_lexer(char)
            if tok == "{":
                self.main_brace_depth += 1
                return char
            if tok == "}":
                if self.main_brace_depth == 1:
                    self.main_brace_depth = 0
                    self.in_main_body = False
                    return ""
                self.main_brace_depth -= 1
                return char
            return char

        if self.in_code_fence:
            tok = self._advance_lexer(char)
            if tok == "{":
                self.fence_brace_depth += 1
                return char
            if tok == "}":
                if self.fence_brace_depth > 0:
                    self.fence_brace_depth -= 1
                    return char
                return ""
            return char

        return char

    @staticmethod
    def _strip_line_comment(text: str) -> str:
        in_str = False
        in_chr = False
        esc = False
        for idx, ch in enumerate(text):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif in_chr:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == "'":
                    in_chr = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "'":
                    in_chr = True
                elif ch == "/" and idx + 1 < len(text) and text[idx + 1] == "/":
                    return text[:idx]
        return text

    @classmethod
    def _is_top_level_return_line(cls, stripped: str) -> Tuple[bool, bool]:
        code_part = cls._strip_line_comment(stripped).strip()
        closes_main = False
        if code_part.endswith("}"):
            without_brace = code_part[:-1].strip()
            if without_brace == "return;" or (
                (without_brace.startswith("return ") or without_brace.startswith("return\t") or without_brace.startswith("return("))
                and without_brace.endswith(";")
            ):
                return True, True
        is_ret = code_part == "return;" or (
            (code_part.startswith("return ") or code_part.startswith("return\t") or code_part.startswith("return("))
            and code_part.endswith(";")
        )
        return is_ret, closes_main

    def _is_potential_buffered_start(self, stripped: str) -> bool:
        if not stripped:
            return True
        if any(p.startswith(stripped) for p in self.FORBIDDEN_LINE_PREFIXES):
            return True
        if "```".startswith(stripped) or stripped.startswith("```"):
            return True
        if self.in_main_body and self.main_brace_depth == 1:
            if "return".startswith(stripped):
                return True
            if stripped in ("return ", "return\t", "return(") or (
                stripped.startswith("return ") or stripped.startswith("return\t") or stripped.startswith("return(")
            ):
                return True
        return False

    def process(self, token: str) -> List[str]:
        out: List[str] = []
        for char in token:
            if self.is_suppressing_line:
                if char == "\n":
                    self.is_suppressing_line = False
                    self._in_line_comment = False
                    self._escape = False
                    self._prev_char = ""
                    if self.suppressing_main_header:
                        self.suppressing_main_header = False
                        if self.main_brace_depth > 0:
                            self.in_main_body = True
                        elif not self._main_header_had_semicolon:
                            self.awaiting_main_brace = True
                        self._main_header_had_semicolon = False
                elif self.suppressing_main_header:
                    tok = self._advance_lexer(char)
                    if tok == "{":
                        self.main_brace_depth += 1
                    elif tok == "}" and self.main_brace_depth > 0:
                        self.main_brace_depth -= 1
                    elif tok == ";" and self.main_brace_depth == 0:
                        self._main_header_had_semicolon = True
                continue

            if self._just_consumed_main_open_brace:
                if char == "\n":
                    self._just_consumed_main_open_brace = False
                    self.line_buffer = ""
                    self._in_line_comment = False
                    continue
                if char in (" ", "\t") and not self.line_buffer.strip():
                    self.line_buffer += char
                    continue
                self._just_consumed_main_open_brace = False
                self.line_buffer = ""

            if self.awaiting_main_brace:
                if char == "\n":
                    out.append(self.line_buffer + "\n")
                    self.line_buffer = ""
                    continue
                if char in (" ", "\t") and not self.line_buffer.strip():
                    self.line_buffer += char
                    continue
                if char == "{" and not self.line_buffer.strip():
                    self.line_buffer = ""
                    self.awaiting_main_brace = False
                    self.in_main_body = True
                    self.main_brace_depth = 1
                    self._just_consumed_main_open_brace = True
                    continue
                self.awaiting_main_brace = False

            if self._line_already_emitted:
                filtered = self._filter_and_track_char(char)
                if filtered:
                    out.append(filtered)
                if char == "\n":
                    self._line_already_emitted = False
                    self._in_line_comment = False
                continue

            if char == "\n":
                stripped = self.line_buffer.lstrip()
                if stripped.startswith("```"):
                    out.append(self.line_buffer + "\n")
                    if stripped.count("```") == 1:
                        self.in_code_fence = not self.in_code_fence
                        self._reset_block_state()
                elif any(stripped.startswith(p) for p in self.SINGLE_LINE_FORBIDDEN_PREFIXES):
                    if not self.has_inserted_stub:
                        out.append(self.STUB_LINE)
                        self.has_inserted_stub = True
                elif any(stripped.startswith(p) for p in self.MAIN_LINE_PREFIXES):
                    if not self.has_inserted_stub:
                        out.append(self.STUB_LINE)
                        self.has_inserted_stub = True
                    self.awaiting_main_brace = True
                elif self.in_main_body and self.main_brace_depth == 1:
                    is_ret, closes_main = self._is_top_level_return_line(stripped)
                    if is_ret:
                        if closes_main:
                            self.main_brace_depth = 0
                            self.in_main_body = False
                    elif stripped.startswith("}"):
                        self.main_brace_depth = 0
                        self.in_main_body = False
                    else:
                        filtered_line = "".join(self._filter_and_track_char(c) for c in self.line_buffer)
                        out.append(filtered_line + "\n")
                else:
                    filtered_line = "".join(self._filter_and_track_char(c) for c in self.line_buffer)
                    out.append(filtered_line + "\n")

                self.line_buffer = ""
                self._in_line_comment = False
                continue

            self.line_buffer += char
            stripped = self.line_buffer.lstrip()

            if any(stripped.startswith(p) for p in self.SINGLE_LINE_FORBIDDEN_PREFIXES):
                self.is_suppressing_line = True
                self.suppressing_main_header = False
                if not self.has_inserted_stub:
                    out.append(self.STUB_LINE)
                    self.has_inserted_stub = True
                self.line_buffer = ""
                continue

            if any(stripped.startswith(p) for p in self.MAIN_LINE_PREFIXES):
                self.is_suppressing_line = True
                self.suppressing_main_header = True
                self._main_header_had_semicolon = False
                if not self.has_inserted_stub:
                    out.append(self.STUB_LINE)
                    self.has_inserted_stub = True
                self.line_buffer = ""
                continue

            if self.in_main_body and self.main_brace_depth == 1 and stripped.startswith("}"):
                self.main_brace_depth = 0
                self.in_main_body = False
                self.is_suppressing_line = True
                self.suppressing_main_header = False
                self.line_buffer = ""
                continue

            if not self._is_potential_buffered_start(stripped):
                self._line_already_emitted = True
                filtered_buf = "".join(self._filter_and_track_char(c) for c in self.line_buffer)
                if filtered_buf:
                    out.append(filtered_buf)
                self.line_buffer = ""

        return out

    def flush(self) -> List[str]:
        out: List[str] = []
        if self.line_buffer and not self.is_suppressing_line:
            stripped = self.line_buffer.lstrip()
            if stripped.startswith("```"):
                out.append(self.line_buffer)
                if stripped.count("```") == 1:
                    self.in_code_fence = not self.in_code_fence
                    self._reset_block_state()
            elif any(stripped.startswith(p) for p in self.FORBIDDEN_LINE_PREFIXES):
                if not self.has_inserted_stub:
                    out.append(self.STUB_LINE)
                    self.has_inserted_stub = True
            elif self.in_main_body and self.main_brace_depth == 1:
                is_ret, closes_main = self._is_top_level_return_line(stripped)
                if is_ret:
                    if closes_main:
                        self.main_brace_depth = 0
                        self.in_main_body = False
                elif stripped.startswith("}"):
                    self.main_brace_depth = 0
                    self.in_main_body = False
                else:
                    filtered_buf = "".join(self._filter_and_track_char(c) for c in self.line_buffer)
                    if filtered_buf:
                        out.append(filtered_buf)
            else:
                filtered_buf = "".join(self._filter_and_track_char(c) for c in self.line_buffer)
                if filtered_buf:
                    out.append(filtered_buf)
        self.line_buffer = ""
        self._line_already_emitted = False
        self.is_suppressing_line = False
        self.suppressing_main_header = False
        self._just_consumed_main_open_brace = False
        return out


class StreamingInternalArtifactSanitizer:
    """
    Bộ lọc luồng SSE (Zero Regex, 0ms TTFT overhead) ngăn chặn mô hình 7B:
    1. Lặp lời chào xã giao ('Chào bạn!', 'Xin chào!') ở đầu câu trả lời học thuật (course_query).
    2. Nhại lại các nhãn cắt tỉa nội bộ ('[...khung code minh họa ở lượt trước...]',
       '[đã rút gọn phản hồi dài ở lượt trước]', '[rút gọn lượt cũ]').
    Bảo toàn 100% cú pháp mảng C++ (a[i], int arr[100]) và luồng token thực.
    """
    GREETING_OPENINGS = (
        "xin chào các bạn",
        "xin chào bạn",
        "xin chào em",
        "xin chào",
        "chào các bạn",
        "chào bạn",
        "chào em",
    )
    OUT_OF_LESSON_VIDEO_OPENINGS = (
        "theo đoạn video bài giảng",
        "theo đoạn video này",
        "theo đoạn video",
        "theo video bài giảng",
        "trong đoạn video này",
        "trong đoạn video",
    )
    FORBIDDEN_BRACKET_MARKERS = (
        "[...khung code minh họa ở lượt trước...]",
        "[đã rút gọn phản hồi dài ở lượt trước]",
        "[rút gọn lượt cũ]",
    )
    CPP_LOWER_PREFIXES = (
        "int ", "void ", "double ", "float ", "char ", "bool ", "long ", "short ",
        "string ", "class ", "struct ", "const ", "static ", "virtual ",
        "for ", "while ", "if ", "vector", "std::", "`",
    )

    def __init__(self, forbid_video_opening: bool = False):
        self.forbid_video_opening = forbid_video_opening
        self._checked_opening = False
        self._need_capitalize = False
        self._opening_buf = ""
        self._marker_buf = ""
        self._emitted_any = False

    def _active_openings(self) -> Tuple[str, ...]:
        if self.forbid_video_opening:
            return self.GREETING_OPENINGS + self.OUT_OF_LESSON_VIDEO_OPENINGS
        return self.GREETING_OPENINGS

    def _consume_opening(self, text: str) -> str:
        if self._checked_opening:
            return text

        self._opening_buf += text
        openings = self._active_openings()

        while self._opening_buf:
            work = self._opening_buf.lstrip(" \t\r\n")
            if not work:
                # Chỉ toàn khoảng trắng đầu luồng, chờ thêm ký tự thực
                if len(self._opening_buf) > 16:
                    self._checked_opening = True
                    out = self._opening_buf
                    self._opening_buf = ""
                    return out
                return ""

            low = work.lower()
            stripped_one = False

            for pref in openings:
                if low.startswith(pref):
                    after = len(pref)
                    if after == len(work):
                        # Chờ thêm token để biết sau cụm chào là dấu câu gì
                        self._opening_buf = work
                        return ""
                    next_ch = work[after]
                    if next_ch in ("!", ",", ".", ":", "-", "—"):
                        cur = after + 1
                        if cur == len(work):
                            # Chờ thêm khoảng trắng sau dấu câu
                            self._opening_buf = work[cur:]
                            self._need_capitalize = True
                            return ""
                        while cur < len(work) and work[cur] in ("!", ",", ".", ":", "-", "—", " ", "\t", "\n"):
                            cur += 1
                        self._opening_buf = work[cur:]
                        self._need_capitalize = True
                        stripped_one = True
                        break

            if stripped_one:
                continue

            # Kiểm tra xem chuỗi hiện tại có đang là tiền tố chưa hoàn chỉnh của một mẫu mở đầu cần lọc không
            if any(pref.startswith(low) for pref in openings):
                self._opening_buf = work
                return ""

            # Không khớp mẫu mở đầu cần lọc -> Xả ngay lập tức
            if self._need_capitalize and work:
                if len(work) < 6 and any(kw.startswith(low) for kw in self.CPP_LOWER_PREFIXES):
                    self._opening_buf = work
                    return ""
                if not any(work.startswith(kw) for kw in self.CPP_LOWER_PREFIXES):
                    if work[0].isalpha() and work[0].islower():
                        work = work[0].upper() + work[1:]
                self._need_capitalize = False

            self._checked_opening = True
            self._opening_buf = ""
            return work

        return ""

    def _filter_brackets(self, text: str) -> List[str]:
        if not text and not self._marker_buf:
            return []
        self._marker_buf += text
        out: List[str] = []

        while self._marker_buf:
            b_idx = self._marker_buf.find("[")
            if b_idx == -1:
                out.append(self._marker_buf)
                self._marker_buf = ""
                break
            if b_idx > 0:
                out.append(self._marker_buf[:b_idx])
                self._marker_buf = self._marker_buf[b_idx:]

            low_rem = self._marker_buf.lower()
            matched_full = None
            for marker in self.FORBIDDEN_BRACKET_MARKERS:
                if low_rem.startswith(marker):
                    matched_full = marker
                    break

            if matched_full is not None:
                # Nuốt trọn nhãn nội bộ bị nhại (kèm khoảng trắng thừa ngay sau nếu có)
                cut_len = len(matched_full)
                self._marker_buf = self._marker_buf[cut_len:]
                if out and out[-1].endswith("... "):
                    out[-1] = out[-1][:-4]
                elif out and out[-1].endswith("..."):
                    out[-1] = out[-1][:-3]
                continue

            if any(marker.startswith(low_rem) for marker in self.FORBIDDEN_BRACKET_MARKERS):
                # Đang khớp dở tiền tố của nhãn nội bộ, giữ trong buffer chờ token kế tiếp
                break

            # Dấu '[' bình thường (ví dụ a[i], int a[100]) -> phát ngay lập tức
            out.append("[")
            self._marker_buf = self._marker_buf[1:]

        return out

    def process(self, token: str) -> List[str]:
        after_opening = self._consume_opening(token)
        if not after_opening:
            return []
        pieces = self._filter_brackets(after_opening)
        if pieces:
            self._emitted_any = True
        return pieces

    def flush(self) -> List[str]:
        out: List[str] = []
        if not self._checked_opening and self._opening_buf:
            work = self._opening_buf
            if self._need_capitalize and work and work[0].isalpha() and work[0].islower():
                work = work[0].upper() + work[1:]
            self._opening_buf = ""
            self._checked_opening = True
            out.extend(self._filter_brackets(work))

        if self._marker_buf:
            low_rem = self._marker_buf.lower()
            if low_rem not in self.FORBIDDEN_BRACKET_MARKERS:
                out.append(self._marker_buf)
            self._marker_buf = ""
        return out


_ROUTER_MANIFEST_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "metadata"
    / "router_intent_manifest.json"
)


@lru_cache(maxsize=1)
def _load_forbidden_closing_prefixes() -> Tuple[str, ...]:
    """Đọc danh sách tiền tố câu kết sáo rỗng từ manifest (Data/Code Separation)."""
    try:
        if _ROUTER_MANIFEST_PATH.exists():
            data = json.loads(_ROUTER_MANIFEST_PATH.read_text(encoding="utf-8"))
            raw = data.get("forbidden_closing_prefixes") or []
            cleaned = [
                str(item).strip().lower()
                for item in raw
                if isinstance(item, str) and str(item).strip()
            ]
            cleaned.sort(key=len, reverse=True)
            return tuple(cleaned)
    except Exception as exc:
        logger.warning(f"[ChatService] Không đọc được forbidden_closing_prefixes: {exc}")
    return ()


def _tokenize_words_simple(text: str) -> List[str]:
    """Tách từ chỉ giữ ký tự chữ/số (Zero Regex)."""
    if not text:
        return []
    buf: List[str] = []
    tokens: List[str] = []
    for ch in text.lower():
        if ch.isalnum():
            buf.append(ch)
        elif buf:
            tokens.append("".join(buf))
            buf.clear()
    if buf:
        tokens.append("".join(buf))
    return tokens


def _split_prose_sentences(prose: str) -> List[str]:
    """Tách văn xuôi thành các câu không rỗng dựa trên dấu kết câu / xuống dòng (Zero Regex)."""
    if not prose:
        return []
    sentences: List[str] = []
    buf: List[str] = []
    for ch in prose:
        buf.append(ch)
        if ch in ".!?\n":
            chunk = "".join(buf).strip()
            buf.clear()
            if any(c.isalnum() for c in chunk):
                sentences.append(chunk)
    tail = "".join(buf).strip()
    if any(c.isalnum() for c in tail):
        sentences.append(tail)
    return sentences


def _is_forbidden_closing_sentence(
    sentence: str,
    prefixes: Optional[Tuple[str, ...]] = None,
) -> bool:
    """Kiểm tra câu có bắt đầu bằng tiền tố đóng câu sáo rỗng từ manifest hay không."""
    active_prefixes = prefixes if prefixes is not None else _load_forbidden_closing_prefixes()
    if not active_prefixes or not sentence:
        return False
    if "`" in sentence:
        return False
    norm = sentence.strip(" \t\r\n*-•>\"'“”()[]{}:;,.!?").lower()
    if not norm:
        return False
    for p in active_prefixes:
        if norm.startswith(p) and (len(norm) == len(p) or norm[len(p)] in " \t,.:;!?-–—\"'"):
            if p in ("bạn đã hiểu", "bạn hiểu được"):
                words = norm.split()
                if len(words) > 8 or any(
                    w in words for w in ("nhầm", "sai", "lệch", "ngược", "thiếu")
                ):
                    return False
            return True
    return False


def _strip_forbidden_closing_sentences(prose: str) -> str:
    """Loại bỏ các câu kết sáo rỗng (ví dụ 'Bạn đã hiểu đúng không?') khỏi văn xuôi."""
    if not prose:
        return ""
    prefixes = _load_forbidden_closing_prefixes()
    if not prefixes:
        return prose
    kept: List[str] = []
    buf: List[str] = []
    for ch in prose:
        buf.append(ch)
        if ch in ".!?\n":
            seg = "".join(buf)
            buf.clear()
            if _is_forbidden_closing_sentence(seg, prefixes):
                continue
            kept.append(seg)
    rem = "".join(buf)
    if rem and not _is_forbidden_closing_sentence(rem, prefixes):
        kept.append(rem)
    return "".join(kept).strip()


def is_echo_only_prose(prose: str, user_prompt: Optional[str]) -> bool:
    """
    Phát hiện phản hồi chỉ nhại lại câu hỏi của học viên (ngắn < 220 ký tự, <= 1 câu và trùng từ >= 0.60).
    """
    if not prose or not user_prompt:
        return False
    cleaned = _strip_forbidden_closing_sentences(prose)
    if len(cleaned) >= 220:
        return False
    sentences = _split_prose_sentences(cleaned)
    if len(sentences) != 1:
        return False
    p_tokens = set(_tokenize_words_simple(cleaned))
    u_tokens = set(_tokenize_words_simple(normalize_user_input(user_prompt)))
    if not p_tokens or not u_tokens:
        return False
    overlap = len(p_tokens & u_tokens) / max(1, len(p_tokens))
    return overlap >= 0.60


def _is_bare_timestamp_line(line_text: str) -> bool:
    """Kiểm tra một dòng chỉ gồm các thẻ <timestamp ...>...</timestamp> và ký tự phân tách '|'/khoảng trắng."""
    if not line_text or "<timestamp" not in line_text.lower():
        return False
    # Kiểm tra chỉ có thẻ <timestamp ...>...</timestamp> và không có văn bản ngoài thẻ (trừ khoảng trắng và '|')
    idx = 0
    low = line_text.lower()
    outside_parts: List[str] = []
    has_tag = False
    while idx < len(line_text):
        start = low.find("<timestamp", idx)
        if start == -1:
            outside_parts.append(line_text[idx:])
            break
        outside_parts.append(line_text[idx:start])
        gt_idx = line_text.find(">", start)
        end = low.find("</timestamp>", start)
        if gt_idx == -1 or end == -1 or gt_idx >= end:
            return False
        if "sec=" not in low[start:gt_idx]:
            return False
        has_tag = True
        idx = end + len("</timestamp>")
    if not has_tag:
        return False
    outside_clean = "".join(outside_parts).replace("|", "").strip()
    return outside_clean == ""


def _is_bare_timestamp_prefix(line_text: str) -> bool:
    """Kiểm tra đoạn đầu dòng vẫn có thể là một dòng bare timestamp hợp lệ đang stream dở."""
    stripped = line_text.lstrip(" \t")
    if not stripped:
        return True
    low = stripped.lower()
    if len(low) < len("<timestamp"):
        return "<timestamp".startswith(low)
    if not low.startswith("<timestamp"):
        return False
    # Quét các cặp <timestamp ...>...</timestamp> hoàn chỉnh rồi kiểm phần dư
    pos = 0
    while pos < len(low):
        while pos < len(low) and low[pos] in " \t|":
            pos += 1
        if pos >= len(low):
            return True
        rem = low[pos:]
        if len(rem) < len("<timestamp"):
            return "<timestamp".startswith(rem)
        if not rem.startswith("<timestamp"):
            return False
        close_idx = low.find("</timestamp>", pos)
        if close_idx == -1:
            # Đang đọc dở nội dung bên trong thẻ <timestamp ...>...</timestamp>
            return True
        pos = close_idx + len("</timestamp>")
    return True


def has_trailing_socratic_question(
    text: str,
    window_chars: int = 320,
    user_prompt: Optional[str] = None,
) -> bool:
    """Kiểm tra phần văn xuôi cuối (sau khi loại bỏ câu sáo rỗng & câu nhại) có dấu hỏi Socratic '?' hay không."""
    prose = extract_prose_outside_code_and_footer(text)
    if not prose:
        return False
    cleaned_prose = _strip_forbidden_closing_sentences(prose)
    if not cleaned_prose:
        return False
    if user_prompt and is_echo_only_prose(cleaned_prose, user_prompt):
        return False
    tail = cleaned_prose[-window_chars:] if len(cleaned_prose) > window_chars else cleaned_prose
    return "?" in tail


def build_socratic_closing_question(
    *,
    retrieval_status: str,
    is_curriculum_navigation: bool = False,
    is_overview_query: bool = False,
    is_code_solicitation: bool = False,
    missing_deictic_sec: bool = False,
    lesson_seq: Optional[int] = None,
    target_lesson_seq: Optional[int] = None,
    has_code_block: bool = False,
) -> str:
    """
    Sinh câu hỏi kết thúc Socratic chuẩn mực khi LLM 7B kết thúc câu trả lời bằng câu trần thuật.
    Không dùng câu xã giao sáo rỗng ('Bạn có câu hỏi gì không?', 'nhé!').
    """
    if missing_deictic_sec:
        return (
            "Bạn đang theo dõi đến mốc phút:giây nào hoặc phân đoạn nào "
            "trong mục lục bài học để mình giải thích chính xác phần đó?"
        )
    if retrieval_status == "out_of_lesson":
        if target_lesson_seq is not None:
            return (
                f"Bạn có muốn mình chuyển sang Bài {target_lesson_seq} "
                "và mở đúng đoạn video bài giảng đó không?"
            )
        return "Bạn muốn tập trung tìm hiểu chủ đề hoặc bài học nào trước?"
    if is_curriculum_navigation or is_overview_query:
        les_ref = f"Bài {lesson_seq}" if lesson_seq is not None else "bài học này"
        return (
            f"Trong các phần kiến thức của {les_ref}, bạn muốn đi sâu vào "
            "khái niệm nền tảng hay ví dụ cài đặt nào trước?"
        )
    if is_code_solicitation or has_code_block:
        return (
            "Dựa vào gợi ý phân tích trên, bạn thử tự chỉnh lại phần logic "
            "hoặc điều kiện đó rồi dự đoán kết quả chạy thử sẽ ra sao?"
        )
    return (
        "Theo bạn, nếu thay đổi dữ liệu đầu vào cho ví dụ vừa nêu thì "
        "kết quả thực thi của chương trình sẽ thay đổi như thế nào?"
    )


class StreamingSocraticFooterGuard:
    """
    Bộ bảo vệ Socratic '?' thời gian thực trên luồng SSE (0ms TTFT overhead):
    - Chỉ đệm khi đầu dòng khớp tiền tố footer ('📍', 'Mốc video bài giảng', hoặc dòng bare <timestamp>) hoặc fence ('```' / '~~~').
    - Hỗ trợ phát hiện footer giữa dòng (Edge Case A), hàng rào tilde/biến độ dài (Edge Case B),
      và tự động đóng fence bị cắt cụt trong flush() (Edge Case D).
    - Tự động loại bỏ các câu kết sáo rỗng trong forbidden_closing_prefixes (manifest) trước khi chèn '?'.
    - Hỗ trợ hold_footer_until_flush để giữ footer '📍' cho tới khi xác nhận có <timestamp> hợp lệ (chống dangling '📍')
      và cho phép chạy corrective continuation trên cùng pipeline khi phát hiện câu trả lời chỉ nhại câu hỏi.
    """
    FOOTER_PREFIXES: Tuple[str, ...] = ("📍", "mốc video bài giảng")
    MID_FOOTER_CANDIDATES: Tuple[str, ...] = (
        "📍",
        "mốc video bài giảng",
        "*mốc video bài giảng",
        "**mốc video bài giảng",
    )

    def __init__(
        self,
        fallback_question: str,
        *,
        user_prompt: Optional[str] = None,
        valid_secs: Optional[set] = None,
        hold_footer_until_flush: bool = False,
    ):
        self.fallback_question = fallback_question
        self.user_prompt = user_prompt
        self.valid_secs = valid_secs
        self.hold_footer_until_flush = hold_footer_until_flush

        self.emitted_text = ""
        self._at_line_start = True
        self._line_buf = ""
        self._mid_buf = ""
        self._in_code_fence = False
        self._fence_char: str = ""
        self._fence_len: int = 0
        self._has_seen_footer = False
        self._inserted_question = False

        self._held_footer_buf: str = ""
        self._saved_held_footer_buf: str = ""
        self._suppress_fallback: bool = False

        # Bộ đệm lọc câu kết sáo rỗng (chỉ giữ tiền tố/câu ngắn đang khớp manifest)
        self._closing_prefixes: Tuple[str, ...] = _load_forbidden_closing_prefixes()
        self._closing_buf: str = ""
        self._closing_matched_prefix: bool = False
        self._at_sentence_start: bool = True
        self._pending_sentence_start: bool = False

    def _raw_emit(self, text: str, out: List[str]) -> None:
        if not text:
            return
        if self.hold_footer_until_flush and self._has_seen_footer:
            self._held_footer_buf += text
        else:
            out.append(text)
            self.emitted_text += text

    def _emit_chunk(self, text: str, out: List[str]) -> None:
        """Phát văn bản qua bộ lọc câu kết sáo rỗng nếu đang ở phần prose trước footer."""
        if not text:
            return
        if self._in_code_fence or self._has_seen_footer:
            self._raw_emit(text, out)
            return
        self._emit_prose_text(text, out)

    def _flush_closing_buf(self, out: List[str], *, force_keep: bool = False) -> None:
        if self._closing_buf:
            buf = self._closing_buf
            self._closing_buf = ""
            self._closing_matched_prefix = False
            if force_keep or not _is_forbidden_closing_sentence(buf, self._closing_prefixes):
                self._raw_emit(buf, out)
                last_ch = buf[-1]
                self._pending_sentence_start = last_ch in ".!?"
                self._at_sentence_start = last_ch == "\n"
            else:
                self._at_sentence_start = True
                self._pending_sentence_start = False

    def _emit_prose_text(self, text: str, out: List[str]) -> None:
        for ch in text:
            if self._closing_buf:
                self._closing_buf += ch
                if ch in (".", "!", "?", "\n") or len(self._closing_buf) > 120:
                    buf = self._closing_buf
                    self._closing_buf = ""
                    self._closing_matched_prefix = False
                    if ch in (".", "!", "?", "\n") and _is_forbidden_closing_sentence(buf, self._closing_prefixes):
                        self._at_sentence_start = True
                        self._pending_sentence_start = False
                        if ch == "\n" and self.emitted_text and not self.emitted_text.endswith("\n\n"):
                            self._raw_emit("\n", out)
                    else:
                        self._raw_emit(buf, out)
                        self._pending_sentence_start = ch in ".!?"
                        self._at_sentence_start = ch == "\n"
                    continue

                if self._closing_matched_prefix:
                    continue

                cand = self._closing_buf.lower()
                if any(
                    cand.startswith(p) and (len(cand) == len(p) or cand[len(p)] in " \t,.:;!?-–—\"'")
                    for p in self._closing_prefixes
                ):
                    self._closing_matched_prefix = True
                    continue

                if any(p.startswith(cand) for p in self._closing_prefixes):
                    continue

                buf = self._closing_buf
                self._closing_buf = ""
                self._raw_emit(buf, out)
                self._pending_sentence_start = ch in ".!?"
                self._at_sentence_start = ch == "\n"
                continue

            if self._at_sentence_start:
                if ch in (" ", "\t", "\n"):
                    self._raw_emit(ch, out)
                    continue
                if (
                    ch.isalpha()
                    and self._closing_prefixes
                    and any(p.startswith(ch.lower()) for p in self._closing_prefixes)
                ):
                    self._closing_buf = ch
                    self._closing_matched_prefix = False
                    self._at_sentence_start = False
                    self._pending_sentence_start = False
                    continue
                self._at_sentence_start = False
                self._pending_sentence_start = ch in ".!?"
                self._raw_emit(ch, out)
                continue

            if self._pending_sentence_start:
                if ch in (" ", "\t", "\n"):
                    self._raw_emit(ch, out)
                    self._pending_sentence_start = False
                    self._at_sentence_start = True
                    continue
                self._pending_sentence_start = False

            if ch in ".!?":
                self._pending_sentence_start = True
            elif ch == "\n":
                self._at_sentence_start = True
            self._raw_emit(ch, out)

    def _ensure_question_before_footer(self, out: List[str]) -> None:
        if self._inserted_question or self._has_seen_footer:
            return
        if not self.emitted_text.strip():
            return
        if has_trailing_socratic_question(self.emitted_text, user_prompt=self.user_prompt):
            return
        sep = ""
        if self.emitted_text.endswith("\n\n"):
            sep = ""
        elif self.emitted_text.endswith("\n"):
            sep = "\n"
        else:
            sep = "\n\n"
        self._raw_emit(f"{sep}{self.fallback_question}\n\n", out)
        self._inserted_question = True

    def _enter_footer(self, out: List[str], *, prefix: str = "") -> None:
        self._flush_closing_buf(out)
        if not self.hold_footer_until_flush:
            self._ensure_question_before_footer(out)
        self._has_seen_footer = True
        if prefix:
            self._raw_emit(prefix, out)

    @staticmethod
    def _count_leading_fence_run(probe: str) -> Tuple[str, int]:
        if not probe or probe[0] not in ("`", "~"):
            return "", 0
        f_ch = probe[0]
        run_len = 0
        while run_len < len(probe) and probe[run_len] == f_ch:
            run_len += 1
        return f_ch, run_len

    def _update_fence_state_from_complete_line(self, line_text: str) -> None:
        probe = line_text.rstrip("\r\n").lstrip(" \t*-•>#")
        f_ch, run_len = self._count_leading_fence_run(probe)
        if run_len < 3:
            return
        rest = probe[run_len:]
        if not self._in_code_fence:
            if f_ch == "`" and "`" in rest:
                return
            self._in_code_fence = True
            self._fence_char = f_ch
            self._fence_len = run_len
        else:
            if f_ch == self._fence_char and run_len >= self._fence_len and rest.strip() == "":
                self._in_code_fence = False
                self._fence_char = ""
                self._fence_len = 0

    def _process_mid_line_char(self, char: str, out: List[str]) -> None:
        if self._in_code_fence or self._has_seen_footer:
            self._raw_emit(char, out)
            if char == "\n":
                self._at_line_start = True
            return

        if self._mid_buf:
            cand = self._mid_buf + char
            cand_low = cand.lower()
            if cand_low.lstrip("*") in self.FOOTER_PREFIXES:
                self._enter_footer(out)
                self._raw_emit(cand, out)
                self._mid_buf = ""
                return
            if any(p.startswith(cand_low) for p in self.MID_FOOTER_CANDIDATES):
                self._mid_buf = cand
                return
            self._emit_prose_text(self._mid_buf, out)
            self._mid_buf = ""

        ch_low = char.lower()
        if char == "📍":
            self._enter_footer(out)
            self._raw_emit(char, out)
            return
        if any(p.startswith(ch_low) for p in self.MID_FOOTER_CANDIDATES):
            self._mid_buf = char
            return

        self._emit_prose_text(char, out)
        if char == "\n":
            self._at_line_start = True

    def process(self, token: str) -> List[str]:
        out: List[str] = []
        for char in token:
            if self._at_line_start:
                self._line_buf += char
                if char == "\n":
                    probe_nl = self._line_buf.rstrip("\r\n").lstrip(" \t")
                    if (
                        not self._in_code_fence
                        and not self._has_seen_footer
                        and self.valid_secs
                        and _is_bare_timestamp_line(probe_nl)
                    ):
                        self._enter_footer(out, prefix="📍 **Mốc video bài giảng:** ")
                        self._raw_emit(self._line_buf, out)
                        self._line_buf = ""
                        self._at_line_start = True
                        continue

                    self._update_fence_state_from_complete_line(self._line_buf)
                    self._emit_chunk(self._line_buf, out)
                    self._line_buf = ""
                    self._at_line_start = True
                    continue

                probe = self._line_buf.lstrip(" \t*-•>#")
                if not probe:
                    continue

                f_ch, run_len = self._count_leading_fence_run(probe)
                if f_ch:
                    # Đang đọc chuỗi ký tự fence ('`' hoặc '~') ở đầu dòng
                    if run_len == len(probe):
                        continue
                    if not self._in_code_fence:
                        if run_len >= 3 and (f_ch == "~" or "`" not in probe[run_len:]):
                            self._flush_closing_buf(out)
                            self._in_code_fence = True
                            self._fence_char = f_ch
                            self._fence_len = run_len
                            self._raw_emit(self._line_buf, out)
                            self._line_buf = ""
                            self._at_line_start = False
                            continue
                    else:
                        if (
                            f_ch == self._fence_char
                            and run_len >= self._fence_len
                            and probe[run_len:].strip(" \t\r") == ""
                        ):
                            # Chờ đến '\n' hoặc flush() để xác nhận dòng đóng fence hợp lệ
                            continue
                        self._raw_emit(self._line_buf, out)
                        self._line_buf = ""
                        self._at_line_start = False
                        continue

                probe_low = probe.lower()
                if (
                    not self._in_code_fence
                    and not self._has_seen_footer
                    and any(probe_low.startswith(fp) for fp in self.FOOTER_PREFIXES)
                ):
                    self._enter_footer(out)
                    self._raw_emit(self._line_buf, out)
                    self._line_buf = ""
                    self._at_line_start = False
                    continue

                is_partial_footer = (
                    not self._in_code_fence
                    and not self._has_seen_footer
                    and any(fp.startswith(probe_low) for fp in self.FOOTER_PREFIXES)
                )
                if is_partial_footer:
                    continue

                # Phát hiện dòng chỉ chứa bare <timestamp ...>...</timestamp> (không có '📍')
                probe_ts = self._line_buf.lstrip(" \t")
                if (
                    not self._in_code_fence
                    and not self._has_seen_footer
                    and self.valid_secs
                    and probe_ts.startswith("<")
                    and len(self._line_buf) <= 450
                    and _is_bare_timestamp_prefix(probe_ts)
                ):
                    continue

                self._emit_chunk(self._line_buf, out)
                self._line_buf = ""
                self._at_line_start = False
            else:
                self._process_mid_line_char(char, out)
        return out

    def flush_before_footer(self) -> List[str]:
        """Xả hết phần prose/code đang đệm trước footer (chưa xả footer giữ tạm nếu hold_footer_until_flush=True)."""
        out: List[str] = []
        if self._mid_buf:
            self._emit_chunk(self._mid_buf, out)
            self._mid_buf = ""
        if self._line_buf:
            probe_eof = self._line_buf.rstrip("\r\n").lstrip(" \t")
            if (
                not self._in_code_fence
                and not self._has_seen_footer
                and self.valid_secs
                and _is_bare_timestamp_line(probe_eof)
            ):
                self._enter_footer(out, prefix="📍 **Mốc video bài giảng:** ")
                self._raw_emit(self._line_buf, out)
                self._line_buf = ""
            else:
                self._update_fence_state_from_complete_line(self._line_buf)
                self._emit_chunk(self._line_buf, out)
                self._line_buf = ""
        if not self._in_code_fence and not self._has_seen_footer:
            self._flush_closing_buf(out)
        if self._in_code_fence:
            close_fence = (self._fence_char or "`") * max(3, self._fence_len or 3)
            self._raw_emit(f"\n{close_fence}", out)
            self._in_code_fence = False
            self._fence_char = ""
            self._fence_len = 0
        return out

    def prepare_for_continuation(self) -> List[str]:
        """Bảo lưu footer giữ tạm từ lượt 1 (nếu có) và mở khóa để tiếp nhận token corrective continuation."""
        out: List[str] = []
        if "<timestamp" in self._held_footer_buf:
            self._saved_held_footer_buf = self._held_footer_buf
        self._held_footer_buf = ""
        self._has_seen_footer = False
        self._inserted_question = False
        self._at_line_start = True
        self._at_sentence_start = True
        self._pending_sentence_start = False
        self._closing_buf = ""
        self._closing_matched_prefix = False
        if self.emitted_text and not self.emitted_text.endswith("\n\n"):
            sep = "\n" if self.emitted_text.endswith("\n") else "\n\n"
            self._raw_emit(sep, out)
        return out

    def suppress_fallback_question(self) -> None:
        """Tắt chèn câu hỏi fallback đóng hộp (Zero Fake Fallback khi echo continuation lỗi/timeout)."""
        self._suppress_fallback = True

    def flush_held_footer(self) -> List[str]:
        """Chèn câu hỏi Socratic (nếu còn thiếu và không bị suppress) và xả footer hợp lệ duy nhất (nếu có <timestamp)."""
        out: List[str] = []
        if self.hold_footer_until_flush:
            active_footer = ""
            if "<timestamp" in self._held_footer_buf:
                active_footer = self._held_footer_buf
            elif "<timestamp" in self._saved_held_footer_buf:
                active_footer = self._saved_held_footer_buf
            self._held_footer_buf = ""
            self._saved_held_footer_buf = ""

            if (
                not self._suppress_fallback
                and not self._inserted_question
                and self.emitted_text.strip()
                and not has_trailing_socratic_question(self.emitted_text, user_prompt=self.user_prompt)
            ):
                sep = "" if self.emitted_text.endswith("\n\n") else ("\n" if self.emitted_text.endswith("\n") else "\n\n")
                self._raw_emit_direct(f"{sep}{self.fallback_question}", out)
                self._inserted_question = True

            if active_footer:
                cleaned_footer = active_footer.lstrip("\r\n")
                sep = "" if (not self.emitted_text or self.emitted_text.endswith("\n\n")) else (
                    "\n" if self.emitted_text.endswith("\n") else "\n\n"
                )
                self._raw_emit_direct(f"{sep}{cleaned_footer}", out)
        else:
            if (
                not self._suppress_fallback
                and not self._has_seen_footer
                and not self._inserted_question
                and self.emitted_text.strip()
                and not has_trailing_socratic_question(self.emitted_text, user_prompt=self.user_prompt)
            ):
                sep = "" if self.emitted_text.endswith("\n\n") else ("\n" if self.emitted_text.endswith("\n") else "\n\n")
                self._raw_emit_direct(f"{sep}{self.fallback_question}", out)
                self._inserted_question = True
        return out

    def _raw_emit_direct(self, text: str, out: List[str]) -> None:
        if text:
            out.append(text)
            self.emitted_text += text

    def flush(self) -> List[str]:
        out = self.flush_before_footer()
        out.extend(self.flush_held_footer())
        return out


class StreamingOutputPipeline:
    """
    Chuỗi lọc luồng SSE hợp nhất (Single-Pass Streaming Output Sanitizer Pipeline):
    1. sanitize_cjk_tokens (Tri-Layer Anti-CJK Token Leakage)
    2. StreamingInternalArtifactSanitizer (Khử lời chào lặp & nhãn nội bộ)
    3. StreamingTimestampSanitizer (Deterministic Timestamp Whitelist Guardrail)
    4. StreamingCodeSanitizer (Chống lộ #include, using namespace std, int main)
    5. StreamingSocraticFooterGuard (Đảm bảo câu hỏi Socratic '?' trước footer + lọc closer + giữ footer)
    """

    def __init__(
        self,
        *,
        valid_secs: Optional[set] = None,
        fallback_question: Optional[str] = None,
        forbid_video_opening: bool = False,
        user_prompt: Optional[str] = None,
        hold_footer_until_flush: bool = False,
    ):
        self.user_prompt = user_prompt
        self.artifact_sanitizer = StreamingInternalArtifactSanitizer(
            forbid_video_opening=forbid_video_opening
        )
        self.ts_sanitizer = StreamingTimestampSanitizer(
            valid_secs=valid_secs if valid_secs is not None else set()
        )
        self.code_sanitizer = StreamingCodeSanitizer()
        self.socratic_guard: Optional[StreamingSocraticFooterGuard] = (
            StreamingSocraticFooterGuard(
                fallback_question=fallback_question,
                user_prompt=user_prompt,
                valid_secs=valid_secs,
                hold_footer_until_flush=hold_footer_until_flush,
            )
            if fallback_question
            else None
        )

    @property
    def inserted_fallback_question(self) -> bool:
        return bool(self.socratic_guard and self.socratic_guard._inserted_question)

    def is_echo_only_prose(self, user_prompt: Optional[str] = None) -> bool:
        prompt_to_check = user_prompt if user_prompt is not None else self.user_prompt
        if not self.socratic_guard or not prompt_to_check:
            return False
        return is_echo_only_prose(self.socratic_guard.emitted_text, prompt_to_check)

    def _pipe_from_ts(self, tokens: List[str]) -> List[str]:
        out: List[str] = []
        for tok in tokens:
            if not tok:
                continue
            for c_tok in self.code_sanitizer.process(tok):
                if self.socratic_guard is not None:
                    out.extend(self.socratic_guard.process(c_tok))
                elif c_tok:
                    out.append(c_tok)
        return out

    def process(self, raw_token: str) -> List[str]:
        clean_token = sanitize_cjk_tokens(raw_token)
        if not clean_token:
            return []
        out: List[str] = []
        for art_tok in self.artifact_sanitizer.process(clean_token):
            if not art_tok:
                continue
            out.extend(self._pipe_from_ts(self.ts_sanitizer.process(art_tok)))
        return out

    def flush_before_footer(self) -> List[str]:
        out: List[str] = []
        for art_tok in self.artifact_sanitizer.flush():
            if art_tok:
                out.extend(self._pipe_from_ts(self.ts_sanitizer.process(art_tok)))
        out.extend(self._pipe_from_ts(self.ts_sanitizer.flush()))
        for c_tok in self.code_sanitizer.flush():
            if self.socratic_guard is not None:
                out.extend(self.socratic_guard.process(c_tok))
            elif c_tok:
                out.append(c_tok)
        if self.socratic_guard is not None:
            out.extend(self.socratic_guard.flush_before_footer())
        return out

    def prepare_for_continuation(self) -> List[str]:
        if self.socratic_guard is not None:
            return self.socratic_guard.prepare_for_continuation()
        return []

    def suppress_fallback_question(self) -> None:
        if self.socratic_guard is not None:
            self.socratic_guard.suppress_fallback_question()

    def flush_held_footer(self) -> List[str]:
        if self.socratic_guard is not None:
            return self.socratic_guard.flush_held_footer()
        return []

    def flush(self) -> List[str]:
        out = self.flush_before_footer()
        out.extend(self.flush_held_footer())
        return out


def apply_streaming_sanitizers(
    text: str,
    valid_secs: Optional[set] = None,
    fallback_question: Optional[str] = None,
    forbid_video_opening: bool = False,
    user_prompt: Optional[str] = None,
) -> Tuple[str, bool]:
    """Áp dụng toàn bộ chuỗi StreamingOutputPipeline cho văn bản tĩnh (non-streaming callers)."""
    pipeline = StreamingOutputPipeline(
        valid_secs=valid_secs,
        fallback_question=fallback_question,
        forbid_video_opening=forbid_video_opening,
        user_prompt=user_prompt,
    )
    chunks = pipeline.process(text) + pipeline.flush()
    return "".join(chunks), pipeline.inserted_fallback_question


class ChatService:
    """
    Dịch vụ điều phối trò chuyện Socratic & Truyền phát dữ liệu thời gian thực (SSE Stream):
    - Tích hợp Curriculum Navigation Dispatcher: Fast-Path (< 20ms) cho câu hỏi lộ trình/playlist.
    - Tích hợp Intent Router: Fast-Path (< 1ms) cho chào hỏi / out-of-scope.
    - Tích hợp Advanced Hybrid Retrieval & CRAG Grader qua LangGraph StateGraph.
    - Chuẩn hóa ngữ cảnh U-shaped & trích xuất mốc <timestamp sec="xxx">mm:ss</timestamp>.
    - Kết nối OpenAI-compatible Client (hỗ trợ cả Ollama Local và vLLM Remote).
    """

    def __init__(
        self,
        retrieval_service: Optional[Any] = None,
        openai_client: Optional[AsyncOpenAI] = None
    ):
        self.curriculum_service = get_curriculum_service()
        self.router = get_intent_router()
        self.client = openai_client or AsyncOpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.OPENAI_API_KEY or "vllm",
            default_headers={"ngrok-skip-browser-warning": "true"}
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Xử lý yêu cầu trò chuyện và phát luồng sự kiện SSE (Dual-Channel Server-Sent Events):
        - Hỗ trợ phiên đa lượt (Multi-turn Stateful Session) qua LangGraph Checkpointer theo thread_id.
        - Event 'metadata': Gửi session_id, turn_count, danh sách nguồn trích dẫn, mốc timestamp đề xuất.
        - Event 'delta': Bắn từng token văn bản được sinh ra từ LLM.
        - Event 'done': Báo hiệu hoàn tất luồng truyền phát và tự động lưu vết turn đối thoại.
        """
        # 1. Quản lý Session ID chuẩn hóa & Chuẩn hóa đầu vào người dùng tại cửa ngõ
        session_id = request.session_id or f"session_{uuid.uuid4().hex[:12]}"
        clean_prompt = normalize_user_input(request.prompt)
        config = {"configurable": {"thread_id": session_id}}

        current_video_sec = getattr(request, "current_video_sec", None)

        # Lưu ý quan trọng: KHÔNG truyền "last_course_query": None vào initial_state
        # để bảo toàn mỏ neo hội thoại đã lưu trong LangGraph MemorySaver Checkpointer!
        initial_state = {
            "session_id": session_id,
            "prompt": clean_prompt,
            "course_id": request.course_id,
            "lesson_seq": request.lesson_seq,
            "current_video_sec": current_video_sec,
            "intent": "course_query",
            "direct_response": None,
            "is_course_query": True,
            "search_query": None,
            "is_curriculum_navigation": False,
            "is_overview_query": False,
            "retrieval_status": "coverage_gap",
            "retrieved_chunks": [],
            "is_approximate": False,
            "is_low_confidence": False,
            "target_lesson_seq": None,
            "suggested_timestamps": [],
            "sources": [],
            "system_prompt": "",
            "user_message_content": "",
            "assembled_messages": []
        }

        # Khởi chạy chu trình điều phối Agentic RAG qua LangGraph StateGraph có Checkpointer
        graph = get_chat_graph()
        final_state = await graph.ainvoke(initial_state, config=config)
        turn_count = final_state.get("turn_count", 1)
        logger.info(
            f"[ChatService:LangGraph] Graph hoàn tất: Session={session_id} | Turn={turn_count} | "
            f"Intent={final_state['intent']} | Status={final_state['retrieval_status']} | "
            f"Chunks={len(final_state['retrieved_chunks'])}"
        )

        # 2. Xử lý Fast-Path (Chào hỏi xã giao, cảm ơn, danh tính, ngoài lề, hoặc xác nhận điều hướng đàm thoại)
        # Fast-Path không tiêu tốn tài nguyên LLM/GPU nên không trừ hạn mức Rate Limiter
        if not final_state["is_course_query"]:
            act = final_state.get("action")
            target_seq = final_state.get("target_lesson_seq")
            auto_seek = None
            if act and act.get("type") == "navigate_and_seek":
                target_seq = act.get("target_lesson_seq")
                auto_seek = act.get("sec")

            fast_metadata = StreamMetadataEvent(
                session_id=session_id,
                turn_count=turn_count,
                intent=final_state["intent"],
                used_fast_path=True,
                retrieved_chunk_count=0,
                is_approximate=False,
                retrieval_status="grounded",
                is_low_confidence=False,
                target_lesson_seq=target_seq,
                auto_seek_sec=auto_seek,
                action=act,
                suggested_timestamps=[],
                sources=[]
            )
            yield {
                "event": "metadata",
                "data": fast_metadata.model_dump_json()
            }

            direct_text = final_state["direct_response"] or ""
            words = direct_text.split(" ")
            for i, word in enumerate(words):
                chunk_token = word if i == 0 else " " + word
                yield {
                    "event": "delta",
                    "data": json.dumps({"content": chunk_token})
                }
                await asyncio.sleep(0.015)

            # Lưu vết lượt Fast-Path vào Checkpointer
            commit_assistant_turn(
                session_id,
                clean_prompt,
                direct_text,
                current_lesson_seq=request.lesson_seq,
                last_course_query=final_state.get("last_course_query")
            )

            yield {
                "event": "done",
                "data": "[DONE]"
            }
            return

        # 2b. Kiểm tra Rate Limiting chỉ cho các truy vấn gọi LLM/GPU (cho phép phiên học/demo tuần tự 10+ lượt mượt mà)
        rate_limiter = get_session_rate_limiter()
        if rate_limiter.max_per_minute < 20:
            rate_limiter.max_per_minute = 20
            rate_limiter.max_per_hour = max(rate_limiter.max_per_hour, 180)
        is_allowed, rate_msg, retry_after = rate_limiter.check_rate_limit(session_id)
        if not is_allowed:
            metadata_event = StreamMetadataEvent(
                session_id=session_id,
                turn_count=turn_count,
                intent="rate_limited",
                used_fast_path=True,
                retrieved_chunk_count=0,
                is_approximate=False,
                retrieval_status="coverage_gap",
                is_low_confidence=False,
                target_lesson_seq=None,
                suggested_timestamps=[],
                sources=[]
            )
            yield {
                "event": "metadata",
                "data": metadata_event.model_dump_json()
            }
            words = (rate_msg or "Vui lòng gửi câu hỏi chậm lại để có thời gian thực hành nhé.").split(" ")
            for i, word in enumerate(words):
                chunk_token = word if i == 0 else " " + word
                yield {
                    "event": "delta",
                    "data": json.dumps({"content": chunk_token})
                }
                await asyncio.sleep(0.012)
            yield {
                "event": "done",
                "data": "[DONE]"
            }
            return

        # 3. Gửi sự kiện 'metadata' đầu tiên cho Frontend UI từ kết quả đồ thị
        # [Zero Auto-Seek Invariant - Phương Án A]:
        # Tuyệt đối CẤM cơ chế tự ý giật màn hình hoặc ép video tự tua ở client.
        # auto_seek_sec được cố định là None; 100% việc tua video do học viên chủ động bấm nút.
        suggested_ts = [
            SuggestedTimestamp(**ts) for ts in final_state.get("suggested_timestamps", [])
        ]
        auto_seek_sec = None

        meta_event = StreamMetadataEvent(
            session_id=session_id,
            turn_count=turn_count,
            intent=final_state["intent"],
            used_fast_path=False,
            retrieved_chunk_count=len(final_state["retrieved_chunks"]),
            is_approximate=final_state["is_approximate"],
            retrieval_status=final_state["retrieval_status"],
            is_low_confidence=final_state["is_low_confidence"],
            target_lesson_seq=final_state["target_lesson_seq"],
            auto_seek_sec=auto_seek_sec,
            action=final_state.get("action"),
            suggested_timestamps=suggested_ts,
            sources=final_state.get("sources", [])
        )
        yield {
            "event": "metadata",
            "data": meta_event.model_dump_json()
        }

        # Sử dụng danh sách tin nhắn ChatML đa lượt do Node context_assembly đóng gói
        raw_messages = final_state.get("assembled_messages")
        if not raw_messages:
            raw_messages = [
                {"role": "system", "content": final_state["system_prompt"]},
                {"role": "user", "content": final_state["user_message_content"]}
            ]

        messages = [dict(m) for m in raw_messages]

        full_assistant_response = ""

        try:
            stream_response = await self.client.chat.completions.create(
                model=settings.LLM_MODEL_NAME,
                messages=messages,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                presence_penalty=0.5,
                frequency_penalty=0.5,
                stop=["\n\n\n", "Học viên:", "Sinh viên:", "<|im_end|>"],
                stream=True,
                timeout=25.0
            )

            retrieval_status = final_state.get("retrieval_status", "coverage_gap")
            is_nav_turn = bool(final_state.get("is_curriculum_navigation", False))

            # Tập hợp Whitelist các mốc giây được bảo chứng (ERR-02)
            valid_secs = set()
            for item in final_state.get("suggested_timestamps", []):
                if isinstance(item, dict) and item.get("sec") is not None:
                    valid_secs.add(int(item["sec"]))

            is_solicitation_turn = self.router.is_code_solicitation(clean_prompt)
            if "is_overview_query" in final_state:
                is_overview_turn = bool(final_state.get("is_overview_query", False))
            else:
                is_overview_turn = self.curriculum_service.is_overview_query(clean_prompt)
            fallback_socratic_q = build_socratic_closing_question(
                retrieval_status=retrieval_status,
                is_curriculum_navigation=is_nav_turn,
                is_overview_query=is_overview_turn,
                is_code_solicitation=is_solicitation_turn,
                missing_deictic_sec=bool(final_state.get("missing_deictic_sec", False)),
                lesson_seq=request.lesson_seq,
                target_lesson_seq=final_state.get("target_lesson_seq"),
            )
            pipeline = StreamingOutputPipeline(
                valid_secs=valid_secs,
                fallback_question=fallback_socratic_q,
                forbid_video_opening=(retrieval_status == "out_of_lesson" or is_nav_turn),
                user_prompt=clean_prompt,
                hold_footer_until_flush=True,
            )

            async for chunk in stream_response:
                if chunk.choices and chunk.choices[0].delta.content:
                    for s_tok in pipeline.process(chunk.choices[0].delta.content):
                        full_assistant_response += s_tok
                        yield {
                            "event": "delta",
                            "data": json.dumps({"content": s_tok})
                        }

            # Xả các token prose/code trước footer
            for s_tok in pipeline.flush_before_footer():
                full_assistant_response += s_tok
                yield {
                    "event": "delta",
                    "data": json.dumps({"content": s_tok})
                }

            # PC-04 Echo-Only Corrective Continuation (chạy tối đa 1 lượt nối tiếp qua CÙNG pipeline)
            echo_continuation_failed = False
            if (
                retrieval_status == "grounded"
                and final_state.get("retrieved_chunks")
                and pipeline.is_echo_only_prose(clean_prompt)
            ):
                try:
                    cont_messages = messages + [
                        {"role": "assistant", "content": full_assistant_response.strip()},
                        {
                            "role": "user",
                            "content": (
                                "[CHỈ THỊ SỬA LỖI]: Câu trên mới chỉ lặp lại câu hỏi của học viên. "
                                "Hãy đánh giá rõ đúng hay chưa đúng, giải thích bản chất kỹ thuật C++ "
                                "trong 2–3 câu dựa trên ngữ cảnh bài giảng, và kết thúc bằng 1 câu hỏi "
                                "Socratic MỚI có dấu ?. CẤM chào hỏi, CẤM tự sinh thẻ timestamp."
                            ),
                        },
                    ]
                    cont_stream = await self.client.chat.completions.create(
                        model=settings.LLM_MODEL_NAME,
                        messages=cont_messages,
                        temperature=settings.LLM_TEMPERATURE,
                        max_tokens=settings.LLM_MAX_TOKENS,
                        presence_penalty=0.5,
                        frequency_penalty=0.5,
                        stop=["\n\n\n", "Học viên:", "Sinh viên:", "<|im_end|>"],
                        stream=True,
                        timeout=15.0,
                    )
                    for sep_tok in pipeline.prepare_for_continuation():
                        full_assistant_response += sep_tok
                        yield {
                            "event": "delta",
                            "data": json.dumps({"content": sep_tok})
                        }
                    async for c_chunk in cont_stream:
                        if c_chunk.choices and c_chunk.choices[0].delta.content:
                            for s_tok in pipeline.process(c_chunk.choices[0].delta.content):
                                full_assistant_response += s_tok
                                yield {
                                    "event": "delta",
                                    "data": json.dumps({"content": s_tok})
                                }
                    for s_tok in pipeline.flush_before_footer():
                        full_assistant_response += s_tok
                        yield {
                            "event": "delta",
                            "data": json.dumps({"content": s_tok})
                        }
                except Exception as cont_exc:
                    echo_continuation_failed = True
                    pipeline.suppress_fallback_question()
                    logger.warning(f"[ChatService] Echo corrective continuation skipped/failed: {cont_exc}")

            # Chèn câu hỏi Socratic (nếu còn thiếu) và xả footer '📍' hợp lệ duy nhất (nếu có <timestamp>)
            for s_tok in pipeline.flush_held_footer():
                full_assistant_response += s_tok
                yield {
                    "event": "delta",
                    "data": json.dumps({"content": s_tok})
                }

            # Deterministic Timestamp Fallback: Nếu có mốc bảo chứng nhưng LLM quên sinh thẻ, tự động gắn mốc video
            if valid_secs and "<timestamp" not in full_assistant_response and suggested_ts:
                ts_items = [
                    f'<timestamp sec="{ts.sec}" lesson="{ts.lesson_seq}">{ts.label}</timestamp>'
                    if ts.lesson_seq is not None
                    else f'<timestamp sec="{ts.sec}">{ts.label}</timestamp>'
                    for ts in suggested_ts[:2]
                ]
                ts_joined = " | ".join(ts_items)
                stripped_resp = full_assistant_response.rstrip(" |\t")
                if stripped_resp.endswith(("Mốc video bài giảng:**", "Mốc video bài giảng:")):
                    ts_footer = f" {ts_joined}"
                else:
                    ts_footer = f"\n\n📍 **Mốc video bài giảng:** {ts_joined}"
                full_assistant_response += ts_footer
                yield {
                    "event": "delta",
                    "data": json.dumps({"content": ts_footer})
                }

            # Lưu vết câu trả lời hoàn chỉnh của Trợ giảng vào LangGraph Checkpointer
            # (Không ghi vào Checkpointer nếu phản hồi chỉ là echo-only thất bại continuation để tránh làm bẩn lịch sử)
            if full_assistant_response.strip() and not echo_continuation_failed:
                # Hàng rào bảo vệ lần 2: Đảm bảo 100% không lọt bất kỳ thẻ timestamp ảo giác nào vào DB
                full_assistant_response = sanitize_timestamp_tags(full_assistant_response, valid_secs)
                history_assistant_response = full_assistant_response
                if pipeline.inserted_fallback_question and fallback_socratic_q:
                    history_assistant_response = history_assistant_response.replace(fallback_socratic_q, "").strip()
                commit_assistant_turn(
                    session_id,
                    clean_prompt,
                    history_assistant_response,
                    current_lesson_seq=request.lesson_seq,
                    last_course_query=final_state.get("last_course_query")
                )

        except Exception as e:
            logger.error(f"[ChatService] Lỗi kết nối LLM Server ({settings.LLM_BASE_URL}): {str(e)}")
            fallback_msg = (
                f"\n\n*(Hệ thống đang tạm thời gián đoạn kết nối tới máy chủ mô hình `{settings.LLM_MODEL_NAME}`. "
                f"Bạn vui lòng thử gửi lại câu hỏi sau ít giây nhé!)*"
            )
            # Tuyệt đối KHÔNG gọi commit_assistant_turn với thông báo lỗi mạng để tránh làm bẩn lịch sử hội thoại
            yield {
                "event": "delta",
                "data": json.dumps({
                    "content": fallback_msg
                })
            }

        yield {
            "event": "done",
            "data": "[DONE]"
        }


# Singleton ChatService instance
_chat_service: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service
