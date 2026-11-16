---
name: rag-runtime-ops
description: >-
  Operational runbook for verifying RTX 2050 4GB ONNX GPU/CPU provider splits,
  profiling Ngrok vs remote LLM TTFT bottlenecks, auditing app/config.py
  hygiene, coordinating Swarm verification, and rendering clean architecture
  diagrams. Use when tuning runtime latency, GPU/CPU inference, Ngrok tunnels,
  config cleanup, Playground debug audits, or technical diagrams.
---

# RAG Runtime Ops & Profiling Runbook

## 1. Verify ONNX GPU/CPU Provider Split (RTX 2050 4 GB)
1. Confirm package integrity inside `.venv` (never mix `onnxruntime` and `onnxruntime-gpu` in the same environment; keep `onnxruntime-gpu==1.23.2`).
2. Verify runtime providers via `.venv\Scripts\python.exe`:
   - `EmbeddingService().device == "cuda"`
   - Dense E5 session uses `['CUDAExecutionProvider', 'CPUExecutionProvider']`
   - Reranker (`data/models/jina-reranker-v2-int8/onnx/model.onnx`) uses `['CPUExecutionProvider']` with `USE_CPU_RERANKER=True`, `USE_INT8_RERANKER=True`, `RERANK_CPU_THREADS=4`, `RERANK_MAX_CHARS=600`.
3. Check GPU memory headroom with `nvidia-smi` to confirm comfortable margin under `4,096 MiB`.

## 2. Layered Latency Profiling (No Guessing)
When the user reports slow TTFT or suspects Ngrok:
1. Measure raw tunnel RTT to `<LLM_BASE_URL>/v1/models`.
2. Measure a tiny authenticated streaming call (`max_tokens=20`) directly to `Qwen/Qwen2.5-Coder-7B-Instruct` to separate network + cold/decode overhead from long prompt/RAG context overhead.
3. Measure local `EmbeddingService` dense + INT8 rerank latencies separately.
4. Inspect the newest `logs/playground_debug/session_*.json` and `*_critique.md` honestly: report both latency wins and any remaining routing, retrieval, or timestamp guardrail bugs verbatim.

## 3. `app/config.py` Hygiene Audit
1. Cross-check every `Settings` field in `app/config.py` against references in `app/`, `scripts/`, and `tests/`.
2. Before deleting unreferenced fields, confirm they are not reserved for an active feature branch or standalone evaluation script.
3. Run targeted `pytest` suites after any config cleanup.

## 4. Swarm Verification Discipline
1. Use Swarm (`swarm` tool) only when work splits cleanly into independent streams (e.g., GPU runtime, prompt/guardrails, independent `verifier`, `monitor`).
2. Always keep an independent `verifier` run unit/regression tests (`pytest`) after all edits land.
3. Explicitly `kill` all Swarm workers once verification passes and work is merged.

## 5. Anti-AI-Slop Architecture Diagram Standard
- Canvas: Pure white `#ffffff` background, crisp typography.
- Palette: At most 3 restrained Slate / Indigo / Teal tones (no neon gradients).
- Rendering: Vector output (e.g., `matplotlib` exported at 300 DPI), zero emoji icons, zero overlapping labels.
