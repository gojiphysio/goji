"""
Replay redacted cases through the agent and write a grading sheet (Track C).

For each case the agent sees the conversation up to the customer's message and
proposes a reply; the sheet puts it next to what Chris actually sent, with the
policy decision, timing and cost, and empty grade columns for Chris.

  python -m wa_agent.eval.replay --cases ~/goji-eval/cases.jsonl \
      --out ~/goji-eval/replay.csv [--limit 30] [--sample 30] \
      [--category new-enquiries,rescheduling] [--include-b2b]

Runs on whichever backend config selects: the Messages API (needs
ANTHROPIC_API_KEY) or the local CLI (WA_AGENT_BACKEND=cli; latency then
includes CLI start-up, so it isn't the production number). Needs a built KB
(wa_agent/_build/kb.json, see kb.py).
Partner (b2b) chats, e.g. doctors' referrals, are skipped unless
--include-b2b. --sample draws the same number of cases from each category
(seeded), so short new-enquiry chats aren't drowned out by long regular ones.
Availability tools hit the live booking API (read-only), so times are today's,
not the ones in the old chat: grade the approach, not the exact slots.
Every run is billed; the summary prints the total.

Grades (Chris fills `grade`; `ai_grade`/`ai_note` are for a first pass by a
model or a person, kept apart): good (send as is) | ok (minor edit) |
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

COLUMNS = ["case", "category", "customer_message", "goji_reply", "agent_reply", "intent",
           "decision", "decision_reason", "confidence", "escalate", "hours_to_appointment",
           "staff_note", "tools", "agent_ms", "cost_usd", "ai_grade", "ai_note", "grade", "notes"]


def select(cases: list[dict], *, include_b2b: bool = False, categories: list[str] = (),
           sample: int = 0, limit: int = 0, seed: int = 7) -> list[dict]:
    """Filter (b2b, category), then a stratified seeded sample or the first N."""
    cases = [c for c in cases if include_b2b or not c.get("b2b")]
    if categories:
        cases = [c for c in cases if c.get("category", "") in categories]
    if sample:
        by_cat: dict[str, list[dict]] = defaultdict(list)
        for c in cases:
            by_cat[c.get("category", "")].append(c)
        rng = random.Random(seed)
        for pool in by_cat.values():
            rng.shuffle(pool)
        picked: list[dict] = []
        # round-robin over categories until N cases or every pool is empty
        while len(picked) < sample and any(by_cat.values()):
            for cat in sorted(by_cat):
                if by_cat[cat] and len(picked) < sample:
                    picked.append(by_cat[cat].pop())
        return picked
    return cases[:limit] if limit else cases


def row_for(case: dict, res) -> dict:
    p, d = res.proposal, decide(res.proposal)
    return {"case": case["case"], "category": case.get("category", ""),
            "customer_message": case["history"][-1]["text"], "goji_reply": case["goji_reply"],
            "agent_reply": p.reply, "intent": p.intent, "decision": d.action,
            "decision_reason": d.reason, "confidence": round(p.confidence, 2),
            "escalate": p.escalate,
            "hours_to_appointment": getattr(p, "hours_to_appointment", -1),
            "staff_note": p.staff_note, "tools": ",".join(res.tools_used),
            "agent_ms": res.total_ms, "cost_usd": round(res.cost_usd or 0, 4),
            "ai_grade": "", "ai_note": "", "grade": "", "notes": ""}


def run(cases: list[dict], client=None, on_row=None, chat_clock: bool = False) -> list[dict]:
    """chat_clock: tell the agent "now" is when the customer wrote (so "next
    Sat" and old dates read right) instead of today. Availability tools still
    answer for today's calendar either way."""
    rows = []
    for i, c in enumerate(cases, 1):
        now = (c["history"][-1].get("ts") or None) if chat_clock else None
        res = agent.propose(c["history"], wa_id="eval", client=client, now=now)
        row = row_for(c, res)
        rows.append(row)
        if on_row:
            on_row(row)
        print(f"[{i}/{len(cases)}] {c['case']} ({row['category'] or '-'}): "
              f"{row['intent']} -> {row['decision']} ({row['agent_ms']} ms)", flush=True)
    return rows


def summary(rows: list[dict]) -> str:
    n = len(rows) or 1
    by_intent = Counter(r["intent"] for r in rows)
    by_decision = Counter(r["decision"] for r in rows)
    ms = sorted(r["agent_ms"] for r in rows) or [0]
    lines = [f"{len(rows)} cases, total cost ${sum(r['cost_usd'] for r in rows):.2f}",
             f"agent time p50 {ms[len(ms) // 2]} ms, p90 {ms[int(len(ms) * 0.9) - 1 if len(ms) > 1 else 0]} ms, "
             f"total {sum(ms) / 1000:.0f} s",
             "decisions: " + ", ".join(f"{k} {v} ({v / n:.0%})" for k, v in by_decision.most_common()),
             "categories:"]
    per_cat = defaultdict(Counter)
    for r in rows:
        per_cat[r.get("category") or "-"][r["decision"]] += 1
    for cat, cnt in sorted(per_cat.items()):
        lines.append(f"  {cat:28} {sum(cnt.values()):3}  " + ", ".join(f"{k} {v}" for k, v in cnt.items()))
    lines.append("intents:")
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
    ap.add_argument("--sample", type=int, default=0,
                    help="N cases, stratified by category (seeded)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--category", default="", help="comma-separated categories to keep")
    ap.add_argument("--include-b2b", action="store_true", help="also replay partner chats")
    ap.add_argument("--chat-clock", action="store_true",
                    help="set the agent's 'now' to the customer's message time, not today")
    args = ap.parse_args()

    cases = [json.loads(line) for line in args.cases.read_text().splitlines() if line.strip()]
    cases = select(cases, include_b2b=args.include_b2b,
                   categories=[c for c in args.category.split(",") if c],
                   sample=args.sample, limit=args.limit, seed=args.seed)
    # Written row by row, so an interrupted run keeps what it has.
    with args.out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()

        def write(row: dict) -> None:
            w.writerow(row)
            f.flush()

        rows = run(cases, on_row=write, chat_clock=args.chat_clock)
    print(summary(rows))
    print(f"grading sheet: {args.out}")


if __name__ == "__main__":
    main()
