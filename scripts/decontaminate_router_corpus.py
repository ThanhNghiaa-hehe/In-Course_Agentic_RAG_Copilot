"""
Script Khử Nhiễm Toàn Diện Dữ Liệu Ngữ Liệu Huấn Luyện Router (Double Decontamination Protocol v2.8.0)
In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Mục tiêu khoa học:
1. Sao lưu an toàn router_training_corpus.json sang router_training_corpus_v2_7_legacy.json.
2. Quét và loại bỏ 100% các mẫu trùng lặp và cận trùng lặp (Jaccard >= 0.70) với CẢ 2 bộ test độc lập:
   - 200 câu Frozen Held-Out Golden Benchmark (tests/data/benchmark_golden_dataset.json)
   - 100 câu Unseen OOD Stress Test (tests/data/ood_stress_test_dataset.json)
3. Tăng cường các mẫu độc lập (Disjoint Augmentation Pool) bảo chứng Jaccard < 0.70 trên cả 2 tập test.
4. Xuất bản router_training_corpus.json phiên bản 2.8.0 sạch 100% (0.00% Data Leakage) với phân phối cân bằng.
"""

import json
import shutil
import unicodedata
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORPUS_PATH = PROJECT_ROOT / "data" / "metadata" / "router_training_corpus.json"
BACKUP_PATH = PROJECT_ROOT / "data" / "metadata" / "router_training_corpus_v2_7_legacy.json"
BENCHMARK_PATH = PROJECT_ROOT / "tests" / "data" / "benchmark_golden_dataset.json"
OOD_PATH = PROJECT_ROOT / "tests" / "data" / "ood_stress_test_dataset.json"


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
# Tất cả đều không trùng với 200 câu Golden Benchmark và 100 câu OOD
# =========================================================================

