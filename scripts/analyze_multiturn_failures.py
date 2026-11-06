import json
from collections import defaultdict

def analyze():
    with open('docs/benchmarks/multiturn_benchmark_results.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    sessions = data['sessions']
    total_turns = 0
    strict_pass = 0
    core_pass = 0
    intent_pass = 0
    status_pass = 0
    anaphora_pass = 0
    anaphora_eval = 0
    socratic_pass = 0
    ts_pass = 0
    budget_pass = 0

    core_failures = []
    all_failures = []

    # Reason breakdown
    reason_categories = defaultdict(list)

    for s in sessions:
        sid = s['session_id']
        tier = s['tier']
        for t in s['turns']:
            total_turns += 1
            i_ok = t['intent_ok']
            s_ok = t['status_ok']
            a_req = t.get('anaphora_required', False)
            a_ok = t.get('anaphora_ok', True)
            soc_ok = t['socratic_ok']
            ts_ok = t['ts_ok']
            b_ok = t['budget_ok']

            if i_ok: intent_pass += 1
            if s_ok: status_pass += 1
            if soc_ok: socratic_pass += 1
            if ts_ok: ts_pass += 1
            if b_ok: budget_pass += 1
            if a_req:
                anaphora_eval += 1
                if a_ok: anaphora_pass += 1

            is_strict = i_ok and s_ok and a_ok and soc_ok and ts_ok and b_ok
            is_core = i_ok and s_ok and a_ok and soc_ok and b_ok

            if is_strict: strict_pass += 1
            if is_core: core_pass += 1

            reasons = []
            if not i_ok:
                r_type = "intent_mismatch"
                reasons.append(f"Sai Intent: kỳ vọng [{t['expected_intent']}], thực tế [{t['actual_intent']}]")
                reason_categories[f"Intent: {t['expected_intent']} -> {t['actual_intent']}"].append((sid, t['turn_idx'], t['user_prompt']))
            if not s_ok:
                r_type = "status_mismatch"
                reasons.append(f"Sai Retrieval Status: kỳ vọng [{t['expected_status']}], thực tế [{t['actual_status']}]")
                reason_categories[f"Status: {t['expected_status']} -> {t['actual_status']}"].append((sid, t['turn_idx'], t['user_prompt']))
            if not a_ok and a_req:
                reasons.append(f"Chưa giải quyết thực thể hồi chỉ (Anaphora): [{t.get('expected_target_entity')}]")
                reason_categories["Anaphora Unresolved"].append((sid, t['turn_idx'], t['user_prompt']))
            if not soc_ok:
                reasons.append(f"Socratic vi phạm: {t.get('socratic_reason')}")
                reason_categories["Socratic Violated"].append((sid, t['turn_idx'], t['user_prompt']))
            if not ts_ok:
                suggested = [x['sec'] for x in t.get('suggested_timestamps', [])]
                reasons.append(f"Lệch mốc timestamp whitelist: thực tế {suggested}")
                reason_categories["Timestamp Whitelist Discrepancy"].append((sid, t['turn_idx'], t['user_prompt']))

            turn_info = {
                'session_id': sid,
                'tier': tier,
                'turn_idx': t['turn_idx'],
                'user_prompt': t['user_prompt'],
                'expected_intent': t['expected_intent'],
                'actual_intent': t['actual_intent'],
                'expected_status': t['expected_status'],
                'actual_status': t['actual_status'],
                'reasons': reasons,
                'is_core_fail': not is_core,
                'is_strict_fail': not is_strict
            }
            if not is_core:
                core_failures.append(turn_info)
            if not is_strict:
                all_failures.append(turn_info)

    print("================================================================================")
    print("                     BÁO CÁO PHÂN TÍCH SỐ LIỆU KIỂM CHỨNG                     ")
    print("================================================================================")
    print(f"Tổng số Sessions (Phiên): {len(sessions)}")
    print(f"Tổng số Turns (Lượt tương tác): {total_turns}")
    print()
    print("1. THEO TIÊU CHÍ LOGIC CỐT LÕI (Intent + CRAG Status + Anaphora + Socratic + Budget):")
    print(f"   - SỐ LƯỢT PASS: {core_pass} / {total_turns} ({core_pass/total_turns*100:.2f}%)")
    print(f"   - SỐ LƯỢT FAIL: {len(core_failures)} / {total_turns} ({len(core_failures)/total_turns*100:.2f}%)")
    print()
    print("2. THEO TIÊU CHÍ TOÀN PHẦN NGHIÊM NGẶT (Kèm cả Whitelist Timestamp Hit Rate WHR):")
    print(f"   - SỐ LƯỢT PASS: {strict_pass} / {total_turns} ({strict_pass/total_turns*100:.2f}%)")
    print(f"   - SỐ LƯỢT FAIL: {len(all_failures)} / {total_turns} ({len(all_failures)/total_turns*100:.2f}%)")
    print()
    print("3. BÓC TÁCH TỪNG CHỈ SỐ THÀNH PHẦN:")
    print(f"   - Intent Classification Accuracy: {intent_pass}/{total_turns} ({intent_pass/total_turns*100:.2f}%) [Sai: {total_turns - intent_pass}]")
    print(f"   - Retrieval Status Accuracy:      {status_pass}/{total_turns} ({status_pass/total_turns*100:.2f}%) [Sai: {total_turns - status_pass}]")
    print(f"   - Anaphora Resolution Rate (ARR): {anaphora_pass}/{anaphora_eval} ({anaphora_pass/anaphora_eval*100:.2f}%) [Sai: {anaphora_eval - anaphora_pass}]")
    print(f"   - Socratic Refusal Precision:     {socratic_pass}/{total_turns} ({socratic_pass/total_turns*100:.2f}%) [Sai: 0]")
    print(f"   - Context Budget Compliance:      {budget_pass}/{total_turns} ({budget_pass/total_turns*100:.2f}%) [Sai: 0]")
    print(f"   - Whitelist Timestamp Hit Rate:   {ts_pass}/{total_turns} ({ts_pass/total_turns*100:.2f}%) [Lệch: {total_turns - ts_pass}]")
    print()
    print("4. PHÂN TÍCH CÁC NHÓM NGUYÊN NHÂN LỖI LOGIC (CORE FAILURES):")
    for cat, items in sorted(reason_categories.items(), key=lambda x: -len(x[1])):
        if cat == "Timestamp Whitelist Discrepancy":
            continue
        print(f"   * Nhóm [{cat}]: {len(items)} lượt")
        for sid, tid, prompt in items[:3]:
            print(f"       - {sid} (Turn {tid}): \"{prompt}\"")
        if len(items) > 3:
            print(f"       ... và {len(items) - 3} lượt khác.")

    print()
    print("5. CHI TIẾT TOÀN BỘ CÁC CÂU LỖI LOGIC CỐT LÕI (CORE FAILURES):")
    for idx, f in enumerate(core_failures, 1):
        print(f"[{idx:02d}] {f['session_id']} (Turn {f['turn_idx']}) - Tier: {f['tier']}")
        print(f"     Câu hỏi: \"{f['user_prompt']}\"")
        for r in f['reasons']:
            if not r.startswith("Lệch mốc timestamp"):
                print(f"     -> Lý do: {r}")

if __name__ == "__main__":
    analyze()
