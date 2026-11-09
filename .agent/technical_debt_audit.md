# BÁO CÁO KIỂM TOÁN TOÀN DIỆN NỢ KỸ THUẬT & DIỆT QUICK-FIX (NHỊP 1A)
> **Hệ thống:** In-Course Agentic RAG Copilot  
> **Sinh viên thực hiện:** Trần Thành Nghĩa (MSSV: `23DH112252`), Trường Đại học Ngoại ngữ - Tin học TP.HCM (HUFLIT)  
> **Repository:** `https://github.com/ThanhNghiaa-hehe/In-Course_Agentic_RAG_Copilot`  
> **Cơ quan kiểm toán:** Thanh Tra Kiểm Toán Độc Lập & Thám Tử Diệt Quick-Fix (`@codebase-auditor`)  
> **Phương pháp luận:** PSTACK / Poteto-Mode Rigor (Lauren Tan) & Data-Centric AI Integrity (Andrew Ng)  
> **Phạm vi kiểm toán (Scope):** [app/services/chat_graph.py](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py), [app/services/telemetry_critic.py](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py), [app/agent/router.py](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py)  
> **Nguyên tắc bất biến:** Zero Quick-Fix | Thẩm định bằng chứng thực tế | Không suy đoán cảm tính | Tuyệt đối không sửa mã nguồn trong Nhịp 1A.

---

## 1. TỔNG QUAN HIỆN TRẠNG & KHỦNG HOẢNG TOÀN VẸN HỆ THỐNG (EXECUTIVE SUMMARY)

Qua quy trình rà soát và đối chiếu tĩnh - động trên 3 tệp nguồn hạt nhân của hệ thống đàm thoại, Thanh tra Kiểm toán bóc trần **4 vùng khuyết tật kiến trúc cấu trúc (Structural Architectural Defects)** dẫn đến cuộc khủng hoảng trải nghiệm học viên và sai lệch đo lường:

