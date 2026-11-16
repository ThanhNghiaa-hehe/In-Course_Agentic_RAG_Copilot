"""
Bộ kiểm thử đơn vị (Unit Tests) cho tầng Chuẩn hóa Đầu vào Người dùng (Entry Pipeline Input Normalization).
Tác giả: Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Phạm vi kiểm chuẩn:
1. Chuẩn hóa tiếng Việt tổ hợp (Unicode NFD -> dựng sẵn chuẩn NFC), kể cả khi bị chèn ký tự zero-width.
2. Loại bỏ ký tự ẩn Zero-Width (\\u200b, \\u200c, \\u200d, \\ufeff, \\u2060, \\u00ad) và ký tự điều khiển ASCII/Unicode (Cc, Cf).
3. Rút gọn khoảng trắng thừa (nhiều dấu cách, tab đơn dòng, \\u00a0, \\u3000, dòng trống liên tiếp).
4. Bảo toàn 100% cấu trúc đa dòng, dấu xuống dòng ('\\n') và thụt lề (indentation) của khối mã nguồn C++ (fenced & unfenced).
5. Tái sử dụng nhất quán hàm dùng chung `normalize_user_input` trên toàn bộ pipeline (guardrails, curriculum, chat_graph, chat, api) với 0% Regex.
"""

import ast
import unicodedata
from pathlib import Path
import pytest

from app.agent.guardrails import (
    normalize_user_input,
    _detect_student_cpp_ast,
    SecurityInputGuardrail,
)
from app.services.curriculum import _normalize_text, CurriculumService
from app.services.chat_graph import commit_assistant_turn, reset_session_state, get_chat_graph


def test_vietnamese_nfd_to_nfc_normalization():
    """Kiểm tra chuẩn hóa tiếng Việt từ tổ hợp NFD sang dựng sẵn NFC."""
    original_nfc = "Thầy ơi cho em hỏi kiểu dữ liệu con trỏ và mảng một chiều trong C++ hoạt động thế nào ạ?"
    decomposed_nfd = unicodedata.normalize("NFD", original_nfc)

    assert decomposed_nfd != original_nfc
    assert not unicodedata.is_normalized("NFC", decomposed_nfd)

    result = normalize_user_input(decomposed_nfd)
    assert result == original_nfc
    assert unicodedata.is_normalized("NFC", result)


def test_vietnamese_nfd_with_interleaved_zero_width_chars():
    """
    Kiểm tra trường hợp ký tự zero-width (\\u200b, \\ufeff) bị chèn giữa nguyên âm gốc và dấu thanh tổ hợp NFD.
    """
    # 'kiểu dữ liệu' ở dạng NFD có chèn \u200b và \ufeff trước dấu thanh
    interleaved = "kiê\u200b\u0309u dư\ufeff\u0303 liê\u200c\u0323u"
    result = normalize_user_input(interleaved)
    assert result == "kiểu dữ liệu"
    assert unicodedata.is_normalized("NFC", result)


def test_zero_width_and_control_character_stripping():
    """Kiểm tra loại bỏ triệt để các ký tự zero-width (Cf) và ký tự điều khiển ASCII/Unicode (Cc)."""
    dirty_input = (
        "\ufeffCho\u200b em\u200c hỏi\u200d về\u2060 vòng\u00ad lặp\x00\x01\x02\x07\x08\x0b\x0c\x1b\x7f\x80\x9f "
        "for trong C++"
    )
    result = normalize_user_input(dirty_input)
    assert result == "Cho em hỏi về vòng lặp for trong C++"
    for ch in result:
        assert unicodedata.category(ch) not in ("Cc", "Cf", "Cs", "Co", "Cn")


def test_whitespace_collapsing_and_special_unicode_spaces():
    """Kiểm tra rút gọn khoảng trắng thừa, tab trên câu đơn và khoảng trắng đặc biệt Unicode (Zs)."""
    messy_spaces = "   Cho\t\tem\u00a0\u00a0hỏi\u2003\u2003về\u3000con   trỏ   trong   C++   "
    result = normalize_user_input(messy_spaces)
    assert result == "Cho em hỏi về con trỏ trong C++"

    # Kiểm tra tham số lowercase và preserve_newlines=False (dùng trong CurriculumService._normalize_text)
    flat_lower = normalize_user_input("  Bài\n\n  Số\t 12:   Mảng 2 Chiều  ", lowercase=True, preserve_newlines=False)
    assert flat_lower == "bài số 12: mảng 2 chiều"
    assert _normalize_text("  Ba\u0300i\u200b   Sô\u0301   12  ") == "bài số 12"


