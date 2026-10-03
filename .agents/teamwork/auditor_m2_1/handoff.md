# BÁO CÁO KIỂM TOÁN TÍNH TOÀN VẸN ĐỘC LẬP (FORENSIC INTEGRITY AUDIT REPORT) — MILESTONE 2

**Cơ quan kiểm toán:** Forensic Integrity Auditor (`@auditor-1` / `auditor_m2_1`)  
**Đối tượng kiểm toán:** Milestone 2 (Worker `worker_m2_1`: `app/services/retrieval.py`, `app/config.py`, `app/agent/router.py`, `scratch/test_targeted_cases.py`, `scratch/debug_case.py`)  
**Tiêu chuẩn kiểm toán (Profile):** General Project — **Benchmark Mode** (Mức độ nghiêm ngặt tối đa theo `ORIGINAL_REQUEST.md`)  
**Phán quyết nhị phân (Verdict):** **CLEAN** (HỢP LỆ — TUÂN THỦ TOÀN VẸN 100%)

---

## 1. OBSERVATION (QUAN SÁT THỰC NGHIỆM ĐỘC LẬP)

1. **Rà soát Mã Nguồn — Zero Quick-Fix Audit:**
   - Đã thực hiện tìm kiếm toàn diện (grep & AST search) trên toàn bộ thư mục `app/` và các tệp sửa đổi (`app/services/retrieval.py`, `app/config.py`, `app/agent/router.py`).
   - Kết quả tìm kiếm từ khóa kiểm thử:
     + Chuỗi `"BENCH-"` trong mã nguồn `app/`: **0 kết quả** trong logic lõi (chỉ xuất hiện trong endpoint phục vụ báo cáo benchmark tại `app/api/v1/benchmark.py`).
     + Chuỗi `"float"`, `"double"`, `"unsigned int"` trong `app/services/retrieval.py`: **0 kết quả** (không có bất kỳ câu lệnh `if "float" in query` hay rẽ nhánh nhân tạo nào).
     + Biểu thức chính quy (`re.*`): Trong `app/services/retrieval.py`, biểu thức regex duy nhất được sử dụng là:
       ```python
       text = re.sub(r"[\uac00-\ud7af\u1100-\u11ff\u4e00-\u9fff]", "", text)
       ```
       tại hàm `sanitize_text()`, nhằm lọc bỏ ký tự rác âm học ngoại lai từ mô hình Whisper. Hoàn toàn không có regex bắt từ khóa người dùng hay câu hỏi cụ thể.

2. **Rà soát Dummy / Facade Implementation:**
   - Tại `app/services/retrieval.py` (dòng 482–588), kiến trúc phân tầng 4 cấp toán học được cài đặt thuần túy bằng thuật toán định lượng (Yan et al. & ICLR 2025):
     + **Tầng 1 (Grounded Anchor & Modality-Aware Early Exit):**
       ```python
       valid_ast_items = [
           it for it in candidate_items
           if it.get("content_type") == "code_ast"
           and it.get("confidence_score", 0.0) >= settings.MODALITY_GATE_AST_THRESHOLD
       ]
       valid_video_items = [
           it for it in candidate_items
           if it.get("content_type") == "video_transcript"
           and it.get("confidence_score", 0.0) >= settings.MODALITY_GATE_VIDEO_THRESHOLD
       ]
       if valid_ast_items or valid_video_items:
           ...
           return RetrievalResult(chunks=final_assembled, status="grounded", is_low_confidence=False)
       ```
     + **Tầng 2 (Future Lesson Probing):**
       ```python
       if target_seq and future_score >= settings.FUTURE_PROBE_MIN_CONFIDENCE and margin >= settings.FUTURE_PROBE_MARGIN:
           return RetrievalResult(chunks=[], status="out_of_lesson", target_lesson_seq=target_seq)
       ```
     + **Tầng 3 (Graceful Degradation):**
       ```python
       low_confidence_items = [
           it for it in candidate_items
           if it.get("confidence_score", 0.0) >= 0.20
           and it.get("raw_semantic_score", 0.0) >= settings.VIDEO_FALLBACK_MIN_THRESHOLD
           and grade_document_relevance(query_text, it, min_confidence=0.20) == "CORRECT"
       ]
       if low_confidence_items:
           return RetrievalResult(chunks=final_assembled, status="grounded", is_low_confidence=True)
       ```
     + **Tầng 4 (Coverage Gap):**
       ```python
       return RetrievalResult(chunks=[], status="coverage_gap")
       ```
   - Không phát hiện bất kỳ hàm facade, mock, hay giá trị trả về cố định (hardcoded constant) nào.

