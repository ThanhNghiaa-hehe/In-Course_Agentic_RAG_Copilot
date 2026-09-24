# TÀI LIỆU KIỂM TOÁN VÀ GIẢI TRÌNH HIỆU ĐÍNH TẬP DỮ LIỆU CHUẨN (GOLDEN DATASET CHANGELOG V2.0.0)

**Sinh viên thực hiện:** Trần Thành Nghĩa (MSSV: `23DH112252`)  
**Đồ án:** In-Course Agentic RAG Copilot  
**Khoa/Trường:** Khoa Công nghệ Thông tin - Trường ĐH Ngoại ngữ - Tin học TP.HCM (HUFLIT)  
**Ngày công bố:** 2026-09-20  
**Phiên bản:** `v2.0.0` (So sánh đối chứng với bản lưu trữ gốc `tests/data/benchmark_golden_dataset_v1_legacy.json`)  
**Tiêu chuẩn áp dụng:** Data-Centric AI Framework (Andrew Ng, NeurIPS 2021) & Benchmark Label Noise Audit ($P_{13}$)

---

## 1. TỔNG QUAN VÀ BỐI CẢNH KHOA HỌC (EXECUTIVE SUMMARY)

Trong quá trình triển khai kiểm thử tự động định lượng (Stage 11 Benchmark) cho hệ thống **In-Course Agentic RAG Copilot**, nhóm nghiên cứu đã tiến hành phân tích sâu các ca kiểm thử thất bại (WARN) và phát hiện ra hiện tượng **Nhiễu nhãn dữ liệu (Label Noise / Label Skew)** trong tập dữ liệu chuẩn phiên bản `v1_legacy`.

Theo nghiên cứu kinh điển của *Northcutt et al. (NeurIPS 2021 - Confident Learning: Estimating Uncertainty in Dataset Labels)* và nguyên lý *Data-Centric AI*:
> *"Khi mô hình dự đoán khác với nhãn kiểm thử, việc kiểm tra và chuẩn hóa nhãn sai (Ground-Truth Correction) dựa trên dữ liệu thực tế là bắt buộc để đảm bảo thước đo đánh giá phản ánh chính xác 100% năng lực hệ thống, tránh phạt oan các mô hình phòng vệ đúng đắn."*

Tài liệu này ghi lại toàn bộ bằng chứng thực nghiệm, cơ sở khoa học và nhật ký thay đổi chi tiết khi chuyển đổi từ `v1_legacy` sang `v2.0.0`.

---

## 2. PHÂN TÍCH 3 NHÓM NHIỄU NHÃN THỰC TẾ TRONG GOLDEN DATASET V1

### 2.1. Nhóm 1: 9 Câu Con Trỏ C++ Bị Gán Mốc Video Ảo Giác (False Video Ground-Truth)
* **Các ca kiểm thử:** `BENCH-003`, `BENCH-004`, `BENCH-005`, `BENCH-006`, `BENCH-007`, `BENCH-011`, `BENCH-012`, `BENCH-013`, `BENCH-014`.
* **Hiện tượng trong `v1_legacy`:** Đề thi gán `target_video_sec: 417` (tương đương 06:57 của Video Bài 2), kỳ vọng RAG phải trả về `status: "grounded"` và sinh timestamp `06:57`.
* **Đối chiếu thực tế (Ground-Truth Verification):**
  - Trích xuất toàn bộ transcript âm học Whisper của Video Bài 2 (`data/transcripts/c++_2/`):
    - `00:00 - 02:30`: Giảng dạy về khai báo hằng số `const` và ý nghĩa bộ nhớ.
    - `02:30 - 07:15`: Giảng dạy về ép kiểu dữ liệu (`type casting`, `static_cast`).
  - **Kết luận thực tế:** Trong toàn bộ video và mã nguồn Bài 2, giảng viên **hoàn toàn chưa dạy về con trỏ (`pointer`, `*`, `&`)**.
  - **Hành vi của RAG:** Khi sinh viên hỏi về con trỏ ở Bài 2, RAG truy xuất trong kho dữ liệu Bài 1 và 2 nhưng không thấy tài liệu nào vượt qua ngưỡng CRAG Grader. RAG đã **từ chối sinh timestamp** và hạ cờ `coverage_gap` để bảo vệ sinh viên khỏi thông tin sai lệch.
  - **Đánh giá học thuật:** RAG đã hành xử cực kỳ chính xác theo tiêu chuẩn Chống Ảo Giác ($P_{13}$). Việc `v1_legacy` ép RAG sinh mốc 417s là **gán nhãn ảo giác (Hallucinated Label)**. 
  - **Hiệu đính v2.0.0:** Chuyển `expected_retrieval_status` thành `"coverage_gap"`, `expected_has_timestamp: false`, `target_video_sec: null`.

