# BÁO CÁO KIỂM CHỨNG & LÀM SẠCH DATASET (4 MÔ HÌNH FINE-TUNE)
- **Thời điểm:** `2026-11-27 22:43:20` | **Chế độ:** `validate` | **E5 Conflict Check:** `True`
- **Số câu held-out kiểm tra khử nhiễm:** `522` | **Trạng thái chung:** `PASS`

| Mô hình | Tổng vào | Sạch đầu ra | Rò rỉ test | Trạng thái | Ghi chú chi tiết |
|---|---:|---:|---:|---|---|
| `slm_router` | 591 | 591 | 0 | **PASS** | Ratio=1.79x, FatalConflict=0, DupConflict=0, E5ConeOverlap=302 |
| `mdeberta_nli` | 2043 | 2043 | 0 | **PASS** | Labels={'0': 641, '2': 1057, '1': 345}, Neutral=0.1689, MultiEnt=0, TempImb=0 |
| `jina_reranker` | 662 | 662 | 0 | **PASS** | FN=0, Over600=0, Shortcut=0, IntraNeg=138, AST=30, Garbled=0 |
| `qwen25_qlora` | 287 | 287 | 0 | **PASS** | Lessons=83/83, BadTS=0, BadSocratic=0, CodeLeak=0, Trunc=0, Openings=154/215 |
