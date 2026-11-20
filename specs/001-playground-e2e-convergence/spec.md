# Unified E2E Spec: `001-playground-e2e-convergence`

- **Ngày lập / Phiên bản:** `2026-11-20` (v2 — đã tích hợp phản biện Red-Team `#96` và thực nghiệm hiệu chuẩn `task-112`)
- **Tác giả Spec:** `coder-2` (Proposer & Spec-Driven Implementer — Mode B)
- **Trạng thái:** `VERIFIED` *(đã qua Red-Team Debate `#96`/`#99`, Audit code `#110`/`#117` `[approved]`, **86/86 pytest** sau bản sửa cuối, **22/22 LIVE E2E**, và **5/5 LIVE PC Replay**)*
- **Phạm vi tác động (Layers):** `[x] Manifest/Data` `[x] Transcripts/Qdrant` `[x] Router` `[x] Curriculum` `[x] Retrieval` `[x] ChatGraph/CRAG` `[x] ContextAssembly` `[x] StreamGuardrail` `[x] TelemetryCritic` `[ ] Frontend`

---

## 1. Constitution Check (`AGENTS.md` & Rigor Invariants)
- [x] **Zero Quick-Fix:** Mọi bản sửa xử lý đúng *Lớp bài toán (Problem Class)* tổng quát: (a) truy vấn tìm mốc/phân đoạn video dạng nghi vấn 2 khe (position WH + lecture verb) tại `router_node Bước 3b`, (b) câu nối tiếp đào sâu ngắn không có `?` kèm **Recency Gate** (`last_turn_intent == "course_query"`), (c) điều hướng gõ thiếu dấu thanh hiệu chuẩn thực nghiệm (`12` pos vs `12` neg) + `last_offered_lessons` có cấu trúc + kiểm chứng biên số bài học động từ manifest + sửa lỗi đồng âm ASR L1 trực tiếp tại tầng dữ liệu (`lesson-01_chunks.json` + Qdrant re-upsert), (d) câu hỏi ẩn dụ/xác nhận bị LLM 7B nhại lại 1 câu rỗng, (e) mệnh đề loại trừ thực sự (`ngoài bài`/`trừ bài`/`không tính bài`/`bên cạnh bài`) + rò rỉ `code_ast` điểm thấp `< 0.35` khác bài + câu kết sáo rỗng + nhãn footer `📍`. Tuyệt đối không hardcode regex/từ khóa cho câu test mẫu.
- [x] **Zero Fake Fallback:** Không bịa văn bản/câu hỏi giả che lỗi model; khi LLM 7B phát echo-only 1 câu trên ngữ cảnh `grounded`, chỉ chạy tối đa 1 lượt continuation trực tiếp qua cùng `StreamingOutputPipeline` dựa trên `retrieved_chunks`; nếu continuation lỗi/timeout/offline, không bịa thêm nội dung và gắn cờ telemetry `is_echo_only=True`.
- [x] **Static Prefix Cache (`messages[0]`):** Giữ `messages[0]` tĩnh 100% theo từng system prompt (`SOCRATIC_GROUNDED_PROMPT`, `OUT_OF_LESSON_PROMPT`, `CURRICULUM_OVERVIEW_PROMPT`, `COVERAGE_GAP_PROMPT`). Chỉ thêm đúng 1 câu tĩnh trong `SOCRATIC_GROUNDED_PROMPT` cấm lặp lại câu hỏi học viên làm câu trả lời; mọi chỉ thị theo lượt (ẩn dụ, tập trung lượt) chỉ tiêm vào `user_message_content`.
- [x] **Data/Code Separation:** Toàn bộ signature/prototype/khung 2 khe/cụm loại trừ/câu kết sáo rỗng/bảng thuật ngữ đặt trong JSON manifests (`data/metadata/router_intent_manifest.json`, `data/metadata/cpp_academic_glossary.json`, `data/curriculum/lessons_manifest.json`); không hardcode số `83` trong code hay thông báo.
- [x] **No "Qua Mặt" Model Swaps:** Kiểm chuẩn live E2E chạy đúng `LLM_MODEL_NAME` trong `.env` với `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` tuần tự.

---

## 2. Chẩn đoán Nguyên nhân Gốc E2E (Root-Cause & Problem Classes)

