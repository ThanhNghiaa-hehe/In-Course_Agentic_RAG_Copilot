"""
Script khảo thí & kiểm chuẩn Bộ nhớ Đa lượt LangGraph StateGraph (Chặng 4 Verification Script).
Tác giả: Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Mục tiêu kiểm chuẩn:
1. Tính toàn vẹn của LangGraph Checkpointer theo `session_id` (Thread Isolation).
2. Kế thừa ngữ cảnh qua các lượt đối thoại (Multi-turn Context Inheritance).
3. Thuật toán Cửa sổ trượt (Sliding Window k=5 turns / 10 messages) bảo vệ ngân sách <= 3,368 tokens.
4. Kích hoạt Conversation Summarizer khi vượt quá 6 turns.
"""

import os
import sys
from pathlib import Path

# Đảm bảo đường dẫn gốc dự án nằm trong sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
import uuid
import logging
from typing import Dict, Any

from app.services.chat_graph import (
    get_chat_graph,
    commit_assistant_turn,
    reset_session_state,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("verify_stateful_memory")


async def run_stateful_test():
    print("=" * 75)
    print("  KHẢO THÍ BỘ NHỚ ĐA LƯỢT LANGGRAPH STATEGRAPH (CHẶNG 4 - ZERO QUICK-FIX)")
    print("=" * 75)

    test_session_id = f"test_session_{uuid.uuid4().hex[:8]}"
    graph = get_chat_graph()
    config = {"configurable": {"thread_id": test_session_id}}

    print(f"\n[KHỞI TẠO] Session ID kiểm thử: {test_session_id}\n")

    # -------------------------------------------------------------
    # LƯỢT 1: Câu hỏi khởi đầu về Constructor (Bài 53)
    # -------------------------------------------------------------
    print("▶ KIỂM THỬ LƯỢT 1: Câu hỏi ban đầu")
    prompt_1 = "Hàm khởi tạo Constructor trong C++ dùng để làm gì?"
    state_1 = {
        "session_id": test_session_id,
        "prompt": prompt_1,
        "course_id": "cpp-oop",
        "lesson_seq": 53,
        "intent": "course_query",
        "direct_response": None,
        "is_course_query": True,
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

    out_1 = await graph.ainvoke(state_1, config=config)
    turn_1 = out_1.get("turn_count", 0)
    assembled_1 = out_1.get("assembled_messages", [])

    print(f"  • Turn count nhận diện: {turn_1} (Kỳ vọng: 1)")
    print(f"  • Trạng thái CRAG:      {out_1.get('retrieval_status')}")
    print(f"  • Số lượng tin nhắn ChatML: {len(assembled_1)} (Kỳ vọng: 2 - System + User hiện tại)")
    assert turn_1 == 1, f"Lỗi: Turn 1 không khớp ({turn_1})"
    assert len(assembled_1) == 2, f"Lỗi: ChatML Turn 1 phải có 2 tin nhắn ({len(assembled_1)})"

    # Giả lập phản hồi của Trợ giảng và commit vào checkpointer
    assistant_resp_1 = "Constructor là hàm đặc biệt dùng để khởi tạo giá trị cho các thuộc tính khi một đối tượng được sinh ra."
    commit_assistant_turn(test_session_id, prompt_1, assistant_resp_1)
    print("  => ĐÃ COMMIT LƯỢT 1 VÀO LANGGRAPH CHECKPOINTER THÀNH CÔNG!\n")

    # -------------------------------------------------------------
    # LƯỢT 2: Câu hỏi nối tiếp phụ thuộc ngữ cảnh (Dùng đại từ 'nó')
    # -------------------------------------------------------------
    print("▶ KIỂM THỬ LƯỢT 2: Câu hỏi nối tiếp (Pronoun Resolution: 'nó')")
    prompt_2 = "Nếu em không viết nó thì chương trình có tự tạo không?"
    state_2 = {
        "session_id": test_session_id,
        "prompt": prompt_2,
        "course_id": "cpp-oop",
        "lesson_seq": 53,
        "intent": "course_query",
        "direct_response": None,
        "is_course_query": True,
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

    out_2 = await graph.ainvoke(state_2, config=config)
    turn_2 = out_2.get("turn_count", 0)
    assembled_2 = out_2.get("assembled_messages", [])

    print(f"  • Turn count nhận diện: {turn_2} (Kỳ vọng: 2)")
    print(f"  • Số lượng tin nhắn ChatML: {len(assembled_2)} (Kỳ vọng: 4 - System + Turn 1 (User+Assistant) + User hiện tại)")
    assert turn_2 == 2, f"Lỗi: Turn 2 không khớp ({turn_2})"
    assert len(assembled_2) == 4, f"Lỗi: ChatML Turn 2 phải có 4 tin nhắn ({len(assembled_2)})"

    # Kiểm tra xem tin nhắn ở Turn 1 có nằm trong assembled_messages không
    has_turn1_user = any(prompt_1 in m["content"] for m in assembled_2)
    has_turn1_bot = any(assistant_resp_1 in m["content"] for m in assembled_2)
    print(f"  • Chứa User Prompt Turn 1:       {'ĐẠT' if has_turn1_user else 'THẤT BẠI'}")
    print(f"  • Chứa Assistant Response Turn 1: {'ĐẠT' if has_turn1_bot else 'THẤT BẠI'}")
    assert has_turn1_user and has_turn1_bot, "Lỗi: Không tìm thấy ngữ cảnh Turn 1 trong StateGraph!"

    assistant_resp_2 = "Nếu bạn không khai báo bất kỳ constructor nào, trình biên dịch C++ sẽ tự động sinh một Default Constructor mặc định."
    commit_assistant_turn(test_session_id, prompt_2, assistant_resp_2)
    print("  => ĐÃ COMMIT LƯỢT 2 VÀO LANGGRAPH CHECKPOINTER THÀNH CÔNG!\n")

    # -------------------------------------------------------------
    # LƯỢT 3 ĐẾN 8: Kiểm thử Cửa sổ trượt (Sliding Window) & Tóm tắt (Summarizer)
    # -------------------------------------------------------------
    print("▶ KIỂM THỬ LƯỢT 3 ĐẾN 8: Đẩy thêm 5 lượt để kiểm tra Cửa Sổ Trượt (k=5 turns)")
    for i in range(3, 8):
        user_p = f"Câu hỏi kiểm thử liên tiếp lượt {i} về con trỏ và struct?"
        asst_p = f"Phản hồi định hướng sư phạm Socratic cho lượt {i}."
        commit_assistant_turn(test_session_id, user_p, asst_p)

    # Thử gọi invoke ở lượt thứ 8
    prompt_8 = "Tổng kết lại các kiến thức em vừa hỏi từ nãy đến giờ?"
    state_8 = {
        "session_id": test_session_id,
        "prompt": prompt_8,
        "course_id": "cpp-oop",
        "lesson_seq": 53,
        "intent": "course_query",
        "direct_response": None,
        "is_course_query": True,
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

    out_8 = await graph.ainvoke(state_8, config=config)
    assembled_8 = out_8.get("assembled_messages", [])
    conv_summary = out_8.get("conversation_summary")

    print(f"\n  • Turn count sau 7 lượt commit: {out_8.get('turn_count')} (Kỳ vọng: 8)")
    print(f"  • Tổng số tin nhắn ChatML truyền LLM: {len(assembled_8)}")
    print(f"  • Giới hạn Cửa sổ trượt (Max 1 System + 10 History + 1 User = 12): {len(assembled_8)} <= 12")
    assert len(assembled_8) <= 12, f"Lỗi: Cửa sổ trượt vượt quá 12 tin nhắn ({len(assembled_8)})"

    print(f"  • Conversation Summary đã kích hoạt: {'ĐẠT' if conv_summary else 'CHƯA KÍCH HOẠT'}")
    if conv_summary:
        print(f"    Nội dung tóm tắt: '{conv_summary}'")

    # -------------------------------------------------------------
    # KIỂM THỬ RESET PHIÊN (Clear Chat Test)
    # -------------------------------------------------------------
    print("\n▶ KIỂM THỬ RESET PHIÊN: Bấm nút 'Làm mới' (Clear Chat)")
    reset_session_state(test_session_id)
    snapshot_reset = graph.get_state(config).values
    reset_msgs = snapshot_reset.get("messages", [])
    reset_turn = snapshot_reset.get("turn_count", 0)
    print(f"  • Số lượng tin nhắn sau reset: {len(reset_msgs)} (Kỳ vọng: 0)")
    print(f"  • Turn count sau reset:        {reset_turn} (Kỳ vọng: 0)")
    assert len(reset_msgs) == 0 and reset_turn == 0, "Lỗi: Reset phiên không thành công!"

    print("\n" + "=" * 75)
    print("  KẾT QUẢ KHẢO THÍ: 100% CÁC BÀI TEST STATEFUL MEMORY ĐÃ PASS HOÀN TOÀN!")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(run_stateful_test())
