import json
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.agent.router import get_intent_router


@pytest.fixture(scope="module")
def client():
    """
    Khởi tạo TestClient với FastAPI Lifespan.
    """
    with TestClient(app) as test_client:
        yield test_client


def test_intent_router_greetings():
    """
    Kiểm thử Bộ định tuyến Tier 1 (Fast-Path Greeting):
    Xác nhận câu chào hỏi được phát hiện tức thì (< 1ms), không kích hoạt RAG.
    """
    router = get_intent_router()
    for greeting in ["Xin chào", "chào bạn", "hello bot", "Hi", "chúc buổi sáng vui vẻ"]:
        res = router.classify(greeting)
        assert res.intent == "chit_chat"
        assert res.is_course_query is False
        assert "In-Course AI Copilot" in res.direct_response


def test_intent_router_identity():
    """
    Kiểm thử Bộ định tuyến Tier 1 (Fast-Path Identity):
    Bảo toàn bất biến tác giả: Trần Thành Nghĩa, MSSV 23DH112252, HUFLIT.
    """
    router = get_intent_router()
    for q in ["Bạn là ai", "ai tạo ra bạn", "giới thiệu về bản thân"]:
        res = router.classify(q)
        assert res.intent == "chit_chat"
        assert res.is_course_query is False
        assert "Trần Thành Nghĩa" in res.direct_response
        assert "23DH112252" in res.direct_response
        assert "HUFLIT" in res.direct_response


def test_intent_router_out_of_scope():
    """
    Kiểm thử Bộ định tuyến Tier 2 (Out-of-Scope Guardrail):
    Chặn các câu hỏi không thuộc phạm vi môn học (nấu ăn, chiên cá, thời tiết...).
    """
    router = get_intent_router()
    for q in ["cách chiên cá giòn ngon", "làm sao để kho thịt", "dự báo thời tiết hôm nay"]:
        res = router.classify(q)
        assert res.intent == "out_of_scope"
        assert res.is_course_query is False
        assert "Trợ giảng Lập trình chuyên biệt" in res.direct_response


def test_intent_router_course_query():
    """
    Kiểm thử Bộ định tuyến Tier 3 (In-Course Query):
    Các câu hỏi lập trình C++ được định tuyến chuẩn xác vào pipeline RAG.
    """
    router = get_intent_router()
    for q in [
        "Cách khai báo hằng số const và ép kiểu trong C++",
        "Con trỏ là gì và tại sao bị lỗi segmentation fault",
        "Vòng lặp for khác gì vòng lặp while"
    ]:
        res = router.classify(q)
        assert res.intent == "course_query"
        assert res.is_course_query is True
        assert res.direct_response is None


def test_chat_stream_fast_path_sse(client):
    """
    Kiểm thử Endpoint POST /api/v1/chat/stream với luồng Fast-Path:
    Xác nhận trả về đúng định dạng text/event-stream và có đầy đủ sự kiện:
    event: metadata -> event: delta -> event: done.
    """
    payload = {
        "prompt": "Xin chào bạn",
        "course_id": "cpp-core",
        "lesson_seq": 2
    }
    response = client.post("/api/v1/chat/stream", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    content = response.text
    assert "event: metadata" in content
    assert "event: delta" in content
    assert "event: done" in content

    # Phân tích sự kiện metadata
    lines = content.split("\n")
    metadata_json = None
    for i, line in enumerate(lines):
        if line.startswith("event: metadata"):
            for next_line in lines[i+1:]:
                if next_line.startswith("data: "):
                    metadata_json = json.loads(next_line[6:])
                    break
            break

    assert metadata_json is not None
    assert metadata_json["intent"] == "chit_chat"
    assert metadata_json["used_fast_path"] is True
    assert metadata_json["retrieved_chunk_count"] == 0


def test_chat_stream_out_of_scope_sse(client):
    """
    Kiểm thử Endpoint POST /api/v1/chat/stream với câu hỏi ngoài lề (chiên cá):
    Xác nhận hệ thống trả về thông báo từ chối sư phạm lịch sự qua SSE mà không gọi RAG.
    """
    payload = {
        "prompt": "chỉ tôi cách chiên cá ngon",
        "course_id": "cpp-core",
        "lesson_seq": 2
    }
    response = client.post("/api/v1/chat/stream", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    content = response.text
    assert "event: metadata" in content
    assert "event: delta" in content
    assert "event: done" in content

    lines = content.split("\n")
    metadata_json = None
    for i, line in enumerate(lines):
        if line.startswith("event: metadata"):
            for next_line in lines[i+1:]:
                if next_line.startswith("data: "):
                    metadata_json = json.loads(next_line[6:])
                    break
            break

    assert metadata_json is not None
    assert metadata_json["intent"] == "out_of_scope"
    assert metadata_json["used_fast_path"] is True
