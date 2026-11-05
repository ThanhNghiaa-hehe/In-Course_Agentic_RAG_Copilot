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

import json
import time
import logging
from pathlib import Path
from typing import Tuple, Optional, List, Dict
import numpy as np
from markdown_it import MarkdownIt

logger = logging.getLogger("uvicorn.error")
_MD_PARSER = MarkdownIt()
SECURITY_MANIFEST_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "metadata" / "security_guardrail_manifest.json"

_CPP_PARSER = None
try:
    import tree_sitter
    import tree_sitter_cpp as tscpp
    _CPP_LANG = tree_sitter.Language(tscpp.language())
    _CPP_PARSER = tree_sitter.Parser(_CPP_LANG)
except Exception:
    _CPP_PARSER = None

SECURITY_REFUSAL_RESPONSE = (
    "Yêu cầu của bạn đã bị từ chối bởi **Tầng Bảo mật An ninh Sư phạm (Security Guardrail)**.\n\n"
    "Hệ thống **In-Course Agentic RAG Copilot** được thiết lập tuân thủ nghiêm ngặt chuẩn mực "
    "phương pháp Socratic: **Tuyệt đối không giải bài tập hộ, không viết sẵn toàn bộ mã nguồn "
    "và không chấp nhận các câu lệnh bẻ khóa (Prompt Injection / System Override)**.\n\n"
    "Vui lòng đặt câu hỏi cụ thể về khái niệm lý thuyết hoặc gửi đoạn code bạn đang tự viết "
    "để chúng ta cùng thảo luận và sửa lỗi từng bước!"
)


def _detect_student_cpp_ast(prompt: str) -> bool:
    """
    Phát hiện mã nguồn C++ của học viên bằng bộ phân tích cú pháp MarkdownIt AST & Tree-sitter C++ AST thực thụ.
    Tuyệt đối không dùng danh sách từ khóa hardcode hay biểu thức chính quy.
    """
    try:
        md_tokens = _MD_PARSER.parse(prompt)
        if any(t.type in ("fence", "code_block") and t.content.strip() for t in md_tokens):
            return True
    except Exception:
        pass

    if _CPP_PARSER is not None and any(ch in prompt for ch in ("{", "}", ";", "#")):
        try:
            tree = _CPP_PARSER.parse(prompt.encode("utf-8"))
            target_ast_nodes = {
                "function_definition",
                "preproc_include",
                "for_statement",
                "while_statement",
                "if_statement",
            }
            stack = [tree.root_node]
            while stack:
                node = stack.pop()
                if node.type in target_ast_nodes and not node.has_error:
                    return True
                for child in node.children:
                    stack.append(child)
        except Exception:
            pass
    return False


