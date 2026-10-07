#include <iostream>
using namespace std;

// Khai báo nguyên mẫu hàm (Function Prototype)
int tong(int a, int b);
int min(int a, int b);
void swap(int &a, int &b);

int tong(int a, int b) {
    return a + b;
}

int min(int a, int b) {
    return (a < b) ? a : b;
}

// Hàm hoán đổi giá trị 2 số nguyên sử dụng tham chiếu (swap)
void swap(int &a, int &b) {
    int temp = a;
    a = b;
    b = temp;
}

int main() {
    int x = 10, y = 20;
    cout << "Tong: " << tong(x, y) << endl;
    cout << "Min: " << min(x, y) << endl;
    swap(x, y);
    cout << "Sau swap: x = " << x << ", y = " << y << endl;
    return 0;
}
