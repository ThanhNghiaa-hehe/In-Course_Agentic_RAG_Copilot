# Runtime & Engineering Rigor Invariants

## 1. Anti-Deception & Zero-Fabrication
- **No "Qua Mặt" Model Swaps:** Never suggest replacing self-hosted `Qwen/Qwen2.5-Coder-7B-Instruct` with a commercial API just to make demo latency look faster.
- **Evidence-Only Reporting:** Report only directly observed file contents, command outputs, timings, and test runs from after the final edit. Never fabricate root causes or hide remaining bugs when reviewing Playground debug logs (`logs/playground_debug/`).
- **Zero Quick-Fix:** Never add per-query regex hacks or hardcoded keyword patches to bypass failing Playground or benchmark cases.

## 2. RTX 2050 4GB VRAM & ONNX Provider Split
- **Single ONNX Package Rule:** In `.venv`, `onnxruntime` (CPU) and `onnxruntime-gpu` share `site-packages/onnxruntime/capi` and overwrite each other. Keep only `onnxruntime-gpu==1.23.2` (CUDA 12 + cuDNN 9 compatible).
- **Device Allocation Invariant:**
  - Keep dense embedding (`intfloat/multilingual-e5-large`) on GPU (`CUDAExecutionProvider`).
  - Pin INT8 cross-encoder reranker (`data/models/jina-reranker-v2-int8/onnx/model.onnx`) on CPU (`USE_CPU_RERANKER=True`, `USE_INT8_RERANKER=True`, `RERANK_CPU_THREADS=4`, `RERANK_MAX_CHARS=600`) so total VRAM stays safely within 4 GB.
- **Socratic Output Budget:** Do not over-shrink `LLM_MAX_TOKENS` in a way that truncates Socratic guiding questions (maintain `LLM_MAX_TOKENS=650` unless proven otherwise).

## 3. Empirical Bottleneck Attribution & Config Hygiene
- **Layered Latency Measurement:** Always separate tunnel RTT (e.g., Ngrok), tiny LLM TTFT (`max_tokens=20`), dense embedding latency, and CPU rerank latency before attributing slowness to a single layer.
- **Clean `app/config.py`:** Do not leave unreferenced "dead" tuning parameters lingering in `app/config.py`. Audit references across `app/`, `scripts/`, `tests/` and offline branches before deleting unused fields.

## 4. RAG Routing, Context & Swarm Invariants
- **No Rigid Keyword Pre-Gates Before Semantic E5/NLI:** Never block semantic intent routing (e.g., `is_curriculum_navigation`) with a hard `if not any(keyword in prompt)` pre-gate before E5 cosine and NLI can evaluate paraphrased queries.
- **Exact `lesson_seq` Integrity on Fallback Chunks:** Never borrow `future_points[0]` from an unrelated lesson while stamping `target_seq` onto it; always verify `lesson_seq == target_seq` or fall back to `CurriculumService.get_lesson_timestamps(target_seq)`.
- **Static `messages[0]` System Prompt:** Keep `messages[0]` (`System Prompt`) 100% static across turns; place per-turn dynamic extensions (`conversation_summary`, `glossary_ext`, `SOFT_NUDGE`) in `user_message_content` so vLLM `--enable-prefix-caching` hits cleanly.
- **Argon-Supervise / Hydrogen-Execute Swarm:** When running a Swarm for complex fixes, assign `Gemini 4 Argon (High)` as the read-only `[spec]` architect & anti-quick-fix `git diff` auditor (`[approved]`), and `Gemini 4 Hydrogen (High)` as implementation & verification workers.

## 5. Live E2E Matrix, Temporal Retrieval & Windows Runtime Learnings (2026-11-18)
- **Windows 4 GB VRAM & OpenMP Process Discipline:**
  - Never launch heavy GPU embedding/rerank `pytest` or E2E harnesses while `uvicorn` is actively holding RTX 2050 4 GB VRAM (`onnxruntime-gpu` + CUDA spills into shared RAM and can segfault). Stop `uvicorn` for default GPU `--suite all` runs, or pass `--safe-cpu` when testing side-by-side with a running server.
  - When running `onnxruntime` CPU alongside `PyTorch` (`mDeBERTa-v3` NLI) in the same Windows process under CPU mode, keep threads pinned (`OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `torch.set_num_threads(1)`) to avoid `libiomp5md.dll` OpenMP barrier deadlocks.
- **Temporal Queries & Non-Domain Time Phrases:**
  - Treat `current_video_sec` + parsed Vietnamese temporal cues (`explicit_sec`, `relative_start/middle/end`, `deictic_current`) as course retrieval signals **only** after guarding runtime duration phrases (`"... mất N phút"`) and running Stage 2 Cross-Encoder NLI (`In-Video Temporal NLI Rescue`), keeping `app/agent/router.py` and `app/services/telemetry_critic.py` aligned.
- **Qwen 7B Anti-Parroting & Socratic Questioning Hygiene:**
  - Never insert bracketed meta-tags (`[đã rút gọn...]`) into `assistant` message history: 7B models autocomplete/parrot those tags verbatim. Strip boilerplate greetings/sign-offs, prune stale history upon video timestamp or lesson jumps, write prompt directives (`SOFT_NUDGE`) without copyable template phrasing, and enforce `StreamingInternalArtifactSanitizer`.
  - Keep AST-guided offline transcript canonicalization (`scripts/canonicalize_transcripts_ast.py`) clean so Whisper phonetic typos (e.g., `"mạng"` vs `"mảng"`) do not leak into 7B grounded answers, and monitor Socratic ending `?` adherence in live E2E runs (`M2` live check caught missing `?` on Turns 1 & 3).
- **Full-Matrix E2E Regression Discipline:**
  - Always verify both real `router_node` behavior and live multi-turn E2E variation matrices (`scripts/e2e_matrix_harness.py --suite all`, plus `--routing-only` for fast routing sweeps), and report exact pass/fail turn metrics rather than claiming blanket passes.
