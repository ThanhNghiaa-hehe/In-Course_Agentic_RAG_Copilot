"""
Telemetry Critic & Diagnostic Service cho Playground Sessions.
In-Course Agentic RAG Copilot - Tác giả: Trần Thành Nghĩa (MSSV: 23DH112252), HUFLIT.

Cung cấp:
1. Phân tích kiểm toán tự động từng lượt đối thoại (Turn-by-turn Diagnostic):
   - Ranh giới mã nguồn Socratic (chống lộ #include, int main, giải bài hộ).
   - Thẩm định mốc video <timestamp> (đối chiếu Whitelist bảo chứng).
   - Kiểm tra định tuyến ý định (Router) và truy xuất CRAG.
   - Đo lường độ trễ (TTFT) và tốc độ sinh token.
2. Xuất log tự động ra thư mục logs/playground_debug/ dưới dạng JSON & Markdown Report.
3. Trả về cấu trúc nhận xét đánh giá chi tiết để hiển thị tức thời trên Playground UI.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = PROJECT_ROOT / "logs" / "playground_debug"


def _ensure_logs_dir() -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return LOGS_DIR


class TelemetryCriticService:
    """
    Dịch vụ kiểm toán tự động & Phê bình chất lượng phiên đối thoại Socratic AI.
    """

    def analyze_turn(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Kiểm toán chi tiết 1 turn đối thoại."""
        turn_num = entry.get("turn", 1)
        prompt = entry.get("prompt", "")
        response_text = entry.get("response_text", "")
        latency = entry.get("latency", {})
        ttft_ms = latency.get("ttft_ms", 0)
        total_ms = latency.get("total_ms", 0)
        tokens_per_sec = latency.get("tokens_per_sec", 0.0)
        
        router = entry.get("router", {})
        intent = router.get("intent", "unknown")
        used_fast_path = router.get("used_fast_path", False)
        
        crag = entry.get("crag", {})
        retrieval_status = crag.get("retrieval_status", "unknown")
        target_lesson_seq = crag.get("target_lesson_seq")
        
        suggested_ts = entry.get("timestamps", [])
        sources = entry.get("sources", [])

        violations = []
        warnings = []
        merits = []

        # 1. Kiểm tra ranh giới mã nguồn Socratic (SOCRATIC CODE POLICY)
        has_include = bool(re.search(r'#\s*include\b', response_text))
        has_main = bool(re.search(r'\b(?:int|void)\s+main\s*\(', response_text))
        
        if has_include:
            violations.append("Vi phạm ranh giới mã nguồn: Xuất hiện chỉ thị khai báo thư viện `#include`.")
        if has_main:
            violations.append("Vi phạm nghiêm trọng ranh giới Socratic: Sinh toàn bộ hàm `main()`, giải bài tập thay vì định hướng tư duy.")
            
        # Kiểm tra độ dài khối code C++
        code_blocks = re.findall(r'```(?:cpp|c\+\+)?\s*([\s\S]*?)```', response_text)
        total_code_lines = 0
        for block in code_blocks:
            lines = [l for l in block.strip().split("\n") if l.strip()]
            total_code_lines += len(lines)
            
        if total_code_lines > 25:
            warnings.append(f"Khối mã nguồn minh họa khá dài ({total_code_lines} dòng). Nên ưu tiên dùng Mã giả (Pseudocode) hoặc đoạn code khuyết.")
        elif total_code_lines > 0 and not has_main and not has_include:
            merits.append("Minh họa cú pháp ngắn gọn, tuân thủ nguyên tắc không giải bài hộ.")

        # Kiểm tra câu hỏi gợi mở Socratic
        has_question = "?" in response_text
        if has_question:
            merits.append("Có đặt câu hỏi gợi mở định hướng tư duy (Socratic Questioning).")
        else:
            warnings.append("Thiếu câu hỏi gợi mở ở cuối câu trả lời để kích thích học viên tự suy luận.")

        # 2. Kiểm toán thẻ Timestamp Video
        ts_tags = re.findall(r'<timestamp\s+sec=["\'](\d+)["\'][^>]*>(.*?)</timestamp>', response_text)
        whitelist_secs = {t.get("sec") for t in suggested_ts if "sec" in t}
        
        unverified_ts = []
        for sec_str, label in ts_tags:
            sec_val = int(sec_str)
            if whitelist_secs and sec_val not in whitelist_secs:
                unverified_ts.append(f"{label} ({sec_val}s)")

        if unverified_ts:
            warnings.append(f"Mốc thời gian không nằm trong Whitelist nguồn xác thực: {', '.join(unverified_ts)}.")
        elif ts_tags:
            merits.append(f"Trích xuất thành công {len(ts_tags)} mốc video chuẩn xác từ nguồn bài giảng.")

        # 3. Đánh giá Router & CRAG
        if used_fast_path:
            merits.append(f"Kích hoạt Fast-Path thành công (< {total_ms}ms), tối ưu tài nguyên và độ trễ phản hồi.")
            
        # Tính điểm lượt này (0 - 100)
        score = 100
        if has_main:
            score -= 40
        if has_include:
            score -= 20
        if unverified_ts:
            score -= 15
        if not has_question and intent == "course_query":
            score -= 10
        if ttft_ms > 4000 and not used_fast_path:
            score -= 10
        score = max(0, min(100, score))

        # Tóm tắt nhận xét
        critique_parts = []
        if violations:
            critique_parts.append(f"❌ Cần sửa: {'; '.join(violations)}")
        if warnings:
            critique_parts.append(f"⚠️ Lưu ý: {'; '.join(warnings)}")
        if merits:
            critique_parts.append(f"✅ Ưu điểm: {'; '.join(merits)}")
        if not critique_parts:
            critique_parts.append("Phản hồi đạt chuẩn chất lượng bình thường.")

        return {
            "turn": turn_num,
            "prompt": prompt,
            "intent": intent,
            "retrieval_status": retrieval_status,
            "target_lesson_seq": target_lesson_seq,
            "used_fast_path": used_fast_path,
            "latency": {
                "ttft_ms": ttft_ms,
                "total_ms": total_ms,
                "tokens_per_sec": tokens_per_sec
            },
            "socratic_compliance": len(violations) == 0,
            "socratic_violations": violations,
            "warnings": warnings,
            "merits": merits,
            "turn_score": score,
            "critique_summary": " | ".join(critique_parts)
        }

    def analyze_session(
        self,
        session_id: str,
        course_id: str,
        lesson_seq: int,
        turns: List[Dict[str, Any]],
        client_timestamp: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Kiểm toán toàn diện toàn bộ phiên đối thoại (Session Holistic Critique).
        """
        turn_critiques = [self.analyze_turn(turn) for turn in turns]
        total_turns = len(turn_critiques)
        
        if total_turns == 0:
            return {
                "session_id": session_id,
                "course_id": course_id,
                "lesson_seq": lesson_seq,
                "total_turns": 0,
                "overall_health_score": 100,
                "rating_label": "CHƯA CÓ DỮ LIỆU (EMPTY SESSION)",
                "socratic_compliance_rate": 100.0,
                "avg_ttft_ms": 0,
                "fast_path_count": 0,
                "grounded_count": 0,
                "coverage_gap_count": 0,
                "turn_critiques": [],
                "critique_markdown": "# Báo cáo phiên rỗng: Chưa có lượt đối thoại nào.",
                "summary": "Chưa có lượt đối thoại nào được ghi nhận."
            }

        compliant_turns = sum(1 for tc in turn_critiques if tc["socratic_compliance"])
        compliance_rate = round((compliant_turns / total_turns) * 100, 1)
        
        avg_score = round(sum(tc["turn_score"] for tc in turn_critiques) / total_turns)
        avg_ttft = round(sum(tc["latency"]["ttft_ms"] for tc in turn_critiques) / total_turns)
        
        fast_path_count = sum(1 for tc in turn_critiques if tc["used_fast_path"])
        grounded_count = sum(1 for tc in turn_critiques if tc["retrieval_status"] == "grounded")
        coverage_gap_count = sum(1 for tc in turn_critiques if tc["retrieval_status"] == "coverage_gap")
        
        # Đánh giá tổng quát
        if avg_score >= 90:
            rating_label = "XUẤT SẮC (SOTA PRODUCTION QUALITY)"
            rating_badge = "🟢"
        elif avg_score >= 75:
            rating_label = "ĐẠT CHUẨN SƯ PHẠM (GOOD COMPLIANCE)"
            rating_badge = "🟡"
        else:
            rating_label = "CẦN TINH CHỈNH (NEEDS TUNING)"
            rating_badge = "🔴"

        # Sinh Markdown Report
        ts_now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        md_lines = [
            f"# Báo Cáo Kiểm Toán & Đánh Giá Phiên Đối Thoại Playground",
            f"> Hệ thống: In-Course Agentic RAG Copilot | Tác giả: Trần Thành Nghĩa (HUFLIT)",
            f"",
            f"- **Session ID:** `{session_id}`",
            f"- **Khóa học:** `{course_id}` | **Bài học hiện tại:** `Bài {lesson_seq}`",
            f"- **Thời điểm kiểm toán:** `{ts_now}`",
            f"- **Tổng số lượt (Turns):** `{total_turns}` lượt",
            f"",
            f"### Đánh Giá Tổng Thể: {rating_badge} {rating_label}",
            f"",
            f"| Chỉ số kiểm chuẩn | Kết quả thực nghiệm | Đánh giá kỹ thuật |",
            f"| :--- | :---: | :--- |",
            f"| **Điểm chất lượng phiên (Health Score)** | **{avg_score} / 100** | {'Tối ưu' if avg_score >= 85 else 'Có điểm cần cải thiện'} |",
            f"| **Tỷ lệ tuân thủ Socratic** | **{compliance_rate}%** | {f'{compliant_turns}/{total_turns} lượt đạt chuẩn không giải hộ' if compliance_rate >= 80 else 'Có lượt vi phạm sinh code hoàn chỉnh'} |",
            f"| **Độ trễ TTFT trung bình** | **{avg_ttft} ms** | {'Rất nhanh (Fast-path / Stream)' if avg_ttft < 1500 else 'Bình thường (LLM Inference)'} |",
            f"| **Tỷ lệ kích hoạt Fast-Path** | **{fast_path_count}/{total_turns}** | Giảm tải gọi GPU/LLM không cần thiết |",
            f"",
            f"---",
            f"## Chi Tiết Kiểm Toán Từng Lượt Đối Thoại (Turn-by-Turn Diagnostic)",
            f""
        ]

        for tc in turn_critiques:
            t_num = tc["turn"]
            p = tc["prompt"]
            intent = tc["intent"]
            r_status = tc["retrieval_status"]
            t_score = tc["turn_score"]
            lat = tc["latency"]
            s_check = "✅ Đạt chuẩn" if tc["socratic_compliance"] else "❌ Vi phạm"
            
            md_lines.append(f"### Lượt #{t_num}: \"{p}\"")
            md_lines.append(f"- **Điểm lượt:** `{t_score}/100` | **Tuân thủ Socratic:** {s_check}")
            md_lines.append(f"- **Ý định:** `{intent}` (Fast-Path: `{tc['used_fast_path']}`) | **CRAG:** `{r_status}`")
            md_lines.append(f"- **Độ trễ:** TTFT `{lat['ttft_ms']}ms` | Tổng `{lat['total_ms']}ms` ({lat['tokens_per_sec']} tok/s)")
            
            if tc["socratic_violations"]:
                for v in tc["socratic_violations"]:
                    md_lines.append(f"  - ❌ **Vi phạm ranh giới:** {v}")
            if tc["warnings"]:
                for w in tc["warnings"]:
                    md_lines.append(f"  - ⚠️ **Cảnh báo:** {w}")
            if tc["merits"]:
                for m in tc["merits"]:
                    md_lines.append(f"  - ✅ **Điểm cộng:** {m}")
            md_lines.append("")

        md_lines.append("---")
        md_lines.append("## Khuyến Nghị Kỹ Thuật & Tối Ưu Hóa Tiếp Theo")
        if compliance_rate < 100:
            md_lines.append("- **Socratic Guardrail:** Siết chặt hơn nữa quy tắc cấm hàm `main()` và `#include` trong System Prompt.")
        if avg_ttft > 3000:
            md_lines.append("- **Độ trễ:** Xem xét tinh chỉnh nhiệt độ mô hình hoặc tăng cường Fast-Path cho các câu hỏi phổ biến.")
        if fast_path_count > 0:
            md_lines.append("- **Fast-Path:** Tiếp tục duy trì và mở rộng chỉ mục ngữ nghĩa giáo trình (Syllabus Vector Index) để phân giải tức thời.")
        md_lines.append("- **Lưu trữ:** Tệp log JSON đầy đủ được lưu tại thư mục `logs/playground_debug/` phục vụ quy trình đánh giá RLHF / DPO.")

        critique_markdown = "\n".join(md_lines)

        return {
            "session_id": session_id,
            "course_id": course_id,
            "lesson_seq": lesson_seq,
            "total_turns": total_turns,
            "overall_health_score": avg_score,
            "rating_label": rating_label,
            "socratic_compliance_rate": compliance_rate,
            "avg_ttft_ms": avg_ttft,
            "fast_path_count": fast_path_count,
            "grounded_count": grounded_count,
            "coverage_gap_count": coverage_gap_count,
            "turn_critiques": turn_critiques,
            "critique_markdown": critique_markdown,
            "summary": f"Phiên {total_turns} lượt đạt {avg_score}/100 điểm ({rating_label}). Tuân thủ Socratic: {compliance_rate}%. TTFT trung bình: {avg_ttft}ms."
        }

    def export_and_critique_session(
        self,
        session_id: str,
        course_id: str,
        lesson_seq: int,
        turns: List[Dict[str, Any]],
        client_timestamp: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Xuất log tự động ra thư mục logs/playground_debug/ và sinh nhận xét đánh giá.
        """
        logs_dir = _ensure_logs_dir()
        timestamp_clean = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_sid = re.sub(r'[^a-zA-Z0-9_\-]', '', session_id) or "session"
        
        # 1. Chạy đánh giá kiểm toán
        analysis = self.analyze_session(
            session_id=session_id,
            course_id=course_id,
            lesson_seq=lesson_seq,
            turns=turns,
            client_timestamp=client_timestamp
        )

        # 2. Đóng gói payload JSON đầy đủ
        session_export_payload = {
            "metadata": {
                "session_id": session_id,
                "course_id": course_id,
                "lesson_seq": lesson_seq,
                "exported_at": datetime.now().isoformat(),
                "total_turns": len(turns),
                "health_score": analysis["overall_health_score"],
                "socratic_compliance_rate": analysis["socratic_compliance_rate"],
                "avg_ttft_ms": analysis["avg_ttft_ms"],
                "summary": analysis["summary"]
            },
            "critique": {
                "overall_health_score": analysis["overall_health_score"],
                "rating_label": analysis["rating_label"],
                "socratic_compliance_rate": analysis["socratic_compliance_rate"],
                "avg_ttft_ms": analysis["avg_ttft_ms"],
                "turn_critiques": analysis["turn_critiques"]
            },
            "turns": turns
        }

        # 3. Ghi ra tệp JSON
        json_filename = f"session_{safe_sid}_{timestamp_clean}.json"
        json_path = logs_dir / json_filename
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(session_export_payload, f, ensure_ascii=False, indent=2)

        # 4. Ghi ra tệp Markdown Critique
        md_filename = f"session_{safe_sid}_{timestamp_clean}_critique.md"
        md_path = logs_dir / md_filename
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(analysis["critique_markdown"])

        relative_json_path = f"logs/playground_debug/{json_filename}"
        relative_md_path = f"logs/playground_debug/{md_filename}"

        return {
            "status": "success",
            "message": f"Đã lưu log thành công vào {relative_json_path} và sinh nhận xét đánh giá tại {relative_md_path}!",
            "file_path": str(json_path.resolve()),
            "relative_path": relative_json_path,
            "critique_file_path": str(md_path.resolve()),
            "relative_critique_path": relative_md_path,
            "session_id": session_id,
            "total_turns": len(turns),
            "overall_health_score": analysis["overall_health_score"],
            "rating_label": analysis["rating_label"],
            "socratic_compliance_rate": analysis["socratic_compliance_rate"],
            "avg_ttft_ms": analysis["avg_ttft_ms"],
            "summary": analysis["summary"],
            "critique_markdown": analysis["critique_markdown"],
            "turn_critiques": analysis["turn_critiques"]
        }


# Singleton instance
_telemetry_critic_service: Optional[TelemetryCriticService] = None

def get_telemetry_critic_service() -> TelemetryCriticService:
    global _telemetry_critic_service
    if _telemetry_critic_service is None:
        _telemetry_critic_service = TelemetryCriticService()
    return _telemetry_critic_service