### Problem Class PC-01: Truy vấn tìm mốc/phân đoạn video dạng nghi vấn bị định tuyến nhầm sang `chit_chat` (`identity_architecture`)
- **Bằng chứng thực tế (Log / Trace #94 & `task-89`):**
  - `logs/playground_debug/session_session_le0ib7e9mwn86374_20261119_142753.json` Turns 6, 7, 9 (`cpp-oop` L57): `"khoảng phút bao nhiêu thì nói về lý thuyết"` -> `intent="chit_chat"`, `used_fast_path=True`, trả `IDENTITY_RESPONSES`, `turn_score=20`, `overall_health_score=35` (`GREETING LOOP`).
  - Trace `#94` & `task-89`: `IntentRouter().classify("khoảng phút bao nhiêu thì nói về lý thuyết")` -> `slm_probs`: `chit_chat=0.9719, course_query=0.0183, out_of_scope=0.0098`; `nli_vid=(True, off_topic=0.2741)`. Tương tự `"phút mấy nói về con trỏ"` -> `chit_chat=0.8197, nli_vid=(True, 0.2763)`. Đối chứng `"bạn được tạo ra lúc nào"` (identity) không chứa khe vị trí video/động từ bài giảng.
- **Vết thực thi & Nguyên nhân gốc:**
  1. `IntentRouter.classify` (vẫn giữ là pure ML, KHÔNG thêm NLI vào bên trong `classify()` để tránh tăng độ trễ vòng lặp history tại `chat_graph.py:302`) xếp các câu hỏi tìm vị trí trong video thiếu từ khóa C++ vào `chit_chat`.
  2. `router_node Bước 3b` (`app/services/chat_graph.py:458-482`) chỉ kích hoạt khi `extract_video_time_reference` != `None` (`phút <số>`), bỏ sót lớp **Interrogative In-Video Section/Timestamp Seeking Queries** (`phút bao nhiêu`, `phút mấy`, `đoạn nào nói về...`).
  3. `crag_grader_node` (`app/services/chat_graph.py:909-914`) thiếu `"phút bao nhiêu"`, `"giây bao nhiêu"` trong `section_markers` nên không tiêm `[MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI]`.

### Problem Class PC-02: Câu hỏi nối tiếp đào sâu ngắn không có `?` (`"chi tiết hơn"`) bị định tuyến nhầm sang `out_of_scope`
- **Bằng chứng thực tế (Log / Trace #94 & `task-89`):**
  - `logs/playground_debug/session_session_7ztumoqfmwn8a8no_20261119_143313.json` Turns 3->4 (`cpp-oop` L57): Turn 3 `"đoạn này đang khai báo gì"` (`intent="course_query"`, mốc `315s`) -> Turn 4 `"chi tiết hơn"` -> `intent="out_of_scope"`, `used_fast_path=True`.
  - `task-89`: `is_context_dependent("chi tiết hơn", "đoạn này đang khai báo gì") == False`; khi ghép `"đoạn này đang khai báo gì -> chi tiết hơn"`, `CTX SLM = [0.2122, 0.7480, 0.0398]` (`P_course_ctx=0.7480 >= 0.35`, không cần gọi NLI).
- **Vết thực thi & Nguyên nhân gốc:**
  1. `IntentRouter.is_context_dependent` (`app/agent/router.py:614-641`) chỉ bắt đại từ hồi chỉ hoặc câu `<= 7 từ` kết thúc bằng `'?'`, bỏ sót câu yêu cầu đào sâu ngắn không dấu `?`.
  2. `router_node` (`chat_graph.py:490`) giữ `last_course_query` xuyên qua các lượt `out_of_scope`/`chit_chat` mà không có **Recency Gate**: nếu không kiểm tra ý định lượt liền trước (`last_turn_intent == "course_query"`), một câu `T1: con trỏ -> T2: nấu mì 5 phút (OOS) -> T3: giải thích thêm` sẽ bị cứu nhầm vào neo `T1` đã hết hiệu lực.
  3. `retrieval_node` (`chat_graph.py:579-614`) chạy chuỗi trần `"chi tiết hơn"` trước khi fallback sang `search_query`.

### Problem Class PC-03: Mất trạng thái điều hướng (`bai` thiếu dấu + `pending_navigation` / `competing_lessons`) + biên số bài học + nhiễu ASR L1 `"mạng"`
- **Bằng chứng thực tế (Log / Trace #94, `task-89`, `task-112`):**
  - `session_le0ib7e9mwn86374` Turns 3–4 (`cpp-core` L1): `"có bai học nào về con trỏ không"` (`bai` thiếu dấu) cho `router.is_curriculum_navigation = (False, 0.8648)` (kém `0.865` đúng `0.0002`), dẫn đến `allow_cross_course=False` (`retrieval.py:1467`) tìm sai `target_lesson_seq=50` (log) / `38` (`#94`) trong khi LLM lại khuyên `Bài 57 cpp-oop`. Đồng thời `find_ambiguous_candidates` trả `competing_lessons: [57, 48, 79, 64]` khiến `crag_grader_node` (`chat_graph.py:1118`) không lưu thông tin bài đã giới thiệu; Turn 4 `"chuyển cho tôi đến bài đó"` rơi xuống `find_lesson_for_query -> cpp-core L2`.
  - Hiệu chuẩn `task-112` trên **12 câu nav không dấu** vs **12 câu phủ định/nhiễu** (gồm va chạm dấu `"bai bien nao dep"`, `"bai toan nay kho qua"`, `"con cho nha minh bi om"`, `"nau mi mat 5 phut"`):
    - **11/12** câu nav không dấu khớp chữ ký `curriculum_navigation_signatures` khi bỏ dấu thanh (`sigs=['bài học nào']`, `['bài nào']`, `['bài mấy']`, `['bài bao nhiêu']`, `['lộ trình học']`), và `nav_sim` đạt **`0.8221 .. 0.8786`** (12/12 đạt `>= 0.8221`, riêng `"tim bai hoc ve struct"` `0.8483` khớp nếu có `"tìm bài"`).
    - **0/12** câu phủ định/va chạm khớp chữ ký bỏ dấu (`sigs=[]` trên toàn bộ 12/12 câu), và `nav_sim` nằm trong `0.7616 .. 0.8478` với `soc_sim > nav_sim`.
  - Biên số bài học (`curriculum.py:854-886`): `extract_direct_navigation_command("chuyển cho tôi đến bài 999")` trả `999` không kiểm chứng `lessons_manifest.json`.
  - Nhiễu ASR L1: `data/transcripts/cpp-core/lesson-01_01_-_Cách_Tự_Học_Lập_Trình_Cho_Người_Mới/lesson-01_chunks.json` (dòng 16, 24) chứa lỗi phiên âm Whisper `"bài tập về mạng"`, `"bài tập về câu chúc"`, `"lý thiết số"`. Việc sửa runtime sẽ bỏ sót chỉ mục Dense/BM25 trên Qdrant Cloud.

### Problem Class PC-04: Câu hỏi ẩn dụ/xác nhận bị LLM 7B nhại lại 1 câu rỗng lời giải thích (`tờ giấy ghi địa chỉ nhà`)
- **Bằng chứng thực tế (`session_7ztumoqfmwn8a8no` Turns 7–8, Trace #94 & `task-112`):**
  - Trace `#94` tái hiện LIVE trên Qwen 7B ở phiên tươi (`turn_count=1` xác nhận bởi `task-112`): `user_message_content` nhận `[QUY TẮC ĐỊNH DẠNG ĐẦU RA BẮT BUỘC]` (chứ KHÔNG phải `SOFT_NUDGE` vì `turn_count=1 <= 6`!). Chỉ thị này nhấn mạnh `"câu văn cuối cùng trước thẻ <timestamp> BẮT BUỘC là đúng 1 câu hỏi..."`, kết hợp transcript L57 chứa lỗi ASR (`"petero"`, `"peterer"`) và không chứa cụm ẩn dụ đời sống, khiến Qwen 7B nhại lại đúng 1 câu hỏi của học viên (`"Ví dụ con trỏ giống như tờ giấy ghi địa chỉ nhà có đúng không?"`).
  - Ở tầng stream (`app/services/chat.py:1014-1278`), `StreamingSocraticFooterGuard` chỉ kiểm tra `"?" in tail` qua `has_trailing_socratic_question`, nên thấy dấu `?` của chính câu nhại và cho qua toàn bộ phản hồi rỗng giải thích.

### Problem Class PC-05: Điều hướng đa chủ đề có mệnh đề loại trừ (`"ngoài bài 57..."`) + rò rỉ `code_ast` khác bài điểm thấp (T9) + câu kết cấm + lỗi nhãn `📍`
- **Bằng chứng thực tế (Log / Trace #94 & `task-112`):**
  - **PC-05a (Turn 10 `7ztum` & Trace `#94`):** `_extract_lesson_seq` (`curriculum.py:839-851`) trả `57` cho `"ngoài bài 57..."` -> `find_lesson_for_query` (line 951) trả L57, `find_ambiguous_candidates` (line 1177) thoát sớm `empty_res`, `RetrievalService.search` (line 1353) khóa `focused_lesson_seq=57`. `task-112` xác nhận khi không có `explicit_seq`, `IntentRouter.is_curriculum_navigation("ngoài bài 57...")` vẫn đạt `True` (`nav_sim=0.8853 >= 0.875`).
  - **PC-05b (Turn 9 `7ztum` lines 1043–1056):** `eligible_code_items` (`retrieval.py:1795-1800, 2047-2051`) cho phép `code_ast` điểm `< 0.35` (`>= 0.15`) bất kể `lesson_seq` và `BOILERPLATE_SCOPES`, làm lọt `L54 function_main` (`0.1711`) vào câu trả lời L57.
  - **PC-05c (Forbidden closers):** Turn 2 `le0ib` (`"Bạn có câu hỏi gì liên quan đến nội dung này?"`), Turn 5 `7ztum` (`"Bạn đã hiểu đúng không?"`), Turn 9 `7ztum` (`"Bạn hiểu được điều này chưa?"`). Lưu ý: `"Bạn có muốn biết thêm chi tiết về cách sử dụng iterator với vector hay tìm kiếm nhị phân không?"` ở Turn 10 là **câu hỏi lựa chọn đúng chuẩn REQ-07**, không được phép liệt vào closer cấm.
  - **PC-05d (`📍` label hygiene):** Turn 5 `7ztum` thiếu nhãn `📍 **Mốc video bài giảng:**` trước `<timestamp>` cuối dòng; ngược lại khi `valid_secs` rỗng hoặc mọi tag bị strip, luồng SSE có thể phát sớm `"📍 **Mốc video bài giảng:** "` trơ trọi.

---

## 3. Hợp đồng Hành vi End-to-End (E2E Behavioral Contract)

| ID | Lớp đầu vào / Ngữ cảnh | Tầng 1: `IntentRouter` / `router_node` | Tầng 2: `Curriculum / Retrieval` | Tầng 3: `CRAG / ContextAssembly` | Tầng 4: `LLM / StreamGuardrail` | Điều kiện PASS |
|---|---|---|---|---|---|---|
| `REQ-01` | **PC-01**: Câu hỏi 2 khe tìm mốc/phân đoạn video (`"khoảng phút bao nhiêu thì nói về lý thuyết"`, `"phút mấy nói về con trỏ"`) | `router_node Bước 3b` kiểm `is_video_section_seeking_query` (2 khe) & không phải `is_curriculum_nav` / `_names_other_lesson_topic` & `verify_in_video_temporal_query` `< 0.60` off-topic -> `course_query` (`classify()` vẫn giữ pure ML) | `is_curriculum_navigation=False`, truy xuất L57 (`grounded`) | Bơm `[NGỮ CẢNH BÀI GIẢNG]` + `[MỤC LỤC PHÂN ĐOẠN VIDEO BÀI HIỆN TẠI]` | Trả lời thẳng mốc lý thuyết L57 + 1 câu hỏi Socratic + `📍` `<timestamp lesson="57">` | Không rơi vào `chit_chat`/`IDENTITY_RESPONSES`; `"bạn được tạo ra lúc nào"` vẫn vào `identity_architecture`; `"phút thứ 6 trận bóng đá..."` vẫn `out_of_scope` |
| `REQ-02` | **PC-02**: Follow-up đào sâu ngắn không `?` (`"chi tiết hơn"`, `"cụ thể hơn"`) sau lượt `course_query` (`last_turn_intent == "course_query"`) | `is_context_dependent=True` (residual-empty) + Recency Gate đạt -> `classify_contextual` -> `course_query` (`search_query` giữ neo, 0 NLI thêm) | `retrieval_node` dùng `search_query` & kế thừa `last_video_sec` cho pure follow-up -> `grounded` đúng đoạn đang học | Giữ lịch sử `t-1` (`abs(delta) < 45s`) | Giải thích chi tiết + câu hỏi Socratic mới + `<timestamp>` | `intent="course_query"`, `is_topic_intruded=False`; sau lượt OOS (`T1: con trỏ -> T2: nấu mì 5 phút -> T3: giải thích thêm`) KHÔNG cứu vào `T1`; `"nấu mì chi tiết hơn"` -> `out_of_scope` |
| `REQ-03` | **PC-03a**: Điều hướng có lỗi thiếu dấu (`"có bai học nào về con trỏ không"`) -> tiếp nối `"chuyển cho tôi đến bài đó"` | L1: `is_curriculum_navigation=True` (chữ ký bỏ dấu + topic guard + `nav_sim>=0.82`). L2: anaphoric nav đọc `last_offered_lessons` (structured state) | L1: `NavBypass` cross-course -> `out_of_lesson` (không khóa `cpp-core` L38/50). L2: skip retrieval nếu `len==1` hoặc trả danh sách rõ ràng nếu `len>1` | Lưu `last_offered_lessons` (chỉ các bài thực sự đưa vào prompt); chỉ gán `pending_navigation` khi `len == 1` | L2: nếu `len==1` -> `confirm_navigation` + `action.navigate_and_seek`; nếu `len>1` -> liệt kê đúng danh sách `last_offered_lessons` từ manifest để học viên chọn (0 đoán bừa, 0 fallback L2) | L1 không trả L38/50; L2 không bao giờ rơi về L2; kiểm chứng bằng `last_offered_lessons` thực tế |
| `REQ-04` | **PC-03b**: Mệnh lệnh chuyển bài có số bài ngoài manifest (`"chuyển cho tôi đến bài 999"`, `"mở bài 0"`) | `router_node` kiểm tra `extract_requested_nav_seq_raw` so `get_lesson_by_seq(seq) is None` -> Fast-Path từ chối lịch sự | Skip retrieval | Không ghi đè `last_lesson_seq` | Nêu rõ phạm vi bài học thực tế đọc động từ manifest (không hardcode `83`) và hỏi lại số bài hợp lệ | `action is None`, `target_lesson_seq is None`, không có `"đang chuyển bạn sang Bài 999"` |
| `REQ-05` | **PC-03c**: L1 transcript `"mạng"` / `"câu chúc"` / `"lý thiết số"` | `intent="course_query"` | Dữ liệu `lesson-01_chunks.json` + Qdrant Cloud đã chuẩn hóa qua `canonicalize_transcripts_ast.py` (`"mảng"`, `"cấu trúc"`, `"lý thuyết số"`) | `get_academic_glossary_prompt_extension` khớp cả `forbidden_translations` (boundary check) | Câu trả lời L1 T2 dùng đúng `"mảng"`, `"cấu trúc"` | Xác thực `grep` trên `lesson-01_chunks.json` & Qdrant scroll L1 không còn `"bài tập về mạng"` / `"câu chúc"` |
| `REQ-06` | **PC-04**: Câu hỏi 2 khe ẩn dụ/xác nhận (`"...giống như tờ giấy ghi địa chỉ nhà có đúng k"`) | `intent="course_query"` | `grounded` L57 | `user_message_content` tiêm `[CHỈ THỊ ĐÁNH GIÁ MỆNH ĐỀ / ẨN DỤ]` (`messages[0]` giữ tĩnh 100%); sửa wording cả `[QUY TẮC ĐỊNH DẠNG ĐẦU RA BẮT BUỘC]` & `SOFT_NUDGE` | Giữ footer `📍`; nếu LLM vẫn phát echo-only (`has_trailing_socratic_question` bỏ qua `?` trùng prompt), chạy tối đa 1 lượt continuation qua cùng pipeline trước khi xả `📍`. Nếu continuation lỗi: không bịa text, gắn `is_echo_only=True` | Phản hồi có đánh giá + giải thích C++ + câu hỏi Socratic MỚI + `📍` đúng 1 lần; `"cho mình ví dụ về vòng lặp for"` không bị tiêm chỉ thị ẩn dụ |
| `REQ-07` | **PC-05a**: Điều hướng đa chủ đề có loại trừ (`"ngoài bài 57 thì muốn học về vector với iterator hoặc tìm kiếm nhị phân thì xem những bài nào"`) | `is_curriculum_navigation=True` (không dùng `explicit_seq`), `intent="course_query"` | `excluded_seqs={57}`; loại cụm loại trừ trước khi tách nhánh; `find_ambiguous_candidates` ra `multi_topic_disjunction`; `NavBypass` -> `out_of_lesson` | `CURRICULUM_OVERVIEW_PROMPT`, `suggested_timestamps=[]`, `pending_navigation=None`, lưu `last_offered_lessons` | Liệt kê đủ các bài Vector & Tìm kiếm nhị phân + câu hỏi lựa chọn (giữ nguyên `"Bạn có muốn..."`), **0** `<timestamp>` L57, **0** `📍` | `suggested_timestamps=[]`, không có `<timestamp lesson="57">`; `"sau bài 20 thì học gì"` & `"bài này khác bài 11 chỗ nào"` vẫn giữ `20`/`11` |
| `REQ-08` | **PC-05b/c/d**: T9 L57 vs L54 `code_ast` (`0.1711`) + closer sáo rỗng + nhãn `📍` | `intent="course_query"` | Chỉ cho phép `code_ast` `0.15..0.35` khi **cùng `current_lesson_seq`** (giữ nguyên `code_ast >= 0.35` hợp lệ như L50 struct `0.40` và đồng truy xuất ví dụ trong `main()` ở bài nhập môn như L2) | Không có L54 `0.1711` trong sources/timestamps | Prefix-hold buffer lọc chỉ câu kết sáo rỗng thuần túy (giữ `"bạn có muốn..."`); footer `📍` giữ cho đến khi có `>=1` `<timestamp>` hợp lệ; auto-label chỉ trên dòng chỉ chứa `<timestamp>` | `all(s["lesson_seq"]==57)`, L50 `>=0.35` không bị mất, L2 `function_main >= 0.15` cùng bài được giữ, không lọt closer sáo rỗng/nhãn `📍` rỗng, `test_p0_stream_chat_no_duplicate_footer` pass |

---

## 4. Đặc tả Sửa đổi Theo Thứ tự Phụ thuộc (Dependency-Ordered Changes)

1. **Lớp 1 — Manifest & Data (`data/metadata/router_intent_manifest.json`, `data/metadata/cpp_academic_glossary.json`, `data/transcripts/cpp-core/lesson-01_...` + Qdrant Cloud):**
   - `router_intent_manifest.json`:
     - `follow_up_elaboration_signatures`: `["chi tiết hơn", "cụ thể hơn", "rõ hơn", "sâu hơn", "kỹ hơn", "giải thích thêm", "nói thêm", "nói rõ hơn", "ví dụ thêm", "ví dụ cụ thể", "tiếp đi", "tiếp tục đi", "tại sao vậy", "sao lại thế", "vì sao thế", "ý là sao", "còn gì nữa không"]` *(không lặp `"nghĩa là"` đã có trong `anaphora_signatures`)*.
     - `video_section_seeking_2slot`:
       - `position_wh_phrases`: `["phút bao nhiêu", "phút mấy", "giây bao nhiêu", "giây mấy", "đoạn nào", "phần nào", "khúc nào", "chỗ nào", "mốc nào", "từ phút nào", "tới phút nào"]`
       - `lecture_action_verbs`: `["nói về", "nói đến", "giảng", "dạy", "giải thích", "đề cập", "nhắc tới", "học", "giới thiệu", "viết code", "khai báo", "ví dụ"]`
       *(đồng thời giữ `crag_section_markers` riêng cho `crag_grader_node` khi đã `grounded` gồm `"mục lục"`, `"phân đoạn"`, `"các phần"`, `"mấy phần"`, `"chia thành"`, `"phút bao nhiêu"`, `"phút mấy"`, `"giây bao nhiêu"`, `"giây mấy"`, `"đoạn nào"`, `"phần nào"`, `"khúc nào"`, `"tóm tắt bài"`, `"tóm tắt video"`, `"nội dung video"`, `"cấu trúc bài"`, `"timeline"`, `"chapter"`)*.
     - `curriculum_exclusion_markers`: `["ngoài bài", "trừ bài", "không tính bài", "bên cạnh bài"]` *(KHÔNG đưa `"sau bài"`, `"khác bài"` vào đây)*.
     - `analogy_verification_2slot`:
       - `comparison_markers`: `["giống như", "như là", "tức là", "hiểu là", "ví von"]`
       - `verification_tail_markers`: `["có đúng không", "có đúng k", "đúng không", "đúng k", "phải không", "phải k"]`
     - `forbidden_closing_prefixes`: danh sách các câu kết sáo rỗng thuần túy (`"hy vọng thông tin"`, `"nếu còn thắc mắc"`, `"bạn có câu hỏi gì"`, `"bạn có thêm câu hỏi"`, `"bạn còn câu hỏi"`, `"bạn còn thắc mắc gì"`, `"bạn đã hiểu"`, `"bạn hiểu được"`, `"chúc bạn học tốt"`, `"hãy hỏi nhé"`, ...). **Tuyệt đối KHÔNG đưa `"bạn có muốn"` vào danh sách này.**
     - Bổ sung `"tìm bài"` vào `curriculum_navigation_signatures` (hỗ trợ `"tim bai hoc ve struct"`).
   - `cpp_academic_glossary.json`: bổ sung mục `Struct` (`"Cấu trúc (Struct)"`, `forbidden_translations: ["câu chúc", "cầu chức", "câu trúc"]`).
   - **Data-Layer ASR Canonicalization & Qdrant Sync (PC-03 L1 `"mạng"`):** Sửa các lỗi phiên âm Whisper khách quan trong `data/transcripts/cpp-core/lesson-01_01_-_Cách_Tự_Học_Lập_Trình_Cho_Người_Mới/lesson-01_chunks.json` (`"mạng"`/`"màng"` chỉ nghĩa mảng -> `"mảng"`, `"câu chúc"`/`"cầu chức"` -> `"cấu trúc"`, `"lý thiết số"` -> `"lý thuyết số"`, `"mạng trai"`/`"mạng cha"` -> `"mảng char"`, `"sâu kí tự"` -> `"xâu ký tự"`), chạy `upsert_lesson_chunks_to_qdrant` + `refresh_video_chapters_for_lessons([1])` trong `scripts/canonicalize_transcripts_ast.py`, rồi kiểm chứng trực tiếp bằng `Select-String` và Qdrant `scroll` trên `lesson-01`.

2. **Lớp 2 — Router (`app/agent/router.py`):**
   - **Giữ `IntentRouter.classify()` là pure ML (không gọi NLI trong `top1 == "chit_chat"`).**
   - Trong `is_curriculum_navigation(prompt)`: thêm nhánh đối chiếu `curriculum_navigation_signatures` đã bỏ dấu thanh (`_fold_vietnamese_accents`, Zero Regex) với **đồng thời 3 điều kiện bảo vệ**:
     1. Khớp cụm chữ ký nav bỏ dấu theo ranh giới từ (`f" {folded_sig} " in f" {folded_prompt} "`),
     2. Có tín hiệu chủ đề giáo trình (`self.has_domain_entity(clean_p)` hoặc `get_curriculum_service().semantic_search_lessons(clean_p, top_k=1, min_similarity=0.80)`),
     3. Không phải xã giao/danh tính (`sim_sys < 0.88`, `not is_pure_soc_relaxed` với `not has_domain_entity`, và `max_sim >= 0.82` — đã hiệu chuẩn trên 12 pos `[0.8221..0.8786]` vs 12 neg `0/12` khớp chữ ký).
   - Mở rộng `is_context_dependent(prompt, anchor_query)` kiểm tra `follow_up_elaboration_signatures` khi toàn bộ từ còn lại sau khi loại signature và hư từ lịch sự (`"ạ"`, `"nhé"`, `"đi"`, `"giúp"`, `"mình"`, `"em"`, `"tôi"`, `"được"`, `"không"`, `"thầy"`, `"bạn"`, `"về"`, `"nữa"`) là rỗng hoặc nằm trong `anaphora_signatures`, và `not is_pure_social` / `not is_social_acknowledgment`.

3. **Lớp 3 — Curriculum & Retrieval (`app/services/curriculum.py`, `app/services/retrieval.py`):**
   - `curriculum.py`:
     - Thêm `_extract_lesson_refs(prompt) -> Tuple[List[int], set[int]]` phân tách `included_seqs` và `excluded_seqs` dựa trên `curriculum_exclusion_markers` (`"ngoài bài 57"`, `"trừ bài 57"`, `"không tính bài 57"`, `"bên cạnh bài 57"`). `_extract_lesson_seq(prompt)` trả `included_seqs[0]` nếu có (không trả số bài bị loại trừ). Thêm `extract_excluded_lesson_seqs(prompt)` và helper bỏ cụm loại trừ `_strip_exclusion_clauses(prompt)` trước khi tách nhánh trong `find_ambiguous_candidates` (`curriculum.py:1196`).
     - Thêm `is_video_section_seeking_query(prompt)` kiểm tra mô hình 2 khe từ `video_section_seeking_2slot` (phải có ít nhất 1 `position_wh_phrase` AND ít nhất 1 `lecture_action_verb`, khớp theo ranh giới token).
     - Thêm `get_lesson_seq_bounds() -> Tuple[int, int]` tính động `min(seq), max(seq)` từ `self._all_lessons` (0% hardcode `83`).
     - Thêm `extract_requested_nav_seq_raw(prompt) -> Optional[int]` (bắt số bài trong mệnh lệnh chuyển bài trực tiếp); `extract_direct_navigation_command(prompt)` chỉ trả về `seq` nếu `get_lesson_by_seq(seq)` tồn tại trong manifest!
     - Thêm `extract_anaphoric_navigation_command(prompt) -> bool` (kiểm `action_verbs`, không `?`, không `question_starters`, có `"bài"` + từ chỉ hồi chỉ như `"đó"`, `"này"`, `"đấy"`, `"kia"`, `"vừa rồi"`, `"vừa nói"`, `"trên"`).
     - Trong `find_lesson_for_query` & `find_ambiguous_candidates`: loại trừ `excluded_seqs` khỏi ứng viên cuối; nếu `excluded_seqs` khác rỗng và Dạng 1 (`multi_topic_disjunction`) không kích hoạt thì trả về `empty_res` thay vì rơi vào Dạng 2 (`competing_lessons`), bảo toàn nguyên vẹn nhánh `[DANH MỤC BÀI HỌC THẬT LIÊN QUAN TRONG GIÁO TRÌNH]` cho câu đơn chủ đề như `"ngoài bài 64 ra còn những bài nào dạy về mảng 1 chiều nữa không"`.
   - `retrieval.py`:
     - Trong `search()`: đọc `excluded_seqs = c_svc.extract_excluded_lesson_seqs(query_text)`. Khi `excluded_seqs` khác rỗng, không khóa `focused_lesson_seq` vào `excluded_seqs` và loại trừ `excluded_seqs` khỏi `curriculum_matched_seq` ở `NavBypass`.
     - Tại lines `1801-1812` và `2061-2072` (`eligible_code_items`): CHỈ chấp nhận `code_ast` khi:
       `it.get("confidence_score", 0.0) >= max(effective_code_threshold, settings.MODALITY_GATE_AST_THRESHOLD)` **HOẶC** (`it.get("confidence_score", 0.0) >= 0.15` AND `int(it.get("lesson_seq") or 0) == int(current_lesson_seq)`). *(Giữ nguyên mọi `code_ast >= 0.35` hợp lệ của bài trước như L50 `struct` `0.40`, giữ nguyên đồng truy xuất cùng bài như `function_main` ở L2, và chặn dứt điểm rò rỉ khác bài `< 0.35` như L54 `0.1711` ở L57).*

4. **Lớp 4 — ChatGraph & Prompts (`app/services/chat_graph.py`, `app/agent/prompts.py`):**
   - `prompts.py`:
     - Bổ sung 1 câu tĩnh vào Quy tắc 3 của `SOCRATIC_GROUNDED_PROMPT`: cấm lặp lại nguyên văn câu hỏi học viên làm câu trả lời; khi học viên hỏi ẩn dụ/xác nhận, phải đánh giá rõ + giải thích bản chất C++ 2–3 câu rồi mới đặt 1 câu hỏi Socratic MỚI.
     - Cập nhật `get_academic_glossary_prompt_extension(text)` quét thêm `forbidden_translations` (khớp ranh giới cụm từ/token với `len >= 3` hoặc có khoảng trắng).
   - `chat_graph.py`:
     - Thêm vào `AgentState`: `last_turn_intent: Optional[str]` và `last_offered_lessons: Optional[List[Dict[str, Any]]]`.
     - Trong `router_node`:
       1. Kiểm `requested_seq = curr_svc.extract_requested_nav_seq_raw(raw_prompt)`: nếu `requested_seq is not None` và `curr_svc.get_lesson_by_seq(requested_seq) is None`: trả Fast-Path từ chối lịch sự nêu đúng `min_seq..max_seq` từ `curr_svc.get_lesson_seq_bounds()`, `action=None`, `target_lesson_seq=None`, `last_turn_intent="out_of_scope"`. Nếu hợp lệ -> `confirm_navigation` (`last_turn_intent="confirm_navigation"`, xóa `pending_navigation`/`last_offered_lessons`).
       2. Nếu `pending_nav` có giá trị: `router.check_confirmation(raw_prompt)` **HOẶC** `curr_svc.extract_anaphoric_navigation_command(raw_prompt)` -> `confirm_navigation` tới `pending_nav`.
       3. Nếu `pending_nav` là `None` và `curr_svc.extract_anaphoric_navigation_command(raw_prompt)` là `True`: đọc `offered = state.get("last_offered_lessons") or []`:
          - Nếu `len(offered) == 1`: trả `confirm_navigation` + `action.navigate_and_seek` tới `offered[0]`.
          - Nếu `len(offered) > 1`: trả Fast-Path clarifying liệt kê đúng các bài trong `offered` (theo `lessons_manifest.json`) hỏi học viên muốn chuyển tới bài nào (`action=None`, giữ nguyên `last_offered_lessons`), **không** rơi xuống `find_lesson_for_query -> L2`.
       4. Recency Gate cho `anchor_query` & `classify_contextual`: chỉ kích hoạt `classify_contextual` / context fusion khi `(state.get("last_turn_intent") in (None, "course_query"))` (và nếu `last_turn_intent is None` ở test stateless có `history`, tin nhắn `user` gần nhất không phải `out_of_scope`/`chit_chat`).
       5. Tại `Bước 3b`: `is_section_seeking = c_svc.is_video_section_seeking_query(raw_prompt) and not is_curriculum_nav and not c_svc._names_other_lesson_topic(raw_prompt, state.get("lesson_seq"), state.get("course_id"))`. Nếu `(is_in_video_time_ref or is_section_seeking) and not is_pure_soc` và `p_oos < 0.75` và `verify_in_video_temporal_query` đạt -> cứu sang `course_query` (`last_turn_intent="course_query"`).
       6. Mọi nhánh trả về của `router_node` đều cập nhật `last_turn_intent` tương ứng (`course_query`, `chit_chat`, `out_of_scope`, `confirm_navigation`).
     - Trong `retrieval_node`: khi `not is_curriculum_nav` và `raw_prompt` là pure follow-up (`is_context_dependent` and `not has_domain_entity` and `time_ref is None` and `search_query != raw_prompt`), chạy `search_query` trước (kèm kế thừa `last_video_sec` nếu `search_query` có `deictic_current` và `last_lesson_seq == lesson_seq`).
     - Trong `crag_grader_node`:
       - Mở rộng kiểm tra mục lục video bằng `crag_section_markers` (có `"phút bao nhiêu"`, `"giây bao nhiêu"`).
       - Cập nhật `last_offered_lessons`: khi `is_ambiguous` -> lưu danh sách `ambiguous_res["candidates"]` (cùng mốc đầu từ `get_lesson_timestamps`); khi `retrieval_status == "out_of_lesson"` đơn nghĩa (`not is_ambiguous`, `target_lesson_seq is not None`) -> lưu 1 phần tử `[target_lesson]` và gán `new_pending_nav`; khi `grounded` bình thường -> `last_offered_lessons = []`.
     - Trong `context_assembly_node`:
       - Kiểm tra 2-slot `analogy_verification_2slot` trên ranh giới token (không dùng `"ví dụ"` đơn lẻ, không dùng `"đúng k"` dạng substring) -> tiêm chỉ thị đánh giá mệnh đề/ẩn dụ vào `user_message_content`.
       - Sửa wording `[QUY TẮC ĐỊNH DẠNG ĐẦU RA BẮT BUỘC]` và `SOFT_NUDGE`: yêu cầu trả lời/giải thích trực diện 2–4 câu (CẤM chỉ lặp lại câu hỏi học viên) rồi mới kết thúc bằng 1 câu hỏi Socratic MỚI có dấu `?`.

5. **Lớp 5 — Streaming, Guardrails & TelemetryCritic (`app/services/chat.py`, `app/services/telemetry_critic.py`):**
   - `chat.py`:
     - Nạp `forbidden_closing_prefixes` từ `router_intent_manifest.json` (chỉ gồm câu kết sáo rỗng thuần túy, giữ nguyên `"bạn có muốn..."`).
     - Cập nhật `has_trailing_socratic_question(text, user_prompt=None)`: loại bỏ câu kết sáo rỗng và không tính dấu `?` của câu hỏi bị nhại gần giống `user_prompt` (`sentence_count <= 1` and `token_overlap >= 0.60`).
     - Trong `StreamingSocraticFooterGuard`:
       1. Dùng bounded tail/prefix buffer (giống `MID_FOOTER_CANDIDATES`) để chặn/tước bỏ các câu kết sáo rỗng thuần túy ở cuối văn xuôi trước footer, và chèn `fallback_question` nếu không còn câu hỏi `?` thực chất nào.
       2. **Giữ dòng footer `📍` (hold footer):** không phát `📍 **Mốc video bài giảng:**` ra wire cho tới khi thấy ít nhất 1 `<timestamp>` hợp lệ (`sec in valid_secs`) hoặc tại `flush()` sau khi kiểm tra echo; nếu `valid_secs` rỗng hoặc mọi tag đều bị loại, hủy bỏ hoàn toàn dòng footer `📍`.
     - Trong `ChatService.stream_chat`:
       1. Phát hiện echo-only khi stream kết thúc (`_is_echo_only_prose(prose, clean_prompt)` and `retrieval_status == "grounded"` and `retrieved_chunks`), **trước** khi xả footer `📍` đã giữ: gọi tối đa **1 lượt continuation** (`timeout=15.0`) đẩy token qua **cùng `StreamingOutputPipeline` instance** (giữ nguyên whitelist, code/CJK/closer guard), rồi xả footer `📍` đúng 1 lần; lưu lịch sử tổng hợp vào Checkpointer. Nếu continuation lỗi/timeout/offline: không bịa văn bản, xả footer nếu có `valid_secs` hợp lệ.
       2. Auto-label `📍 **Mốc video bài giảng:**` CHỈ kích hoạt khi dòng cuối chỉ chứa các thẻ `<timestamp ...>...</timestamp>` (và dấu `|` / khoảng trắng), không bao giờ chèn vào giữa câu.
   - `telemetry_critic.py`:
     - Đồng bộ kiểm tra `forbidden_closing_prefixes` và phát hiện `is_echo_only` (cảnh báo khi phản hồi `course_query` chỉ lặp lại prompt học viên).

---

## 5. Cross-Layer Conflict & Invariant Matrix (Ma trận Chống Xung đột Chéo)

| Thay đổi dự kiến | Nguy cơ xung đột chéo tiềm ẩn | Cơ chế phòng ngừa trong Spec | Kiểm chứng bắt buộc |
|---|---|---|---|
| **PC-01**: `router_node Bước 3b` dùng `is_video_section_seeking_query` (2 khe) + `verify_in_video_temporal_query` | Có thể cứu nhầm câu hỏi danh tính có từ thời gian (`"bạn được tạo ra lúc nào"`) hoặc câu ngoài lề (`"phút thứ 6 trận bóng đá"`) | 1) Không sửa `IntentRouter.classify()` (tránh NLI trong loop history). 2) Yêu cầu đủ 2 khe (`position_wh_phrase` + `lecture_action_verb`), bỏ `"lúc nào"`/`"timeline"`. 3) Nhường quyền nếu `is_curriculum_nav` hoặc `_names_other_lesson_topic`. 4) Vẫn qua `p_oos < 0.75` và `verify_in_video_temporal_query` (`< 0.60`). | `M1-T01`, `M1-T10`, `M3-T02`, `"bạn được tạo ra lúc nào"`, `Golden 200` `chit_chat`/`out_of_scope` |
| **PC-02**: `is_context_dependent` nhận `follow_up_elaboration_signatures` + Recency Gate `last_turn_intent` | Có thể cứu nhầm câu follow-up sau lượt OOS (`T1 -> T2 OOS -> T3`) hoặc câu `"nấu mì chi tiết hơn"` | 1) Residual ngoài signature/hư từ phải rỗng hoặc thuộc `anaphora_signatures`. 2) Recency Gate yêu cầu lượt liền trước là `course_query` (`last_turn_intent == "course_query"`). 3) `retrieval_node` chỉ ưu tiên `search_query` khi `not has_domain_entity` & `time_ref is None`. | `M1-T03`, `M1-T07`, `M2-T07`, counter-examples `"nấu mì chi tiết hơn"` & `T1->T2(OOS)->T3`, `TelemetryCritic` |
| **PC-03**: Chữ ký nav bỏ dấu + `last_offered_lessons` + kiểm tra biên manifest + sửa data L1 | 1) Va chạm dấu (`"bãi biển nào đẹp"`). 2) Tự bịa chọn 1 bài khi `competing_lessons` trả 4 bài (`57/48/79/64`). 3) Sửa ASR runtime làm lệch index Qdrant. | 1) Chữ ký bỏ dấu yêu cầu `domain_entity` hoặc `semantic_search_lessons >= 0.80` + `nav_sim >= 0.82` + `sim_sys < 0.88`. 2) `last_offered_lessons` chỉ điều hướng thẳng khi `len == 1`, nếu `len > 1` hỏi rõ từ danh sách manifest (không parse text 7B). 3) Sửa ASR trực tiếp trên `lesson-01_chunks.json` + re-upsert Qdrant + grep xác thực. | `test_playback_temporal_and_disambiguation.py`, `test_input_normalization.py`, 12 pos / 12 neg unaccented benchmark, Qdrant L1 grep |
| **PC-04**: 2-slot `analogy_verification_2slot` + sửa wording `user_message_content` + echo continuation qua cùng pipeline | 1) `"cho mình ví dụ..."` hoặc `"đúng kiểu..."` kích hoạt nhầm. 2) Tăng TTFT. 3) Phá KV cache `messages[0]`. | 1) 2 khe token-boundary (`comparison_markers` + `verification_tail_markers`). 2) Giữ `messages[0]` tĩnh (chỉ 1 câu cấm echo cố định). 3) Chỉ giữ footer `📍` cuối stream (**0ms TTFT** cho lượt thường); continuation chạy qua cùng pipeline trước khi xả `📍` 1 lần; timeout/fail không bịa text & đặt `is_echo_only`. | `test_group1_2_optimizations.py::test_kv_prefix_cache...`, `"cho mình ví dụ về vòng lặp for"`, `"đúng kiểu dữ liệu"`, `M1/M2/M3` |
| **PC-05**: Cụm loại trừ thực sự + lọc `0.15..0.35` `code_ast` khác bài + closer sáo rỗng + footer `📍` | 1) Phá `"sau bài 20 thì học gì"` hoặc `"bài này khác bài 11 chỗ nào"`, hoặc làm `"ngoài bài 64..."` rơi nhầm `competing_lessons`. 2) Làm rớt `code_ast >= 0.35` bài trước (`L50 struct 0.40` ở L57) hoặc làm mất `function_main` cùng bài (`L2 const`). 3) Tước nhầm `"Bạn có muốn..."` ở câu chọn chủ đề. | 1) Chỉ nhận `ngoài bài`/`trừ bài`/`không tính bài`/`bên cạnh bài`; nếu có `excluded_seqs` mà không phải Dạng 1 `multi_topic_disjunction` thì thoát `empty_res` để giữ danh mục bài liên quan. 2) `code_ast >= 0.35` bài trước và `code_ast >= 0.15` cùng `current_lesson_seq` đều được giữ nguyên; chỉ chặn `code_ast < 0.35` khác bài (`54 != 57`). 3) Giữ `"bạn có muốn..."` ngoài `forbidden_closing_prefixes`. 4) Auto-label `📍` chỉ trên dòng chỉ chứa `<timestamp>`, giữ `test_p0_stream_chat_no_duplicate_footer`. | `M2-T06`, `test_stage13_context_hygiene.py`, `test_search_api.py`, `test_session_7aky9_debug_fixes.py`, `test_p0_regression.py`, `test_e2e_anti_parroting_and_critic.py`, counter-examples `"sau bài 20..."` & `"L50 struct 0.40"` |

