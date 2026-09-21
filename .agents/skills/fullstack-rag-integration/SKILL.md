---
name: fullstack-rag-integration
description: Architectural contracts, runtime setup (Docker/MongoDB/IntelliJ, React 19/Vite), and integration blueprints for connecting fe-codelearning and nghia BE with In-Course Agentic RAG Copilot.
---

# Fullstack RAG Integration Architecture & Integration Blueprint

Kỹ năng lưu trữ kiến trúc, hợp đồng dữ liệu (schemas & contracts), cấu hình môi trường thực thi (IntelliJ, Docker MongoDB, React 19/Vite 7) và quy trình tích hợp giữa hệ thống Web học lập trình với **In-Course Agentic RAG Copilot**.

---

## 1. Kiến Trúc Tổng Thể (Hybrid Dual-Backend Topology)

Hệ thống vận hành theo mô hình kiến trúc phân tán 2 backend độc lập:

```mermaid
flowchart TD
    subgraph Frontend["Frontend Client (fe-codelearning - Port 5173)"]
        UI["CourseContent.jsx & ChatWidget.jsx"]
        Player["Video Player (iframeRef / videoRef)"]
    end

    subgraph SpringBoot["Platform Core BE (nghia - Port 8080)"]
        Auth["Spring Security + JWT"]
        MongoDB[("MongoDB (Docker)")]
        LessonSvc["Lesson & Course Management"]
        Payment["PayOS Payment & Invoices"]
    end

    subgraph FastAPICopilot["Agentic RAG Copilot BE (FastAPI - Port 8000)"]
        StreamAPI["/api/v1/chat/stream (SSE)"]
        Router["Intent Router (Fast-Path vs RAG)"]
        Qdrant[("Qdrant Dual Vectors (E5 + BM25)")]
        LLM["Socratic LLM (Ollama / vLLM)"]
    end

    UI -->|1. Xác thực & lấy bài học, video| LessonSvc
    LessonSvc --- MongoDB
    UI -->|2. SSE: Gửi câu hỏi kèm course_id & lesson_seq| StreamAPI
    StreamAPI --> Router
    Router -->|In-HNSW Filter: course_id == C AND lesson_seq <= L| Qdrant
    Qdrant --> LLM
    LLM -->|3. Streaming phản hồi Socratic + <timestamp>| UI
    UI -->|4. Click mốc thời gian -> seekTo(sec)| Player
```

* **Spring Boot Platform BE (Port 8080)**:
  * **Môi trường**: Chạy bằng **IntelliJ IDEA**, kết nối **Docker MongoDB** làm cơ sở dữ liệu chính và Redis cho OTP.
  * **Nhiệm vụ**: Quản lý nghiệp vụ người dùng (Auth/JWT), thông tin khóa học, bài học, thanh toán PayOS, bài kiểm tra trắc nghiệm (Quiz), và tiến độ học tập.
* **FastAPI Copilot BE (Port 8000)**:
  * **Môi trường**: Python 3.11 trong `.venv`, Uvicorn reload IPv4 `http://127.0.0.1:8000`.
  * **Nhiệm vụ**: Đảm nhiệm toàn bộ quy trình RAG đa phương thức: In-HNSW Pre-filtering, Re-ranking với Sigmoid, Socratic Method Prompting, trích xuất thẻ `<timestamp sec="...">mm:ss</timestamp>`, và phát luồng Server-Sent Events (SSE).
* **React Frontend (Port 5173)**:
  * **Công nghệ**: React 19 (`^19.2.0`), Vite 7 (`^7.2.2`), Tailwind CSS v4.
  * **Cấu hình bắt buộc**: File `vite.config.js` **phải nằm ở thư mục gốc** `fe-codelearning/vite.config.js` (không để trong `src/`) để nạp đúng plugin `@vitejs/plugin-react`.

---

## 2. Bảng Ánh Xạ Dữ Liệu Thực Thể (Entity Contract Mapping)

