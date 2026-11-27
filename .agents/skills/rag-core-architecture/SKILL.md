---
name: rag-core-architecture
description: >-
  Core RAG, CRAG (Yan et al.), Pareto Context Sufficiency (ICLR 2025), Cascade SLM+mDeBERTa NLI Router,
  LangGraph 4-Node StateGraph, FSM Timestamp Whitelist, Contrastive Vector Guardrail, Tree-sitter Socratic
  AST Sanitizer, and Polyglot Persistence invariants for In-Course Agentic RAG Copilot. Use when modifying
  app/services/, app/agent/, retrieval, CRAG, router, guardrails, or multi-turn orchestration.
---

# In-Course Agentic RAG Core Architecture & Mathematical Invariants

Tài liệu kỹ thuật lõi được trích xuất từ `AGENTS.md` (Progressive Disclosure) — bắt buộc đọc khi chỉnh sửa tầng retrieval, CRAG, router, guardrails, LangGraph orchestration hoặc SSE streaming.

---

## 1. Embedding, Retrieval & Score Normalization

- **Dual Stack (`fastembed`):** Dense `intfloat/multilingual-e5-large` (1024-dim Cosine) + Sparse `Qdrant/bm25` (DotProduct), kết hợp RRF.
- **E5 Asymmetric Prefix Standard:** Bắt buộc thêm `passage: ` khi index tài liệu/code và `query: ` khi truy vấn tìm kiếm.
- **In-HNSW Pre-filtering Rule:** Single-call pre-filtering (`course_id == current_course_id AND lesson_seq <= current_lesson_seq`). Cấm hardcode dãy bài cố định.
- **U-Shaped Context Assembly:** Sắp xếp `[Top 1, Top 3, Top 2]` để loại bỏ suy thoái *Lost-in-the-Middle* (Stanford/TACL).
- **Dynamic Min-Max RRF Scaling Invariant:** Cấm chia điểm RRF cho hằng số cứng (như `0.8333`); chuẩn hóa động trên tập ứng viên $\mathcal{C}$ của lượt truy vấn:
  $$S_{\text{RRF}}(d) = \frac{\text{RRF}(d) - \min_{c \in \mathcal{C}} \text{RRF}(c)}{\max_{c \in \mathcal{C}} \text{RRF}(c) - \min_{c \in \mathcal{C}} \text{RRF}(c) + \epsilon}$$
- **Length-Compensated Cross-Encoder Temperature Scaling (NeurIPS):** Chuẩn hóa Sigmoid bù chiều dài câu hỏi $|q|$ và nhiệt độ $\tau$:
  $$S(q, d) = \sigma\left( \frac{z(q, d) - \mu_z}{\tau \cdot \sqrt{\frac{\max(|q|, L_{\min})}{|q|_0}}} \right)$$
  (Triệt tiêu nén điểm câu ngắn 1–4 từ và thổi phồng câu hỏi đối nghịch dài 25–40 từ.)

---

## 2. CRAG (Yan et al., arXiv:2401.15884) & Pareto Context Sufficiency (ICLR 2025)

- **CRAG Attribution Standard:** Theo **Yan et al. (arXiv:2401.15884)** (3 trạng thái: `Correct` -> `grounded`, `Ambiguous`, `Incorrect` -> `out_of_lesson` / `coverage_gap`); không nhầm với benchmark Meta CRAG (KDD Cup 2024).
- **Relevance vs. Context Sufficiency (ICLR 2025):** Phân định rạch ròi độ liên quan ngữ nghĩa và độ đầy đủ sư phạm; câu nhắc lướt bài sau ở bài cũ tuyệt đối không được gán `grounded`.
- **Retrieval Hierarchy 4 Tầng (`app/services/retrieval.py`):**
  1. *Grounded cấp cao:* $\text{CRAG} \ge 0.40$ hoặc AST Grounding Anchor $\ge 0.35$ của bài hiện tại.
  2. *Thăm dò bài tương lai (`_probe_future_lessons`):* BẮT BUỘC chạy TRƯỚC Graceful Degradation với $S_{\text{future}} \ge 0.35$ và $\text{Margin} = S_{\text{future}} - \max(S_{\text{current}}) > 0.08$.
  3. *Graceful Degradation:* Chỉ kích hoạt khi bài tương lai không vượt trội và bài hiện tại đạt sàn $S_{\text{current}} \ge 0.20$.
  4. *Coverage Gap:* Khi cả hai đều không đạt chuẩn.