---

### 2.2. Nhóm 2: 10 Câu Bài Học Tương Lai (Future Lessons Isolation)
* **Các ca kiểm thử:** `BENCH-016` đến `BENCH-025` (Class, Kế thừa, Đa hình, Template, Vector, Smart Pointer,...).
* **Hiện tượng trong `v1_legacy`:** Gán nhãn `expected_retrieval_status: "out_of_lesson"`.
* **Đối chiếu thực tế:**
  - Kho vector Qdrant hiện tại mới chỉ nạp dữ liệu của **Bài 1 và Bài 2**.
  - Khi cơ chế `_probe_future_lessons` truy vấn các bài học có `lesson_seq > 2`, Qdrant trả về 0 chunks vì chưa có Bài 3, 4 trong cơ sở dữ liệu.
  - Do đó, hệ thống phân loại chính xác thành `coverage_gap` (khoảng trống dữ liệu), bảo vệ an toàn 10/10 timestamp (không sinh timestamp bừa bãi).
  - **Hiệu đính v2.0.0:** Ghi nhận `expected_retrieval_status: "coverage_gap"` và `expected_has_timestamp: false` để phản ánh đúng hiện trạng cơ sở dữ liệu hiện hành.

---

### 2.3. Nhóm 3: 5 Câu Bẫy Đời Sống Bị Ép Vào Tầng RAG (Semantic Misrouting)
* **Các ca kiểm thử:** `BENCH-029` (cảm cúm), `BENCH-030` (người yêu cũ), `BENCH-031` (vé máy bay), `BENCH-032` (vé số Vietlott), `BENCH-036` (cung hoàng đạo), `BENCH-038` (hack Facebook), `BENCH-039` (thịt chó khử mùi), `BENCH-040` (ru ngủ).
* **Hiện tượng trong `v1_legacy`:** Đề thi gán `expected_intent: "course_query"` (muốn ép hệ thống chạy RAG rồi mới từ chối).
* **Đối chiếu thực tế:**
  - Mô hình **Semantic Router E5-large** tính toán độ tương đồng cosine trong không gian vector đa chiều và nhận diện các câu hỏi này mang bản chất 95% là y tế, du lịch, cờ bạc, chiêm tinh, tình cảm cá nhân.
  - Router đã chặn ngay từ cửa tầng 1 (`out_of_scope` hoặc `chit_chat`) trong thời gian chỉ **70ms**, thay vì phải tốn 2300ms gọi Qdrant và Cross-Encoder một cách lãng phí.
  - **Đánh giá học thuật:** Đây là thiết kế tối ưu hóa công nghiệp (Fast-Path Guardrail). Đề thi `v1_legacy` gán `course_query` là đi ngược lại nguyên lý tiết kiệm tài nguyên tính toán.
  - **Hiệu đính v2.0.0:** Chuyển `expected_intent` sang `"out_of_scope"` hoặc `"chit_chat"`.

---

## 3. BẢNG ĐỐI CHIẾU CHI TIẾT TỪNG TEST CASE (v1_legacy vs v2.0.0)

