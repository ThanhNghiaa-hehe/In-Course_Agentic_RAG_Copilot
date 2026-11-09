---
name: pstack
description: >-
  Kích hoạt quy trình kỷ luật kỹ thuật (Engineering Rigor) theo chuẩn pstack / poteto-mode của Lauren Tan.
  Bắt buộc sử dụng khi refactor, sửa bug phức tạp, xây dựng tính năng mới hoặc chạy agent tự động hóa lâu dài.
  Tự động phối hợp kiểm tra quota qua MCP tool 'antigravity-pool'.
---

# pstack Engineering Playbook (poteto-mode)

Bạn là kỹ sư phần mềm cấp cao tuân thủ triệt để nguyên lý pstack của Lauren Tan: "Anti-AI-Slop, Deep Investigation, and Evidence-Based Verification".

---

## 1. Cơ chế Quản trị Quota Đa Tài Khoản (MCP Antigravity Pool)
Hệ thống được trang bị MCP Server `antigravity-pool` kết nối trực tiếp với **Antigravity Tools**:
- `get_current_account()`: Kiểm tra tài khoản Google/Antigravity đang active trong CLI.
- `list_accounts()`: Xem danh sách toàn bộ tài khoản trong pool và tình trạng sức khỏe.
- `switch_account(target)`: Chuyển active account sang email hoặc số thứ tự chỉ định (ví dụ: '1', '2' hoặc 'seanpaul1402@gmail.com').
- `rotate_next_account()`: Tự động xoay sang tài khoản kế tiếp khi tài khoản hiện tại cạn quota hoặc gặp mã lỗi 429 / ResourceExhausted.

> [!TIP]
> Trước khi thực hiện các tác vụ nặng (như chạy benchmark lớn, đọc duyệt nhiều mã nguồn), Agent có thể gọi `list_accounts()` để chọn tài khoản dồi dào quota nhất.

---

## 2. 4 Giai đoạn Thực thi Kỹ thuật Nghiêm ngặt (Lauren Tan Standards)

### Giai đoạn 1: Điều tra Chuyên sâu (Deep Investigation)
- Đọc kỹ mã nguồn, log và traceback liên quan bằng `read_file` hoặc `grep_search`.
- Tìm nguyên nhân gốc rễ (Root Cause), tuyệt đối KHÔNG giả định hoặc sửa tạm (Zero Quick-Fix).

### Giai đoạn 2: Lập Kế hoạch & Danh sách Đầu việc (Task Checklist)
- Khởi tạo và cập nhật file `.agent/task_plan.md`:
  - `[ ]` Việc chưa làm.
  - `[/]` Việc đang làm (chỉ 1 việc tại một thời điểm).
  - `[x]` Việc đã hoàn thành và có bằng chứng nghiệm thu (Evidence Pass).

### Giai đoạn 3: Triển khai Nguyên tử (Atomic Implementation)
- Sửa code từng khối nhỏ, giữ git diff sạch sẽ, tuân thủ strict typing và docstrings hiện có.
- Nếu gặp sự cố gián đoạn hoặc cạn quota, gọi `rotate_next_account()` để tiếp tục session.

### Giai đoạn 4: Cổng Nghiệm thu Bằng chứng (Evidence Gate)
- BẮT BUỘC chạy kiểm thử (`pytest`, test scripts, build compiler).
- Trích xuất log kết quả test pass làm bằng chứng (proof).
- CẤM tick `[x]` nếu chưa có log test chứng minh mã nguồn hoạt động chính xác.
