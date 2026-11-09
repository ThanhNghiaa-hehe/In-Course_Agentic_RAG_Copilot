# BẢN ĐẶC TẢ KIẾN TRÚC KỸ THUẬT TOÀN DIỆN (NHỊP 1B)
## CẢI TỔ ĐÀM THOẠI ĐA LƯỢT, DIỆT BẪY CATCH-22 & KHỬ GIAN LẬN ĐO LƯỜNG
> **Tài liệu:** `.agent/implementation_spec.md`  
> **Hệ thống:** In-Course Agentic RAG Copilot  
> **Sinh viên thực hiện:** Trần Thành Nghĩa (MSSV: `23DH112252`), Trường Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT)  
> **Hội đồng Thiết kế (Nhịp 1B):** Kiến trúc sư trưởng + `@rag-architect` + `@solution-analyst`  
> **Đối tượng thi công (Nhịp 2 & 3):** `@core-coder`, `@grounding-evaluator`, `@qa-tester`  
> **Quy chuẩn phương pháp luận:** PSTACK / Poteto-Mode Rigor (Lauren Tan) & Data-Centric AI Integrity (Andrew Ng)  
> **Cam kết chất lượng:** Zero Quick-Fix | Zero Regex Hardcoding | Mathematical Rigor | Bảo toàn 100% Benchmark Đơn lượt.

---

## 1. BỐI CẢNH VÀ NGUYÊN TẮC THIẾT KẾ CỐT LÕI