CANDIDATE_COURSE_QUERY = [
    # Cú pháp & Kiểu dữ liệu C++ nâng cao
    "Làm sao để dùng static_cast để chuyển đổi an toàn giữa float và int trong C++?",
    "Cú pháp sử dụng kiểu dữ liệu auto để trình biên dịch tự suy luận kiểu biến trong C++11?",
    "Tại sao không nên khai báo biến toàn cục bừa bãi trong các project C++ lớn?",
    "Ý nghĩa của từ khóa explicit trước constructor 1 tham số trong C++ là gì?",
    "Sự khác biệt về an toàn bộ nhớ giữa nullptr và con trỏ NULL kiểu C?",
    "Cách dùng toán tử 3 ngôi ternary operator lồng nhau để phân loại kết quả học lực?",
    "Tại sao chia cho số nguyên 0 trong C++ lại làm ứng dụng crash ngay lập tức?",
    "Khái niệm const reference tham chiếu hằng giúp tối ưu hiệu năng truyền tham số ra sao?",
    "Làm thế nào để sử dụng typedef hoặc using để định nghĩa bí danh kiểu dữ liệu trong C++?",
    "Ý nghĩa của từ khóa volatile khi khai báo biến phần cứng trong lập trình C++ là gì?",

    # Cấu trúc điều khiển & Vòng lặp
    "Làm sao để thoát khỏi 2 vòng lặp lồng nhau mà không cần dùng câu lệnh goto?",
    "Cấu trúc switch case có cho phép kiểm tra biến kiểu chuỗi std::string không?",
    "Khi nào ta nên ưu tiên dùng vòng lặp do while thay vì vòng lặp while trong bài toán menu?",
    "Làm cách nào để duyệt qua từng phần tử của mảng một chiều bằng range based for loop?",
    "Cơ chế ngắn mạch short circuit evaluation trong biểu thức logic AND và OR hoạt động ra sao?",
    "Làm sao để viết cấu trúc điều khiển lặp lùi từ n về 0 mà không bị lỗi dưới ngưỡng unsigned int?",
    "Cách dùng enum class trong C++11 để định nghĩa các trạng thái an toàn kiểu?",

    # Hàm, Phạm vi biến & Bộ nhớ
    "Điều kiện dừng base condition trong giải thuật đệ quy có vai trò quyết định ra sao?",
    "Hiện tượng stack overflow khi đệ quy quá sâu xảy ra do cấu trúc vùng nhớ nào bị đầy?",
    "Hàm nạp chồng function overloading phân biệt các phiên bản dựa trên chữ ký hàm thế nào?",
    "Cách khai báo hàm inline để giảm chi phí overhead gọi hàm trong vòng lặp lớn?",
    "Hàm trả về con trỏ vùng nhớ stack có gây ra lỗi lơ lửng dangling pointer không?",
    "Sự khác biệt về tốc độ truy xuất và dung lượng giữa bộ nhớ stack và heap trong C++?",
    "Làm sao dùng con trỏ thông minh std::unique_ptr để tự động thu hồi vùng nhớ heap?",
    "Tại sao toán tử new[] cho mảng phải đi kèm với delete[] tương ứng?",
    "Con trỏ hằng const int* khác với hằng con trỏ int* const ở vị trí nào?",
    "Làm thế nào để truyền mảng 2 chiều kích thước động vào một hàm xử lý ma trận?",

    # Mảng, Chuỗi & Cấu trúc dữ liệu STL
    "Sự khác biệt giữa mảng tĩnh C-style và std::vector về mặt tự động cấp phát lại bộ nhớ?",
    "Hàm capacity() và size() của std::vector phản ánh điều gì về dung lượng mảng động?",
    "Cách sử dụng std::sort với hàm so sánh tùy biến lambda để sắp xếp mảng cấu trúc?",
    "Cấu trúc dữ liệu std::set trong STL tự động cân bằng cây và loại bỏ phần tử trùng ra sao?",
    "Độ phức tạp thời gian khi tìm kiếm phần tử trong std::unordered_map so với std::map?",
    "Cách duyệt và xóa an toàn một phần tử trong std::vector bằng iterator và erase?",
    "Làm sao để tách một chuỗi std::string thành các từ riêng biệt bằng std::stringstream?",
    "Hàm substr() trong thư viện string nhận tham số vị trí bắt đầu và số lượng ký tự như thế nào?",

    # Lập trình Hướng đối tượng OOP
    "Bốn trụ cột chính của lập trình hướng đối tượng trong C++ gồm những tính chất nào?",
    "Tại sao nên che giấu dữ liệu bằng phạm vi private và cung cấp getter setter trong class?",
    "Hàm tạo sao chép copy constructor được kích hoạt tự động trong những tình huống nào?",
    "Cách dùng danh sách khởi tạo member initializer list để khởi tạo thuộc tính const trong class?",
    "Từ khóa const đặt ở đuôi của phương thức class có tác dụng bảo vệ dữ liệu ra sao?",
    "Hàm bạn friend function có thể truy cập vào vùng private của class như thế nào?",
    "Hàm ảo virtual function giúp trình biên dịch thực hiện liên kết muộn late binding ra sao?",
    "Bảng hàm ảo vtable và con trỏ vptr được tổ chức như thế nào cho từng đối tượng đa hình?",
    "Hàm thuần ảo pure virtual function và khái niệm Abstract Class được thiết kế ra sao?",
    "Tại sao hàm hủy của lớp cơ sở base class luôn bắt buộc phải khai báo là virtual?",
    "Vấn đề hình thoi diamond problem trong đa kế thừa được giải quyết bằng virtual inheritance thế nào?",
    "Nạp chồng toán tử gán assignment operator= cần kiểm tra điều kiện tự gán this != &other ra sao?",
    "Thành viên tĩnh static variable trong class được chia sẻ chung cho mọi thực thể như thế nào?",
    "Cơ chế nạp chồng toán tử cộng operator+ để thực hiện phép cộng trên hai vector toán học?",
    "Cách viết class khuôn mẫu template để tái sử dụng cấu trúc ngăn xếp cho mọi kiểu dữ liệu?"
]

