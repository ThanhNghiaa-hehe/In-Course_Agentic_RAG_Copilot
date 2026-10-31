"""
Script Kiểm Toán Dữ Liệu Âm Học Toàn Diện 83 Bài Học (Corpus Health Auditor)
In-Course Agentic RAG Copilot - Tác giả: Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Tính năng:
- Tự động nạp danh mục 83 bài học từ data/curriculum/lessons_manifest.json.
- Quét toàn bộ các tệp transcript raw_segments.json và chunks.json trên ổ đĩa.
- Bóc tách toàn diện các lỗi phiên âm âm học Whisper (Phonetic Acoustic Anomalies):
  + Cấu trúc điều khiển & vòng lặp: vòng lập 4, vòng fo, vòng foe, vòng là con, vòng lặp qua, do y,...
  + Kiểu dữ liệu nguyên thủy: flow đáp bồ, phút lót, trè/che (char), bu lơ (bool), sờ chinh (string),...
  + Cú pháp & Thư viện: thăng in, ios chìm, can chua, hàm men, hai dầu trầm 7,...
  + Ảo giác tiếng Anh ngẫu nhiên khi im lặng (Whisper Hallucinations).
- Xuất báo cáo Markdown chi tiết tại docs/benchmarks/corpus_phonetic_health_report.md.
"""

import sys
import json
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PROJECT_ROOT / "data" / "curriculum" / "lessons_manifest.json"
TRANSCRIPTS_ROOT = PROJECT_ROOT / "data" / "transcripts"
REPORT_PATH = PROJECT_ROOT / "docs" / "benchmarks" / "corpus_phonetic_health_report.md"

# Danh mục các mẫu lỗi âm học cần kiểm toán
AUDIT_PATTERNS = {
    # 1. Cấu trúc điều khiển & Vòng lặp
    "Vòng lặp For": [
        r'\bvòng\s+(?:lập|lặp)\s+(?:4|bốn)\b',
        r'\bvòng\s+(?:là\s+)?(?:fo|foe)\b',
        r'\bvòng\s+là\s+con\b',
    ],
    "Vòng lặp While / Do-While": [
        r'\bvòng\s+(?:lập|lặp)\s+(?:qua|quai|wai)\b',
        r'\bvòng\s+(?:lập|lặp)\s+do\s*(?:y|wai|quai)\b',
    ],
    "Dấu phân cách cú pháp": [
        r'\b(?:hai\s+)?(?:dầu|dấu)\s+(?:trầm|chấm)\s+7\b',
    ],
    # 2. Kiểu dữ liệu & I/O
    "Kiểu số thực (float/double)": [
        r'\b(flow\s+(đáp|đắp|đúp)\s*bồ|phờ\s*lốt\s*(và\s*)?(đáp|đắp|đúp)\s*bồ)\b',
        r'\b(flow|full\s*load|phút\s*lót|phút\s*load|phờ\s*lốt)\b',
        r'\b(thẳng|thằng)?\s*(đáp|đắp|đúp)\s*bồ\b',
    ],
    "Kiểu ký tự (char) & Boolean": [
        r'\b(trè|che)\b',
        r'\b(bu\s*lơ|bu\s*lê|bu\s*lin|bu\s*lơn)\b',
    ],
    "Nhập xuất cin / cout / endl": [
        r'\b(xì\s*in|si\s*in|xê\s*in)\b',
        r'\b(xì\s*out|si\s*out|xê\s*out|xi\s*out)\b',
        r'\b(en\s*lai|en\s*đơ\s*lai)\b',
    ],
    "Xâu ký tự (string / stringstream)": [
        r'\b(sờ\s*chinh|sờ\s*tring|sờ\s*trinh)\b',
        r'\b(sờ\s*tring\s*sờ\s*trim|xì\s*tring\s*xì\s*trim)\b',
    ],
    # 3. Cú pháp & Môi trường IDE
    "Cú pháp Include & Thư viện": [
        r'\b(thăng\s*inqlude|thăng\s*in\s*cờ\s*lút|thang\s*in|hãn\s*thang\s*in)\b',
        r'\b(ios\s*chìm|ai\s*âu\s*sờ\s*trim)\b',
    ],
    "Phím tắt & Hàm Main": [
        r'\b(can\s*chua|can\s*chô|can\s*trô|con\s*chó)\b',
        r'\b(ham\s*men|hàm\s*men)\b',
    ],
    # 4. Ảo giác tiếng Anh vô nghĩa
    "Ảo giác âm học im lặng": [
        r'Inaja ra kế hoạchApp Injury bath',
        r'The Nippin Flock Vishal Perfure Solean Img',
        r'App Injury bath The Nippin Flock',
    ]
}


