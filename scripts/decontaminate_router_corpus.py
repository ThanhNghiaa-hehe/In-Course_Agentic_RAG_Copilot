"""
Script Khử Nhiễm Dữ Liệu Ngữ Liệu Huấn Luyện Router (Data Decontamination & Augmentation)
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Mục tiêu khoa học:
1. Sao lưu router_training_corpus.json sang router_training_corpus_v2_3_legacy.json.
2. Quét và loại bỏ 100% các mẫu trùng lặp (Exact Match) và cận trùng lặp (Jaccard >= 0.80) với 200 câu Golden Benchmark.
3. Sinh bổ sung các mẫu mới độc lập (Disjoint Guardrail: Jaccard < 0.70 so với Golden Benchmark) để đạt ~300 mẫu cân bằng.
4. Ghi đè router_training_corpus.json phiên bản 2.4.0 sạch hoàn toàn (Zero Data Leakage).
"""

import json
import shutil
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORPUS_PATH = PROJECT_ROOT / "data" / "metadata" / "router_training_corpus.json"
BACKUP_PATH = PROJECT_ROOT / "data" / "metadata" / "router_training_corpus_v2_3_legacy.json"
BENCHMARK_PATH = PROJECT_ROOT / "tests" / "data" / "benchmark_golden_dataset.json"


def norm(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text.lower().strip())
    clean = "".join(c if c.isalnum() else " " for c in text)
    return " ".join(clean.split())


def jaccard_similarity(s1: str, s2: str) -> float:
    w1 = set(norm(s1).split())
    w2 = set(norm(s2).split())
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / len(w1 | w2)


# =========================================================================
# DANH SÁCH MẪU MỚI ĐỘC LẬP CHUẨN BỊ BỔ SUNG (DISJOINT AUGMENTATION POOL)
# Tất cả đều không trùng với 200 câu Golden Benchmark
# =========================================================================