CANDIDATE_OUT_OF_SCOPE = [
    # Ngôn ngữ lập trình & Framework khác ngoài phạm vi C++
    "Làm sao để tạo một môi trường ảo virtualenv bằng lệnh python -m venv trong Python?",
    "Cú pháp khai báo decorator @staticmethod và @classmethod trong Python khác nhau ra sao?",
    "Cách kết nối cơ sở dữ liệu MongoDB bằng thư viện Mongoose trong môi trường Node.js?",
    "Sự khác biệt giữa Interface và Abstract Class trong ngôn ngữ lập trình Java?",
    "Làm thế nào để khởi tạo một dự án React 19 kết hợp với Vite bằng lệnh npm create vite?",
    "Cách viết câu lệnh truy vấn SELECT lồng nhau kết hợp LEFT JOIN trong PostgreSQL?",
    "Làm sao để viết tệp Dockerfile nhiều giai đoạn multi-stage build để tối ưu dung lượng image?",
    "Cách xử lý bất đồng bộ bằng async await kết hợp Promise.all trong JavaScript?",
    "Làm thế nào để triển khai một ứng dụng web microservices lên cụm Kubernetes?",
    "Sự khác biệt giữa CSS Grid và CSS Flexbox khi căn chỉnh bố cục giao diện web responsive?",
    "Cách dùng lệnh git rebase -i để gộp các commit lịch sử trước khi tạo pull request?",
    "Làm sao để viết workflow CI/CD tự động chạy kiểm thử bằng GitHub Actions?",
    "Kiến trúc Clean Architecture trong backend Java Spring Boot gồm những tầng nào?",
    "Làm thế nào để deploy mô hình Machine Learning lên Hugging Face Spaces?",

    # Đời sống, thể thao, khoa học & văn hóa
    "Công thức tính tích phân suy rộng cấp 1 của hàm số vô tỷ trong giải tích toán học?",
    "Giải thích ý nghĩa của định lý giới hạn trung tâm Central Limit Theorem trong xác suất?",
    "Dự báo thời tiết cuối tuần này tại thành phố Đà Lạt có thích hợp đi dã ngoại không?",
    "Hướng dẫn công thức nấu món lẩu thái hải sản chua cay thơm ngon chuẩn vị?",
    "Cầu thủ bóng đá nào đang nắm giữ kỷ lục ghi nhiều bàn thắng nhất lịch sử Champions League?",
    "Biến động giá vàng thế giới và tỷ giá đồng USD hôm nay có xu hướng tăng hay giảm?",
    "Lộ trình ôn thi chứng chỉ IELTS Academic từ band 5.0 lên band 7.5 trong vòng 6 tháng?",
    "Gợi ý một số cuốn sách kinh điển về phát triển tư duy phản biện và quản lý tài chính cá nhân?",
    "Các phương pháp khoa học giúp giảm mỡ bụng an toàn mà không làm mất cơ bắp?",
    "Thủ đô hành chính của đất nước Nam Phi nằm ở thành phố nào vậy bạn?",
    "Tư vấn cấu hình máy tính bàn để dựng phim 4K và render 3D trong tầm giá 30 triệu?",
    "Những thói quen tốt vào buổi tối giúp cải thiện chất lượng giấc ngủ sâu?",
    "Hiện tượng nguyệt thực toàn phần xảy ra khi vị trí của Trái Đất, Mặt Trời và Mặt Trăng ra sao?",
    "Nguyên lý hoạt động của hệ thống phanh chống bó cứng ABS trên xe ô tô hiện đại?"
]

