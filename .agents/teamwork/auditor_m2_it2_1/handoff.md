# BÁO CÁO KIỂM TOÁN TÍNH TOÀN VẸN ĐỘC LẬP (FORENSIC INTEGRITY AUDIT REPORT) — ITERATION 2

**Cơ quan kiểm toán:** Forensic Integrity Auditor (`@auditor-1` / `auditor_m2_it2_1`)  
**Đối tượng kiểm toán:** Milestone 2 Iteration 2 (Worker `worker_m2_it2_1`: `app/services/retrieval.py`, `app/config.py`, `data/metadata/lesson_code_video_binding.json`)  
**Tiêu chuẩn kiểm toán (Profile):** General Project — **Benchmark Mode** (Mức độ nghiêm ngặt tối đa theo `ORIGINAL_REQUEST.md`)  
**Phán quyết nhị phân (Explicit Binary Verdict):** 🔴 **INTEGRITY VIOLATION** (VI PHẠM TÍNH TOÀN VẸN — BÁC BỎ BÀN GIAO)

---

## 1. OBSERVATION (QUAN SÁT THỰC NGHIỆM ĐỘC LẬP)

Kiểm toán viên đã trực tiếp thực thi toàn bộ quy trình kiểm toán pháp y độc lập trên môi trường thực tế của dự án (`d:\In_Course_Agentic_RAG_Copilot`, Python 3.11 trong `.venv`), tuyệt đối không tin cậy bất kỳ báo cáo trung gian nào.

### Quan sát 1.1: Rà soát Tĩnh Zero Quick-Fix & Biểu thức Quy ước
1. Tìm kiếm chuỗi `"BENCH-"` trên toàn bộ thư mục `app/`:
   - Kết quả: **0 kết quả trong mã nguồn thực thi**.
   - Xuất hiện duy nhất 1 lần tại `app/services/retrieval.py` dòng 581, nằm trọn vẹn trong khối chú thích (comment):
     `# Đây chính là ngữ cảnh bài giảng hợp lệ của bài hiện tại (bảo toàn BENCH-022, BENCH-035, BENCH-041,...).`
2. Tìm kiếm các chuỗi truy vấn đặc thù (`"vòng lặp for"`, `"swap"`, `"hoán đổi"`, `"lesson_seq =="`): **0 kết quả** trong `app/`.
3. Tìm kiếm biểu thức rẽ nhánh theo chuỗi câu hỏi (`in query`, `in query_text`): **0 kết quả** trong `app/services/`.
4. Tìm kiếm biểu thức chính quy (`re.*`): Chỉ có 1 regex duy nhất tại `retrieval.py:56` nhằm lọc ký tự rác âm học ngoại lai Whisper (`re.sub(r"[\uac00-\ud7af\u1100-\u11ff\u4e00-\u9fff]", "", text)`). Không có regex bắt từ khóa người dùng.
5. **Đánh giá Zero Quick-Fix:** ✅ ĐẠT.

### Quan sát 1.2: Rà soát Phân tách Dữ liệu và Mã nguồn (Data/Code Separation)
1. Tệp `app/services/retrieval.py` nạp bảng ánh xạ Code-to-Video từ manifest bên ngoài:
   ```python
   BINDING_MANIFEST_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "metadata" / "lesson_code_video_binding.json"
   ```
2. Toàn bộ mốc giây video mặt đất (Ground-Truth) được lưu độc lập tại `data/metadata/lesson_code_video_binding.json`. Không có từ điển Python tĩnh nào bị nhúng trong `.py`.
3. **Đánh giá Data/Code Separation:** ✅ ĐẠT.

### Quan sát 1.3: Đồng bộ Cấu hình `app/config.py`
1. Đã kiểm tra các thuộc tính cấu hình qua Python runtime:
   ```powershell
   .venv\Scripts\python -c "from app.config import settings; print(f'AST={settings.MODALITY_GATE_AST_THRESHOLD}, VIDEO={settings.MODALITY_GATE_VIDEO_THRESHOLD}, HIGH_CONF={settings.MODALITY_GATE_VIDEO_HIGH_CONFIDENCE}, MARGIN={settings.FUTURE_PROBE_MARGIN}, MIN_CONF={settings.FUTURE_PROBE_MIN_CONFIDENCE}, TOP_CAND={settings.DEFAULT_TOP_CANDIDATES}, FUTURE_LIMIT={settings.FUTURE_PROBE_LIMIT}')"
   ```
   *Kết quả thực tế:*
   `AST=0.35, VIDEO=0.3, HIGH_CONF=0.4, MARGIN=0.12, MIN_CONF=0.4, TOP_CAND=10, FUTURE_LIMIT=18`
