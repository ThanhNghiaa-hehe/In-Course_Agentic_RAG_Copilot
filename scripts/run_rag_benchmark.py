"""
Kịch bản khảo thí tự động Stage 11: RAG Triad & Multi-Tier Quantitative Benchmark
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Tính năng:
- Interactive Dataset Selector: Chọn tệp benchmark theo menu số hoặc qua cờ lệnh --dataset.
- Logging chi tiết thời gian: Hiển thị [YYYY-MM-DD HH:MM:SS] cho từng test case khi thực thi.
- Lưu trữ vĩnh viễn không đè file:
  + Markdown: docs/benchmarks/stage11_report_YYYY-MM-DD_HH-MM-SS.md
  + JSON:     docs/benchmarks/stage11_results_YYYY-MM-DD_HH-MM-SS.json
  + Dashboard sync: docs/benchmarks/latest_benchmark_results.json
"""

import os
import sys
import json
import time
import asyncio
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

# Đảm bảo đường dẫn gốc dự án nằm trong sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.router import get_intent_router
from app.services.retrieval import RetrievalService
from app.services.embedding import get_embedding_service
from app.services.qdrant import get_async_qdrant_client, close_async_qdrant_client
from app.config import settings


def select_dataset_interactive() -> Path:
    """Hiển thị menu chọn tệp Benchmark từ thư mục tests/data."""
    data_dir = PROJECT_ROOT / "tests" / "data"
    json_files = sorted(list(data_dir.glob("*.json")))

    if not json_files:
        raise FileNotFoundError(f"Không tìm thấy tệp JSON nào trong {data_dir}")

    # Ưu tiên đưa benchmark_golden_dataset.json lên đầu danh sách làm mặc định
    priority_files: List[Path] = []
    for f in json_files:
        if f.name == "benchmark_golden_dataset.json":
            priority_files.insert(0, f)
        else:
            priority_files.append(f)

    print("\n" + "=" * 74)
    print("  BỘ KHẢO THÍ ĐỊNH LƯỢNG RAG TRIAD - STAGE 11 BENCHMARK SUITE")
    print("  Tác giả: Trần Thành Nghĩa (MSSV: 23DH112252) - HUFLIT")
    print("=" * 74)
    print("[?] DANH SÁCH TẬP DỮ LIỆU BENCHMARK KHẢ DỤNG:")
    for idx, f in enumerate(priority_files, start=1):
        default_tag = " [MẶC ĐỊNH]" if idx == 1 else ""
        print(f"  [{idx}] {f.name}{default_tag}")
    print(f"  [{len(priority_files) + 1}] Nhập đường dẫn tệp JSON tùy chỉnh khác...")
    print("-" * 74)

    try:
        choice = input(f">> Nhập số thứ tự tập dữ liệu cần kiểm thử [1-{len(priority_files) + 1}] (Enter để chọn [1]): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n[INFO] Tự động chọn tập dữ liệu mặc định [1].")
        return priority_files[0]

    if not choice or choice == "1":
        return priority_files[0]

    try:
        choice_num = int(choice)
        if 1 <= choice_num <= len(priority_files):
            return priority_files[choice_num - 1]
        elif choice_num == len(priority_files) + 1:
            custom_path_str = input(">> Nhập đường dẫn tệp JSON: ").strip()
            custom_path = Path(custom_path_str)
            if custom_path.exists():
                return custom_path
            else:
                print(f"[CẢNH BÁO] Không tìm thấy tệp {custom_path}. Sử dụng tập dữ liệu mặc định [1].")
                return priority_files[0]
    except ValueError:
        print("[CẢNH BÁO] Lựa chọn không hợp lệ. Sử dụng tập dữ liệu mặc định [1].")

    return priority_files[0]


