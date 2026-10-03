# Original User Request

## 2026-10-03T14:31:33Z

# Teamwork Project Prompt — Launched

Dự án In-Course Agentic RAG Copilot (Sinh viên thực hiện: Trần Thành Nghĩa - MSSV: 23DH112252, Trường Đại học Ngoại ngữ - Tin học TP.HCM - HUFLIT).
Tối ưu hóa Lõi Truy xuất, Modality-Aware Latency Gate và loại bỏ triệt để hiện tượng bài cũ nuốt bài mới theo chuẩn mực Yan et al. (arXiv:2401.15884) và ICLR 2025 (Relevance vs. Context Sufficiency Invariant).

Working directory: d:\In_Course_Agentic_RAG_Copilot
Integrity mode: benchmark

Reference materials:
- Lý thuyết Corrective RAG (CRAG): Yan et al. (Google DeepMind / USTC / UCLA - arXiv:2401.15884)
- Bất biến ICLR 2025: Relevance vs. Context Sufficiency Invariant
- Tệp kết quả khảo thí định lượng: docs/benchmarks/stage11_results_2026-10-03_20-52-50.json
- Báo cáo khảo thí định lượng: docs/benchmarks/stage11_report_2026-10-03_20-52-50.md
- Quy chuẩn dự án: AGENTS.md

---

## Bảng Phân Bổ Subagents & Kỹ Năng Kích Hoạt (Skill Allocation Matrix)

| Subagent | Vai trò (Role) | Model | Kỹ năng may đo kích hoạt (Bespoke Skills) | Trọng tâm nhiệm vụ |
| :--- | :--- | :---: | :--- | :--- |
| `@rag-architect` | RAG & CRAG Architect | Pro | `rag-diagnostics-eval`<br>`qdrant-hybrid-inspector` | Chẩn đoán lỗi P01-P12, kiểm định toán học phân tầng, phê duyệt thiết kế Modality-Aware Gate. |
| `@solution-analyst` | Mathematical Decision Specialist | Pro | `rag-diagnostics-eval`<br>`qdrant-hybrid-inspector` | Thẩm định phân phối điểm số, tính toán biên độ tối ưu Pareto (Margin 0.12, S_video 0.30, S_ast 0.35). |
| `@core-coder` | Core Retrieval Engineer | Pro | `ast-code-chunker`<br>`whisper-canonicalizer-tester` | Cài đặt Modality-Aware Gate vào `retrieval.py`, đồng bộ `config.py`, bảo toàn Data/Code Separation. |
| `@qa-tester` | QA Benchmark Engineer | Flash | `rag-diagnostics-eval` | Chạy Pre/Post Benchmark 200 câu Golden Dataset, đối chứng 14 ca lỗi Tier 1, rà soát hồi quy Tier 4/Security. |
| `@academic-scribe` | Academic Scribe & Auditor | Flash | `daily-workflow` | Biên soạn Daily Mentor Report (`docs/daily_reports/`) và Theory Learning Document (`docs/theory_learning/`). |

---

## Requirements

### R1. Pha 1 - Chẩn đoán Ma trận Nhầm lẫn P01-P12 & Thiết kế Kiến trúc Phân tầng
**Phụ trách:** `@rag-architect` & `@solution-analyst`  
**Kỹ năng kích hoạt:** `rag-diagnostics-eval`, `qdrant-hybrid-inspector`
- Phân tích chi tiết 14 ca lỗi Tier 1 In-Scope trong `docs/benchmarks/stage11_results_2026-10-03_20-52-50.json` (BENCH-004, BENCH-007, BENCH-010, BENCH-011, BENCH-014, BENCH-041,...).
- Phân loại nguyên nhân gốc theo 12 Failure Patterns (P01-P12) để xác định rõ cơ chế Future Probing nuốt nhầm câu hỏi bài hiện tại sang `out_of_lesson` hoặc `coverage_gap`.
- Thiết kế kiến trúc phân tầng 4 cấp toán học tuân thủ nghiêm ngặt *Retrieval Hierarchy Precedence Invariant* và *Modality-Aware Latency Gate Invariant*:
  + **Tầng 1 (Grounded Anchor - Early Exit):** Bài hiện tại có Code AST >= 0.35 HOẶC Video Transcript >= 0.30 -> Xác lập GROUNDED ngay lập tức, khóa cổng Early Exit không cho thăm dò bài tương lai.
  + **Tầng 2 (Future Lesson Probe):** Chỉ kích hoạt khi bài hiện tại thực sự thiếu thông tin (< 0.22) VÀ bài tương lai đạt biên độ vượt trội Delta Margin >= 0.12 cùng điểm sàn tự tin >= 0.40.
  + **Tầng 3 (Graceful Degradation):** Chỉ kích hoạt khi bài tương lai không đạt biên độ vượt trội, và bài hiện tại có điểm sàn S_current >= 0.20 cùng xác thực CRAG.
  + **Tầng 4 (Coverage Gap):** Khi cả bài hiện tại và bài tương lai đều không đạt điểm chuẩn.
