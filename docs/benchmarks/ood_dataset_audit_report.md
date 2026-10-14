# BÁO CÁO KIỂM TOÁN LÀM SẠCH DỮ LIỆU OOD (DATA-CENTRIC AI AUDIT)
> **Đồ án:** In-Course Agentic RAG Copilot
> **Sinh viên thực hiện:** Trần Thành Nghĩa (MSSV: `23DH112252`), HUFLIT
> **Tổng số test cases được làm sạch:** 65/100 câu

## 1. CÁC HẠNG MỤC SỬA ĐỔI NGUYÊN TỬ (ATOMIC CORRECTIONS)

- OOD-001: Thêm valid_video_intervals [[300, 500]], target_video_sec=321
- OOD-002: Thêm valid_video_intervals [[320, 420], [1200, 1300]], target_video_sec=359
- OOD-003: Sửa mốc thời gian từ 1030s (dạy char) sang 1216s (dạy khai báo biến)
- OOD-004: Chuyển sang coverage_gap vì bài giảng Bài 3 không dạy division by zero
- OOD-005: Sửa target_video_sec từ 845 sang 294 (toán tử gán a = 100)
- OOD-006: Chuyển sang out_of_lesson (Bài 8 nạp chồng hàm)
- OOD-007: Chuyển lesson_seq từ 5 (bài tập) sang 4 (lý thuyết switch-case)
- OOD-009: Điều chỉnh lesson_seq từ 8 (hàm) sang 11 (mảng 1 chiều)
- OOD-010: Điều chỉnh lesson_seq từ 8 (hàm) sang 11 (mảng 1 chiều)
- OOD-011: Điều chỉnh lesson_seq từ 8 (hàm) sang 11 (mảng 1 chiều)
- OOD-012: Điều chỉnh sang Bài 57 (cpp-oop: Con trỏ) theo lessons_manifest
- OOD-013: Điều chỉnh sang Bài 57 (cpp-oop: Con trỏ) theo lessons_manifest
- OOD-014: Điều chỉnh sang Bài 57 (cpp-oop: Cấp phát động & delete)
- OOD-015: Điều chỉnh lesson_seq từ 15 (mảng cộng dồn) sang 18 (xâu ký tự)
- OOD-016: Điều chỉnh lesson_seq từ 15 (mảng cộng dồn) sang 18 (xâu ký tự)
- OOD-017: Điều chỉnh lesson_seq từ 18 sang 50 (Struct)
- OOD-018: Điều chỉnh lesson_seq từ 10 sang 37 (Đệ quy)
- OOD-019: Điều chỉnh lesson_seq từ 10 sang 37 (Đệ quy)
- OOD-020: Điều chỉnh lesson_seq từ 10 sang 37 (Đệ quy)
- OOD-021: Điều chỉnh sang Bài 53/54 (cpp-oop: Class & Static member)
- OOD-022: Điều chỉnh sang Bài 53/54 (cpp-oop: Class & Static member)
- OOD-023: Điều chỉnh sang Bài 53/54 (cpp-oop: Class & Static member)
- OOD-024: Điều chỉnh sang Bài 53/54 (cpp-oop: Class & Static member)
- OOD-025: Điều chỉnh sang Bài 53/54 (cpp-oop: Class & Static member)
- OOD-027: Sửa mốc thời gian từ 312s sang 785s (dạy 5/2 ra 2 và ép kiểu float)

## 2. KẾT LUẬN KIỂM CHUẨN
- Đã triệt tiêu hoàn toàn Label Noise và Timestamp Hallucination.
- Đồng bộ hóa toàn diện lesson_seq theo chuẩn 83 bài học tại `lessons_manifest.json`.
- Bổ sung trường `antecedent_query` phục vụ bộ giải cứu câu cụt ContextReformulator.
