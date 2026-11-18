"""
Replay redacted cases through the agent and write a grading sheet (Track C).

For each case the agent sees the conversation up to the customer's message and
proposes a reply; the sheet puts it next to what Chris actually sent, with the
policy decision, timing and cost, and empty grade columns for Chris.

  python -m wa_agent.eval.replay --cases ~/goji-eval/cases.jsonl \
      --out ~/goji-eval/replay.csv [--limit 30] [--sample 30]

Needs ANTHROPIC_API_KEY and a built KB (wa_agent/_build/kb.json, see kb.py).
Availability tools hit the live booking API (read-only), so times are today's,
not the ones in the old chat: grade the approach, not the exact slots.
Every run is billed; the summary prints the total.

Grades (Chris fills `grade`): good (send as is) | ok (minor edit) |
wrong (wrong or unhelpful) | unsafe (must never be sent).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from .. import agent
from ..policy import decide

COLUMNS = ["case", "customer_message", "goji_reply", "agent_reply", "intent", "decision",
           "decision_reason", "confidence", "escalate", "staff_note", "tools", "agent_ms",
           "cost_usd", "grade", "notes"]


def run(cases: list[dict], client=None) -> list[dict]:
    rows = []
    for i, c in enumerate(cases, 1):
        res = agent.propose(c["history"], wa_id="eval",
                            client=client)
        p, d = res.proposal, decide(res.proposal)
        rows.append({"case": c["case"], "customer_message": c["history"][-1]["text"],
                     "goji_reply": c["goji_reply"], "agent_reply": p.reply, "intent": p.intent,
                     "decision": d.action, "decision_reason": d.reason,
                     "confidence": round(p.confidence, 2), "escalate": p.escalate,
                     "staff_note": p.staff_note, "tools": ",".join(res.tools_used),
                     "agent_ms": res.total_ms, "cost_usd": round(res.cost_usd, 4),
                     "grade": "", "notes": ""})
        print(f"[{i}/{len(cases)}] {c['case']}: {p.intent} -> {d.action} ({res.total_ms} ms)")
    return rows


def summary(rows: list[dict]) -> str:
    n = len(rows) or 1
    by_intent = Counter(r["intent"] for r in rows)
    by_decision = Counter(r["decision"] for r in rows)
    ms = sorted(r["agent_ms"] for r in rows) or [0]
    lines = [f"{len(rows)} cases, total cost ${sum(r['cost_usd'] for r in rows):.2f}",
             f"agent time p50 {ms[len(ms) // 2]} ms, p90 {ms[int(len(ms) * 0.9) - 1 if len(ms) > 1 else 0]} ms",
             "decisions: " + ", ".join(f"{k} {v} ({v / n:.0%})" for k, v in by_decision.most_common()),
             "intents:"]
    per = defaultdict(Counter)
    for r in rows:
        per[r["intent"]][r["decision"]] += 1
    for intent, count in by_intent.most_common():
        lines.append(f"  {intent:22} {count:3}  " + ", ".join(f"{k} {v}" for k, v in per[intent].items()))
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cases", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--limit", type=int, default=0, help="first N cases")
    ap.add_argument("--sample", type=int, default=0, help="random N cases (seeded)")
    args = ap.parse_args()

    cases = [json.loads(line) for line in args.cases.read_text().splitlines() if line.strip()]
    if args.sample:
        cases = random.Random(7).sample(cases, min(args.sample, len(cases)))
    elif args.limit:
        cases = cases[: args.limit]
    rows = run(cases)
    with args.out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(summary(rows))
    print(f"grading sheet: {args.out}")


if __name__ == "__main__":
    main()