NEW_COURSE_QUERY_SAMPLES = [
    # Cú pháp & Kiểu dữ liệu cơ bản
    "Làm sao để dùng toán tử sizeof để kiểm tra kích thước bộ nhớ của một biến trong C++?",
    "Cách khai báo một biến tham chiếu reference và sự khác nhau với biến con trỏ thông thường?",
    "Tại sao không nên dùng biến toàn cục global variable một cách bừa bãi trong chương trình C++?",
    "Cú pháp sử dụng kiểu dữ liệu auto để tự động suy luận kiểu trong C++11?",
    "Khái niệm về phạm vi biến variable scope và thời gian sống variable lifetime trong C++?",
    "Làm thế nào để ép kiểu an toàn bằng static_cast thay vì ép kiểu kiểu C (C-style cast)?",
    "Ý nghĩa của từ khóa explicit trong hàm khởi tạo constructor của C++ là gì?",
    "Sự khác biệt giữa nullptr và NULL trong C++ hiện đại?",
    "Cách dùng toán tử 3 ngôi conditional operator để viết ngắn gọn câu lệnh if else?",
    "Tại sao chia cho số 0 trong C++ lại gây ra lỗi runtime crash chương trình?",
    
    # Cấu trúc điều khiển & Vòng lặp
    "Làm sao để thoát khỏi 2 vòng lặp for lồng nhau mà không dùng lệnh goto?",
    "Sự khác nhau giữa vòng lặp do-while và vòng lặp while thông thường khi điều kiện sai ngay lần đầu?",
    "Lệnh continue trong vòng lặp bỏ qua những câu lệnh nào?",
    "Làm cách nào để duyệt qua từng phần tử của mảng bằng range-based for loop trong C++?",
    "Cấu trúc switch case có hỗ trợ so sánh chuỗi std::string trực tiếp không?",
    "Làm sao để phòng ngừa lỗi vòng lặp vô tận infinite loop khi lập trình C++?",
    "Cách viết chương trình in ra bảng cửu chương bằng 2 vòng for lồng nhau?",
    "Khi nào dùng câu lệnh break trong cấu trúc rẽ nhánh switch case?",

    # Hàm & Đệ quy & Bộ nhớ Stack/Heap
    "Cơ chế truyền tham trị pass-by-value và truyền tham chiếu pass-by-reference hoạt động ra sao?",
    "Điều kiện dừng base case trong hàm đệ quy có vai trò quan trọng như thế nào?",
    "Hiện tượng tràn bộ nhớ stack overflow xảy ra khi đệ quy quá sâu là do đâu?",
    "Hàm nạp chồng function overloading trong C++ phân biệt các hàm dựa trên tiêu chí nào?",
    "Cách viết hàm trả về nhiều giá trị bằng cách dùng std::pair hoặc std::tuple?",
    "Hàm inline trong C++ giúp cải thiện hiệu năng thực thi như thế nào?",
    "Toán tử new và delete quản lý vùng nhớ heap khác gì so với vùng nhớ stack?",
    "Làm sao để giải phóng bộ nhớ động đúng cách để tránh memory leak?",
    "Con trỏ lơ lửng dangling pointer là gì và cách phòng tránh như thế nào?",
    "Toán tử tham chiếu & và toán tử giải tham chiếu * khác nhau ra sao khi thao tác con trỏ?",

    # Mảng, Chuỗi & STL Container
    "Làm sao để truyền mảng 1 chiều vào hàm như một tham số con trỏ trong C++?",
    "Sự khác nhau giữa mảng tĩnh C-style array và std::vector trong thư viện chuẩn STL?",
    "Cách dùng hàm push_back và pop_back để thêm bớt phần tử trong std::vector?",
    "Hàm size() và capacity() của std::vector khác nhau như thế nào?",
    "Cách xóa một ký tự bất kỳ trong chuỗi std::string bằng phương thức erase()?",
    "Làm sao để chuyển đổi một chuỗi std::string thành số nguyên bằng std::stoi?",
    "Cách dùng thuật toán std::sort để sắp xếp một vector theo thứ tự giảm dần?",
    "Cấu trúc dữ liệu std::set trong C++ tự động loại bỏ phần tử trùng lặp như thế nào?",
    "Sự khác biệt về độ phức tạp thời gian giữa std::map và std::unordered_map?",
    "Cách sử dụng iterator để duyệt qua các phần tử của một std::vector?",

    # Lập trình Hướng đối tượng (OOP)
    "Bốn tính chất cốt lõi của lập trình hướng đối tượng OOP trong C++ là gì?",
    "Tại sao nên đặt thuộc tính là private và cung cấp các hàm getter setter?",
    "Constructor mặc định default constructor được trình biên dịch tự sinh ra khi nào?",
    "Hàm hủy destructor có vai trò gì và có thể nạp chồng destructor được không?",
    "Cách khởi tạo giá trị cho thuộc tính bằng Member Initializer List trong constructor?",
    "Từ khóa const đặt ở cuối phương thức của class có ý nghĩa gì?",
    "Hiện tượng che khuất tên biến name shadowing và cách dùng con trỏ this để phân biệt?",
    "Hàm bạn friend function có thể truy cập các thành viên private của class như thế nào?",
    "Kế thừa công khai public inheritance trong C++ thiết lập quan hệ IS-A ra sao?",
    "Hàm ảo virtual function và cơ chế đa hình runtime polymorphism hoạt động như thế nào?",
    "Bảng hàm ảo vtable và con trỏ vptr được tổ chức như thế nào trong bộ nhớ?",
    "Hàm ảo thuần túy pure virtual function và khái niệm Abstract Class là gì?",
    "Tại sao hàm hủy của lớp cơ sở base class luôn cần khai báo là virtual?",
    "Vấn đề hình thoi diamond problem trong đa kế thừa C++ được giải quyết bằng virtual inheritance ra sao?",
    "Nạp chồng toán tử cộng operator+ để cộng hai đối tượng phân số như thế nào?"
]

NEW_OUT_OF_SCOPE_SAMPLES = [
    # Lập trình ngôn ngữ khác (Python, Java, JS, C#)
    "Làm sao để tạo một môi trường ảo virtualenv trong Python?",
    "Cú pháp khai báo decorator trong Python hoạt động như thế nào?",
    "Cách kết nối cơ sở dữ liệu MongoDB bằng Mongoose trong Node.js?",
    "Sự khác nhau giữa Interface và Abstract Class trong ngôn ngữ Java?",
    "Làm thế nào để cài đặt framework React 19 với Vite?",
    "Cách viết truy vấn SELECT JOIN giữa hai bảng trong PostgreSQL?",
    "Làm sao để cấu hình Dockerfile để đóng gói một ứng dụng FastAPI?",
    "Cách sử dụng async await trong JavaScript để gọi API?",
    "Làm thế nào để deploy một ứng dụng web lên Kubernetes cluster?",
    "Sự khác nhau giữa CSS Flexbox và CSS Grid khi căn chỉnh giao diện?",
    "Cách dùng Git rebase để gộp các commit trước khi tạo Pull Request?",
    "Làm sao để cấu hình CI/CD pipeline với GitHub Actions?",
    "Khái niệm microservices khác gì so với monolithic architecture?",
    
    # Khoa học, Toán cao cấp & Đời sống
    "Công thức tính đạo hàm riêng cấp 2 của hàm nhiều biến là gì?",
    "Giải thích định lý Bayes trong xác suất thống kê ứng dụng?",
    "Thời tiết ngày mai ở Hà Nội có mưa không hả bạn?",
    "Chỉ cho mình công thức nấu món bún bò Huế chuẩn vị truyền thống",
    "Đội tuyển bóng đá nào vô địch World Cup 2022?",
    "Giá vàng SJC hôm nay tăng hay giảm bao nhiêu một chỉ?",
    "Tư vấn cho mình lộ trình học tiếng Anh để đạt IELTS 7.0 từ con số 0",
    "Gợi ý cho mình một cuốn sách hay về tâm lý học hành vi",
    "Làm thế nào để giảm cân an toàn trong vòng 1 tháng?",
    "Thủ đô của nước Úc là thành phố nào vậy bạn?",
    "Tư vấn cấu hình máy tính để chơi game mượt trong tầm giá 20 triệu",
    "Cách khắc phục tình trạng mất ngủ ban đêm hiệu quả nhất?",
    "Kinh tế thế giới năm nay có dấu hiệu suy thoái hay phục hồi?",
    "Giá vé máy bay khứ hồi từ Sài Gòn ra Đà Nẵng tháng này bao nhiêu?",
    "Tư vấn giúp em chọn trường đại học khối A1 ở TP.HCM",
    "Chỉ cho em cách viết CV xin việc ngành Marketing ấn tượng",
    "Cách làm món cà phê muối thơm béo tại nhà đơn giản nhất",
    "Tại sao bầu trời ban ngày lại có màu xanh lam?",
    "Giải thích nguyên lý hoạt động của động cơ phản lực trên máy bay",
    "Cho em hỏi quy trình đăng ký giấy phép lái xe A1 gồm những bước nào?"
]

