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
