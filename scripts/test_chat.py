import sys
import json
import httpx

API_URL = "http://127.0.0.1:8000/api/v1/chat/stream"


def stream_question(prompt: str, title: str):
    print("\n" + "=" * 70)
    print(f"📌 {title}")
    print(f"💬 Câu hỏi: '{prompt}'")
    print("=" * 70)

    payload = {
        "prompt": prompt,
        "course_id": "cpp-core",
        "lesson_seq": 2
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            with client.stream("POST", API_URL, json=payload) as response:
                if response.status_code != 200:
                    print(f"❌ Lỗi HTTP {response.status_code}: {response.text}")
                    return

                current_event = None
                for line in response.iter_lines():
                    if not line:
                        continue
                    if line.startswith("event: "):
                        current_event = line[7:].strip()
                    elif line.startswith("data: "):
                        data_str = line[6:].strip()
                        if current_event == "metadata":
                            meta = json.loads(data_str)
                            print(f"\n🏷️  [METADATA]")
                            print(f"   - Intent: {meta.get('intent')}")
                            print(f"   - Fast-Path: {meta.get('used_fast_path')}")
                            print(f"   - Số chunks RAG: {meta.get('retrieved_chunk_count')}")
                            if meta.get("suggested_timestamps"):
                                print(f"   - Timestamps video:")
                                for ts in meta["suggested_timestamps"]:
                                    print(f"     * [{ts.get('label')}] ({ts.get('sec')}s): {ts.get('title')}")
                            print(f"\n🤖 [AI COPILOT]: ", end="", flush=True)
                            current_event = None

                        elif current_event == "delta":
                            delta = json.loads(data_str)
                            print(delta.get("content", ""), end="", flush=True)

                        elif current_event == "done":
                            print("\n\n✅ [Hoàn tất luồng SSE]")
                            break
    except httpx.ConnectError:
        print(f"❌ Không thể kết nối tới {API_URL}.")
        print("👉 Vui lòng đảm bảo bạn đã chạy server ở tab kia: .venv\\Scripts\\uvicorn app.main:app --port 8000")
    except Exception as e:
        print(f"❌ Lỗi: {e}")


if __name__ == "__main__":
    # Lựa chọn kịch bản kiểm thử
    if len(sys.argv) > 1:
        custom_query = " ".join(sys.argv[1:])
        stream_question(custom_query, "KIỂM THỬ CÂU HỎI TÙY CHỌN")
    else:
        # Chạy lần lượt 3 kịch bản
        stream_question("Xin chào bạn, bạn là ai?", "KỊCH BẢN 1: FAST-PATH CHÀO HỎI & DANH TÍNH")
        stream_question("chỉ tôi cách chiên cá giòn ngon", "KỊCH BẢN 2: OUT-OF-SCOPE GUARDRAILS (CHIÊN CÁ)")
        stream_question("Làm sao để khai báo hằng số const và ép kiểu trong C++?", "KỊCH BẢN 3: IN-COURSE SOCRATIC RAG PIPELINE")