class SecurityInputGuardrail:
    """
    Tầng 1: Security Input Guardrail (OWASP LLM01 Standard)
    Cơ chế: Data-Driven Manifest + MarkdownIt/Tree-sitter AST Gate + Contrastive Semantic Vector Guardrail.
    Nhiệm vụ: Chặn đứng các nỗ lực Jailbreak, System Override và ép AI giải bài tập hộ (Zero Hardcoded Signatures).
    """

    def __init__(self, manifest_path: Path = SECURITY_MANIFEST_PATH):
        self.manifest_path = manifest_path
        self._embedding_service = None
        self._proto_matrix: Optional[np.ndarray] = None
        self._benign_matrix: Optional[np.ndarray] = None
        self._attack_prototypes: List[str] = []
        self._benign_prototypes: List[str] = []
        self._compiler_error_tokens: List[str] = []
        self._load_manifest()

    def _load_manifest(self) -> None:
        try:
            if self.manifest_path.exists():
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._attack_prototypes = data.get("attack_prototypes", [])
                self._benign_prototypes = data.get("benign_prototypes", [])
                self._compiler_error_tokens = [
                    str(tok).lower() for tok in data.get("compiler_error_tokens", [])
                ]
        except Exception as e:
            logger.warning(f"[SecurityInputGuardrail] Lỗi đọc manifest {self.manifest_path}: {e}")

    def _ensure_embeddings(self):
        if self._proto_matrix is None and self._attack_prototypes and self._benign_prototypes:
            try:
                from app.services.embedding import get_embedding_service
                self._embedding_service = get_embedding_service()

                proto_vecs = []
                for p in self._attack_prototypes:
                    v = self._embedding_service.embed_query_dense(p)
                    norm_v = np.array(v) / (np.linalg.norm(v) + 1e-9)
                    proto_vecs.append(norm_v)
                self._proto_matrix = np.array(proto_vecs)

                benign_vecs = []
                for p in self._benign_prototypes:
                    v = self._embedding_service.embed_query_dense(p)
                    norm_v = np.array(v) / (np.linalg.norm(v) + 1e-9)
                    benign_vecs.append(norm_v)
                self._benign_matrix = np.array(benign_vecs)
            except Exception as e:
                logger.warning(f"[SecurityInputGuardrail] Không thể nạp embedding guardrail ({e}).")

    def validate_input(self, prompt: str) -> Tuple[bool, Optional[str]]:
        """
        Kiểm tra tính an toàn của câu hỏi đầu vào:
        - Context-Aware Socratic Input Gate: Kiểm tra cây cú pháp MarkdownIt AST / Tree-sitter C++ AST
          hoặc mã lỗi trình biên dịch nạp từ manifest.
        - Contrastive Semantic Vector Guardrail: Phân tách dựa trên biên độ tương phản (Margin >= 0.02, AttackSim >= 0.85)
          giữa vector tấn công và vector câu hỏi học tập trên không gian E5 1024 chiều.
        - Trả về (True, None) nếu an toàn.
        - Trả về (False, SECURITY_REFUSAL_RESPONSE) nếu phát hiện tấn công cố ý.
        """
        if not prompt or not prompt.strip():
            return True, None

        normalized_prompt = prompt.strip()
        lower_prompt = normalized_prompt.lower()

        # 1. Context-Aware Socratic Input Gate (MarkdownIt AST & Tree-sitter C++ AST)
        has_compiler_error = any(tok in lower_prompt for tok in self._compiler_error_tokens)
        has_student_code = _detect_student_cpp_ast(normalized_prompt)

        if has_compiler_error or has_student_code:
            logger.info("[SecurityInputGuardrail] Context-Aware Socratic AST Gate: Kích hoạt chế độ Socratic Debugging.")
            return True, None

        # 2. Contrastive Semantic Vector Guardrail (100% Dense Vector E5 Cosine, Zero Hardcoded Signatures)
        self._ensure_embeddings()
        if self._proto_matrix is not None and self._benign_matrix is not None:
            try:
                vec = self._embedding_service.embed_query_dense(normalized_prompt)
                norm_vec = np.array(vec) / (np.linalg.norm(vec) + 1e-9)
                sim_attack = float(np.max(np.dot(self._proto_matrix, norm_vec)))
                sim_benign = float(np.max(np.dot(self._benign_matrix, norm_vec)))
                margin = sim_attack - sim_benign

                if margin >= 0.02 and sim_attack >= 0.85:
                    logger.warning(
                        f"[SecurityInputGuardrail] 🚨 PHÁT HIỆN TẤN CÔNG (Semantic Margin={margin:+.4f}, "
                        f"AttackSim={sim_attack:.4f}): '{prompt[:50]}...'"
                    )
                    return False, SECURITY_REFUSAL_RESPONSE
            except Exception as e:
                logger.debug(f"[SecurityInputGuardrail] Semantic check lỗi nhẹ ({e}), bỏ qua.")

        return True, None


