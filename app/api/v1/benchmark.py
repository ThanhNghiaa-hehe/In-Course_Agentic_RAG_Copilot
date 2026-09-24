import json
import logging
from pathlib import Path
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/benchmark", tags=["Stage 11 Benchmark & Golden Dataset"])

BENCHMARK_DIR = Path(__file__).resolve().parent.parent.parent.parent / "docs" / "benchmarks"
NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0"
}


def find_latest_benchmark_file() -> Path | None:
    """
    Tìm tệp benchmark mới nhất theo thứ tự ưu tiên:
    1. Quét các tệp `stage11_results_*.json` sắp xếp theo thời gian sửa đổi (mtime) mới nhất.
    2. Nếu không tìm thấy, fallback về tệp `latest_benchmark_results.json`.
    """
    if not BENCHMARK_DIR.exists():
        return None

    # Tìm các tệp kết quả theo timestamp
    archived_files = list(BENCHMARK_DIR.glob("stage11_results_*.json"))
    if archived_files:
        archived_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        latest_archived = archived_files[0]
        
        # Nếu có latest_benchmark_results.json, so sánh mtime
        latest_link = BENCHMARK_DIR / "latest_benchmark_results.json"
        if latest_link.exists() and latest_link.stat().st_mtime >= latest_archived.stat().st_mtime:
            return latest_link
        return latest_archived

    latest_link = BENCHMARK_DIR / "latest_benchmark_results.json"
    if latest_link.exists():
        return latest_link

    return None


@router.get(
    "/latest",
    summary="Lấy kết quả khảo thí Stage 11 Benchmark mới nhất",
    description="Tự động phát hiện và trả về tệp kết quả JSON mới nhất trong thư mục `docs/benchmarks/`, kèm header chống cache triệt để."
)
async def get_latest_benchmark():
    target_file = find_latest_benchmark_file()
    if not target_file or not target_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chưa có dữ liệu Benchmark Stage 11 nào được ghi nhận. Vui lòng chạy `scripts/run_rag_benchmark.py`."
        )

    return FileResponse(
        target_file,
        media_type="application/json",
        headers=NO_CACHE_HEADERS
    )


@router.get(
    "/history",
    summary="Danh sách lịch sử các đợt khảo thí Benchmark Stage 11",
    description="Trích xuất siêu dữ liệu (Metadata & KPI Summary) của toàn bộ các đợt chạy trong thư mục `docs/benchmarks/` để phục vụ đối sánh độ hồi quy (Regression Tracking)."
)
async def get_benchmark_history() -> List[Dict[str, Any]]:
    if not BENCHMARK_DIR.exists():
        return []

    files = list(BENCHMARK_DIR.glob("stage11_results_*.json"))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    history: List[Dict[str, Any]] = []
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
                meta = data.get("metadata", {})
                summary = data.get("summary", {})
                history.append({
                    "file_name": fp.name,
                    "mtime": fp.stat().st_mtime,
                    "start_time": meta.get("start_time"),
                    "end_time": meta.get("end_time"),
                    "total_elapsed_sec": meta.get("total_elapsed_sec"),
                    "total_cases": meta.get("total_cases", len(data.get("cases", []))),
                    "dataset_name": meta.get("dataset_name"),
                    "router_accuracy": summary.get("router_accuracy"),
                    "crag_precision": summary.get("crag_precision"),
                    "timestamp_safety": summary.get("timestamp_safety"),
                    "avg_latency_ms": summary.get("avg_latency_ms")
                })
        except Exception as e:
            logger.warning(f"[Benchmark History] Không thể đọc {fp.name}: {e}")
            continue

    return history
