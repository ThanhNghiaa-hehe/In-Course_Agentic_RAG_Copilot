# Dead Ends Log

| Iteration | Approach Tried | Why It Failed | Files Touched |
|-----------|---------------|---------------|---------------|
| 1 | Unconditional Video Early Exit at flat 0.30 (`valid_ast_items or valid_video_items`) | Caused 4 Tier 2 regressions (e.g. BENCH-091, BENCH-092) where video transcript casually mentioning concepts in old lesson (score 0.381) falsely early-exited before probing future lesson where executable code exists (score > 0.60, margin > 0.12). Violates ICLR 2025 Context Sufficiency. | `app/services/retrieval.py`, `app/config.py` |
| 2 | Denying early exit to video in [0.30, 0.40) and forcing future probe with flat margin 0.12 | Practice/exercise lessons (L+1 or later) containing code AST score >= 0.55-0.70 easily surpassed theory video (0.30-0.38) by margin > 0.12, causing 5/5 in-scope theory cases (BENCH-022, 035, 041, 045, 049) to regress to out_of_lesson. | `app/services/retrieval.py`, `app/config.py` |
