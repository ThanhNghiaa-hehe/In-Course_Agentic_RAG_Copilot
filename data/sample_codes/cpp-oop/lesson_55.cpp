#include <iostream>
#include <string>
using namespace std;

class NhanVien {
private:
    string ma, ten, gioiTinh, ngaySinh, diaChi, maSoThue, ngayKi;
public:
    NhanVien() {
        ma = "00001";
        ten = "";
        gioiTinh = "";
        ngaySinh = "";
        diaChi = "";
        maSoThue = "";
        ngayKi = "";
    }

    friend istream& operator >> (istream& in, NhanVien& a) {
        getline(in, a.ten);
        in >> a.gioiTinh >> a.ngaySinh;
        in.ignore();
        getline(in, a.diaChi);
        in >> a.maSoThue >> a.ngayKi;
        return in;
    }

    friend ostream& operator << (ostream& out, NhanVien a) {
        out << a.ma << " " << a.ten << " " << a.gioiTinh << " " 
            << a.ngaySinh << " " << a.diaChi << " " 
            << a.maSoThue << " " << a.ngayKi << endl;
        return out;
    }
};

int main() {
    NhanVien a;
    cin >> a;
    cout << a;
    return 0;
}