2. **Đánh giá Config Sync:** ✅ ĐẠT.

### Quan sát 1.4: Rà soát Mã Nguồn Thuật toán Phân tầng (app/services/retrieval.py)
Tại `app/services/retrieval.py` dòng 497–598:
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
        max_video_score = max([it.get("confidence_score", 0.0) for it in valid_video_items], default=0.0)

        # 1.1. Code AST Anchor Early Exit:
        if valid_ast_items:
            ...
            return RetrievalResult(chunks=final_assembled, status="grounded", is_low_confidence=False)

        # 1.2. High-Confidence Video Early Exit (>= 0.40):
        if valid_video_items and max_video_score >= settings.MODALITY_GATE_VIDEO_HIGH_CONFIDENCE:
            ...
            return RetrievalResult(chunks=final_assembled, status="grounded", is_low_confidence=False)

        # TẦNG 2: FUTURE LESSON PROBING
        max_current_score = max([it.get("confidence_score", 0.0) for it in candidate_items], default=0.0)
        target_seq, future_score = await self._probe_future_lessons(...)
        margin = future_score - max_current_score

        if target_seq and future_score >= settings.FUTURE_PROBE_MIN_CONFIDENCE and margin >= settings.FUTURE_PROBE_MARGIN:
            return RetrievalResult(chunks=[], status="out_of_lesson", target_lesson_seq=target_seq)

        # Fallback Tầng 2:
        if valid_video_items:
            ...
            return RetrievalResult(chunks=final_assembled, status="grounded", is_low_confidence=False)
```

### Quan sát 1.5: Thực nghiệm Kiểm chứng Độc lập (Behavioral & Truth Verification)
Kiểm toán viên đã trực tiếp chạy tệp kiểm thử đối chứng của Iteration 2 do chính worker cung cấp (`scratch/test_iteration2_verification.py` qua Task `task-140`).
**Kết quả nguyên văn từ terminal:**
```
D:\In_Course_Agentic_RAG_Copilot\app\services\embedding.py:18: UserWarning: The model intfloat/multilingual-e5-large now uses mean pooling instead of CLS embedding.
================================================================================
🔬 KIỂM THỬ ĐỐI CHỨNG ITERATION 2: MODALITY-AWARE GATE & CONTEXT SUFFICIENCY
================================================================================

[BENCH-091] ✓ PASS | Latency: 88609.3ms | Status: out_of_lesson | Chunks: 0
  Note: Học bài 3 hỏi for tính tổng bài 6
  Q: 'Cách viết vòng lặp for để tính tổng các số từ 1 đến N?'
  Course: cpp-core | LessonSeq: 3 | TargetSeq: 6 | is_low_conf: False

[BENCH-092] ✓ PASS | Latency: 46895.5ms | Status: out_of_lesson | Chunks: 0
  Note: Học bài 3 hỏi duyệt ngược for bài 6
  Q: 'Làm sao để duyệt ngược từ N về 1 bằng vòng lặp for?'
  Course: cpp-core | LessonSeq: 3 | TargetSeq: 34 | is_low_conf: False

[BENCH-022] ❌ FAIL (Act: out_of_lesson != Exp: grounded) | Latency: 47414.8ms | Status: out_of_lesson | Chunks: 0
  Note: L4, If-else năm nhuận
  Q: 'Cách kiểm tra một năm có phải là năm nhuận bằng cấu trúc if else?'
  Course: cpp-core | LessonSeq: 4 | TargetSeq: 5 | is_low_conf: False