def scan_text(text: str) -> List[Dict[str, str]]:
    """Quét văn bản và trả về danh sách các lỗi phát hiện được."""
    findings = []
    for cat_name, patterns in AUDIT_PATTERNS.items():
        for pat in patterns:
            matches = re.finditer(pat, text, re.IGNORECASE)
            for m in matches:
                findings.append({
                    "category": cat_name,
                    "matched_text": m.group(0),
                    "pattern": pat
                })
    return findings


def run_audit():
    print("=" * 72)
    print(" BẮT ĐẦU KIỂM TOÁN ÂM HỌC TOÀN BỘ GIÁO TRÌNH (CORPUS HEALTH AUDITOR)")
    print("=" * 72)

    if not MANIFEST_PATH.exists():
        print(f"[LỖI] Không tìm thấy file manifest tại {MANIFEST_PATH}")
        return

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)

    courses = manifest_data.get("courses", {})
    all_lessons = []
    for c_id, c_data in courses.items():
        for l in c_data.get("lessons", []):
            all_lessons.append({
                "course_id": c_id,
                "course_name": c_data.get("course_name", c_id),
                "seq": l.get("seq"),
                "title": l.get("title", ""),
                "keywords": l.get("keywords", [])
            })

    print(f"Tổng số bài học trong giáo trình: {len(all_lessons)}")

    # Quét từng thư mục bài học trong data/transcripts
    audit_results = []
    total_anomalies = 0

    for l_info in all_lessons:
        seq = l_info["seq"]
        c_id = l_info["course_id"]
        title = l_info["title"]

        # Tìm thư mục tương ứng
        lesson_dirs = list(TRANSCRIPTS_ROOT.glob(f"**/*lesson-{seq:02d}*"))
        if not lesson_dirs:
            lesson_dirs = list(TRANSCRIPTS_ROOT.glob(f"**/*lesson_{seq:02d}*"))
        if not lesson_dirs and seq == 1:
            lesson_dirs = list(TRANSCRIPTS_ROOT.glob("**/lesson-01*"))

        if not lesson_dirs:
            audit_results.append({
                "seq": seq,
                "course_id": c_id,
                "title": title,
                "status": "MISSING_FOLDER",
                "total_segments": 0,
                "anomalies_count": 0,
                "findings": []
            })
            continue

        l_dir = lesson_dirs[0]
        # Tìm file raw_segments hoặc chunks
        raw_file = l_dir / f"lesson-{seq:02d}_raw_segments.json"
        chunk_file = l_dir / f"lesson-{seq:02d}_chunks.json"

        target_file = raw_file if raw_file.exists() else (chunk_file if chunk_file.exists() else None)
        if not target_file:
            # Tìm file json bất kỳ
            json_files = list(l_dir.glob("*.json"))
            if json_files:
                target_file = json_files[0]

        if not target_file or not target_file.exists():
            audit_results.append({
                "seq": seq,
                "course_id": c_id,
                "title": title,
                "status": "NO_JSON_DATA",
                "total_segments": 0,
                "anomalies_count": 0,
                "findings": []
            })
            continue

        with open(target_file, "r", encoding="utf-8") as tf:
            try:
                data = json.load(tf)
            except Exception:
                data = []

        lesson_findings = []
        for item in data:
            t = item.get("text") or item.get("raw_text") or ""
            start_s = item.get("start") or item.get("start_sec") or 0
            res = scan_text(t)
            for r in res:
                r["start_sec"] = int(start_s)
                r["label"] = f"{int(start_s)//60:02d}:{int(start_s)%60:02d}"
                lesson_findings.append(r)

        anom_count = len(lesson_findings)
        total_anomalies += anom_count
        status = "CLEAN" if anom_count == 0 else ("MINOR_NOISE" if anom_count <= 3 else "HIGH_NOISE")

        audit_results.append({
            "seq": seq,
            "course_id": c_id,
            "title": title,
            "status": status,
            "total_segments": len(data),
            "anomalies_count": anom_count,
            "findings": lesson_findings
        })

    # Tổng kết và tạo Báo cáo Markdown
    clean_count = sum(1 for r in audit_results if r["status"] == "CLEAN")
    minor_count = sum(1 for r in audit_results if r["status"] == "MINOR_NOISE")
    high_count = sum(1 for r in audit_results if r["status"] == "HIGH_NOISE")

    print("\n" + "=" * 72)
    print(" KẾT QUẢ KIỂM TOÁN DỮ LIỆU:")
    print(f" - Tổng bài học đã quét: {len(audit_results)}")
    print(f" - Bài học Sạch hoàn toàn (CLEAN): {clean_count}")
    print(f" - Bài học Nhiễu nhẹ (MINOR_NOISE 1-3 lỗi): {minor_count}")
    print(f" - Bài học Nhiễu đáng kể (HIGH_NOISE > 3 lỗi): {high_count}")
    print(f" - Tổng số lỗi âm học phát hiện: {total_anomalies}")
    print("=" * 72)

    # Viết báo cáo Markdown
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as rf:
        rf.write("# Báo Cáo Kiểm Toán Sức Khỏe Âm Học Dữ Liệu Toàn Diện 83 Bài Học\n\n")
        rf.write("**Tác giả:** Trần Thành Nghĩa (MSSV: `23DH112252`), HUFLIT  \n")
        rf.write("**Phương pháp:** Static Corpus Pattern Auditing (Data-Centric AI)  \n")
        rf.write(f"**Ngày thực hiện:** 31/10/2026  \n\n")

        rf.write("## 1. Tổng Quan Sức Khỏe Giáo Trình (Corpus Health Summary)\n\n")
        rf.write("| Chỉ số | Số lượng | Tỷ lệ |\n")
        rf.write("| :--- | :--- | :--- |\n")
        rf.write(f"| **Tổng bài học** | {len(audit_results)} | 100.0% |\n")
        rf.write(f"| **Bài học Chuẩn Sạch (CLEAN)** | {clean_count} | {clean_count/len(audit_results)*100:.1f}% |\n")
        rf.write(f"| **Bài học Nhiễu Nhẹ (MINOR 1-3)** | {minor_count} | {minor_count/len(audit_results)*100:.1f}% |\n")
        rf.write(f"| **Bài học Cần Chuẩn Hóa (HIGH > 3)** | {high_count} | {high_count/len(audit_results)*100:.1f}% |\n")
        rf.write(f"| **Tổng số dị thường âm học** | **{total_anomalies}** | - |\n\n")

        rf.write("## 2. Chi Tiết Các Bài Học Cần Chuẩn Hóa (Action List)\n\n")
        rf.write("| Seq | Khóa | Tiêu đề Bài học | Trạng thái | Lỗi phát hiện | Chi tiết mẫu lỗi âm học |\n")
        rf.write("| :---: | :---: | :--- | :---: | :---: | :--- |\n")

        for r in audit_results:
            if r["anomalies_count"] > 0:
                # Gom nhóm mẫu lỗi
                summary_sample = []
                for f in r["findings"][:5]:
                    summary_sample.append(f"`{f['matched_text']}` @ {f['label']}")
                sample_str = ", ".join(summary_sample)
                if len(r["findings"]) > 5:
                    sample_str += f", ... (+{len(r['findings'])-5} lỗi khác)"

                rf.write(f"| **Bài {r['seq']}** | `{r['course_id']}` | {r['title']} | **{r['status']}** | **{r['anomalies_count']}** | {sample_str} |\n")

        rf.write("\n## 3. Danh Sách Bài Học Đã Chuẩn Sạch Hoàn Toàn (CLEAN)\n\n")
        clean_lessons = [f"Bài {r['seq']}" for r in audit_results if r["status"] == "CLEAN"]
        rf.write(", ".join(clean_lessons) + "\n")

    print(f"✓ Đã xuất bản báo cáo kiểm toán thành công tại: {REPORT_PATH}")


if __name__ == "__main__":
    run_audit()