CANDIDATE_CHIT_CHAT = [
    # Chào hỏi sư phạm & Khởi động buổi học
    "Chào buổi sáng trợ giảng AI, chúc bạn một ngày làm việc tràn đầy năng lượng!",
    "Chào buổi tối bot, hôm nay mình tiếp tục đồng hành cùng bạn học code nhé!",
    "Hi copilot, mình đã sẵn sàng cho buổi học hôm nay rồi nè!",
    "Alo trợ giảng ơi, bạn có đang trực ca trực tuyến không?",
    "Hello bot thân mến, rất vui được gặp lại bạn trong khóa học này!",
    "Chào bạn nhé, hôm nay mình sẽ cố gắng hoàn thành hết bài tập C++!",
    "Chào trợ giảng, hôm nay tâm trạng của bạn thế nào?",
    "Good evening copilot, hy vọng hôm nay bạn sẽ giúp mình khai sáng nhiều kiến thức hay!",
    "Chào bot nhé, chúc bạn có một ca hỗ trợ học viên thật hiệu quả!",
    "Hi bạn trợ lý ảo dễ thương của môn lập trình C++!",

    # Cảm ơn & Ghi nhận giá trị sư phạm gợi mở
    "Cảm ơn bot rất nhiều, cách bạn đặt câu hỏi gợi ý làm mình tự nhận ra chỗ sai!",
    "Cảm ơn trợ giảng đã kiên nhẫn dẫn dắt mà không giải bài hộ mình!",
    "Nhờ bạn giải thích cặn kẽ bản chất mà mình đã thông suốt phần logic này rồi, cảm ơn nhé!",
    "Tuyệt vời lắm bot, phong cách giảng dạy Socratic của bạn rất cuốn hút!",
    "Mình cảm ơn copilot nhiều nha, bạn là người bạn học tập tuyệt vời nhất của mình!",
    "Cảm ơn bạn đã luôn hỗ trợ nhiệt tình mỗi khi mình gặp bài toán khó!",
    "Cách bạn hướng dẫn từng bước nhỏ giúp mình nhớ kiến thức lâu hơn rất nhiều, thanks bạn!",
    "Cảm ơn trợ giảng, nhờ bạn mà mình thấy việc học C++ không còn quá đáng sợ nữa!",
    "Giải thích rất sắc sảo và đi đúng trọng tâm, mình cảm ơn bạn nhiều nhé!",
    "Cảm ơn bot nha, bạn kiên nhẫn hơn cả mong đợi của mình luôn!",

    # Hỏi thăm danh tính, vai trò & Nguyên tắc Socratic
    "Bạn là ai và sứ mệnh của bạn trong hệ thống học tập này là gì?",
    "Ai là người đã thiết kế và lập trình ra bạn vậy copilot?",
    "Tên gọi chính thức của bạn trong đồ án này là gì?",
    "Tại sao bạn lại luôn từ chối viết sẵn toàn bộ code giải bài mà chỉ đưa ra gợi ý?",
    "Phương pháp vấn đáp Socratic mà bạn đang áp dụng có nguồn gốc từ triết gia nào?",
    "Bạn có thể hỗ trợ những môn học lập trình nào trong nền tảng web này?",
    "Mục tiêu đào tạo của bạn là giúp sinh viên rèn luyện tư duy tự giải quyết vấn đề đúng không?",
    "Hôm nay bạn đã trợ giúp cho bao nhiêu bạn sinh viên rồi bot?",
    "Bạn có cảm thấy mệt mỏi khi phải trả lời hàng trăm câu hỏi mỗi ngày không?",

    # Tạm biệt, động viên & Hẹn gặp lại
    "Hôm nay mình học đến đây thôi, cảm ơn trợ giảng và chúc bạn ngủ ngon!",
    "Tạm biệt bot nhé, ngày mai mình sẽ quay lại học tiếp phần nạp chồng toán tử!",
    "Bye bye copilot, hẹn gặp lại bạn trong buổi học tiếp theo vào tối mai!",
    "Mình hoàn thành xong bài tập của ngày hôm nay rồi, tạm biệt bạn nhé!",
    "Cảm ơn bạn đã đồng hành cùng mình suốt buổi học hôm nay, bye bye!",
    "Hẹn gặp lại trợ giảng thân yêu vào ngày mai, chúc bạn một buổi tối an lành!",
    "Mình tắt máy đi nghỉ ngơi đây, cảm ơn bạn rất nhiều vì sự hướng dẫn tận tình!",
    "Tạm biệt nhé, mai mình sẽ lại nhờ bạn giải đáp thêm các thắc mắc về con trỏ!"
]


