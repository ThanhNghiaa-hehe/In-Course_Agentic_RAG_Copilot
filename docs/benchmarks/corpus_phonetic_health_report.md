# Báo Cáo Kiểm Toán Sức Khỏe Âm Học Dữ Liệu Toàn Diện 83 Bài Học

**Tác giả:** Trần Thành Nghĩa (MSSV: `23DH112252`), HUFLIT  
**Phương pháp:** Static Corpus Pattern Auditing (Data-Centric AI)  
**Ngày thực hiện:** 31/10/2026  

## 1. Tổng Quan Sức Khỏe Giáo Trình (Corpus Health Summary)

| Chỉ số | Số lượng | Tỷ lệ |
| :--- | :--- | :--- |
| **Tổng bài học** | 83 | 100.0% |
| **Bài học Chuẩn Sạch (CLEAN)** | 67 | 80.7% |
| **Bài học Nhiễu Nhẹ (MINOR 1-3)** | 11 | 13.3% |
| **Bài học Cần Chuẩn Hóa (HIGH > 3)** | 5 | 6.0% |
| **Tổng số dị thường âm học** | **42** | - |

## 2. Chi Tiết Các Bài Học Cần Chuẩn Hóa (Action List)

| Seq | Khóa | Tiêu đề Bài học | Trạng thái | Lỗi phát hiện | Chi tiết mẫu lỗi âm học |
| :---: | :---: | :--- | :---: | :---: | :--- |
| **Bài 11** | `cpp-core` | Bài 11: Mảng một chiều trong C++ & Bài toán thường gặp | **HIGH_NOISE** | **6** | `vòng fo` @ 16:43, `vòng fo` @ 16:43, `vòng fo` @ 16:43, `vòng fo` @ 17:25, `vòng fo` @ 17:25, ... (+1 lỗi khác) |
| **Bài 12** | `cpp-core` | Bài 12: Hướng dẫn giải bài tập Mảng 1 chiều (Phần 1) | **MINOR_NOISE** | **1** | `vòng fo` @ 14:33 |
| **Bài 15** | `cpp-core` | Bài 15: Mảng cộng dồn 1 chiều & 2 chiều - Prefix Sum | **MINOR_NOISE** | **1** | `vòng fo` @ 23:48 |
| **Bài 22** | `cpp-core` | Bài 22: Cấu trúc dữ liệu Set trong C++ - Multiset | **MINOR_NOISE** | **2** | `flow` @ 00:46, `flow` @ 01:26 |
| **Bài 27** | `cpp-core` | Bài 27: Thuật toán sắp xếp chèn, nổi bọt, chọn, đếm | **HIGH_NOISE** | **5** | `vòng lập qua` @ 35:35, `vòng lập qua` @ 36:21, `vòng lập qua` @ 37:06, `vòng lập qua` @ 40:08, `vòng lập qua` @ 40:52 |
| **Bài 28** | `cpp-core` | Bài 28: Thuật toán sắp xếp trộn (Merge Sort) | **HIGH_NOISE** | **5** | `vòng lập qua` @ 11:56, `vòng lập qua` @ 11:56, `vòng lập qua` @ 11:56, `vòng lập qua` @ 12:40, `vòng lập qua` @ 12:40 |
| **Bài 30** | `cpp-core` | Bài 30: Sắp xếp nhanh QuickSort - Lomuto & Hoare | **MINOR_NOISE** | **1** | `vòng lập qua` @ 39:17 |
| **Bài 33** | `cpp-core` | Bài 33: Hướng dẫn giải bài tập Sắp xếp và Tìm kiếm (P2) | **MINOR_NOISE** | **1** | `flow` @ 01:27 |
| **Bài 35** | `cpp-core` | Bài 35: Kiến thức toán & Lý thuyết số (Phần 2) | **MINOR_NOISE** | **3** | `vòng lập qua` @ 15:11, `vòng lập qua` @ 22:26, `vòng lập qua` @ 23:06 |
| **Bài 39** | `cpp-core` | Bài 39: Giải bài tập Xâu kí tự trong C++ (Phần 2) | **MINOR_NOISE** | **1** | `vòng lập qua` @ 54:47 |
| **Bài 43** | `cpp-core` | Bài 43: Cấu trúc dữ liệu Ngăn xếp (Stack) trong C++ | **MINOR_NOISE** | **1** | `vòng lập qua` @ 27:36 |
| **Bài 45** | `cpp-core` | Bài 45: Hàng đợi hai đầu (Deque in C++) | **MINOR_NOISE** | **3** | `vòng lập qua` @ 26:09, `vòng lập qua` @ 26:09, `vòng lập qua` @ 26:48 |
| **Bài 48** | `cpp-core` | Bài 48: Kỹ thuật hai con trỏ (Two Pointers) | **MINOR_NOISE** | **1** | `vòng lập qua` @ 15:04 |
| **Bài 62** | `cpp-oop` | Bài 62: Chữa đề thi thử lập trình C++ PTIT Test 3 | **HIGH_NOISE** | **4** | `vòng fo` @ 06:33, `vòng fo` @ 06:33, `vòng fo` @ 07:19, `vòng fo` @ 07:19 |
| **Bài 65** | `cpp-oop` | Bài 65: Hướng dẫn C++ Final Test 1 - Giải đề cuối kỳ | **HIGH_NOISE** | **5** | `vòng lập qua` @ 02:22, `vòng lập qua` @ 02:22, `vòng fo` @ 03:13, `vòng lập qua` @ 03:13, `vòng lập qua` @ 03:13 |
| **Bài 75** | `cpp-oop` | Bài 75: Lập trình Hướng Đối Tượng OOP Phần 1 (Update 2025) | **MINOR_NOISE** | **2** | ` đáp bồ` @ 20:13, ` đáp bồ` @ 20:57 |

## 3. Danh Sách Bài Học Đã Chuẩn Sạch Hoàn Toàn (CLEAN)

Bài 1, Bài 2, Bài 3, Bài 4, Bài 5, Bài 6, Bài 7, Bài 8, Bài 9, Bài 10, Bài 13, Bài 14, Bài 16, Bài 17, Bài 18, Bài 19, Bài 20, Bài 21, Bài 23, Bài 24, Bài 25, Bài 26, Bài 29, Bài 31, Bài 32, Bài 34, Bài 36, Bài 37, Bài 38, Bài 40, Bài 41, Bài 42, Bài 44, Bài 46, Bài 47, Bài 49, Bài 50, Bài 51, Bài 52, Bài 53, Bài 54, Bài 55, Bài 56, Bài 57, Bài 58, Bài 59, Bài 60, Bài 61, Bài 63, Bài 64, Bài 66, Bài 67, Bài 68, Bài 69, Bài 70, Bài 71, Bài 72, Bài 73, Bài 74, Bài 76, Bài 77, Bài 78, Bài 79, Bài 80, Bài 81, Bài 82, Bài 83