- **Modality-Aware Latency Gate Invariant:** Cấm dùng ngưỡng phẳng $0.22$ trên video transcript để Early Exit bỏ qua `_probe_future_lessons`. Chỉ Early Exit khi bài hiện tại có **Code AST Anchor $\ge 0.35$** HOẶC **Video Transcript $\ge 0.30$**. Trong dải lơ lửng $0.22 \le S < 0.30$ (video-only), bắt buộc thăm dò bài tương lai với $\text{Margin} \in [0.08, 0.10]$.
- **Pareto Context Sufficiency 3 Phân Tầng & Biên Độ Đơn Điệu:**
  - (a) $S_{\text{current}} < 0.22$: bài tương lai thống trị khi $S_{\text{future}} \ge 0.25, \text{Margin} \ge 0.12$.
  - (b) $0.22 \le S_{\text{current}} < 0.30$ (video-only): Code AST tương lai thống trị khi $S_{\text{future}} \ge 0.35, \text{Margin} \ge 0.10$; Video tương lai khi $S_{\text{future}} \ge 0.30, \text{Margin} \ge 0.08$.
  - (c) $S_{\text{current}} \ge 0.30$: bài tương lai phải vượt trội $S_{\text{future}} \ge 0.45, \text{Margin} \ge 0.12$ (hoặc $S_{\text{future}} \ge 0.52, \text{Margin} \ge 0.25$ cho Code AST).
  - **Strictly Monotonic Pareto Frontier:**
    $$\text{Margin}_{\text{req}}(S_{\text{current}}) = 0.08 + 0.20 \cdot \max\left(0, \frac{S_{\text{current}} - 0.20}{0.15}\right)$$
    Phân loại câu hỏi (cú pháp vs lý thuyết) dựa trên cấu trúc ranh giới AST thực tế, cấm regex `is_theory_query`.
- **Prerequisite Order Pareto Invariant v2.1:** Khi hỏi khái niệm tương lai, ưu tiên **bài tiên quyết có thứ tự nhỏ nhất ($\min L_{\text{seq}}$)** đạt $S \ge 0.30$; bài ứng dụng đến sau chỉ thay thế khi $S_{\text{late}} - S_{\text{early}} > 0.15$. Khi đang ở bài tiên quyết: câu hỏi lý thuyết giữ ngưỡng bảo chứng $S_{\text{current}} \ge 0.30$ (bài sau phải $S_{\text{future}} \ge 0.65, \text{Margin} \ge 0.25$ mới cướp quyền); câu hỏi cú pháp thiếu AST giữ $S_{\text{current}} \ge 0.35$.
- **Multimodal Thresholding & Phase 2 Code-to-Video Binding (Active):**
  - *Phase 2 (Active):* Dùng `approx_video_sec` từ Code AST (`is_approximate: false`) thay thế phỏng đoán xác suất Phase 1 (`CODE=0.35`, `VIDEO=0.22`, best-effort video $\ge 0.15$ khi Code $\ge 0.60$).
- **Outro Semantic Trap & Dimension Disambiguation:**
  - Không ép mốc `00:01` hoặc `sec > 90%`; dùng **Multi-Grounding Chronological Retrieval** (Lý thuyết -> Code -> Bài tập) + Query Entity Expansion từ Syllabus SSOT.
  - Phân định số chiều 1D vs 2D trong `CurriculumService`: câu hỏi `"2 chiều"` không cho bài `"1 chiều"` cướp quyền (và ngược lại).

---

## 3. Cascade Semantic Router, NLI & Security Guardrails

- **Fast-Path SLM + Stage 2 `mDeBERTa-v3` NLI Arbiter:**
  - SLM ONNX INT8 chạy CPU (< 10ms) làm tầng 1; Stage 2 Cross-Encoder `mDeBERTa-v3` phân định các ca biên.
  - **Exhaustive Multi-Class NLI Hypothesis Space:** 3 nhãn toàn diện (`course_query`, `chit_chat`, `out_of_scope`); khi SLM chọn `chit_chat`, chỉ gọi NLI cứu khi $P_{\text{chit\_chat}} < 0.75$ hoặc $P_{\text{course}} \ge 0.15$ (NLI suy luận học tập $\ge 50\%$ -> `course_query`), triệt tiêu Greeting Loop không cần regex.
  - **Curriculum Navigation Rescue:** Khi $P_{\text{oos}} < 0.75$ và $P_{\text{course}} \ge 0.15$, gọi NLI phân định câu hỏi lộ trình học tập vs ngoài lề.
  - **Two-Tier Conversational Navigation Confirmation:** Tầng 1 E5 Cosine ($\text{sim}_c \ge 0.88, \text{Margin} \ge 0.05$) -> Tầng 2 NLI ($P(\text{Đồng ý}) \ge 70\%$). Không dùng regex.