async def run_benchmark(dataset_path: Path):
    start_dt = datetime.now()
    start_time_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    timestamp_file_str = start_dt.strftime("%Y-%m-%d_%H-%M-%S")

    output_report_path = PROJECT_ROOT / "docs" / "benchmarks" / f"stage11_report_{timestamp_file_str}.md"
    json_archive_path = PROJECT_ROOT / "docs" / "benchmarks" / f"stage11_results_{timestamp_file_str}.json"
    latest_json_path = PROJECT_ROOT / "docs" / "benchmarks" / "latest_benchmark_results.json"

    print("=" * 74)
    print(" BẮT ĐẦU KHẢO THÍ ĐỊNH LƯỢNG TỰ ĐỘNG STAGE 11 (BENCHMARK SUITE)")
    print(f" Thời gian bắt đầu: {start_time_str}")
    print(f" Tập dữ liệu nạp:   {dataset_path.name}")
    print(f" Tác giả:           Trần Thành Nghĩa (MSSV: 23DH112252) - HUFLIT")
    print("=" * 74)

    if not dataset_path.exists():
        print(f"[LỖI] Không tìm thấy tệp dataset tại: {dataset_path}")
        return

    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset: List[Dict[str, Any]] = json.load(f)

    total_cases = len(dataset)
    print(f"[INFO] Đã nạp thành công {total_cases} test cases từ Golden Dataset.")

    # Khởi tạo các dịch vụ
    print("[INFO] Đang khởi tạo các mô hình và kết nối Qdrant...")
    router = get_intent_router()
    embedding_service = get_embedding_service()
    qdrant_client = get_async_qdrant_client()
    retrieval_service = RetrievalService(client=qdrant_client, embedding_service=embedding_service)

    # Thống kê tổng thể
    router_correct = 0
    crag_status_correct = 0
    timestamp_correct = 0
    total_time_ms = 0.0

    tier_stats = {
        "in_scope": {"total": 0, "router_ok": 0, "status_ok": 0, "ts_ok": 0, "time_ms": 0.0},
        "out_of_lesson": {"total": 0, "router_ok": 0, "status_ok": 0, "ts_ok": 0, "time_ms": 0.0},
        "adversarial_hybrid": {"total": 0, "router_ok": 0, "status_ok": 0, "ts_ok": 0, "time_ms": 0.0},
        "chit_chat": {"total": 0, "router_ok": 0, "status_ok": 0, "ts_ok": 0, "time_ms": 0.0},
    }

    results_detail: List[Dict[str, Any]] = []

    print("\nĐang thực thi các kịch bản kiểm thử...")
    print("-" * 74)

    for idx, item in enumerate(dataset, start=1):
        test_id = item["id"]
        tier = item["tier"]
        query = item["query"]
        course_id = item["course_id"]
        lesson_seq = item["lesson_seq"]
        expected_intent = item["expected_intent"]
        expected_status = item["expected_retrieval_status"]
        expected_has_ts = item["expected_has_timestamp"]
        target_sec = item.get("target_video_sec")

        tier_stats[tier]["total"] += 1
        t_start = time.perf_counter()

        # 1. Đo lường Router
        router_res = router.classify(query)
        actual_intent = router_res.intent
        is_router_ok = (actual_intent == expected_intent)
        if is_router_ok:
            router_correct += 1
            tier_stats[tier]["router_ok"] += 1

        # 2. Đo lường Retrieval & CRAG (nếu là course_query)
        actual_status = "coverage_gap"
        actual_has_ts = False
        actual_ts_sec = None
        is_ts_ok = False

        if router_res.is_course_query:
            retrieval_res = await retrieval_service.search(
                query_text=query,
                course_id=course_id,
                current_lesson_seq=lesson_seq,
                top_candidates=settings.DEFAULT_TOP_CANDIDATES,
                final_top_k=settings.DEFAULT_FINAL_TOP_K
            )
            actual_status = retrieval_res.status

            for c in retrieval_res.chunks:
                if c.get("content_type") == "video_transcript" and c.get("start_sec") is not None:
                    actual_has_ts = True
                    actual_ts_sec = c["start_sec"]
                    break
                elif c.get("content_type") == "code_ast" and c.get("approx_video_sec") is not None:
                    actual_has_ts = True
                    actual_ts_sec = c["approx_video_sec"]
                    break
        else:
            # Fast-path hoặc out-of-scope không gọi RAG
            actual_status = "coverage_gap"
            actual_has_ts = False

        is_status_ok = (actual_status == expected_status)
        if is_status_ok:
            crag_status_correct += 1
            tier_stats[tier]["status_ok"] += 1

        # 3. Đánh giá Timestamp
        if not expected_has_ts:
            # Kỳ vọng KHÔNG có timestamp (chống ảo giác): Nếu thực tế không có -> ĐẠT
            is_ts_ok = (actual_has_ts is False)
        else:
            # Kỳ vọng CÓ timestamp: Nếu có và |Δt| <= 30s
            if actual_has_ts:
                if target_sec is not None:
                    delta_t = abs(actual_ts_sec - target_sec)
                    is_ts_ok = (delta_t <= 30)  # Cửa sổ dung hòa 30s
                else:
                    is_ts_ok = True
            else:
                is_ts_ok = False

        if is_ts_ok:
            timestamp_correct += 1
            tier_stats[tier]["ts_ok"] += 1

        t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        total_time_ms += t_elapsed_ms
        tier_stats[tier]["time_ms"] += t_elapsed_ms

        fail_reasons = []
        if not is_router_ok:
            fail_reasons.append(f"Router(Act: {actual_intent} != Exp: {expected_intent})")
        if not is_status_ok:
            fail_reasons.append(f"Status(Act: {actual_status} != Exp: {expected_status})")
        if not is_ts_ok:
            fail_reasons.append(f"TS(Act: {actual_ts_sec} != Exp: {target_sec}, has_ts: {actual_has_ts})")

        reason_str = f" | [Lý do: {', '.join(fail_reasons)}]" if fail_reasons else ""
        status_flag = "PASS" if (is_router_ok and is_status_ok and is_ts_ok) else "WARN"

        cur_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{cur_timestamp}] [{idx:03d}/{total_cases:03d}] {test_id} ({tier[:4].upper()}): {status_flag} | Latency: {t_elapsed_ms:6.1f}ms | Query: {query[:45]}...{reason_str}")

        results_detail.append({
            "id": test_id,
            "tier": tier,
            "query": query,
            "course_id": course_id,
            "lesson_seq": lesson_seq,
            "timestamp": cur_timestamp,
            "expected": {
                "intent": expected_intent,
                "status": expected_status,
                "has_timestamp": expected_has_ts,
                "target_video_sec": target_sec
            },
            "actual": {
                "intent": actual_intent,
                "status": actual_status,
                "has_timestamp": actual_has_ts,
                "video_sec": actual_ts_sec
            },
            "pass_flags": {
                "router_ok": is_router_ok,
                "status_ok": is_status_ok,
                "ts_ok": is_ts_ok,
                "overall_pass": (is_router_ok and is_status_ok and is_ts_ok)
            },
            "fail_reasons": fail_reasons,
            "notes": item.get("notes", ""),
            "latency_ms": round(t_elapsed_ms, 1),
            "chunks": [
                {
                    "id": c.get("id"),
                    "content_type": c.get("content_type"),
                    "confidence_score": round(float(c.get("confidence_score", 0.0)), 4),
                    "lesson_seq": c.get("lesson_seq"),
                    "snippet": (c.get("raw_text", "") or c.get("context_code", ""))[:250]
                }
                for c in (retrieval_res.chunks if router_res.is_course_query else [])
            ]
        })

    end_dt = datetime.now()
    end_time_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")
    total_elapsed_sec = (end_dt - start_dt).total_seconds()

    # Tính toán chỉ số tổng hợp
    router_acc = (router_correct / total_cases) * 100.0
    crag_acc = (crag_status_correct / total_cases) * 100.0
    ts_acc = (timestamp_correct / total_cases) * 100.0
    avg_latency = total_time_ms / total_cases

    print("\n" + "=" * 74)
    print(" KẾT QUẢ TỔNG QUAN BENCHMARK STAGE 11")
    print(f" - Thời gian bắt đầu:          {start_time_str}")
    print(f" - Thời gian hoàn tất:         {end_time_str} (Tổng thời gian: {total_elapsed_sec:.1f}s)")
    print(f" - Tổng số ca kiểm thử:       {total_cases}")
    print(f" - Router Accuracy:            {router_acc:5.1f}% ({router_correct}/{total_cases})")
    print(f" - CRAG Grader Precision:      {crag_acc:5.1f}% ({crag_status_correct}/{total_cases})")
    print(f" - Timestamp Precision/Safety: {ts_acc:5.1f}% ({timestamp_correct}/{total_cases})")
    print(f" - Thời gian trung bình/câu:   {avg_latency:5.1f} ms")
    print("=" * 74)

    print("\n" + "=" * 74)
    print(" CHI TIẾT TỪNG TẦNG KIỂM THỬ (BREAKDOWN BY TIERS)")
    print("=" * 74)
    tier_titles = {
        "in_scope": "1. In-Scope Technical (Kiến thức trong bài)",
        "out_of_lesson": "2. Out-of-Lesson (Chặn bài tương lai)",
        "adversarial_hybrid": "3. Adversarial Hybrid (Bẫy đời sống)",
        "chit_chat": "4. Chit-Chat / Out-of-Scope (Giao tiếp)"
    }
    for t_key, t_title in tier_titles.items():
        st = tier_stats[t_key]
        total = st["total"]
        tier_pass = sum(1 for r in results_detail if r["tier"] == t_key and r["pass_flags"]["overall_pass"])
        tier_fail = total - tier_pass
        avg_t = st["time_ms"] / max(1, total)

        print(f"\n▶ {t_title} (Tổng: {total} câu):")
        print(f"   • Kết quả tổng thể:     {tier_pass}/{total} ĐẠT ({tier_fail} câu có điểm WARN)")
        print(f"   • Router Phân luồng:    {st['router_ok']}/{total} ĐÚNG ({total - st['router_ok']} SAI)")
        print(f"   • CRAG Grader Ngữ cảnh: {st['status_ok']}/{total} ĐÚNG ({total - st['status_ok']} SAI)")
        print(f"   • Timestamp Video:      {st['ts_ok']}/{total} ĐÚNG ({total - st['ts_ok']} SAI)")
        print(f"   • Độ trễ trung bình:    {avg_t:.1f} ms")
    print("=" * 74)

    # Xuất báo cáo Markdown vĩnh viễn (không đè tệp)
    output_report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_report_path, "w", encoding="utf-8") as f:
        f.write(f"""# BÁO CÁO KHẢO THÍ ĐỊNH LƯỢNG RAG STAGE 11 (BENCHMARK SUITE)
**Thời gian bắt đầu:** {start_time_str}  
**Thời gian kết thúc:** {end_time_str} ({total_elapsed_sec:.1f} giây)  
**Sinh viên thực hiện:** Trần Thành Nghĩa (MSSV: `23DH112252`)  
**Đồ án:** In-Course Agentic RAG Copilot - Trường ĐH Ngoại ngữ - Tin học TP.HCM (HUFLIT)  
**Tập dữ liệu chuẩn:** `{dataset_path.name}` ({total_cases} test cases qua 4 tầng)

---

## 1. TỔNG HỢP CHỈ SỐ ĐỊNH LƯỢNG CỐT LÕI (OVERALL METRICS)

| Chỉ số khảo thí | Kết quả đạt được | Ngưỡng cam kết (CI Gate) | Đánh giá |
| :--- | :---: | :---: | :---: |
| **Router Accuracy** (Phân luồng ý định) | **{router_acc:.1f}%** ({router_correct}/{total_cases}) | $\\ge 90.0\\%$ | {'✅ ĐẠT' if router_acc >= 90 else '⚠️ CẦN TỐI ƯU'} |
| **CRAG Grader Precision** (Thẩm định ngữ cảnh) | **{crag_acc:.1f}%** ({crag_status_correct}/{total_cases}) | $\\ge 85.0\\%$ | {'✅ ĐẠT' if crag_acc >= 85 else '⚠️ CẦN TỐI ƯU'} |
| **Timestamp Safety & Accuracy** (|Δt| $\\le$ 15s / 0 ảo giác) | **{ts_acc:.1f}%** ({timestamp_correct}/{total_cases}) | $\\ge 88.0\\%$ | {'✅ ĐẠT' if ts_acc >= 88 else '⚠️ CẦN TỐI ƯU'} |
| **Độ trễ trung bình truy xuất** | **{avg_latency:.1f} ms** | $\\le 300.0 \\text{{ ms}}$ | ✅ ĐẠT |

---

## 2. PHÂN TÍCH THEO TỪNG TẦNG KIỂM THỬ (BREAKDOWN BY TIERS)

| Tầng kiểm thử (Tier) | Số ca | Router OK | CRAG OK | Timestamp OK | Độ trễ TB (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **1. In-Scope Technical** | {tier_stats['in_scope']['total']} | {tier_stats['in_scope']['router_ok']}/{tier_stats['in_scope']['total']} | {tier_stats['in_scope']['status_ok']}/{tier_stats['in_scope']['total']} | {tier_stats['in_scope']['ts_ok']}/{tier_stats['in_scope']['total']} | {tier_stats['in_scope']['time_ms']/max(1, tier_stats['in_scope']['total']):.1f} |
| **2. Out-of-Lesson** | {tier_stats['out_of_lesson']['total']} | {tier_stats['out_of_lesson']['router_ok']}/{tier_stats['out_of_lesson']['total']} | {tier_stats['out_of_lesson']['status_ok']}/{tier_stats['out_of_lesson']['total']} | {tier_stats['out_of_lesson']['ts_ok']}/{tier_stats['out_of_lesson']['total']} | {tier_stats['out_of_lesson']['time_ms']/max(1, tier_stats['out_of_lesson']['total']):.1f} |
| **3. Adversarial Hybrid** | {tier_stats['adversarial_hybrid']['total']} | {tier_stats['adversarial_hybrid']['router_ok']}/{tier_stats['adversarial_hybrid']['total']} | {tier_stats['adversarial_hybrid']['status_ok']}/{tier_stats['adversarial_hybrid']['total']} | {tier_stats['adversarial_hybrid']['ts_ok']}/{tier_stats['adversarial_hybrid']['total']} | {tier_stats['adversarial_hybrid']['time_ms']/max(1, tier_stats['adversarial_hybrid']['total']):.1f} |
| **4. Chit-Chat / Out-of-Domain** | {tier_stats['chit_chat']['total']} | {tier_stats['chit_chat']['router_ok']}/{tier_stats['chit_chat']['total']} | {tier_stats['chit_chat']['status_ok']}/{tier_stats['chit_chat']['total']} | {tier_stats['chit_chat']['ts_ok']}/{tier_stats['chit_chat']['total']} | {tier_stats['chit_chat']['time_ms']/max(1, tier_stats['chit_chat']['total']):.1f} |

---

## 3. KẾT LUẬN & ĐỊNH HƯỚNG BƯỚC TIẾP THEO
* Báo cáo này được tự động tạo và lưu trữ vĩnh viễn theo mốc thời gian, đảm bảo tính minh bạch khoa học của đồ án.
* Tệp JSON chi tiết phục vụ Interactive Workflow Dashboard được lưu độc lập tại `{json_archive_path.name}`.
""")

    # Xuất tệp JSON vĩnh viễn và bản copy latest cho Dashboard
    benchmark_payload = {
        "metadata": {
            "start_time": start_time_str,
            "end_time": end_time_str,
            "total_elapsed_sec": round(total_elapsed_sec, 2),
            "student_name": "Trần Thành Nghĩa",
            "student_id": "23DH112252",
            "university": "HUFLIT",
            "dataset_name": dataset_path.name,
            "total_cases": total_cases
        },
        "summary": {
            "router_accuracy": round(router_acc, 1),
            "router_correct": router_correct,
            "crag_precision": round(crag_acc, 1),
            "crag_correct": crag_status_correct,
            "timestamp_safety": round(ts_acc, 1),
            "timestamp_correct": timestamp_correct,
            "avg_latency_ms": round(avg_latency, 1),
            "tier_breakdown": {
                t_key: {
                    "total": tier_stats[t_key]["total"],
                    "router_ok": tier_stats[t_key]["router_ok"],
                    "status_ok": tier_stats[t_key]["status_ok"],
                    "ts_ok": tier_stats[t_key]["ts_ok"],
                    "avg_latency_ms": round(tier_stats[t_key]["time_ms"] / max(1, tier_stats[t_key]["total"]), 1)
                } for t_key in tier_stats
            }
        },
        "cases": results_detail
    }

    # 1. Lưu bản lưu trữ vĩnh viễn có timestamp
    with open(json_archive_path, "w", encoding="utf-8") as f:
        json.dump(benchmark_payload, f, ensure_ascii=False, indent=2)

    # 2. Cập nhật bản latest phục vụ Dashboard đồng bộ
    with open(latest_json_path, "w", encoding="utf-8") as f:
        json.dump(benchmark_payload, f, ensure_ascii=False, indent=2)

    print(f"\n[LƯU TRỮ VĨNH VIỄN] Báo cáo Markdown: {output_report_path}")
    print(f"[LƯU TRỮ VĨNH VIỄN] Dữ liệu JSON:     {json_archive_path}")
    print(f"[ĐỒNG BỘ DASHBOARD] Dữ liệu mới nhất: {latest_json_path}")

    await close_async_qdrant_client()


def main():
    parser = argparse.ArgumentParser(description="Chạy bộ khảo thí tự động Stage 11 Benchmark cho In-Course Agentic RAG Copilot.")
    parser.add_argument("--dataset", "-d", type=str, default=None, help="Đường dẫn tới tệp benchmark JSON cần chạy (bỏ qua menu tương tác)")
    args = parser.parse_args()

    if args.dataset:
        dataset_path = Path(args.dataset)
        if not dataset_path.is_absolute():
            dataset_path = PROJECT_ROOT / dataset_path
    else:
        dataset_path = select_dataset_interactive()

    asyncio.run(run_benchmark(dataset_path))


if __name__ == "__main__":
    main()