NEW_CHIT_CHAT_SAMPLES = [
    # Chào hỏi tự nhiên
    "Chào buổi sáng trợ giảng nhé!",
    "Chào buổi tối bot, hôm nay bạn thế nào?",
    "Hi copilot, chúc bạn một ngày làm việc hiệu quả nhé!",
    "Alo có ai ở đây không?",
    "Hello bot thân mến",
    "Chào bạn nha, mình vừa mới vào học bài",
    "Chào bạn, rất vui được làm quen với bạn!",
    "Good morning trợ giảng AI!",
    "Yo copilot!",
    "Chào bạn nhé, hôm nay mình lại tiếp tục học code nè",

    # Cảm ơn & Khen ngợi
    "Cảm ơn bot rất nhiều, bạn giải thích dễ hiểu lắm!",
    "Thanks bạn nhé, nhờ bạn mà mình hiểu ra bản chất vấn đề rồi!",
    "Tuyệt vời quá, trợ giảng nhiệt tình số 1 luôn!",
    "Mình cảm ơn copilot nhiều nha, câu trả lời rất có tâm!",
    "Cảm ơn trợ giảng đã kiên nhẫn hướng dẫn mình!",
    "Bạn thông minh và hỗ trợ rất nhanh, cảm ơn nhé!",
    "Cảm ơn bạn nhiều, giải thích theo kiểu gợi mở này thích thật!",
    "Bạn giảng hay hơn cả thầy trên lớp nữa, cảm ơn bạn!",

    # Hỏi thăm danh tính & Trò chuyện sư phạm
    "Bạn là ai và có thể giúp gì cho mình trong khóa học này?",
    "Tên của bạn là gì vậy bot?",
    "Bạn được tạo ra bởi ai thế?",
    "Bạn có phải là trợ giảng chính thức của khóa học C++ này không?",
    "Phương pháp giảng dạy Socratic của bạn là gì vậy?",
    "Hôm nay bạn có khỏe không copilot?",
    "Bạn học lập trình C++ từ đâu mà giỏi thế?",
    
    # Tạm biệt
    "Tạm biệt bot nhé, hôm nay mình học đến đây thôi mai học tiếp!",
    "Bye bye copilot, chúc bạn buổi tối vui vẻ!",
    "Mình đi ngủ đây, hẹn gặp lại bạn vào ngày mai nhé!",
    "Hẹn gặp lại trợ giảng trong buổi học sau!",
    "Tạm biệt nhé, cảm ơn bạn đã đồng hành cùng mình tối nay!"
]