- Bàn giao Technical Specifications cho `@core-coder`.

### R2. Pha 2 - Triển khai Mã nguồn Lõi & Đồng bộ Cấu hình
**Phụ trách:** `@core-coder`  
**Kỹ năng kích hoạt:** `ast-code-chunker`, `whisper-canonicalizer-tester`
- Triển khai kiến trúc phân tầng vào `app/services/retrieval.py`:
  + Xóa bỏ hoàn toàn cổng chặn độ trễ phẳng 0.22.
  + Cài đặt Modality-Aware Gate phân biệt rạch ròi giữa Code AST (chính xác cú pháp) và Video Transcript (văn nói tự nhiên).
- Đồng bộ các hằng số toán học vào `app/config.py`:
  + `MODALITY_GATE_AST_THRESHOLD = 0.35`
  + `MODALITY_GATE_VIDEO_THRESHOLD = 0.30`
  + `FUTURE_PROBE_MARGIN = 0.12`
  + `FUTURE_PROBE_MIN_CONFIDENCE = 0.40`
- Đảm bảo 100% tuân thủ Pydantic v2, typing nghiêm ngặt và không vi phạm Data/Code Separation Invariant (không hardcode từ điển hay metadata trong file `.py`).

### R3. Pha 3 - Kiểm thử Độc lập, Đối chứng & Chống Hồi quy
**Phụ trách:** `@qa-tester`  
**Kỹ năng kích hoạt:** `rag-diagnostics-eval`
- Chạy Pre/Post Benchmark Cycle: Xác nhận 14 ca lỗi Tier 1 mục tiêu chuyển trạng thái về GROUNDED.
- Khảo thí toàn diện trên toàn bộ 200 câu hỏi của Golden Dataset (`tests/data/benchmark_golden_dataset.json`):
  + Router Accuracy duy trì >= 98.0%.
  + CRAG Grader Precision vượt ngưỡng cam kết CI/CD: >= 85.0% (>= 170/200).
  + Timestamp Safety & Accuracy tiếp tục cải thiện lên >= 75.0% - 85.0%.
  + Tuyệt đối không phát sinh hồi quy (regression) ở Tier 4 Chit-chat hoặc Security Guardrail.

### R4. Pha 4 - Tổng hợp Hồ sơ Học thuật & Báo cáo Giảng viên
**Phụ trách:** `@academic-scribe`  
**Kỹ năng kích hoạt:** `daily-workflow`
- Cập nhật Báo cáo Giảng viên hàng ngày tại `docs/daily_reports/2026-10-03_report.md`:
  + Ghi nhận tiến trình: Reclean Transcripts 83 bài -> Code AST Metadata Binding -> Tối ưu Modality-Aware Gate.
  + Bảng đối chiếu chỉ số: Baseline cũ (76.5%) -> Khảo thí đợt 1 (80.0%) -> Khảo thí đợt 2 (>= 85.0%).
- Soạn thảo Tài liệu Lý thuyết tại `docs/theory_learning/2026-10-03_theory.md`:
  + Luận giải cơ sở khoa học: Tại sao không dùng từ điển vá tạm (Zero Quick-Fix) mà phải dùng Modality-Aware Gate?
  + Phân tích nguyên lý toán học phân tách ngữ nghĩa (Semantic Relevance) vs Độ đầy đủ thông tin (Context Sufficiency - ICLR 2025).
  + Bộ 5 câu hỏi phản biện bảo vệ đồ án trước Hội đồng tốt nghiệp HUFLIT.

---

## Acceptance Criteria

### Technical & Quantitative Metrics (Golden Dataset 200 câu)
- [ ] Router Accuracy >= 98.0% (196/200)
- [ ] CRAG Grader Precision >= 85.0% (>= 170/200, tăng tối thiểu +5.0% từ mốc 80.0%)
- [ ] Timestamp Safety & Accuracy >= 75.0%
- [ ] 14 ca lỗi Tier 1 In-Scope (BENCH-004, BENCH-007, BENCH-010,...) được phục hồi về trạng thái `grounded`
- [ ] Không có hồi quy (0 regression) tại Tier 4 Chit-chat (40/40) và Security Guardrail (10/10)

### Architectural & Scientific Invariants
- [ ] Zero Quick-Fix: Không có bất kỳ dòng regex hay hardcode từ khóa truy vấn cá biệt nào trong `app/agent/router.py` và `app/services/retrieval.py`
- [ ] Data/Code Separation Invariant: Mọi metadata ánh xạ mốc video và danh mục nghiệp vụ được lưu trữ độc lập tại `data/metadata/*.json`
- [ ] Tuân thủ chuẩn mực Yan et al. (arXiv:2401.15884) và ICLR 2025 (Context Sufficiency)
- [ ] Đầy đủ hồ sơ học thuật `docs/daily_reports/2026-10-03_report.md` và `docs/theory_learning/2026-10-03_theory.md`
