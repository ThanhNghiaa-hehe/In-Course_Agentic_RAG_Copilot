import os
import sys
import json
import uuid
import re
import argparse
import unicodedata
from pathlib import Path
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import ctranslate2
from faster_whisper import WhisperModel
from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.config import settings

# Bộ từ điển thuật ngữ tự động theo từng ngôn ngữ lập trình (Domain Lexicon)
DOMAIN_HOTWORDS = {
    "cpp": [
        "C++", "include", "iostream", "namespace", "std", "cout", "cin", "main", 
        "Ctrl", "pointer", "con trỏ", "class", "struct", "Visual Studio", "Debug",
        "endl", "int", "void", "return", "vector", "string", "template", "OOP"
    ],
    "java": [
        "Java", "public", "static", "void", "main", "System.out.println", "class",
        "interface", "extends", "implements", "Spring", "SpringBoot", "Autowired",
        "Repository", "Service", "Controller", "NullPointerException", "override"
    ],
    "python": [
        "Python", "def", "class", "return", "import", "print", "self", "None",
        "lambda", "try", "except", "FastAPI", "Pydantic", "dict", "list", "tuple"
    ]
}

# [STAGE 2] BỘ TỪ ĐIỂN CHUẨN HÓA THUẬT NGỮ LẬP TRÌNH (TECH CANONICALIZER)
TECH_CANONICAL_MAP = {
    r'\b(si|xi|xy|xê|xì)\s+cộng\s+cộng\b': 'C++',
    r'\bC\+\+\s+cộng\b': 'C++',
    r'(cdc共 cộng|C共 cộng|si\s*cộng\s*cộng)': 'C++',
    r'\b(xi|si)\s*(sáp|thăng|sap)\b': 'C#',
    r'\b(pay\s*thần|pai\s*thơn)\b': 'Python',
    r'\b(code\s*lin|cốt\s*lin)\b': 'Kotlin',
    r'\b(can\s*chua|can\s*chô|can\s*trô|con\s*chó)\b': 'Ctrl',
    r'\b(ham\s*men|hàm\s*men)\b': 'hàm main',
    r'\b(thăng\s*inqlude|thăng\s*in\s*cờ\s*lút|thang\s*in|hãn\s*thang\s*in)\b': '#include',
    r'\b(ios\s*chìm|ai\s*âu\s*sờ\s*trim)\b': '<iostream>',
    r'\b(dao\s*loát|đào\s*loát|đao\s*loát|daoluoat|free dao loat)\b': 'download',
    r'\b(răn\s*adan\s*min|chạy\s*admin)\b': 'Run as Administrator',
    r'\b(bui\s*nè|bui\s*number|đợi\s*mà\s*lát\s*nó\s*bui)\b': 'build',
    r'\b(visual\s*tildo|vizual\s*studio)\b': 'Visual Studio',
}

def get_hotwords_for_course(course_id: str, custom_hotwords: str = None) -> str:
    selected_words = []
    course_lower = course_id.lower()
    
    if "c++" in course_lower or "cpp" in course_lower:
        selected_words.extend(DOMAIN_HOTWORDS["cpp"])
    elif "java" in course_lower:
        selected_words.extend(DOMAIN_HOTWORDS["java"])
    elif "py" in course_lower:
        selected_words.extend(DOMAIN_HOTWORDS["python"])
    else:
        selected_words.extend(DOMAIN_HOTWORDS["cpp"])

    if custom_hotwords:
        extra = [w.strip() for w in custom_hotwords.split(",") if w.strip()]
        selected_words.extend(extra)

    unique_words = list(dict.fromkeys(selected_words))
    return ", ".join(unique_words)

def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).strip()
    
    fillers = ["à ừm", "ừm", "à thì", "kiểu như là", "các bạn biết đấy"]
    for f in fillers:
        text = text.replace(f, "")
    
    for pattern, replacement in TECH_CANONICAL_MAP.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    text = re.sub(r'\b(CREATE|include|main|iostream)\s+(?:\1\s*)+', r'\1 ', text, flags=re.IGNORECASE)
    return " ".join(text.split())

