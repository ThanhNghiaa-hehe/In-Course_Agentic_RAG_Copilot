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

### Tuần 3: Socratic Agentic Copilot & Streaming SSE Backend
- **Day 15:** FastAPI architecture, Pydantic v2 schemas, and dependency injection.
- **Day 16:** Intent Classifier Router (Chitchat fast-path vs RAG tool call).
- **Day 17:** Socratic Prompt Engine & Strict Code Guardrail (refusal to write full solution).
- **Day 18:** Automated video timestamp extraction (`<timestamp sec="xxx">mm:ss</timestamp>`).
- **Day 19:** Server-Sent Events (SSE) streaming endpoint (`/api/v1/chat/stream`).
- **Day 20:** Redis sliding window session & LangGraph state checkpointer.
- **Day 21:** Tuần 3 Review, API testing, and mentor checkpoint report.

### Tuần 4: Evaluation, Frontend Integration & Final Defense Preparation
- **Day 22:** RAG Triad automated evaluation (TruLens/Ragas: Faithfulness, Answer Relevance).
- **Day 23:** Frontend React Hook contract & Video Player sync (`player.seekTo(sec)`).
- **Day 24:** End-to-end integration testing (Docker Compose, Redis, FastAPI).
- **Day 25:** System performance profiling, load testing, and caching optimizations.
- **Day 26:** Comprehensive project documentation, API docs (Swagger/OpenAPI).
- **Day 27:** Final thesis report draft & slide deck for Academic Mentor review.
- **Day 28:** Project defense rehearsal & final production release.

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
1. [ ] Rà soát `git status`, đảm bảo không commit `.env`, secret tokens hoặc file video nặng `*.mp4`.
2. [ ] Tạo Báo cáo Tiến độ Mentor: `docs/daily_reports/YYYY-MM-DD_report.md`.
3. [ ] **Tạo Tài liệu Học tập Lý thuyết Chuyên sâu cho Sinh viên:** `docs/theory_learning/YYYY-MM-DD_theory.md`.
   - Tổng hợp và giải thích chuyên sâu toàn bộ lý thuyết, thuật toán, công thức toán học và kiến trúc xuất hiện trong phiên.
   - Cung cấp bộ câu hỏi phản biện & gợi ý trả lời bảo vệ đồ án trước hội đồng.
4. [ ] Chạy Git add, commit chuẩn Conventional Commits và push lên `origin/main`.
