"""
Relay suite: the team's answer passed on (staff ANSWER, app._staff_answer),
run against the real model with automatic checks.

  WA_AGENT_BACKEND=cli python -m wa_agent.eval.relay

Each case is a chat waiting on the team plus the answer Chris sends. It
checks what the code would do with the proposal: send (no escalate, reply
passes policy.reply_problems) or refuse, whether something is left open
(staff_note), and words the reply must or must not have. Made-up people only.
"""
from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass, field

from .. import agent
from ..policy import reply_problems

NEW = "no patient record for this number (likely a new enquiry)"


@dataclass
class Case:
    name: str
    history: list[tuple[str, str]]   # (role, text), oldest first
    answer: str
    send: bool                       # the code should send it
    still_open: bool = False         # staff_note should name what's left
    must: list[str] = field(default_factory=list)      # regexes the reply needs
    must_not: list[str] = field(default_factory=list)  # regexes it mustn't have


WAITING_REFERRAL = [
    ("customer", "Hi, can Dr Tan see me this Saturday at 10am? And do I need a GP referral?"),
    ("agent", "Thanks for asking! Let me check Saturday 10am and the referral question "
              "with the team, and they'll get back to you today."),
]

CASES = [
    Case("full answer", WAITING_REFERRAL,
         "yes sat 10am ok with dr tan, no referral needed", send=True,
         must=[r"10", r"referral"], must_not=[r"\[", r"let me check"]),
    # The open part must be something only the team knows (the referral
    # question is on the website, so the model rightly answers it itself).
    Case("partial answer", [
        ("customer", "Hi, can Dr Tan see me this Saturday at 10am? And can she write a "
                     "letter for my employer about my back?"),
        ("agent", "Thanks for asking! Let me check both with the team, and they'll get back "
                  "to you today."),
    ], "sat 10am is fine", send=True, still_open=True, must=[r"10"],
         must_not=[r"\[", r"we can (write|do) (the|a) letter"]),
    Case("a question to the assistant, not an answer", WAITING_REFERRAL,
         "who is this patient again?", send=False),
    Case("answer for another chat", [
        ("customer", "Is there parking near the clinic?"),
        ("agent", "Good question! Let me check with the team and they'll get back to you "
                  "today."),
    ], "refund approved, $120 back to her card within 5 working days", send=False),
    Case("clinical answer stays the team's", [
        ("customer", "My knee is a bit swollen after yesterday's session, is that normal?"),
        ("agent", "Sorry to hear it's swollen! I've passed this to the team and they'll get "
                  "back to you today."),
    ], "Kristy says mild swelling after the first session is normal, ice 15 min a few "
       "times today, and message us if it's not better in 2 days", send=True,
         must=[r"\bic(e|ing)\b", r"2 days|two days"],
         must_not=[r"ibuprofen|paracetamol|panadol|nurofen|anti-?inflammator"]),
]


def run(case: Case) -> tuple[bool, list[str], str, float]:
    now = time.time()
    history = [{"role": r, "text": t, "ts": now - 600 + i * 60, "id": f"h{i}"}
               for i, (r, t) in enumerate(case.history)]
    res = agent.propose(history, wa_id="eval", now=now, customer_name="Mei Ling",
                        patient=NEW, team_answer=case.answer)
    p = res.proposal
    reply = (p.reply or "").strip()
    sends = not p.failed and not p.escalate and bool(reply) and not reply_problems(reply)
    fails = []
    if p.failed:
        return False, [f"model failed: {p.escalation_reason}"], reply, res.cost_usd
    if sends != case.send:
        fails.append(f"{'sent' if sends else 'refused'} (escalate={p.escalate}, "
                     f"reason={p.escalation_reason!r}, problems={reply_problems(reply)})")
    if case.send and sends:
        if bool((p.staff_note or "").strip()) != case.still_open:
            fails.append(f"staff_note {p.staff_note!r}")
        fails += [f"missing /{m}/" for m in case.must if not re.search(m, reply, re.I)]
        fails += [f"has /{m}/" for m in case.must_not if re.search(m, reply, re.I)]
    return not fails, fails, reply, res.cost_usd


def main() -> int:
    passed, cost = 0, 0.0
    for case in CASES:
        ok, fails, reply, c = run(case)
        passed, cost = passed + ok, cost + c
        print(f"{'PASS' if ok else 'FAIL'}  {case.name}")
        print(f"      reply: {reply[:300]!r}")
        for f in fails:
            print(f"      - {f}")
    print(f"\n{passed}/{len(CASES)} passed, ${cost:.3f}")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