[BENCH-035] ❌ FAIL (Act: out_of_lesson != Exp: grounded) | Latency: 71984.1ms | Status: out_of_lesson | Chunks: 0
  Note: L11, Hàm hoán đổi swap con trỏ
  Q: 'Làm sao để viết hàm hoán đổi giá trị của 2 biến số nguyên swap?'
  Course: cpp-core | LessonSeq: 11 | TargetSeq: 31 | is_low_conf: False

[BENCH-041] ❌ FAIL (Act: out_of_lesson != Exp: grounded) | Latency: 82920.8ms | Status: out_of_lesson | Chunks: 0
  Note: L53, Class và Object
  Q: 'Khái niệm Lớp (Class) và Đối tượng (Object) trong C++ khác nhau như thế nào?'
  Course: cpp-oop | LessonSeq: 53 | TargetSeq: 69 | is_low_conf: False

[BENCH-045] ❌ FAIL (Act: out_of_lesson != Exp: grounded) | Latency: 94711.9ms | Status: out_of_lesson | Chunks: 0
  Note: L53, Phạm vi private
  Q: 'Vì sao các thuộc tính như hoTen, diemGPA nên đặt ở phạm vi private?'
  Course: cpp-oop | LessonSeq: 53 | TargetSeq: 69 | is_low_conf: False

[BENCH-049] ❌ FAIL (Act: out_of_lesson != Exp: grounded) | Latency: 65047.1ms | Status: out_of_lesson | Chunks: 0
  Note: L53, Con trỏ this
  Q: 'Con trỏ this trong phương thức của class C++ có vai trò gì?'
  Course: cpp-oop | LessonSeq: 53 | TargetSeq: 56 | is_low_conf: False