3. **Rà soát Data/Code Separation Invariant:**
   - Tệp `app/services/retrieval.py` nạp bảng ánh xạ Code-to-Video thông qua manifest JSON ngoài:
     ```python
     BINDING_MANIFEST_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "metadata" / "lesson_code_video_binding.json"
     ```
   - Không có bất kỳ từ điển Python (`dict`) nào chứa mốc thời gian video hay bài học bị nhúng trực tiếp trong mã nguồn `.py`. Toàn bộ dữ liệu nằm tại `data/metadata/lesson_code_video_binding.json`.

4. **Đồng bộ Cấu hình `app/config.py`:**
   - Lệnh kiểm tra:
     ```powershell
     .venv\Scripts\python -c "from app.config import settings; print(f'AST={settings.MODALITY_GATE_AST_THRESHOLD}, VIDEO={settings.MODALITY_GATE_VIDEO_THRESHOLD}, MARGIN={settings.FUTURE_PROBE_MARGIN}, MIN_CONF={settings.FUTURE_PROBE_MIN_CONFIDENCE}, TOP_CAND={settings.DEFAULT_TOP_CANDIDATES}, FUTURE_LIMIT={settings.FUTURE_PROBE_LIMIT}')"
     ```
   - Kết quả xuất ra:
     `AST=0.35, VIDEO=0.3, MARGIN=0.12, MIN_CONF=0.4, TOP_CAND=10, FUTURE_LIMIT=18`
     Khớp hoàn toàn với Interface Contracts và yêu cầu của `ORIGINAL_REQUEST.md`.

5. **Xác minh Tính Trung thực Thực nghiệm (Verification of Truth):**
   - Kiểm toán viên đã trực tiếp chạy độc lập tệp `scratch/test_targeted_cases.py` trên môi trường thực tế (Task ID: `task-62`).
   - Kết quả thu được từ terminal:
     + `BENCH-022`: `✓ PASS` | Latency: `10974.7ms` | Status: `grounded` | Conf: `0.3078` | TS: `<timestamp sec="751">12:31</timestamp>`
     + `BENCH-035`: `✓ PASS` | Latency: `10644.7ms` | Status: `grounded` | Conf: `0.3043` | TS: `<timestamp sec="2638">43:58</timestamp>`
     + `BENCH-041`: `✓ PASS` | Latency: `10925.7ms` | Status: `grounded` | Conf: `0.3796` | TS: `<timestamp sec="228">03:48</timestamp>`
     + `BENCH-045`: `✓ PASS` | Latency: `10035.8ms` | Status: `grounded` | Confs: `0.3921, 0.3044, 0.3744` | TS: `<timestamp sec="724">12:04</timestamp>`
     + `BENCH-049`: `✓ PASS` | Latency: `9264.4ms` | Status: `grounded` | Conf: `0.3254` | TS: `<timestamp sec="1584">26:24</timestamp>`
     + 9 ca còn lại (`BENCH-004`, `BENCH-007`, `BENCH-010`, `BENCH-011`, `BENCH-014`, `BENCH-016`, `BENCH-037`, `BENCH-058`, `BENCH-064`): Trạng thái `out_of_lesson` hoặc `coverage_gap`.
   - **Đối chiếu với báo cáo bàn giao của `worker_m2_1`:**
     Từng số liệu điểm tin cậy (đến 4 chữ số thập phân), từng mốc giây video timestamp, và từng trạng thái thất bại của 9 ca đều **trùng khớp 100% với những gì worker đã báo cáo**.
     Worker không hề làm giả kết quả 14/14 PASS, mà báo cáo hoàn toàn trung thực kết quả 5/14 PASS cùng chẩn đoán nguyên nhân dữ liệu âm học Whisper thô trong Qdrant.

