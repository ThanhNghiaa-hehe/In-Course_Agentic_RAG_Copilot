---
name: whisper-canonicalizer-tester
description: Fast validation and tuning of audio speech-to-text (faster-whisper, Silero VAD), domain hotwords lexicon biasing, and Stage 2 Tech Canonicalizer phonetic regex repair without re-running heavy GPU/CPU transcription.
---

# Whisper & Tech Canonicalizer Tester Runbook

## 1. Mục Đích & Phạm Vi Áp Dụng
Sử dụng kỹ năng này khi:
- Cần kiểm thử và bổ sung các mẫu Regex chuẩn hóa âm học tiếng Việt (Tech Canonicalizer) cho thuật ngữ lập trình C++/Java (`cout`, `cin`, `namespace`, `#include`, `Ctrl+F5`,...).
- Cần tinh chỉnh bộ lọc ngắt câu theo giọng nói Silero VAD (`threshold`, `speech_pad_ms`) khi bài giảng có nhiều khoảng lặng hoặc lẫn tạp âm bàn phím.
- Muốn cập nhật và làm sạch lại các file transcript đã phiên âm trước đó mà **không cần chạy lại mô hình Whisper** (tiết kiệm 100% thời gian và tài nguyên CPU/GPU).

---

## 2. Hai Vòng Lặp Vận Hành (Fast-Loop vs Full-Loop)

```text
[NHU CẦU: SỬA TỪ KHÓA / REGEX] ➔ Chạy FAST-LOOP (0 giây GPU, lấy kết quả ngay)
[NHU CẦU: NẠP VIDEO MỚI TỪ ĐẦU] ➔ Chạy FULL-LOOP (faster-whisper + Silero VAD)
```

### Vòng lặp A: Fast-Loop (Kiểm thử nhanh Regex không tốn tài nguyên)
Khi phát hiện lời giảng phiên âm bị sai từ kỹ thuật (ví dụ: *"lời láo"*, *"xi cộng cộng"*, *"can cho D"*):
1. **Mở file cấu hình Canonicalizer:** [scripts/reclean_transcripts.py](file:///d:/In_Course_Agentic_RAG_Copilot/scripts/reclean_transcripts.py) hoặc [scripts/ingest_video.py](file:///d:/In_Course_Agentic_RAG_Copilot/scripts/ingest_video.py).
2. **Cập nhật mẫu từ điển trong `TECH_CORRECTIONS`:**
   ```python
   TECH_CORRECTIONS = [
       (r'\b(xi\s*cộng\s*cộng|c\s*cộng\s*cộng)\b', 'C++'),
       (r'\bcan\s*cho\s*([a-zA-Z0-9]+)\b', r'Ctrl+\1'),
       (r'\byêu\s*sinh\s*nem\s*xpay\b', 'using namespace'),
       (r'\bart\s*cái\b', 'Add cái'),
   ]
   ```
3. **Thực thi script làm sạch lại tức thì:**
   ```powershell
   .venv\Scripts\python scripts\reclean_transcripts.py
   ```
4. **Kiểm tra kết quả đầu ra:** Mở file báo cáo markdown tương ứng trong `data/transcripts/<video_stem>/<video_stem>_report.md` để kiểm tra độ mượt của câu chữ sau khi thay thế.

---

### Vòng lặp B: Full-Loop (Nạp & Phiên âm Video mới)
Khi cần xử lý một video bài giảng `.mp4` hoàn toàn mới:
1. **Tham số VAD chuẩn hóa:**
   - `threshold=0.35`: Nhạy vừa đủ, không ngắt vỡ câu khi giảng viên thở dài.
   - `speech_pad_ms=400`: Đệm 400ms đầu và cuối câu để không bị nuốt chữ âm đầu/âm cuối.
   - `condition_on_previous_text=False`: Chống hiện tượng lặp từ vô tận (Whisper hallucination loop).
2. **Domain Hotwords Biasing:**
   - Luôn duy trì chuỗi `hotwords`: `"C++, cout, cin, namespace, include, iostream, int, return, main, visual studio, void, variable, constant, using"`.
3. **Chạy pipeline nạp video:**
   ```powershell
   .venv\Scripts\python scripts\ingest_video.py "path/to/video.mp4" --course cpp-core --lesson lesson-03 --seq 3
   ```

---

## 3. Quy Chuẩn Hiển Thị Terminal & Bảo Vệ Con Trỏ Windows

Để tránh lỗi nhảy đè con trỏ và tràn dòng trên Windows PowerShell khi in kết quả transcript:
1. **Tuyệt đối không dùng emoji 2 ô (multi-byte double-width):** Thay vì `🎬`, `📌`, `📝`, hãy dùng các ký tự ASCII chuẩn: `>>> [CONTEXT 1]`, `- Video:`, `- Moc thoi gian:`.
2. **Luôn gói dòng bằng `textwrap`:**
   ```python
   import textwrap
   wrapped_text = textwrap.fill(speech_text, width=72, initial_indent="   ", subsequent_indent="   ")
   print(wrapped_text, flush=True)
   ```
3. **Luôn có `flush=True`:** Đảm bảo toàn bộ buffer được đẩy ra console ngay lập tức mà không bị kẹt trong luồng I/O.

---

## 4. Xử Lý Sự Cố Thường Gặp (Troubleshooting)

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| :--- | :--- | :--- |
| Whisper lặp đi lặp lại 1 câu 10 lần | Bật `condition_on_previous_text=True` | Chuyển thành `condition_on_previous_text=False` trong hàm transcribe. |
| Mất hẳn chữ âm đầu/cuối câu | `speech_pad_ms` quá ngắn | Tăng `speech_pad_ms` lên 400ms hoặc 500ms. |
| Chữ tiếng Hàn/Hán sinh ngẫu nhiên | Whisper hallucination khi gặp đoạn im lặng dài | Bổ sung Regex lọc ký tự Unicode ngoại lai trong hàm `sanitize_terminal_text()`. |
| Thiếu file `cublas64_12.dll` trên Windows | Thiếu CUDA toolkit runtime | Tự động bắt `Exception` và fallback về `device="cpu", compute_type="int8"`. |