def time_aware_chunking(segments, min_duration=60, max_duration=90, overlap=15):
    chunks = []
    if not segments:
        return chunks

    total_duration = segments[-1]["end"] - segments[0]["start"]
    if total_duration < min_duration:
        chunk_text = " ".join([s["text"] for s in segments])
        start_sec = int(segments[0]["start"])
        end_sec = int(segments[-1]["end"])
        return [{
            "chunk_id": f"chunk_{start_sec}_{end_sec}",
            "start_sec": start_sec,
            "end_sec": end_sec,
            "start_label": f"{start_sec//60:02d}:{start_sec%60:02d}",
            "end_label": f"{end_sec//60:02d}:{end_sec%60:02d}",
            "raw_text": normalize_text(chunk_text)
        }]

    current_chunk_segments = []
    chunk_start = segments[0]["start"]

    for seg in segments:
        current_chunk_segments.append(seg)
        current_duration = seg["end"] - chunk_start

        if current_duration >= min_duration:
            chunk_end = seg["end"]
            chunk_text = " ".join([s["text"] for s in current_chunk_segments])
            start_sec = int(chunk_start)
            end_sec = int(chunk_end)
            
            chunks.append({
                "chunk_id": f"chunk_{start_sec}_{end_sec}",
                "start_sec": start_sec,
                "end_sec": end_sec,
                "start_label": f"{start_sec//60:02d}:{start_sec%60:02d}",
                "end_label": f"{end_sec//60:02d}:{end_sec%60:02d}",
                "raw_text": normalize_text(chunk_text)
            })

            target_overlap_start = chunk_end - overlap
            current_chunk_segments = [s for s in current_chunk_segments if s["end"] > target_overlap_start]
            if current_chunk_segments:
                chunk_start = current_chunk_segments[0]["start"]
            else:
                chunk_start = seg["end"]

    if current_chunk_segments:
        chunk_end = current_chunk_segments[-1]["end"]
        chunk_text = " ".join([s["text"] for s in current_chunk_segments])
        start_sec = int(chunk_start)
        end_sec = int(chunk_end)
        chunks.append({
            "chunk_id": f"chunk_{start_sec}_{end_sec}",
            "start_sec": start_sec,
            "end_sec": end_sec,
            "start_label": f"{start_sec//60:02d}:{start_sec%60:02d}",
            "end_label": f"{end_sec//60:02d}:{end_sec%60:02d}",
            "raw_text": normalize_text(chunk_text)
        })

    return chunks

def load_whisper_model(model_size="small"):
    try:
        if ctranslate2.get_cuda_device_count() > 0:
            print(f"Thử khởi chạy Whisper ({model_size}) trên NVIDIA CUDA...")
            return WhisperModel(model_size, device="cuda", compute_type="float16")
    except Exception as e:
        print(f"CUDA initialization failed ({e}).")

    print(f"Khởi chạy Whisper ({model_size}) trên CPU (int8)...")
    return WhisperModel(model_size, device="cpu", compute_type="int8")