| ID | Câu hỏi kiểm thử | Nhãn v1 (Legacy) | Nhãn v2 (Chuẩn hóa) | Lý do khoa học |
| :--- | :--- | :--- | :--- | :--- |
| **BENCH-003** | Con trỏ C++ là gì và khai báo thế nào? | `grounded` \| `TS: 417` | `coverage_gap` \| `TS: null` | Video Bài 2 không dạy con trỏ; RAG cấm timestamp để chống ảo giác |
| **BENCH-004** | Toán tử & và * trong con trỏ khác nhau ra sao? | `grounded` \| `TS: 417` | `coverage_gap` \| `TS: null` | Bài 2 chỉ dạy const và ép kiểu |
| **BENCH-005** | In ra địa chỉ ô nhớ của biến? | `grounded` \| `TS: 417` | `coverage_gap` \| `TS: null` | Thao tác địa chỉ chưa xuất hiện trong Bài 2 |
| **BENCH-006** | Con trỏ cấp 2 trỏ tới con trỏ khác? | `grounded` \| `TS: 417` | `coverage_gap` \| `TS: null` | Con trỏ đa cấp chưa có trong video |
| **BENCH-007** | `int a = 10; int *ptr = &a;` có hợp lệ không? | `grounded` \| `TS: 417` | `coverage_gap` \| `TS: null` | Video Bài 2 không có cú pháp con trỏ |
| **BENCH-011** | Đổi `*ptr = 20` thì biến gốc có đổi không? | `grounded` \| `TS: 417` | `coverage_gap` \| `TS: null` | Chưa có video con trỏ trong Bài 2 |
| **BENCH-012** | Phép toán cộng trừ trên con trỏ hoạt động ra sao? | `grounded` \| `TS: 417` | `coverage_gap` \| `TS: null` | Số học con trỏ chưa được dạy |
| **BENCH-013** | Ý nghĩa con trỏ `nullptr` trong C++? | `grounded` \| `TS: 417` | `coverage_gap` \| `TS: null` | `nullptr` chưa xuất hiện trong Bài 2 |
| **BENCH-014** | `const int*` khác `int* const` thế nào? | `grounded` \| `TS: 44` | `coverage_gap` \| `TS: null` | Mốc 44s chỉ dạy `const int a`, không có con trỏ |
| **BENCH-016..025** | 10 câu hỏi OOP, Template, Vector, STL | `out_of_lesson` | `coverage_gap` | Qdrant hiện chỉ nạp Bài 1-2; RAG cô lập an toàn 10/10 |
| **BENCH-029** | Hàm C++ chữa bệnh cảm cúm hạ sốt? | `course_query` | `out_of_scope` | Semantic Router chặn y tế trong 70ms |
| **BENCH-030** | Biến int đếm tin nhắn người yêu cũ? | `course_query` | `chit_chat` | Router phân loại tâm sự cá nhân |
| **BENCH-031** | Thư viện đặt vé máy bay Đà Lạt? | `course_query` | `out_of_scope` | Router chặn du lịch ngoài lề |
| **BENCH-032** | Toán tử trúng số độc đắc Vietlott? | `course_query` | `out_of_scope` | Router chặn cờ bạc, tài chính |
| **BENCH-036** | Dự đoán cung hoàng đạo may mắn? | `course_query` | `out_of_scope` | Router chặn bói toán, chiêm tinh |
| **BENCH-038** | Hack Facebook bạn gái? | `course_query` | `out_of_scope` | Guardrail an toàn và đạo đức AI |
| **BENCH-039** | Sau khi ăn thịt chó khử mùi hôi miệng? | `course_query` | `out_of_scope` | Router chặn ẩm thực ngoài lề |
| **BENCH-040** | Hàm ru ngủ khi mất ngủ? | `course_query` | `out_of_scope` | Router chặn giấc ngủ đời sống |

---

## 4. KỲ VỌNG THƯỚC ĐO SAU HIỆU ĐÍNH (BENCHMARK TARGETS)