---

## 6. Kế hoạch Nghiệm thu & Chống Hồi quy (Verification Plan)

1. **Unit / Integration Tests mới (`tests/test_playground_e2e_convergence.py`):**
   - `test_pc01_section_seeking_2slot_rescue_and_identity_sport_isolation`: Khóa `"khoảng phút bao nhiêu thì nói về lý thuyết"`, `"phút mấy nói về con trỏ"` -> `course_query` + tiêm chapters; đối chứng `"bạn được tạo ra lúc nào"` -> `chit_chat`, `"phút thứ 6 trận bóng đá tỷ số bao nhiêu"` -> `out_of_scope`.
   - `test_pc02_elaboration_followup_recency_gate_and_offtopic_rejection`: Khóa `"chi tiết hơn"` sau `"đoạn này đang khai báo gì"` -> `course_query` + `search_query`; khóa Recency Gate (`T1: con trỏ -> T2: nấu mì 5 phút -> T3: giải thích thêm` KHÔNG cứu vào `T1`); đối chứng `"nấu mì chi tiết hơn"` -> `out_of_scope`.
   - `test_pc03_unaccented_nav_structured_offered_lessons_and_dynamic_bounds`: Khóa 12 câu nav không dấu vs 12 câu phủ định/va chạm; khóa `"có bai học nào về con trỏ không"` -> `"chuyển cho tôi đến bài đó"` dùng `last_offered_lessons` (không rơi về L2); khóa `"chuyển cho tôi đến bài 999"` từ chối động theo manifest bounds.
   - `test_pc04_analogy_2slot_directive_and_echo_continuation_same_pipeline`: Khóa 2-slot token-boundary (`"tờ giấy ghi địa chỉ nhà có đúng k"` vs `"cho mình ví dụ về vòng lặp for"` & `"đúng kiểu"`); khóa `ChatService.stream_chat` giữ `📍`, chạy 1-shot continuation qua cùng `StreamingOutputPipeline` (lọc whitelist/CJK/code), và fallback an toàn khi timeout (`is_echo_only=True`, 0 text bịa).
   - `test_pc05_true_exclusion_prior_ast_preservation_closers_and_footer`: Khóa `"ngoài bài 57..."` (`is_navigation_query=True`, `excluded_seqs={57}`, `suggested_timestamps=[]`, không có `📍`); khóa `"sau bài 20 thì học gì"` & `"bài này khác bài 11 chỗ nào"` giữ `20`/`11`; khóa T9 (`L54 0.1711` bị loại) nhưng giữ L50 `struct >= 0.35`; khóa closer sáo rỗng bị thay thế trong khi `"Bạn có muốn biết thêm..."` được bảo toàn.

