"""
Focused unit and regression tests for Group 1 & Group 2 optimizations:
1. Paraphrased curriculum navigation ("bài mảng 1 chiều ở vị trí nào trong khóa học")
   without hardcoded phrase lists, and CurriculumService.semantic_search_lessons
   without "query: query: " double prefix.
2. EmbeddingService.embed_query_dense bounded LRU caching consistency and
   model call deduplication.
3. context_assembly_node keeping messages[0] (system prompt) static across turns
   while placing conv_summary, glossary, and soft-nudge extensions in user content.
4. chat.py timestamp sanitizer and cleaner leaving no dangling "|" or empty
   "📍 **Mốc video bài giảng:**" lines.
"""

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.agent.prompts import SOCRATIC_GROUNDED_PROMPT, get_academic_glossary_prompt_extension
from app.agent.router import get_intent_router
from app.config import settings
from app.services.chat import (
    StreamingTimestampSanitizer,
    clean_dangling_timestamp_artifacts,
    sanitize_timestamp_tags,
)
from app.services.chat_graph import context_assembly_node
from app.services.curriculum import get_curriculum_service
from app.services.embedding import EmbeddingService, get_embedding_service


def test_paraphrased_curriculum_navigation_and_no_double_query_prefix():
    """
    "bài mảng 1 chiều ở vị trí nào trong khóa học" must activate
    is_curriculum_navigation via ML similarity (not hardcoded phrase lists),
    and CurriculumService.semantic_search_lessons must emit exactly one "query: "
    prefix to dense_model.embed (never "query: query: ").
    """
    router_src = Path("app/agent/router.py").read_text(encoding="utf-8")
    assert "ở vị trí nào trong khóa học" not in router_src

    router = get_intent_router()
    prompt = "bài mảng 1 chiều ở vị trí nào trong khóa học"
    is_nav, nav_score = router.is_curriculum_navigation(prompt)
    assert is_nav is True
    assert nav_score >= 0.865

    emb_svc = get_embedding_service()
    curr_svc = get_curriculum_service()

    seen_embed_inputs = []
    orig_embed = emb_svc.dense_model.embed

    def _spy_embed(texts, *args, **kwargs):
        text_list = list(texts)
        seen_embed_inputs.extend(text_list)
        return orig_embed(text_list, *args, **kwargs)

    emb_svc.embed_query_dense.cache_clear()
    emb_svc.dense_model.embed = _spy_embed
    try:
        results = curr_svc.semantic_search_lessons(prompt, top_k=3)
    finally:
        emb_svc.dense_model.embed = orig_embed
        emb_svc.embed_query_dense.cache_clear()

    assert len(results) > 0
    assert seen_embed_inputs, "Expected dense_model.embed to be invoked after cache_clear()"
    for item in seen_embed_inputs:
        assert item.startswith("query: ")
        assert not item.lower().startswith("query: query:")

    # Direct concept lookup also resolves cleanly to array lesson(s)
    direct_results = curr_svc.semantic_search_lessons("mảng 1 chiều", top_k=3)
    assert len(direct_results) > 0
    top_score, top_lesson = direct_results[0]
    assert top_score >= 0.78
    assert "mảng" in top_lesson.get("title", "").lower()


