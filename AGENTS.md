# In-Course Agentic RAG Copilot - Architectural Rules & Guidelines

## 1. Project Overview & Mission
- **System:** Enterprise In-Course Agentic RAG Copilot integrated into a full-stack programming learning website.
- **Pedagogical Core:** Socratic Method (explain errors, ask guiding questions, strictly refuse to write full solution code for students).
- **Video Sync Core:** Extract video timestamps `<timestamp sec="145">02:25</timestamp>` to drive frontend video player `player.seekTo(sec)`.

- **Author Invariant:** Sinh viên thực hiện: Trần Thành Nghĩa (MSSV: `23DH112252`), Trường Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT). Repository: `https://github.com/ThanhNghiaa-hehe/In-Course_Agentic_RAG_Copilot`. Tuyệt đối không thay đổi sang họ khác.

## 2. Technical Stack & Standards
- **Python Environment:** Python 3.11 inside `.venv`.
- **Backend:** FastAPI (asyncio), Pydantic v2, Server-Sent Events (SSE).
- **Vector DB:** Qdrant with dual Named Vectors (`dense`: 1024-dim Cosine, `sparse`: DotProduct for BM25).
- **Embedding & Sparse Engine:** `fastembed` with `intfloat/multilingual-e5-large` (1024-dim) and `Qdrant/bm25` (unified single stack, no TEI dependency).
- **E5 Asymmetric Prefix Standard:** Bắt buộc thêm `passage: ` khi index tài liệu/code và `query: ` khi truy vấn tìm kiếm để tối ưu hóa không gian vector cosine.
- **Re-ranking & Normalization:** Cross-encoder with **Logistic Sigmoid Normalization** $\sigma(z) = \frac{1}{1 + e^{-z}}$. Triết lý thiết kế **Recall-First** với ngưỡng lọc $\ge 0.35$ kết hợp Calibrated Sigmoid / Min-Max Normalization để loại bỏ nhiễu từ câu hỏi ngắn.
- **Speech-to-Text & Lexicon Biasing:** `faster-whisper` with automatic domain **`hotwords`** (C++, Java, Python keywords) maintained across every window, tuned Silero VAD (`threshold=0.35`, `speech_pad_ms=400`, `condition_on_previous_text=False`), and CPU fallback if `cublas64_12.dll` is missing.
- **Context Assembly:** U-shaped layout `[Top 1, Top 3, Top 2]` to eliminate Stanford's "Lost-in-the-Middle" degradation.
- **Pre-filtering Rule:** In-HNSW dynamic single-call pre-filtering (`course_id == current_course_id AND lesson_seq <= current_lesson_seq`). Never hardcode fixed lesson sequences.
- **Anti-Robotic Socratic Synthesizer:** Single-pass prompt fusion inside the primary Socratic LLM call to distill raw colloquial transcripts into warm, natural 1-on-1 mentoring with zero additional API cost.
- **Session & State Persistence:** Redis sliding window (4–6 turns) + LangGraph Checkpointer (no separate Postgres needed).
- **Zero Foreign Superpower Policy:** Từ chối các plugin superpower ngoại lai không rõ nguồn gốc; chỉ sử dụng bespoke custom skills may đo trong thư mục `.agents/skills/`.

## 3. Production Conventions
- Always write type annotations (`typing`) and Pydantic schemas.
- Do NOT perform raw character chunking on code; always use AST ranh giới hàm/class via `tree-sitter`.
- Ensure all text is normalized to Unicode NFC before vectorizing.
- Never write full solutions in Socratic prompts.
- Qdrant Cloud Client: Always set `timeout=60.0` for international latency resilience.
- **Windows CLI & Terminal Output:** Avoid double-width multi-byte emojis (🎬, 📌, 📝) in terminal output logs to prevent PowerShell cursor drift and buffer overwrites. Always wrap lines with textwrap (width <= 75) and enforce flush=True.
- **Interactive Command Protocol:** Always provide clean, ready-to-run PowerShell commands and explain their purpose before execution, prioritizing user-controlled terminal execution.

## 4. Enterprise Git & Daily Delivery Cadence
- **Commit Frequency:** Atomic commits daily. Never accumulate multiple days into a single huge commit.
- **Conventional Commits Standard:** Follow strict prefixes:
  - `feat:` New feature or pipeline stage (e.g., `feat(ingest): add tech canonicalizer and subfolder splitting`)
  - `fix:` Bug fix or resilience patch (e.g., `fix(whisper): add CPU fallback for missing cublas DLL`)
  - `docs:` Documentation or report updates (e.g., `docs(daily): add 2026-09-06 mentor progress summary`)
  - `refactor:` Code refactoring without changing functionality
  - `test:` Search or pipeline verification tests
  - `chore:` Dependency, gitignore or config updates
- **Secret & Data Hygiene:** Always inspect `git status` before commit. NEVER commit `.env`, secret tokens, or raw video media files (`*.mp4`).

## 5. Academic Mentor Daily Briefing Mandate
- At the end of each working session/day, generate a structured Daily Summary report at `docs/daily_reports/YYYY-MM-DD_report.md`.
- Provide a concise, copy-ready summary formatted for sending to the Academic Mentor/Instructor via email or chat.

## 6. Session Kickoff & Student Theory Learning Protocol
- **Kickoff Protocol:** Khi sinh viên hỏi *"hôm nay làm gì tiếp theo"* hoặc câu tương tự, AI phải ngay lập tức rà soát `docs/daily_reports/` gần nhất và tiến trình hiện tại để xuất ra danh sách ưu tiên gồm 2–3 đầu việc cụ thể, link file trực tiếp, kỹ năng liên quan và lệnh PowerShell sẵn sàng chạy.
- **Student Theory Document Mandate:** Mỗi khi kết thúc một phiên làm việc bằng việc đẩy code lên GitHub, AI **BẮT BUỘC phải tạo thêm một tài liệu học tập lý thuyết chuyên sâu tại `docs/theory_learning/YYYY-MM-DD_theory.md`**. Tài liệu này giải thích chi tiết toàn bộ kiến thức nền tảng, công thức toán học, nguyên lý thuật toán và bộ câu hỏi phản biện bảo vệ đồ án của phiên đó (đảm bảo tính chính xác 100%, không suy đoán - No Hallucination).

