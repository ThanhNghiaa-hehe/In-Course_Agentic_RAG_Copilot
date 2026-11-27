# Evaluation, Calibration & Benchmark Integrity Invariants

Tài liệu trích xuất từ `AGENTS.md` (§10, §11, §12, §14) theo cơ chế Progressive Disclosure cho kỹ năng `rag-diagnostics-eval`.

---

## 1. Evaluation-Driven Development (EDD) & Benchmark-First Mandate (§10)
- **Benchmark-First:** Không chỉnh hàng loạt prompt, threshold hay thuật toán retrieval chỉ vì 1–2 ca thủ công đơn lẻ; mọi cải tiến bắt buộc đối chiếu qua **Stage 11 Benchmark Suite** (Pre/Post Optimization Cycle).
- **Golden Dataset 4 Tầng:** (1) `in_scope`; (2) `out_of_lesson`; (3) `adversarial_hybrid`; (4) `chit_chat` / `out_of_domain`.
- **4 Chỉ Số Cốt Lõi:** Router & Grader Accuracy; Timestamp Multi-Grounding & Strict Hit ($|\Delta t| \le 15\text{s}$ / $0$ timestamp khi gap/OOD); Faithfulness (RAGAS Triad); Latency (TTFT & Total ms).
- **Regression Prevention:** Chỉ phê duyệt & commit thay đổi kiến trúc khi điểm tổng thể tăng hoặc giữ vững, không làm sụt giảm các test chuẩn.
- **Data-Centric AI Label Audit & Versioning:** Khi đề thi có Label Noise (P13), tuyệt đối không sửa đè âm thầm: (1) lưu bản `tests/data/<dataset>_v1_legacy.json`; (2) cập nhật `<dataset>.json` đối chiếu 1:1 transcript & AST; (3) lập changelog khoa học tại `docs/benchmarks/dataset_audit_and_changelog_v2.md`.

## 2. Calibrated Decision Layer & Empirical Hardware Benchmarking (§11)
- **Zero Pseudo-Calibration:** Không tự nhận Softmax với $T$ cảm tính là calibrated. Bắt buộc tối ưu bằng dữ liệu thực nghiệm (Platt Scaling qua CV hoặc Temperature Scaling tối thiểu hóa NLL — Guo et al., ICML 2017) và xác nhận bằng:
  $$\text{ECE} = \sum_{m=1}^{M} \frac{|B_m|}{N} \left| \text{acc}(B_m) - \text{conf}(B_m) \right| \le 0.1200 \quad (M = 10), \qquad \text{Brier} = \frac{1}{N} \sum_{i=1}^N \sum_{k=1}^K (p_{ik} - y_{ik})^2 \le 0.1200$$
- **Empirical Hardware Benchmarking:** Không đưa số thời gian ước lượng cảm tính (như 0.1s) vào báo cáo/luận văn; mọi latency & thời gian train phải đo bằng `time.perf_counter()` trên phần cứng thực ($\mu \pm \sigma$).
- **Local Independence:** Router, Embedding và Socratic logic phải sẵn sàng độc lập trên môi trường local, không phụ thuộc dịch vụ Cloud thử nghiệm/waitlist.

## 3. Strict Benchmark Authenticity, Anti-Surrogate & Decoupling (§12)
- **Anti-Surrogate Evaluation:** Tuyệt đối cấm công thức xấp xỉ giả tạo (như `0.92 + crag * 0.06`) hoặc chuỗi `mock_socratic_response` để đẻ ra RAGAS/G-Eval xanh giả. Nếu không gọi LLM thật, phải ghi rõ `null` / `--` / `Chưa đo lường (Cần LLM)`.
- **Data-Centric Benchmark Decoupling:** Khôi phục câu hỏi nguyên bản không chèn alias gợi ý; phân tách rạch ròi mẫu số RAG ($N_{\text{RAG}} = 160$, không mượn 40 câu Chit-chat làm phồng CRAG/TS); cột đánh giá latency phải phản ánh SLA thực.
- **Curriculum-Aligned Labeling:** Mọi nhãn `lesson_seq`, `expected_retrieval_status`, `expected_has_timestamp` phải đối chiếu 1:1 với `lessons_manifest.json` và transcript thật.
- **Multi-Grounding Timestamp Evaluation Principle:** Video 30–60 phút thường nhắc 1 khái niệm ở nhiều đoạn; cờ `has_ts: True` xác nhận trích đúng video thật, $|\Delta t| > 30\text{s}$ là *Single-Label Annotation Discrepancy* chứ không phải lỗi ảo giác.
- **RAGAS Domain Pre-filtering & Multi-Passage Max-Entailment:** Chỉ tính Faithfulness khi `is_course_query == True` và `actual_status == "grounded"` (cấm tính trên `chit_chat`, `nav`, `oos`, `jailbreak`); đánh giá $\max_j P(\text{Entailment}(c_j, s)) \ge 0.30$ trên từng chunk độc lập.

## 4. Data Decontamination & Confident Learning (§14)
- **Zero Test-Set Leakage:** Kiểm toán tự động Jaccard ($J < 0.70$, Data Leakage = `0.00%`); luôn báo cáo song song **K-Fold CV Score**, **Frozen Held-Out Unseen Score**, và **Generalization Gap** ($\text{Score}_{\text{CV}} - \text{Score}_{\text{Unseen}}$).
- **Confident Learning (MIT JAIR 2021):** Lọc nhiễu nhãn qua ma trận $C_{\tilde{y}, y^*}$; câu ẩn dụ đời sống chứa thực thể cú pháp C++ hỏi logic lập trình -> `course_query`, câu thơ/tình cảm/ý kiến cá nhân -> `out_of_scope`.

## 5. Historical Benchmark Milestones (Tham Chiếu So Sánh)
- **Chặng 4 (05/11/2026):** Unseen 200-Query Router `95.50%`, CRAG `89.00%` (`178/200`), TS Multi-Grounding `91.00%`, 5-Fold CV `90.87% ± 3.44%`, ECE `0.0241` ($T^* = 0.7520$), OOD-100 `96.00%`, RAGAS No-Hallucination `86.52%`, OWASP `100.0%`.
- **Chặng 5 Multi-Turn (09/11/2026 - 50 sessions / 222 turns):** Intent `90.99%`, SRP `100.00%`, Budget `100.00%`, Status `82.88%`, ARR `68.09%`, WHR `44.14%`.
- **Chặng Stage-2 + Kaggle Check (27/11/2026, commit `fc7f700`):** Stage 11 Golden 200: Router `94.0%`, CRAG **`92.5%`**, TS Multi-Grounding **`92.0%`**, TS Strict `85.5%`, Avg Latency `853.9ms`; Multi-Turn Retrieval: Intent `97.75%`, Status `92.34%`, ARR **`97.87%`**, Strict WHR `53.15%`, Budget `100.0%`, P50 `857.5ms`; `46/46` pytest PASSED.
