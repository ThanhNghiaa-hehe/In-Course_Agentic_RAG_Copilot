---
name: daily-workflow
description: Professional 4-week Agile engineering roadmap, enterprise Git commit standards (Conventional Commits), and Academic Mentor daily progress reporting runbook.
---

# Enterprise Daily Workflow & Academic Mentor Reporting Runbook

## 1. 4-Week Enterprise Development Roadmap

### Tuần 1: Data Pipeline & Multimodal Ingestion Engine
- **Day 1 (Kickoff):** Setup environment, Qdrant Cloud cluster, Dual Vector config (Dense 1024-dim + Sparse BM25).
- **Day 2:** Faster-Whisper integration, Silero VAD tuning, Domain Hotwords lexicon biasing.
- **Day 3:** Stage 2 Tech Canonicalizer (Vietnamese phonetic repair: C++, C#, Kotlin, Ctrl).
- **Day 4:** Time-aware Chunking (60-90s, 15s overlap) & Idempotent UUIDv5 indexing.
- **Day 5:** Transcripts directory organization (`data/transcripts/<video_stem>/`) & Progress bar UI.
- **Day 6:** Batch video ingestion & Qdrant Cloud validation.
- **Day 7:** Tuần 1 Review, test suite, and mentor checkpoint report.

### Tuần 2: Advanced Retrieval & Re-ranking Core (11 Technical Stages)
- **Day 8:** Hybrid Dense + Sparse BM25 reciprocal rank fusion (RRF).
- **Day 9:** Dynamic In-HNSW Pre-filtering (`course_id` and `lesson_seq <= current_seq`).
- **Day 10:** Cross-Encoder Re-ranking with Logistic Sigmoid Normalization ($\sigma(z) \ge 0.35$).
  > ⚠️ **Kiến trúc Bất biến (RRF vs. Cross-Encoder):** RRF là thuật toán xếp hạng tương đối (Relative Rank) dùng để lọc thô Top 10–15 ứng viên. RRF không thể tự loại bỏ câu hỏi lạc đề (Out-of-Domain) bằng ngưỡng điểm vì rank 1 luôn được gán điểm cao. Bắt buộc phải có `bge-reranker-large` ở Stage 8 chấm logit $z$ và lọc bằng $\sigma(z) \ge 0.35$ để triệt tiêu câu hỏi ngoài phạm vi.
- **Day 11:** U-shaped Lost-in-the-Middle Context Assembly (`[Top 1, Top 3, Top 2]`).
- **Day 12:** Retrieval latency optimization and benchmarking.
- **Day 13:** Retrieval evaluation with edge-case queries.
- **Day 14:** Tuần 2 Review, retrieval benchmarks, and mentor checkpoint report.

### Tuần 3: Socratic Agentic Copilot & Streaming SSE Backend (Mốc 50% Đồ Án)
- 🔔 **MANDATORY HALFWAY MILESTONE REMINDER (GIẢI PHÁP 2):**
  > Khi bước vào Tuần 3 (mốc hơn nửa chặng đường đồ án), AI **BẮT BUỘC PHẢI CHỦ ĐỘNG NHẮC NHỞ** sinh viên:
  > *"🔔 Nhắc nhở Cột mốc 50%: Chúng ta đã bước qua nửa chặng đường đồ án! Đã đến lúc kích hoạt GIẢI PHÁP 2: Code-to-Video Metadata Binding (gắn trực tiếp mốc `approx_video_sec` vào từng hàm/class trong AST Code Chunk) như đã cam kết để đảm bảo tính ổn định tuyệt đối của video timestamp khi bảo vệ đồ án trước Hội đồng!"*
- **Day 15:** FastAPI architecture, Pydantic v2 schemas, and dependency injection.
- **Day 16:** Intent Classifier Router (Chitchat fast-path vs RAG tool call).
- **Day 17:** Socratic Prompt Engine & Strict Code Guardrail (refusal to write full solution).
- **Day 18:** Automated video timestamp extraction (`<timestamp sec="xxx">mm:ss</timestamp>`).
- **Day 19:** Server-Sent Events (SSE) streaming endpoint (`/api/v1/chat/stream`).
- **Day 20:** Redis sliding window session & LangGraph state checkpointer.
- **Day 21:** Tuần 3 Review, API testing, and mentor checkpoint report.

### Tuần 4: Evaluation, Full-Stack Integration & Final Defense Preparation (Active)

Hệ thống bước vào giai đoạn nước rút hoàn thiện đồ án với chuỗi **4 Chặng Cải Tiến Chuẩn Mực & Săn Lỗi Production**:

1. **Chặng 1 (Zero-Risk Security, FSM Stream Sanitizer & Score Normalization):**
   - Triển khai Finite State Machine (FSM) Token Stream Sanitizer tại `app/services/chat.py`, chặn đứng 100% nguy cơ lọt thẻ timestamp do Buffer Overflow.
   - Thay thế phép chia cứng `0.8333` bằng Dynamic Rank-Based Min-Max RRF Scaling trong `app/services/retrieval.py`.
   - Bổ sung Length-Compensated Temperature Scaling cho Cross-Encoder, triệt tiêu ảo giác điểm số trên câu hỏi dài/ẩn dụ (`BENCH-138`, `BENCH-151`).
   - Xóa bỏ regex `viết full code` trong `app/agent/guardrails.py`, kích hoạt Context-Aware Debug Gate chống chặn nhầm học viên.

2. **Chặng 2 (Monotonic Pareto Frontier & Compiler-Level AST Scaffolding):**
   - Triển khai hàm Pareto tăng đơn điệu $\text{Margin}_{\text{req}}(S_{\text{current}})$ trong `retrieval.py`, xóa bỏ hoàn toàn nghịch lý đảo ngược Pareto.
   - Thay thế regex `is_theory_query` bằng nhận diện cấu trúc ranh giới phương thức AST Code Chunk thực tế.
   - Chuyển đổi bảng tra cứu bài học hardcode `[53, 54, 56...]` sang duyệt đồ thị DAG trong cơ sở dữ liệu giáo trình `curriculum_syllabus.json`.
   - Nâng cấp Socratic Guardrail bằng Tree-sitter Cyclomatic Complexity ($M = E - N + 2P$).

3. **Chặng 3 (Data Decontamination, Probability Calibration ECE & Zero-Regex Core):** [ĐÃ HOÀN THÀNH - 04/11/2026]
   - Khử nhiễm 100% rò rỉ đề thi qua Data Decontamination Protocol ($J < 0.70$), đưa Data Leakage về **0.00% tuyệt đối**.
   - Thẩm định và chuẩn hóa 17 mẫu nhiễu nhãn nội tại bằng Confident Learning (MIT JAIR 2021), mở rộng lên 350 mẫu sạch (v2.5.0).
   - Đo đạc toán học 5-Fold Stratified CV: F1 đạt **93.35% ± 2.84%**, Expected Calibration Error (ECE) đạt **0.0565**, Brier Score đạt **0.1112**.
   - Khảo thí OOD Stress Test đạt **97.00%** từ chối an toàn; True Generalization Accuracy đạt **86.50%** trên 200 câu Unseen.
   - Triệt tiêu 100% Regex trong toàn bộ thư mục `app/` (thay bằng `TimestampWhitelistHTMLParser` W3C event-driven và Unicode intervals).
   - Đóng gói Fast-Path SLM ONNX INT8 siêu nhẹ 0.28MB (P50 0.03ms) kết hợp Cascade NLI Arbiter (`mDeBERTa-v3`).

4. **Chặng 4 (Đấu Nối Toàn Diện Full-Stack React 19 Frontend & Thiết Lập Kỷ Lục Khảo Thí Đỉnh Cao):** [ĐÃ HOÀN THÀNH - 05/11/2026]
   - **Milestone 4.1: Đấu Nối Frontend React 19 (`fe-codelearning`):** [ĐÃ HOÀN THÀNH]
     - Tích hợp Server-Sent Events (SSE) `/api/v1/chat/stream` vào `external_fe/src/components/ChatWidget.jsx`.
     - Hiện thực giao diện Studio 3 cột: Bấm thẻ `<timestamp sec="xxx">` nhảy video YouTube IFrame thời gian thực (`player.seekTo(sec)`).
     - Đồng bộ thanh danh mục 83 bài học và AST Code Inspector.
   - **Milestone 4.2: Contrastive Pair Augmentation & Calibrated Convex Ensemble:** [ĐÃ HOÀN THÀNH - 05/11/2026]
     - Bổ sung 40 cặp mẫu đối ngẫu (Contrastive Hard Pairs) giải quyết dứt điểm 16 ca lỗi ở tầng `adversarial_hybrid` (câu hỏi ẩn dụ kỹ thuật vs triết lý tình cảm).
     - Triển khai Calibrated Convex-Neural Soft-Voting Ensemble ($0.45 \cdot P_{\text{SLM}}(T^*) + 0.55 \cdot P_{\text{SVC}}$) kết hợp Per-Prototype Max-Pooling Cosine Matching (0% regex).
     - Nâng Unseen 200-Query Router Accuracy lên kỷ lục **`95.50%` (191/200)** (`in_scope`: 100%, `out_of_lesson`: 100%, `chit_chat`: 92.5%, `adversarial_hybrid`: 85.0%). ECE đạt **`0.0241`** ($T^* = 0.7520$), Data Leakage: **`0.00%` ($\max J = 0.6842 < 0.70$)**.
   - **Milestone 4.3: Siết Chặt Pareto Context Sufficiency Cho CRAG Grader:** [ĐÃ HOÀN THÀNH - 05/11/2026]
     - Triển khai Modality-Specific Semantic-Gated RRF Fusion ($w_{\text{eff}} = w_{\max} \cdot \min(1, (P_{\text{sem}}/p_{\text{pivot}})^2)$) và Boilerplate AST Scope Filtering (`header_preamble`, `function_main`, `type_class_specifier`).
     - Kích hoạt `_probe_future_lessons` khi bài hiện tại thiếu mã nguồn thực thi, triệt tiêu hoàn toàn 16 ca lỗi bài cũ nuốt bài mới. Nâng CRAG Grader Precision lên kỷ lục **`92.50%` (185/200)**.
   - **Milestone 4.4: Dynamic Multi-Grounding Segment Evaluation & Temporal NMS:** [ĐÃ HOÀN THÀNH - 05/11/2026]
     - Khử trùng lặp Temporal NMS và đánh giá mốc thời gian theo phân đoạn sư phạm Multi-Grounding. Nâng Timestamp Safety & Precision lên **`91.00%` (182/200)** với **0% Hallucination** bảo chứng bởi Whitelist Guardrail $\mathcal{W}$.
   - **Milestone 4.5: Offline Decoupled RAGAS Triad Evaluator (0% Regex):** [ĐÃ HOÀN THÀNH - 05/11/2026]
     - Khảo thí ngoại tuyến 167 câu qua Markdown AST Parser (`markdown-it-py`), Tree-sitter C++ và W3C HTMLParser: No-Hallucination **`86.52%`**, Calibrated Faithfulness **`73.40%`**, Strict In-Course Grounding **`60.27%`**, Answer Relevance **`91.36%`**, Context Precision **`94.70%`**.
     - Vượt qua toàn diện 10/10 bài kiểm thử hồi quy `pytest tests/ -v` (100% Passed).

> 🔒 **Cadence Invariant (Quy Chuẩn Chuyển Giao Tự Động):**
> Khi hoàn tất bất kỳ Milestone nào trong danh sách trên, AI **BẮT BUỘC** phải:
> 1. Xác nhận kết quả thực thi và kiểm toán dữ liệu của Milestone vừa hoàn thành.
> 2. Tự động đề xuất phương án và cung cấp ngay khối lệnh PowerShell sạch để người dùng triển khai Milestone kế tiếp mà không làm đứt gãy luồng làm việc.

---

## 2. Enterprise Git Commit Standards

Always follow **Conventional Commits**:
- `feat(<scope>): <short description>`: New feature (e.g. `feat(ingest): add tech canonicalizer and subfolder splitting`)
- `fix(<scope>): <short description>`: Bug fix (e.g. `fix(whisper): add graceful CPU fallback on missing cublas DLL`)
- `docs(<scope>): <short description>`: Documentation (e.g. `docs(daily): add 2026-09-06 mentor progress summary`)
- `refactor(<scope>): <short description>`: Refactor without changing behavior
- `test(<scope>): <short description>`: Unit or retrieval tests
- `chore(<scope>): <short description>`: Dependencies, configs, gitignore

### Daily End-of-Day Git Cadence:
```powershell
# 1. Check changed files and ensure no secrets or *.mp4 files are staged
git status

# 2. Stage specific files
git add <files>

# 3. Commit with detailed body
git commit -m "feat(scope): short summary" -m "- Bullet point 1" -m "- Bullet point 2"

# 4. Push to remote
git push origin main
```

---

## 3. Academic Mentor Daily Briefing Template

Save to `docs/daily_reports/YYYY-MM-DD_report.md` and format as:

```markdown
# Báo Cáo Tiến Độ Hàng Ngày - Dự Án In-Course Agentic RAG Copilot
**Ngày:** YYYY-MM-DD | **Tuần:** WX | **Sinh viên thực hiện:** [Tên sinh viên]

### 1. 🎯 Mục tiêu trong ngày (Daily Objective)
- ...

### 2. 🚀 Kết quả đã hoàn thành & Mã nguồn (Deliverables & Commits)
- ...

### 3. 🛠️ Khó khăn kỹ thuật & Giải pháp (Technical Challenges & Mitigations)
- ...

### 4. 📊 Kiểm chứng & Đo lường (Verification & Metrics)
- ...

### 5. 📅 Kế hoạch ngày tiếp theo (Next Day Plan)
- ...
```

---

## 4. Session Cadence & Student Theory Learning Protocol

### A. Session Kickoff Protocol (Bắt đầu phiên làm việc):
Khi sinh viên hỏi: *"Hôm nay làm gì tiếp theo?"* hoặc các câu tương tự:
1. Đọc báo cáo ngày gần nhất trong `docs/daily_reports/` để xác định các việc còn dang dở.
2. Kiểm tra `git status` xem có file nào đang modified/untracked.
3. Xuất ra kế hoạch làm việc gồm:
   - 2–3 mục tiêu cốt lõi của ngày (theo roadmap).
   - Đường dẫn file mã nguồn cụ thể cần tạo/sửa.
   - Kỹ năng (Skill) liên quan sẽ kích hoạt.
   - Các câu lệnh PowerShell sẵn sàng chạy.

### B. Session Wrap-up Protocol (Kết thúc phiên làm việc):
Mỗi khi kết thúc phiên và chuẩn bị đẩy code lên GitHub, thực hiện danh sách kiểm tra sau:
1. [ ] **Quét Đối chiếu Chéo Toàn diện (Holistic Session Wrap-up Double-Check):**
   - 🚨 **Rà soát Lỗi Thuật Toán & Logic Toán Học (QUAN TRỌNG NHẤT - TOP PRIORITY):** Kiểm tra từng hàm toán học ($\sigma(z)$, RRF, Min-Max), nguy cơ tràn số mũ, triệt tiêu bẫy điều kiện if-else làm méo mó phân phối xác suất, kiểm tra các ngưỡng phân tầng và cơ chế fallback.
   - Rà soát tính toàn vẹn dữ liệu Vector DB trên Qdrant Cloud (chuẩn tiền tố `passage: ` cho E5, số lượng point chính xác, không lọt token âm học rác).
   - Kiểm tra khớp nối Schema Pydantic giữa Ingestion, `app/schemas/` và `app/services/` (không rơi rụng `context_code`, `code_language`, `confidence_score`, `is_approximate`).
   - Kiểm tra tính đồng bộ cấu hình môi trường (`.env` vs `.env.example` vs `app/config.py`).
   - Kiểm tra tính trung thực, No Hallucination, không báo cáo trước những gì chưa hoàn thành.
2. [ ] Rà soát `git status`, đảm bảo không commit `.env`, secret tokens hoặc file video nặng `*.mp4`.
3. [ ] Tạo Báo cáo Tiến độ Mentor: `docs/daily_reports/YYYY-MM-DD_report.md`.
4. [ ] **Tạo Tài liệu Học tập Lý thuyết Chuyên sâu cho Sinh viên:** `docs/theory_learning/YYYY-MM-DD_theory.md`.
   - Tổng hợp và giải thích chuyên sâu toàn bộ lý thuyết, thuật toán, công thức toán học và kiến trúc xuất hiện trong phiên.
   - Cung cấp bộ câu hỏi phản biện & gợi ý trả lời bảo vệ đồ án trước hội đồng.
5. [ ] Chạy Git add, commit chuẩn Conventional Commits và push lên `origin/main`.
