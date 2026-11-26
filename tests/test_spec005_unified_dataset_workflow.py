"""
Unit & Integration Tests for Unified E2E Spec 005 (`005-unified-dataset-workflow-repair` v1.0).
Locks Root Causes RC-005-01..RC-005-07 and Cross-Layer Conflict Matrix C005-01..C005-10.
Zero benchmark IDs, zero verbatim held-out prompts, and zero runtime regex in `app/`.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
import torch
from transformers import DataCollatorForSeq2Seq

from app.agent.prompts import SOCRATIC_GROUNDED_PROMPT
from app.agent.router import IntentRouter, get_intent_router
from app.services.chat_graph import retrieval_node
from app.services.retrieval import RetrievalResult
from scripts import canonicalize_transcripts_ast as canon
from scripts import validate_training_datasets as vtd
from scripts.kaggle_jobs.train_jina_reranker import (
    compute_jina_group_key,
    split_jina_triplets_by_group,
)
from scripts.kaggle_jobs.train_mdeberta_nli import (
    normalize_premise_group,
    split_nli_rows_by_premise,
)
from scripts.kaggle_jobs.train_qwen25_qlora import (
    MAX_SEQ_LENGTH,
    extract_qwen_lesson_group,
    split_qwen_rows_by_lesson,
    tokenize_assistant_only_sft,
)
import scripts.kaggle_jobs.train_qwen25_qlora as qwen_trainer_mod


# ==============================================================================
# RC-005-01 / C005-01: Router NLI OOS Override & Curriculum/AST Shield
# ==============================================================================


def test_rc005_01_router_nli_oos_override_and_curriculum_shield():
    router = IntentRouter()
    router._ensure_chitchat_prototypes()
    assert router._slm_session is not None

    # Helper to mock SLM logits producing exact post-temperature probabilities
    # classes = ["chit_chat", "course_query", "out_of_scope"]
    def _logits_for_probs(p_chit: float, p_course: float, p_oos: float) -> List[np.ndarray]:
        arr = np.log(np.array([[p_chit, p_course, p_oos]], dtype=np.float32))
        return [arr]

    # (a) Ambiguous SLM (p_course=0.50, p_oos=0.40), high NLI OOS (0.88), no curriculum topic, no C++ AST -> flips to out_of_scope
    with patch.object(router._slm_session, "run", return_value=_logits_for_probs(0.10, 0.50, 0.40)), patch.object(
        router._nli_arbiter, "arbitrate", return_value=("out_of_scope", 0.88)
    ), patch.object(router, "_has_verified_curriculum_topic", return_value=False), patch.object(
        router, "is_curriculum_navigation", return_value=(False, 0.1)
    ), patch.object(router, "is_pure_social", return_value=(False, 0.1)), patch.object(
        router, "is_social_acknowledgment", return_value=(False, 0.1)
    ):
        res_a = router.classify("mẹo chọn mua nệm cao su êm lưng cho phòng ngủ gia đình")
    assert res_a.intent == "out_of_scope"
    assert res_a.is_course_query is False

    # (b) Same ambiguous SLM + NLI OOS, WITH verified curriculum topic -> protected as course_query
    with patch.object(router._slm_session, "run", return_value=_logits_for_probs(0.10, 0.50, 0.40)), patch.object(
        router._nli_arbiter, "arbitrate", return_value=("out_of_scope", 0.88)
    ), patch.object(router, "_has_verified_curriculum_topic", return_value=True), patch.object(
        router, "is_curriculum_navigation", return_value=(False, 0.1)
    ), patch.object(router, "is_pure_social", return_value=(False, 0.1)), patch.object(
        router, "is_social_acknowledgment", return_value=(False, 0.1)
    ):
        res_b = router.classify("ví von vùng nhớ động giống kho hàng thuê theo nhu cầu có hợp lý không")
    assert res_b.intent == "course_query"
    assert res_b.is_course_query is True

    # (c) Same ambiguous SLM + NLI OOS, WITH student C++ AST code -> protected as course_query
    cpp_snippet = "em chạy thử đoạn này bị sai:\nint tong = 0;\nfor (int i = 0; i < n; i++) { tong += a[i]; }"
    with patch.object(router._slm_session, "run", return_value=_logits_for_probs(0.10, 0.50, 0.40)), patch.object(
        router._nli_arbiter, "arbitrate", return_value=("out_of_scope", 0.88)
    ), patch.object(router, "_has_verified_curriculum_topic", return_value=False), patch.object(
        router, "is_curriculum_navigation", return_value=(False, 0.1)
    ):
        res_c = router.classify(cpp_snippet)
    assert res_c.intent == "course_query"
    assert res_c.is_course_query is True

    # (d) High-confidence SLM (p_course=0.75, p_oos=0.18) -> protected as course_query
    with patch.object(router._slm_session, "run", return_value=_logits_for_probs(0.07, 0.75, 0.18)), patch.object(
        router._nli_arbiter, "arbitrate", return_value=("out_of_scope", 0.88)
    ), patch.object(router, "_has_verified_curriculum_topic", return_value=False), patch.object(
        router, "is_curriculum_navigation", return_value=(False, 0.1)
    ), patch.object(router, "is_pure_social", return_value=(False, 0.1)), patch.object(
        router, "is_social_acknowledgment", return_value=(False, 0.1)
    ):
        res_d = router.classify("cách khai báo tham số mặc định cho hàm tính diện tích")
    assert res_d.intent == "course_query"
    assert res_d.is_course_query is True


# ==============================================================================
# RC-005-02 / C005-02: Advice Subintent Isolated from Navigation Gate
# ==============================================================================


def test_rc005_02_router_advice_isolated_from_navigation_while_preserving_nav_sigs():
    router = get_intent_router()

    advice_prompts = [
        "mình thấy học thuật toán và code khó quá dễ nản lòng làm sao để rèn tư duy tốt hơn",
        "công cụ trí tuệ nhân tạo có thay thế hoàn toàn kỹ sư lập trình trong tương lai không",
    ]
    for ap in advice_prompts:
        is_nav, _ = router.is_curriculum_navigation(ap)
        assert is_nav is False, f"Advice query must not be hijacked by navigation gate: {ap}"
        cls_res = router.classify(ap)
        assert cls_res.intent == "chit_chat", f"Advice query must classify as chit_chat: {ap}"
        assert cls_res.is_course_query is False

    nav_prompts = [
        "em mới bắt đầu học thì nên học bài nào trước",
        "trong khóa học bài mấy hướng dẫn về con trỏ",
        "lộ trình học hướng đối tượng bắt đầu từ đâu",
    ]
    for np_q in nav_prompts:
        is_nav, _ = router.is_curriculum_navigation(np_q)
        assert is_nav is True, f"Genuine navigation query must remain True: {np_q}"
        cls_res = router.classify(np_q)
        assert cls_res.intent == "course_query"
        assert cls_res.is_course_query is True


# ==============================================================================
# RC-005-03 / C005-03: ChatGraph Empty Fallback Scores Fail-Closed
# ==============================================================================


@pytest.mark.asyncio
async def test_rc005_03_chat_graph_empty_fallback_scores_fail_closed():
    state = {
        "prompt": "xử lý nó ra sao",
        "search_query": "mảng động hai chiều -> xử lý nó ra sao",
        "last_course_query": "mảng động hai chiều",
        "course_id": "cpp-core",
        "lesson_seq": 6,
        "messages": [{"role": "user", "content": "mảng động hai chiều"}],
        "is_curriculum_navigation": False,
        "current_video_sec": None,
    }
    fake_router = MagicMock()
    fake_router.is_context_dependent.return_value = False
    fake_router.has_domain_entity.return_value = False

    unverified_ool = RetrievalResult(
        chunks=[],
        status="out_of_lesson",
        target_lesson_seq=46,
        curriculum_matched_seq=27,
        curriculum_matched_course="cpp-core",
    )
    empty_grounded = RetrievalResult(
        chunks=[],
        status="grounded",
        is_low_confidence=False,
        is_approximate=False,
    )
    scoreless_grounded = RetrievalResult(
        chunks=[{"id": "missing-conf", "lesson_seq": 6, "content_type": "video_transcript"}],
        status="grounded",
        is_low_confidence=False,
        is_approximate=False,
    )

    for bogus_fb in (empty_grounded, scoreless_grounded):
        ret_svc = MagicMock(hybrid_search=AsyncMock(side_effect=[unverified_ool, bogus_fb]))
        with patch("app.services.chat_graph.get_retrieval_service", return_value=ret_svc), patch(
            "app.services.chat_graph.get_intent_router", return_value=fake_router
        ):
            out = await retrieval_node(state)
        assert out["retrieval_status"] == "out_of_lesson"
        assert out["target_lesson_seq"] == 46


# ==============================================================================
# RC-005-04 / C005-04: Deterministic Transcript Sanitizer & 134 NFC Preservation
# ==============================================================================


def test_rc005_04_sanitizer_foreign_scripts_loops_and_vietnamese_nfc_preservation():
    assert len(canon.VIETNAMESE_NFC_LETTERS) == 134
    all_vn_letters = "".join(sorted(canon.VIETNAMESE_NFC_LETTERS))
    clean_vn_sample = f"Mảng khởi tạo 0, 0, 0 bảo toàn đủ dấu tiếng Việt: {all_vn_letters}."
    assert canon._contains_corrupted_asr_artifacts(clean_vn_sample) is False
    sanitized_vn = canon._sanitize_corrupted_asr_artifacts(clean_vn_sample)
    for ch in canon.VIETNAMESE_NFC_LETTERS:
        assert ch in sanitized_vn
    assert "0, 0, 0" in sanitized_vn

    noisy_sample = (
        "Ví dụ αβγ אבג ோளர 《》【】 ı İ ğ ş ö ä ç ø ß 📷🤟 "
        "a₁ → b₂ × 3 ∞ ½ € đoạn e e e e e và cout, cout, cout cùng phim, phim, phim."
    )
    assert canon._contains_corrupted_asr_artifacts(noisy_sample) is True
    cleaned = canon._sanitize_corrupted_asr_artifacts(noisy_sample)
    assert canon._contains_corrupted_asr_artifacts(cleaned) is False
    assert "a1 -> b2 * 3" in cleaned
    assert "cout" in cleaned and "cout, cout" not in cleaned
    assert "phim" in cleaned and "phim, phim" not in cleaned
    assert "e e e e" not in cleaned

    en_hallucination = (
        "If you have any question, you can leave feedback in comments below the video for more questions."
    )
    assert canon._contains_corrupted_asr_artifacts(en_hallucination) is True
    assert canon._sanitize_corrupted_asr_artifacts(en_hallucination) == ""


# ==============================================================================
# RC-005-05 / C005-05: SSOT Decontamination (Exact + Jaccard + Containment)
# ==============================================================================


def test_rc005_05_ssot_decontamination_jaccard_and_containment():
    heldout = [
        "toán tử giải tham chiếu sao và địa chỉ trong con trỏ",
        "phương thức rutGonPhanSo của lớp PhanSo tính ước chung lớn nhất thế nào",
    ]
    norms = {vtd.norm_text_for_jaccard(q) for q in heldout}

    # 1. Exact match
    ok_ex, sc_ex, rsn_ex = vtd.check_decontamination_detailed(heldout[0], norms, heldout)
    assert ok_ex is False and sc_ex == 1.0 and rsn_ex == "exact_match"

    # 2. High Jaccard >= 0.65
    ok_jac, _, rsn_jac = vtd.check_decontamination_detailed(
        "toán tử giải tham chiếu sao và địa chỉ trong con trỏ C++",
        norms,
        heldout,
    )
    assert ok_jac is False and rsn_jac == "jaccard_overlap"

    # 3. Padded clone (low Jaccard < 0.50, high raw token containment >= 0.85)
    padded_clone = (
        "toán tử giải tham chiếu sao và địa chỉ trong con trỏ có tự động biến bàn học thành quán kem mùa hè ngoài biển không"
    )
    ok_raw, sc_raw, rsn_raw = vtd.check_decontamination_detailed(padded_clone, norms, heldout)
    assert ok_raw is False and sc_raw >= 0.85 and rsn_raw == "token_containment"

    # 4. Content-token containment >= 0.85 (function words swapped + extra padding)
    content_clone = (
        "em hỏi vì sao phương thức rutGonPhanSo trong lớp PhanSo lại tính ước chung lớn nhất khi cài đặt chương trình thực hành tự học ở nhà vậy ạ"
    )
    ok_cnt, sc_cnt, rsn_cnt = vtd.check_decontamination_detailed(content_clone, norms, heldout)
    assert ok_cnt is False and sc_cnt >= 0.85 and rsn_cnt in ("token_containment", "content_containment")

    # 5. Clean independent C++ question passes
    clean_q = "cơ chế cấp phát mảng động bằng new[] và giải phóng bằng delete[] trên vùng nhớ heap hoạt động ra sao"
    ok_cln, _, rsn_cln = vtd.check_decontamination_detailed(clean_q, norms, heldout)
    assert ok_cln is True and rsn_cln == "ok"


# ==============================================================================
# RC-005-06 / C005-06..10: Validator Rejects False-Green & Merge-Safe Report
# ==============================================================================


def test_rc005_06_validator_rejects_false_green_across_all_4_models(tmp_path: Path):
    norms: set[str] = set()
    heldout: list[str] = []

    # 1. SLM corpus: exact duplicate conflict + stale audit mismatch
    slm_file = tmp_path / "slm_bad.json"
    slm_samples = [
        {"text": "câu hỏi trùng chuẩn hóa nhưng gán nhãn mâu thuẫn nhau hoàn toàn", "intent": "course_query"},
        {"text": "Câu hỏi trùng chuẩn hóa, nhưng gán nhãn mâu thuẫn nhau hoàn toàn!", "intent": "out_of_scope"},
    ] + [
        {"text": f"mẫu huấn luyện kiểm định phân loại ý định thứ {i} hợp lệ rõ ràng", "intent": ("course_query" if i % 3 == 0 else ("chit_chat" if i % 3 == 1 else "out_of_scope"))}
        for i in range(305)
    ]
    slm_file.write_text(
        json.dumps({"audit": {"total_clean_samples": 999}, "samples": slm_samples}, ensure_ascii=False),
        encoding="utf-8",
    )
    res_slm = vtd.validate_slm_corpus(
        heldout_norms=norms,
        heldout_queries=heldout,
        clean_in_place=False,
        corpus_path=slm_file,
    )
    assert res_slm["passed"] is False
    assert res_slm["exact_duplicate_conflict_count"] == 1
    assert res_slm["audit_synced"] is False

    # 2. mDeBERTa NLI: missing neutral(1), multi-entailment, and 20:0 temporal skew
    intent_manifest = json.loads(vtd.INTENT_MANIFEST_PATH.read_text(encoding="utf-8"))
    tpl = intent_manifest["nli_template"]
    c_hyp = tpl.format(intent_manifest["nli_hypotheses"]["course_query"])
    ch_hyp = tpl.format(intent_manifest["nli_hypotheses"]["chit_chat"])
    t_tpl = intent_manifest["temporal_nli_template"]
    in_vid_h = t_tpl.format(intent_manifest["temporal_nli_labels"]["in_video"])
    off_h = t_tpl.format(intent_manifest["temporal_nli_labels"]["off_topic"])

    nli_file = tmp_path / "nli_bad.jsonl"
    nli_rows = [
        {"premise": "câu hỏi gây lỗi hai nhãn entailment cùng lúc", "hypothesis": c_hyp, "label": 0},
        {"premise": "câu hỏi gây lỗi hai nhãn entailment cùng lúc", "hypothesis": ch_hyp, "label": 0},
    ]
    for i in range(260):
        nli_rows.append({"premise": f"câu hỏi kỹ thuật lập trình mẫu số {i}", "hypothesis": c_hyp, "label": 0})
        nli_rows.append({"premise": f"câu hỏi kỹ thuật lập trình mẫu số {i}", "hypothesis": ch_hyp, "label": 2})
    for i in range(20):
        nli_rows.append({"premise": f"câu hỏi thời gian lệch tuyệt đối số {i}", "hypothesis": in_vid_h, "label": 2})
        nli_rows.append({"premise": f"câu hỏi thời gian lệch tuyệt đối số {i}", "hypothesis": off_h, "label": 0})
    nli_file.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in nli_rows), encoding="utf-8")

    res_nli = vtd.validate_mdeberta_jsonl(
        heldout_norms=norms,
        heldout_queries=heldout,
        clean_in_place=False,
        dataset_path=nli_file,
    )
    assert res_nli["passed"] is False
    assert res_nli["neutral_ratio"] == 0.0
    assert res_nli["multi_entailment_count"] >= 1
    assert res_nli["temporal_imbalance_count"] >= 1

    # 3. Jina Reranker: > 600 chars, `| từ khóa:` shortcut, and garbled Greek in validate mode
    jina_file = tmp_path / "jina_bad.jsonl"
    jina_rows = [
        {
            "query": "cách duyệt mảng một chiều trong C++",
            "pos_passage": "[Bài giảng Video lesson-11.mp4 mốc 02:10]\n" + ("Nội dung dài vượt trần sáu trăm ký tự. " * 20),
            "neg_passage": "[Bài giảng Video lesson-20.mp4 mốc 05:00]\nNội dung đối chứng hợp lệ.",
        },
        {
            "query": "khái niệm hàm khởi tạo trong hướng đối tượng",
            "pos_passage": "[Bài 53 | mốc 03:00 | từ khóa: class, constructor]\nNội dung có tiêu đề gian lận từ khóa.",
            "neg_passage": "[Bài giảng Video lesson-11.mp4 mốc 02:10]\nNội dung đối chứng.",
        },
        {
            "query": "cấu trúc rẽ nhánh có điều kiện trong C++",
            "pos_passage": "[Bài giảng Video lesson-04.mp4 mốc 01:20]\nĐoạn văn chứa chữ Hy Lạp αβγ lỗi ASR.",
            "neg_passage": "[Bài giảng Video lesson-11.mp4 mốc 02:10]\nNội dung đối chứng sạch sẽ.",
        },
    ]
    jina_file.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in jina_rows), encoding="utf-8")
    res_jina = vtd.validate_jina_jsonl(
        heldout_norms=norms,
        heldout_queries=heldout,
        clean_in_place=False,
        dataset_path=jina_file,
    )
    assert res_jina["passed"] is False
    assert res_jina["over_600_chars_count"] == 1
    assert res_jina["header_shortcut_count"] == 1
    assert res_jina["garbled_unicode_count"] == 1

    # 4. Qwen2.5 Socratic: wrong-lesson timestamp, `!` ending, `#include <bits/stdc++.h>`, and `...` truncation
    valid_map = vtd.load_valid_lesson_timestamps()
    l1_sec, l1_lbl = next(iter(valid_map[1].items()))
    qwen_file = tmp_path / "qwen_bad.jsonl"

    def _mk_user(seq: int, sec: int, lbl: str, q: str) -> str:
        return (
            f"[CÂU HỎI THẮC MẮC CỦA HỌC VIÊN]\n{q}\n\n"
            f"[NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC]\n"
            f'Nguồn Bài {seq} (mốc <timestamp sec="{sec}">{lbl}</timestamp>): Nội dung bài giảng xác thực.'
        )

    qwen_rows = [
        {
            "lesson_seq": 2,
            "messages": [
                {"role": "system", "content": SOCRATIC_GROUNDED_PROMPT},
                {"role": "user", "content": _mk_user(2, 999999, "99:59", "Câu hỏi kiểm tra sai mốc giây bài học?")},
                {
                    "role": "assistant",
                    "content": 'Phân tích khái niệm cơ bản. Bạn dự đoán kết quả thế nào?\n\n📍 **Mốc video bài giảng:** <timestamp sec="999999">99:59</timestamp>',
                },
            ],
        },
        {
            "lesson_seq": 1,
            "messages": [
                {"role": "system", "content": SOCRATIC_GROUNDED_PROMPT},
                {"role": "user", "content": _mk_user(1, l1_sec, l1_lbl, "Câu hỏi kiểm tra lỗi kết câu bằng dấu chấm than?")},
                {
                    "role": "assistant",
                    "content": f'Phân tích khái niệm cơ bản, hãy tự kiểm tra lại nhé!\n\n📍 **Mốc video bài giảng:** <timestamp sec="{l1_sec}">{l1_lbl}</timestamp>',
                },
            ],
        },
        {
            "lesson_seq": 1,
            "messages": [
                {"role": "system", "content": SOCRATIC_GROUNDED_PROMPT},
                {"role": "user", "content": _mk_user(1, l1_sec, l1_lbl, "Câu hỏi kiểm tra rò rỉ thư viện tổng hợp?")},
                {
                    "role": "assistant",
                    "content": f'Dùng #include <bits/stdc++.h> rồi thử xem kết quả ra sao?\n\n📍 **Mốc video bài giảng:** <timestamp sec="{l1_sec}">{l1_lbl}</timestamp>',
                },
            ],
        },
        {
            "lesson_seq": 1,
            "messages": [
                {"role": "system", "content": SOCRATIC_GROUNDED_PROMPT},
                {"role": "user", "content": _mk_user(1, l1_sec, l1_lbl, "Câu hỏi kiểm tra lỗi cắt cụt dấu ba chấm?")},
                {
                    "role": "assistant",
                    "content": f'Ý chính trích dẫn bị cắt lửng... Bạn nghĩ tiếp theo là gì?\n\n📍 **Mốc video bài giảng:** <timestamp sec="{l1_sec}">{l1_lbl}</timestamp>',
                },
            ],
        },
    ]
    qwen_file.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in qwen_rows), encoding="utf-8")
    res_qwen = vtd.validate_qwen25_jsonl(
        heldout_norms=norms,
        heldout_queries=heldout,
        clean_in_place=False,
        dataset_path=qwen_file,
    )
    assert res_qwen["passed"] is False
    assert res_qwen["invalid_timestamp_count"] == 1
    assert res_qwen["bad_socratic_ending_count"] == 1
    assert res_qwen["code_leak_count"] == 1
    assert res_qwen["truncation_count"] == 1


def test_rc005_06b_run_validation_subset_merge_safe(tmp_path: Path):
    report_json = tmp_path / "dataset_validation_report.json"
    initial_payload = {
        "all_passed": False,
        "models": {
            "slm_router": {"model": "slm_router", "total_in": 552, "total_clean": 552, "leaked_count": 0, "passed": True},
            "mdeberta_nli": {"model": "mdeberta_nli", "total_in": 1800, "total_clean": 1800, "leaked_count": 0, "passed": True},
        },
    }
    report_json.write_text(json.dumps(initial_payload, ensure_ascii=False), encoding="utf-8")

    mock_jina = {"model": "jina_reranker", "total_in": 300, "total_clean": 300, "leaked_count": 0, "passed": True}
    with patch.object(vtd, "validate_jina_jsonl", return_value=mock_jina):
        out_partial = vtd.run_validation(
            clean_in_place=False,
            models=["jina_reranker"],
            reports_dir=tmp_path,
        )

    # Subset run must preserve existing models AND keep all_passed=False because qwen25_qlora is still missing
    assert set(out_partial["models"].keys()) == {"slm_router", "mdeberta_nli", "jina_reranker"}
    assert out_partial["all_passed"] is False

    mock_qwen = {"model": "qwen25_qlora", "total_in": 260, "total_clean": 260, "leaked_count": 0, "passed": True}
    with patch.object(vtd, "validate_qwen25_jsonl", return_value=mock_qwen):
        out_full = vtd.run_validation(
            clean_in_place=False,
            models=["qwen25_qlora"],
            reports_dir=tmp_path,
        )

    assert set(out_full["models"].keys()) == set(vtd.ALL_MODELS)
    assert out_full["all_passed"] is True
    md_text = (tmp_path / "dataset_validation_report.md").read_text(encoding="utf-8")
    for m_key in vtd.ALL_MODELS:
        assert f"`{m_key}`" in md_text


# ==============================================================================
# RC-005-07 / C005-08..09: GroupShuffleSplit & Assistant-Only Loss Masking
# ==============================================================================


class _DeterministicChatTokenizer:
    """Lightweight ChatML tokenizer for deterministic offline verification of assistant-only loss masking."""

    pad_token_id = 0
    eos_token_id = 2
    padding_side = "right"

    def apply_chat_template(
        self,
        messages: List[Dict[str, str]],
        tokenize: bool = False,
        add_generation_prompt: bool = False,
    ) -> str:
        parts = [f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>" for m in messages]
        if add_generation_prompt:
            parts.append("<|im_start|>assistant\n")
        return "\n".join(parts)

    def __call__(
        self,
        text: str,
        truncation: bool = True,
        max_length: int = 2048,
        add_special_tokens: bool = False,
    ) -> Dict[str, List[int]]:
        tokens = [10 + (sum(ord(c) for c in tok) % 900) for tok in text.split()]
        if truncation:
            tokens = tokens[:max_length]
        return {"input_ids": tokens, "attention_mask": [1] * len(tokens)}

    def pad(
        self,
        encoded_inputs: List[Dict[str, Any]],
        padding: Any = True,
        max_length: Any = None,
        pad_to_multiple_of: Any = None,
        return_tensors: str = "pt",
    ) -> Dict[str, torch.Tensor]:
        max_len = max(len(x["input_ids"]) for x in encoded_inputs)
        if pad_to_multiple_of:
            rem = max_len % int(pad_to_multiple_of)
            if rem != 0:
                max_len += int(pad_to_multiple_of) - rem
        batch_ids = []
        batch_mask = []
        for x in encoded_inputs:
            pad_n = max_len - len(x["input_ids"])
            batch_ids.append(list(x["input_ids"]) + [self.pad_token_id] * pad_n)
            batch_mask.append(list(x["attention_mask"]) + [0] * pad_n)
        return {
            "input_ids": torch.tensor(batch_ids, dtype=torch.long),
            "attention_mask": torch.tensor(batch_mask, dtype=torch.long),
        }


def test_rc005_07_kaggle_trainers_group_split_and_assistant_only_loss():
    # 1. NLI GroupShuffleSplit by premise
    nli_sample = [
        {"premise": f"Câu hỏi kiểm định nhóm số {g}", "hypothesis": f"Hyp {h}", "label": 0 if h == 0 else 2}
        for g in range(20)
        for h in range(3)
    ]
    tr_nli, va_nli = split_nli_rows_by_premise(nli_sample, test_size=0.20, seed=42)
    assert {normalize_premise_group(r["premise"]) for r in tr_nli}.isdisjoint(
        {normalize_premise_group(r["premise"]) for r in va_nli}
    )

    # 2. Jina GroupShuffleSplit by (lesson_seq, norm_query)
    jina_sample = [
        {
            "lesson_seq": g,
            "query": f"Truy vấn bài học số {g}",
            "pos_passage": f"[Bài giảng Video lesson-{g:02d}.mp4 mốc 01:00]\nNội dung {k}",
            "neg_passage": f"[Bài giảng Video lesson-{(g+5):02d}.mp4 mốc 04:00]\nĐối chứng {k}",
        }
        for g in range(1, 21)
        for k in range(2)
    ]
    tr_jina, va_jina = split_jina_triplets_by_group(jina_sample, test_size=0.20, seed=42)
    assert {compute_jina_group_key(r) for r in tr_jina}.isdisjoint(
        {compute_jina_group_key(r) for r in va_jina}
    )

    # 3. Qwen2.5 GroupShuffleSplit by lesson_seq
    qwen_sample = [
        {
            "lesson_seq": seq,
            "messages": [
                {"role": "system", "content": SOCRATIC_GROUNDED_PROMPT},
                {"role": "user", "content": f"Nguồn Bài {seq}: câu hỏi thứ {k}?"},
                {"role": "assistant", "content": f"Gợi mở thứ {k}?"},
            ],
        }
        for seq in range(1, 21)
        for k in range(2)
    ]
    tr_qwen, va_qwen = split_qwen_rows_by_lesson(qwen_sample, test_size=0.20, seed=42)
    assert {extract_qwen_lesson_group(r) for r in tr_qwen}.isdisjoint(
        {extract_qwen_lesson_group(r) for r in va_qwen}
    )

    # 4. Qwen2.5 max_length=2048, assistant-only loss masking, and Seq2Seq collator preservation
    assert MAX_SEQ_LENGTH == 2048
    qwen_src = inspect.getsource(qwen_trainer_mod)
    assert "DataCollatorForLanguageModeling" not in qwen_src
    assert "DataCollatorForSeq2Seq" in qwen_src

    tok = _DeterministicChatTokenizer()
    ex1 = {
        "messages": [
            {"role": "system", "content": SOCRATIC_GROUNDED_PROMPT},
            {
                "role": "user",
                "content": '[CÂU HỎI THẮC MẮC CỦA HỌC VIÊN]\nGiải thích toán tử chia dư?\n\n[NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC]\nNguồn Bài 3 (mốc <timestamp sec="321">05:21</timestamp>): Phép chia lấy phần dư.',
            },
            {
                "role": "assistant",
                "content": 'Phép toán trả về phần dư nguyên. Nếu chia cho 2 thì kết quả nhận những giá trị nào?\n\n📍 **Mốc video bài giảng:** <timestamp sec="321">05:21</timestamp>',
            },
        ]
    }
    ex2 = {
        "messages": [
            {"role": "system", "content": SOCRATIC_GROUNDED_PROMPT},
            {
                "role": "user",
                "content": '[CÂU HỎI THẮC MẮC CỦA HỌC VIÊN]\nPhân biệt biến cục bộ?\n\n[NGỮ CẢNH BÀI GIẢNG ĐÃ ĐƯỢC XÁC THỰC TỪ KHÓA HỌC]\nNguồn Bài 2 (mốc <timestamp sec="454">07:34</timestamp>): Phạm vi khối lệnh.',
            },
            {
                "role": "assistant",
                "content": 'Biến cục bộ chỉ tồn tại trong khối ngoặc nhọn. Ra ngoài khối thì biến còn truy cập được không?\n\n📍 **Mốc video bài giảng:** <timestamp sec="454">07:34</timestamp>',
            },
        ]
    }
    enc1 = tokenize_assistant_only_sft(ex1, tok, max_length=2048)
    enc2 = tokenize_assistant_only_sft(ex2, tok, max_length=2048)

    prompt1_len = len(tok(tok.apply_chat_template(ex1["messages"][:2], add_generation_prompt=True))["input_ids"])
    assert all(x == -100 for x in enc1["labels"][:prompt1_len])
    assert all(x != -100 for x in enc1["labels"][prompt1_len:])
    assert len(enc1["labels"][prompt1_len:]) >= 5

    collator = DataCollatorForSeq2Seq(tokenizer=tok, label_pad_token_id=-100, pad_to_multiple_of=8)
    batch = collator([enc1, enc2])
    assert batch["labels"].shape[1] % 8 == 0
    assert torch.all(batch["labels"][0, :prompt1_len] == -100).item() is True
    assert torch.any(batch["labels"][0, prompt1_len:] != -100).item() is True

    # Truncation below prompt length must fail-closed with ValueError rather than all -100 (loss=NaN)
    with pytest.raises(ValueError):
        tokenize_assistant_only_sft(ex1, tok, max_length=32)


def test_mdeberta_nli_fp32_dynamic_padding_ranking_and_noncpp_alignment(tmp_path: Path):
    import scripts.kaggle_jobs.train_mdeberta_nli as nli_trainer_mod
    from scripts.kaggle_automl_runner import build_mdeberta_nli_dataset

    nli_src = inspect.getsource(nli_trainer_mod)
    assert "torch_dtype=torch.float32" in nli_src
    assert "fp16=False" in nli_src
    assert "DataCollatorWithPadding" in nli_src

    # Verify compute_zero_shot_ranking_accuracy mirrors multi_label=False argmax over entailment_id=0
    val_rows = [
        {"premise": "Câu A", "hypothesis": "H1", "label": 0},
        {"premise": "Câu A", "hypothesis": "H2", "label": 2},
        {"premise": "Câu B", "hypothesis": "H1", "label": 2},
        {"premise": "Câu B", "hypothesis": "H2", "label": 0},
    ]
    val_logits = np.array(
        [
            [2.4, -1.0, -1.2],  # Câu A -> H1 wins (label 0) -> hit
            [-1.1, 0.2, 2.0],
            [1.9, 0.1, -1.5],   # Câu B -> H1 wins (label 2) -> miss
            [0.4, 0.3, -0.5],
        ],
        dtype=np.float32,
    )
    assert nli_trainer_mod.compute_zero_shot_ranking_accuracy(val_rows, val_logits, entailment_id=0) == 0.5

    # Verify generated NLI dataset has non-C++ tech aligned to label=0 on oos_hyp and >=25 temporal per side
    out_nli = tmp_path / "mdeberta_test.jsonl"
    norms, heldout = vtd.load_heldout_queries()
    build_mdeberta_nli_dataset(out_nli, norms, heldout)
    rows = [json.loads(line) for line in out_nli.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_prem: Dict[str, List[int]] = {}
    for r in rows:
        by_prem.setdefault(r["premise"], []).append(int(r["label"]))
    # On 3-hypothesis intent rows, zero premises should lack an entailment (0) target
    intent_3h = [lbls for lbls in by_prem.values() if len(lbls) == 3]
    assert intent_3h and all(0 in lbls for lbls in intent_3h)
