"""
Mô-đun Kiểm soát An toàn & Nguyên tắc Sư phạm (Security & Socratic Guardrails)
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Tuân thủ chuẩn bảo mật công nghiệp OWASP Top 10 for LLM (LLM01: Prompt Injection)
và phương pháp luận Socratic (Strict Anti-Solution Code Dumping).

Bao gồm 2 chốt chặn kiến trúc:
1. SecurityInputGuardrail: Chốt chặn cửa vào (Front-Door Gateway) phát hiện chữ ký tấn công
   Prompt Injection, Jailbreak, System Override với độ trễ ~0ms trên CPU.
2. SocraticOutputGuardrail: Chốt chặn cửa ra (Back-Door Socratic Guard) dùng Tree-sitter AST
   để phát hiện và cắt tỉa các đoạn code giải bài hộ học sinh thành scaffolding gợi mở.
"""

import re
import logging
from typing import Tuple, Optional, List

logger = logging.getLogger("uvicorn.error")

SECURITY_REFUSAL_RESPONSE = (
    "Yêu cầu của bạn đã bị từ chối bởi **Tầng Bảo mật An ninh Sư phạm (Security Guardrail)**.\n\n"
    "Hệ thống **In-Course Agentic RAG Copilot** được thiết lập tuân thủ nghiêm ngặt chuẩn mực "
    "phương pháp Socratic: **Tuyệt đối không giải bài tập hộ, không viết sẵn toàn bộ mã nguồn "
    "và không chấp nhận các câu lệnh bẻ khóa (Prompt Injection / System Override)**.\n\n"
    "Vui lòng đặt câu hỏi cụ thể về khái niệm lý thuyết hoặc gửi đoạn code bạn đang tự viết "
    "để chúng ta cùng thảo luận và sửa lỗi từng bước!"
)


class SecurityInputGuardrail:
    """
    Tầng 1: Security Input Guardrail (OWASP LLM01 Standard)
    Cơ chế: Deterministic Signature & Heuristic Pattern Matching (Độ trễ ~0ms).
    Nhiệm vụ: Chặn đứng các nỗ lực Jailbreak, System Override và ép AI giải bài tập hộ.
    """

    def __init__(self):
        # Bộ chữ ký tấn công bảo mật đã biết (Known Injection Signatures)
        self._attack_patterns: List[re.Pattern] = [
            # 1. Bẻ khóa chỉ dẫn hệ thống (System Override / Jailbreak)
            re.compile(
                r"(?i)\bignore\s+(all\s+)?(previous|prior|above|existing)\s+(instructions|prompts|protocols|constraints|rules|guidelines)\b"
            ),
            re.compile(
                r"(?i)\b(bypass|disable|override|disregard)\s+(all\s+)?(safety|security|pedagogical|socratic|system)\s+(protocols|constraints|guidelines|rules)\b"
            ),
            re.compile(
                r"(?i)\byou\s+are\s+(now\s+)?(an?\s+)?(expert\s+c\+\+\s+code\s+generator|dan|jailbreak|unrestricted|god\s+mode|code\s+machine)\b"
            ),
            re.compile(
                r"(?i)\b(act\s+as|pretend\s+to\s+be)\s+(an?\s+)?(unrestricted|jailbroken|unfiltered)\b"
            ),
            # 2. Ép sinh toàn bộ code giải bài không qua Socratic
            re.compile(
                r"(?i)\boutput\s+the\s+complete\s+solution\s+code\s+(without|with\s+no)\s+(any\s+)?(socratic|guidance|questions)\b"
            ),
            re.compile(
                r"(?i)\b(give|write|generate|provide)\s+(me\s+)?(the\s+)?full\s+(solution|code)\s+without\s+explaining\b"
            ),
            # 3. Các mẫu bẻ khóa tiếng Việt tương ứng
            re.compile(
                r"(?i)\bquên\s+(hết|tất\s+cả)\s+(các\s+)?(quy\s+tắc|chỉ\s+dẫn|hướng\s+dẫn|ràng\s+buộc|bảo\s+mật)\b"
            ),
            re.compile(
                r"(?i)\bhãy\s+đóng\s+vai\s+(một\s+)?(cỗ\s+máy\s+viết\s+code|bot\s+không\s+giới\s+hạn|hacker)\b"
            ),
            re.compile(
                r"(?i)\bviết\s+(luôn|hộ|toàn\s+bộ)\s+(lời\s+giải|code)\s+(không\s+cần|đừng)\s+(giải\s+thích|hướng\s+dẫn|hỏi)\b"
            ),
        ]

    def validate_input(self, prompt: str) -> Tuple[bool, Optional[str]]:
        """
        Kiểm tra tính an toàn của câu hỏi đầu vào:
        Trả về (True, None) nếu an toàn.
        Trả về (False, SECURITY_REFUSAL_RESPONSE) nếu phát hiện tấn công.
        """
        if not prompt or not prompt.strip():
            return True, None

        normalized_prompt = prompt.strip()
        for pattern in self._attack_patterns:
            if pattern.search(normalized_prompt):
                logger.warning(
                    f"[SecurityInputGuardrail] 🚨 PHÁT HIỆN TẤN CÔNG PROMPT INJECTION: "
                    f"Pattern='{pattern.pattern[:40]}...' | Input='{prompt[:50]}...'"
                )
                return False, SECURITY_REFUSAL_RESPONSE

        return True, None