---

## 2. LOGIC CHAIN (CHUỖI LÝ LUẬN TỪ QUAN SÁT ĐẾN KẾT LUẬN)

1. **Về Zero Quick-Fix:** Quan sát 1 chứng minh không có sự xuất hiện của bất kỳ chuỗi tìm kiếm cứng, ID kiểm thử hay biểu thức regex cá biệt nào trong mã nguồn sản phẩm. Do đó, tiêu chí Zero Quick-Fix hoàn toàn ĐẠT.
2. **Về Tính Chân thực Thuật toán:** Quan sát 2 chứng minh các nhánh rẽ trong `retrieval.py` hoàn toàn vận hành dựa trên các phép so sánh điểm số định lượng thực tế (`confidence_score`, `raw_semantic_score`, `margin`). Không có facade hay mock. Do đó, tiêu chí Dummy Implementation Audit hoàn toàn ĐẠT.
3. **Về Phân tách Dữ liệu và Mã nguồn:** Quan sát 3 xác nhận toàn bộ bảng ánh xạ Ground-Truth mốc video được đọc động từ tệp JSON độc lập `data/metadata/lesson_code_video_binding.json`. Do đó, tiêu chí Data/Code Separation hoàn toàn ĐẠT.
4. **Về Tính Trung thực Báo cáo:** Quan sát 5 xác nhận kết quả kiểm thử độc lập của kiểm toán viên tái hiện chính xác 100% từng số liệu, mốc thời gian và trạng thái mà worker đã tuyên bố trong `handoff.md`. Không có sự ngụy tạo dữ liệu hay chứng nhận khống.

---

## 3. CAVEATS (GIỚI HẠN VÀ KHUYẾN NGHỊ VÙNG BIÊN)

1. **Phạm vi kiểm toán:** Báo cáo này kiểm toán toàn diện mã nguồn triển khai của Milestone 2. Việc chạy toàn bộ 200 câu hỏi Golden Dataset thuộc phạm vi chuyên biệt của Milestone 3 (`@qa-tester`).
2. **Hiện tượng âm học thô trên Qdrant:** 9 ca lỗi còn lại trong nhóm 14 ca Tier 1 xuất phát từ văn bản âm học chưa chuẩn hóa trong Vector DB (như "thẳng đáp bồ" thay vì "double"), đây là vấn đề của tầng dữ liệu Ingestion/Whisper, không thuộc lỗi logic của `retrieval.py`.

---

## 4. CONCLUSION (KẾT LUẬN)

- **Phán quyết cuối cùng:** **CLEAN** (Toàn bộ các tiêu chí kiểm toán tính toàn vẹn đều ĐẠT, không phát hiện bất kỳ hành vi vi phạm nào).
- **Hành động đề xuất:** Phê duyệt hoàn thành Milestone 2 và chuyển giao sang Milestone 3 (`@qa-tester`) để thực thi bộ Benchmark 200 câu Golden Dataset.

---

## 5. VERIFICATION METHOD (PHƯƠNG PHÁP TỰ KIỂM CHỨNG LẠI)

1. **Kiểm tra biên dịch và cấu hình:**
   ```powershell
   .venv\Scripts\python -c "from app.config import settings; print(settings.MODALITY_GATE_AST_THRESHOLD, settings.MODALITY_GATE_VIDEO_THRESHOLD, settings.FUTURE_PROBE_MARGIN)"
   ```
   *Kỳ vọng:* Xuất ra `0.35 0.3 0.12`.

2. **Kiểm chứng tính trung thực của 14 ca mục tiêu:**
   ```powershell
   .venv\Scripts\python scratch/test_targeted_cases.py
   ```
   *Kỳ vọng:* Xuất ra chính xác 5/14 ca PASS (BENCH-022, 035, 041, 045, 049) với các điểm số conf và timestamp khớp hoàn toàn.

3. **Điều kiện vô hiệu hóa (Invalidation Conditions):**
   - Nếu phát hiện bất kỳ chuỗi `if "BENCH-"` hoặc `if query == ...` nào trong `app/services/retrieval.py` $\to$ Phán quyết lập tức chuyển thành `INTEGRITY VIOLATION`.