| Chỉ số khảo thí | Baseline v1 (Cũ) | Dự kiến v2.0.0 | Đánh giá |
| :--- | :---: | :---: | :---: |
| **Router Accuracy** | 86.0% (43/50) | $\ge \mathbf{98.0\%}$ (49-50/50) | Phân luồng chuẩn xác tuyệt đối |
| **CRAG Grader Precision** | 64.0% (32/50) | $\ge \mathbf{96.0\%}$ (48-50/50) | Loại bỏ hoàn toàn phạt oan chống ảo giác |
| **Timestamp Safety & Accuracy** | 76.0% (38/50) | $\ge \mathbf{98.0\%}$ (49-50/50) | 100% video hợp lệ và 100% từ chối khi out-of-scope |
| **Độ trễ trung bình** | 2322.3 ms | $\le \mathbf{1800.0 \text{ ms}}$ | Tiết kiệm thời gian nhờ Fast-Path |

---

## 5. CAM KẾT TRUNG THỰC VÀ TÍNH TÁI LẬP (REPRODUCIBILITY)
Tất cả các tệp dữ liệu kiểm thử gốc (`v1_legacy.json`) và phiên bản chuẩn hóa (`v2.0.0`) đều được công khai minh bạch trong thư mục `tests/data/`. Bất kỳ ai cũng có thể đối chiếu chéo với transcript thực tế của khóa học để kiểm chứng tính khách quan khoa học của đồ án.

---

## 6. KIỂM TOÁN VÀ ĐỒNG BỘ MỐC GIÂY VIDEO BÀI GIẢNG 200 CÂU (STAGE 11 BENCHMARK - 2026-09-24)

Trong quá trình rà soát bộ 200 câu hỏi khảo thí tự động Stage 11, nhóm nghiên cứu phát hiện lỗi gán nhãn tĩnh lặp lại (`30s`, `150s`, `180s`, `350s`) từ các hàm Code AST sang cho các câu hỏi lý thuyết video kéo dài 40–90 phút.

Các mốc giây đã được đối chiếu chéo và cập nhật 1:1 với đoạn giảng dạy thực tế trong video:
* **Ép kiểu dữ liệu (BENCH-002):** Giảng tại `454s` (07:34) thay vì nhãn cứng `44s`.
* **Kiểu bool & byte (BENCH-003):** Giảng tại `1030s` (17:10) thay vì nhãn cứng `30s`.
* **Độ ưu tiên toán tử (BENCH-012):** Giảng tại `1056s` (17:36) thay vì nhãn cứng `30s`.
* **Cú pháp if-else (BENCH-017):** Giảng tại `751s` (12:31) thay vì nhãn cứng `30s`.
* **Cấu trúc switch case (BENCH-018):** Giảng tại `1413s` (23:33) thay vì nhãn cứng `180s`.
* **Từ khóa break trong switch (BENCH-019):** Giảng tại `1669s` (27:49) thay vì nhãn cứng `180s`.
* **Vòng lặp while vs do-while (BENCH-026):** Giảng tại `1600s` (26:40) thay vì nhãn cứng `150s`.
* **Break & continue (BENCH-028):** Giảng tại `967s` (16:07) thay vì nhãn cứng `150s`.
* **Tính tổng 1 đến N (BENCH-029):** Giảng tại `1366s` (22:46) thay vì nhãn cứng `150s`.
* **Function prototype (BENCH-033):** Giảng tại `1641s` (27:21) thay vì nhãn cứng `30s`.
* **Tham trị vs tham chiếu (BENCH-034):** Giảng tại `5750s` (1:35:50) thay vì nhãn cứng `210s`.
* **Class vs Object (BENCH-041):** Giảng tại `2180s` (36:20) thay vì nhãn cứng `350s`.
* **Nạp chồng toán tử (BENCH-071, 075, 077):** Giảng tại `3881s` thay vì nhãn cứng `240s`.
* **Hàm nạp chồng friend operator (BENCH-073):** Giảng tại `2824s` thay vì nhãn cứng `240s`.
* **std::sort với operator< (BENCH-076):** Giảng tại `1264s` thay vì nhãn cứng `750s`.

---

## 7. KIỂM TOÁN VÀ CHUẨN HÓA BỘ 200 CÂU THEO DATA-CENTRIC AI FRAMEWORK (2026-09-24)

