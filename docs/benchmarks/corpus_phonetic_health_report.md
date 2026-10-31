# Báo Cáo Kiểm Toán Sức Khỏe Âm Học Dữ Liệu Toàn Diện 83 Bài Học

**Tác giả:** Trần Thành Nghĩa (MSSV: `23DH112252`), HUFLIT  
**Phương pháp:** Static Corpus Pattern Auditing (Data-Centric AI)  
**Ngày thực hiện:** 31/10/2026  

## 1. Tổng Quan Sức Khỏe Giáo Trình (Corpus Health Summary)

| Chỉ số | Số lượng | Tỷ lệ |
| :--- | :--- | :--- |
| **Tổng bài học** | 83 | 100.0% |
| **Bài học Chuẩn Sạch (CLEAN)** | 41 | 49.4% |
| **Bài học Nhiễu Nhẹ (MINOR 1-3)** | 29 | 34.9% |
| **Bài học Cần Chuẩn Hóa (HIGH > 3)** | 13 | 15.7% |
| **Tổng số dị thường âm học** | **208** | - |

## 2. Chi Tiết Các Bài Học Cần Chuẩn Hóa (Action List)

| Seq | Khóa | Tiêu đề Bài học | Trạng thái | Lỗi phát hiện | Chi tiết mẫu lỗi âm học |
| :---: | :---: | :--- | :---: | :---: | :--- |
| **Bài 2** | `cpp-core` | Bài 2: Làm quen C++, Vào Ra & Kiểu dữ liệu, Biến | **HIGH_NOISE** | **15** | `thẳng đáp bồ` @ 14:48, `thẳng đáp bồ` @ 14:48, `thẳng đáp bồ` @ 14:48, `flow đáp bồ` @ 14:55, `flow` @ 14:55, ... (+10 lỗi khác) |
| **Bài 5** | `cpp-core` | Bài 5: Giải bài tập If Else & Kiểm tra Năm Nhuận | **HIGH_NOISE** | **6** | ` đắp bồ` @ 12:02, ` đắp bồ` @ 12:04, ` đáp bồ` @ 14:33, ` đáp bồ` @ 14:38, ` đáp bồ` @ 21:55, ... (+1 lỗi khác) |
| **Bài 6** | `cpp-core` | Bài 6: Vòng lặp For, While và Do-While | **HIGH_NOISE** | **50** | `vòng lập 4` @ 01:25, `vòng lập 4` @ 01:40, `vòng là con` @ 02:29, `vòng fo` @ 02:54, `vòng là fo` @ 03:03, ... (+45 lỗi khác) |
| **Bài 10** | `cpp-core` | Bài 10: Phân tích độ phức tạp của thuật toán | **HIGH_NOISE** | **13** | `vòng fo` @ 07:09, `vòng fo` @ 07:09, `vòng fo` @ 07:09, `vòng fo` @ 07:30, `vòng fo` @ 07:49, ... (+8 lỗi khác) |
| **Bài 11** | `cpp-core` | Bài 11: Mảng một chiều trong C++ & Bài toán thường gặp | **MINOR_NOISE** | **3** | `vòng fo` @ 17:25, `vòng fo` @ 17:25, `vòng fo` @ 17:25 |
| **Bài 12** | `cpp-core` | Bài 12: Hướng dẫn giải bài tập Mảng 1 chiều (Phần 1) | **MINOR_NOISE** | **1** | `vòng fo` @ 14:49 |
| **Bài 15** | `cpp-core` | Bài 15: Mảng cộng dồn 1 chiều & 2 chiều - Prefix Sum | **MINOR_NOISE** | **1** | `vòng fo` @ 24:10 |
| **Bài 18** | `cpp-core` | Bài 18: Xâu ký tự trong C++ - Cách sử dụng String | **HIGH_NOISE** | **4** | `flow` @ 25:49, `che` @ 26:33, `che` @ 26:40, `che` @ 26:46 |
| **Bài 22** | `cpp-core` | Bài 22: Cấu trúc dữ liệu Set trong C++ - Multiset | **MINOR_NOISE** | **1** | `flow` @ 01:34 |
| **Bài 27** | `cpp-core` | Bài 27: Thuật toán sắp xếp chèn, nổi bọt, chọn, đếm | **MINOR_NOISE** | **3** | `vòng lập qua` @ 36:31, `vòng lập qua` @ 37:43, `vòng lập qua` @ 40:52 |
| **Bài 28** | `cpp-core` | Bài 28: Thuật toán sắp xếp trộn (Merge Sort) | **MINOR_NOISE** | **3** | `vòng lập qua` @ 12:37, `vòng lập qua` @ 12:40, `vòng lập qua` @ 12:44 |
| **Bài 30** | `cpp-core` | Bài 30: Sắp xếp nhanh QuickSort - Lomuto & Hoare | **MINOR_NOISE** | **1** | `vòng lập qua` @ 39:46 |
| **Bài 32** | `cpp-core` | Bài 32: Hướng dẫn giải bài tập Sắp xếp và Tìm kiếm (P1) | **MINOR_NOISE** | **1** | `trè` @ 14:52 |
| **Bài 33** | `cpp-core` | Bài 33: Hướng dẫn giải bài tập Sắp xếp và Tìm kiếm (P2) | **MINOR_NOISE** | **3** | `flow` @ 01:52, `che` @ 07:00, `che` @ 62:16 |
| **Bài 34** | `cpp-core` | Bài 34: Kiến thức toán & Lý thuyết số (Phần 1) | **HIGH_NOISE** | **7** | `che` @ 03:27, `che` @ 03:27, `vòng fo` @ 07:41, `vòng fo` @ 23:00, `vòng lập qua` @ 37:53, ... (+2 lỗi khác) |
| **Bài 35** | `cpp-core` | Bài 35: Kiến thức toán & Lý thuyết số (Phần 2) | **MINOR_NOISE** | **2** | `vòng lập qua` @ 15:37, `vòng lập qua` @ 23:12 |
| **Bài 37** | `cpp-core` | Bài 37: Kỹ thuật đệ quy trong C++ & Cách hàm hoạt động | **MINOR_NOISE** | **1** | `trè` @ 00:29 |
| **Bài 38** | `cpp-core` | Bài 38: Giải bài tập Xâu kí tự trong C++ (Phần 1) | **MINOR_NOISE** | **1** | `che` @ 41:04 |
| **Bài 39** | `cpp-core` | Bài 39: Giải bài tập Xâu kí tự trong C++ (Phần 2) | **MINOR_NOISE** | **1** | `vòng lập qua` @ 55:29 |
| **Bài 41** | `cpp-core` | Bài 41: Thuật toán sinh kế tiếp - Nhị phân, Hoán vị | **HIGH_NOISE** | **4** | `Vòng lập qua` @ 10:05, `vòng lập qua` @ 10:14, `vòng lập qua` @ 28:36, `vòng lập qua` @ 45:11 |
| **Bài 42** | `cpp-core` | Bài 42: Hướng dẫn giải bài tập Thuật toán sinh kế tiếp | **MINOR_NOISE** | **2** | `che` @ 16:27, `trè` @ 48:46 |
| **Bài 43** | `cpp-core` | Bài 43: Cấu trúc dữ liệu Ngăn xếp (Stack) trong C++ | **MINOR_NOISE** | **1** | `vòng lập qua` @ 27:51 |
| **Bài 45** | `cpp-core` | Bài 45: Hàng đợi hai đầu (Deque in C++) | **MINOR_NOISE** | **2** | `vòng lập qua` @ 26:35, `vòng lập qua` @ 26:56 |
| **Bài 47** | `cpp-core` | Bài 47: Kỹ thuật cửa sổ trượt (Sliding Window) | **MINOR_NOISE** | **1** | `che` @ 07:15 |
| **Bài 48** | `cpp-core` | Bài 48: Kỹ thuật hai con trỏ (Two Pointers) | **MINOR_NOISE** | **1** | `vòng lập qua` @ 15:44 |
| **Bài 54** | `cpp-oop` | Bài 54: Giải bài tập OOP Phần 1 & Static Member | **MINOR_NOISE** | **1** | ` đắp bồ` @ 12:06 |
| **Bài 55** | `cpp-oop` | Bài 55: Giải bài tập OOP Phần 2 & Class NhanVien | **HIGH_NOISE** | **4** | `si in` @ 25:39, `si in` @ 25:39, `si in` @ 25:44, `si in` @ 40:29 |
| **Bài 56** | `cpp-oop` | Bài 56: Kế Thừa & Nạp Chồng Toán Tử >>, << | **MINOR_NOISE** | **1** | `che` @ 38:20 |
| **Bài 57** | `cpp-oop` | Bài 57: Lý thuyết về con trỏ trong C++ - Mảng & Con trỏ | **HIGH_NOISE** | **4** | ` đắp bồ` @ 14:56, ` đắp bồ` @ 15:06, ` đắp bồ` @ 15:10, ` đắp bồ` @ 15:22 |
| **Bài 58** | `cpp-oop` | Bài 58: Danh sách liên kết đơn trong C++ - QLSV | **HIGH_NOISE** | **4** | `vòng lập qua` @ 16:10, `vòng lập qua` @ 40:01, `vòng lập qua` @ 40:52, `vòng lập qua` @ 56:26 |
| **Bài 59** | `cpp-oop` | Bài 59: Thuật toán quay lui - Bài toán N quân hậu | **HIGH_NOISE** | **19** | `vòng fo` @ 09:49, `vòng fo` @ 09:54, `vòng fo` @ 09:54, `vòng fo` @ 10:04, `vòng fo` @ 10:11, ... (+14 lỗi khác) |
| **Bài 62** | `cpp-oop` | Bài 62: Chữa đề thi thử lập trình C++ PTIT Test 3 | **MINOR_NOISE** | **2** | `vòng fo` @ 07:26, `vòng fo` @ 07:30 |
| **Bài 64** | `cpp-oop` | Bài 64: Mảng 1 chiều, Lý thuyết con trỏ, Vector & Iterator | **MINOR_NOISE** | **1** | `che` @ 26:40 |
| **Bài 65** | `cpp-oop` | Bài 65: Hướng dẫn C++ Final Test 1 - Giải đề cuối kỳ | **MINOR_NOISE** | **3** | `vòng lập qua` @ 03:16, `vòng lập qua` @ 03:22, `vòng fo` @ 03:38 |
| **Bài 67** | `cpp-oop` | Bài 67: Mảng 1 chiều & Vòng lặp Range Based For Loop | **HIGH_NOISE** | **12** | `vòng fo` @ 16:11, `vòng fo` @ 16:36, `vòng fo` @ 16:38, `Vòng fo` @ 19:24, `vòng fo` @ 19:24, ... (+7 lỗi khác) |
| **Bài 71** | `cpp-oop` | Bài 71: Xâu ký tự trong C++ & Kỹ năng xử lý bài tập xâu | **MINOR_NOISE** | **3** | `che` @ 39:46, `trè` @ 43:51, `trè` @ 66:34 |
| **Bài 72** | `cpp-oop` | Bài 72: Xâu ký tự (String) & Các dạng bài tập xâu quan trọng | **MINOR_NOISE** | **3** | `si in` @ 03:41, `si in` @ 03:51, `si in` @ 04:15 |
| **Bài 75** | `cpp-oop` | Bài 75: Lập trình Hướng Đối Tượng OOP Phần 1 (Update 2025) | **MINOR_NOISE** | **3** | ` đắp bồ` @ 18:12, ` đáp bồ` @ 21:11, ` đắp bồ` @ 52:45 |
| **Bài 76** | `cpp-oop` | Bài 76: Thuật toán quay lui và bài tập áp dụng (Update 2025) | **HIGH_NOISE** | **15** | `vòng fo` @ 07:40, `vòng fo` @ 07:40, `vòng fo` @ 07:46, `vòng fo` @ 07:48, `vòng fo` @ 09:02, ... (+10 lỗi khác) |
| **Bài 77** | `cpp-oop` | Bài 77: Set & Map trong C++ (2025) | **MINOR_NOISE** | **1** | `che` @ 27:44 |
| **Bài 78** | `cpp-oop` | Bài 78: Cấu trúc rẽ nhánh If Else và Switch Case (2025) | **MINOR_NOISE** | **2** | `che` @ 104:07, `che` @ 104:24 |
| **Bài 83** | `cpp-oop` | Bài 83: Lập trình Hướng đối tượng OOP (2026) | **MINOR_NOISE** | **2** | ` đắp bồ` @ 19:26, ` đắp bồ` @ 19:26 |

## 3. Danh Sách Bài Học Đã Chuẩn Sạch Hoàn Toàn (CLEAN)

Bài 1, Bài 3, Bài 4, Bài 7, Bài 8, Bài 9, Bài 13, Bài 14, Bài 16, Bài 17, Bài 19, Bài 20, Bài 21, Bài 23, Bài 24, Bài 25, Bài 26, Bài 29, Bài 31, Bài 36, Bài 40, Bài 44, Bài 46, Bài 49, Bài 50, Bài 51, Bài 52, Bài 53, Bài 60, Bài 61, Bài 63, Bài 66, Bài 68, Bài 69, Bài 70, Bài 73, Bài 74, Bài 79, Bài 80, Bài 81, Bài 82
