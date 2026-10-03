# Project: In-Course Agentic RAG Copilot - Retrieval & Latency Optimization

## Architecture
- Module: `app/services/retrieval.py` (Core retrieval service, hybrid search Qdrant dense+sparse, cross-encoder reranker, Modality-Aware Gate, Future Lesson Probing, Graceful Degradation)
- Module: `app/config.py` (System constants & mathematical thresholds)
- Module: `app/services/chat_graph.py` (LangGraph StateGraph nodes: router, retrieval, crag_grader)
- Module: `tests/data/benchmark_golden_dataset.json` (200-question Golden Dataset test suite)
- Module: `docs/daily_reports/` and `docs/theory_learning/` (Academic documentation & thesis defense preparation)

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | P01-P12 Diagnostic Matrix | Chẩn đoán 14 ca lỗi Tier 1 theo 12 failure patterns từ kết quả stage 11 | M1 | ORIGINAL_REQUEST §R1 |
| 2 | 4-Tier Hierarchical Specification | Thiết kế phân tầng toán học: Grounded Anchor (T1), Future Probe (T2), Degradation (T3), Coverage Gap (T4) | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Modality-Aware Latency Gate | Xóa cổng phẳng 0.22, cài đặt cổng phân biệt Code AST (>=0.35) vs Video Transcript (>=0.30) | M2 | ORIGINAL_REQUEST §R2 |
| 4 | Config Synchronization | Đồng bộ các ngưỡng toán học (`MODALITY_GATE_AST_THRESHOLD=0.35`, `MODALITY_GATE_VIDEO_THRESHOLD=0.30`, `FUTURE_PROBE_MARGIN=0.12`, `FUTURE_PROBE_MIN_CONFIDENCE=0.40`) | M2 | ORIGINAL_REQUEST §R2 |
| 5 | Data/Code Separation & Invariants | Đảm bảo không hardcode regex/từ điển, tuân thủ Yan et al. & ICLR 2025 | M2 | ORIGINAL_REQUEST §R2, AGENTS.md |
| 6 | Golden Dataset 200 Benchmark Run | Chạy Pre/Post Benchmark, đo Router Accuracy (>=98%), CRAG Precision (>=85%), Timestamps (>=75%) | M3 | ORIGINAL_REQUEST §R3 |
| 7 | Anti-Regression & Error Recovery | Xác nhận 14 ca Tier 1 phục hồi thành GROUNDED, 0 regression ở Tier 4 Chit-chat & Security | M3 | ORIGINAL_REQUEST §R3 |
| 8 | Academic Daily Report | Soạn thảo `docs/daily_reports/2026-10-03_report.md` | M4 | ORIGINAL_REQUEST §R4 |
| 9 | Academic Theory Document | Soạn thảo `docs/theory_learning/2026-10-03_theory.md` với 5 câu hỏi phản biện HUFLIT | M4 | ORIGINAL_REQUEST §R4 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | P01-P12 Diagnosis & Hierarchical Architecture | Phân tích 14 ca lỗi Tier 1, phân loại P01-P12, đặc tả kiến trúc phân tầng 4 cấp | none | DONE |
| M2 | Core Retrieval & Config Sync | Cài đặt Modality-Aware Gate trong `retrieval.py`, đồng bộ `config.py`, tuân thủ Invariants | M1 | IN_PROGRESS |
| M3 | Benchmark & Anti-Regression Verification | Chạy benchmark 200 câu Golden Dataset, đo đạt tiêu chuẩn CRAG >=85%, 0 regression | M2 | PLANNED |
| M4 | Academic Documentation & Final Reporting | Lập báo cáo tiến độ giảng viên và tài liệu lý thuyết phản biện tốt nghiệp | M3 | PLANNED |

## Interface Contracts
### `app.config` ↔ `app.services.retrieval`
- `MODALITY_GATE_AST_THRESHOLD: float = 0.35`
- `MODALITY_GATE_VIDEO_THRESHOLD: float = 0.30`
- `FUTURE_PROBE_MARGIN: float = 0.12`
- `FUTURE_PROBE_MIN_CONFIDENCE: float = 0.40`
- `CODE_SCORE_THRESHOLD: float = 0.35`
- `VIDEO_SCORE_THRESHOLD: float = 0.22`

### `RetrievalService._probe_future_lessons`
- Pre-condition: Check current lesson confidence via Modality-Aware Gate.
- Early Exit if: `(has_ast and max_ast >= 0.35)` or `(max_video >= 0.30)`.
- Future Probe condition: `S_future >= 0.40` and `(S_future - max_current) >= 0.12`.

## Code Layout
- `app/config.py`: Threshold constants and settings
- `app/services/retrieval.py`: RetrievalService logic and latency gate
- `tests/data/benchmark_golden_dataset.json`: Golden dataset test cases
- `scripts/run_rag_benchmark.py`: Benchmark runner script
- `docs/daily_reports/2026-10-03_report.md`: Daily mentor report
- `docs/theory_learning/2026-10-03_theory.md`: Academic theory learning document
