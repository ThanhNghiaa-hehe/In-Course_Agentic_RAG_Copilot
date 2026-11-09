# TASK PLAN: CẢI TỔ HẠ TẦNG ĐA LƯỢT, DIỆT QUICK-FIX & CHUẨN HÓA KIỂM TOÁN HỘI THOẠI
> **Dự án:** In-Course Agentic RAG Copilot  
> **Tác giả:** Trần Thành Nghĩa (MSSV: `23DH112252`), HUFLIT  
> **Cơ sở kỹ thuật:** Báo cáo Kiểm toán Nhịp 1A (`.agent/technical_debt_audit.md`) & Thẩm định Toán học Nhịp 1B (`.agent/implementation_spec.md`)  
> **Nguyên tắc bất biến:** Zero Quick-Fix | 100% Machine Learning Data-Driven | Zero Regression (Golden 200 Benchmarks)

---

## GIAI ĐOẠN 1: THIẾT LẬP CẤU HÌNH TẬP TRUNG & TÁCH RỜI DỮ LIỆU (NHỊP 2 - @core-coder)
- [x] **Mục 1.1: Bổ sung các tham số cấu hình vào `app/config.py`**
  - [x] Bổ sung `ROUTER_SOCIAL_PURE_THRESHOLD: float = 0.88`
  - [x] Bổ sung `ROUTER_CONTEXTUAL_COURSE_MIN: float = 0.35`
  - [x] Bổ sung `ROUTER_CONTEXTUAL_GAIN_MARGIN: float = 0.05`
  - [x] Bổ sung `MAX_HISTORY_CHARS: int = 2400`
  - [x] Bổ sung `SLIDING_WINDOW_TURNS: int = 5`
  - [x] Bổ sung `MAX_CODE_ILLUSTRATION_LINES: int = 25`
  - [x] Bổ sung `MARKOV_HIJACK_PENALTY: int = 80`
  - [x] Bổ sung `GREETING_LOOP_PENALTY: int = 20`
- [x] **Mục 1.2: Chuẩn hóa `data/metadata/router_intent_manifest.json`**
  - [x] Chuyển toàn bộ 7 văn mẫu phản hồi tĩnh từ `app/agent/router.py` vào mục `chitchat_subintents` trong file JSON.
  - [x] Bổ sung các Prototype xác nhận chuyển bài đơn âm (*"ừ"*, *"có"*, *"ok"*, *"dạ"*) vào `confirm_anchors`.
  - [x] Bổ sung các nhãn template giả thuyết NLI đầy đủ cho điều hướng bài học và xác nhận chuyển bài.

---

## GIAI ĐOẠN 2: TRIỆT TIÊU BẪY CATCH-22 & CẢI TỔ ĐỊNH TUYẾN ĐA LƯỢT (NHỊP 2 - @core-coder)
- [x] **Mục 2.1: Tái cấu trúc logic tại `app/services/chat_graph.py` quanh L220-L245**
  - [x] Xóa bỏ hoàn toàn câu lệnh chặn nhị phân `if not raw_clf.is_course_query: classification = raw_clf` tại L228.
  - [x] Xóa bỏ hoàn toàn điều kiện số ma thuật `len(raw_prompt.split()) < 4` tại L231.
  - [x] Triển khai cơ chế Dual-Track Semantic Evaluation (Context-Aware Query Formulation chuẩn SIGIR):
    - Track 1 (Pure Social Gate): Kiểm tra qua `router.is_pure_social(raw_prompt)`. Nếu độ tương quan với Prototype chào hỏi/cảm ơn/tạm biệt thuần túy $\ge 0.88$, xác định ngay là `chit_chat`.
    - Track 2 (Academic Contextual Gain Gate): Nếu không thỏa Pure Social và có `last_user_query`, xây dựng $u_{\text{contextual}} = \text{Formulate}(u_{t-1}, u_t)$ và phân loại song song.
    - So sánh biên độ gia tăng xác suất học thuật $\Delta P_{\text{course}}$ hoặc xác thực qua NLI Arbiter. Nếu đạt điều kiện Pareto, kích hoạt RAG pipeline với `is_course_query = True` và cập nhật `search_query`.