Dựa trên Báo cáo Kiểm toán Nợ kỹ thuật [`.agent/technical_debt_audit.md`](file:///D:/In_Course_Agentic_RAG_Copilot/.agent/technical_debt_audit.md), hệ thống đang đối mặt với 4 khuyết tật cấu trúc:
1. **Bẫy Catch-22 tại [chat_graph.py#L228](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L228) và số ma thuật `len(raw_prompt.split()) < 4` tại [chat_graph.py#L231](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L231):** Khiến 100% câu hỏi tỉnh lược (Ellipsis) và câu hỏi quy chiếu (Anaphora) trong hội thoại đa lượt (như *"cụ thể là ở bài mấy trong khóa học"*, *"nội dung bài đó có gì"*) bị ép thành `chit_chat`, cuốn học viên vào vòng lặp chào hỏi (Greeting Loop).
2. **Ô nhiễm hoặc đứt gãy mỏ neo chủ đề (`last_course_query`):** Nếu chỉ lấy `history[-1]` của user mà không phân biệt lượt `chit_chat` (ví dụ Turn 1 *"hello"*) với lượt `course_query` (Turn 2 *"tôi muốn học thuật toán sắp xếp thì ở bài mấy"*), hoặc ghi đè mỏ neo bằng câu tỉnh lược thiếu thực thể ở Turn 3 (*"cụ thể là ở bài mấy"*), thì ở Turn 4 (*"nội dung bài đó có gì"*) chuỗi ghép sẽ mất hoàn toàn thực thể kỹ thuật gốc (*"thuật toán sắp xếp"*).
3. **Bẫy Tự Nịnh & Gian Lận Đo Lường (Self-Flattery Scoring Trap) tại [telemetry_critic.py#L187-L203](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py#L187-L203):** Lượt đối thoại bị lỗi đứt gãy luồng học tập lại được khen thưởng Fast-Path và chấm 100/100 điểm tuyệt đối (`Score = 100`), che giấu lỗi hệ thống.
4. **Rải rác Magic Numbers & Hardcoded Strings:** Các hằng số phản hồi tĩnh trong [router.py#L30-L77](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L30-L77), điều kiện `len(prompt.split()) >= 2` tại [router.py#L179](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L179), và `num_lines > 10` tại [telemetry_critic.py#L142](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py#L142).

Bản đặc tả này thiết lập giải pháp tổng quát ở tầng nền tảng theo 4 bất biến học thuật:
- **SIGIR / Google Research Conversational Query Formulation:** Biểu diễn trạng thái hội thoại Markov $P(I_t \mid u_t, u_{\text{anchor}}, I_{t-1})$ với mỏ neo chủ đề học thuật `last_course_query` được bảo lưu xuyên suốt mạch hỏi đáp và tạo câu hỏi tìm kiếm ngữ cảnh `search_query`.
- **Pareto Context Sufficiency (ICLR 2025):** Phân định rạch ròi giữa xã giao thuần khiết (`Pure Social Prototype Matching`: `greeting`, `gratitude`, `goodbye`) và câu hỏi làm rõ giáo trình / kỹ thuật. Tuyệt đối **CẤM 100% REGEX HARDCODE** (cấm viết `if "bài mấy" in query:`).
- **Multi-Turn Intent Fidelity Audit:** Kiểm toán chuyển trạng thái ý định, trừng phạt nặng lỗi Conversational Hijacking (`-80` điểm, kéo điểm lượt xuống $\le 20/100$) và đánh sập điểm phiên khi dính Greeting Loop ($\le 35/100$).
- **Strict Pydantic v2 Configuration & Clean Code:** Đưa 100% tham số, ngưỡng và ngân sách vào `app/config.py`.

---

## 2. CƠ SỞ TOÁN HỌC & CÔNG THỨC QUYẾT ĐỊNH PARETO

### 2.1. Phân Phối Xác Suất Ý Định Đa Lượt & Mỏ Neo Học Thuật (`last_course_query`)
Tại lượt $t$, người dùng gửi phát ngôn $u_t$ (`raw_prompt`). Gọi $u_{\text{anchor}}$ (`last_course_query`) là câu hỏi học thuật tự lập gần nhất đã được xác nhận là `course_query` trong phiên (các lượt `chit_chat` như Turn 1 `"hello"` hoàn toàn không được gán làm $u_{\text{anchor}}$).

1. **Bước 1: Kiểm định Độ thuần khiết Xã giao (Pure Social Prototype Gate - $\mathcal{G}_{\text{social}}$):**
   Gọi $\mathcal{P}_{\text{social}} = \mathcal{P}_{\text{greeting}} \cup \mathcal{P}_{\text{gratitude}} \cup \mathcal{P}_{\text{goodbye}}$ là tập hợp các vector nguyên mẫu xã giao thuần túy (1024-dim E5) nạp từ `data/metadata/router_intent_manifest.json`.
   $$\text{Sim}_{\text{social}}(u_t) = \max_{\mathbf{p} \in \mathcal{P}_{\text{social}}} \frac{\mathbf{e}(u_t) \cdot \mathbf{p}}{\|\mathbf{e}(u_t)\| \|\mathbf{p}\|}$$
   Gọi $\mathcal{P}_{\text{all\_chitchat}}$ là toàn bộ các subintents trong `chitchat_subintents` (bao gồm cả `identity_architecture`, `socratic_pedagogy`, `advice`).
   Phát ngôn $u_t$ được công nhận là **Xã giao thuần khiết / Chào hỏi độc lập** khi và chỉ khi:
   $$\text{IsPureSocial}(u_t) \iff \text{Sim}_{\text{social}}(u_t) \ge \tau_{\text{pure\_social}} \quad (\tau_{\text{pure\_social}} = 0.88)$$

2. **Bước 2: Đánh giá Ngữ cảnh Kép (Dual-Track Contextual Formulation - SIGIR):**
   - **Trường hợp 1 ($u_{\text{anchor}} = \emptyset$ — Chưa có ngữ cảnh học tập trước đó, ví dụ Turn 1 `"hello"` hoặc Turn 2 câu học thuật đầu tiên):**
     Thực thi phân loại đơn lượt chuẩn mực $P(I_t \mid u_t)$ qua `router.classify(u_t)`.
     - Nếu `raw_clf.is_course_query == True`: Khởi tạo mỏ neo $u_{\text{anchor}} \leftarrow u_t$, `search_query` $\leftarrow u_t$.
     - Nếu `raw_clf.is_course_query == False`: Giữ nguyên $u_{\text{anchor}} = \emptyset$.
   - **Trường hợp 2 ($u_{\text{anchor}} \neq \emptyset$ — Đang trong mạch thảo luận học tập):**
     - **Nhánh 2a (`IsPureSocial(u_t) == True`):** Học viên chủ động chào / cảm ơn / tạm biệt kết thúc mạch $\rightarrow$ Trả về `chit_chat` (`Fast-Path`), giữ nguyên hoặc xóa nhẹ trạng thái điều hướng.
     - **Nhánh 2b (`raw_clf.is_course_query == True`):** Phát ngôn mới tự thân đã là `course_query`.
       - Để bảo vệ tính liên kết cho cả câu hỏi mới tự lập lẫn câu hỏi nối tiếp có chứa thuật ngữ mỏng, thiết lập `search_query = raw_prompt`, còn `retrieval_node` sẽ tự động dùng `last_course_query` làm Contextual Fallback nếu `raw_prompt` rơi vào `coverage_gap` hoặc `is_low_confidence`. Cập nhật $u_{\text{anchor}} \leftarrow u_t$.
     - **Nhánh 2c (`raw_clf.is_course_query == False` và `IsPureSocial(u_t) == False`):**
       Đây chính là vùng của các câu hỏi tỉnh lược / đại từ chỉ định / làm rõ vị trí bài giảng (như Turn 3 *"cụ thể là ở bài mấy trong khóa học"*, Turn 4 *"nội dung bài đó có gì"*).
       Hệ thống kiến tạo truy vấn hợp nhất theo chuẩn SIGIR:
       $$u_{\text{contextual}} = \mathcal{F}(u_{\text{anchor}}, u_t) = u_{\text{anchor}} \oplus \text{" -> "} \oplus u_t$$
       Và thẩm định qua phương thức `router.classify_contextual(raw_prompt=u_t, contextual_prompt=u_{\text{contextual}}, anchor_query=u_{\text{anchor}})`:
       1. Tính phân phối xác suất SLM ONNX INT8 trên $u_{\text{contextual}}$: $\mathbf{P}^{\text{ctx}} = [p_{\text{chit}}^{\text{ctx}}, p_{\text{course}}^{\text{ctx}}, p_{\text{oos}}^{\text{ctx}}]$ và trên $u_t$: $\mathbf{P}^{\text{raw}} = [p_{\text{chit}}^{\text{raw}}, p_{\text{course}}^{\text{raw}}, p_{\text{oos}}^{\text{raw}}]$.
       2. Tính độ gia tăng xác suất học thuật khi ghép ngữ cảnh:
          $$\Delta P_{\text{course}} = p_{\text{course}}^{\text{ctx}} - p_{\text{course}}^{\text{raw}}$$
       3. **Tiêu chuẩn Cứu xét Pareto (Contextual Course Rescue):**
          Phát ngôn $u_t$ được xác nhận là `course_query` nối tiếp nếu thỏa mãn **một trong ba** điều kiện toán học:
          - **(i) Trội xác suất ngữ cảnh:** `contextual_clf.is_course_query == True` (hoặc $p_{\text{course}}^{\text{ctx}} \ge \tau_{\text{ctx\_course}} = 0.35$).
          - **(ii) Độ lợi thông tin ngữ cảnh dương (Positive Contextual Information Gain):** $\Delta P_{\text{course}} \ge \tau_{\text{gain}} = 0.05$ và $p_{\text{oos}}^{\text{raw}} < 0.65$ (chứng tỏ khi ghép với mỏ neo bài học, vector dịch chuyển mạnh về phía không gian học thuật).
          - **(iii) Suy luận NLI Đa lượt (Multi-Turn NLI Entailment Rescue):** Kích hoạt Cross-Encoder `mDeBERTa-v3` với tiền đề ghép nối:
            $$\text{Premise} = \text{f"Học viên đang tìm hiểu: '\{u_{\text{anchor}}\}'. Tiếp theo học viên hỏi: '\{u_t\}'."}$$
            Nếu xác suất giả thuyết `course_query` đạt $\ge 0.45$ (hoặc cao hơn `out_of_scope`), lập tức phân định là `course_query`.
       4. Khi được cứu xét thành `course_query`:
          - Đặt `is_course_query = True`, `intent = "course_query"`, `direct_response = None`.
          - Đặt `search_query = f"{u_anchor} {u_t}"` để tầng `retrieval_node` có đầy đủ thực thể kỹ thuật từ $u_{\text{anchor}}$ kết hợp với yêu cầu làm rõ của $u_t$.
          - **Bảo toàn mỏ neo gốc ($u_{\text{anchor}}$):** Giữ nguyên $u_{\text{anchor}}$ (không ghi đè bằng câu cụt $u_t$) để ở Turn 4 (*"nội dung bài đó có gì"*), mỏ neo vẫn giữ nguyên thực thể kỹ thuật của Turn 2 (*"tôi muốn học thuật toán sắp xếp thì ở bài mấy"*).

### 2.2. Chứng Minh Bảo Toàn 100% Benchmark Đơn Lượt (Zero Regression Proof)
Trên toàn bộ 200 câu hỏi của bộ Golden Benchmark Stage 11 và các bài kiểm thử đơn lượt (`pytest tests/`):
- Mọi lời gọi `router.classify(prompt)` độc lập đều có `history = []` và `last_course_query = None`.
- Do đó nhánh hợp nhất ngữ cảnh đa lượt hoàn toàn không can thiệp vào phân phối xác suất đơn lượt $P(I_t \mid u_t)$, bảo toàn tuyệt đối 100% kết quả khảo thí hiện hành.

---

## 3. CÔNG THỨC KIỂM TOÁN ĐA LƯỢT `Multi-Turn Intent Fidelity` (`telemetry_critic.py`)

### 3.1. Định Nghĩa Biến Cố Đứt Gãy Hội Thoại (Conversational Hijacking / Intent Collapse)
Tại lượt $t$, xét phát ngôn $u_t$ có kết quả định tuyến $I_t$ và trạng thái `used_fast_path`:
Một lượt bị đánh dấu **Đứt gãy ý định học tập (`is_intent_hijacked = True`)** trong 2 trường hợp:
1. **Chuyển trạng thái Markov bất hợp lệ (Multi-Turn Hijacking):**
   Lượt trước là học tập ($I_{t-1} = \text{"course\_query"}$ hoặc đã có lượt học tập trong phiên), lượt hiện tại bị rớt xuống $I_t = \text{"chit\_chat"}$ (`used_fast_path == True`), nhưng phát ngôn $u_t$ **KHÔNG đạt ngưỡng xã giao thuần khiết** ($\text{Sim}_{\text{social}}(u_t) < 0.88$).
2. **Câu hỏi nghi vấn học tập bị đánh tráo thành chào hỏi (Interrogative Intent Misclassification):**
   $I_t = \text{"chit\_chat"}$ và phản hồi của bot là văn mẫu chào hỏi mở đầu (*"Chào bạn! Tôi là In-Course AI Copilot..."*), nhưng $u_t$ không phải là lời chào ($\text{Sim}_{\text{social}}(u_t) < 0.88$).

### 3.2. Công Thức Tính Điểm Nghiêm Ngặt (Ràng Buộc Bắt Buộc $\text{Score}_t \le 20/100$)
Khi `is_intent_hijacked == True`:
1. **Tước bỏ 100% lời khen Fast-Path:** Tuyệt đối không ghi nhận Merit *"Kích hoạt Fast-Path thành công..."*.
2. **Trừ điểm trực diện (`CRITIC_HIJACKING_PENALTY = 80`):**
   $$\text{Score}_t = \max\left(0, 100 - 80 - \sum \Delta_{\text{other}}\right) \le 20/100$$
3. **Bổ sung trường chỉ số tường minh trong kết quả trả về:**
   - `"multi_turn_intent_fidelity": 0.0` (khi `is_intent_hijacked == True`) hoặc `1.0` (khi bảo toàn mạch ý định).
   - Trong `analyze_session`: Tính `intent_fidelity_rate` (%) trên toàn phiên. Nếu có $\ge 1$ lượt bị hijack, khóa trần đánh giá không được phép đạt `🟢 XUẤT SẮC`. Nếu có $\ge 2$ lượt bị hijack (Greeting Loop), ép điểm toàn phiên `overall_health_score <= 35` và gắn nhãn `🔴 CẦN TINH CHỈNH KHẨN CẤP (GREETING LOOP / INTENT DRIFT)`.

---

## 4. THIẾT KẾ CHI TIẾT THAY ĐỔI MÃ NGUỒN TỪNG FILE

### 4.1. Tệp [app/config.py](file:///D:/In_Course_Agentic_RAG_Copilot/app/config.py)
Bổ sung các hằng số cấu hình Pydantic v2 vào `Settings`:
```python
    # Multi-Turn Memory & Context Budget Settings (LangGraph)
    SLIDING_WINDOW_TURNS: int = 5
    MAX_HISTORY_CHARS: int = 2400
    MAX_CONTEXT_CHARS: int = 2400
    SUMMARIZER_TURN_TRIGGER: int = 6
    SOFT_NUDGE_TURN_TRIGGER: int = 6

    # Multi-Turn Intent Router & Semantic Formulation Settings
    ROUTER_PURE_SOCIAL_THRESHOLD: float = 0.88
    ROUTER_CONTEXTUAL_COURSE_MIN_PROB: float = 0.35
    ROUTER_CONTEXTUAL_GAIN_MARGIN: float = 0.05
    ROUTER_CONTEXTUAL_NLI_MIN_CONF: float = 0.45
    ROUTER_CONFIRM_COSINE_THRESHOLD: float = 0.88
    ROUTER_CONFIRM_MARGIN: float = 0.05
    ROUTER_CONFIRM_NLI_THRESHOLD: float = 0.70

    # Telemetry Critic Rigor & Multi-Turn Intent Fidelity Settings
    CRITIC_HIJACKING_PENALTY: int = 80
    CRITIC_GREETING_LOOP_PENALTY: int = 20
    CRITIC_MAIN_VIOLATION_PENALTY: int = 40
    CRITIC_INCLUDE_VIOLATION_PENALTY: int = 20
    CRITIC_UNVERIFIED_TS_PENALTY: int = 15
    CRITIC_MISSING_QUESTION_PENALTY: int = 10
    CRITIC_HIGH_LATENCY_PENALTY: int = 10
    CRITIC_LATENCY_THRESHOLD_MS: int = 4000
    CRITIC_MAX_SESSION_SCORE_ON_GREETING_LOOP: int = 35
    MAX_CODE_ILLUSTRATION_LINES: int = 25
```

### 4.2. Tệp [data/metadata/router_intent_manifest.json](file:///D:/In_Course_Agentic_RAG_Copilot/data/metadata/router_intent_manifest.json)
1. Mở rộng mô tả ngữ nghĩa của giả thuyết NLI `course_query` để bao quát cả câu hỏi điều hướng cấu trúc bài giảng và nội dung bài học trong khóa học:
   ```json
   "course_query": "Học viên đang hỏi kiến thức lập trình C++, cú pháp, thuật toán, hàm, lớp, tìm hiểu nội dung bài giảng, bài học cụ thể hoặc cách dùng mã nguồn để tính toán dữ liệu trong chương trình máy tính"
   ```
2. Bổ sung trường `"pure_social_subintents": ["greeting", "gratitude", "goodbye"]` vào manifest để định danh rõ nhóm xã giao thuần khiết theo hướng Data-Driven.

### 4.3. Tệp [app/agent/router.py](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py)
1. **Tách dữ liệu phản hồi khỏi code:** Nạp các phản hồi mặc định từ `_manifest_data["chitchat_subintents"]` thay vì phụ thuộc vào khối chuỗi cứng đồ sộ.
2. **Xóa số ma thuật `len(prompt.split()) >= 2` tại L179** trong `NLIArbiter.is_confirmation`: Sử dụng `settings.ROUTER_CONFIRM_COSINE_THRESHOLD`, `settings.ROUTER_CONFIRM_MARGIN`, `settings.ROUTER_CONFIRM_NLI_THRESHOLD`.
3. **Bổ sung ma trận Prototype xã giao thuần khiết (`_pure_social_proto_matrix`) và hàm `get_pure_social_similarity(prompt: str) -> float`:**
   - Trong `_ensure_chitchat_prototypes()`, ngoài `_chitchat_proto_matrix` (cho cả 6 subintents), tách riêng các vector thuộc `pure_social_subintents` (`greeting`, `gratitude`, `goodbye`) vào `self._pure_social_proto_matrix`.
   - Hàm `get_pure_social_similarity(self, prompt: str) -> float` trả về $\max \cos(\mathbf{e}(\text{prompt}), \mathcal{P}_{\text{social}})$.
   - Hàm `is_pure_social(self, prompt: str) -> tuple[bool, float]` trả về `(sim >= settings.ROUTER_PURE_SOCIAL_THRESHOLD, sim)`.
4. **Bổ sung phương thức `classify_contextual(self, raw_prompt: str, anchor_query: str) -> tuple[RouterClassification, str]`:**
   - Nhận `raw_prompt` ($u_t$) và `anchor_query` ($u_{\text{anchor}}$).
   - Kiểm tra `is_pure_social(raw_prompt)`: Nếu `True`, trả về ngay kết quả phân loại `chit_chat` của `raw_prompt`.
   - Tính xác suất SLM cho `raw_prompt` ($\mathbf{P}^{\text{raw}}$) và cho `contextual_prompt = f"{anchor_query} -> {raw_prompt}"` ($\mathbf{P}^{\text{ctx}}$).
   - Nếu `contextual_clf.is_course_query` là `True`, HOẶC $p_{\text{course}}^{\text{ctx}} \ge \text{settings.ROUTER\_CONTEXTUAL\_COURSE\_MIN\_PROB}$, HOẶC $(p_{\text{course}}^{\text{ctx}} - p_{\text{course}}^{\text{raw}} \ge \text{settings.ROUTER\_CONTEXTUAL\_GAIN\_MARGIN} \text{ và } p_{\text{oos}}^{\text{raw}} < 0.65)$:
     Trả về `RouterClassification(intent="course_query", direct_response=None, is_course_query=True)` kèm `search_query = f"{anchor_query} {raw_prompt}"`.
   - Nếu vẫn phân vân, gọi `_nli_arbiter.arbitrate(contextual_prompt)`: Nếu NLI dự đoán `course_query` hoặc độ tin cậy `course_query` $\ge \text{settings.ROUTER\_CONTEXTUAL\_NLI\_MIN\_CONF}$, giải cứu về `course_query`.

### 4.4. Tệp [app/services/chat_graph.py](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py)
1. **Cập nhật `AgentState`:**
   Bổ sung 2 trường trạng thái:
   ```python
   search_query: Optional[str]        # Câu truy vấn đã hợp nhất ngữ cảnh cho Retrieval
   last_course_query: Optional[str]   # Mỏ neo câu hỏi học thuật tự lập gần nhất
   ```
2. **Tái cấu trúc hoàn toàn `router_node` (L220-L246):**
   - **XÓA BỎ HOÀN TOÀN** dòng `if not raw_clf.is_course_query: classification = raw_clf` (L228) và `elif last_user_query and len(raw_prompt.split()) < 4:` (L231).
   - Thuật toán mới:
     ```python
     raw_clf = router.classify(raw_prompt)
     anchor_query = state.get("last_course_query")
     if not anchor_query and history:
         # Tìm câu hỏi user gần nhất trong history mà không phải là pure social greeting
         for m in reversed(history):
             if m.get("role") == "user":
                 cand = m.get("content", "")
                 is_soc, _ = router.is_pure_social(cand)
                 if not is_soc and router.classify(cand).is_course_query:
                     anchor_query = cand
                     break

     search_query: Optional[str] = raw_prompt if raw_clf.is_course_query else None
     new_last_course_query: Optional[str] = anchor_query

     if raw_clf.is_course_query:
         classification = raw_clf
         search_query = raw_prompt
         new_last_course_query = raw_prompt
         logger.info(f"[LangGraph:router_node] Query học thuật tự lập: '{raw_prompt[:40]}...' -> course_query")
     elif anchor_query:
         is_soc, soc_sim = router.is_pure_social(raw_prompt)
         if is_soc:
             classification = raw_clf
             search_query = None
             logger.info(f"[LangGraph:router_node] Phát ngôn xã giao thuần khiết (Sim={soc_sim:.3f}): '{raw_prompt[:35]}...' -> chit_chat")
         else:
             classification, formulated_q = router.classify_contextual(raw_prompt, anchor_query)
             if classification.is_course_query:
                 search_query = formulated_q
                 # Giữ nguyên anchor_query gốc để các lượt tỉnh lược kế tiếp (Turn 3 -> Turn 4) không bị mất thực thể gốc
                 new_last_course_query = anchor_query
                 logger.info(f"[LangGraph:router_node] Cứu xét đa lượt thành công: '{raw_prompt}' -> SearchQuery: '{search_query[:55]}...'")
             else:
                 search_query = None
     else:
         classification = raw_clf
         search_query = None
         logger.info(f"[LangGraph:router_node] Query đơn lượt ({raw_clf.intent}): '{raw_prompt[:35]}...'")
     ```
   - Trả về `"search_query": search_query` và `"last_course_query": new_last_course_query` trong dict kết quả của `router_node`.
3. **Cập nhật `retrieval_node`:**
   - Lấy `query_to_search = state.get("search_query") or raw_prompt`.
   - Lấy `fallback_anchor = state.get("last_course_query")`.
   - Bước 1: Truy xuất Qdrant bằng `query_to_search`.
   - Bước 2: Nếu `retrieval_res.status == "coverage_gap" or retrieval_res.is_low_confidence` và có `fallback_anchor` (khác `query_to_search`), thực hiện truy xuất dự phòng với `f"{fallback_anchor} {raw_prompt}"`.
4. **Cập nhật `commit_assistant_turn` và `reset_session_state`:**
   - Bảo toàn `last_course_query` trong `commit_assistant_turn` và xóa về `None` trong `reset_session_state`.
   - Thay toàn bộ số ma thuật (`5`, `2400`, `6`) bằng `settings.SLIDING_WINDOW_TURNS`, `settings.MAX_HISTORY_CHARS`, `settings.SUMMARIZER_TURN_TRIGGER`, `settings.SOFT_NUDGE_TURN_TRIGGER`.

### 4.5. Tệp [app/services/telemetry_critic.py](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py)
1. **Cập nhật `analyze_turn(self, entry: Dict[str, Any], prev_entry: Optional[Dict[str, Any]] = None, had_prior_course_query: bool = False)`:**
   - Kiểm tra **Multi-Turn Intent Fidelity**:
     - Sử dụng `get_intent_router().is_pure_social(prompt)` để biết chính xác câu nói của học viên có phải là chào hỏi / cảm ơn / tạm biệt thuần khiết hay không (Zero Hardcoded Keyword List!).
     - Nếu `intent == "chit_chat"` và `used_fast_path == True`:
       - Nếu `(had_prior_course_query or (prev_entry and prev_entry.get("router", {}).get("intent") == "course_query"))` VÀ `not is_pure_social`:
         Đánh dấu `is_intent_hijacked = True`, `multi_turn_intent_fidelity = 0.0`.
         Thêm vi phạm: `"Vi phạm Multi-Turn Intent Fidelity (Conversational Hijacking): Câu hỏi nối tiếp trong mạch học tập bị phân loại nhầm thành chit_chat."`
         Trừ `settings.CRITIC_HIJACKING_PENALTY` (`80` điểm) $\Rightarrow \text{Score} \le 20/100$!
         **Tuyệt đối không thêm Merit Fast-Path.**
   - **Xóa số ma thuật `num_lines > 10` tại L142:**
     Kiểm tra `_inspect_cpp_code_ast(block)` trên mọi khối code Markdown; phạt `has_main` trên mọi khối code chứa hàm `main()` thực thi, và phạt `has_include` nếu khối code có `#include` vượt quá 5 dòng.
   - **Chuẩn hóa kiểm tra câu hỏi gợi mở Socratic:**
     Tách phần văn bản ngoài code block, kiểm tra câu/đoạn kết thúc.
2. **Cập nhật `analyze_session`:**
   - Truyền `prev_entry` và cờ `had_prior_course_query` qua từng lượt.
   - Tính `intent_fidelity_rate` và đếm số lượt `hijacked_turns`.
   - Nếu `len(hijacked_turns) >= 2` (Greeting Loop): Khống chế `avg_score = min(avg_score, settings.CRITIC_MAX_SESSION_SCORE_ON_GREETING_LOOP)` ($\le 35/100$) và gắn nhãn `"CẦN TINH CHỈNH KHẨN CẤP (GREETING LOOP / INTENT DRIFT)"` (`🔴`).
   - Nếu `len(hijacked_turns) == 1`: Khống chế `avg_score = min(avg_score, 65)` và không cho phép đạt nhãn `🟢` hay `🟡`.
   - Hiển thị rõ chỉ số **Multi-Turn Intent Fidelity** trong báo cáo Markdown (`_render_markdown_report`).
