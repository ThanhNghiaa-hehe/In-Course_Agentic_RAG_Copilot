import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="module")
def client():
    """
    Khởi tạo TestClient với FastAPI Lifespan để nạp mô hình vào RAM.
    """
    with TestClient(app) as test_client:
        yield test_client


def test_health_check_endpoint(client):
    """
    Kiểm tra endpoint /health:
    Xác nhận dịch vụ FastAPI, mô hình Embedding và kết nối Qdrant đều ở trạng thái healthy.
    """
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["qdrant"]["collection_exists"] is True
    assert data["qdrant"]["target_collection"] == "In-Course_Agentic_RAG_Copilot"


def test_search_endpoint_valid_cpp_query(client):
    """
    Kiểm tra endpoint POST /api/v1/search với câu hỏi hợp lệ về C++ (Bài 2):
    Xác nhận trả về đúng 200 OK, có cả Code AST và Video Transcript có thẻ tua <timestamp>.
    """
    payload = {
        "query": "Cách khai báo hằng số const và ép kiểu trong C++",
        "course_id": "cpp-core",
        "lesson_seq": 2,
        "top_candidates": 10,
        "final_top_k": 3,
        "min_score_threshold": 0.35
    }
    response = client.post("/api/v1/search", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == payload["query"]
    assert data["total_retrieved"] > 0
    assert len(data["results"]) <= 3

    # Kiểm tra cấu trúc đa phương thức của các chunks trả về
    content_types = [item["content_type"] for item in data["results"]]
    assert "code_ast" in content_types or "video_transcript" in content_types

    for item in data["results"]:
        assert "rrf_score" in item
        assert "confidence_pct" in item
        if item["content_type"] == "video_transcript":
            assert "timestamp_tag" in item
            assert item["timestamp_tag"].startswith("<timestamp sec=")


@pytest.mark.xfail(
    reason="TODO(Day-4): Cần tích hợp bge-reranker-large (Cross-Encoder) ở Stage 8 để áp dụng chuẩn hóa Sigmoid lọc tuyệt đối câu hỏi lạc đề (RRF hiện tại chỉ xếp hạng tương đối).",
    strict=False
)
def test_search_endpoint_out_of_domain_guardrails(client):
    """
    Kiểm tra cơ chế phòng thủ Guardrails:
    Khi học viên hỏi câu hỏi ngoài phạm vi khóa học (hỏi về Java Spring Boot trong lớp C++),
    hệ thống phải loại bỏ nhiễu và trả về danh sách rỗng (total_retrieved == 0).
    """
    payload = {
        "query": "Cách cấu hình dependency injection trong Java Spring Boot và tạo Bean",
        "course_id": "cpp-core",
        "lesson_seq": 2,
        "top_candidates": 10,
        "final_top_k": 3,
        "min_score_threshold": 0.35
    }
    response = client.post("/api/v1/search", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["total_retrieved"] == 0
    assert len(data["results"]) == 0


def test_search_endpoint_pydantic_validation_error(client):
    """
    Kiểm tra Pydantic v2 Input Validation:
    Khi gửi câu hỏi quá ngắn (1 ký tự) hoặc lesson_seq không hợp lệ (< 1),
    FastAPI phải lập tức chặn và trả về mã lỗi 422 Unprocessable Entity.
    """
    invalid_payload = {
        "query": "a",  # min_length=2
        "course_id": "cpp-core",
        "lesson_seq": 0  # ge=1
    }
    response = client.post("/api/v1/search", json=invalid_payload)
    assert response.status_code == 422
