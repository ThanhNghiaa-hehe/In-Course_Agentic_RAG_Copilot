# Milestone History Archive (Chặng 1–7)

> Tài liệu lưu trữ nhật ký các chặng hoàn thành trước đó (được trích xuất từ `AGENTS.md` §6 để giữ `AGENTS.md` dưới trần 24 KB).

1. **Ưu tiên 1 (Hoàn thành 100%):** Tối ưu hóa và làm sạch Ground-Truth Golden Dataset v2.1 (Data-Centric AI: loại bỏ Label Noise, tích hợp 10 kịch bản kiểm thử an ninh, thiết lập điểm chuẩn Baseline 85.50%).
2. **Chặng 1 (Hoàn thành 100% - Router 98.00%):** Triển khai Module Cascade NLI Router (Stage 1 LinearSVC Fast-Path 2.06ms -> Stage 2 Cross-Encoder NLI Arbiter CPU) kết hợp Security Input Guardrail (OWASP LLM01 Gate 1.8ms) và Tree-sitter Socratic Output Guardrail.
3. **Chặng 2 (Hoàn thành 100% - Router 99.5%, CRAG 97.5%, TS 97.5%):**
   - Hoàn tất tối ưu hóa Lõi Truy xuất & Hiệu năng Toàn diện (Retrieval, CRAG, Timestamps & Balanced Modality Assembly) với 0.0% Hallucination.
   - Tích hợp 2 kỹ thuật kiến trúc dài hạn: (a) *Selective Dual-Stream Query Intent Decomposition* cho ẩn dụ đời sống (`BENCH-141`, `147`); (b) *Data-Centric Code AST Enrichment* dưới bất đẳng thức bảo vệ Pareto ($S_{\text{future}} \ge 0.52, \text{Margin} \ge 0.25$).
4. **Chặng 3 (Hoàn thành 100%):** Thiết lập **Interactive Chatbot Playground** (`/playground`) chuẩn EdTech SaaS 3 cột (Syllabus 83 bài học, YouTube Video Player Playlist 28Tech mở rộng toàn phần, Trợ giảng Socratic AI với Thought Drawer và `<timestamp>` click-to-seek).
5. **Chặng 4.1 (Hoàn thành 100% - TTFT < 1.0s, Token Input giảm > 75%):** Lean Structured Zero-Shot Prompting, Context Distillation & Pruning (<= 800 tokens), Curriculum Navigation Intent Dispatcher (< 20ms trên `lessons_manifest.json`), Dead Code Cleanup & Zero-Regex NLI Rescue ($P_{\text{chit}} < 0.75$), Playground Telemetry Debug Inspector.
6. **Chặng 4.2 (Hoàn thành 100% - OOD 100/100):** Stateful Sliding Window Memory Checkpointer trong `app/services/chat_graph.py` (4 Discrete Nodes, `MemorySaver`, $k=5$ turns, Conversation Summarizer); OOD Stress-Test Benchmark đạt Router 100%, CRAG 76%, Latency giảm 35% (P90 `61.2s -> 24.5s`).
7. **Chặng 5 (Hoàn thành 100% - G-Eval 95.0%–96.9%):** Compiler Error Semantic Bridge (HyDE), Tree-sitter AST Socratic Scaffolding Guardrail, Data-Centric AI Label Audit (`OOD-004` -> `out_of_lesson`).
8. **Chặng 6 (Tối ưu hóa độ trễ):**
   - M-04 Scatter-Gather Async Parallel Future Probing (`asyncio.gather()` trong `retrieval.py`).
   - M-05a Context Truncation $O(L^2)$ & Candidate Pruning (`FUTURE_PROBE_LIMIT=6`).
   - M-05b Non-blocking Asyncio Thread Offloading (`asyncio.to_thread`).
   - M-05c Dynamic INT8 PTQ Reranker (được thử nghiệm, hiệu chỉnh lại với Calibration/RTX 2050 VRAM split).
   - M-06 Pre-rerank Window Deduplication (Temporal NMS) & Co-location.
9. **Chặng 7 (Quy hoạch Đấu nối Full-Stack):** Đấu nối giao diện React 19 `CourseContent.jsx` (`fe-codelearning`) và Spring Boot/MongoDB (`nghia`).
