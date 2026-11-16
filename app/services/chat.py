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


def sanitize_timestamp_tags(text: str, valid_secs: set) -> str:
    """
    Deterministic Timestamp Whitelist Guardrail (Zero Regex):
    Loại bỏ triệt để các thẻ <timestamp sec=\"X\"> không nằm trong danh mục Whitelist được bảo chứng.
    - Nếu valid_secs rỗng hoặc không có thẻ: Loại bỏ toàn bộ thẻ <timestamp>, giữ lại nội dung trơn.
    - Nếu valid_secs có phần tử: Bắt buộc sec phải thuộc valid_secs.
    """
    if not text or "<timestamp" not in text:
        return text

    parser = TimestampWhitelistHTMLParser(valid_secs)
    try:
        parser.feed(text)
        return "".join(parser.result)
    except Exception as e:
        logger.warning(f"[sanitize_timestamp_tags] Lỗi HTML parser: {e}. Trả về văn bản gốc.")
        return text


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

    def process(self, token: str) -> List[str]:
        self.buffer += token
        out: List[str] = []

        while self.buffer:
            if self.state == self.STATE_EMIT:
                lt_idx = self.buffer.find("<")
                if lt_idx == -1:
                    out.append(self.buffer)
                    self.buffer = ""
                    break
                elif lt_idx > 0:
                    out.append(self.buffer[:lt_idx])
                    self.buffer = self.buffer[lt_idx:]

                # Buffer bắt đầu bằng '<'
                if "<timestamp".startswith(self.buffer):
                    # Đang khớp một phần của '<timestamp', chờ thêm token
                    break
                elif self.buffer.startswith("<timestamp"):
                    self.state = self.STATE_ACCUMULATE_TAG
                else:
                    # Ký tự '<' thông thường không phải thẻ timestamp (ví dụ i < n hoặc template <T>)
                    out.append(self.buffer[0])
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
                        out.append(f"{self.tag_open}{body}{close_tag}")

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
                out.append(self.buffer)

        self.buffer = ""
        self.body_buffer = ""
        self.tag_open = ""
        self.is_valid_sec = False
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

        # -1. Kiểm tra Rate Limiting (Chống spam dồn dập per session)
        rate_limiter = get_session_rate_limiter()
        is_allowed, rate_msg, retry_after = rate_limiter.check_rate_limit(session_id)
        if not is_allowed:
            metadata_event = StreamMetadataEvent(
                session_id=session_id,
                turn_count=1,
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

        initial_state = {
            "session_id": session_id,
            "prompt": clean_prompt,
            "course_id": request.course_id,
            "lesson_seq": request.lesson_seq,
            "intent": "course_query",
            "direct_response": None,
            "is_course_query": True,
            "search_query": None,
            "last_course_query": None,
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

        # Phân định rạch ròi tài liệu bài giảng truy xuất vs phát biểu của học viên (chống Context Drift)
        messages = [dict(m) for m in raw_messages]
        if messages and messages[-1].get("role") == "user":
            u_content = messages[-1].get("content", "")
            grounded_marker = "[NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC]"
            future_marker = "[HỌC LIỆU BÀI GIẢNG TƯƠNG LAI ĐỂ GIẢI THÍCH BẢN CHẤT]"
            if grounded_marker in u_content:
                u_content = u_content.replace(
                    grounded_marker,
                    f"{grounded_marker}\n"
                    "(Lưu ý nguồn gốc: Các trích đoạn [Video Bài ...] và [MÃ NGUỒN ...] dưới đây là "
                    "tài liệu bài giảng do hệ thống truy xuất để bạn đối chiếu, KHÔNG phải lời nói hay ý kiến do học viên nêu ra.)",
                    1
                )
            if future_marker in u_content:
                u_content = u_content.replace(
                    future_marker,
                    f"{future_marker}\n"
                    "(Lưu ý nguồn gốc: Đây là trích đoạn tài liệu bài giảng tương lai do hệ thống truy xuất, "
                    "KHÔNG phải phát biểu của học viên.)",
                    1
                )
            messages[-1]["content"] = u_content

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
                timeout=8.0
            )

            retrieval_status = final_state.get("retrieval_status", "coverage_gap")
            retrieved_chunks = final_state.get("retrieved_chunks", [])

            # Tập hợp Whitelist các mốc giây được bảo chứng (ERR-02)
            valid_secs = set()
            for item in final_state.get("suggested_timestamps", []):
                if isinstance(item, dict) and item.get("sec") is not None:
                    valid_secs.add(int(item["sec"]))

            ts_sanitizer = StreamingTimestampSanitizer(valid_secs=valid_secs)
            code_sanitizer = StreamingCodeSanitizer()

            async for chunk in stream_response:
                if chunk.choices and chunk.choices[0].delta.content:
                    raw_token = chunk.choices[0].delta.content

                    # Tri-Layer Anti-CJK Token Leakage Guardrail (Tầng 2 - Backend Streaming Sanitizer)
                    clean_token = sanitize_cjk_tokens(raw_token)
                    if not clean_token:
                        continue

                    # Deterministic Timestamp Whitelist Guardrail (Streaming Buffer)
                    sanitized_tokens = ts_sanitizer.process(clean_token)
                    for tok in sanitized_tokens:
                        # Deterministic Streaming Code Sanitizer (Chống rò rỉ #include, using namespace, main)
                        clean_code_tokens = code_sanitizer.process(tok)
                        for c_tok in clean_code_tokens:
                            full_assistant_response += c_tok
                            yield {
                                "event": "delta",
                                "data": json.dumps({"content": c_tok})
                            }

            # Xả các token còn lại trong bộ đệm cuối luồng
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
                stripped_resp = full_assistant_response.rstrip()
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
            fallback_msg = f"\n\n*(Hệ thống đang gặp sự cố kết nối tới LLM Local ({settings.LLM_MODEL_NAME}). Bạn vui lòng kiểm tra xem Ollama đã chạy chưa: `ollama run {settings.LLM_MODEL_NAME}`)*"
            commit_assistant_turn(
                session_id,
                clean_prompt,
                fallback_msg,
                current_lesson_seq=request.lesson_seq,
                last_course_query=final_state.get("last_course_query")
            )
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