- **Tri-Tier Metaphor Grounding Invariant (câu hỏi ẩn dụ đời sống như `BENCH-141`):**
  1. Pre-retrieval Query Intent Decomposition (giữ câu gốc + bóc bản chất kỹ thuật).
  2. CRAG AST Grounding Anchor khi $0.15 \le S < 0.22$ (`is_approximate: true`).
  3. Socratic Synthesis trừu tượng hóa, đánh giá phần đúng/chưa đúng và từ chối giải bài hộ.
- **Contrastive Semantic Vector Guardrail (OWASP LLM01 / LLM07):**
  $$\Delta_{\text{margin}}(q) = \max_{a \in \mathcal{A}} \cos(\mathbf{e}_q, \mathbf{e}_a) - \max_{b \in \mathcal{B}} \cos(\mathbf{e}_q, \mathbf{e}_b)$$
  Chặn prompt injection / system prompt exfiltration / ép full code khi $\Delta_{\text{margin}} \ge +0.02$ và $\cos(q, a) \ge 0.86$, bảo toàn **Context-Aware Socratic Input Gate** cho học viên gửi code thật để hỏi lỗi biên dịch.

---

## 4. LangGraph Stateful Orchestration & Multi-Turn Integrity

- **4 Discrete Nodes (`app/services/chat_graph.py`):** `router_node` -> `retrieval_node` -> `crag_grader_node` -> `context_assembly_node` với `MemorySaver` theo `thread_id: session_id`.
- **Context Window & Pruning:** Sliding Window $k=5$ turns, trần lịch sử $\le 2,400$ chars, cắt tỉa bằng AST line-slicing (`token.map`), `Conversation Summarizer` kẹp chặt `current_lesson_seq`.
- **Multi-Turn Context Isolation & Anti-Pollution:** Cấm nối thô `f"{last_user_query} {raw_prompt}"`. Giữ nguyên truy vấn độc lập khi câu mới đã có chủ thể kỹ thuật rõ; chỉ liên kết lịch sử khi là câu cụt Ellipsis/Anaphora.
- **Stateful Navigation Dispatcher:** Câu điều hướng tham chiếu lịch sử (*"vấn đề vừa rồi"*, *"bài vừa rồi"*) phải tra `last_user_query` từ checkpointer.

---

## 5. Streaming, Socratic AST Firewall & System Architecture

- **FSM Stream Sanitizer & Whitelist $\mathcal{W}$ (`app/services/chat.py`):**
  - Máy trạng thái 3 trạng thái (`EMIT`, `ACCUMULATE_TAG`, `STREAM_BODY`) + `TimestampWhitelistHTMLParser` W3C event-driven.
  - Chỉ giữ `<timestamp sec="X">` khi $X \in \mathcal{W} = \text{suggested\_timestamps}$; `0%` sinh mốc giả `sec=0`/`sec=1`.
- **Tri-Layer Anti-CJK Token Leakage Guardrail:** Lọc Hán tự / Hangul bằng kiểm tra khoảng mã Unicode (`is_cjk_char`, `is_hangul_or_cjk`) cả ở Backend stream và Frontend Markdown renderer.
- **In-Context AST Sanitization & Socratic Code Boundary:**
  - Tước `#include` và vỏ `int main()` bằng Tree-sitter trước khi nhét ngữ cảnh vào Prompt; gắn nhãn `[MÃ NGUỒN BÀI GIẢNG THAM KHẢO - ĐÂY KHÔNG PHẢI CODE CỦA HỌC VIÊN]` để chống *In-Context Imitation*.
  - Đo độ phức tạp chu trình $M = E - N + 2P$; kích hoạt Scaffolding khi $M \ge 3$ có luồng I/O + `return`; cho phép skeleton 1–3 dòng kèm `// TODO` thay vì full solution.
- **Factual Faithfulness & C++ Invariants (ICLR 2025):** Không suy diễn thanh ghi/địa chỉ ngoài bài giảng; mảng C++ luôn **Row-Major Order**, **0-indexed**, mảng tĩnh kích thước compile-time; mỗi lượt cô đọng 2–3 điểm cốt lõi + 1 câu hỏi `?`.
- **"Use First, Build Last" & Polyglot Persistence:** Kế thừa Qdrant/FastEmbed/Whisper/Tree-sitter/LangGraph và tự xây CRAG/Pareto/Router; tách rạch ròi Vector DB (ANN semantic search) với Relational SQL (ACID Single Source of Truth cho auth, rate-limit, `lesson_seq`, CMS, `CHAT_QUERIES`).
- **Systemic Optimization Initiatives (`M-04..M-08`):** Parallel Future Probing (`M-04`), Context Truncation & Candidate Pruning + Asyncio Thread Offloading + RTX 2050 CUDA (`M-05`), Temporal NMS Deduplication (`M-06`), Tri-Timestamp Budget (`M-07`), Offline Decoupled RAGAS Triad (`M-08`).
