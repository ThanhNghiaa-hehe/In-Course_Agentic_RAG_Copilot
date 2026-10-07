#include <iostream>
using namespace std;

// Kiểm tra năm nhuận: chia hết cho 400 hoặc chia hết cho 4 và không chia hết cho 100
bool namNhuan(int n) {
    if (n <= 0) {
        return false;
    }
    if ((n % 400 == 0) || (n % 4 == 0 && n % 100 != 0)) {
        return true;
    }
    return false;
}

int main() {
    int n;
    cin >> n;
    if (n <= 0) {
        cout << "INVALID" << endl;
    } else if (namNhuan(n)) {
        cout << "YES" << endl;
    } else {
        cout << "NO" << endl;
    }
    return 0;
}
