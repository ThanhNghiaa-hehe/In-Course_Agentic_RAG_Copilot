#include <iostream>
using namespace std;

// Truyền tham trị (Pass by value): bản sao của biến, không làm thay đổi biến gốc ngoài main
void thayDoi(int n) {
    n += 1000;
}

// Truyền tham chiếu (Pass by reference): toán tử &, tham chiếu đến cùng ô nhớ, thay đổi biến gốc
void thamChieu(int &n) {
    n += 1000;
}

int main() {
    int m = 20;
    thayDoi(m);
    cout << "Gia tri sau khi goi thayDoi (tham tri): " << m << endl; // vẫn là 20
    thamChieu(m);
    cout << "Gia tri sau khi goi thamChieu (tham chieu): " << m << endl; // thành 1020
    return 0;
}
