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

## 7. Local AI Serving & Windows Engineering Protocols
- **Explicit IPv4 Standard:** Luôn sử dụng `http://127.0.0.1:<PORT>` thay vì `localhost` trong toàn bộ cấu hình backend (`app/config.py`, `.env`) để ngăn ngừa triệt để lỗi phân giải chậm/timeout do IPv6 `[::1]` trên Windows.
- **Hugging Face Container Extract Standard:** Khi trích xuất file model GGUF từ Docker/WSL sang Windows, TUYỆT ĐỐI KHÔNG copy từ `snapshots/` (chỉ là Linux symlink 1.5KB); bắt buộc phải copy trực tiếp từ `blobs/<hash>` thật sự.
- **PowerShell CLI Hygiene:**
  - Không bao giờ dùng `Out-File -Encoding utf8` khi tạo file cấu hình cho Golang/Ollama (tránh lỗi UTF-8 BOM `\ufeff`). Phải dùng `Set-Content -Encoding Ascii`.
  - Không cung cấp lệnh `curl.exe` với chuỗi JSON lồng ngoặc kép `\"` tiếng Việt. Luôn cung cấp script test Python (`httpx`) hoặc `Invoke-RestMethod` để tránh vỡ chuỗi Punycode.
- **Anti-Hallucination Socratic Prompt Guardrail:**
  - Không đưa số giây/mốc thời gian cụ thể (như `145`, `02:25`) vào câu ví dụ của System Prompt để tránh việc các mô hình LLM nhỏ (3B) sao chép mù quáng.
  - Khi RAG trả về `0 chunks` (nội dung chưa học trong phạm vi bài hiện tại), hệ thống phải kích hoạt prompt rẽ nhánh cảnh báo tiêu cực: TUYỆT ĐỐI CẤM sinh thẻ `<timestamp>`, thông báo cho sinh viên biết bài học hiện tại chưa giảng dạy chủ đề này và chỉ giải thích lý thuyết thuần túy.
- **Uvicorn Development Standard:** Luôn khởi chạy uvicorn với cờ `--reload` để đảm bảo code chỉnh sửa lập tức được cập nhật vào RAM.

## 8. Direct Communication & Zero-Hallucination Answering Protocols
- **Direct Answer First (Trả lời trực diện trước tiên):** Khi người dùng đặt câu hỏi kỹ thuật, kiến trúc hoặc xác nhận phạm vi (Yes/No, có phải/không phải, tại sao), AI BẮT BUỘC phải đưa ra câu trả lời trực tiếp ngay ở câu đầu tiên (Đúng/Sai/Có/Không/Kết luận trọng tâm). Tuyệt đối không vòng vo, không lan man lý thuyết giáo trình khi không được yêu cầu.
- **Strict Scope & Conciseness (Đúng trọng tâm, không lan man):** Chỉ trả lời đúng câu hỏi người dùng đưa ra. Không tự ý mở rộng phân tích các chủ đề ngoài lề trừ khi người dùng yêu cầu "hãy phân tích chi tiết" hoặc "giải thích sâu hơn".
- **Codebase Cross-Verification Mandate (Đối chiếu mã nguồn tuyệt đối):** Tuyệt đối KHÔNG dựa vào suy đoán hoặc dữ liệu mẫu cũ về tên mô hình, thuật toán và tham số cấu hình. Mọi phát biểu kỹ thuật phải đối chiếu trực tiếp từ `app/config.py`, `.env` và các tệp services liên quan (ví dụ: mô hình Re-ranker là `jinaai/jina-reranker-v2-base-multilingual`, tuyệt đối không nhầm sang BGE).

## 9. Anti-Quick-Fix, Deep Research & Strict Code Integrity Mandate
- **Cấm Tuyệt Đối Phương Pháp Vá Tạm (Zero Quick-Fix Policy):**
  - Tuyệt đối KHÔNG đề xuất hoặc áp dụng các giải pháp "chữa cháy tình huống" (như hardcode tăng/giảm ngưỡng threshold cục bộ, viết thêm regex thủ công bắt câu chữ, hoặc cắt bớt các tầng phòng thủ kiến trúc vì lý do tiện tay).
  - Mọi giải pháp cho bài toán RAG, Router, Context Misalignment hoặc LLM Degeneration phải được xây dựng dựa trên các chuẩn mực kiến trúc đã được thẩm định từ tài liệu học thuật và công nghiệp chính thống (ví dụ: *CRAG - Corrective RAG (Yan et al., 2024)*, *Semantic Router (Aurelio AI)*, *Decoding Constraints (Holtzman et al., 2019)*).
