# Windows Serving, Speech & MLOps Budgeting Protocols

Tài liệu trích xuất từ `AGENTS.md` (§2, §7) theo cơ chế Progressive Disclosure cho kỹ năng `rag-runtime-ops`.

---

## 1. Windows Local AI Serving & CLI Hygiene (§7)
- **Explicit IPv4 Standard:** Luôn dùng `http://127.0.0.1:<PORT>` thay vì `localhost` trong `app/config.py`, `.env` để tránh chậm/timeout IPv6 `[::1]` trên Windows.
- **Hugging Face Container Extract Standard:** Khi copy model GGUF/weights từ Docker/WSL sang Windows, KHÔNG copy từ `snapshots/` (symlink 1.5 KB trên Linux); phải copy trực tiếp file thật từ `blobs/<hash>`.
- **PowerShell CLI Hygiene:**
  - Dùng `Set-Content -Encoding Ascii` (không dùng `Out-File -Encoding utf8` gây UTF-8 BOM `\ufeff` cho Golang/Ollama config).
  - Tránh `curl.exe` với chuỗi JSON tiếng Việt lồng `\"`; ưu tiên Python (`httpx`/`urllib`) hoặc `Invoke-RestMethod`.
  - PowerShell 5.1 không hỗ trợ `&&`: dùng `; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE };` khi nối lệnh phụ thuộc.
- **Uvicorn Development Standard:** Khởi chạy `uvicorn` với `--reload` khi dev; lưu ý tắt `uvicorn` trước khi chạy benchmark GPU RTX 2050 4GB hoặc truyền `--safe-cpu`.
- **Hardware Compatibility Invariant:** Tuyệt đối không đề xuất framework độc quyền hệ điều hành khác (như Apple MLX); mọi Encoder/Router mới phải chạy được qua ONNX Runtime hoặc PyTorch CUDA trên Windows 11 x86_64 trong trần `4 GB VRAM` (RTX 2050).

## 2. Remote GPU Inference (Kaggle + Tunnel) & MLOps Resource Budgeting
- **Remote GPU + Static Tunnel:** Chạy LLM 7B (`Qwen2.5-Coder-7B-Instruct` + LoRA [qwen25-coder-7b-socratic-lora](file:///D:/In_Course_Agentic_RAG_Copilot/data/models/qwen25-coder-7b-socratic-lora)) trên Kaggle GPU (`enable-prefix-caching`), nối qua Ngrok static domain hoặc `cloudflared` và đặt `LLM_BASE_URL` trong `.env`. Dùng anti-idle khi demo trực tiếp.
- **Resilience Khi LLM Remote Offline:** Backend FastAPI phải vận hành bình thường toàn bộ Fast-Path, Retrieval, CRAG Grader, Video Seek và AST Code Inspector ngay cả khi Kaggle GPU đang tắt để tiết kiệm quota 30h/tuần.
- **Context Window Budgeting ($8,192$ tokens trần vật lý):**
  - RAG context + System prompt chiếm $\approx 3,650$ tokens.
  - Khả dụng $\approx 3,368$ tokens cho lịch sử hội thoại -> giữ Sliding Window $k \in [4, 6]$ turns (8–12 messages, cắt $\le 2,400$ chars), vượt ngưỡng sẽ tóm tắt (`Conversation Summarizer`).
- **Speech-to-Text (`faster-whisper` + Silero VAD):** Duy trì domain `hotwords` qua mọi cửa sổ, `threshold=0.35`, `speech_pad_ms=400`, `condition_on_previous_text=False`, và fallback CPU tự động nếu thiếu `cublas64_12.dll`.