| Tham Số Frontend / RAG | Thuộc Tính Backend Spring Boot (`Lesson.java`) | Kiểu Dữ Liệu | Mục Đích Nghiệp Vụ |
| :--- | :--- | :--- | :--- |
| `course_id` | `lesson.getCourseId()` | `String` | Định danh khóa học (ví dụ: `cpp-oop`) |
| `lesson_seq` | `lesson.getOrder()` | `Integer` | Thứ tự bài học trong chương $\rightarrow$ dùng lọc In-HNSW `lesson_seq <= current_lesson_seq` |
| `video_url` | `lesson.getVideoUrl()` | `String` | URL YouTube hoặc link file video tự host |
| `video_id` | `lesson.getVideoId()` | `String` | Mã định danh YouTube trích xuất từ URL |
| `code_snippets` | `lesson.getCodeSnippets()` | `List<CodeSnippet>` | Mã nguồn C++/Java mẫu gắn liền với bài học |
| `content` | `lesson.getContent()` | `String` | Nội dung lý thuyết bài giảng (Markdown/HTML) |

---

## 3. Giao Thức Điều Khiển Video Player (`player.seekTo(sec)`)

Trong giao diện học bài [CourseContent.jsx](file:///d:/In_Course_Agentic_RAG_Copilot/external_fe/src/pages/CourseContent.jsx), frontend quản lý 2 loại player:

### A. YouTube Iframe Player
Iframe được khởi tạo với tham số `enablejsapi=1`:
```jsx
<iframe
  ref={iframeRef}
  src={`https://www.youtube.com/embed/${videoId}?autoplay=1&enablejsapi=1`}
  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
  allowFullScreen
/>
```
Khi người dùng click vào thẻ `<timestamp sec="145">02:25</timestamp>` do AI sinh ra, frontend gửi lệnh qua `postMessage`:
```javascript
const seekYouTubeTo = (seconds) => {
  if (iframeRef.current && iframeRef.current.contentWindow) {
    iframeRef.current.contentWindow.postMessage(
      JSON.stringify({
        event: "command",
        func: "seekTo",
        args: [Number(seconds), true]
      }),
      "*"
    );
  }
};
```

### B. HTML5 Video Player
```jsx
<video ref={videoRef} src={videoUrl} controls />
```
Thực thi lệnh seek trực tiếp trên DOM:
```javascript
const seekHtml5VideoTo = (seconds) => {
  if (videoRef.current) {
    videoRef.current.currentTime = Number(seconds);
    videoRef.current.play();
  }
};
```

---

## 4. Hợp Đồng Luồng SSE Streaming (Frontend $\leftrightarrow$ FastAPI)

### Endpoint: `POST http://127.0.0.1:8000/api/v1/chat/stream`
* **Request Payload**:
  ```json
  {
    "message": "Hàm hủy ảo trong C++ dùng để làm gì?",
    "course_id": "cpp-oop",
    "lesson_seq": 44,
    "conversation_id": "session-xyz-123"
  }
  ```
* **Response Event Stream**:
  ```http
  Content-Type: text/event-stream
  Cache-Control: no-cache
  Connection: keep-alive

  data: {"type": "token", "content": "Hàm hủy ảo (virtual destructor) được sử dụng để"}
  data: {"type": "token", "content": " giải phóng tài nguyên của lớp dẫn xuất..."}
  data: {"type": "timestamp", "sec": 145, "display": "02:25", "label": "Giải thích Virtual Destructor"}
  data: {"type": "done"}
  ```

---

## 5. Quy Chuẩn Vận Hành & Khắc Phục Lỗi Nhanh

1. **Lỗi `[vite:build-html]` khi chạy `npm run build`**:
   * Kiểm tra vị trí file `vite.config.js`. Phải đặt tại `fe-codelearning/vite.config.js`.
2. **Lỗi CORS giữa React (5173) và FastAPI (8000)**:
   * Đảm bảo FastAPI `CORSMiddleware` cho phép `http://localhost:5173` và `http://127.0.0.1:5173`.
3. **Lỗi Docker MongoDB không kết nối được từ Spring Boot**:
   * Kiểm tra chuỗi kết nối trong `application.properties` hoặc `application.yml` (`mongodb://localhost:27017/cake_db`).
