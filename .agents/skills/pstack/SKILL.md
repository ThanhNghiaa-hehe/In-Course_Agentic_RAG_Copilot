---
name: pstack
description: >-
  Kích hoạt quy trình kỷ luật kỹ thuật (Engineering Rigor) theo chuẩn pstack / poteto-mode của Lauren Tan,
  tích hợp Spec-Driven Unified E2E Spec & Cross-Layer Conflict Matrix (`specs/<slug>/spec.md`).
  Bắt buộc sử dụng khi refactor, sửa bug phức tạp trong pipeline RAG, xây dựng tính năng mới hoặc chạy Swarm/agent tự động hóa.
  Tự động phối hợp kiểm tra quota qua MCP tool 'antigravity-pool' và `swarm{action:"models"}`.
---

# pstack Engineering Playbook (Spec-Driven End-to-End Edition)

Bạn là kỹ sư phần mềm cấp cao tuân thủ triệt để nguyên lý pstack của Lauren Tan kết hợp **Spec-Driven Development**:
**"Anti-AI-Slop, Deep E2E Investigation, Conflict-Free Unified Spec, and Evidence-Based Verification"**.

---

## 1. Cơ chế Quản trị Quota Đa Tài Khoản (`antigravity-pool` & Swarm Quota)
Hệ thống được trang bị MCP Server `antigravity-pool` kết nối trực tiếp với **Antigravity Tools**:
- `get_current_account()`: Kiểm tra tài khoản Google/Antigravity đang active trong CLI.
- `list_accounts()`: Xem danh sách toàn bộ tài khoản trong pool và tình trạng sức khỏe.
- `switch_account(target)`: Chuyển active account sang email hoặc số thứ tự chỉ định.
- `rotate_next_account()`: Tự động xoay sang tài khoản kế tiếp khi tài khoản hiện tại cạn quota hoặc gặp mã lỗi `429` / `ResourceExhausted`.

> [!TIP]
> Trước khi khởi chạy Swarm hoặc tác vụ nặng, **luôn kiểm tra `swarm{action:"models", all:true}` và `list_accounts()`** để phân bổ vai (`auditor`, `coder`, `verifier`) sang pool còn dồi dào (tránh đốt cạn pool Weekly thấp như `< 30%`, ưu tiên pool 5H đang còn cao hoặc xoay sang tài khoản dự phòng).

---

## 2. Quy trình 5 Giai đoạn Kỹ thuật Nghiêm ngặt (pstack x Spec-Driven)

### Giai đoạn 1: Điều tra E2E Chuyên sâu (Deep End-to-End Investigation)
- Đọc trực tiếp mã nguồn, log phiên (`logs/playground_debug/*.json`) và traceback liên quan bằng `read_file` / tìm kiếm có định hướng.
- Truy vết trọn luồng từ đầu vào tới đầu ra: `IntentRouter` -> `CurriculumService` -> `RetrievalService` -> `ChatGraph (CRAG / ContextAssembly)` -> `ChatService (SSE / StreamGuardrails)` -> `TelemetryCritic`.
- Xác định đúng **Lớp bài toán (Problem Class)** và nguyên nhân gốc rễ; tuyệt đối **KHÔNG** đoán mò hoặc vá tạm (`Zero Quick-Fix`, cấm regex hardcode theo câu test mẫu).

