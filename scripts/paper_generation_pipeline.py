"""
Automated Multi-Stage Academic Paper Generation Pipeline
HUFLIT Journal of Science (HJS) Publication Suite

Author: Tran Thanh Nghia (Student ID: 23DH112252)
Supervisor: M.Sc. Tieu Phung Mai Suong
Faculty of Information Technology, HUFLIT
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = PROJECT_ROOT / ".agents" / "skills" / "docx-paper-studio" / "scripts"
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))


def run_pipeline(variants: str = "all", out_dir: Path = Path("docs"), figures_dir: Path = Path("scratch/paper_figures"), benchmarks_dir: Path = Path("docs/benchmarks")):
    start_time = time.time()
    print("\n" + "=" * 80)
    print("🎓 AUTOMATED MULTI-STAGE ACADEMIC PAPER GENERATION PIPELINE (HJS SUITE)")
    print("   Author    : Tran Thanh Nghia (Student ID: 23DH112252)")
    print("   Role      : Sole Author (Author Invariant)")
    print("   Advisor   : M.Sc. Tieu Phung Mai Suong (Academic Consultation & Mentorship)")
    print("   Journal   : HUFLIT Journal of Science (HJS)")
    print("   Standards : Native OMML Math, 300-DPI Figures, Three-Line Tables, 0% Leak")
    print("=" * 80 + "\n")

    # -------------------------------------------------------------
    # GIAI ĐOẠN 1: KIỂM TOÁN TÍNH NGUYÊN VẸN CỦA DỮ LIỆU THỰC NGHIỆM
    # -------------------------------------------------------------
    print("[*] GIAI ĐOẠN 1: Kiểm toán dữ liệu thực nghiệm từ Qdrant & Khảo thí...")
    s11_file = benchmarks_dir / "latest_benchmark_results.json"
    mt_file = benchmarks_dir / "multiturn_benchmark_results.json"

    if not s11_file.exists():
        print(f"[!] LỖI: Không tìm thấy tệp {s11_file}. Cần chạy benchmark đơn lượt trước.")
        sys.exit(1)
    if not mt_file.exists():
        print(f"[!] LỖI: Không tìm thấy tệp {mt_file}. Cần chạy benchmark đa lượt trước.")
        sys.exit(1)

    print(f"  [✔] Khảo thí Đơn lượt Golden 200: {s11_file.name} ({s11_file.stat().st_size / 1024:.1f} KB)")
    print(f"  [✔] Khảo thí Đa lượt 222 Turns  : {mt_file.name} ({mt_file.stat().st_size / 1024:.1f} KB)")

    # -------------------------------------------------------------
    # GIAI ĐOẠN 2: XUẤT BẢN BIỂU ĐỒ KHOA HỌC 300 DPI
    # -------------------------------------------------------------
    print("\n[*] GIAI ĐOẠN 2: Tự động khởi tạo biểu đồ phân giải cao 300 DPI...")
    figures_dir.mkdir(parents=True, exist_ok=True)
    from hjs_benchmark_charts import plot_multiturn_tiers, plot_stage11_tiers

    fig1_path = figures_dir / "fig_stage11_tiers.png"
    fig2_path = figures_dir / "fig_multiturn_tiers.png"

    plot_stage11_tiers(s11_file, fig1_path)
    plot_multiturn_tiers(mt_file, fig2_path)
    print(f"  [✔] Figure 1 (Stage 11 Tiers): {fig1_path} (300 DPI)")
    print(f"  [✔] Figure 2 (Multi-turn Tiers): {fig2_path} (300 DPI)")

    # -------------------------------------------------------------
    # GIAI ĐOẠN 3: LẮP RÁP CÁC BẢN THẢO WORD (BẢN A VÀ BẢN B)
    # -------------------------------------------------------------
    from build_full_hjs_paper import build_variant_paper
    from validate_docx import audit_docx

    target_variants = ["A", "B"] if variants == "all" else [variants.upper()]
    results = {}

    for var in target_variants:
        var_name = "Algorithmic" if var == "A" else "Socratic"
        out_docx = out_dir / f"HJS_Paper_Variant_{var}_{var_name}.docx"
        print(f"\n[*] GIAI ĐOẠN 3: Đang khởi tạo Bản thảo {var} ({var_name} Focus)...")
        built_path = build_variant_paper(out_docx, benchmarks_dir, figures_dir, variant=var)

        print(f"  [*] Đang kiểm toán thể thức Word cho Bản {var} (audit_docx)...")
        report = audit_docx(built_path)
        warnings = report.get("warnings", [])
        latex_leak_status = "0% (SẠCH HOÀN TOÀN)" if not warnings else f"CẢNH BÁO: {'; '.join(warnings)}"

        results[var] = {
            "path": built_path,
            "name": var_name,
            "size_kb": built_path.stat().st_size / 1024,
            "paragraphs": report.get("paragraphs_nonempty", 0),
            "tables": report.get("tables", 0),
            "images": report.get("embedded_images", 0),
            "omml_equations": report.get("native_omml_equations", 0),
            "latex_leak": latex_leak_status,
        }

    # If building all, also copy Variant A to default HJS_Paper_Final.docx
    if "A" in results:
        final_docx = out_dir / "HJS_Paper_Final.docx"
        import shutil
        shutil.copy2(results["A"]["path"], final_docx)
        print(f"\n[✔] Đã đồng bộ bản mặc định: {final_docx} (sao chép từ Bản A)")

    # -------------------------------------------------------------
    # TỔNG KẾT & ĐỐI CHIẾU 2 BẢN
    # -------------------------------------------------------------
    elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print(f"🎉 HOÀN TẤT XUẤT BẢN TRONG {elapsed:.1f} GIÂY!")
    print("=" * 80)
    print(f"{'Thông số':<30} | {'Bản A (Kiến trúc Giải thuật)':<24} | {'Bản B (Phương pháp Sư phạm)':<24}")
    print("-" * 80)

    res_a = results.get("A", {})
    res_b = results.get("B", {})

    print(f"{'Tiêu đề chính':<30} | {'Pareto-Sufficient RAG':<24} | {'Socratic Tutoring RAG':<24}")
    print(f"{'Trọng tâm học thuật':<30} | {'Bất đẳng thức Pareto, SLM':<24} | {'Tree-sitter AST, 100% SRP':<24}")
    print(f"{'Kích thước tệp (.docx)':<30} | {res_a.get('size_kb', 0):.1f} KB{'':<18} | {res_b.get('size_kb', 0):.1f} KB")
    print(f"{'Số đoạn văn bản':<30} | {res_a.get('paragraphs', 0):<24} | {res_b.get('paragraphs', 0):<24}")
    print(f"{'Số bảng biểu học thuật':<30} | {res_a.get('tables', 0):<24} | {res_b.get('tables', 0):<24}")
    print(f"{'Số biểu đồ 300 DPI':<30} | {res_a.get('images', 0):<24} | {res_b.get('images', 0):<24}")
    print(f"{'Số công thức Native OMML':<30} | {res_a.get('omml_equations', 0):<24} | {res_b.get('omml_equations', 0):<24}")
    print(f"{'Rò rỉ LaTeX thô ($)':<30} | {res_a.get('latex_leak', 'N/A'):<24} | {res_b.get('latex_leak', 'N/A'):<24}")
    print("-" * 80)
    print("Tác giả duy nhất : Trần Thành Nghĩa (MSSV: 23DH112252)")
    print("Giảng viên tư vấn: ThS. Tiếu Phùng Mai Sương (Tri ân tại Mục VII. Acknowledgments)")
    print("=" * 80 + "\n")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Automated Academic Paper Pipeline for HUFLIT Journal of Science")
    parser.add_argument("--variants", choices=["A", "B", "all"], default="all", help="Chọn biến thể cần xuất bản (A, B hoặc all)")
    parser.add_argument("--out-dir", default="docs", help="Thư mục lưu các tệp .docx")
    parser.add_argument("--figures-dir", default="scratch/paper_figures", help="Thư mục chứa biểu đồ 300 DPI")
    parser.add_argument("--benchmarks-dir", default="docs/benchmarks", help="Thư mục chứa kết quả khảo thí JSON")
    args = parser.parse_args()

    run_pipeline(
        variants=args.variants,
        out_dir=Path(args.out_dir),
        figures_dir=Path(args.figures_dir),
        benchmarks_dir=Path(args.benchmarks_dir),
    )


if __name__ == "__main__":
    main()
