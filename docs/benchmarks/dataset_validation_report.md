# BÁO CÁO KIỂM CHỨNG & LÀM SẠCH DATASET (4 MÔ HÌNH FINE-TUNE)
- **Thời điểm:** `2026-11-26 22:16:48` | **Chế độ:** `validate` | **E5 Conflict Check:** `True`
- **Số câu held-out kiểm tra khử nhiễm:** `522` | **Trạng thái chung:** `PASS`

| Mô hình | Tổng vào | Sạch đầu ra | Rò rỉ test | Trạng thái | Ghi chú chi tiết |
|---|---:|---:|---:|---|---|
| `slm_router` | 551 | 551 | 0 | **PASS** | Ratio=1.74x, FatalConflict=0, DupConflict=0, E5ConeOverlap=253 |
| `mdeberta_nli` | 1953 | 1953 | 0 | **PASS** | Labels={0: 611, 2: 1027, 1: 315}, Neutral=0.1613, MultiEnt=0, TempImb=0 |
| `jina_reranker` | 663 | 663 | 0 | **PASS** | FN=0, Over600=0, Shortcut=0, IntraNeg=139, AST=30, Garbled=0 |
| `qwen25_qlora` | 284 | 284 | 0 | **PASS** | Lessons=83/83, BadTS=0, BadSocratic=0, CodeLeak=0, Trunc=0, Openings=17/36 |