def test_embed_query_dense_lru_cache_consistency_and_dedup():
    """
    embed_query_dense must normalize redundant 'query:' prefixes, return
    consistent vectors across repeated calls, return fresh list copies,
    and avoid repeated dense_model.embed calls on identical normalized text.
    """
    svc = EmbeddingService.__new__(EmbeddingService)
    call_inputs = []

    def _fake_embed(texts):
        batch = list(texts)
        call_inputs.append(batch)
        return [np.array([0.25, -0.5, 0.75, 1.0], dtype=np.float32)]

    svc.dense_model = MagicMock()
    svc.dense_model.embed.side_effect = _fake_embed

    svc._embed_query_dense_cached.cache_clear()
    try:
        v1 = svc.embed_query_dense("mảng 1 chiều")
        v2 = svc.embed_query_dense("  mảng 1 chiều  ")
        v3 = svc.embed_query_dense("query: mảng 1 chiều")
        v4 = svc.embed_query_dense("query: query: mảng 1 chiều")

        assert v1 == v2 == v3 == v4
        assert v1 == pytest.approx([0.25, -0.5, 0.75, 1.0])
        assert v1 is not v2

        # Mutating returned list must not corrupt cached tuple
        v1[0] = 999.0
        v5 = svc.embed_query_dense("mảng 1 chiều")
        assert v5[0] == pytest.approx(0.25)

        assert len(call_inputs) == 1
        assert call_inputs[0] == ["query: mảng 1 chiều"]

        info = svc.embed_query_dense.cache_info()
        assert info.misses == 1
        assert info.hits == 4
        assert info.maxsize == 512
    finally:
        svc._embed_query_dense_cached.cache_clear()


@pytest.mark.asyncio
async def test_context_assembly_node_static_system_prompt_across_turns():
    """
    context_assembly_node must keep messages[0] (system prompt) 100% static
    across turns (for vLLM KV prefix caching) and place conversation_summary,
    academic glossary extension, and soft-nudge text into user content.
    """
    state_t1 = {
        "prompt": "Biến int là gì?",
        "user_message_content": "Câu hỏi: Biến int là gì?",
        "system_prompt": SOCRATIC_GROUNDED_PROMPT,
        "messages": [],
        "conversation_summary": None,
    }
    res_t1 = await context_assembly_node(state_t1)

    conv_summary = "Học viên đã thảo luận về kiểu int và tràn số ở lượt trước."
    long_history = []
    for i in range(settings.SOFT_NUDGE_TURN_TRIGGER):
        long_history.append({"role": "user", "content": f"Câu hỏi lượt {i + 1}"})
        long_history.append({"role": "assistant", "content": f"Giải thích lượt {i + 1}"})

    glossary_prompt = "Giải thích con trỏ và mảng trong C++"
    expected_glossary = get_academic_glossary_prompt_extension(glossary_prompt).strip()
    assert expected_glossary

    state_t2 = {
        "prompt": glossary_prompt,
        "user_message_content": f"Câu hỏi: {glossary_prompt}",
        "system_prompt": SOCRATIC_GROUNDED_PROMPT,
        "messages": long_history,
        "conversation_summary": conv_summary,
    }
    res_t2 = await context_assembly_node(state_t2)

    msg0_t1 = res_t1["assembled_messages"][0]
    msg0_t2 = res_t2["assembled_messages"][0]
    assert msg0_t1["role"] == "system"
    assert msg0_t2["role"] == "system"
    assert msg0_t1["content"] == SOCRATIC_GROUNDED_PROMPT
    assert msg0_t2["content"] == SOCRATIC_GROUNDED_PROMPT
    assert msg0_t1["content"] == msg0_t2["content"]

    final_user_msg = res_t2["assembled_messages"][-1]
    assert final_user_msg["role"] == "user"
    assert conv_summary in final_user_msg["content"]
    assert expected_glossary in final_user_msg["content"]
    assert "[HƯỚNG DẪN SƯ PHẠM ĐA LƯỢT]" in final_user_msg["content"]
    assert final_user_msg["content"] == res_t2["user_message_content"]

    assert conv_summary not in msg0_t2["content"]
    assert expected_glossary not in msg0_t2["content"]


