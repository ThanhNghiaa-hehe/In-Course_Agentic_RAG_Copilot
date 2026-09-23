#include <iostream>
#include <string>
#include <iomanip>
#include <algorithm>

using namespace std;

/**
 * Bài 69: Lập trình hướng đối tượng trong C++ (OOP) - Nạp chồng toán tử (Operator Overloading)
 * Khóa học: cpp-oop | Lesson: lesson-69
 * Nội dung: Nạp chồng toán tử nhập >>, xuất << và toán tử so sánh < cho class SinhVien
 */
class SinhVien {
private:
    string id;
    string name;
    string ns;
    double gpa;

public:
    SinhVien() : id(""), name(""), ns(""), gpa(0.0) {}

    SinhVien(string id, string name, string ns, double gpa) {
        this->id = id;
        this->name = name;
        this->ns = ns;
        this->gpa = gpa;
    }

    double getGPA() const {
        return this->gpa;
    }

    // 1. Nạp chồng toán tử nhập >> (Friend function)
    friend istream& operator>>(istream& in, SinhVien& a) {
        cout << "Nhap ma sinh vien: ";
        in >> a.id;
        in.ignore();
        cout << "Nhap ho ten: ";
        getline(in, a.name);
        cout << "Nhap ngay sinh: ";
        in >> a.ns;
        cout << "Nhap diem GPA: ";
        in >> a.gpa;
        return in;
    }

    // 2. Nạp chồng toán tử xuất << (Friend function)
    friend ostream& operator<<(ostream& out, const SinhVien& a) {
        out << "Ma SV: " << a.id << " | Ho ten: " << a.name 
            << " | Ngay sinh: " << a.ns 
            << " | GPA: " << fixed << setprecision(2) << a.gpa << endl;
        return out;
    }

    // 3. Nạp chồng toán tử so sánh < (Friend function phục vụ sắp xếp theo GPA)
    friend bool operator<(const SinhVien& a, const SinhVien& b) {
        return a.gpa < b.gpa;
    }
};

int main() {
    SinhVien sv1("SV01", "Nguyen Van A", "20/10/2004", 3.75);
    SinhVien sv2("SV02", "Tran Thi B", "15/05/2004", 3.90);

    cout << "Thong tin sinh vien 1:" << endl;
    cout << sv1;

    cout << "Thong tin sinh vien 2:" << endl;
    cout << sv2;

    if (sv1 < sv2) {
        cout << "Sinh vien 2 co GPA cao hon Sinh vien 1." << endl;
    } else {
        cout << "Sinh vien 1 co GPA cao hon hoac bang Sinh vien 2." << endl;
    }

    return 0;
}