def main():
    print("=" * 80)
    print("QUY TRÌNH KHỬ NHIỄM DỮ LIỆU HUẤN LUYỆN (DATA DECONTAMINATION PROTOCOL)")
    print("=" * 80)

    # 1. Sao lưu corpus cũ
    shutil.copy2(CORPUS_PATH, BACKUP_PATH)
    print(f"[BƯỚC 1] Đã sao lưu an toàn tệp gốc sang: {BACKUP_PATH.name}")

    # 2. Đọc tập benchmark 200 câu
    with open(BENCHMARK_PATH, "r", encoding="utf-8") as f:
        benchmark_data = json.load(f)
    print(f"[BƯỚC 2] Nạp {len(benchmark_data)} câu từ Frozen Held-out Benchmark.")

    benchmark_queries = []
    for item in benchmark_data:
        q = item.get("query") or item.get("prompt") or ""
        if q:
            benchmark_queries.append(q)

    # 3. Đọc tập huấn luyện hiện tại
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        corpus_data = json.load(f)
    raw_samples = corpus_data.get("samples", [])
    print(f"[BƯỚC 3] Tập huấn luyện hiện tại có: {len(raw_samples)} mẫu.")

    # 4. Lọc bỏ các mẫu bị leak (Exact Match hoặc Jaccard >= 0.80)
    clean_retained_samples = []
    leaked_count = 0

    for sample in raw_samples:
        s_text = sample.get("text", "")
        is_leaked = False
        max_sim = 0.0

        for b_q in benchmark_queries:
            # Check exact match sau khi chuẩn hóa
            if norm(s_text) == norm(b_q):
                is_leaked = True
                max_sim = 1.0
                break
            # Check Jaccard
            sim = jaccard_similarity(s_text, b_q)
            if sim > max_sim:
                max_sim = sim
            if sim >= 0.80:
                is_leaked = True
                break

        if is_leaked:
            leaked_count += 1
        else:
            clean_retained_samples.append(sample)

    print(f"[BƯỚC 4] Đã loại bỏ triệt để: {leaked_count} mẫu bị nhiễm độc / rò rỉ đề thi.")
    print(f"         Số mẫu sạch giữ lại: {len(clean_retained_samples)} mẫu.")

    # 5. Thẩm định và bổ sung mẫu mới độc lập (Disjoint Check)
    print(f"\n[BƯỚC 5] Kiểm chuẩn và bổ sung mẫu mới độc lập...")

    def check_and_add_samples(sample_list: List[str], intent_label: str):
        added = 0
        for text in sample_list:
            # Bắt buộc max Jaccard với benchmark < 0.70
            max_sim = max((jaccard_similarity(text, b_q) for b_q in benchmark_queries), default=0.0)
            if max_sim < 0.70:
                clean_retained_samples.append({
                    "text": text,
                    "intent": intent_label
                })
                added += 1
            else:
                print(f"  [BỎ QUA] Mẫu có độ tương đồng cao với benchmark (J={max_sim:.2f}): '{text}'")
        return added

    n_added_course = check_and_add_samples(NEW_COURSE_QUERY_SAMPLES, "course_query")
    n_added_oos = check_and_add_samples(NEW_OUT_OF_SCOPE_SAMPLES, "out_of_scope")
    n_added_chat = check_and_add_samples(NEW_CHIT_CHAT_SAMPLES, "chit_chat")

    print(f"  + Đã bổ sung thành công course_query: {n_added_course} mẫu.")
    print(f"  + Đã bổ sung thành công out_of_scope: {n_added_oos} mẫu.")
    print(f"  + Đã bổ sung thành công chit_chat   : {n_added_chat} mẫu.")
    print(f"  -> Tổng số mẫu sạch sau tăng cường: {len(clean_retained_samples)} mẫu.")

    # 6. Kiểm toán lần cuối: Zero Leakage Verification
    final_leak_check = 0
    for s in clean_retained_samples:
        s_text = s["text"]
        for b_q in benchmark_queries:
            if norm(s_text) == norm(b_q) or jaccard_similarity(s_text, b_q) >= 0.80:
                final_leak_check += 1

    print("-" * 80)
    print(f"KẾT QUẢ KIỂM TOÁN CHỐT HẠ (FINAL ZERO-LEAKAGE VERIFICATION):")
    print(f"Số mẫu trùng lặp còn lại: {final_leak_check} (0.00% Leakage)")
    assert final_leak_check == 0, "LỖI BẤT BIẾN: Vẫn còn mẫu rò rỉ dữ liệu trong tập huấn luyện!"

    # 7. Ghi đè tập ngữ liệu sạch chuẩn 2.4.0
    decontaminated_data = {
        "description": "Tập ngữ liệu huấn luyện ý định đa lớp khử nhiễm độc lập chuẩn hóa (Decontaminated Intent Training Corpus)",
        "version": "2.4.0",
        "author": "Trần Thành Nghĩa (MSSV: 23DH112252)",
        "university": "HUFLIT",
        "classes": [
            "chit_chat",
            "course_query",
            "out_of_scope"
        ],
        "samples": clean_retained_samples
    }

    with open(CORPUS_PATH, "w", encoding="utf-8") as f:
        json.dump(decontaminated_data, f, ensure_ascii=False, indent=2)

    print(f"[BƯỚC 7] Đã lưu thành công tập ngữ liệu sạch v2.4.0 tại: {CORPUS_PATH.name}")
    print("=" * 80)


if __name__ == "__main__":
    main()
