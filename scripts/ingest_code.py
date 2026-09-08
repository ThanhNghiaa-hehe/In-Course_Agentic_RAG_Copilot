import os
import sys
import json
import uuid
import argparse
import unicodedata
from pathlib import Path
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import tree_sitter
import tree_sitter_cpp as tscpp
from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.config import settings

def normalize_text(text: str) -> str:
    """Chuẩn hóa chuỗi văn bản sang định dạng Unicode NFC chuẩn."""
    if not text:
        return ""
    return unicodedata.normalize("NFC", text.strip())

class CppASTChunker:
    """
    Trình bóc tách cú pháp mã nguồn C++ sử dụng Tree-sitter.
    Tuân thủ quy tắc kiến trúc: Không cắt ký tự thô, bảo toàn ranh giới hàm/lớp/khối khai báo.
    """
    def __init__(self):
        self.language = tree_sitter.Language(tscpp.language())
        self.parser = tree_sitter.Parser(self.language)

    def extract_function_name(self, func_node, source_bytes: bytes) -> str:
        """Trích xuất tên hàm từ nút function_definition."""
        for child in func_node.children:
            if child.type == "function_declarator":
                for sub in child.children:
                    if sub.type == "identifier":
                        return source_bytes[sub.start_byte:sub.end_byte].decode("utf-8")
        return "anonymous"

    def chunk_file(self, file_path: Path, course_id: str, lesson_id: str, lesson_seq: int):
        """Phân tích file C++ và trả về danh sách các chunks ngữ nghĩa có cấu trúc."""
        with open(file_path, "rb") as f:
            source_bytes = f.read()

        source_code = source_bytes.decode("utf-8")
        lines = source_code.splitlines()
        tree = self.parser.parse(source_bytes)
        root = tree.root_node

        chunks = []
        header_lines = []
        header_nodes = []

        # 1. Thu thập các khai báo phần đầu (Header Preamble): includes, using, comments
        for child in root.children:
            if child.type in ["preproc_include", "using_declaration", "preproc_def"]:
                header_nodes.append(child)
                start_l = child.start_point.row
                end_l = child.end_point.row
                header_lines.extend(lines[start_l:end_l + 1])

        header_text = "\n".join(header_lines).strip()

        # Nếu có phần header, tạo một chunk riêng cho Header Preamble
        if header_nodes:
            first_h = header_nodes[0]
            last_h = header_nodes[-1]
            start_l = first_h.start_point.row + 1
            end_l = last_h.end_point.row + 1

            chunk_id = f"header_{start_l}_{end_l}"
            chunks.append({
                "chunk_id": chunk_id,
                "code_scope": "header_preamble",
                "start_line": start_l,
                "end_line": end_l,
                "raw_text": header_text,
                "context_code": header_text
            })

        # 2. Thu thập các hàm (Functions), Lớp (Classes), Cấu trúc (Structs)
        for child in root.children:
            c_type = child.type
            start_l = child.start_point.row + 1
            end_l = child.end_point.row + 1
            node_text = "\n".join(lines[child.start_point.row:child.end_point.row + 1]).strip()

            if c_type == "function_definition":
                func_name = self.extract_function_name(child, source_bytes)
                code_scope = f"function_{func_name}"
                chunk_id = f"func_{func_name}_{start_l}_{end_l}"

                # Tự khép kín (Self-contained): Ghép kèm header để LLM và Embedding nắm đủ ngữ cảnh
                if header_text and not node_text.startswith("#include"):
                    enriched_text = f"// [Header Context]\n{header_text}\n\n// [Function Implementation]\n{node_text}"
                else:
                    enriched_text = node_text

                chunks.append({
                    "chunk_id": chunk_id,
                    "code_scope": code_scope,
                    "func_name": func_name,
                    "start_line": start_l,
                    "end_line": end_l,
                    "raw_text": node_text,
                    "context_code": enriched_text
                })

            elif c_type in ["class_specifier", "struct_specifier"]:
                code_scope = f"type_{c_type}"
                chunk_id = f"{c_type}_{start_l}_{end_l}"
                chunks.append({
                    "chunk_id": chunk_id,
                    "code_scope": code_scope,
                    "start_line": start_l,
                    "end_line": end_l,
                    "raw_text": node_text,
                    "context_code": node_text
                })

        # Nếu tệp ngắn không có hàm rõ rệt, bọc toàn bộ file làm 1 chunk
        if not chunks:
            chunks.append({
                "chunk_id": "full_file_1",
                "code_scope": "full_script",
                "start_line": 1,
                "end_line": len(lines),
                "raw_text": source_code.strip(),
                "context_code": source_code.strip()
            })

        return chunks

