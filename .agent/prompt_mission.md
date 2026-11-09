# NHIỆM VỤ TỐI ƯU HÓA XUYÊN ĐÊM (OVERNIGHT PIPELINE MANDATE): ĐỘT PHÁ CHỈ SỐ ĐA LƯỢT ARR & RETRIEVAL STATUS
> **Dự án:** In-Course Agentic RAG Copilot — LangGraph Stateful Orchestration  
> **Tác giả:** Trần Thành Nghĩa (MSSV: `23DH112252`), HUFLIT  
> **Thời điểm xuất phát:** 2026-11-09T23:15:00+07:00  
> **Nguyên tắc bất biến:** Zero Fake Data | Zero Hardcoded Regex | 100% Machine Learning / Semantic Vector Formulation

---

## 1. BẢNG SỐ LIỆU XUẤT PHÁT (BASELINE TRỰC TIẾP TỪ 50 SESSIONS / 222 TURNS)
- **Intent Classification Accuracy:** **90.99%** (202/222 turns) -> ĐÃ ĐẠT CHUẨN
- **Socratic Refusal Precision (SRP):** **100.00%** (15/15 turns) -> XUẤT SẮC (Bảo toàn 100% không rò rỉ mã nguồn giải bài hộ)
- **Context Budget Compliance:** **100.00%** (222/222 turns) -> XUẤT SẮC (Lịch sử <= 1,126 / 2,400 chars)
- **CÁC ĐIỂM NGHẼN BẮT BUỘC ĐỘT PHÁ TRONG ĐÊM:**
  1. **Anaphora Resolution Rate (ARR):** Hiện đạt **68.09%** (64/94 turns) -> **Mục tiêu: $\ge 85.0\% - 90.0\%$**.
  2. **Retrieval Status Precision:** Hiện đạt **82.88%** (184/222 turns) -> **Mục tiêu: $\ge 88.0\%$**.
  3. **Topic Switching Precision (Tier 3):** Hiện đạt **59.52%** -> **Mục tiêu: $\ge 80.0\%$**.
  4. **Deterministic Timestamp Whitelist Hit (WHR):** Hiện đạt **44.14%** -> Mở rộng dung sai Multi-Grounding cho bài giảng dài.

---

## 2. CHỈ ĐỊNH PHƯƠNG PHÁP CHÍNH THỐNG (CHỐNG 100% QUICK-FIX / OVERFITTING)
1. **Context-Aware Query Formulation (SIGIR / Google Research):**
   - Khi phát hiện đại từ thay thế / câu cụt (*"nó"*, *"bài đó"*, *"cụ thể là ở đâu"*, *"trong đó có gì"*), áp dụng thuật toán Semantic Context Fusion:
     - Nâng cấp cơ chế trích xuất thực thể từ turn trước $u_{t-1}$ để hợp nhất vào dense query vector.
     - Sử dụng E5 Asymmetric Prefix đúng chuẩn: `query: ` cho toàn bộ câu ghép, kết hợp BM25 sparse weights cho các thực thể then chốt.
2. **Pareto Context Sufficiency & Topic Switch Gate (ICLR 2025):**
   - Giải quyết điểm nghẽn Tier 3 (59.52%): Khi học viên nhảy sang bài học mới ("thế còn con trỏ thì học ở đâu"), router và retrieval cần nhận diện ranh giới chuyển bài (Topic Shift Detection) để không bị neo vào bài học cũ, điều chỉnh `target_lesson_seq` chuẩn xác.
3. **Dynamic CRAG Grader Calibration (Yan et al.):**
   - Tinh chỉnh biên độ Pareto giữa `grounded`, `coverage_gap` và `out_of_lesson` trên các câu hỏi đa lượt.
4. **Nghiêm cấm tuyệt đối:**
   - KHÔNG hardcode từ khóa theo câu hỏi của 50 sessions trong `multiturn_benchmark_dataset.json`.
   - KHÔNG viết regex dạng `if "con trỏ" in text:` hay `if "sắp xếp" in text:`. Mọi cải tiến phải nằm ở thuật toán tổng quát hóa.

---

## 3. PHỐI HỢP ĐA TÁC NHÂN QUA 3 NHỊP LIÊN HOÀN (pstack Standards)
- **Nhịp 1A (@codebase-auditor - Claude):** Phân tích sâu 30 ca lỗi ARR và 38 ca lỗi Retrieval Status trong file `docs/benchmarks/multiturn_benchmark_results.json`. Bóc tách căn nguyên toán học.
- **Nhịp 1B (@rag-architect & @solution-analyst - Gemini Argon):** Thiết kế giải thuật Semantic Context Fusion và Topic Shift Gate. Xuất đặc tả toán học vào `.agent/implementation_spec.md`.
- **Nhịp 2 (@core-coder - Gemini Flash High):** Triển khai mã nguồn chính xác vào `app/services/chat_graph.py` và `app/services/retrieval.py`. Strict typing, Pydantic v2.
- **Nhịp 3 (@grounding-evaluator & @qa-tester):** Chạy lại bộ khảo thí `python scripts/run_multiturn_benchmark.py` để lấy bằng chứng thực nghiệm (Evidence Gate) đối chiếu trước và sau khi tối ưu.