def main():
    print("=" * 80)
    print("QUY TRÌNH KHỬ NHIỄM KÉP TOÀN DIỆN (DATA DECONTAMINATION PROTOCOL v2.8.0)")
    print("In-Course Agentic RAG Copilot - Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT")
    print("=" * 80)

    # 1. Sao lưu corpus cũ
    shutil.copy2(CORPUS_PATH, BACKUP_PATH)
    print(f"[BƯỚC 1] Đã sao lưu an toàn tệp gốc sang: {BACKUP_PATH.name}")

    # 2. Đọc tập benchmark 200 câu
    with open(BENCHMARK_PATH, "r", encoding="utf-8") as f:
        benchmark_data = json.load(f)
    benchmark_queries = [item.get("query") or item.get("prompt") or "" for item in benchmark_data]
    print(f"[BƯỚC 2] Nạp {len(benchmark_queries)} câu từ Frozen Held-out Golden Benchmark.")

    # 3. Đọc tập OOD Stress Test 100 câu
    with open(OOD_PATH, "r", encoding="utf-8") as f:
        ood_data = json.load(f)
    ood_queries = [item.get("query") or item.get("prompt") or "" for item in ood_data]
    print(f"[BƯỚC 3] Nạp {len(ood_queries)} câu từ Unseen OOD Stress Test.")

    # 4. Đọc tập huấn luyện hiện tại
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        corpus_data = json.load(f)
    raw_samples = corpus_data.get("samples", [])
    print(f"[BƯỚC 4] Tập huấn luyện hiện tại có: {len(raw_samples)} mẫu.")

    # 5. Lọc bỏ các mẫu bị leak với Benchmark HOẶC OOD
    clean_retained_samples = []
    leaked_bench_count = 0
    leaked_ood_count = 0

    bench_norm_set = {norm(q) for q in benchmark_queries}
    ood_norm_set = {norm(q) for q in ood_queries}

    for sample in raw_samples:
        s_text = sample.get("text", "")
        n_text = norm(s_text)

        # Check Golden Benchmark
        is_leak = False
        if n_text in bench_norm_set:
            is_leak = True
            leaked_bench_count += 1
        else:
            max_sim = max((jaccard_similarity(s_text, b_q) for b_q in benchmark_queries), default=0.0)
            if max_sim >= 0.70:
                is_leak = True
                leaked_bench_count += 1

        if is_leak:
            continue

        # Check OOD Stress Test
        if n_text in ood_norm_set:
            is_leak = True
            leaked_ood_count += 1
        else:
            max_sim = max((jaccard_similarity(s_text, o_q) for o_q in ood_queries), default=0.0)
            if max_sim >= 0.70:
                is_leak = True
                leaked_ood_count += 1

        if not is_leak:
            clean_retained_samples.append(sample)

    print(f"[BƯỚC 5] Đã loại bỏ triệt để: {leaked_bench_count} mẫu rò rỉ Golden Benchmark.")
    print(f"         Đã loại bỏ triệt để: {leaked_ood_count} mẫu rò rỉ OOD Stress Test.")
    print(f"         Số mẫu sạch giữ lại: {len(clean_retained_samples)} mẫu.")
    print(f"         Phân phối nhãn sạch: {Counter(s['intent'] for s in clean_retained_samples)}")

    # 6. Thẩm định và bổ sung mẫu mới độc lập (Disjoint Check)
    print(f"\n[BƯỚC 6] Kiểm chuẩn và bổ sung mẫu mới độc lập từ Disjoint Pool...")
    existing_norm_set = {norm(s["text"]) for s in clean_retained_samples}

    def check_and_add_samples(sample_list: List[str], intent_label: str):
        added = 0
        for text in sample_list:
            n_t = norm(text)
            if n_t in existing_norm_set:
                continue
            max_sim_bench = max((jaccard_similarity(text, b_q) for b_q in benchmark_queries), default=0.0)
            if max_sim_bench >= 0.70:
                print(f"  [BỎ QUA - Bench J={max_sim_bench:.2f}]: '{text}'")
                continue
            max_sim_ood = max((jaccard_similarity(text, o_q) for o_q in ood_queries), default=0.0)
            if max_sim_ood >= 0.70:
                print(f"  [BỎ QUA - OOD J={max_sim_ood:.2f}]: '{text}'")
                continue

            clean_retained_samples.append({
                "text": text,
                "intent": intent_label
            })
            existing_norm_set.add(n_t)
            added += 1
        return added

    n_added_course = check_and_add_samples(CANDIDATE_COURSE_QUERY, "course_query")
    n_added_oos = check_and_add_samples(CANDIDATE_OUT_OF_SCOPE, "out_of_scope")
    n_added_chat = check_and_add_samples(CANDIDATE_CHIT_CHAT, "chit_chat")

    print(f"  + Đã bổ sung thành công course_query: {n_added_course} mẫu.")
    print(f"  + Đã bổ sung thành công out_of_scope: {n_added_oos} mẫu.")
    print(f"  + Đã bổ sung thành công chit_chat   : {n_added_chat} mẫu.")
    print(f"  -> Tổng số mẫu sạch sau tăng cường: {len(clean_retained_samples)} mẫu.")
    print(f"  -> Phân phối nhãn cuối cùng: {Counter(s['intent'] for s in clean_retained_samples)}")

    # 7. Kiểm toán chốt hạ: Zero Leakage Verification
    max_j_bench_final = 0.0
    final_leak_bench = 0
    for s in clean_retained_samples:
        s_text = s["text"]
        for b_q in benchmark_queries:
            j = jaccard_similarity(s_text, b_q)
            if j > max_j_bench_final:
                max_j_bench_final = j
            if norm(s_text) == norm(b_q) or j >= 0.70:
                final_leak_bench += 1

    max_j_ood_final = 0.0
    final_leak_ood = 0
    for s in clean_retained_samples:
        s_text = s["text"]
        for o_q in ood_queries:
            j = jaccard_similarity(s_text, o_q)
            if j > max_j_ood_final:
                max_j_ood_final = j
            if norm(s_text) == norm(o_q) or j >= 0.70:
                final_leak_ood += 1

    print("-" * 80)
    print(f"KẾT QUẢ KIỂM TOÁN CHỐT HẠ (FINAL ZERO-LEAKAGE VERIFICATION):")
    print(f"Max Jaccard với Golden Benchmark: {max_j_bench_final:.4f} (< 0.70) | Leakage: {final_leak_bench} (0.00%)")
    print(f"Max Jaccard với OOD Stress Test:   {max_j_ood_final:.4f} (< 0.70) | Leakage: {final_leak_ood} (0.00%)")
    assert final_leak_bench == 0, "LỖI BẤT BIẾN: Vẫn còn mẫu rò rỉ Golden Benchmark!"
    assert final_leak_ood == 0, "LỖI BẤT BIẾN: Vẫn còn mẫu rò rỉ OOD Stress Test!"

    # 8. Ghi đè tập ngữ liệu sạch chuẩn 2.8.0
    decontaminated_data = {
        "description": "Tập ngữ liệu huấn luyện ý định đa lớp khử nhiễm độc lập kép chuẩn hóa (Double-Decontaminated Intent Training Corpus)",
        "version": "2.8.0",
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

    print(f"[BƯỚC 8] Đã lưu thành công tập ngữ liệu sạch v2.8.0 tại: {CORPUS_PATH.name}")
    print("=" * 80)


if __name__ == "__main__":
    main()