def compute_ast_cyclomatic_complexity(node) -> int:
    """
    Đo lường độ phức tạp chu trình AST Cyclomatic Complexity (McCabe 1976):
    M = E - N + 2P
    Đối với một hàm đơn (P = 1), M = 1 + số lượng điểm quyết định rẽ nhánh (Decision Points).
    Các điểm rẽ nhánh trong Tree-sitter C++ AST gồm:
    - Cấu trúc điều khiển: if_statement, for_statement, while_statement, do_statement, case_statement
    - Toán tử điều kiện: conditional_expression (? :)
    - Phép toán logic: binary_expression có toán tử '&&' hoặc '||'
    """
    decision_types = {
        "if_statement", "for_statement", "while_statement", "do_statement",
        "case_statement", "conditional_expression"
    }
    complexity = 1
    stack = [node]
    while stack:
        curr = stack.pop()
        if curr.type in decision_types:
            complexity += 1
        elif curr.type == "binary_expression":
            for child in curr.children:
                if child.type in ("&&", "||"):
                    complexity += 1
                    break
        for child in curr.children:
            stack.append(child)
    return complexity


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
        Kiểm tra và hiệu chỉnh văn bản đầu ra của LLM qua Markdown AST & Tree-sitter C++ AST (Zero Regex):
        - Trích xuất các khối mã nguồn fence blocks từ Markdown AST.
        - Phát hiện và triệt tiêu vi phạm P10 (sinh trọn vẹn chương trình có #include và int main()).
        - Cắt tỉa các hàm giải hoàn chỉnh (Cyclomatic Complexity M >= 3) thành khung gợi mở Socratic Scaffolding.
        - Trả về (was_modified, safe_text).
        """
        if not text or "```" not in text:
            return False, text

        md_tokens = _MD_PARSER.parse(text)
        fence_blocks = [t.content for t in md_tokens if t.type in ("fence", "code_block") and t.content.strip()]
        if not fence_blocks:
            return False, text

        modified = False
        new_text = text

        for code_snippet in fence_blocks:
            original_code = code_snippet
            current_code = code_snippet

            # 1. Xử lý qua Tree-sitter C++ AST (nếu có parser)
            if self._parser is not None:
                try:
                    tree = self._parser.parse(current_code.encode("utf-8"))
                    root = tree.root_node

                    has_include = any(c.type == "preproc_include" for c in root.children)
                    func_nodes = [c for c in root.children if c.type == "function_definition"]
                    has_main = False

                    for fnode in func_nodes:
                        is_main_func = False
                        for sub in fnode.children:
                            if sub.type == "function_declarator":
                                for subsub in sub.children:
                                    if subsub.type == "identifier" and subsub.text.decode("utf-8") == "main":
                                        is_main_func = True
                                        has_main = True

                        body_node = next((c for c in fnode.children if c.type == "compound_statement"), None)
                        if body_node:
                            cyclomatic_m = compute_ast_cyclomatic_complexity(body_node)
                            if (is_main_func and has_include) or (cyclomatic_m >= 3):
                                body_bytes = current_code.encode("utf-8")[body_node.start_byte:body_node.end_byte].decode("utf-8")
                                socratic_body = (
                                    "{\n    // [SOCRATIC SCAFFOLDING]: Không cung cấp toàn bộ code giải bài.\n"
                                    "    // Gợi ý: Hãy đọc kỹ giải thích tư duy và mã giả bên trên để tự hoàn thiện logic!\n"
                                    "    // TODO: Học viên tự viết mã thực thi vào đây.\n"
                                    "    return 0;\n}"
                                ) if is_main_func else (
                                    "{\n    // [SOCRATIC SCAFFOLDING]: Hãy đọc kỹ gợi ý bên trên và tự triển khai logic tại đây!\n"
                                    "    // Gợi ý: Kiểm tra điều kiện đầu vào trước khi thực hiện tính toán.\n"
                                    "    // TODO: Học viên tự hoàn thiện phần thân hàm này.\n}"
                                )
                                current_code = current_code.replace(body_bytes, socratic_body, 1)

                    # Khử thẻ #include nếu có hàm main đi kèm (ngăn chặn copy-run toàn bộ chương trình)
                    if has_main and has_include:
                        sanitized_lines = []
                        for line in current_code.splitlines():
                            stripped = line.strip()
                            if stripped.startswith("#") and "include" in stripped:
                                parts = stripped[1:].strip().split()
                                if parts and parts[0] == "include":
                                    sanitized_lines.append("// [Lưu ý]: Học viên tự khai báo thư viện cần thiết")
                                    continue
                            sanitized_lines.append(line)
                        current_code = "\n".join(sanitized_lines)

                except Exception as err:
                    logger.debug(f"[SocraticOutputGuardrail] Parse tree-sitter lỗi nhẹ ({err}), chuyển sang Heuristic.")

            # 2. Fallback Heuristics cấu trúc khi Tree-sitter không hoạt động
            else:
                has_main = any("main(" in l.replace(" ", "") for l in current_code.splitlines() if not l.strip().startswith("//"))
                has_include = any(l.strip().startswith("#") and "include" in l for l in current_code.splitlines())
                if has_main and has_include:
                    sanitized_lines = []
                    for line in current_code.splitlines():
                        stripped = line.strip()
                        if stripped.startswith("#") and "include" in stripped:
                            parts = stripped[1:].strip().split()
                            if parts and parts[0] == "include":
                                sanitized_lines.append("// [Lưu ý]: Học viên tự khai báo thư viện cần thiết")
                                continue
                        sanitized_lines.append(line)
                    current_code = "\n".join(sanitized_lines)

            if current_code != original_code:
                new_text = new_text.replace(original_code, current_code, 1)
                modified = True
                logger.info("[SocraticOutputGuardrail] Đã can thiệp cắt tỉa code giải hộ thành Socratic Scaffolding.")

        return modified, new_text


class SessionRateLimiter:
    """
    Tầng Kiểm soát Tần suất Phiên Học (Session Rate Limiter - In-Memory Sliding Window).
    Nhiệm vụ: Chặn đứng hành vi spam dồn dập hoặc DoS tài nguyên GPU.
    - Giới hạn: max_per_minute = 6 requests/phút (trung bình 10s/câu).
    - Giới hạn: max_per_hour = 60 requests/giờ.
    - Độ trễ kiểm tra: < 0.1ms trên RAM.
    """

    def __init__(self, max_per_minute: int = 6, max_per_hour: int = 60):
        self.max_per_minute = max_per_minute
        self.max_per_hour = max_per_hour
        # Dictionary mapping session_id -> list of float timestamps (epoch seconds)
        self._history: Dict[str, List[float]] = {}

    def check_rate_limit(self, session_id: str) -> Tuple[bool, Optional[str], Optional[int]]:
        """
        Kiểm tra tần suất cho session_id.
        Trả về (is_allowed, error_message, retry_after_seconds).
        """
        now = time.time()
        timestamps = self._history.get(session_id, [])

        # Dọn dẹp các mốc thời gian cũ hơn 1 giờ (3600s)
        cutoff_hour = now - 3600.0
        timestamps = [ts for ts in timestamps if ts > cutoff_hour]

        # Kiểm tra ngưỡng 1 phút (60s)
        cutoff_minute = now - 60.0
        recent_minute = [ts for ts in timestamps if ts > cutoff_minute]

        if len(recent_minute) >= self.max_per_minute:
            oldest_in_minute = recent_minute[0]
            retry_after = max(1, int(60.0 - (now - oldest_in_minute)))
            msg = (
                f"Bạn đang gửi câu hỏi khá nhanh ({len(recent_minute)} câu/phút). "
                f"Phương pháp Socratic khuyến khích bạn dành {retry_after}s để đọc kỹ gợi ý trước đó, "
                "mở IDE và tự gõ thử mã nguồn trước khi đặt câu hỏi tiếp theo nhé!"
            )
            self._history[session_id] = timestamps
            return False, msg, retry_after

        # Kiểm tra ngưỡng 1 giờ (3600s)
        if len(timestamps) >= self.max_per_hour:
            oldest_in_hour = timestamps[0]
            retry_after = max(1, int(3600.0 - (now - oldest_in_hour)))
            msg = (
                f"Bạn đã đặt {len(timestamps)} câu hỏi trong 1 giờ qua. "
                "Hãy dành thời gian thực hành các bài tập đã thảo luận để củng cố kiến thức trước khi tiếp tục nhé!"
            )
            self._history[session_id] = timestamps
            return False, msg, retry_after

        # Hợp lệ: Ghi nhận timestamp mới
        timestamps.append(now)
        self._history[session_id] = timestamps
        return True, None, None

    def reset_session(self, session_id: str) -> None:
        """Xóa lịch sử tần suất khi học viên bấm làm mới phiên."""
        self._history.pop(session_id, None)


# Singleton instances
_security_input_guardrail: Optional[SecurityInputGuardrail] = None
_socratic_output_guardrail: Optional[SocraticOutputGuardrail] = None
_session_rate_limiter: Optional[SessionRateLimiter] = None


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


def get_session_rate_limiter() -> SessionRateLimiter:
    global _session_rate_limiter
    if _session_rate_limiter is None:
        _session_rate_limiter = SessionRateLimiter()
    return _session_rate_limiter