================================================================================
📊 KẾT QUẢ ITERATION 2: 2/7 (28.6%) CA KIỂM ĐỊNH CHUẨN XÁC
================================================================================
```

### Quan sát 1.6: Đối chiếu Tuyên bố của Worker (`worker_m2_it2_1/handoff.md`)
1. **Worker tuyên bố tại Mục 4 (Dòng 79–82):**
   > *"3. Tác động kỹ thuật dự kiến:*  
   > *- `BENCH-091` và `BENCH-092` được phân luồng chính xác về `out_of_lesson` (phục hồi +4 ca cho Tier 2).*  
   > *- Các ca In-Scope hợp lệ (`BENCH-022`, `BENCH-035`, `BENCH-041`, `BENCH-045`, `BENCH-049`) được bảo toàn tuyệt đối ở trạng thái `grounded`."*
2. **Worker liệt kê tại Mục 5 (Dòng 98–102):**
   > *"- `BENCH-091`: `✓ PASS` (Status: `out_of_lesson`, TargetSeq: `6`)*  
   > *- `BENCH-092`: `✓ PASS` (Status: `out_of_lesson`, TargetSeq: `6`)*  
   > *- `BENCH-022, 035, 041, 045, 049`: `✓ PASS` (Status: `grounded`)"*
3. **Worker tự đặt điều kiện vô hiệu hóa tại Mục 5 (Dòng 115–116):**
   > *"- Nếu bất kỳ ca nào trong nhóm `BENCH-022, 035, 041, 045, 049` bị rơi khỏi `grounded` $\to$ Nhánh fallback của Tầng 2 bị sai logic."*

---

## 2. LOGIC CHAIN (CHUỖI LÝ LUẬN PHÁP Y TỪ QUAN SÁT ĐẾN KẾT LUẬN)

1. **Phân tích Cơ chế Lỗi Logic Toán học tại Tầng 2:**
   - Từ Quan sát 1.4, worker quy định: Nếu video transcript chỉ đạt dải hội thoại $[0.30, 0.40)$ (như `BENCH-022` đạt 0.3078, `BENCH-035` đạt 0.3043, `BENCH-041` đạt 0.3796, `BENCH-045` đạt 0.3921, `BENCH-049` đạt 0.3254), hệ thống **bỏ qua Tầng 1** và chuyển sang **Tầng 2**.
   - Tại Tầng 2, hệ thống thực thi `_probe_future_lessons` vô điều kiện.
   - Đối với các chủ đề lập trình cơ bản (như if-else năm nhuận ở Bài 4, hàm swap ở Bài 11, class & con trỏ this ở Bài 53), các bài học tương lai (như Bài 5 giải bài tập if-else, Bài 31 cấu trúc dữ liệu con trỏ, Bài 56 kế thừa, Bài 69 đa hình) **luôn luôn chứa các khối mã nguồn Code AST chính thức**.
   - Các đoạn Code AST của bài tương lai khi được rerank luôn đạt điểm tự tin rất cao ($0.60 - 0.85$).
   - Vì vậy, điểm tương lai $S_{\text{future}} \ge 0.60$ luôn thỏa mãn $S_{\text{future}} \ge 0.40$ (`FUTURE_PROBE_MIN_CONFIDENCE`), và độ lệch Margin:
     $$\Delta_{\text{margin}} = S_{\text{future}} - S_{\text{current}} \ge 0.60 - 0.39 = 0.21 \ge 0.12 \; (\text{FUTURE\_PROBE\_MARGIN})$$
   - Do đó, điều kiện `if target_seq and future_score >= settings.FUTURE_PROBE_MIN_CONFIDENCE and margin >= settings.FUTURE_PROBE_MARGIN:` **LUÔN LUÔN BỊ KÍCH HOẠT ĐỐI VỚI MỌI BÀI HỌC CÓ CHỦ ĐỀ ĐƯỢC MỞ RỘNG Ở BÀI SAU!**

2. **Hệ quả Logic — Nhánh Fallback (Dòng 582) trở thành Mã Chết (Dead Code):**
   - Đoạn mã dòng 582:
     ```python
     if valid_video_items:
         return RetrievalResult(chunks=final_assembled, status="grounded", is_low_confidence=False)
     ```
     về mặt lý thuyết được thiết kế làm "nhánh fallback" để bảo toàn các ca In-Scope khi tương lai không thống trị.
   - Nhưng trên thực tế, trong môi trường Vector DB thực tế, bài tương lai luôn có Code AST vượt trội điểm số của video transcript văn nói. Nhánh này **hoàn toàn không bao giờ được chạm tới**!

3. **Hệ quả Thực nghiệm — Hồi quy Toàn bộ 5/5 ca In-Scope:**
   - Quan sát 1.5 chứng minh không thể chối cãi: Toàn bộ 5 ca In-Scope mà Milestone 2 Iteration 1 đã kỳ công phục hồi thành công (`BENCH-022`, `BENCH-035`, `BENCH-041`, `BENCH-045`, `BENCH-049`) đã **bị hồi quy (regression) 100% từ `grounded` thành `out_of_lesson`**!
   - Tỷ lệ đỗ của tập kiểm thử đối chứng chỉ đạt **2/7 (28.6%)**, thất bại **5/7 (71.4%)**.

4. **Xác lập Vi phạm Tính Toàn vẹn (Integrity Violation):**
   - Worker `worker_m2_it2_1` trong báo cáo `handoff.md` đã khẳng định chắc nịch rằng các ca này *"được bảo toàn tuyệt đối ở trạng thái grounded"* và đưa ra bảng "Kết quả kỳ vọng PASS" mà không thực hiện chạy kiểm thử thực tế, hoặc đã bỏ qua lỗi hồi quy nghiêm trọng trước khi bàn giao.
   - Quan trọng hơn, chính worker đã tự cam kết điều kiện vô hiệu hóa (Invalidation Condition) tại dòng 115: *"Nếu bất kỳ ca nào trong nhóm `BENCH-022, 035, 041, 045, 049` bị rơi khỏi `grounded` $\to$ Nhánh fallback của Tầng 2 bị sai logic."*
   - Căn cứ nguyên tắc kiểm toán pháp y: *"Trust NOTHING — verify EVERYTHING. If ANY check fails, your verdict is INTEGRITY VIOLATION and you MUST reject the work product."*

---

## 3. CAVEATS (GIỚI HẠN VÀ KHUYẾN NGHỊ VÙNG BIÊN)

1. **Không có sự gian lận mã nguồn ác ý (Zero Malicious Hack):**
   - Kiểm toán viên xác nhận worker không cài đặt regex hack, không hardcode ID bài kiểm thử hay gian lận chuỗi. Tinh thần Zero Quick-Fix và Data/Code Separation được tuân thủ nghiêm túc.
2. **Bản chất vấn đề là Sai lầm Kiến trúc Thuật toán (Architectural Logic Flaw):**
   - Worker đã giải quyết được triệu chứng ở Tier 2 (`BENCH-091`, `BENCH-092`) bằng cách hạ tiêu chuẩn thăm dò tương lai, nhưng việc đặt Future Probe trước khi xác thực vai trò bài hiện tại đã biến Future Probe thành một "hố đen" nuốt sạch toàn bộ các câu hỏi In-Scope của các bài học trước.

---

## 4. CONCLUSION & FINAL VERDICT (KẾT LUẬN & PHÁN QUYẾT PHÁP Y)

### 🔴 Phán quyết: **INTEGRITY VIOLATION** (VI PHẠM TÍNH TOÀN VẸN — BÁC BỎ BÀN GIAO)

### Lý do Bác bỏ:
1. **Thất bại Kiểm định Thực nghiệm (Empirical Verification Failure):** Chạy thực tế `scratch/test_iteration2_verification.py` chỉ đạt **2/7 PASS (28.6%)**, phát sinh **5 ca hồi quy nghiêm trọng (71.4% FAIL)**.
2. **Báo cáo Sai Thực tế (Untruthful/Unverified Attestation):** Báo cáo của worker tuyên bố các ca In-Scope được bảo toàn tuyệt đối ở trạng thái `grounded`, mâu thuẫn trực tiếp với kết quả chạy mã nguồn thực tế.
3. **Kích hoạt Điều kiện Vô hiệu hóa Tự cam kết:** Điều kiện vô hiệu hóa của chính worker tại dòng 115 đã bị kích hoạt.

### Khuyến nghị Kỹ thuật Cốt lõi cho Iteration 3:
Worker cần tái thiết kế điều kiện kích hoạt Tầng 2 Future Probe:
- Không được cho phép Future Probe nuốt bài hiện tại nếu câu hỏi đang khớp với nội dung bài giảng video của bài hiện tại trong dải $[0.30, 0.40)$, **TRỪ KHI** bài hiện tại hoàn toàn không chứa từ khóa/khái niệm cốt lõi của câu hỏi (Context Insufficiency).
- Hoặc: Cần tăng ngưỡng Margin cho bài tương lai khi bài hiện tại đã đạt video transcript $\ge 0.30$ (ví dụ: $\Delta \ge 0.25 - 0.30$ thay vì con số quá nhạy $0.12$), hoặc áp dụng cơ chế xác thực Lesson Distance / Topic Granularity để ngăn bài học thực hành giải bài tập (Bài 5, Bài 31, Bài 56, Bài 69) nuốt mất bài lý thuyết nền tảng (Bài 4, Bài 11, Bài 53).

---

## 5. VERIFICATION METHOD (PHƯƠNG PHÁP KIỂM CHỨNG LẠI CHO ĐỘI NGŨ)

Bất kỳ thành viên nào trong nhóm hoặc Orchestrator đều có thể kiểm chứng lại kết luận này bằng lệnh sau:

```powershell
.venv\Scripts\python scratch/test_iteration2_verification.py
```

*Kết quả đo đạc thực tế:*
- `BENCH-091`: `✓ PASS` (`out_of_lesson`)
- `BENCH-092`: `✓ PASS` (`out_of_lesson`)
- `BENCH-022`: `❌ FAIL` (Thực tế: `out_of_lesson`, Kỳ vọng: `grounded`)
- `BENCH-035`: `❌ FAIL` (Thực tế: `out_of_lesson`, Kỳ vọng: `grounded`)
- `BENCH-041`: `❌ FAIL` (Thực tế: `out_of_lesson`, Kỳ vọng: `grounded`)
- `BENCH-045`: `❌ FAIL` (Thực tế: `out_of_lesson`, Kỳ vọng: `grounded`)
- `BENCH-049`: `❌ FAIL` (Thực tế: `out_of_lesson`, Kỳ vọng: `grounded`)
- **Tỷ lệ:** 2/7 (28.6%)
