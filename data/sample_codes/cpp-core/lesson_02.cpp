#include <iostream>

using namespace std;

/**
 * Bài 2: Hằng số (Constants) và Thăng cấp kiểu dữ liệu (Type Promotion)
 * Khóa học: cpp-core | Lesson: lesson-02
 */
int main() {
    // 1. Khai báo hằng số (constants) - Không thể thay đổi giá trị trong suốt chương trình
    const int DO_SOI = 100;
    const int DO_DONG = 0;

    cout << "Nhiet do soi cua nuoc: " << DO_SOI << " do C" << endl;
    cout << "Nhiet do dong dac cua nuoc: " << DO_DONG << " do C" << endl;

    // DO_SOI = 105; // Lỗi biên dịch: Không thể gán lại giá trị cho biến const

    // 2. Thăng cấp kiểu dữ liệu (Type Promotion)
    // Khi thực hiện biểu thức giữa kiểu số nguyên (int) và số thực (double),
    // trình biên dịch C++ tự động chuyển đổi sang kiểu dữ liệu lớn hơn (double).
    int a = 8;
    double b = 7.5;

    // a (int) + b (double) -> Kết quả tự động thăng cấp thành double (15.5)
    double tong = a + b;
    cout << "Tong a + b (Type Promotion): " << a << " + " << b << " = " << tong << endl;

    return 0;
}
