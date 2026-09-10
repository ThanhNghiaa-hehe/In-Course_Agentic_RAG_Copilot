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
- **Re-ranking & Normalization:** Cross-encoder with **Logistic Sigmoid Normalization** $\sigma(z) = \frac{1}{1 + e^{-z}}$. Triết lý thiết kế **Recall-First** kết hợp Calibrated Sigmoid / Min-Max Normalization để loại bỏ nhiễu từ câu hỏi ngắn.
- **Multimodal Thresholding & Fallback Policy (2-Phase Roadmap):**
  - **Phase 1 (Current - Under 50% Progress):** Áp dụng *Modality-Aware Thresholding*:
    - `CODE_SCORE_THRESHOLD = 0.35` (nghiêm ngặt cho Code AST nhằm đảm bảo tính đúng đắn cú pháp).
    - `VIDEO_SCORE_THRESHOLD = 0.22` (linh hoạt cho Video Transcript nhằm dung hòa văn nói tự nhiên và nhiễu âm học Whisper).
    - *Best-Effort In-Course Fallback:* Nếu Code AST $\ge 0.60$ nhưng không có video nào $\ge 0.22$, hệ thống tự động chọn 1 video chunk có điểm cao nhất thuộc cùng `lesson_seq` đạt $\ge 0.15$ (gắn nhãn `is_approximate: true`) để luôn bảo toàn thẻ `<timestamp>` cho frontend.
  - **Phase 2 (Halfway Milestone - Over 50% Progress):** Chuyển dịch sang *Code-to-Video Metadata Binding*:
    - Gắn mốc `approx_video_sec` vào payload của AST Code Chunk trong khâu Ingestion.
    - **Mandatory AI Reminder:** AI có nghĩa vụ chủ động nhắc nhở sinh viên kích hoạt Phase 2 ngay khi hoàn tất tầng Agentic Orchestration / Chat UI (bắt đầu Tuần 3).
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
- **Interactive Command Protocol:** Tuyệt đối KHÔNG tự ý chạy lệnh test/tìm kiếm khi chưa có sự yêu cầu rõ ràng từ người dùng. Khi người dùng hỏi lệnh test hoặc cách chạy, AI luôn cung cấp các khối lệnh PowerShell chuẩn, sạch, giải thích mục đích và kết quả mong đợi để người dùng tự copy chạy trên terminal của họ.

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
- **Session Wrap-up Holistic Double-Check Mandate:** Trước khi kết thúc bất kỳ phiên làm việc nào và trước khi viết báo cáo hàng ngày, AI **BẮT BUỘC phải thực hiện một lượt rà soát đối chiếu chéo toàn diện (Holistic End-to-End Audit)** bao gồm 6 trụ cột theo thứ tự ưu tiên:
  1. 🚨 **Lỗi Thuật Toán & Logic Toán Học (QUAN TRỌNG NHẤT - TOP PRIORITY):**
     - Rà soát từng công thức toán học và hàm chuẩn hóa ($\sigma(z)$, RRF, Min-Max, Cosine).
     - Kiểm tra triệt để nguy cơ tràn số mũ (overflow/underflow), tránh các bẫy điều kiện if-else làm sai lệch bản chất phân phối của mô hình (ví dụ: bẫy ternary condition trên raw logits).
     - Kiểm tra tính đúng đắn của các điều kiện biên (edge cases), ngưỡng sàn an toàn và cơ chế fallback.
  2. **Dữ liệu & Vector DB:** Kiểm tra tính toàn vẹn của dữ liệu trên Qdrant (chuẩn tiền tố `passage: ` cho E5, số lượng point, không chứa token rác âm học).
  3. **Khớp nối Schema & Service:** Đối chiếu từng trường dữ liệu giữa tầng nạp (Ingestion), mô hình Pydantic (`app/schemas/`), và dịch vụ truy xuất (`app/services/`). Tuyệt đối không để rơi rụng các trường quan trọng (như `context_code`, `code_language`, `confidence_score`, `is_approximate`).
  4. **Cấu hình Môi trường:** Kiểm tra tính đồng nhất giữa `.env`, `.env.example`, và `app/config.py`.
  5. **Hồ sơ Học thuật:** Đảm bảo có đầy đủ cả Daily Report (`docs/daily_reports/YYYY-MM-DD_report.md`) VÀ tài liệu học tập lý thuyết (`docs/theory_learning/YYYY-MM-DD_theory.md`) tương ứng cho mỗi phiên commit code lên GitHub.
  6. **Tính trung thực:** Báo cáo đúng thực tế triển khai, tuyệt đối không suy đoán hoặc khẳng định những hạng mục chưa hoàn thành (No Hallucination).


