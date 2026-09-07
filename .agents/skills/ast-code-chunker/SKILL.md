---
name: ast-code-chunker
description: AST-aware semantic code chunking using Tree-sitter for C++ and Java. Enforces clean function/class boundaries without cutting code lines, maps code scopes to lesson sequences, and indexes code AST chunks into Qdrant.
---

# AST Code Chunker Runbook (Tree-sitter Parsing)

## 1. Mục Đích & Phạm Vi Áp Dụng
Sử dụng kỹ năng này khi:
- Chuẩn bị và phân tích cú pháp mã nguồn C++/Java trong thư mục `data/sample_codes/cpp-core/` (`lesson_01.cpp`, `lesson_02.cpp`).
- Cắt mã nguồn thành các khối ngữ nghĩa (Semantic Chunks) theo ranh giới cú pháp thực tế: định nghĩa hàm (`function_definition`), lớp (`class_specifier`), cấu trúc (`struct_specifier`), hoặc tiền xử lý (`preproc_include`).
- Kiểm tra tính toàn vẹn cú pháp, đảm bảo **tuyệt đối không cắt ngang thân hàm** hoặc chia nhỏ theo số lượng ký tự cơ học.
- Chuẩn bị nạp các điểm code vào Qdrant Cloud với `content_type="code_ast"`.

---

## 2. Quy Trình Thực Hiện & Debug (Step-by-Step)

```text
[BƯỚC 1: LOAD SOURCE CODE] ➔ [BƯỚC 2: PARSE AST TREE] ➔ [BƯỚC 3: EXTRACT BOUNDARIES] ➔ [BƯỚC 4: ENRICH METADATA] ➔ [BƯỚC 5: INDEX & VERIFY]
```

### Bước 1: Chuẩn Bị & Đọc Mã Nguồn Mẫu
1. Kiểm tra các file mã nguồn mẫu trong:
   - `data/sample_codes/cpp-core/lesson_01.cpp` (Biến, hằng số `const`, lệnh `cout`)
   - `data/sample_codes/cpp-core/lesson_02.cpp` (Khối gán dữ liệu, namespace `std`, lỗi biên dịch)
2. Đảm bảo toàn bộ mã nguồn được lưu bằng bảng mã **UTF-8 chuẩn** và Unicode NFC.

### Bước 2: Khởi Tạo Trình Phân Tích Cú Pháp Tree-sitter
1. Sử dụng thư viện `tree-sitter` kết hợp ngữ pháp ngôn ngữ C++:
   ```python
   import tree_sitter_cpp as tscpp
   from tree_sitter import Language, Parser

   CPP_LANGUAGE = Language(tscpp.language())
   parser = Parser(CPP_LANGUAGE)
   ```
2. Đọc file code dưới dạng bytes và tạo cây cú pháp:
   ```python
   tree = parser.parse(source_bytes)
   root_node = tree.root_node
   ```

### Bước 3: Trích Xuất Các Nút AST Theo Ranh Giới Ngữ Nghĩa
Duyệt các nút con cấp cao nhất (`root_node.children`) và phân loại:
* **Khối Tiền Xử Lý & Khai Báo Đầu Tệp (`preproc_include`, `using_directive`):**
  - Gom các dòng `#include <iostream>`, `using namespace std;` thành khối header cơ sở.
* **Khối Hàm (`function_definition`):**
  - Trích xuất trọn vẹn từ chữ ký hàm đến dấu ngoặc nhọn kết thúc `}` (ví dụ: toàn bộ thân hàm `int main() { ... }`).
* **Khối Khai Báo Biến / Hằng Toàn Cục (`declaration`):**
  - Trích xuất các biến `const double PI = 3.14;`, `const int SO_SO = 100;`.

### Bước 4: Đóng Gói Metadata Đoạn Mã (AST Payload Schema)
Mỗi chunk mã nguồn phải có cấu trúc Payload sau:
```python
{
    "course_id": "cpp-core",
    "lesson_id": "lesson-01",
    "lesson_seq": 1,
    "content_type": "code_ast",
    "code_scope": "main_function",        # hoặc "header_includes", "global_constants"
    "start_line": node.start_point[0] + 1,
    "end_line": node.end_point[0] + 1,
    "raw_text": source_code[node.start_byte:node.end_byte],
    "file_path": "data/sample_codes/cpp-core/lesson_01.cpp"
}
```

### Bước 5: Kiểm Thử & Nạp Điểm Lên Qdrant Cloud
1. Sinh vector kép qua `fastembed`:
   - Dense vector: thêm tiền tố `passage: ` vào đoạn code:
     `dense_vec = dense_model.embed([f"passage: {chunk['raw_text']}"])`
   - Sparse vector: sinh trực tiếp qua `sparse_model.embed([chunk['raw_text']])`.
2. Upsert vào Qdrant Cloud với ID tất định:
   `deterministic_key = f"{course_id}_{lesson_id}_ast_{start_line}_{end_line}"`
   `point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, deterministic_key))`

---

## 3. Các Quy Tắc Bất Biến Cần Tuân Thủ (Invariants)

1. **Tuyệt đối không dùng Regular Text Splitter (LangChain RecursiveCharacterTextSplitter):** Cắt theo số ký tự sẽ xé đôi vòng lặp, ngắt gãy lệnh `cout << "hello"`, làm mô hình LLM hiểu sai ngữ pháp.
2. **Bảo toàn ngữ cảnh Header:** Một hàm con nếu đứng độc lập cần được ghép kèm ngữ cảnh các thư viện phụ thuộc (`#include`) hoặc tên class cha để đảm bảo tính tự khép kín (Self-contained).
3. **Bộ lọc In-HNSW đồng bộ:** Mọi điểm code AST phải có trường `lesson_seq` chuẩn xác để khi học viên học bài 1, hệ thống không bao giờ truy xuất nhầm code giải của bài 2 (`lesson_seq <= 1`).

---

## 4. Xử Lý Sự Cố Thường Gặp (Troubleshooting)

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| :--- | :--- | :--- |
| Nút AST bị gán nhãn `ERROR` | Code C++ bị thiếu dấu `;` hoặc sai cú pháp | Kiểm tra `node.has_error`; nếu có lỗi, in dòng lỗi và vị trí cột để sửa code mẫu trước khi chunk. |
| Mất khối include trong chunk hàm | Cắt hàm rời rạc không kèm scope cha | Bổ sung hàm tiện ích gom các `preproc_include` vào phần preamble của mỗi chunk độc lập. |
| Chiều vector code không khớp | Quên dùng chung model E5 1024 chiều | Dùng chung `intfloat/multilingual-e5-large` đồng bộ với transcript video. |
