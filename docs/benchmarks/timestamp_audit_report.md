# Báo Cáo Kiểm Toán Timestamp 27 Ca In-Scope

- **Tổng số ca in_scope bị cảnh báo:** 27 / 80
- **Ứng viên Multi-Span Grounding (Grounded thành công nhưng lệch mốc):** 21
- **Lỗi Retrieval thực sự (Status != grounded):** 6

## 1. Danh Sách Ứng Viên Multi-Span Grounding

| ID | Bài | Câu hỏi | Exp TS | Act TS | Δt | Đoạn trích Top 1 |
| :--- | :---: | :--- | :---: | :---: | :---: | :--- |
| `BENCH-005` | 2 | Cú pháp dùng std::cin và std::cout để nhập xuất dữ liệu cơ bản? | 321s | 2627s | 2306s | các câu dẫn vào cũng được nhé, thông thường thì mình chạy yêu cầu khi mà cốt thì... |
| `BENCH-008` | 2 | Cách in ký tự xuống dòng bằng endl và '\n' khác nhau ra sao? | 45s | 1669s | 1624s | Sau khi mà bạn cr, chỗ này là 9x, sau đó là nline, sau khi mà bạn in 9x, sau khi... |
| `BENCH-010` | 3 | Sự khác biệt giữa toán tử tiền tố ++x (tăng trước) và hậu tố x++ (tăng sau) trong C++ là gì? | 1168s | 1275s | 107s | Nhưng mà giá trị của B thì thằng B lại được gán 1 cái giá trị trước thì tăng, đú... |
| `BENCH-015` | 3 | Toán tử quan hệ == và != khác với toán tử gán = ở điểm nào? | 1460s | 1507s | 47s | Thì 4 thằng này là rất là quen thuộc rồi đúng không? Đấy, có 2 thằng khác lẹ một... |
| `BENCH-016` | 4 | Hiện tượng ngắn mạch (short-circuit evaluation) của toán tử logic && trong C++? | 751s | 611s | 140s | và nó sẽ ra được kết quả của condition tổng web này trong trịu hợp này là nó lớn... |
| `BENCH-018` | 4 | Khi nào nên dùng cấu trúc switch case thay cho nhiều lệnh if else lồng nhau? | 1413s | 1715s | 302s | Cái default này thì bạn không cần break, bởi vì thằng sau, thằng default thì nó ... |
| `BENCH-019` | 4 | Từ khóa break trong khối lệnh switch case có vai trò gì và nếu thiếu thì sao? | 1669s | 1627s | 42s | Đó là một cái chữ ý như thế này. Đấy chính là trong cái câu chút switch cây này ... |
| `BENCH-021` | 4 | Toán tử ba ngôi (ternary operator) ?: có thể thay thế câu lệnh if-else đơn giản ra sao? | 180s | 751s | 571s | Ví dụ như là, mình nhập vào một số đúng không? Sau đó kiểm tra xem số đấy là số ... |
| `BENCH-025` | 6 | Cú pháp và cơ chế hoạt động của vòng lặp for trong C++ gồm những gì? | 52s | 1554s | 1502s | C++, string, Clip, sau khi mà xong vòng lập qua thì các bạn sẽ nằm kênh với một ... |
| `BENCH-027` | 6 | Vòng lặp vô tận (infinite loop) xảy ra khi nào và cách khắc phục? | 1366s | 741s | 625s | Điểm tiện lập của mình là rất là y lời của một, và tiện tếp đầy của mình là rất ... |
| `BENCH-031` | 6 | Làm sao để duyệt ngược từ N về 1 bằng vòng lặp for? | 1554s | 1366s | 188s | Và các bạn chú ý là cái vòng for này nó sẽ thực hiện, nó sẽ được dùng khi mà bạn... |
| `BENCH-032` | 6 | Khi nào nên dùng vòng lặp while thay vì for trong việc xử lý số nguyên? | 2249s | 1366s | 883s | Và các bạn chú ý là cái vòng for này nó sẽ thực hiện, nó sẽ được dùng khi mà bạn... |
| `BENCH-037` | 7 | Toán tử & trong định nghĩa tham số hàm void func(int &x) có tác dụng gì? | 5750s | 1508s | 4242s | hoa luồng thứ 3 đấy là 2, 3 và 6, 5 em nghĩ là void nên nó in ra như vậy á Thực ... |
| `BENCH-046` | 53 | Cách viết hàm thành viên TinhGPA() của class SinhVien để tính điểm trung bình? | 1087s | 350s | 737s | class SinhVien { private: // Neu khong khai bao public ma chi khai bao moi may c... |
| `BENCH-057` | 54 | Cách gọi hàm chuanHoaThongTin() tự động ngay sau khi nhập dữ liệu sinh viên? | 3393s | 2541s | 852s | để lần mà nhập sinh viên sau ấy thì nó không bị chôi lại, chôi lại kết line này ... |
| `BENCH-058` | 18 | Toán tử s[i] dùng để truy cập từng ký tự trong biến std::string như thế nào? | 350s | 601s | 251s | Thì nó sẽ in là cái kết thúc y tế hot-off and off, ok? Thì đây chính là cái cách... |
| `BENCH-059` | 54 | Cách tách các từ trong họ tên bằng luồng stringstream trong C++? | 2980s | 3021s | 41s | Mình sẽ dùng string stream, nhưng mà cái này nó hơi bất tiệm, bởi vì là cái tên ... |
| `BENCH-068` | 56 | Hàm gcd có thể viết bằng thuật toán đệ quy ngắn gọn như thế nào? | 120s | 41s | 79s | Đấy là cái thế nhất, và cái thứ 2 đây chính là người ta nhập cái phân số này bằn... |
| `BENCH-070` | 56 | Có thể gán giá trị mặc định cho phân số là 0/1 bằng constructor không? | 2269s | 1042s | 1227s | và bây giờ các cái thông tin của mình nó sẽ đưa gán lần lượt để chính là mã thì ... |
| `BENCH-073` | 69 | Vì sao hàm nạp chồng toán tử nhập xuất << và >> cần được khai báo là friend? | 2824s | 1266s | 1558s | Các bạn không muốn khai báo cái hàm nhập với cái hàm in này là một cái hàm bạn c... |
| `BENCH-074` | 69 | Toán tử xuất << (operator<<) cần trả về kiểu tham chiếu std::ostream& để làm gì? | 5459s | 5507s | 48s | Vậy là mình đã nạp trong được cái tản thư xuất Thế còn cái toán thự nhập, thì tư... |

## 2. Danh Sách Lỗi Retrieval Thực Sự

| ID | Trạng thái thực tế | Lý do | Câu hỏi |
| :--- | :---: | :--- | :--- |
| `BENCH-004` | `out_of_lesson` | Status(Act: out_of_lesson != Exp: grounded), TS(Act: None != Exp: 1216, has_ts: False) | Sự khác nhau giữa float và double trong C++ là gì? |
| `BENCH-014` | `out_of_lesson` | Status(Act: out_of_lesson != Exp: grounded), TS(Act: None != Exp: 751, has_ts: False) | Làm thế nào để kiểm tra một số nguyên n có phải là số chẵn bằng toán tử %? |
| `BENCH-035` | `out_of_lesson` | Status(Act: out_of_lesson != Exp: grounded), TS(Act: None != Exp: 2638, has_ts: False) | Làm sao để viết hàm hoán đổi giá trị của 2 biến số nguyên swap? |
| `BENCH-041` | `out_of_lesson` | Status(Act: out_of_lesson != Exp: grounded), TS(Act: None != Exp: 2180, has_ts: False) | Khái niệm Lớp (Class) và Đối tượng (Object) trong C++ khác nhau như thế nào? |
| `BENCH-045` | `out_of_lesson` | Status(Act: out_of_lesson != Exp: grounded), TS(Act: None != Exp: 462, has_ts: False) | Vì sao các thuộc tính như hoTen, diemGPA nên đặt ở phạm vi private? |
| `BENCH-049` | `out_of_lesson` | Status(Act: out_of_lesson != Exp: grounded), TS(Act: None != Exp: 418, has_ts: False) | Con trỏ this trong phương thức của class C++ có vai trò gì? |
