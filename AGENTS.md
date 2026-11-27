# In-Course Agentic RAG Copilot - Core Rules & Skill Index

## 1. Project Overview, Mission & Author Invariant
- **System:** Enterprise In-Course Agentic RAG Copilot integrated into a full-stack C++/OOP programming learning platform.
- **Pedagogical Core:** Socratic Method (explain concepts/errors, provide at most short pseudocode or 1–3 line skeleton with `// TODO`, strictly refuse to write full runnable `#include` + `int main()` solutions, and end domain turns with 1 concrete guiding question `?`).
- **Video Sync Core:** Extract verified video timestamps `<timestamp sec="145">02:25</timestamp>` to drive frontend `player.seekTo(sec)` (and `playVideoAt` for cross-lesson sync), with zero fabricated timestamps.
- **Author Invariant:** Sinh viên thực hiện: **Trần Thành Nghĩa** (MSSV: `23DH112252`), Trường Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT). Repository: `https://github.com/ThanhNghiaa-hehe/In-Course_Agentic_RAG_Copilot`. Tuyệt đối không thay đổi sang họ khác.

## 2. Core Technical Stack Snapshot
- **Runtime:** Python 3.11 (`.venv`), FastAPI (asyncio), Pydantic v2, Server-Sent Events (SSE), `uvicorn --reload`.
- **Vector & Embedding:** Qdrant Cloud (`timeout=60.0`) with Dual Named Vectors (`dense`: 1024-dim Cosine `intfloat/multilingual-e5-large` with mandatory `passage: ` / `query: ` asymmetric prefix; `sparse`: DotProduct `Qdrant/bm25` via `fastembed`). Keep `onnxruntime-gpu==1.23.2` only (Dense E5 on GPU; Jina INT8 `data/models/jina-reranker-v2-int8` on CPU).
- **Routing & Orchestration:** Cascade Fast-Path SLM (`ONNX INT8`) + `mDeBERTa-v3` NLI Arbiter, Contrastive E5 Vector Security Guardrail, LangGraph `StateGraph` (4 nodes + `MemorySaver`, `k=5`, `<= 2400` chars).
- **Parsing & Speech:** `tree-sitter` AST chunking/scaffolding (zero raw character slicing on code); `faster-whisper` + Silero VAD + AST canonicalizer; Qwen2.5-Coder-7B-Instruct (+ Socratic LoRA) on Kaggle GPU.

## 3. Always-On Engineering, Integrity & Pedagogical Guardrails
- **Zero Quick-Fix & Zero-Regex Core (`app/`):** Tuyệt đối KHÔNG vá tạm bằng regex bắt từ khóa/entity, hardcode tên/số bài học, hay chỉnh ngưỡng threshold toàn cục theo từng ca lẻ. Thư mục `app/` duy trì `0% import re` (chỉ dùng HTMLParser event-driven, Unicode range checks, Tree-sitter AST, và `markdown-it-py`).
- **Zero-Reinventing-the-Wheel & Zero Foreign Superpower:** Ưu tiên thư viện chuẩn (`scikit-learn`, `onnxruntime`, `fastembed`, `tree-sitter`, `qdrant-client`, `langgraph`); chỉ sử dụng bespoke skills trong `.agents/skills/`.
- **Data/Code Separation:** Tuyệt đối KHÔNG hardcode từ điển/bảng ánh xạ metadata (như glossary, AST ground-truth map) vào file `.py`; luôn lưu dưới `data/`.
- **Data-Inspected Verification & Anti-Surrogate Honesty:** Không bao giờ kết luận dữ liệu sạch hay check đạt chỉ từ Exit Code 0 — phải kiểm tra trực tiếp file/chunk/output thực tế. Cấm bịa/ước lượng số liệu RAGAS/G-Eval (ghi `null`/`--` khi không chạy LLM).
- **Benchmark Integrity & Zero Test-Set Snooping:** Không copy câu hỏi held-out vào tập train/manifest; mọi tối ưu hóa kiến trúc bắt buộc chạy chu trình đối chiếu Pre/Post Stage 11 (giữ hoặc tăng chất lượng, không hồi quy).
- **Direct Communication & Pre-Action Discipline:**
  - *Direct Answer First:* Trả lời trực diện kết luận ngay câu đầu, đúng trọng tâm, đối chiếu trực tiếp `app/config.py`/`.env`/code (không đoán theo trí nhớ).
  - *Runtime Data State Invariant:* Không suy đoán DB đã có dữ liệu chỉ từ Schema.
  - *Pre-Action Audit & Scratch Guardrail:* Rà soát User Rules & Skills trước khi tạo/sửa file hay chạy lệnh; không tự ý tạo/sửa/xóa `scratch/` khi chưa được đồng ý; khi người dùng hỏi lệnh test, không sửa mã nguồn âm thầm.