def test_chat_timestamp_sanitizer_and_cleaner_no_dangling_pipes_or_empty_footer():
    """
    clean_dangling_timestamp_artifacts, sanitize_timestamp_tags, and
    StreamingTimestampSanitizer must remove empty "📍 **Mốc video bài giảng:**"
    lines and dangling "|" separators while preserving valid timestamps,
    Markdown tables, and C++ code fences.
    """
    # 1. Direct cleaner: drops empty footer & dangling pipes, preserves code/tables
    raw = (
        "Giải thích ngắn gọn.\n\n"
        "```cpp\n"
        "int flags = 1 | 2;\n"
        "if (a || b) { return 0; }\n"
        "```\n\n"
        "| Kiểu | Kích thước |\n"
        "| --- | --- |\n\n"
        "📍 **Mốc video bài giảng:**   |   \n"
    )
    cleaned = clean_dangling_timestamp_artifacts(raw)
    assert "Mốc video bài giảng" not in cleaned
    assert "int flags = 1 | 2;" in cleaned
    assert "if (a || b)" in cleaned
    assert "| Kiểu | Kích thước |" in cleaned
    assert "| --- | --- |" in cleaned

    # Non-table dangling pipes are cleaned without leaving trailing "|"
    dangling = "Xem phần tiếp theo: | \nNội dung chính. | "
    cleaned_dangling = clean_dangling_timestamp_artifacts(dangling)
    assert "|" not in cleaned_dangling
    assert cleaned_dangling == "Xem phần tiếp theo:\nNội dung chính."

    # 2. sanitize_timestamp_tags: all invalid tags stripped -> footer disappears cleanly
    all_invalid = (
        "Bạn hãy thử kiểm tra lại điều kiện dừng.\n\n"
        "📍 **Mốc video bài giảng:** "
        '<timestamp sec="999">16:39</timestamp> | <timestamp sec="888">14:48</timestamp>'
    )
    sanitized_empty = sanitize_timestamp_tags(all_invalid, valid_secs={10})
    assert "<timestamp" not in sanitized_empty
    assert "Mốc video bài giảng" not in sanitized_empty
    assert "|" not in sanitized_empty
    assert sanitized_empty == "Bạn hãy thử kiểm tra lại điều kiện dừng."

    # 3. sanitize_timestamp_tags: 1 invalid + 1 valid tag -> clean single timestamp, no "|"
    mixed = (
        "Xem lại phần khai báo mảng.\n\n"
        "📍 **Mốc video bài giảng:** "
        '<timestamp sec="999">16:39</timestamp> | <timestamp sec="45">00:45</timestamp> | '
    )
    sanitized_mixed = sanitize_timestamp_tags(mixed, valid_secs={45})
    assert sanitized_mixed == (
        'Xem lại phần khai báo mảng.\n\n'
        '📍 **Mốc video bài giảng:** <timestamp sec="45">00:45</timestamp>'
    )

    # 4. StreamingTimestampSanitizer: chunked tokens with dropped tag + trailing "|"
    tokens = [
        "Gợi ý bước đầu.\n\n",
        "📍 **Mốc video bài giảng:** ",
        '<timestamp sec="999">',
        "16:39",
        "</timestamp>",
        " | ",
        '<timestamp sec="45">',
        "00:45",
        "</timestamp>",
    ]
    sanitizer = StreamingTimestampSanitizer(valid_secs={45})
    streamed = []
    for tok in tokens:
        streamed.extend(sanitizer.process(tok))
    streamed.extend(sanitizer.flush())
    streamed_text = clean_dangling_timestamp_artifacts("".join(streamed))
    assert streamed_text == (
        'Gợi ý bước đầu.\n\n'
        '📍 **Mốc video bài giảng:** <timestamp sec="45">00:45</timestamp>'
    )

    # 5. StreamingTimestampSanitizer: trailing " | " after single invalid tag is suppressed
    tokens_single_invalid = [
        "Nội dung.\n\n",
        "📍 **Mốc video bài giảng:** ",
        '<timestamp sec="999">16:39</timestamp>',
        " | ",
    ]
    sanitizer2 = StreamingTimestampSanitizer(valid_secs={45})
    streamed2 = []
    for tok in tokens_single_invalid:
        streamed2.extend(sanitizer2.process(tok))
    streamed2.extend(sanitizer2.flush())
    streamed2_text = clean_dangling_timestamp_artifacts("".join(streamed2))
    assert streamed2_text == "Nội dung."