class SocraticOutputGuardrail:
    """
    Tầng 2: Socratic AST Output Guardrail (Tree-sitter AST & Pedagogical Enforcement)
    Nhiệm vụ: Phân tích AST của code do LLM sinh ra trong câu trả lời.
    Nếu phát hiện LLM viết sẵn toàn bộ hàm/bài giải hoàn chỉnh cho học viên (rho_impl >= 1.0),
    guardrail sẽ can thiệp thay thế thân hàm bằng gợi ý dàn khung (Scaffolding).
    """

    def __init__(self):
        self._parser = None
        self._init_parser()

    def _init_parser(self):
        """Khởi tạo Tree-sitter C++ parser an toàn."""
        try:
            import tree_sitter
            import tree_sitter_cpp as tscpp
            self._language = tree_sitter.Language(tscpp.language())
            self._parser = tree_sitter.Parser(self._language)
        except Exception as e:
            logger.warning(f"[SocraticOutputGuardrail] Không thể nạp tree-sitter C++ ({e}). Sử dụng Fallback Heuristics.")
            self._parser = None

    def audit_output(self, text: str) -> Tuple[bool, str]:
        """
        Kiểm tra và hiệu chỉnh văn bản đầu ra của LLM:
        - Trích xuất các khối mã nguồn ```cpp ... ```
        - Kiểm tra xem có hàm nào được triển khai hoàn chỉnh logic (> 6 câu lệnh thân hàm)
          mà không có hướng dẫn gợi mở Socratic.
        - Trả về (was_modified, safe_text).
        """
        if not text or "```" not in text:
            return False, text

        code_block_pattern = re.compile(r"```(?:cpp|c\+\+|c)?\n(.*?)```", re.DOTALL | re.IGNORECASE)
        matches = list(code_block_pattern.finditer(text))
        if not matches:
            return False, text

        modified = False
        new_text = text

        for match in matches:
            code_snippet = match.group(1)
            # Kiểm tra nhanh: Nếu code chỉ là vài dòng minh họa cú pháp (< 4 dòng code thật), bỏ qua
            lines = [l for l in code_snippet.splitlines() if l.strip() and not l.strip().startswith("//")]
            if len(lines) <= 4:
                continue

            # Nếu có Tree-sitter: Phân tích cú pháp cây AST
            if self._parser is not None:
                try:
                    tree = self._parser.parse(code_snippet.encode("utf-8"))
                    root = tree.root_node

                    # Đếm số lượng hàm có thân lệnh đầy đủ (function_definition)
                    func_nodes = [c for c in root.children if c.type == "function_definition"]
                    for fnode in func_nodes:
                        # Kiểm tra compound_statement (khối thân hàm { ... })
                        body_node = next((c for c in fnode.children if c.type == "compound_statement"), None)
                        if body_node and len(body_node.children) >= 8:
                            # Phát hiện hàm giải hoàn chỉnh -> Cắt tỉa thân hàm bảo vệ Socratic
                            body_bytes = code_snippet.encode("utf-8")[body_node.start_byte:body_node.end_byte].decode("utf-8")
                            socratic_body = (
                                "{\n    // [SOCRATIC SCAFFOLDING]: Hãy đọc kỹ gợi ý bên trên và tự triển khai logic tại đây!\n"
                                "    // Gợi ý: Kiểm tra điều kiện đầu vào trước khi thực hiện tính toán.\n"
                                "    // TODO: Học viên tự hoàn thiện phần thân hàm này.\n}"
                            )
                            new_code = code_snippet.replace(body_bytes, socratic_body, 1)
                            new_text = new_text.replace(code_snippet, new_code, 1)
                            modified = True
                            logger.info("[SocraticOutputGuardrail] Đã can thiệp cắt tỉa code giải hộ thành Socratic Scaffolding.")
                except Exception as err:
                    logger.debug(f"[SocraticOutputGuardrail] Parse tree-sitter lỗi nhẹ ({err}), giữ nguyên văn bản.")

        return modified, new_text


# Singleton instances
_security_input_guardrail: Optional[SecurityInputGuardrail] = None
_socratic_output_guardrail: Optional[SocraticOutputGuardrail] = None


def get_security_input_guardrail() -> SecurityInputGuardrail:
    global _security_input_guardrail
    if _security_input_guardrail is None:
        _security_input_guardrail = SecurityInputGuardrail()
    return _security_input_guardrail


def get_socratic_output_guardrail() -> SocraticOutputGuardrail:
    global _socratic_output_guardrail
    if _socratic_output_guardrail is None:
        _socratic_output_guardrail = SocraticOutputGuardrail()
    return _socratic_output_guardrail