def ingest_single_file(file_path: Path, course_id: str, lesson_id: str, lesson_seq: int, clean_old: bool = True):
    print("=" * 72)
    print(f">> DANG XU LY MA NGUON AST: {file_path.name}")
    print(f" - Khoa hoc: {course_id} | Bai hoc: {lesson_id} (Seq: {lesson_seq})")
    print("=" * 72)

    chunker = CppASTChunker()
    chunks = chunker.chunk_file(file_path, course_id, lesson_id, lesson_seq)
    print(f"[STAGE 3] Tree-sitter da trich xuat thanh cong {len(chunks)} chunks cu phap.")

    for i, c in enumerate(chunks, 1):
        print(f"   + Chunk {i}: Scope='{c['code_scope']}', Dong [{c['start_line']} -> {c['end_line']}]")

    # Lưu bản JSON mô tả chunks cục bộ để kiểm tra
    json_path = file_path.parent / f"{file_path.stem}_ast_chunks.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    print(f"v Da luu danh sach AST chunks tai: {json_path}")

    # [STAGE 4 & 5] Sinh Vector kép & Nạp lên Qdrant Cloud
    print("\n[STAGE 4 & 5] Sinh Vector kep (Dense E5 + Sparse BM25) & Indexing Qdrant...")
    dense_model = TextEmbedding("intfloat/multilingual-e5-large")
    sparse_model = SparseTextEmbedding("Qdrant/bm25")

    # BẮT BUỘC: Thêm tiền tố 'passage: ' cho mô hình multilingual-e5-large
    dense_inputs = [f"passage: {c['context_code']}" for c in chunks]
    sparse_inputs = [c['context_code'] for c in chunks]

    dense_embeddings = list(dense_model.embed(dense_inputs))
    sparse_embeddings = list(sparse_model.embed(sparse_inputs))

    qdrant = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=60.0)

    if clean_old:
        print(f"Dọn dẹp code cũ của bài '{lesson_id}' trên Qdrant Cloud...")
        try:
            qdrant.delete(
                collection_name=settings.QDRANT_COLLECTION_NAME,
                points_selector=models.Filter(
                    must=[
                        models.FieldCondition(key="course_id", match=models.MatchValue(value=course_id)),
                        models.FieldCondition(key="lesson_id", match=models.MatchValue(value=lesson_id)),
                        models.FieldCondition(key="content_type", match=models.MatchValue(value="code_ast"))
                    ]
                )
            )
        except Exception as e:
            pass

    points = []
    for i, c in enumerate(chunks):
        sparse_val = sparse_embeddings[i]
        # Định danh tất định UUIDv5 chống trùng lặp điểm
        deterministic_key = f"{course_id}_{lesson_id}_ast_{c['chunk_id']}"
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, deterministic_key))

        point = models.PointStruct(
            id=point_id,
            vector={
                "dense": dense_embeddings[i].tolist(),
                "sparse": models.SparseVector(
                    indices=sparse_val.indices.tolist(),
                    values=sparse_val.values.tolist()
                )
            },
            payload={
                "course_id": course_id,
                "lesson_id": lesson_id,
                "lesson_seq": lesson_seq,
                "content_type": "code_ast",
                "code_scope": c["code_scope"],
                "start_line": c["start_line"],
                "end_line": c["end_line"],
                "raw_text": c["raw_text"],
                "context_code": c["context_code"],
                "file_path": str(file_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "code_language": "cpp"
            }
        )
        points.append(point)

    with tqdm(total=len(points), desc=">> Nap AST Points len Qdrant Cloud", unit="pt") as pbar:
        qdrant.upsert(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            points=points
        )
        pbar.update(len(points))

    print(f"v HOAN TAT NAP {len(points)} AST CODE CHUNKS CUA '{file_path.name}' VAO QDRANT CLOUD!\n")

def main():
    parser = argparse.ArgumentParser(description="Pipeline bóc tách cú pháp AST mã nguồn C++ và nạp lên Qdrant Cloud.")
    parser.add_argument("path", nargs="?", default=None, help="Đường dẫn đến file .cpp hoặc thư mục chứa file code")
    parser.add_argument("--course", default="cpp-core", help="Mã khóa học (mặc định: cpp-core)")
    parser.add_argument("--lesson", default=None, help="Mã bài học (ví dụ: lesson-01)")
    parser.add_argument("--seq", type=int, default=None, help="Thứ tự bài học lũy kế (ví dụ: 1, 2)")
    parser.add_argument("--all", action="store_true", help="Nạp toàn bộ mã nguồn mẫu trong data/sample_codes/cpp-core/")

    args = parser.parse_args()

    if args.all or (args.path and Path(args.path).is_dir()):
        target_dir = Path(args.path) if args.path else PROJECT_ROOT / "data" / "sample_codes" / "cpp-core"
        cpp_files = sorted(list(target_dir.glob("*.cpp")))
        if not cpp_files:
            print(f"Không tìm thấy file .cpp nào trong thư mục: {target_dir}")
            return

        print(f"Tim thay {len(cpp_files)} file C++ trong {target_dir}. Bat dau nap hang loat...")
        for cpp_file in cpp_files:
            # Tự động suy luận lesson_id và lesson_seq từ tên file: lesson_01.cpp -> lesson-01, seq 1
            stem = cpp_file.stem
            parts = stem.split("_")
            if len(parts) >= 2 and parts[0] == "lesson":
                seq_num = int(parts[1])
                l_id = f"lesson-{seq_num:02d}"
            else:
                seq_num = 1
                l_id = "lesson-01"

            ingest_single_file(cpp_file, args.course, l_id, seq_num)
    else:
        if not args.path:
            print("Vui long cung cap duong dan file .cpp hoac dung flag --all")
            return
        target_file = Path(args.path)
        if not target_file.exists():
            print(f"File khong ton tai: {target_file}")
            return
        
        lesson_id = args.lesson or "lesson-01"
        lesson_seq = args.seq or 1
        ingest_single_file(target_file, args.course, lesson_id, lesson_seq)

if __name__ == "__main__":
    main()