- **Production Conventions & Git Hygiene:**
  - Strict `typing` + Pydantic v2; chuẩn hóa Unicode **NFC** trước khi vector hóa; không chunk code bằng ký tự thô.
  - **Atomic Conventional Commits** (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`); cấm gom bừa `git add .`. Kiểm tra `git status` trước commit; KHÔNG commit `.env`, secret tokens, `*.mp4`, hoặc file tạm `~$*.docx`.
  - Khi kết thúc phiên/ngày commit code: lập **Daily Report** (`docs/daily_reports/YYYY-MM-DD_report.md`) và **Theory Learning Doc** (`docs/theory_learning/YYYY-MM-DD_theory.md`) sau khi rà soát chéo thuật toán toán học, Qdrant parity, Schema/Service alignment và config `.env`.

## 4. On-Demand Skill Map (Progressive Disclosure)
To keep context compact (`< 24 KB` rule cap), domain specifications live in `.agents/skills/` and MUST be read before working in their scope:

| Domain / Task | Skill (`SKILL.md`) | Scope & Key Contents |
| :--- | :--- | :--- |
| **RAG, CRAG, Router, LangGraph, Socratic AST** | `rag-core-architecture` | Pareto ICLR 2025, CRAG (Yan et al.), NLI rescues, FSM Timestamp Whitelist $\mathcal{W}$, Contrastive Vector Guardrail, Polyglot Persistence, `M-04..M-08`. |
| **Benchmarks, RAGAS, Calibration & Data Integrity** | `rag-diagnostics-eval` | 20 failure patterns (P01–P20), EDD, P13 Label Audit, ECE/Brier calibration, Data Decontamination ($J < 0.70$), RAGAS Pre-filtering. |
| **RTX 2050 VRAM, Kaggle LLM, Windows Serving** | `rag-runtime-ops` | `onnxruntime-gpu` split, Ngrok/Cloudflare TTFT profiling, Windows IPv4/PowerShell hygiene, 8K token budget, Whisper/VAD, Swarm discipline. |
| **UI, Playground 3-Column Canvas & Video Sync** | `ui-ux-pro-max` | Studio 3-column layout (83 lessons + Flex YouTube + Thought Drawer), Light EdTech / Dark Observability palettes, Zero Auto-Seek, Lucide SVG. |
| **Roadmap, EduBot Backlog (E1–E5) & Daily Wrap** | `daily-workflow` | 4-week agile roadmap, Milestone archive, **Command-Gated EduBot SOTA Backlog (E1–E5)**, Git commits & Academic Mentor templates. |
| **C++/Java Code AST Chunking** | `ast-code-chunker` | Tree-sitter function/class boundaries, `approx_video_sec` metadata binding & Qdrant indexing. |
| **ASR Canonicalization & Qdrant Reclean** | `whisper-canonicalizer-tester` | `scripts/canonicalize_transcripts_ast.py` 2-pass Gemini + Supervisor, phonetics, chapter refresh, Qdrant parity. |
| **Qdrant Cluster Inspection** | `qdrant-hybrid-inspector` | Dual-vector sanity check, payload schema contract, HNSW auditing, latency benchmarks. |
| **Engineering Rigor & E2E Spec** | `pstack` | Unified `specs/<slug>/spec.md`, Cross-Layer Conflict Matrix, quota checks (`antigravity-pool`), Swarm review. |
| **Full-Stack Integration** | `fullstack-rag-integration` | `fe-codelearning` (React 19) & `nghia` BE (Spring/MongoDB) contracts. |
| **DBMS Final Project (Oracle 23ai)** | `oracle-23ai-rag-adapter` | Qdrant -> Oracle 23ai VECTOR migration, 3NF schema, PL/SQL, oral defense cheatsheet (Topic 22). |
| **Academic Word Manuscript** | `docx-paper-studio` | `.docx` OOXML editing, native OMML equations, 300-DPI figures, HJS formatting. |