1. **Bẫy Catch-22 Triệt Tiêu Ngữ Cảnh Đa Lượt ([chat_graph.py#L220-L239](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L220-L239)):**  
   Câu hỏi tiếp nối / làm rõ / tỉnh lược (Ellipsis / Anaphora) của học viên (như *"cụ thể là ở bài mấy"*, *"trong đó có gì"*, *"nội dung như thế nào"*) bị Router phán định độc lập là `chit_chat` do thiếu thực thể kỹ thuật độc lập. Dòng L228 áp đặt điều kiện chặn đứng nhị phân `if not raw_clf.is_course_query: classification = raw_clf`, khiến nhánh bổ sung ngữ cảnh `elif last_user_query` vĩnh viễn không bao giờ được kích hoạt. Hậu quả: Học viên bị cuốn vào "vòng lặp chào hỏi" (Greeting Loop), trợ giảng AI liên tục trả lời bằng văn mẫu xã giao thay vì giải đáp bài học.

2. **Bệnh Dịch "Số Ma Thuật" (Magic Numbers Epidemic):**  
   Xuất hiện dày đặc các ngưỡng cắt cứng thiếu cơ sở toán học: điển hình là `len(raw_prompt.split()) < 4` tại [chat_graph.py#L231](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L231) loại bỏ 100% câu hỏi nối tiếp tự nhiên dài từ 4-10 từ; ngưỡng `len(prompt.split()) >= 2` tại [router.py#L179](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L179); các ngưỡng kiểm tra AST `num_lines > 10`, `total_code_lines > 25` tại [telemetry_critic.py#L142-L154](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py#L142-L154); trần ngữ cảnh `2400` chars; ngưỡng sliding window `5` turns, `6` turns.

3. **Vấn Nạn Rải Rác Hardcode & Heuristics Thủ Công (Hardcoded Regex / Substrings / Strings):**  
   Hệ thống còn lưu giữ các bộ mẫu kiểm tra thô sơ: từ việc kiểm tra chuỗi `? in response_text` tại [telemetry_critic.py#L160](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py#L160) để chấm điểm gợi mở Socratic, đến các chuỗi nhúng tĩnh `endswith("?")` tại [router.py#L175](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L175), các nhãn template giả thuyết NLI gắn cứng trong mã Python, và 7 khối phản hồi văn mẫu tĩnh đồ sộ [router.py#L30-L77](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L30-L77).

4. **Cơ Chế Chấm Điểm Ảo & Tự Nịnh (Self-Flattery Scoring Trap - Metric Fraud):**  
   Tại [telemetry_critic.py#L187-L203](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py#L187-L203), khi Router phân loại sai một câu hỏi học tập thành `chit_chat`, hệ thống phát Fast-Path văn mẫu chào hỏi. Bộ kiểm toán tự động không những không trừ điểm phân loại sai mà còn **cộng điểm khen thưởng (Merit)** vì "kích hoạt Fast-Path tối ưu độ trễ" và cho điểm **100/100 tuyệt đối**! Đánh giá toàn phiên đạt **🟢 XUẤT SẮC 99-100/100 (SOTA PRODUCTION QUALITY)** bất chấp học viên đang bị kẹt trong bế tắc.

---

## 2. BỐC TRẦN CHI TIẾT 4 MỤC KIỂM TOÁN TRỌNG TÂM

### MỤC 1: BẪY CATCH-22 QUANH L228 TRONG `chat_graph.py`

#### 1. Bằng chứng mã nguồn thực tế
Trích dẫn trực tiếp từ [app/services/chat_graph.py#L220-L246](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L220-L246):

```python
# app/services/chat_graph.py L220-L246
# 1. Phân loại ý định trên câu hỏi độc lập (raw_prompt) trước
raw_clf = router.classify(raw_prompt)

last_user_query = ""
if history:
    last_user_query = next((m["content"] for m in reversed(history) if m.get("role") == "user"), "")

# Invariant 1: Nếu câu hỏi mới rõ ràng là chào hỏi, cảm ơn, hoặc ngoài lề, TUYỆT ĐỐI KHÔNG ghép ngữ cảnh cũ
if not raw_clf.is_course_query:
    classification = raw_clf
    logger.info(f"[LangGraph:router_node] Query độc lập xác định ({raw_clf.intent}): '{raw_prompt[:35]}...'")
elif last_user_query and len(raw_prompt.split()) < 4:
    # Chỉ khi câu hỏi kỹ thuật quá ngắn (câu cụt ellipsis, ví dụ 'tại sao?', 'nó dùng làm gì?') mới bổ sung ngữ cảnh
    contextual_prompt = f"{last_user_query} -> {raw_prompt}"
    classification = router.classify(contextual_prompt)
    logger.info(f"[LangGraph:router_node] Query cụt nối tiếp: '{raw_prompt}' -> Contextual: '{contextual_prompt[:45]}...'")
else:
    classification = raw_clf
    logger.info(f"[LangGraph:router_node] Query kỹ thuật tự lập (Self-Contained): '{raw_prompt[:35]}...' -> course_query")
```

Kèm cơ chế rẽ nhánh hạ tầng tại [app/services/chat_graph.py#L542-L551](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L542-L551):
```python
def should_retrieve(state: AgentState) -> str:
    if state.get("is_course_query", False):
        return "retrieval"
    return "fast_path"
```

#### 2. Cơ chế hình thành bẫy Catch-22 (Mechanisms & Probabilistic Failure)
1. **Bản chất ngữ nghĩa của câu hỏi tỉnh lược (Elliptical / Anaphora Query):**  
   Khi học viên ở lượt trước hỏi: *"tôi muốn học các thuật toán về các hàm sắp xếp thì ở bài mấy"*, lượt sau học viên hỏi tiếp: *"cụ thể là ở bài mấy"* hoặc *"trong đó có gì"*. Câu hỏi này vốn dĩ là một mệnh đề phụ thuộc (dependent clause), bản thân nó **không chứa thực thể kỹ thuật C++ độc lập** (không có các token `sort`, `vector`, `con trỏ`, `hàm`).
2. **Sai lầm giả định độc lập (Naive Independence Fallacy):**  
   Xác suất ý định hội thoại đa lượt đúng đắn về mặt toán học là $P(I_t \mid u_t, H_{<t})$. Tuy nhiên, L221 lại thực hiện $P(I_t \mid u_t)$ hoàn toàn cô lập. Do $u_t$ chứa các từ ngữ giao tiếp phổ thông (*cụ thể, là, ở, bài, mấy*), mô hình phân loại (SLM ONNX / NLI) định tuyến sang cụm `chit_chat` ($P_{	ext{chit}} > P_{	ext{course}}$).
3. **Cú khóa chết Catch-22 tại L228:**  
   `raw_clf.is_course_query` nhận giá trị `False`. Điều kiện L228 `if not raw_clf.is_course_query:` được thỏa mãn! Mã nguồn lập tức gán `classification = raw_clf` và thoát khỏi khối logic.
   - **Vòng lặp nghịch lý Catch-22:** Để câu hỏi được ghép ngữ cảnh với lượt trước (`last_user_query -> raw_prompt`), nó bắt buộc phải thỏa mãn điều kiện là `course_query` khi đứng một mình! Nhưng vì nó là câu hỏi tỉnh lược đứng một mình, nó không bao giờ có thể tự chứng minh mình là `course_query`!
4. **Hậu quả hạ tầng:**  
   StateGraph chuyển sang `fast_path`, hoàn toàn bỏ qua `retrieval_node`, `crag_grader_node` và `context_assembly_node`. Người dùng nhận phản hồi chào hỏi xã giao lặp đi lặp lại.

#### 3. Đánh giá Mức độ Nghiêm trọng & Tác động
- **Mức độ nghiêm trọng:** **CRITICAL (Khẩn cấp cấp 1 - Phá hủy tính năng hội thoại đa lượt)**.
- **Tác động thực tế:**
  - 100% câu hỏi làm rõ, câu hỏi chỉ định giáo trình tiếp nối của học viên bị biến thành chào hỏi xã giao.
  - Phá vỡ toàn bộ giá trị sư phạm của Agentic RAG Copilot, biến trợ giảng AI thành một con chatbot lặp văn mẫu ngô nghê.
  - Vi phạm trắng trợn Invariant kiến trúc về LangGraph Stateful Multi-turn Orchestration trong `AGENTS.md`.

#### 4. Hướng khắc phục tổng quát (Zero Quick-Fix Standard)
- **Không áp dụng Quick-Fix:** Cấm hardcode regex kiểm tra từ khóa như `if 'bài mấy' in raw_prompt:` hay `if 'trong đó' in raw_prompt:`.
- **Giải pháp Kiến trúc Tổng Quát (Dual-Track Semantic Evaluation):**
  - Trong `router_node`: Khi `history` có tồn tại tin nhắn người dùng (`last_user_query`), trước khi kết luận `chit_chat`, hệ thống phải thực hiện đánh giá ngữ cảnh kép:
    1. Đánh giá độ tự tin thuần khiết của Chit-Chat: Chỉ chấp nhận `chit_chat` độc lập khi câu hỏi đạt độ tương đồng vector cực cao với tập Prototype chào hỏi xã giao thuần túy ($Sim_{	ext{chitchat}} \ge 0.88$ và độ dài $\le 3$ từ như *"chào bạn"*, *"hello"*, *"cảm ơn nhé"*).
    2. Đối với mọi câu hỏi còn lại (chứa từ nghi vấn, đại từ chỉ định, hoặc không thuộc cụm chào hỏi tuyệt đối): BẮT BUỘC xây dựng biểu diễn ngữ cảnh $u_{	ext{contextual}} = 	ext{Formulate}(u_{	ext{last}}, u_{	ext{raw}})$ và phân loại song song. Nếu $u_{	ext{contextual}}$ được mô hình xác định là `course_query` với biên độ vượt trội, lập tức chuyển tiếp vào RAG pipeline.

---

### MỤC 2: ĐIỀU KIỆN SỐ MA THUẬT `len < 4` VÀ TẤT CẢ MAGIC NUMBERS / NGƯỠNG CỨNG

#### 1. Bằng chứng mã nguồn chi tiết từng file

##### A. Trong [app/services/chat_graph.py](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py)
1. **[L231](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L231):** `elif last_user_query and len(raw_prompt.split()) < 4:`  
   - **Số ma thuật:** `4`.
   - **Bản chất:** Giả định vô căn cứ rằng chỉ câu hỏi dưới 4 từ mới là câu cụt/tỉnh lược. Trong tiếng Việt, các câu hỏi tiếp nối tự nhiên luôn có độ dài 5-10 từ (*"cụ thể là ở bài mấy vậy trợ giảng"* - 9 từ; *"nội dung phần đó học những gì"* - 7 từ). Số ma thuật này thẳng tay tiêu diệt toàn bộ câu hỏi bình thường của người dùng.
2. **[L132, L164](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L132):** `max_chars: int = 2400` và `idx > 1`  
   - **Số ma thuật:** `2400` ký tự (áp trần cứng ngân sách ngữ cảnh RAG) và `idx > 1` (bỏ qua kiểm tra độ dài cho chunk đầu tiên bất chấp chunk đó dài bao nhiêu).
3. **[L455, L456](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L455):** `SLIDING_WINDOW_TURNS = 5`, `max_history_count = SLIDING_WINDOW_TURNS * 2`  
   - **Số ma thuật:** Cố định `5` lượt (10 messages) mà không dựa vào token budget động của context window LLM.
4. **[L465](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L465):** `MAX_HISTORY_CHARS = 2400`  
   - **Số ma thuật:** Cắt tỉa cứng lịch sử ở mức 2400 ký tự.
5. **[L475](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L475):** `len(content) > 180`  
   - **Số ma thuật:** `180` ký tự để quyết định có bóc tách Markdown fence hay không.
6. **[L502](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L502):** `len(sliding_history) >= 2`  
   - **Số ma thuật:** Ép buộc giữ lại tối thiểu đúng 2 messages khi tràn bộ nhớ.
7. **[L514](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L514):** `if turn_count > 6:`  
   - **Số ma thuật:** `6` lượt để kích hoạt Soft Nudge sư phạm.
8. **[L632, L633, L635](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L632):** `current_turn > 6 and len(history) > 10`, `history[:-10]`, `m['content'][:60]`  
   - **Số ma thuật:** `6` lượt, `10` messages, cắt lát cứng `[:-10]` và cắt chuỗi tiêu đề `[:60]`.

##### B. Trong [app/services/telemetry_critic.py](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py)
1. **[L142](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py#L142):** `if num_lines > 10:`  
   - **Số ma thuật:** `10` dòng. Chỉ kiểm tra `#include` và `main()` nếu khối code dài hơn 10 dòng! Một khối code 10 dòng giải trọn vẹn bài tập của học sinh sẽ hoàn toàn thoát khỏi bộ lọc kiểm tra ranh giới Socratic!
2. **[L154](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py#L154):** `if total_code_lines > 25:`  
   - **Số ma thuật:** `25` dòng để cảnh báo code minh họa quá dài.
3. **[L191-L202](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py#L191-L202):** Điểm khởi tạo và trừ điểm:
   - `score = 100`
   - `score -= 40` (nếu có `main` trong code dài)
   - `score -= 20` (nếu có `#include` trong code dài)
   - `score -= 15` (nếu có timestamp ngoài Whitelist)
   - `score -= 10` (nếu thiếu dấu hỏi trong `course_query`)
   - `score -= 10` (nếu `ttft_ms > 4000` và không phải fast-path)
   - Toàn bộ thang điểm 40/20/15/10/4000ms là các con số ma thuật tùy tiện, không phản ánh độ suy giảm chất lượng sư phạm thực tế.
4. **[L278, L281, L303, L304, L305, L342](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py#L278):**
   - `avg_score >= 90` (Xuất sắc)
   - `avg_score >= 75` (Đạt chuẩn)
   - `avg_score >= 85` (Tối ưu - mâu thuẫn trực tiếp với mốc 90 ở trên!)
   - `compliance_rate >= 80`
   - `avg_ttft < 1500` và `avg_ttft > 3000`

##### C. Trong [app/agent/router.py](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py)
1. **[L176](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L176):** `sim_c >= 0.88` và `sim_c > sim_r + 0.05`  
   - **Số ma thuật:** Ngưỡng tương đồng cosine `0.88` và biên độ chênh lệch `0.05` để phán định học viên đồng ý chuyển bài.
2. **[L179](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L179):** `len(prompt.split()) >= 2`  
   - **Số ma thuật:** `2`. Bắt buộc prompt phải có từ 2 từ trở lên mới kích hoạt NLI giải cứu xác nhận chuyển bài. Các câu phản hồi đơn âm kinh điển như *"ừ"*, *"có"*, *"ok"*, *"dạ"* có độ dài 1 từ sẽ bị loại bỏ không thương tiếc nếu điểm cosine vector E5 rơi vào vùng $pprox 0.82-0.87$!
3. **[L191](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L191):** `top_score >= 0.70` (Ngưỡng tin cậy NLI xác nhận).
4. **[L371-L375](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L371-L375):** Ngưỡng mở cổng Bi-Directional Entropy/Margin Gate:
   - `margin < 0.18`
   - `top1_class == "out_of_scope" and p_course >= 0.22`
   - `top1_class == "course_query" and (p_oos >= 0.28 or p_chit >= 0.25)`
5. **[L384, L387, L394](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L384):** Ngưỡng phân định NLI Arbiter:
   - `nli_conf >= 0.50 or p_course >= 0.35`
   - `nli_conf >= 0.55 or (nli_conf >= 0.42 and p_chit >= 0.30)`
   - `nli_conf >= 0.65`

#### 2. Đánh giá Mức độ Nghiêm trọng & Tác động
- **Mức độ nghiêm trọng:** **HIGH (Nguy cơ suy thoái tính tổng quát hóa - Brittleness)**.
- **Tác động:** Khiến hệ thống cực kỳ mỏng manh trước các biến thể diễn đạt tự nhiên của người dùng; tạo ra các lỗ hổng biên (edge cases) vô lý mà các bài kiểm thử benchmark ngẫu nhiên sẽ dễ dàng kích hoạt lỗi.

#### 3. Hướng khắc phục tổng quát
- Tập trung hóa toàn bộ các tham số cấu hình ngưỡng vào `app/config.py` (hoặc manifest metadata JSON), tuyệt đối không để rải rác trong code logic.
- Thay thế các điều kiện độ dài thô sơ (`len.split() < 4`, `len.split() >= 2`) bằng các đặc trưng ngôn ngữ học thực sự: kiểm tra sự tồn tại của từ nghi vấn / chỉ định (Interrogative / Demonstrative Pronouns) kết hợp phân tích tương đồng ngữ nghĩa vector.

---

### MỤC 3: TOÀN BỘ HARDCODE REGEX / TỪ KHÓA / KEYWORD LIST TRONG BA FILE

#### 1. Bằng chứng mã nguồn chi tiết từng file

##### A. Trong [app/services/chat_graph.py](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py)
- **[L97](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L97):** `if s.startswith("#include") or s.startswith("using namespace"):`  
  - So khớp tiền tố chuỗi thô trong fallback làm sạch AST.
- **[L113](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L113):** `if decl and b"main" in decl.text:`  
  - So khớp byte chuỗi cứng `b"main"` trong Tree-sitter declarator.
- **[L119](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L119):** `not (c.type == "return_statement" and b"0" in c.text)`  
  - Kiểm tra byte chuỗi cứng `b"0"` trong lệnh return.
- **[L140](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L140):** Văn bản thông báo tiếng Việt nhúng cứng trực tiếp trong hàm:  
  `"[LƯU Ý: Không tìm thấy tài liệu bài giảng nào vượt qua ngưỡng tin cậy...]"`
- **[L153-L156, L161](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L153):** Chuỗi template định dạng context:  
  `"[MÃ NGUỒN BÀI GIẢNG THAM KHẢO - ĐÂY KHÔNG PHẢI CODE CỦA HỌC VIÊN]"`, `"[Video Bài {lesson_seq} - {tag}]:"`.
- **[L200-L203](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L200):** Văn mẫu phản hồi chuyển bài hardcode toàn phần:  
  `"Đã rõ! Mình đang chuyển bạn sang **Bài {target_seq}** tại mốc **{target_lbl}** để bạn theo dõi video bài giảng ngay nhé! 🎬"`
- **[L233](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L233):** Ký tự phân cách ghép câu hardcode: `f"{last_user_query} -> {raw_prompt}"`.
- **[L282](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L282):** Ghép chuỗi khoảng trắng đơn giản: `f"{last_user_query} {raw_prompt}"`.
- **[L404-L405](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L404):** Câu hỏi gợi mở chỉ thị đàm thoại hardcode trong prompt:  
  `""Bạn có muốn mình chuyển sang Bài {target_lesson_seq} và mở ngay đoạn video này cho bạn không?""`
- **[L475](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L475):** Kiểm tra dấu markdown code block: `"```" in content`.
- **[L487](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L487):** Chuỗi thay thế hardcode: `"[...khung code minh họa ở lượt trước...]"`.
- **[L515-L519](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L515):** Khối chỉ dẫn sư phạm hardcode cho lượt > 6.
- **[L638](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L638):** Định dạng tóm tắt tiến trình hội thoại hardcode.

##### B. Trong [app/services/telemetry_critic.py](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py)
- **[L85](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py#L85):** `any(line.strip().startswith("#") and "include" in line for line in code.splitlines())`  
  - Heuristic thô kiểm tra `#` và `include`.
- **[L86](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py#L86):** `any("main(" in line.replace(" ", "") for line in code.splitlines() if not line.strip().startswith("//"))`  
  - Xóa khoảng trắng và tìm chuỗi con `main(` kèm bỏ qua comment `//`.
- **[L160](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py#L160):** `has_question = "?" in response_text`  
  - **Heuristic siêu ngây thơ:** Chỉ kiểm tra sự tồn tại của dấu chấm hỏi `?` trong toàn bộ văn bản phản hồi để kết luận có tuân thủ phương pháp gợi mở Socratic hay không! Bất kỳ câu văn nào có dấu hỏi (kể cả câu tu từ vô nghĩa) đều được tính điểm; ngược lại một câu chỉ dẫn định hướng tư duy sâu sắc nhưng kết thúc bằng dấu chấm sẽ bị trừ 10 điểm!
- **[L38-L54](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py#L38):** Gắn cứng tên thẻ XML `"timestamp"` và thuộc tính `"sec"`.

##### C. Trong [app/agent/router.py](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py)
- **[L30-L77](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L30-L77):** 7 hằng số phản hồi trực tiếp hardcode toàn phần trong mã nguồn Python:
  - `GREETING_RESPONSES` (L30-34)
  - `GRATITUDE_RESPONSES` (L36-40)
  - `GOODBYE_RESPONSES` (L42-46)
  - `IDENTITY_RESPONSES` (L48-57) - Ghi cứng tên sinh viên, trường, repo github, thông số công nghệ!
  - `SOCRATIC_PEDAGOGY_RESPONSES` (L59-64)
  - `ADVICE_RESPONSES` (L66-71)
  - `OFFTOPIC_CASUAL_RESPONSES` (L73-77)
  Vi phạm nghiêm trọng nguyên tắc **Data/Code Separation Invariant** quy định trong `AGENTS.md`.
- **[L109, L226](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L109):** Hardcode danh sách nhãn lớp: `["chit_chat", "course_query", "out_of_scope"]`.
- **[L175](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L175):** `is_question_punct = prompt.strip().endswith("?")`  
  - Dùng dấu hỏi cuối câu để loại trừ phản hồi đồng ý chuyển bài.
- **[L182](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L182):** Chuỗi mẫu tiền đề NLI cứng:  
  `f"Trợ giảng hỏi: 'Bạn có muốn mình chuyển sang bài học tiếp theo và mở video cho bạn không?'. Học viên trả lời: '{prompt}'."`
- **[L185](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L185):** Danh sách nhãn ứng viên NLI cứng:  
  `["đồng ý mở video bài học", "từ chối hoặc đặt câu hỏi khác"]`
- **[L186](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L186):** Chuỗi template giả thuyết NLI cứng: `"Ý định của học viên là {}."`
- **[L191](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L191):** So khớp chuỗi chính xác với nhãn: `top_lbl == "đồng ý mở video bài học"`.

#### 2. Đánh giá Mức độ Nghiêm trọng & Tác động
- **Mức độ nghiêm trọng:** **HIGH (Vi phạm tính độc lập dữ liệu & Chuẩn mực Clean Code)**.
- **Tác động:** Khi cần cập nhật nội dung phản hồi, bổ sung ngôn ngữ, hoặc tinh chỉnh prompt, buộc phải chỉnh sửa mã nguồn cốt lõi; tạo rủi ro hồi quy (regression) và khó bảo trì trong môi trường Production.

#### 3. Hướng khắc phục tổng quát
- Di chuyển toàn bộ các mẫu phản hồi tĩnh và nhãn NLI candidate labels vào `router_intent_manifest.json` theo đúng triết lý Data-Driven.
- Chuẩn hóa việc phân tích câu hỏi gợi mở trong `telemetry_critic.py` bằng mô hình phân loại câu hỏi (Sentence-level Question Classifier) hoặc phân tích cú pháp mệnh đề thay vì kiểm tra ký tự `?`.

---

### MỤC 4: CƠ CHẾ CHẤM ĐIỂM ẢO TRONG `telemetry_critic.py` (SELF-FLATTERY SCORING TRAP)

#### 1. Bằng chứng mã nguồn thực tế
Trích dẫn trực tiếp từ [app/services/telemetry_critic.py#L186-L203](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py#L186-L203):

```python
# app/services/telemetry_critic.py L186-L203
# 3. Đánh giá Router & CRAG
if used_fast_path:
    merits.append(f"Kích hoạt Fast-Path thành công (< {total_ms}ms), tối ưu tài nguyên và độ trễ phản hồi.")

# Tính điểm lượt này (0 - 100)
score = 100
if has_main_in_long_code:
    score -= 40
if has_include_in_long_code:
    score -= 20
if unverified_ts:
    score -= 15
if not has_question and intent == "course_query":
    score -= 10
if ttft_ms > 4000 and not used_fast_path:
    score -= 10
score = max(0, min(100, score))
```

Và xếp loại tổng thể toàn phiên tại [app/services/telemetry_critic.py#L278-L286](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py#L278-L286):
```python
if avg_score >= 90:
    rating_label = "XUẤT SẮC (SOTA PRODUCTION QUALITY)"
    rating_badge = "🟢"
elif avg_score >= 75:
    rating_label = "ĐẠT CHUẨN SƯ PHẠM (GOOD COMPLIANCE)"
    rating_badge = "🟡"
else:
    rating_label = "CẦN TINH CHỈNH (NEEDS TUNING)"
    rating_badge = "🔴"
```

#### 2. Cơ chế hình thành hiện tượng "Tự Nịnh" (Self-Flattery Scoring Trap)
1. **Thiết kế xuất phát điểm 100 tuyệt đối (Default Optimism):**  
   Hàm `analyze_turn` mặc định gán `score = 100`. Tất cả các điều kiện sau đó chỉ là kiểm tra trừ điểm thụ động về mặt hình thức (syntax code và timestamp).
2. **Miễn trừ toàn diện cho lỗi Router:**  
   - Khi một câu hỏi học tập nghiêm túc bị phân loại sai thành `chit_chat` do bẫy Catch-22 (ví dụ: *"cụ thể là ở bài mấy"*):
     - Không sinh code $ightarrow$ Không bị phạt 40 hay 20 điểm.
     - Không có timestamp $ightarrow$ Không bị phạt 15 điểm.
     - `intent != "course_query"` $ightarrow$ Điều kiện L198 không thỏa mãn, **không bị phạt 10 điểm** vì thiếu câu hỏi gợi mở!
     - `used_fast_path == True` (do phát văn mẫu) $ightarrow$ Điều kiện L200 không thỏa mãn, **không bị phạt độ trễ**!
     - **NGHỊCH LÝ ĐỈNH ĐIỂM TẠI L187-L188:** Hệ thống còn cộng thêm lời khen ngợi (Merit): *"Kích hoạt Fast-Path thành công (< 1260ms), tối ưu tài nguyên và độ trễ phản hồi"*!
3. **Kết quả:**  
   Lượt hội thoại bị lỗi nghiêm trọng nhất lại đạt **100/100 điểm tuyệt đối**! Toàn bộ phiên đối thoại bị phá vỡ hoàn toàn vẫn được trao nhãn **🟢 XUẤT SẮC 99-100/100 (SOTA PRODUCTION QUALITY)**.

#### 3. Bằng chứng thực nghiệm đối chiếu từ Log thực tế
Kiểm tra tệp nhật ký kiểm toán thực tế [logs/playground_debug/session_session_d4tvabbbmw97bb90_20261109_185357_critique.md](file:///D:/In_Course_Agentic_RAG_Copilot/logs/playground_debug/session_session_d4tvabbbmw97bb90_20261109_185357_critique.md):
- **Lượt #1:** *"tôi muốn học các thuật toán về các hàm sắp xếp thì ở bài mấy"* $ightarrow$ Đạt 100/100 (Xử lý đúng).
- **Lượt #3:** Học viên hỏi tiếp *"cụ thể là ở bài mấy trong khóa học"* $ightarrow$ Router đoán sai thành `chit_chat` $ightarrow$ Trả lời chào hỏi $ightarrow$ **Điểm: 100/100** (Khen Fast-Path 1260ms).
- **Lượt #4:** Học viên ức chế hỏi *"??* $ightarrow$ Router đoán `chit_chat` $ightarrow$ **Điểm: 100/100** (Khen Fast-Path 1017ms).
- **Lượt #5:** Học viên hỏi lại trong tuyệt vọng *"cụ thể là bài nào ở trong khóa học"* $ightarrow$ Router đoán `chit_chat` $ightarrow$ **Điểm: 100/100** (Khen Fast-Path 1184ms).
- **Lượt #7:** Học viên hỏi *"nội dung trong đó có những gì"* $ightarrow$ Router đoán `chit_chat` $ightarrow$ **Điểm: 100/100** (Khen Fast-Path 2549ms).
- **ĐÁNH GIÁ TỔNG THỂ PHIÊN:** **🟢 XUẤT SẮC 99/100 (SOTA PRODUCTION QUALITY)**!

#### 4. Đánh giá Mức độ Nghiêm trọng & Tác động
- **Mức độ nghiêm trọng:** **CRITICAL (Gian lận đo lường / Vi phạm Luật Goodhart)**.
- **Tác động:** Tạo ra bức màn che giấu sự thật mù quáng cho đội ngũ phát triển; vô hiệu hóa toàn bộ cơ chế giám sát chất lượng (Observability & Telemetry); đánh mất hoàn toàn độ tin cậy của bài báo cáo khoa học khi nghiệm thu.

#### 5. Hướng khắc phục tổng quát (Zero Quick-Fix Standard)
- **Xóa bỏ lời khen mù quáng:** Tuyệt đối không khen Fast-Path nếu phiên đang ở trong mạch thảo luận chuyên môn.
- **Cơ chế Thẩm Định Tính Hợp Lý Ý Định (Intent Transition & Conversational Coherence Audit):**
  - Trong `analyze_turn`: Xây dựng ma trận chuyển trạng thái Markov hợp thức của phiên học tập. Nếu lượt trước là `course_query`, lượt này người dùng hỏi câu hỏi ngắn / câu hỏi làm rõ mà Router lại chuyển đột ngột sang `chit_chat` và trả lời câu chào hỏi: **TRỪ THẲNG TAY 60 - 80 ĐIỂM** cho lượt đó!
  - Bổ sung chỉ số **Greeting Loop Incident Detector**: Trong `analyze_session`, nếu có $\ge 2$ lượt `chit_chat` liên tiếp khi học viên đang đặt câu hỏi trong phiên, đánh sập điểm Health Score toàn phiên xuống dưới 40 điểm (🔴 CẦN TINH CHỈNH KHẨN CẤP).

---

## 3. BẢNG TỔNG MỤC NỢ KỸ THUẬT TOÀN DIỆN (TECHNICAL DEBT INVENTORY)

| Mã Nợ | File & Số Dòng Code | Phân Loại Lỗi | Mức Độ | Tác Động Hệ Thống | Hướng Khắc Phục Tổng Quát |
| :--- | :--- | :--- | :---: | :--- | :--- |
| **DEBT-01** | [app/services/chat_graph.py#L228](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L228) | Structural Logic Flaw (Catch-22) | **CRITICAL** 🔴 | Khóa chết câu hỏi tỉnh lược trong `chit_chat`, phá hủy đàm thoại đa lượt | Triển khai Dual-Track Semantic Evaluation: chỉ chốt chit-chat khi độ tin cậy vector $\ge 0.88$ và độ dài cực ngắn, còn lại bắt buộc đánh giá ngữ cảnh kép |
| **DEBT-02** | [app/services/telemetry_critic.py#L187-L203](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py#L187-L203) | Metric Fraud / Self-Flattery | **CRITICAL** 🔴 | Cho 100/100 và khen thưởng cho câu router đoán sai bét, tạo số liệu giả tạo | Xây dựng Intent Coherence Audit: trừ 70 điểm nếu ngắt mạch học tập sang chào hỏi; phát hiện Greeting Loop đánh sập điểm phiên |
| **DEBT-03** | [app/services/chat_graph.py#L231](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L231) | Magic Number Quick-Fix | **HIGH** 🟠 | `len < 4` loại bỏ 100% câu hỏi nối tiếp tự nhiên dài từ 4-10 từ | Loại bỏ hoàn toàn điều kiện độ dài số từ; thay thế bằng đặc trưng ngôn ngữ học (từ nghi vấn/chỉ định) và tương quan vector |
| **DEBT-04** | [app/agent/router.py#L30-L77](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L30-L77) | Data/Code Coupling | **HIGH** 🟠 | Ghi cứng 7 văn mẫu phản hồi tĩnh đồ sộ trực tiếp trong mã nguồn Python | Chuyển toàn bộ chuỗi phản hồi vào `router_intent_manifest.json` theo chuẩn Data-Driven |
| **DEBT-05** | [app/services/telemetry_critic.py#L142-L154](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py#L142-L154) | Heuristic Blindspot | **HIGH** 🟠 | `num_lines > 10` tạo lỗ hổng cho phép bỏ lọt mã nguồn giải bài hộ $\le 10$ dòng | Kiểm tra AST Tree-sitter trên mọi khối code Markdown không phân biệt số dòng; phân tích cấu trúc hàm và câu lệnh hoàn chỉnh |
| **DEBT-06** | [app/agent/router.py#L179](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L179) | Magic Number Quick-Fix | **MEDIUM** 🟡 | `len >= 2` loại bỏ các phản hồi xác nhận đơn âm tự nhiên (*"ừ"*, *"có"*, *"ok"*) | Bỏ điều kiện độ dài; tối ưu hóa không gian vector prototype xác nhận cho các từ đơn âm |
| **DEBT-07** | [app/services/telemetry_critic.py#L160](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/telemetry_critic.py#L160) | Naive String Matching | **MEDIUM** 🟡 | Kiểm tra chuỗi `? in response_text` để chấm điểm sư phạm Socratic | Sử dụng bộ phân loại câu hỏi sư phạm (Pedagogical Question Verifier) dựa trên ngữ nghĩa câu cuối |
| **DEBT-08** | [app/services/chat_graph.py#L455-L465](file:///D:/In_Course_Agentic_RAG_Copilot/app/services/chat_graph.py#L455-L465) | Hardcoded Resource Caps | **MEDIUM** 🟡 | Cố định `SLIDING_WINDOW_TURNS=5`, `MAX_HISTORY_CHARS=2400` trong code | Đưa toàn bộ tham số ngân sách ngữ cảnh vào `app/config.py` để đồng bộ với Physical Context Window |
| **DEBT-09** | [app/agent/router.py#L182-L186](file:///D:/In_Course_Agentic_RAG_Copilot/app/agent/router.py#L182-L186) | Hardcoded NLI Templates | **LOW** 🟢 | Ghi cứng premise và candidate labels của NLI trong logic hàm | Nạp toàn bộ template và labels từ manifest metadata JSON |

---

## 4. KẾT LUẬN & CHỈ THỊ HÀNH ĐỘNG CHO NHỊP 1B

Thanh tra Kiểm toán độc lập khẳng định: **Toàn bộ 4 nhóm vấn đề nêu trên là khuyết tật kiến trúc cấu trúc (Structural Architectural Defects), không phải là lỗi ngẫu nhiên cá biệt.**

Mọi nỗ lực giải quyết bằng cách:
- Thêm regex `if 'bài mấy' in query:`
- Tăng ngưỡng ma thuật từ `< 4` lên `< 8`
- Điều chỉnh trọng số điểm số để che giấu lỗi

...đều bị coi là **hành vi gian lận kỹ thuật và vi phạm nghiêm trọng phương pháp luận PSTACK**.

Chỉ thị cho Nhịp 1B (`@rag-architect`, `@core-coder`):
1. **Thiết kế lại luồng phân loại ý định đa lượt (Context-Aware Intent Classification)** theo mô hình toán học tổng quát, triệt tiêu 100% bẫy Catch-22 tại L228.
2. **Cải tổ toàn diện bộ kiểm toán `telemetry_critic.py`**: Xóa bỏ hiện tượng tự nịnh, bổ sung bộ phát hiện đứt gãy luồng hội thoại (Conversational Hijacking) và Greeting Loop Incident Detector.
3. **Chuẩn hóa toàn bộ tham số vào tệp cấu hình**: Xóa bỏ hoàn toàn số ma thuật `len < 4`, tách dữ liệu phản hồi ra khỏi code logic.

---
*Báo cáo được lập ngày 09/11/2026 bởi Subagent Codebase Auditor - Thanh Tra Kiểm Toán & Diệt Quick-Fix.*