def test_cpp_multiline_fenced_code_preservation():
    """
    Kiểm tra bảo toàn định dạng đa dòng, dấu xuống dòng ('\\n') và thụt lề (indentation)
    trong khối mã nguồn C++ có hàng rào Markdown (```cpp ... ```), đồng thời làm sạch NFC & ký tự ẩn.
    """
    raw_prompt = (
        "  Thâ\u0300y\u200b ơi   cho em   ho\u0309i đoạn code này bị lỗi gì ạ:\r\n\r\n\r\n"
        "```cpp\r\n"
        "#include <iostream>\r\n"
        "using namespace std;\r\n"
        "\r\n"
        "int main() {\r\n"
        "    int a\u200b = 10;\x00\r\n"
        "    int b = 20;\r\n"
        "    if (a < b) {\r\n"
        "        cout << a + b << endl;\r\n"
        "    }\r\n"
        "    return 0;\r\n"
        "}\r\n"
        "```\r\n\r\n\r\n"
        "Ta\u0323i   sao   nó   không   chạy   được   ạ?  "
    )

    normalized = normalize_user_input(raw_prompt)

    expected = (
        "Thầy ơi cho em hỏi đoạn code này bị lỗi gì ạ:\n\n"
        "```cpp\n"
        "#include <iostream>\n"
        "using namespace std;\n"
        "\n"
        "int main() {\n"
        "    int a = 10;\n"
        "    int b = 20;\n"
        "    if (a < b) {\n"
        "        cout << a + b << endl;\n"
        "    }\n"
        "    return 0;\n"
        "}\n"
        "```\n\n"
        "Tại sao nó không chạy được ạ?"
    )

    assert normalized == expected
    assert "\n    int a = 10;\n" in normalized
    assert "\n        cout << a + b << endl;\n" in normalized
    assert _detect_student_cpp_ast(normalized) is True


def test_cpp_multiline_unfenced_code_preservation():
    """Kiểm tra bảo toàn xuống dòng và thụt lề cho khối code C++ đa dòng không bọc trong ```."""
    unfenced_cpp = (
        "#include <iostream>\r\n"
        "int main() {\r\n"
        "    int   x\u200b = 5;\x07\r\n"
        "    for (int i = 0; i < x; i++) {\r\n"
        "        std::cout << i << std::endl;\r\n"
        "    }\r\n"
        "    return 0;\r\n"
        "}"
    )

    normalized = normalize_user_input(unfenced_cpp)
    expected = (
        "#include <iostream>\n"
        "int main() {\n"
        "    int x = 5;\n"
        "    for (int i = 0; i < x; i++) {\n"
        "        std::cout << i << std::endl;\n"
        "    }\n"
        "    return 0;\n"
        "}"
    )
    assert normalized == expected
    assert _detect_student_cpp_ast(normalized) is True


def test_pipeline_integration_curriculum_and_guardrail_and_graph():
    """
    Kiểm tra sự tích hợp đồng nhất của `normalize_user_input` tại CurriculumService,
    SecurityInputGuardrail và LangGraph Checkpointer.
    """
    # 1. CurriculumService: Mệnh lệnh chuyển bài có NFD + zero-width + khoảng trắng thừa
    dirty_nav_cmd = "  chuyê\u0309n\u200b   sang   ba\u0300i\ufeff   12   giu\u0301p   em\x00  "
    assert CurriculumService.extract_direct_navigation_command(dirty_nav_cmd) == 12

    # 2. SecurityInputGuardrail: Nhận diện đúng code C++ đa dòng có chứa ký tự ẩn để mở cổng Socratic Debugging
    guardrail = SecurityInputGuardrail()
    student_debug_prompt = (
        "Em viết code bị lỗi:\n"
        "```cpp\n"
        "#include <iostream>\n"
        "int main() {\n"
        "    int n\u200b = 5;\x00\n"
        "    return 0;\n"
        "}\n"
        "```"
    )
    is_safe, refusal = guardrail.validate_input(student_debug_prompt)
    assert is_safe is True
    assert refusal is None

    # 3. LangGraph Checkpointer: commit_assistant_turn lưu prompt đã chuẩn hóa NFC
    session_id = "test_norm_session_checkpointer"
    reset_session_state(session_id)
    nfd_user_q = unicodedata.normalize("NFD", "  Cho\u200b   em   hỏi   về   hàm   đệ   quy\x00  ")
    commit_assistant_turn(session_id, nfd_user_q, "Phản hồi Socratic", current_lesson_seq=1)

    graph = get_chat_graph()
    state = graph.get_state({"configurable": {"thread_id": session_id}})
    messages = state.values.get("messages", [])
    assert len(messages) == 2
    assert messages[0]["content"] == "Cho em hỏi về hàm đệ quy"
    assert unicodedata.is_normalized("NFC", messages[0]["content"])
    reset_session_state(session_id)


def test_zero_regex_and_single_shared_normalization_source_in_app():
    """Kiểm toán tĩnh: Đảm bảo 0% `import re` trong toàn bộ `app/` và chỉ duy nhất `guardrails.py` gọi `unicodedata`."""
    app_dir = Path(__file__).resolve().parent.parent / "app"
    unicodedata_files = []

    for py_file in app_dir.rglob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "re", f"Phát hiện import re bị cấm tại {py_file}"
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "re", f"Phát hiện from re import bị cấm tại {py_file}"
        if "unicodedata" in source:
            unicodedata_files.append(py_file.name)

    assert "guardrails.py" in unicodedata_files
    assert "curriculum.py" not in unicodedata_files
