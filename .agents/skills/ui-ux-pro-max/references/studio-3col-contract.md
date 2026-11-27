# In-Course 3-Column Studio & Video Sync UX Contract

Tài liệu trích xuất từ `AGENTS.md` (§2) theo cơ chế Progressive Disclosure cho kỹ năng `ui-ux-pro-max` khi thiết kế hoặc chỉnh sửa Playground/Studio (`app/templates/playground.html`, React `fe-codelearning`).

---

## 1. Bố Cục 3 Cột Studio Học Tập (3-Column Canvas Standard)
Mọi giao diện học tập tương tác (Playground/Studio) bắt buộc giữ đúng 3 cột:
1. **Cột 1 (Trái — `340px`):** Khung Giáo trình & Thẩm định (*Syllabus Panel*) — hiển thị **đầy đủ 83 bài học** (không dùng mock đại diện), kèm bộ lọc tìm kiếm tức thời và **AST Code Inspector** (click-to-seek mốc video gắn với định nghĩa code).
2. **Cột 2 (Giữa — `flex: 1; height: 100%; overflow: hidden;`):** Khung Video Toàn Phần (*Focal Video Canvas*) — tích hợp YouTube IFrame API đồng bộ playlist thời gian thực. **Cấm chèn thẻ mock/placeholder chapter làm co hẹp màn hình video.**
3. **Cột 3 (Phải — `390px`):** Khung Trợ Giảng Socratic AI (*Assistance Panel*) — Thought Drawer minh bạch quyết định CRAG Grader, nút mốc thời gian click-to-seek `<timestamp sec="xxx">mm:ss</timestamp>`, và phản hồi định hướng tư duy Socratic.

## 2. Visual Hierarchy Cho Studio Học Tập (EdTech Light Theme Exception)
> Lưu ý: Bảng màu Slate/Zinc tối ở `SKILL.md` áp dụng cho *Observability Dashboard* (`evaluation_dashboard.html`), còn giao diện học tập tương tác **Playground / Study Studio** áp dụng chuẩn **EdTech SaaS Light Theme**:
- **Nền chính:** `#f8fafc` | **Card:** `#ffffff` | **Viền mảnh:** `#e2e8f0` | **Typography:** Slate `#0f172a` | **Điểm nhấn:** Indigo `#4f46e5`.
- **100% icon SVG Lucide** sắc nét (`0%` emoji icon); bo góc `8px - 12px`, bóng đổ nhẹ tự nhiên.

## 3. Video Synchronization UX & Cross-Lesson Alignment (Phương Án A)
- **Zero Auto-Seek:** Tuyệt đối **CẤM** tự động tua video (`auto_seek_sec`) khi học viên chưa đồng ý; 100% hành vi seek phải đến từ cú nhấp chuột chủ động của học viên.
- **Cross-Lesson Sync:** Khi học viên đang ở bài $K$ nhưng truy vấn kiến thức bài cũ $J < K$, thẻ `<timestamp>` bắt buộc mang định danh bài học `lesson_seq`. Khi click seek, frontend phải chuyển playlist (`ytPlayer.playVideoAt(lesson_J.pIndex)`) rồi mới gọi `player.seekTo(sec)`.
- **Grounding Source Citations:** Hiển thị thẻ timestamp gọn ở cuối phản hồi (mô tả ngữ cảnh ngắn gọn nếu có) để không làm đứt mạch đọc mã nguồn và câu hỏi Socratic.