- **Quy Trình Nghiên Cứu Thấu Đáo & Zero-Hallucination (Deep Research Mandate):**
  - Khi đối mặt với lỗi kiến trúc hoặc bài toán mới, AI BẮT BUỘC phải thực hiện tra cứu tài liệu chuyên sâu, đối chiếu các paper và tài liệu chính thống (LangChain, LlamaIndex, vLLM, Meta AI), giải thích rõ cơ chế khoa học, không phỏng đoán, không giải thích nửa vời.
- **Kỷ Luật Bất Khả Xâm Phạm Mã Nguồn Khi Yêu Cầu Test (Strict Code Integrity):**
  - Mỗi khi người dùng yêu cầu lệnh test hoặc test case: AI TUYỆT ĐỐI KHÔNG được tự ý chỉnh sửa bất kỳ file mã nguồn, file script hay file HTML nào.
  - AI chỉ cung cấp lệnh kiểm thử và giải thích kết quả mong đợi.
  - Mọi đề xuất cải tiến hoặc chỉnh sửa file phát sinh BẮT BUỘC phải trình bày phương án rõ ràng và xin ý kiến phê duyệt từ người dùng; chỉ khi người dùng bấm đồng ý mới được phép chỉnh sửa.

## 10. Evaluation-Driven Development (EDD) & Benchmark-First Mandate
- **Nguyên Tắc Benchmark-First (Thước Đo Đi Trước, Tối Ưu Đi Sau):**
  - Tuyệt đối KHÔNG tiến hành chỉnh sửa hàng loạt prompt, router threshold hay thuật toán retrieval chỉ vì 1–2 ca test thử nghiệm thủ công đơn lẻ.
  - Mọi hoạt động cải tiến, nâng cấp hệ thống (đặc biệt là bước chuyển dịch từ Phase 1 sang Phase 2 - Code-to-Video Metadata Binding) BẮT BUỘC phải dựa trên kết quả đo lường từ **Bộ Benchmark Tự Động (Stage 11)**.
- **Tiêu Chuẩn Bộ Benchmark Định Lượng (Golden Dataset Standard):**
  - Thiết lập Golden Dataset tối thiểu 40–50 kịch bản thử nghiệm bao phủ 4 tầng:
    1. *In-Scope Technical:* Khái niệm lập trình, bộ nhớ, cú pháp thuộc bài học hiện tại.
    2. *Out-of-Lesson Scope:* Khái niệm thuộc bài tương lai (kiểm tra rào chắn rò rỉ kiến thức).
    3. *Adversarial Hybrid Queries:* Câu hỏi lập trình lồng ghép nội dung đời sống phi logic (nhậu nhẹt, nấu ăn, du lịch,...).
    4. *Chit-Chat / Out-of-Domain:* Lời chào hỏi, cảm ơn hoặc hoàn toàn ngoài lề.
  - Đo lường định lượng tự động 4 chỉ số cốt lõi:
    - **Router & Grader Accuracy:** Tỷ lệ phân luồng và thẩm định chunk chính xác.
    - **Timestamp Precision & Recall:** Sai số $|\Delta t| \le 15$s khi có video, và tỷ lệ 0 timestamp khi out-of-scope/gap (chống ảo giác).
    - **Faithfulness (RAG Triad):** Độ trung thực của câu trả lời dựa trên ngữ cảnh thực tế, không sinh liên hệ phi lý.
    - **Latency (TTFT & Total Duration):** Tốc độ phản hồi thời gian thực qua luồng SSE.
- **Quy Tắc Chống Thụt Lùi (Regression Prevention):**
  - Một thay đổi kiến trúc chỉ được phép phê duyệt và commit vào repository khi điểm Benchmark tổng thể tăng lên hoặc giữ vững, không làm sụt giảm độ chính xác của các bài test chuẩn.