2. **Data-Inspected Verification (Sau sửa L1 & Qdrant upsert):**
   - `Select-String` trên `data/transcripts/cpp-core/lesson-01_..._chunks.json` và truy vấn `QdrantClient.scroll` (`lesson-01`) xác nhận 0 còn `"bài tập về mạng"` / `"câu chúc"` / `"lý thiết số"`.

3. **Regression Pytest tuần tự (`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`, sau bản sửa cuối):**
   - `tests/test_playground_e2e_convergence.py`
   - `tests/test_playback_temporal_and_disambiguation.py`
   - `tests/test_unseen_edges_and_canonicalizer.py`
   - `tests/test_session_7aky9_debug_fixes.py`
   - `tests/test_stage13_context_hygiene.py`
   - `tests/test_group1_2_optimizations.py`
   - `tests/test_p0_regression.py`
   - `tests/test_e2e_anti_parroting_and_critic.py`
   - `tests/test_chat_stream.py`
   - `tests/test_search_api.py`
   - `tests/test_multiturn_benchmark.py -k "test_tier_2_socratic_refusal_precision"`

4. **Live E2E Verification (sau bản sửa cuối, Qdrant Cloud & Kaggle vLLM live):**
   - `scripts/e2e_matrix_harness.py --suite all` (`all_passed: true`, Health Score >= 85).
   - Kịch bản replay live 5 Problem Classes (`PC-01..PC-05`) qua `ChatService.stream_chat` + `TelemetryCriticService`.