def process_video(video_path: str, course_id="cpp-core", lesson_id="lesson-01", lesson_seq=1, model_size="small", custom_hotwords: str = None, clean_old_points: bool = True):
    video_file = Path(video_path)
    if not video_file.exists():
        print(f"❌ Lỗi: Không tìm thấy file video tại: {video_path}")
        return

    print("=" * 60)
    print(f"[STAGE 1 & 2] Khởi động Whisper Speech-to-Text Pipeline (with Progress Bar)")
    print(f"Video File: {video_file.name}")
    print(f"Khóa học: {course_id} | Bài học: {lesson_id} (Thứ tự: {lesson_seq})")

    hotwords_str = get_hotwords_for_course(course_id, custom_hotwords)
    print(f"🔥 Kích hoạt Hotwords: {hotwords_str}")

    whisper_model = load_whisper_model(model_size=model_size)

    vad_parameters = {
        "threshold": 0.35,
        "min_speech_duration_ms": 150,
        "min_silence_duration_ms": 800,
        "speech_pad_ms": 400
    }

    initial_prompt = f"Khóa học {course_id}, bài học {lesson_id}. Lập trình C++, Visual Studio, code."

    print("Đang phân tích âm thanh và bắt đầu phiên âm...")
    try:
        segments_raw, info = whisper_model.transcribe(
            str(video_file),
            language="vi",
            beam_size=5,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters=vad_parameters,
            initial_prompt=initial_prompt,
            hotwords=hotwords_str
        )

        total_audio_sec = round(info.duration)
        total_min_label = f"{total_audio_sec//60:02d}:{total_audio_sec%60:02d}"
        print(f"⏱️ Tổng thời lượng video: {total_audio_sec} giây (~{total_min_label})")

        extracted_segments = []
        with tqdm(total=total_audio_sec, unit="s", desc="🎧 Phiên âm video (STT)", dynamic_ncols=True) as pbar:
            last_pos = 0
            for s in segments_raw:
                clean_s = normalize_text(s.text)
                if clean_s:
                    extracted_segments.append({
                        "start": s.start,
                        "end": s.end,
                        "text": clean_s
                    })
                # Cập nhật thanh tiến trình theo số giây Whisper vừa đi qua
                current_pos = min(round(s.end), total_audio_sec)
                delta = current_pos - last_pos
                if delta > 0:
                    pbar.update(delta)
                    last_pos = current_pos
            # Đảm bảo kết thúc ở 100%
            if total_audio_sec > last_pos:
                pbar.update(total_audio_sec - last_pos)

    except Exception as transcribe_err:
        print(f"\nChuyển sang CPU do lỗi: {transcribe_err}")
        whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments_raw, info = whisper_model.transcribe(
            str(video_file),
            language="vi",
            beam_size=5,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters=vad_parameters,
            initial_prompt=initial_prompt,
            hotwords=hotwords_str
        )
        total_audio_sec = round(info.duration)
        extracted_segments = []
        with tqdm(total=total_audio_sec, unit="s", desc="🎧 Phiên âm video (CPU)", dynamic_ncols=True) as pbar:
            last_pos = 0
            for s in segments_raw:
                clean_s = normalize_text(s.text)
                if clean_s:
                    extracted_segments.append({
                        "start": s.start,
                        "end": s.end,
                        "text": clean_s
                    })
                current_pos = min(round(s.end), total_audio_sec)
                delta = current_pos - last_pos
                if delta > 0:
                    pbar.update(delta)
                    last_pos = current_pos
            if total_audio_sec > last_pos:
                pbar.update(total_audio_sec - last_pos)

    print(f"\n✓ Hoàn tất phiên âm: trích xuất được {len(extracted_segments)} câu phát biểu.")
    if not extracted_segments:
        print("Cảnh báo: Không phát hiện giọng nói trong video.")
        return

    # 3. Time-aware Chunking (60-90 giây)
    print("\n[STAGE 3] Đang phân rã Chunks theo khung 60-90 giây...")
    chunks = time_aware_chunking(extracted_segments, min_duration=60, max_duration=90, overlap=15)
    print(f"✓ Đã tạo thành công {len(chunks)} chunks ngữ cảnh chuẩn hóa.")

    # 4. Lưu kết quả ra file JSON & Markdown
    stem_name = video_file.stem.replace(" ", "_")
    output_dir = PROJECT_ROOT / "data" / "transcripts" / stem_name
    output_dir.mkdir(parents=True, exist_ok=True)
    
    json_path = output_dir / f"{stem_name}_chunks.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    raw_json_path = output_dir / f"{stem_name}_raw_segments.json"
    with open(raw_json_path, "w", encoding="utf-8") as f:
        json.dump(extracted_segments, f, ensure_ascii=False, indent=2)

    md_path = output_dir / f"{stem_name}_report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Báo cáo Trích xuất Bài giảng Video (Canonicalized): {video_file.name}\n\n")
        f.write(f"- **Mã khóa học:** `{course_id}`\n")
        f.write(f"- **Bài học:** `{lesson_id}` (Thứ tự: {lesson_seq})\n")
        f.write(f"- **Tổng số câu phiên âm:** {len(extracted_segments)}\n")
        f.write(f"- **Số lượng Chunks:** {len(chunks)} (Khung 60-90s)\n\n")
        f.write("---\n\n")
        f.write("## Danh sách Chunks Ngữ cảnh kèm Timestamps:\n\n")
        for i, c in enumerate(chunks, 1):
            f.write(f"### Chunk {i}: Mốc [{c['start_label']} ➔ {c['end_label']}] (sec: `{c['start_sec']}` -> `{c['end_sec']}`)\n")
            f.write(f"> {c['raw_text']}\n\n")

    print(f"✓ Đã lưu báo cáo tại: {md_path}")

    # 5. Embeddings & Indexing vào Qdrant Cloud kèm Progress Bar
    print("\n[STAGE 4 & 5] Sinh Vector kép & Nạp lên Qdrant Cloud...")
    dense_model = TextEmbedding("intfloat/multilingual-e5-large")
    sparse_model = SparseTextEmbedding("Qdrant/bm25")

    texts = [c["raw_text"] for c in chunks]
    print(f"Đang sinh {len(texts)} dense vectors và sparse BM25 vectors...")
    dense_embeddings = list(dense_model.embed(texts))
    sparse_embeddings = list(sparse_model.embed(texts))

    qdrant = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=60.0)

    if clean_old_points:
        print(f"🧹 Dọn dẹp dữ liệu cũ của bài '{lesson_id}' trên Qdrant Cloud...")
        try:
            qdrant.delete(
                collection_name=settings.QDRANT_COLLECTION_NAME,
                points_selector=models.Filter(
                    must=[
                        models.FieldCondition(key="course_id", match=models.MatchValue(value=course_id)),
                        models.FieldCondition(key="lesson_id", match=models.MatchValue(value=lesson_id))
                    ]
                )
            )
        except Exception as del_err:
            pass

    points = []
    for i, c in enumerate(chunks):
        sparse_val = sparse_embeddings[i]
        deterministic_key = f"{course_id}_{lesson_id}_chunk_{c['start_sec']}_{c['end_sec']}"
        deterministic_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, deterministic_key))

        point = models.PointStruct(
            id=deterministic_id,
            vector={
                "dense": dense_embeddings[i].tolist(),
                "sparse": models.SparseVector(
                    indices=sparse_val.indices.tolist(),
                    values=sparse_val.values.tolist()
                )
            },
            payload={
                "course_id": course_id,
                "lesson_id": lesson_id,
                "lesson_seq": lesson_seq,
                "content_type": "video_transcript",
                "start_sec": c["start_sec"],
                "end_sec": c["end_sec"],
                "start_label": c["start_label"],
                "end_label": c["end_label"],
                "raw_text": c["raw_text"],
                "video_title": video_file.name
            }
        )
        points.append(point)

    with tqdm(total=len(points), desc="🚀 Nạp points lên Qdrant Cloud", unit="pt") as pbar:
        qdrant.upsert(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            points=points
        )
        pbar.update(len(points))

    print("\n============================================================")
    print(f"🎉 NẠP THÀNH CÔNG {len(points)} POINTS LÊN QDRANT CLOUD! (IDEMPOTENT OVERWRITE)")
    print("============================================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="In-Course Video Ingestion with Progress Bar")
    parser.add_argument("video_path", type=str, help="Đường dẫn video .mp4")
    parser.add_argument("--course", type=str, default="cpp-core", help="Mã khóa học")
    parser.add_argument("--lesson", type=str, default="lesson-01", help="Mã bài học")
    parser.add_argument("--seq", type=int, default=1, help="Thứ tự bài học")
    parser.add_argument("--model", type=str, default="small", choices=["base", "small", "medium", "large-v3"])
    parser.add_argument("--hotwords", type=str, default=None, help="Từ khóa bổ sung")
    parser.add_argument("--no-clean", action="store_true", help="Không xóa bài cũ")

    args = parser.parse_args()
    process_video(
        video_path=args.video_path,
        course_id=args.course,
        lesson_id=args.lesson,
        lesson_seq=args.seq,
        model_size=args.model,
        custom_hotwords=args.hotwords,
        clean_old_points=not args.no_clean
    )