- [x] **Mục 2.2: Tái cấu trúc `app/agent/router.py`**
  - [x] Tích hợp hàm `is_pure_social(prompt: str) -> tuple[bool, float]` dựa trên ma trận prototype Cosine của `router_intent_manifest.json`.
  - [x] Bỏ điều kiện ma thuật `len(prompt.split()) >= 2` tại L179 trong `is_confirmation`.
  - [x] Đọc 100% các chuỗi phản hồi sư phạm từ manifest JSON, loại bỏ các biến chuỗi hardcode cục bộ.

---

## GIAI ĐOẠN 3: CẢI TỔ BỘ KIỂM TOÁN HỘI THOẠI `app/services/telemetry_critic.py` (NHỊP 2 - @core-coder)
- [x] **Mục 3.1: Xóa bỏ hoàn toàn cơ chế khen thưởng mù quáng và tự nịnh**
  - [x] Xóa bỏ lời khen Fast-Path vô điều kiện tại L187-L188. Chỉ cho phép ghi nhận Merit khi lượt đối thoại là chào hỏi hợp lệ thực sự.
- [x] **Mục 3.2: Triển khai Multi-Turn Intent Fidelity (Markov Intent Transition Penalty & Greeting Loop Detector)**
  - [x] Trong `analyze_turn`: Phát hiện Contextual Hijacking ($\mathcal{H}_t = 1$) hoặc câu hỏi mang bản chất truy vấn học tập bị phân loại nhầm sang `chit_chat`. Trừ ngay 80 điểm ($\text{Score} \le 20/100$) và xuất cảnh báo vi phạm luồng hội thoại.
  - [x] Trong `analyze_session`: Đếm số lượt bị cướp luồng $N_{\text{hijack}}$. Nếu $N_{\text{hijack}} \ge 2$ (Greeting Loop), ép sập điểm toàn phiên xuống $\le 35/100$ và dán nhãn `🔴 CẦN TINH CHỈNH KHẨN CẤP`.
- [x] **Mục 3.3: Diệt số ma thuật ranh giới code AST và câu hỏi Socratic**
  - [x] Xóa bỏ điều kiện `num_lines > 10` tại L142. Áp dụng `_inspect_cpp_code_ast` trên mọi khối code fence Markdown.
  - [x] Thay thế phép kiểm tra thô sơ `? in response_text` tại L160 bằng bộ trích xuất câu kết thúc (Concluding Sentence Extractor) kết hợp kiểm tra ngữ nghĩa chỉ thị sư phạm.

---

## GIAI ĐOẠN 4: KIỂM CHUẨN TOÀN DIỆN & NGHIỆM THU CHỐNG HỒI QUY (NHỊP 3 - @grounding-evaluator & @qa-tester)
- [x] **Mục 4.1: Kiểm thử Unit Test & Hồi quy hồi chuẩn**
  - [x] Kiểm tra `git diff` xác nhận 0% regex hardcode theo đề thi (không tồn tại `if "bài mấy" in query`, 100% Data-Driven & Semantic Cosine Prototypes).
  - [x] Chạy kiểm thử hồi quy toàn bộ test suite hiện có: `pytest tests/ -v` (Đã pass 100% tests/test_chat_stream.py, tests/test_search_api.py và tests/test_multiturn_benchmark.py).
- [x] **Mục 4.2: Mô phỏng kịch bản chat đa lượt trong Playground Debug**
  - [x] Turn 1: `"hello"` $\rightarrow$ `chit_chat` (Đúng)
  - [x] Turn 2: `"tôi muốn học thuật toán sắp xếp thì ở bài mấy"` $\rightarrow$ `course_query` (Đúng)
  - [x] Turn 3: `"cụ thể là ở bài mấy trong khóa học"` $\rightarrow$ `course_query` (CỨU XÉT THÀNH CÔNG, KHÔNG BỊ CHIT_CHAT, Search query được bổ sung ngữ cảnh chính xác)
  - [x] Turn 4: `"nội dung bài đó có gì"` $\rightarrow$ `course_query` (Đúng)
  - [x] Kiểm chứng điểm số của `telemetry_critic.py`: Phiên đạt **100/100 điểm - XUẤT SẮC (SOTA PRODUCTION QUALITY)**, Multi-Turn Intent Fidelity: 100.0%, Socratic Compliance: 100.0%.
