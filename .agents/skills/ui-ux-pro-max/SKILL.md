---
name: ui-ux-pro-max
description: Chuyên gia thiết kế UI/UX cấp cao, triệt tiêu hoàn toàn lỗi AI Slop, chuẩn hóa giao diện Enterprise Observability, bảng màu Slate/Zinc công nghiệp, icon SVG Lucide và micro-interactions tinh tế.
---

# UI/UX Pro Max - Tiêu Chuẩn Thiết Kế Giao Diện Đẳng Cấp

## 1. Nguyên Tắc Cốt Lõi: Triệt Tiêu "AI Slop" (Anti-Patterns)
- 🚫 **TUYỆT ĐỐI KHÔNG dùng Emoji làm Icon:** Không dùng các emoji nhí nhố (🌐, ⚡, 🔄, 🛡️, 🚀, 📌, 📥, 📤) trên các nút bấm, tiêu đề thẻ hay nhãn trạng thái. Bắt buộc dùng 100% SVG Icons chuẩn công nghiệp (Lucide / Heroicons / Feather).
- 🚫 **TUYỆT ĐỐI KHÔNG dùng Gradient tím/hồng viễn tưởng:** Tránh xa các phong cách gradient AI rập khuôn khiến giao diện trông như sản phẩm đồ chơi công nghệ.
- 🚫 **KHÔNG dùng màu Neon chói lóa:** Bỏ hiệu ứng `box-shadow` phát sáng giật mắt kiểu hoạt hình (`pulseGlow`). Thay bằng viền mỏng 1px sắc nét (`border: 1px solid rgba(255, 255, 255, 0.08)` hoặc `border: 1px solid rgba(59, 130, 246, 0.3)`).
- 🚫 **KHÔNG để layout ngột ngạt:** Luôn giữ tỷ lệ khoảng thở (Whitespace) chuẩn nhịp điệu 8px / 12px / 16px / 24px.

## 2. Hệ Màu Sắc Chuẩn Enterprise Observability (Datadog / LangSmith / Vercel)
- **Nền chính (Background):** Slate tối thượng (`#0b0f19`, `#0f172a`) hoặc Zinc (`#09090b`, `#18181b`).
- **Bề mặt Card (Surface):** `#111827` hoặc `#1e293b` với viền `1px solid rgba(255, 255, 255, 0.08)`.
- **Màu Kỹ thuật (Functional Palette):**
  - **Success / Pass:** Emerald Green (`#10b981`, `#059669`).
  - **Warning / Fallback:** Amber (`#f59e0b`, `#d97706`).
  - **Error / Alert / Hallucination:** Crimson Red (`#ef4444`, `#dc2626`).
  - **Primary Action:** Deep Technical Blue / Indigo (`#2563eb`, `#3b82f6`).
  - **Muted Text:** Slate 400 (`#94a3b8`) với độ tương phản WCAG AAA $\ge 4.5:1$.

## 3. Kiểu Chữ (Typography & Contrast)
- **Font UI chính:** `Inter`, `Plus Jakarta Sans` hoặc system-ui `-apple-system, BlinkMacSystemFont`.
- **Font Code & Telemetry Metrics:** `JetBrains Mono` hoặc `Fira Code`.
- **Phân cấp thị giác:**
  - Tiêu đề màn hình: 16px - 18px (Font weight: 700).
  - Tên Card/Stage: 13px - 14px (Font weight: 600).
  - Nhãn kỹ thuật/Metadata: 11px - 12px (Font weight: 500, Monospace).
  - Caption/Footer: 10px - 11px (Muted color).

## 4. Quy Chuẩn Kỹ Thuật Chống AI Slop (Kế Thừa từ ibelick/ui-skills)
- **Baseline Deslop Protocol:**
  - Font Monospace: Bắt buộc dùng `JetBrains Mono` cho toàn bộ telemetry, code snippet, latency ms và các định danh kỹ thuật.
  - Heading & Copy: Sử dụng `tracking-tight` cho tiêu đề và `sentence case` cho toàn bộ nhãn / nút bấm (ví dụ: `Gửi truy vấn`, không viết hoa vô tội vạ `GỬI TRUY VẤN`).
  - Neutral / Parchment Hierarchy: Giữ bảng màu nền trung tính, sạch sẽ; chỉ làm nổi bật bề mặt tương tác bằng viền 1px tinh tế và độ tương phản cao, loại bỏ hoàn toàn các mảng gradient bóng bẩy vô nghĩa.
  - Semantic Accessibility: Mọi icon-only button đều bắt buộc có thuộc tính `aria-label` và trạng thái `:focus-visible` rõ ràng.

## 5. Quy Chuẩn Hiệu Năng Chuyển Động (Motion Performance 60fps)
- **Compositor-Only Motion:** 100% hiệu ứng chuyển động và micro-interactions chỉ được phép can thiệp vào tầng Compositor của GPU (`transform` và `opacity`).
- 🚫 **CẤM TUYỆT ĐỐI Layout Thrashing:** Không bao giờ animate các thuộc tính kích thước hoặc vị trí (`width`, `height`, `top`, `left`, `margin`, `padding`) hoặc các bộ lọc nặng (`blur`, `box-shadow`) lặp đi lặp lại trong vòng lặp animation frame vì sẽ gây sụt FPS nghiêm trọng trên CPU.
- **Micro-Interactions Easing:**
  - Sử dụng timing curve cao cấp: `cubic-bezier(0.16, 1, 0.3, 1)` cho hover/active states.
  - Phản hồi xúc giác thị giác (Tactile Feedback): Các nút bấm và card khi click phải có hiệu ứng nén nhẹ `transform: scale(0.98)` tức thì (`transition: transform 0.1s`).
  - Hardware Acceleration: Khai báo `will-change: transform` trên các phần tử di chuyển liên tục (như gói tin dữ liệu hay tia xung nhịp).

## 6. Danh Sách Kiểm Tra Trước Khi Bàn Giao (Pre-Delivery Checklist)
- [ ] 100% biểu tượng là SVG vector (Lucide icons), 0% emoji.
- [ ] Font chữ chuẩn hóa: `Inter` cho text và `JetBrains Mono` cho dữ liệu kỹ thuật.
- [ ] `cursor: pointer` cùng hiệu ứng `scale(0.98)` trên các phần tử tương tác.
- [ ] Không có hiện tượng giật lag (Zero Jank): Chỉ animate `transform` và `opacity`.
- [ ] Trợ năng chuẩn WCAG: Đầy đủ `aria-label` cho nút icon-only, tỷ lệ tương phản $\ge 4.5:1$.
- [ ] Trình bày rõ ràng các chỉ số đo lường (Latency ms, Tokens, Điểm số xác suất, Trace ID).

