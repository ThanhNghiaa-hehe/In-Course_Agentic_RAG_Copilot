import asyncio
import json
import logging
import uuid
from html.parser import HTMLParser
from typing import AsyncGenerator, Dict, Any, List, Optional, Tuple
from openai import AsyncOpenAI

from app.config import settings
from app.services.curriculum import get_curriculum_service, CurriculumService
from app.services.chat_graph import get_chat_graph, commit_assistant_turn, reset_session_state
from app.agent.router import get_intent_router
from app.agent.guardrails import get_session_rate_limiter, normalize_user_input
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

            artifact_sanitizer = StreamingInternalArtifactSanitizer(
                forbid_video_opening=(retrieval_status == "out_of_lesson" or is_nav_turn)
            )
            ts_sanitizer = StreamingTimestampSanitizer(valid_secs=valid_secs)
            code_sanitizer = StreamingCodeSanitizer()

            async for chunk in stream_response:
                if chunk.choices and chunk.choices[0].delta.content:
                    raw_token = chunk.choices[0].delta.content

                    # Tri-Layer Anti-CJK Token Leakage Guardrail (Tầng 2 - Backend Streaming Sanitizer)
                    clean_token = sanitize_cjk_tokens(raw_token)
                    if not clean_token:
                        continue

                    for art_tok in artifact_sanitizer.process(clean_token):
                        if not art_tok:
                            continue
                        # Deterministic Timestamp Whitelist Guardrail (Streaming Buffer)
                        sanitized_tokens = ts_sanitizer.process(art_tok)
                        for tok in sanitized_tokens:
                            # Deterministic Streaming Code Sanitizer (Chống rò rỉ #include, using namespace, main)
                            clean_code_tokens = code_sanitizer.process(tok)
                            for c_tok in clean_code_tokens:
                                full_assistant_response += c_tok
                                yield {
                                    "event": "delta",
                                    "data": json.dumps({"content": c_tok})
                                }

            # Xả các token còn lại trong bộ đệm cuối luồng theo đúng thứ tự pipeline
            for art_tok in artifact_sanitizer.flush():
                for tok in ts_sanitizer.process(art_tok):
                    for c_tok in code_sanitizer.process(tok):
                        full_assistant_response += c_tok
                        yield {
                            "event": "delta",
                            "data": json.dumps({"content": c_tok})
                        }

            final_flushed = ts_sanitizer.flush()
            for tok in final_flushed:
                for c_tok in code_sanitizer.process(tok):
                    full_assistant_response += c_tok
                    yield {
                        "event": "delta",
                        "data": json.dumps({"content": c_tok})
                    }

            final_code_flushed = code_sanitizer.flush()
            for c_tok in final_code_flushed:
                full_assistant_response += c_tok
                yield {
                    "event": "delta",
                    "data": json.dumps({"content": c_tok})
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
            if full_assistant_response.strip():
                # Hàng rào bảo vệ lần 2: Đảm bảo 100% không lọt bất kỳ thẻ timestamp ảo giác nào vào DB
                full_assistant_response = sanitize_timestamp_tags(full_assistant_response, valid_secs)
                commit_assistant_turn(
                    session_id,
                    clean_prompt,
                    full_assistant_response,
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
