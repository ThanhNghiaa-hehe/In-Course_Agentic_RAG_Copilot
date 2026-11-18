"""
Focused regression tests for the 4 session 7aky9 debug fixes:
1. `_build_lightweight_future_chunk` never steals an unrelated lesson's
   `video_title`/`start_sec` (`lesson-64`/`lesson-74`) when `target_seq` is 11 or 14,
   and `CurriculumService.get_lesson_timestamps` prioritizes non-preamble scopes.
2. `"ngoài mảng 1 chiều ra, tôi muốn học thêm về mảng 2 chiều"` at `lesson_seq=11`
   does NOT stay `grounded` on low-confidence `lesson-03` chunks when `lesson-14` is available.
3. `"trong bài này chúng ta cần lưu ý việc gì"` at `lesson_seq=11`
   prioritizes `lesson_seq=11` chunks over `lesson_seq=7`.
4. `StreamingTimestampSanitizer` buffers `" | "` before an invalid `<timestamp>`
   so `<valid> | <invalid>` emits ONLY `<valid>` with no dangling `" | "`.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.chat import StreamingTimestampSanitizer
from app.services.curriculum import get_curriculum_service
from app.services.retrieval import RetrievalService


def _make_hit(
    hit_id: str,
    score: float,
    lesson_seq: int,
    content_type: str = "video_transcript",
    raw_text: str = "Nội dung bài giảng C++ chi tiết.",
    video_title: str = "",
    start_sec: int = 100,
    end_sec: int = 160,
    code_scope: str = "",
    approx_video_sec=None,
):
    payload = {
        "lesson_id": f"lesson-{lesson_seq:02d}",
        "lesson_seq": lesson_seq,
        "content_type": content_type,
        "raw_text": raw_text,
    }
    if content_type == "code_ast":
        payload.update(
            {
                "file_path": f"lesson_{lesson_seq:02d}/main.cpp",
                "language": "cpp",
                "code_scope": code_scope or "function_main",
                "start_line": 1,
                "end_line": 15,
                "context_code": raw_text,
                "approx_video_sec": approx_video_sec,
            }
        )
    else:
        payload.update(
            {
                "video_title": video_title or f"lesson-{lesson_seq:02d}_lecture.mp4",
                "start_sec": start_sec,
                "end_sec": end_sec,
                "start_label": f"{start_sec // 60:02d}:{start_sec % 60:02d}",
                "end_label": f"{end_sec // 60:02d}:{end_sec % 60:02d}",
            }
        )
    return SimpleNamespace(id=hit_id, score=score, payload=payload)


def _make_mock_embedding_service(rerank_fn):
    emb = MagicMock()
    emb.embed_query_dense.return_value = [0.1] * 8
    emb.embed_query_sparse.return_value = ([1, 2], [0.5, 0.5])
    emb.rerank_documents_async = AsyncMock(side_effect=rerank_fn)
    return emb


# ---------------------------------------------------------------------------
# Fix 1: _build_lightweight_future_chunk never steals lesson-64 / lesson-74
# ---------------------------------------------------------------------------
def test_build_lightweight_future_chunk_never_steals_unrelated_lesson():
    c_svc = get_curriculum_service()

    # Case A: target_seq=11 while future_points only has unrelated lesson-64 hit
    unrelated_64 = [
        _make_hit(
            "hit-64",
            0.91,
            lesson_seq=64,
            video_title="lesson-64_64_-_OOP_Ke_Thua.mp4",
            start_sec=999,
        )
    ]
    chunk_11 = RetrievalService._build_lightweight_future_chunk(
        future_points=unrelated_64,
        target_seq=11,
        c_svc=c_svc,
        matched_lesson=c_svc.get_lesson_by_seq(11),
    )
    assert chunk_11 is not None
    assert chunk_11["lesson_seq"] == 11
    assert "lesson-64" not in chunk_11["video_title"]
    assert chunk_11["start_sec"] != 999

    ts_11 = c_svc.get_lesson_timestamps(11)
    if ts_11:
        # Non-preamble timestamp must precede preamble
        non_preambles = [t for t in ts_11 if t["title"].lower() != "preamble"]
        if non_preambles:
            assert ts_11[0]["title"].lower() != "preamble"
        assert chunk_11["start_sec"] == ts_11[0]["sec"]

    # Case B: target_seq=14 while future_points only has unrelated lesson-74 hit
    unrelated_74 = [
        _make_hit(
            "hit-74",
            0.89,
            lesson_seq=74,
            video_title="lesson-74_74_-_File_Handling.mp4",
            start_sec=1888,
        )
    ]
    chunk_14 = RetrievalService._build_lightweight_future_chunk(
        future_points=unrelated_74,
        target_seq=14,
        c_svc=c_svc,
        matched_lesson=c_svc.get_lesson_by_seq(14),
    )
    assert chunk_14 is not None
    assert chunk_14["lesson_seq"] == 14
    assert "lesson-74" not in chunk_14["video_title"]
    assert chunk_14["start_sec"] != 1888

    # Case C: when future_points DOES contain target_seq=14, prefer video_transcript over preamble
    mixed_14 = [
        _make_hit(
            "hit-74-other",
            0.95,
            lesson_seq=74,
            video_title="lesson-74_unrelated.mp4",
            start_sec=1888,
        ),
        _make_hit(
            "hit-14-code",
            0.70,
            lesson_seq=14,
            content_type="code_ast",
            code_scope="header_preamble",
            approx_video_sec=15,
        ),
        _make_hit(
            "hit-14-vid",
            0.65,
            lesson_seq=14,
            video_title="lesson-14_14_-_9_C_Lý_Thuyết_Về_Mảng_2_Chiều.mp4",
            start_sec=1334,
        ),
    ]
    chunk_14_matched = RetrievalService._build_lightweight_future_chunk(
        future_points=mixed_14,
        target_seq=14,
        c_svc=c_svc,
        matched_lesson=c_svc.get_lesson_by_seq(14),
    )
    assert chunk_14_matched["lesson_seq"] == 14
    assert chunk_14_matched["start_sec"] == 1334
    assert "lesson-14" in chunk_14_matched["video_title"]


# ---------------------------------------------------------------------------
# Fix 2: Dual-modifier transition query at lesson_seq=11 -> lesson-14 (not lesson-03)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_transition_query_2d_array_at_lesson_11_does_not_stay_grounded_on_lesson_03():
    c_svc = get_curriculum_service()
    query = "ngoài mảng 1 chiều ra, tôi muốn học thêm về mảng 2 chiều"

    # Curriculum resolution must pick lesson 14 (Mảng 2 chiều), not lesson 13 revision or lesson 11
    c_match = c_svc.find_lesson_for_query(
        query, current_lesson_seq=11, preferred_course_id="cpp-core"
    )
    assert c_match is not None
    matched_lesson, _ = c_match
    assert int(matched_lesson["seq"]) == 14

    lesson_03_low_hits = [
        _make_hit(
            "cur-03-a",
            0.55,
            lesson_seq=3,
            raw_text="Giới thiệu biến và kiểu dữ liệu cơ bản trong C++.",
            video_title="lesson-03_bien_va_kieu_du_lieu.mp4",
            start_sec=210,
        ),
        _make_hit(
            "cur-03-b",
            0.48,
            lesson_seq=3,
            raw_text="Cách nhập xuất giá trị từ bàn phím bằng cin và cout.",
            video_title="lesson-03_bien_va_kieu_du_lieu.mp4",
            start_sec=420,
        ),
    ]
    lesson_14_future_hits = [
        _make_hit(
            "fut-14-a",
            0.82,
            lesson_seq=14,
            raw_text="Lý thuyết về mảng 2 chiều, khai báo ma trận int a[100][100] và duyệt hàng cột.",
            video_title="lesson-14_14_-_9_C_Lý_Thuyết_Về_Mảng_2_Chiều.mp4",
            start_sec=1380,
        )
    ]

    recorded_filters = []

    async def _fake_query_points(**kwargs):
        prefetch = kwargs.get("prefetch") or []
        f = prefetch[0].filter if prefetch else None
        recorded_filters.append(f)
        # Inspect filter to distinguish current (lte/eq 11) vs future (eq 14 / gt 11)
        is_future = False
        if f and getattr(f, "must", None):
            for cond in f.must:
                if getattr(cond, "key", None) == "lesson_seq":
                    if getattr(cond, "range", None) is not None and cond.range.gt is not None:
                        is_future = True
                    elif getattr(cond, "match", None) is not None and cond.match.value == 14:
                        is_future = True
        return SimpleNamespace(points=lesson_14_future_hits if is_future else lesson_03_low_hits)

    def _fake_rerank(query: str, documents):
        scores = []
        for doc in documents:
            if "mảng 2 chiều" in doc.lower() or "lesson-14" in doc.lower():
                scores.append(1.5)
            else:
                # Low relevance on lesson-03 (~0.18-0.20 raw_prob)
                scores.append(-2.0)
        return scores

    fake_qdrant = MagicMock()
    fake_qdrant.query_points = AsyncMock(side_effect=_fake_query_points)
    fake_emb = _make_mock_embedding_service(_fake_rerank)

    svc = RetrievalService(client=fake_qdrant, embedding_service=fake_emb)
    res = await svc.search(
        query_text=query,
        course_id="cpp-core",
        current_lesson_seq=11,
        is_continuation_turn=True,
    )

    assert res.status == "out_of_lesson"
    assert res.target_lesson_seq == 14
    assert res.chunks == []
    assert res.future_best_chunk is not None
    assert res.future_best_chunk["lesson_seq"] == 14
    assert res.future_best_chunk["start_sec"] == 1380
    assert "lesson-14" in res.future_best_chunk["video_title"]


# ---------------------------------------------------------------------------
# Fix 3: Current-lesson reference query at lesson_seq=11 prioritizes seq=11 over seq=7
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_current_lesson_reference_at_seq_11_prioritizes_11_over_7():
    c_svc = get_curriculum_service()
    query = "trong bài này chúng ta cần lưu ý việc gì"
    assert c_svc.has_current_lesson_reference(query) is True

    mixed_hits = [
        _make_hit(
            "hit-07",
            0.92,
            lesson_seq=7,
            raw_text="Lưu ý về vòng lặp for và điều kiện dừng ở bài 7.",
            video_title="lesson-07_vong_lap_for.mp4",
            start_sec=300,
        ),
        _make_hit(
            "hit-11-vid",
            0.70,
            lesson_seq=11,
            raw_text="Lưu ý quan trọng về chỉ số mảng 1 chiều từ 0 đến n - 1 và tránh truy cập ngoài biên.",
            video_title="lesson-11_11_-_8_C_Mảng_Một_Chiều.mp4",
            start_sec=1228,
        ),
        _make_hit(
            "hit-11-code",
            0.68,
            lesson_seq=11,
            content_type="code_ast",
            raw_text="int a[100]; for (int i = 0; i < n; i++) cin >> a[i];",
            code_scope="function_main",
            approx_video_sec=520,
        ),
    ]

    captured_current_filters = []

    async def _fake_query_points(**kwargs):
        prefetch = kwargs.get("prefetch") or []
        f = prefetch[0].filter if prefetch else None
        is_future = False
        if f and getattr(f, "must", None):
            for cond in f.must:
                if getattr(cond, "key", None) == "lesson_seq" and getattr(cond, "range", None) is not None and cond.range.gt is not None:
                    is_future = True
        if is_future:
            return SimpleNamespace(points=[])
        captured_current_filters.append(f)
        # Even if mock Qdrant ignores filter and returns mixed hits (seq 7 + seq 11),
        # RetrievalService must keep only seq 11 chunks.
        return SimpleNamespace(points=mixed_hits)

    def _fake_rerank(query: str, documents):
        # Give neutral logits so floor + pre-rerank filter decide cleanly
        return [0.0 for _ in documents]

    fake_qdrant = MagicMock()
    fake_qdrant.query_points = AsyncMock(side_effect=_fake_query_points)
    fake_emb = _make_mock_embedding_service(_fake_rerank)

    svc = RetrievalService(client=fake_qdrant, embedding_service=fake_emb)
    res = await svc.search(
        query_text=query,
        course_id="cpp-core",
        current_lesson_seq=11,
    )

    # Current Qdrant filter must target exact lesson_seq == 11 (MatchValue)
    assert captured_current_filters
    seq_conds = [
        c for c in captured_current_filters[0].must if getattr(c, "key", None) == "lesson_seq"
    ]
    assert seq_conds
    assert seq_conds[0].match is not None and seq_conds[0].match.value == 11

    assert res.status == "grounded"
    assert len(res.chunks) > 0
    assert all(ch["lesson_seq"] == 11 for ch in res.chunks)
    assert all(ch["lesson_seq"] != 7 for ch in res.chunks)


# ---------------------------------------------------------------------------
# Fix 4: StreamingTimestampSanitizer separator buffering (<valid> | <invalid>)
# ---------------------------------------------------------------------------
def _run_sanitizer(tokens, valid_secs):
    sanitizer = StreamingTimestampSanitizer(valid_secs=valid_secs)
    out = []
    for tok in tokens:
        out.extend(sanitizer.process(tok))
    out.extend(sanitizer.flush())
    return "".join(out)


def test_streaming_timestamp_sanitizer_buffers_pipe_before_invalid_tag():
    # Single-chunk emission: <valid> | <invalid> must emit ONLY <valid> with no dangling " | "
    full_line = (
        "📍 **Mốc video bài giảng:** "
        '<timestamp sec="1103">18:23</timestamp> | <timestamp sec="2349">39:09</timestamp>'
    )
    result_single = _run_sanitizer([full_line], valid_secs={1103})
    assert result_single == '📍 **Mốc video bài giảng:** <timestamp sec="1103">18:23</timestamp>'
    assert "|" not in result_single
    assert "2349" not in result_single

    # Split token-by-token around " | " and tag boundaries
    split_tokens = [
        "📍 **Mốc video bài giảng:** ",
        '<timestamp sec="1103">',
        "18:23",
        "</timestamp>",
        " ",
        "|",
        " ",
        '<timestamp sec="2349">',
        "39:09",
        "</timestamp>",
    ]
    result_split = _run_sanitizer(split_tokens, valid_secs={1103})
    assert result_split == '📍 **Mốc video bài giảng:** <timestamp sec="1103">18:23</timestamp>'

    # <valid> | <invalid> | <valid> preserves single separator between the two valid tags
    three_tags = [
        "📍 **Mốc video bài giảng:** ",
        '<timestamp sec="1103">18:23</timestamp>',
        " | ",
        '<timestamp sec="2349">39:09</timestamp>',
        " | ",
        '<timestamp sec="1500">25:00</timestamp>',
    ]
    result_three = _run_sanitizer(three_tags, valid_secs={1103, 1500})
    assert result_three == (
        '📍 **Mốc video bài giảng:** '
        '<timestamp sec="1103">18:23</timestamp> | <timestamp sec="1500">25:00</timestamp>'
    )

    # <invalid> | <valid> emits ONLY <valid> with no leading " | "
    invalid_first = [
        "📍 **Mốc video bài giảng:** ",
        '<timestamp sec="2349">39:09</timestamp>',
        " | ",
        '<timestamp sec="1500">25:00</timestamp>',
    ]
    result_invalid_first = _run_sanitizer(invalid_first, valid_secs={1500})
    assert result_invalid_first == '📍 **Mốc video bài giảng:** <timestamp sec="1500">25:00</timestamp>'

    # Markdown tables and bitwise OR inside text remain intact
    table_text = "| Kiểu | Kích thước |\n| --- | --- |\nBitwise: a | b"
    assert _run_sanitizer([table_text], valid_secs={1103}) == table_text