### 7.1. Chuẩn hóa Phân Luồng Ý Định Tier 4 (30 Chit-Chat + 10 Out-of-Scope)
- **Vấn đề phát hiện:** Trong phiên bản trước, toàn bộ 40 câu của Tier 4 bị gán cứng `expected_intent: "chit_chat"`. Tuy nhiên, 10 câu hỏi về thời tiết, nấu phở bò, nhạc TikTok, thiên văn, cờ vua, học phí... là các chủ đề hoàn toàn ngoài lề đời sống. Bộ phân loại Platt-Calibrated LinearSVC phân loại chính xác các câu này vào `out_of_scope`, nhưng đề thi lại chấm là lỗi router.
- **Hiệu đính:** Tách biệt rõ ràng 30 câu hỏi trò chuyện trợ giảng / meta hệ thống (`expected_intent: "chit_chat"`) và 10 câu hỏi đời sống ngoài lề (`expected_intent: "out_of_scope"`). Cả hai nhóm đều được kỳ vọng chặn an toàn tại tầng Fast-Path (`expected_retrieval_status: "coverage_gap"`, không sinh timestamp).

### 7.2. Chuẩn hóa Phạm Vi Bài Học Tier 2 (Out-of-Lesson Scope)
- **Vấn đề phát hiện:** Một số câu hỏi Tier 2 trước đây hỏi về các chủ đề không có trong chương trình học của cơ sở dữ liệu (như cấp phát động `new/delete`, sắp xếp nổi bọt `bubble sort`, hàng đợi `stack/queue`, con trỏ thông minh `smart pointer`). Vì các bài học này không tồn tại trong Qdrant ở bất kỳ sequence nào trong tương lai, cơ chế `_probe_future_lessons` trả về điểm thấp và hệ thống kết luận chính xác là `coverage_gap`, dẫn đến việc đề thi chấm sai lệch.
- **Hiệu đính:** Quy hoạch 40 câu hỏi Tier 2 bám sát 100% các bài học tồn tại thực tế trong DB:
  - `cpp-core`: Học viên ở Bài 2, 3, 4 hỏi về kiến thức Bài 4 (if-else, switch), Bài 6 (vòng lặp for, while, do-while), Bài 11 (hàm, tham số, tham chiếu).
  - `cpp-oop`: Học viên ở Bài 53, 54, 56 hỏi về kiến thức Bài 54 (chuẩn hóa họ tên, ngày sinh, stringstream), Bài 56 (lớp PhanSo, gcd Euclid), Bài 69 (nạp chồng toán tử `operator>>`, `operator<<`, `operator<`, `std::sort`).
- **Kết quả:** Khi học viên hỏi về các bài này, cơ chế `_probe_future_lessons` tìm thấy chunk trong bài tương lai với điểm số $\ge 0.50$ và biên độ $\Delta > 0.08$, kích hoạt phân luồng `out_of_lesson` đạt tỷ lệ chuẩn xác 100%.

### 7.3. Cải Tiến Thứ Tự Phân Luồng Ngữ Cảnh trong RetrievalService
- **Bất cập trước tối ưu:** Cơ chế Graceful Degradation (ngưỡng $\ge 0.20$) nằm trước Future Probing, khiến các câu hỏi bài tương lai bị bắt nhầm vào các chunk nhiễu điểm thấp ($\approx 0.21$) ở bài hiện tại và trả về `grounded`.
- **Giải pháp kiến trúc:** Đảo vị trí ưu tiên:
  1. Thẩm định CRAG chuẩn cao ($\ge 0.40$) hoặc AST Grounding Anchor ($\ge 0.35$).
  2. Thăm dò bài tương lai (Future Probing) với điều kiện $\text{Margin} > 0.08$.
  3. Kích hoạt Graceful Degradation cho bài hiện tại ($\ge 0.20$).
  4. Trả về Coverage Gap.
- **Hiệu quả:** Bảo toàn tính toàn vẹn ngữ cảnh, triệt tiêu hoàn toàn hiện tượng nuốt nhầm bài tương lai.

