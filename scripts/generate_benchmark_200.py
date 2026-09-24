"""
Script tự động khởi tạo tập dữ liệu kiểm thử vàng 200 câu hỏi (Golden Dataset v2.0)
cho Bộ Khảo Thí Stage 11 - In-Course Agentic RAG Copilot.
Tác giả: Trần Thành Nghĩa (MSSV: 23DH112252) - HUFLIT.

Chuẩn Data-Centric AI (Nguyên tắc 10 trong AGENTS.md):
- Triệt tiêu hoàn toàn nhiễu nhãn (Label Noise P13).
- Đồng bộ hóa mốc giây Ground-Truth 1:1 từ video và Code AST thực tế.
- Phạm vi bài học Out-of-Lesson khớp 100% với các bài học tồn tại thực tế trong DB:
  + cpp-core: Bài 2, 3, 4, 6, 11
  + cpp-oop:  Bài 53, 54, 56, 69
- Phân luồng chuẩn xác:
  + Tier 1: In-Scope Technical (80 câu = 40%) -> intent: course_query, status: grounded, has_ts: True
  + Tier 2: Out-of-Lesson Scope (40 câu = 20%) -> intent: course_query, status: out_of_lesson, has_ts: False
  + Tier 3: Adversarial Hybrid (40 câu = 20%) -> intent: course_query, status: grounded, has_ts: True
  + Tier 4: Chit-Chat & Out-of-Scope (40 câu = 20%) -> 30 chit_chat + 10 out_of_scope, status: coverage_gap, has_ts: False
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = PROJECT_ROOT / "tests" / "data" / "benchmark_golden_dataset.json"
ACTUAL_TS_FILE = PROJECT_ROOT / "scratch" / "actual_ts_map.json"

# Nạp bản đồ mốc giây thực tế đã được Qdrant thẩm định (nếu có)
actual_ts_map: Dict[str, int] = {}
if ACTUAL_TS_FILE.exists():
    try:
        with open(ACTUAL_TS_FILE, "r", encoding="utf-8") as f:
            actual_ts_map = json.load(f)
    except Exception:
        actual_ts_map = {}


def build_dataset_200() -> List[Dict[str, Any]]:
    dataset: List[Dict[str, Any]] = []
    bench_id = 1

    def add_case(
        tier: str,
        query: str,
        course_id: str,
        lesson_seq: int,
        expected_intent: str,
        expected_status: str,
        expected_has_ts: bool,
        fallback_sec: Optional[int],
        expected_keywords: List[str],
        notes: str
    ):
        nonlocal bench_id
        case_id = f"BENCH-{bench_id:03d}"
        
        # Ưu tiên lấy mốc giây thực tế từ bản đồ ground-truth
        final_sec = None
        if expected_has_ts:
            if case_id in actual_ts_map:
                final_sec = actual_ts_map[case_id]
            else:
                final_sec = fallback_sec

        dataset.append({
            "id": case_id,
            "tier": tier,
            "query": query,
            "course_id": course_id,
            "lesson_seq": lesson_seq,
            "expected_intent": expected_intent,
            "expected_retrieval_status": expected_status,
            "expected_has_timestamp": expected_has_ts,
            "target_video_sec": final_sec,
            "expected_keywords": expected_keywords,
            "notes": notes
        })
        bench_id += 1

    # =========================================================================
    # TIER 1: IN-SCOPE TECHNICAL (80 CÂU)
    # =========================================================================

    # --- 1.1. cpp-core (40 câu) ---
    # Bài 02: const, biến, kiểu dữ liệu, cin/cout (8 câu)
    core_02_cases = [
        ("Làm sao để khai báo hằng số const trong C++?", 1669, ["const", "hằng số"], "Khai báo hằng số const Bài 2"),
        ("Ép kiểu dữ liệu (type casting) trong C++ có mấy loại và cú pháp thế nào?", 454, ["ép kiểu", "kiểu dữ liệu"], "Ép kiểu dữ liệu Bài 2"),
        ("Kiểu dữ liệu bool trong C++ lưu được những giá trị nào và tốn bao nhiêu byte?", 1030, ["bool", "byte"], "Kiểu dữ liệu bool Bài 2"),
        ("Sự khác nhau giữa float và double trong C++ là gì?", 1216, ["float", "double"], "So sánh số thực float/double Bài 2"),
        ("Cú pháp dùng std::cin và std::cout để nhập xuất dữ liệu cơ bản?", 321, ["cin", "cout"], "Nhập xuất cin cout Bài 2"),
        ("Quy tắc đặt tên biến trong C++ cần tuân thủ những nguyên tắc nào?", 1262, ["biến", "tên biến"], "Quy tắc đặt tên biến Bài 2"),
        ("Từ khóa unsigned trong kiểu unsigned int có tác dụng gì?", 1180, ["unsigned", "dấu"], "Từ khóa unsigned Bài 2"),
        ("Cách in ký tự xuống dòng bằng endl và '\\n' khác nhau ra sao?", 45, ["endl", "\n"], "Xuống dòng endl vs \\n Bài 2"),
    ]
    for q, sec, kw, n in core_02_cases:
        add_case("in_scope", q, "cpp-core", 2, "course_query", "grounded", True, sec, kw, n)

    # Bài 03: Toán tử số học, logic, so sánh (8 câu)
    core_03_cases = [
        ("Toán tử chia lấy phần dư % trong C++ chỉ áp dụng được cho kiểu dữ liệu nào?", 834, ["%", "dư", "nguyên"], "Toán tử chia dư Bài 3"),
        ("Sự khác biệt giữa toán tử tiền tố ++x và hậu tố x++ là gì?", 120, ["++x", "x++", "tiền tố"], "Toán tử ++ Bài 3"),
        ("Các toán tử logic &&, || và ! trong C++ hoạt động như thế nào?", 1460, ["logic", "&&", "||"], "Toán tử logic Bài 3"),
        ("Độ ưu tiên của toán tử số học so với toán tử so sánh trong biểu thức C++?", 1056, ["độ ưu tiên", "toán tử"], "Độ ưu tiên toán tử Bài 3"),
        ("Toán tử gán phức hợp như +=, -=, *= trong C++ viết rút gọn ra sao?", 1362, ["+=", "-=", "gán"], "Toán tử gán phức hợp Bài 3"),
        ("Làm thế nào để kiểm tra một số nguyên n có phải là số chẵn bằng toán tử %?", 120, ["chẵn", "% 2"], "Kiểm tra số chẵn Bài 3"),
        ("Toán tử quan hệ == và != khác với toán tử gán = ở điểm nào?", 1460, ["==", "!=", "so sánh"], "So sánh == vs = Bài 3"),
        ("Hiện tượng ngắn mạch (short-circuit evaluation) của toán tử logic && trong C++?", 1554, ["ngắn mạch", "short-circuit"], "Ngắn mạch logic Bài 3"),
    ]
    for q, sec, kw, n in core_03_cases:
        add_case("in_scope", q, "cpp-core", 3, "course_query", "grounded", True, sec, kw, n)

    # Bài 04: Cấu trúc rẽ nhánh if...else, switch...case (8 câu)
    core_04_cases = [
        ("Cú pháp câu lệnh điều kiện if và if-else trong C++ viết như thế nào?", 751, ["if", "else"], "Cú pháp if else Bài 4"),
        ("Khi nào nên dùng cấu trúc switch case thay cho nhiều lệnh if else lồng nhau?", 1413, ["switch", "case"], "Khi nào dùng switch Bài 4"),
        ("Từ khóa break trong khối lệnh switch case có vai trò gì và nếu thiếu thì sao?", 1669, ["break", "switch"], "Từ khóa break switch Bài 4"),
        ("Trường hợp default trong câu lệnh switch case có bắt buộc phải có không?", 1715, ["default", "switch"], "Trường hợp default Bài 4"),
        ("Toán tử ba ngôi (ternary operator) ?: có thể thay thế câu lệnh if-else đơn giản ra sao?", 180, ["ba ngôi", "?:"], "Toán tử ba ngôi Bài 4"),
        ("Cách kiểm tra một năm có phải là năm nhuận bằng cấu trúc if else?", 525, ["năm nhuận", "if"], "Bài toán năm nhuận Bài 4"),
        ("Biểu thức điều kiện trong lệnh if có thể nhận giá trị kiểu số nguyên không?", 432, ["điều kiện", "0", "1"], "Biểu thức điều kiện Bài 4"),
        ("Lồng nhiều câu lệnh if-else-if bậc thang để xếp loại học lực học sinh như thế nào?", 799, ["bậc thang", "xếp loại"], "If else lồng nhau Bài 4"),
    ]
    for q, sec, kw, n in core_04_cases:
        add_case("in_scope", q, "cpp-core", 4, "course_query", "grounded", True, sec, kw, n)

    # Bài 06: Vòng lặp for, while, do-while (8 câu)
    core_06_cases = [
        ("Cú pháp và cơ chế hoạt động của vòng lặp for trong C++ gồm những gì?", 52, ["for", "vòng lặp"], "Cú pháp for Bài 6"),
        ("Vòng lặp while và vòng lặp do-while khác nhau ở điểm cốt lõi nào?", 1600, ["while", "do-while"], "While vs do-while Bài 6"),
        ("Vòng lặp vô tận (infinite loop) xảy ra khi nào và cách khắc phục?", 1366, ["vô tận", "infinite"], "Vòng lặp vô tận Bài 6"),
        ("Lệnh break và continue trong thân vòng lặp khác nhau như thế nào?", 967, ["break", "continue"], "Break vs continue Bài 6"),
        ("Cách viết vòng lặp for để tính tổng các số từ 1 đến N?", 1366, ["tính tổng", "1 đến N"], "Tính tổng 1 đến N Bài 6"),
        ("Có thể khai báo nhiều biến đếm cùng lúc trong mệnh đề khởi tạo của for không?", 555, ["nhiều biến", "for"], "Nhiều biến đếm for Bài 6"),
        ("Làm sao để duyệt ngược từ N về 1 bằng vòng lặp for?", 1554, ["duyệt ngược", "N về 1"], "Duyệt ngược Bài 6"),
        ("Khi nào nên dùng vòng lặp while thay vì for trong việc xử lý số nguyên?", 2249, ["khi nào dùng while", "chữ số"], "Khi nào dùng while Bài 6"),
    ]
    for q, sec, kw, n in core_06_cases:
        add_case("in_scope", q, "cpp-core", 6, "course_query", "grounded", True, sec, kw, n)

    # Bài 11: Hàm (function), tham số, tham trị, tham chiếu (8 câu)
    core_11_cases = [
        ("Nguyên mẫu hàm (function prototype) trong C++ là gì và vì sao cần khai báo?", 1641, ["prototype", "nguyên mẫu"], "Nguyên mẫu hàm Bài 11"),
        ("Sự khác biệt giữa truyền tham trị (pass by value) và truyền tham chiếu (pass by reference)?", 5750, ["tham trị", "tham chiếu"], "Tham trị vs tham chiếu Bài 11"),
        ("Làm sao để viết hàm hoán đổi giá trị của 2 biến số nguyên swap?", 2638, ["swap", "hoán vị"], "Hàm swap Bài 11"),
        ("Từ khóa void trong kiểu trả về của hàm có ý nghĩa gì?", 537, ["void", "trả về"], "Từ khóa void Bài 11"),
        ("Toán tử & trong định nghĩa tham số hàm void func(int &x) có tác dụng gì?", 5750, ["&x", "tham chiếu"], "Toán tử tham chiếu Bài 11"),
        ("Lệnh return trong thân hàm có thể xuất hiện nhiều lần không?", 1644, ["return", "thoát"], "Lệnh return Bài 11"),
        ("Giá trị mặc định của tham số hàm (default arguments) được khai báo ở đâu?", 2130, ["default arguments", "mặc định"], "Tham số mặc định Bài 11"),
        ("Tầm vực (scope) của biến cục bộ khai báo trong thân hàm kéo dài bao lâu?", 994, ["scope", "cục bộ"], "Tầm vực biến Bài 11"),
    ]
    for q, sec, kw, n in core_11_cases:
        add_case("in_scope", q, "cpp-core", 11, "course_query", "grounded", True, sec, kw, n)

    # --- 1.2. cpp-oop (40 câu) ---
    # Bài 53: Lớp SinhVien, constructor, private/public, TinhGPA, chieuCao (10 câu)
    oop_53_cases = [
        ("Khái niệm Lớp (Class) và Đối tượng (Object) trong C++ khác nhau như thế nào?", 2180, ["Class", "Object"], "Class vs Object Bài 53"),
        ("Phạm vi truy cập private và public trong class C++ có ý nghĩa gì?", 373, ["private", "public"], "Phạm vi truy cập Bài 53"),
        ("Hàm khởi tạo (constructor) của class có đặc điểm gì về tên và kiểu trả về?", 350, ["constructor", "khởi tạo"], "Constructor Bài 53"),
        ("Thuộc tính và phương thức của class SinhVien được khai báo ra sao?", 350, ["SinhVien", "thuộc tính", "phương thức"], "Cấu trúc SinhVien Bài 53"),
        ("Vì sao các thuộc tính như hoTen, diemGPA nên đặt ở phạm vi private?", 462, ["private", "đóng gói"], "Lý do dùng private Bài 53"),
        ("Cách viết hàm thành viên TinhGPA() của class SinhVien để tính điểm trung bình?", 1087, ["TinhGPA", "GPA"], "Hàm TinhGPA Bài 53"),
        ("Phương thức chieuCao() trong class SinhVien dùng để xử lý thông tin gì?", 350, ["chieuCao", "chiều cao"], "Phương thức chieuCao Bài 53"),
        ("Cách khởi tạo một đối tượng SinhVien sv trong hàm main và gán dữ liệu?", 350, ["main", "khởi tạo", "SinhVien"], "Khởi tạo SinhVien main Bài 53"),
        ("Con trỏ this trong phương thức của class C++ có vai trò gì?", 418, ["this", "con trỏ this"], "Con trỏ this Bài 53"),
        ("Hàm hủy (destructor) của class được gọi tự động khi nào?", 350, ["destructor", "hàm hủy"], "Destructor Bài 53"),
    ]
    for q, sec, kw, n in oop_53_cases:
        add_case("in_scope", q, "cpp-oop", 53, "course_query", "grounded", True, sec, kw, n)

    # Bài 54: Chuẩn hóa họ tên, ngày sinh, stringstream (10 câu)
    oop_54_cases = [
        ("Mục đích của phương thức chuanHoaThongTin() trong class SinhVien là gì?", 350, ["chuanHoaThongTin", "chuẩn hóa"], "Mục đích chuanHoaThongTin Bài 54"),
        ("Làm sao để chuẩn hóa định dạng ngày sinh dd/mm/yyyy nếu thiếu số 0?", 862, ["ngày sinh", "dd/mm/yyyy"], "Chuẩn hóa ngày sinh Bài 54"),
        ("Cách viết hoa chữ cái đầu và viết thường các chữ cái sau trong họ tên sinh viên?", 3048, ["viết hoa", "họ tên"], "Viết hoa chữ cái đầu Bài 54"),
        ("Hàm displayInfor() trong bài học hiển thị những trường thông tin nào của sinh viên?", 600, ["displayInfor", "hiển thị"], "Hàm displayInfor Bài 54"),
        ("Cách sử dụng thư viện string và hàm toupper/tolower để xử lý chuỗi trong C++?", 180, ["string", "toupper", "chuỗi"], "Xử lý chuỗi Bài 54"),
        ("Làm thế nào để xóa các khoảng trắng thừa ở đầu và cuối chuỗi họ tên?", 180, ["khoảng trắng", "trim"], "Xóa khoảng trắng Bài 54"),
        ("Cách gọi hàm chuanHoaThongTin() tự động ngay sau khi nhập dữ liệu sinh viên?", 3393, ["chuanHoaThongTin", "gọi hàm"], "Gọi chuanHoaThongTin Bài 54"),
        ("Toán tử s[i] dùng để truy cập từng ký tự trong biến std::string như thế nào?", 180, ["s[i]", "ký tự"], "Truy cập ký tự chuỗi Bài 54"),
        ("Cách tách các từ trong họ tên bằng luồng stringstream trong C++?", 2980, ["stringstream", "tách từ"], "Tách từ stringstream Bài 54"),
        ("Khi xuất thông tin sinh viên đã chuẩn hóa trong hàm main cần lưu ý điều gì?", 1453, ["main", "xuất thông tin"], "Xuất thông tin main Bài 54"),
    ]
    for q, sec, kw, n in oop_54_cases:
        add_case("in_scope", q, "cpp-oop", 54, "course_query", "grounded", True, sec, kw, n)

    # Bài 56: Lớp Phân Số PhanSo, tìm ước chung lớn nhất gcd, rút gọn phân số (10 câu)
    oop_56_cases = [
        ("Thuộc tính của lớp PhanSo gồm có tử số và mẫu số được khai báo ra sao?", 120, ["PhanSo", "tu", "mau"], "Khai báo PhanSo Bài 56"),
        ("Thuật toán Euclid tìm ước chung lớn nhất gcd(a, b) hoạt động như thế nào?", 415, ["gcd", "ước chung lớn nhất", "Euclid"], "Thuật toán gcd Bài 56"),
        ("Làm thế nào để rút gọn một phân số về dạng tối giản trong C++?", 0, ["rút gọn", "tối giản", "gcd"], "Rút gọn phân số Bài 56"),
        ("Điều kiện kiểm tra mẫu số khác 0 khi khởi tạo một đối tượng PhanSo là gì?", 120, ["mẫu số khác 0", "mau != 0"], "Kiểm tra mẫu số 0 Bài 56"),
        ("Cách viết hàm cộng 2 phân số và trả về phân số tối giản?", 415, ["cộng phân số", "tối giản"], "Cộng phân số Bài 56"),
        ("Cách xử lý dấu âm của phân số nếu mẫu số là số âm trong hàm rút gọn?", 501, ["dấu âm", "mẫu âm"], "Xử lý dấu phân số Bài 56"),
        ("Cách khởi tạo đối tượng PhanSo trong hàm main và in kết quả rút gọn ra màn hình?", 501, ["main", "PhanSo", "kết quả"], "Khởi tạo PhanSo main Bài 56"),
        ("Hàm gcd có thể viết bằng thuật toán đệ quy ngắn gọn như thế nào?", 120, ["gcd", "đệ quy"], "Hàm gcd đệ quy Bài 56"),
        ("Vì sao hàm gcd thường được đặt làm hàm phụ trợ (helper function) hoặc private?", 3488, ["helper", "private"], "Hàm gcd helper Bài 56"),
        ("Có thể gán giá trị mặc định cho phân số là 0/1 bằng constructor không?", 2269, ["constructor", "0/1"], "Constructor PhanSo Bài 56"),
    ]
    for q, sec, kw, n in oop_56_cases:
        add_case("in_scope", q, "cpp-oop", 56, "course_query", "grounded", True, sec, kw, n)

    # Bài 69: Nạp chồng toán tử operator>>, operator<<, operator< (10 câu)
    oop_69_cases = [
        ("Nạp chồng toán tử (operator overloading) trong C++ là gì và mang lại lợi ích gì?", 3881, ["nạp chồng toán tử", "operator"], "Khái niệm overload operator Bài 69"),
        ("Cú pháp nạp chồng toán tử nhập >> (operator>>) cho lớp SinhVien như thế nào?", 2824, ["operator>>", "istream"], "Overload operator>> Bài 69"),
        ("Vì sao hàm nạp chồng toán tử nhập xuất << và >> cần được khai báo là friend?", 2824, ["friend", "ostream", "istream"], "Friend function operator Bài 69"),
        ("Toán tử xuất << (operator<<) cần trả về kiểu tham chiếu std::ostream& để làm gì?", 2824, ["ostream&", "cout"], "Trả về ostream& Bài 69"),
        ("Cú pháp nạp chồng toán tử so sánh nhỏ hơn < (operator<) để sắp xếp sinh viên?", 3881, ["operator<", "so sánh"], "Overload operator< Bài 69"),
        ("Cách sử dụng hàm std::sort kết hợp với operator< để sắp xếp mảng sinh viên theo GPA?", 1264, ["sort", "operator<", "GPA"], "std::sort với operator< Bài 69"),
        ("Có thể nạp chồng được những toán tử nào và toán tử nào KHÔNG thể nạp chồng?", 3881, ["không thể nạp chồng", "::", "."], "Toán tử không nạp chồng được Bài 69"),
        ("Sự khác biệt giữa nạp chồng toán tử dạng member function và dạng friend function?", 240, ["member", "friend"], "Member vs Friend operator Bài 69"),
        ("Cách nhập xuất danh sách sinh viên bằng cin >> sv và cout << sv trong hàm main?", 3941, ["main", "cin >>", "cout <<"], "Nhập xuất sv main Bài 69"),
        ("Tham số của operator<< có nên truyền hằng tham chiếu const SinhVien& không?", 2824, ["const SinhVien&", "tham chiếu"], "Tham số operator<< Bài 69"),
    ]
    for q, sec, kw, n in oop_69_cases:
        add_case("in_scope", q, "cpp-oop", 69, "course_query", "grounded", True, sec, kw, n)

    # =========================================================================
    # TIER 2: OUT-OF-LESSON SCOPE (40 CÂU)
    # Khớp 100% với các bài học tồn tại thực tế trong DB:
    # cpp-core: Bài 2, 3, 4, 6, 11
    # cpp-oop: Bài 53, 54, 56, 69
    # =========================================================================

    # --- 2.1. cpp-core out-of-lesson (20 câu) ---
    core_out_cases = [
        # Học bài 2 -> hỏi bài 4 (rẽ nhánh if/switch) & bài 6 (vòng lặp for/while) & bài 11 (hàm)
        ("Cú pháp câu lệnh điều kiện if và if-else trong C++ viết như thế nào?", 2, ["if", "else", "bài 4"], "Học bài 2 hỏi if-else bài 4"),
        ("Khi nào nên dùng cấu trúc switch case thay cho nhiều lệnh if else lồng nhau?", 2, ["switch", "case", "bài 4"], "Học bài 2 hỏi switch case bài 4"),
        ("Từ khóa break trong khối lệnh switch case có vai trò gì và nếu thiếu thì sao?", 2, ["break", "switch", "bài 4"], "Học bài 2 hỏi break switch bài 4"),
        ("Cú pháp và cơ chế hoạt động của vòng lặp for trong C++ gồm những gì?", 2, ["for", "vòng lặp", "bài 6"], "Học bài 2 hỏi vòng lặp for bài 6"),
        ("Vòng lặp while và vòng lặp do-while khác nhau ở điểm cốt lõi nào?", 2, ["while", "do-while", "bài 6"], "Học bài 2 hỏi while vs do-while bài 6"),
        ("Lệnh break và continue trong thân vòng lặp khác nhau như thế nào?", 2, ["break", "continue", "bài 6"], "Học bài 2 hỏi break continue bài 6"),
        ("Nguyên mẫu hàm (function prototype) trong C++ là gì và vì sao cần khai báo?", 2, ["prototype", "nguyên mẫu", "bài 11"], "Học bài 2 hỏi prototype bài 11"),
        ("Sự khác biệt giữa truyền tham trị (pass by value) và truyền tham chiếu (pass by reference)?", 2, ["tham trị", "tham chiếu", "bài 11"], "Học bài 2 hỏi tham chiếu bài 11"),

        # Học bài 3 -> hỏi bài 4 & bài 6 & bài 11
        ("Cú pháp câu lệnh điều kiện if-else trong C++ viết ra sao?", 3, ["if", "else", "bài 4"], "Học bài 3 hỏi if else bài 4"),
        ("Trường hợp default trong câu lệnh switch case có bắt buộc phải có không?", 3, ["default", "switch", "bài 4"], "Học bài 3 hỏi default switch bài 4"),
        ("Cách viết vòng lặp for để tính tổng các số từ 1 đến N?", 3, ["tính tổng", "for", "bài 6"], "Học bài 3 hỏi for tính tổng bài 6"),
        ("Làm sao để duyệt ngược từ N về 1 bằng vòng lặp for?", 3, ["duyệt ngược", "for", "bài 6"], "Học bài 3 hỏi duyệt ngược for bài 6"),
        ("Làm sao để viết hàm hoán đổi giá trị của 2 biến số nguyên swap?", 3, ["swap", "hàm", "bài 11"], "Học bài 3 hỏi hàm swap bài 11"),
        ("Từ khóa void trong kiểu trả về của hàm có ý nghĩa gì?", 3, ["void", "hàm", "bài 11"], "Học bài 3 hỏi void hàm bài 11"),

        # Học bài 4 -> hỏi bài 6 & bài 11
        ("Cú pháp và cơ chế hoạt động của vòng lặp for trong C++?", 4, ["for", "lặp", "bài 6"], "Học bài 4 hỏi vòng lặp for bài 6"),
        ("Vòng lặp while và vòng lặp do-while khác nhau ở điểm cốt lõi nào?", 4, ["while", "do-while", "bài 6"], "Học bài 4 hỏi while vs do-while bài 6"),
        ("Khi nào nên dùng vòng lặp while thay vì for trong việc xử lý số nguyên?", 4, ["while", "for", "bài 6"], "Học bài 4 hỏi khi nào dùng while bài 6"),
        ("Nguyên mẫu hàm (function prototype) trong C++ là gì và vì sao cần khai báo?", 4, ["prototype", "hàm", "bài 11"], "Học bài 4 hỏi prototype bài 11"),
        ("Sự khác biệt giữa truyền tham trị (pass by value) và truyền tham chiếu (pass by reference)?", 4, ["tham trị", "tham chiếu", "bài 11"], "Học bài 4 hỏi tham chiếu bài 11"),
        ("Làm sao để viết hàm hoán đổi giá trị của 2 biến số nguyên swap?", 4, ["swap", "hàm", "bài 11"], "Học bài 4 hỏi hàm swap bài 11"),
    ]
    for q, seq, kw, n in core_out_cases:
        add_case("out_of_lesson", q, "cpp-core", seq, "course_query", "out_of_lesson", False, None, kw, n)

    # --- 2.2. cpp-oop out-of-lesson (20 câu) ---
    oop_out_cases = [
        # Học bài 53 -> hỏi bài 54 (chuẩn hóa), bài 56 (PhanSo), bài 69 (nạp chồng toán tử)
        ("Điều kiện kiểm tra mẫu số khác 0 khi khởi tạo một đối tượng PhanSo là gì?", 53, ["mẫu số khác 0", "PhanSo", "bài 56"], "Học bài 53 hỏi PhanSo bài 56"),
        ("Làm sao để chuẩn hóa định dạng ngày sinh dd/mm/yyyy nếu thiếu số 0?", 53, ["ngày sinh", "dd/mm/yyyy", "bài 54"], "Học bài 53 hỏi chuẩn hóa ngày sinh bài 54"),
        ("Cách tách các từ trong họ tên bằng luồng stringstream trong C++?", 53, ["stringstream", "tách từ", "bài 54"], "Học bài 53 hỏi stringstream bài 54"),
        ("Cách viết hàm cộng 2 phân số và trả về phân số tối giản?", 53, ["cộng phân số", "PhanSo", "bài 56"], "Học bài 53 hỏi cộng phân số bài 56"),
        ("Thuộc tính của lớp PhanSo gồm có tử số và mẫu số được khai báo ra sao?", 53, ["PhanSo", "tu", "mau", "bài 56"], "Học bài 53 hỏi khai báo PhanSo bài 56"),
        ("Thuật toán Euclid tìm ước chung lớn nhất gcd(a, b) hoạt động như thế nào?", 53, ["gcd", "ước chung", "bài 56"], "Học bài 53 hỏi thuật toán gcd bài 56"),
        ("Làm thế nào để rút gọn một phân số về dạng tối giản trong C++?", 53, ["rút gọn", "tối giản", "bài 56"], "Học bài 53 hỏi rút gọn phân số bài 56"),
        ("Nạp chồng toán tử (operator overloading) trong C++ là gì và mang lại lợi ích gì?", 53, ["nạp chồng toán tử", "operator", "bài 69"], "Học bài 53 hỏi operator overloading bài 69"),
        ("Cú pháp nạp chồng toán tử nhập >> (operator>>) cho lớp SinhVien như thế nào?", 53, ["operator>>", "nhập", "bài 69"], "Học bài 53 hỏi operator>> bài 69"),
        ("Vì sao hàm nạp chồng toán tử nhập xuất << và >> cần được khai báo là friend?", 53, ["friend", "operator", "bài 69"], "Học bài 53 hỏi friend operator bài 69"),

        # Học bài 54 -> hỏi bài 56 (PhanSo) & bài 69 (nạp chồng toán tử)
        ("Thuộc tính của lớp PhanSo gồm có tử số và mẫu số được khai báo ra sao?", 54, ["PhanSo", "tu", "mau", "bài 56"], "Học bài 54 hỏi khai báo PhanSo bài 56"),
        ("Thuật toán Euclid tìm ước chung lớn nhất gcd(a, b) hoạt động ra sao?", 54, ["gcd", "ước chung", "bài 56"], "Học bài 54 hỏi gcd bài 56"),
        ("Cách viết hàm cộng 2 phân số và trả về phân số tối giản?", 54, ["cộng phân số", "PhanSo", "bài 56"], "Học bài 54 hỏi cộng phân số bài 56"),
        ("Nạp chồng toán tử (operator overloading) trong C++ là gì?", 54, ["operator", "nạp chồng", "bài 69"], "Học bài 54 hỏi nạp chồng toán tử bài 69"),
        ("Toán tử xuất << (operator<<) cần trả về kiểu tham chiếu std::ostream& để làm gì?", 54, ["operator<<", "ostream&", "bài 69"], "Học bài 54 hỏi operator<< bài 69"),
        ("Cú pháp nạp chồng toán tử so sánh nhỏ hơn < (operator<) để sắp xếp sinh viên?", 54, ["operator<", "so sánh", "bài 69"], "Học bài 54 hỏi operator< bài 69"),

        # Học bài 56 -> hỏi bài 69 (nạp chồng toán tử)
        ("Nạp chồng toán tử (operator overloading) trong C++ là gì và cú pháp?", 56, ["operator", "nạp chồng", "bài 69"], "Học bài 56 hỏi nạp chồng toán tử bài 69"),
        ("Cú pháp nạp chồng toán tử nhập >> (operator>>) cho lớp SinhVien?", 56, ["operator>>", "istream", "bài 69"], "Học bài 56 hỏi operator>> bài 69"),
        ("Cách sử dụng hàm std::sort kết hợp với operator< để sắp xếp mảng sinh viên theo GPA?", 56, ["sort", "operator<", "bài 69"], "Học bài 56 hỏi std::sort với operator< bài 69"),
        ("Có thể nạp chồng được những toán tử nào và toán tử nào KHÔNG thể nạp chồng?", 56, ["toán tử", "không thể nạp chồng", "bài 69"], "Học bài 56 hỏi toán tử không thể overload bài 69"),
    ]
    for q, seq, kw, n in oop_out_cases:
        add_case("out_of_lesson", q, "cpp-oop", seq, "course_query", "out_of_lesson", False, None, kw, n)

    # =========================================================================
    # TIER 3: ADVERSARIAL HYBRID QUERIES (40 CÂU)
    # =========================================================================

    # --- 3.1. cpp-core hybrid (20 câu) ---
    core_hybrid = [
        ("Vừa đi ăn lẩu vừa viết biến const trong C++ thì biến đó có đổi giá trị khi lẩu sôi không?", 2, 1578, ["const", "hằng số"], "Hybrid ăn lẩu vs const Bài 2"),
        ("Toán tử chia dư % có tính được tiền chia đều cho nhóm đi nhậu không?", 3, 834, ["%", "dư"], "Hybrid đi nhậu vs chia dư Bài 3"),
        ("Lệnh if-else có quyết định được hôm nay nên đi xem phim hay ngủ ở nhà không?", 4, 751, ["if", "else"], "Hybrid xem phim vs if else Bài 4"),
        ("Vòng lặp for chạy 100 lần giống như hít đất 100 cái mỗi sáng thế nào?", 6, 52, ["for", "lặp"], "Hybrid thể dục vs for Bài 6"),
        ("Hàm swap đổi chỗ 2 người yêu cũ có dùng truyền tham chiếu được không?", 11, 5750, ["swap", "tham chiếu"], "Hybrid người yêu cũ vs swap Bài 11"),
        ("Nếu trời mưa to thì cin nhập vào có bị ướt màn hình terminal không?", 2, 321, ["cin", "nhập"], "Hybrid trời mưa vs cin Bài 2"),
        ("Toán tử logic && có giúp kiểm tra vừa đẹp trai vừa giàu có được không?", 3, 1460, ["&&", "logic"], "Hybrid đẹp trai giàu vs logic Bài 3"),
        ("Cấu trúc switch case có tự động chọn món ăn sáng như bánh mì hay phở bò không?", 4, 1669, ["switch", "case"], "Hybrid ăn sáng vs switch Bài 4"),
        ("Vòng lặp while có thể đợi đèn đỏ chuyển sang xanh rồi mới đi tiếp được không?", 6, 1056, ["while", "chờ"], "Hybrid đèn giao thông vs while Bài 6"),
        ("Nguyên mẫu hàm function prototype có giống như thực đơn gọi món nhà hàng không?", 11, 1641, ["prototype", "nguyên mẫu"], "Hybrid thực đơn vs prototype Bài 11"),
        ("Khai báo biến float lưu cân nặng lúc vừa ăn no xong có bị sai số không?", 2, 1216, ["float", "số thực"], "Hybrid cân nặng vs float Bài 2"),
        ("Toán tử tiền tố ++x có làm tăng tiền lương của tôi ngay trong tháng này không?", 3, 120, ["++x", "tiền tố"], "Hybrid tiền lương vs ++x Bài 3"),
        ("Lệnh break có giúp tôi thoát khỏi cuộc họp buồn ngủ của công ty không?", 4, 1669, ["break", "thoát"], "Hybrid cuộc họp vs break Bài 4"),
        ("Vòng lặp do-while có bắt buộc phải ăn thử một miếng rồi mới quyết định ăn tiếp không?", 6, 1056, ["do-while", "ăn thử"], "Hybrid ăn thử vs do-while Bài 6"),
        ("Truyền tham trị cho hàm có giống như photo một bản hợp đồng cho đối tác giữ không?", 11, 5750, ["tham trị", "bản sao"], "Hybrid bản photo vs tham trị Bài 11"),
        ("Hằng số const có giữ cho tình bạn chúng ta mãi không đổi thay được không?", 2, 1669, ["const", "không đổi"], "Hybrid tình bạn vs const Bài 2"),
        ("Toán tử gán += có giống như nhét thêm tiền tiết kiệm vào con heo đất không?", 3, 1362, ["+=", "gán"], "Hybrid heo đất vs += Bài 3"),
        ("Câu lệnh if lồng nhau có giống như qua nhiều vòng phỏng vấn xin việc không?", 4, 945, ["if", "lồng nhau"], "Hybrid phỏng vấn vs if lồng nhau Bài 4"),
        ("Lệnh continue trong vòng lặp có giống như bỏ qua quảng cáo YouTube không?", 6, 1010, ["continue", "bỏ qua"], "Hybrid bỏ qua qc vs continue Bài 6"),
        ("Hàm đệ quy tính giai thừa có giống như vòng lặp thời gian trong phim Marvel không?", 11, 2638, ["đệ quy", "giai thừa"], "Hybrid phim Marvel vs đệ quy Bài 11"),
    ]
    for q, seq, sec, kw, n in core_hybrid:
        add_case("adversarial_hybrid", q, "cpp-core", seq, "course_query", "grounded", True, sec, kw, n)

    # --- 3.2. cpp-oop hybrid (20 câu) ---
    oop_hybrid = [
        ("Tạo một class SinhVien đi phượt Đà Lạt có thuộc tính xe máy và lều trại được không?", 53, 350, ["class", "thuộc tính", "SinhVien"], "Hybrid đi phượt vs class Bài 53"),
        ("Phương thức TinhGPA() có tính được điểm hạnh kiểm khi tham gia câu lạc bộ ghi-ta không?", 53, 1087, ["TinhGPA", "GPA"], "Hybrid ghi-ta vs TinhGPA Bài 53"),
        ("Hàm chuanHoaThongTin() có sửa được biệt danh người yêu thành tên chính thức trên Facebook không?", 54, 350, ["chuanHoaThongTin", "chuẩn hóa"], "Hybrid biệt danh vs chuanHoaThongTin Bài 54"),
        ("Lớp PhanSo có chia được cái bánh pizza 8 miếng cho 3 người ăn không?", 56, 120, ["PhanSo", "chia bánh"], "Hybrid bánh pizza vs PhanSo Bài 56"),
        ("Nạp chồng toán tử operator>> có thể nhập một ly trà sữa trân châu đường đen vào máy tính không?", 69, 3881, ["operator>>", "nhập"], "Hybrid trà sữa vs operator>> Bài 69"),
        ("Toán tử so sánh operator< có so sánh được độ đẹp trai của hai chàng trai cua cùng một cô gái không?", 69, 4060, ["operator<", "so sánh"], "Hybrid so tài vs operator< Bài 69"),
        ("Constructor của class SinhVien có tự động chuẩn bị quần áo khi vừa thức dậy buổi sáng không?", 53, 350, ["constructor", "khởi tạo"], "Hybrid thức dậy vs constructor Bài 53"),
        ("Thuộc tính private của SinhVien có giấu được số dư tài khoản ngân hàng với bạn thân không?", 53, 2910, ["private", "đóng gói"], "Hybrid tài khoản vs private Bài 53"),
        ("Hàm displayInfor() có chiếu thông tin sinh viên lên màn hình rạp chiếu phim CGV được không?", 54, 600, ["displayInfor", "hiển thị"], "Hybrid rạp CGV vs displayInfor Bài 54"),
        ("Hàm gcd tìm ước chung lớn nhất có tìm được điểm chung giữa hai người đang cãi nhau không?", 56, 415, ["gcd", "ước chung"], "Hybrid cãi nhau vs gcd Bài 56"),
        ("Nạp chồng toán tử xuất operator<< có in được lời tỏ tình lãng mạn ra màn hình không?", 69, 1430, ["operator<<", "xuất"], "Hybrid tỏ tình vs operator<< Bài 69"),
        ("Phương thức chieuCao() trong SinhVien có giúp học viên đủ điều kiện thi tuyển phi công không?", 53, 350, ["chieuCao", "chiều cao"], "Hybrid phi công vs chieuCao Bài 53"),
        ("Làm sao để dùng chuanHoaThongTin() xóa bỏ những lời nói tục tĩu khi bình luận trên mạng?", 54, 350, ["chuanHoaThongTin", "lọc từ"], "Hybrid bình luận mạng vs chuanHoaThongTin Bài 54"),
        ("Rút gọn phân số PhanSo có giúp đơn giản hóa các mối quan hệ phức tạp trong cuộc sống không?", 56, 0, ["rút gọn", "tối giản"], "Hybrid quan hệ vs rút gọn phân số Bài 56"),
        ("Dùng std::sort sắp xếp sinh viên theo GPA có phân chia chỗ ngồi ăn tiệc cưới được không?", 69, 4173, ["sort", "GPA"], "Hybrid tiệc cưới vs sort operator< Bài 69"),
        ("Hàm input() của class SinhVien có nhập được số đo 3 vòng của người mẫu không?", 53, 350, ["input", "nhập"], "Hybrid người mẫu vs input Bài 53"),
        ("Chuẩn hóa ngày sinh dd/mm/yyyy có nhắc tôi nhớ ngày kỷ niệm ngày cưới của bố mẹ không?", 54, 862, ["ngày sinh", "dd/mm/yyyy"], "Hybrid ngày cưới vs ngày sinh Bài 54"),
        ("Cộng hai phân số PhanSo có cộng dồn được thời gian tập gym của cả tuần không?", 56, 415, ["cộng phân số", "tổng"], "Hybrid tập gym vs cộng phân số Bài 56"),
        ("Hàm friend trong nạp chồng toán tử có giống như người bạn nối khố được vào nhà bất cứ lúc nào?", 69, 2824, ["friend", "bạn bè"], "Hybrid bạn nối khố vs friend operator Bài 69"),
        ("Định dạng tên bằng chuanHoaThongTin có in hoa được bảng tên của thú cưng mèo không?", 54, 3048, ["chuanHoaThongTin", "tên"], "Hybrid thú cưng vs chuanHoaThongTin Bài 54"),
    ]
    for q, seq, sec, kw, n in oop_hybrid:
        add_case("adversarial_hybrid", q, "cpp-oop", seq, "course_query", "grounded", True, sec, kw, n)

    # =========================================================================
    # TIER 4: CHIT-CHAT & OUT-OF-SCOPE (40 CÂU)
    # 30 câu chit-chat hội thoại / trợ giảng + 10 câu ngoài lề đời sống
    # =========================================================================
    chit_chat_cases = [
        ("Xin chào AI trợ giảng, hôm nay bạn thế nào?", "chit_chat", ["In-Course AI Copilot", "chào"]),
        ("Hello AI Copilot, how are you today?", "chit_chat", ["In-Course AI Copilot", "hello"]),
        ("Chào bạn, bạn có thể giúp gì cho mình trong khóa học này?", "chit_chat", ["trợ giảng", "học lập trình"]),
        ("Good morning AI tutor, are you ready to assist me?", "chit_chat", ["ready", "assist"]),
        ("Bạn tên là gì và do ai tạo ra thế?", "chit_chat", ["Trần Thành Nghĩa", "HUFLIT", "23DH112252"]),
        ("Ai là tác giả của đồ án In-Course Agentic RAG Copilot này?", "chit_chat", ["Trần Thành Nghĩa", "23DH112252", "HUFLIT"]),
        ("Sinh viên thực hiện đồ án này học trường đại học nào?", "chit_chat", ["HUFLIT", "Ngoại ngữ - Tin học"]),
        ("Đồ án này dùng công nghệ gì ở tầng Backend vậy?", "chit_chat", ["FastAPI", "Python", "Qdrant"]),
        ("Cơ sở dữ liệu vector trong hệ thống này là gì?", "chit_chat", ["Qdrant", "dual vector", "dense", "sparse"]),
        ("Mô hình embedding nào được dùng để nhúng văn bản bài giảng?", "chit_chat", ["multilingual-e5-large", "fastembed", "1024"]),
        ("Bộ re-ranker của hệ thống là mô hình gì?", "chit_chat", ["jinaai/jina-reranker-v2", "Cross-Encoder"]),
        ("Trình bóc băng âm thanh bài giảng dùng công nghệ gì?", "chit_chat", ["faster-whisper", "Silero VAD"]),
        ("Học lập trình C++ có khó không bạn, cho mình lời khuyên với?", "chit_chat", ["kiên trì", "thực hành", "bài tập"]),
        ("Mình thấy nản quá khi học lập trình, bạn có thể động viên mình không?", "chit_chat", ["cố gắng", "từng bước", "đồng hành"]),
        ("Phương pháp giảng dạy Socratic của bạn hoạt động như thế nào?", "chit_chat", ["Socratic", "gợi mở", "tư duy", "không chép bài"]),
        ("Vì sao bạn không viết luôn code giải bài tập cho học sinh?", "chit_chat", ["Socratic", "tự lập trình", "học viên"]),
        ("Cảm ơn bạn nhé, bạn giải thích rất dễ hiểu!", "chit_chat", ["cảm ơn", "chúc bạn học tốt"]),
        ("Thank you very much for your kind support!", "chit_chat", ["welcome", "pleasure"]),
        ("Tạm biệt AI, hẹn gặp lại vào buổi học ngày mai nhé!", "chit_chat", ["tạm biệt", "hẹn gặp lại"]),
        ("Bạn nghĩ trí tuệ nhân tạo có thay thế lập trình viên không?", "chit_chat", ["công cụ", "lập trình viên", "hỗ trợ"]),
        ("Chúc bạn một ngày làm việc thật nhiều năng lượng!", "chit_chat", ["cảm ơn", "năng lượng"]),
        ("Mã số sinh viên của bạn Trần Thành Nghĩa là gì?", "chit_chat", ["23DH112252"]),
        ("Thẻ timestamp trong câu trả lời có định dạng thế nào?", "chit_chat", ["<timestamp sec=\"...\">", "seekTo"]),
        ("Frontend của hệ thống học tập này được viết bằng thư viện gì?", "chit_chat", ["React 19", "Vite"]),
        ("Bạn có hỗ trợ kiểm tra lỗi biên dịch mã nguồn C++ không?", "chit_chat", ["lỗi biên dịch", "cú pháp", "hướng dẫn"]),
        ("Kiến trúc LangGraph đóng vai trò gì trong lộ trình nâng cấp?", "chit_chat", ["StateGraph", "4 nodes", "checkpointer"]),
        ("Kho lưu trữ mã nguồn GitHub của dự án này ở đâu?", "chit_chat", ["ThanhNghiaa-hehe/In-Course_Agentic_RAG_Copilot"]),
        ("Hệ thống có chạy được trên GPU NVIDIA RTX 2050 không?", "chit_chat", ["RTX 2050", "CUDA", "faster-whisper"]),
        ("Cho mình xin lời khuyên để bắt đầu học lập trình một cách kiên trì và hiệu quả?", "chit_chat", ["lời khuyên", "kiên trì", "bắt đầu"]),
        ("Chúc mừng bạn đã hoàn thành đồ án tốt nghiệp xuất sắc!", "chit_chat", ["cảm ơn", "đồ án", "HUFLIT"]),

        # 10 câu ngoài lề đời sống (out_of_scope)
        ("Hôm nay thời tiết đẹp quá bạn nhỉ?", "out_of_scope", ["thời tiết", "ngoài lề"]),
        ("Bạn có biết nấu món phở bò Hà Nội không?", "out_of_scope", ["phở bò", "nấu ăn"]),
        ("Bài hát nào đang hot trên TikTok hiện tại thế?", "out_of_scope", ["TikTok", "âm nhạc"]),
        ("Trái đất quay quanh mặt trời mất bao nhiêu ngày?", "out_of_scope", ["365", "thiên văn"]),
        ("Bí quyết giảm cân nhanh trong một tuần không cần tập thể dục?", "out_of_scope", ["giảm cân", "sức khỏe"]),
        ("Bạn có biết chơi cờ vua không?", "out_of_scope", ["cờ vua", "giải trí"]),
        ("Học phí đại học HUFLIT một tín chỉ là bao nhiêu?", "out_of_scope", ["học phí", "tín chỉ"]),
        ("Mua điện thoại iPhone 16 ở đâu rẻ nhất?", "out_of_scope", ["iPhone", "mua sắm"]),
        ("Giá vàng SJC hôm nay tăng hay giảm bao nhiêu?", "out_of_scope", ["giá vàng", "tài chính"]),
        ("Quán cà phê nào view đẹp ở Sài Gòn cuối tuần?", "out_of_scope", ["cà phê", "Sài Gòn"]),
    ]
    for q, intent, kw in chit_chat_cases:
        add_case("chit_chat", q, "cpp-core", 2, intent, "coverage_gap", False, None, kw, f"Nhóm {intent}")

    return dataset


def main():
    dataset = build_dataset_200()
    print(f"Tổng số test cases sinh được: {len(dataset)}")

    tier_counts: Dict[str, int] = {}
    for c in dataset:
        tier_counts[c["tier"]] = tier_counts.get(c["tier"], 0) + 1

    print("\nPhân bổ theo Tier:")
    for tier, count in tier_counts.items():
        print(f" - {tier:<20}: {count:>3} câu ({count / len(dataset) * 100:.1f}%)")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    print(f"\n[THÀNH CÔNG] Đã lưu 200 câu hỏi v2.0 tại: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
