## 2026-10-03T15:40:41Z

You are the Core Retrieval Engineer (@core-coder / worker_m2_it2_1) implementing Iteration 2 fixes for In-Course Agentic RAG Copilot.

MANDATORY FIRST STEP:
Read the authoritative user request at:
d:\In_Course_Agentic_RAG_Copilot\.agents\teamwork\ORIGINAL_REQUEST.md
Also read:
d:\In_Course_Agentic_RAG_Copilot\.agents\teamwork\orchestrator_1\PROJECT.md
d:\In_Course_Agentic_RAG_Copilot\.agents\teamwork\orchestrator_1\DEAD_ENDS.md
d:\In_Course_Agentic_RAG_Copilot\.agents\teamwork\challenger_m3_1\handoff.md
Also read:
d:\In_Course_Agentic_RAG_Copilot\.agents\skills\ast-code-chunker\SKILL.md
d:\In_Course_Agentic_RAG_Copilot\.agents\skills\whisper-canonicalizer-tester\SKILL.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

WRITE OWNERSHIP:
You have exclusive write ownership of:
- app/config.py
- app/services/retrieval.py
- data/metadata/lesson_code_video_binding.json (if adding valid metadata bindings)

CONTEXT & PROBLEM IDENTIFIED IN ITERATION 1:
In Iteration 1, CRAG reached 81.0% (162/200). 4 Tier 2 questions (e.g. BENCH-091, BENCH-092) were falsely swallowed into grounded at Lesson 3 because unconditional video early exit at 0.30 triggered on conversational video mentions (0.381) without Code AST, before checking Lesson 6 where the actual 'for' loop code exists. This violated the Relevance vs Context Sufficiency Invariant (ICLR 2025).

ACTIONABLE TASKS:
1. In app/services/retrieval.py (Tầng 1 & Tầng 2 & Tầng 3):
   Refine Tầng 1 Modality-Aware Gate:
   - If valid_ast_items (confidence >= MODALITY_GATE_AST_THRESHOLD [0.35]):
     TRIGGER Early Exit immediately -> return grounded. (Code AST is an unambiguous syntax anchor).
   - If valid_video_items and not valid_ast_items:
     - If max_video_score >= 0.40:
       TRIGGER Early Exit immediately -> return grounded. (High-confidence video explanation).
     - If 0.30 <= max_video_score < 0.40:
       DO NOT early exit immediately! Proceed to Tầng 2 (_probe_future_lessons).
       If future lesson probe dominates (target_seq is not None, future_score >= FUTURE_PROBE_MIN_CONFIDENCE [0.40], and margin >= FUTURE_PROBE_MARGIN [0.12]):
         return out_of_lesson! (Future lesson has official code/explanation, resolving BENCH-091/092).
       Else:
         return grounded! (Because future lesson does NOT dominate, so this current lesson video in [0.30, 0.40) is indeed the grounded context, preserving BENCH-022, 035, etc.).
   - In Tầng 3 Graceful Degradation:
     - Evaluate current lesson items where confidence_score >= 0.20 (or slightly lowered floor if appropriate) with CRAG validation.
2. In app/config.py:
   - Ensure all settings are consistent and clean:
     MODALITY_GATE_AST_THRESHOLD = 0.35
     MODALITY_GATE_VIDEO_THRESHOLD = 0.30
     MODALITY_GATE_VIDEO_HIGH_CONFIDENCE: float = 0.40 (or used directly in retrieval logic)
     FUTURE_PROBE_MARGIN = 0.12
     FUTURE_PROBE_MIN_CONFIDENCE = 0.40
     DEFAULT_TOP_CANDIDATES = 10
     FUTURE_PROBE_LIMIT = 18
3. Verification:
   - Run compilation & import check.
   - Run targeted cases: python scratch/test_targeted_cases.py.
   - Run test on Tier 2 cases (specifically test BENCH-091, BENCH-092 to ensure they return out_of_lesson and NOT grounded).
   - Document commands, outputs, and metrics.
4. Delivery:
   - Update your progress.md (include 'Last visited: [timestamp]').
   - Write comprehensive handoff.md in your working directory:
     d:\In_Course_Agentic_RAG_Copilot\.agents\teamwork\worker_m2_it2_1\handoff.md
   - Send completion message to parent orchestrator via send_message.
