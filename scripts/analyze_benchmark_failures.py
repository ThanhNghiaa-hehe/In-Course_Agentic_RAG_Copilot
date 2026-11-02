import json
from pathlib import Path

results_file = Path("docs/benchmarks/stage11_results_2026-11-02_19-58-16.json")
with open(results_file, "r", encoding="utf-8") as f:
    d = json.load(f)

cases = d.get("cases", [])
failures = [c for c in cases if not c.get("pass_flags", {}).get("overall_pass", True)]

print(f"================================================================================")
print(f" TỔNG SỐ TEST CASE CÓ CẢNH BÁO / THẤT BẠI: {len(failures)} / {len(cases)}")
print(f"================================================================================")

for idx, f in enumerate(failures, 1):
    pf = f.get("pass_flags", {})
    reasons = []
    if not pf.get("router_ok"):
        reasons.append(f"Router(Act: {f['actual']['intent']} != Exp: {f['expected']['intent']})")
    if not pf.get("status_ok"):
        reasons.append(f"CRAG(Act: {f['actual']['status']} != Exp: {f['expected']['status']})")
    if not pf.get("ts_ok"):
        reasons.append(f"TS(Act: {f['actual']['video_sec']} != Exp: {f['expected']['target_video_sec']}, has_ts: {f['actual']['has_timestamp']})")
    
    r_str = " | ".join(reasons)
    print(f"[{idx:02d}] {f['id']} | Tier: {f['tier']:18s} | Seq: {f['lesson_seq']:2d}")
    print(f"     Query: {f['query']}")
    print(f"     Lý do: {r_str}")
    print()