### Giai đoạn 1.5: Xuất Unified E2E Spec & Cross-Layer Conflict Matrix (`specs/<slug>/spec.md`)
BẮT BUỘC viết `specs/<slug>/spec.md` theo mẫu tại [references/e2e_spec_template.md](references/e2e_spec_template.md) **trước khi sửa dòng code đầu tiên** (đặc biệt khi thay đổi tác động >= 2 tầng pipeline RAG hoặc sửa nhiều bug dễ xung đột):
1. **Constitution Check:** Ràng buộc `AGENTS.md`, `runtime-and-rigor-invariants.md`, tĩnh `messages[0]`, `Zero Fake Fallback`, `Data/Code Separation`.
2. **Problem Classes & E2E Behavioral Contract:** Khóa bảng hợp đồng `Input -> IntentRouter -> Curriculum/Retrieval -> CRAG/Context -> StreamGuardrail -> Output`.
3. **Dependency-Ordered Changes:** Chốt thứ tự sửa từ đầu luồng -> cuối luồng (`Manifest/Data -> Router -> Curriculum/Retrieval -> ChatGraph -> Chat/Guardrails`).
4. **Cross-Layer Conflict & Invariant Matrix (Cổng Chống Xung đột Chéo):** Phân tích rõ từng thay đổi có nguy cơ phá `M1/M2/M3`, `Golden 200`, `Multi-turn Anaphora`, `Streaming`, hoặc `KV Cache` hay không và nêu cơ chế phòng ngừa + test khóa kèm theo.
5. **Spec Gate:** Khi dùng Swarm, `auditor` (hoặc Thinker) thẩm định `spec.md` đạt `[approved]` (và trình User chốt nếu là đợt nâng cấp lớn) rồi mới mở khóa sang Giai đoạn 3.

### Giai đoạn 2: Lập Kế hoạch & Danh sách Đầu việc (`.agent/task_plan.md`)
- Cập nhật `.agent/task_plan.md` theo đúng thứ tự phụ thuộc trong `spec.md`:
  - `[ ]` Việc chưa làm.
  - `[/]` Việc đang làm (chỉ tối đa 1 việc active ở một thời điểm trên mỗi luồng).
  - `[x]` Việc đã hoàn thành **sau khi** có bằng chứng nghiệm thu thực tế (`Evidence Pass`).

### Giai đoạn 3: Triển khai Nguyên tử & Đối chiếu Spec (Atomic Implementation & Spec Audit)
- Sửa code theo đúng thứ tự phụ thuộc đã duyệt trong `specs/<slug>/spec.md`, giữ git diff gọn, strict typing (Pydantic v2), bảo toàn comments/docstrings không liên quan.
- **Zero Fake/Bogus Fallback:** Tuyệt đối không dùng fallback giả mạo hoặc nới lỏng điều kiện kiểm tra chỉ để qua test.
- Khi dùng Swarm, `auditor` đối chiếu git diff ngược lại **từng điều khoản và Conflict Matrix trong `specs/<slug>/spec.md`**, trả `@coordinator [approved]` mới chuyển sang Giai đoạn 4.
- Nếu gặp `429` / cạn quota giữa chừng, dùng `swarm{action:"model"}` (không kill worker mất ngữ cảnh) hoặc `rotate_next_account()`.

### Giai đoạn 4: Cổng Nghiệm thu Bằng chứng & Chống Ảo giác (Evidence & Data-Inspected Gate)
- **Thứ tự thực thi phần cứng:** Chạy **tuần tự từng tiến trình một** với `HF_HUB_OFFLINE=1` và `TRANSFORMERS_OFFLINE=1` (cấm chạy đồng thời nhiều tiến trình PyTorch/ONNX/FastEmbed/Uvicorn tranh GPU/CPU).
- **Chạy kiểm thử SAU bản sửa cuối cùng:**
  - Chạy unit/integration test mới tái hiện từng `PC-*` trong `spec.md`.
  - Chạy đầy đủ các bộ `pytest` hồi quy liên quan + LIVE `scripts/e2e_matrix_harness.py --suite all` (đúng model trong `.env`, không đánh tráo model).
- **No Hallucination & Data-Inspected Verification:**
  - Tuyệt đối không tự bịa số liệu, thời gian chạy hoặc báo "PASS" theo trí nhớ / khi chưa chạy lại sau bản sửa cuối.
  - Mọi báo cáo kết quả test phải nêu trung thực số lượng `passed / failed / skipped`, thời gian chạy thực tế, và phân định rạch ròi bài test dùng mock vs gọi Qdrant/LLM thật.
  - Kiểm chứng trực tiếp tệp dữ liệu / log đầu ra liên quan trước khi tick `[x]` trong `.agent/task_plan.md`.
  - Khi đóng phiên Swarm: `kill` sạch worker và kiểm tra không còn tiến trình Python/server mồ côi.
