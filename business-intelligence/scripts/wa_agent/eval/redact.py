"""
Turn WhatsApp chat exports into a redacted test set (Phase 0, Track C).

Input: a folder of exports from the WhatsApp Business app, one per chat
(.zip from iPhone containing _chat.txt, or .txt from Android).
Output (written to --out, which must be OUTSIDE the repo):
  chats.jsonl  one chat per line: {"chat": "c007", "messages": [{role, text, ts}]}
  cases.jsonl  one case per customer turn that got a reply from Goji:
               {"case": "c007-3", "history": [...up to and including the
               customer's message...], "goji_reply": "what Chris actually sent"}

Redaction (deterministic, before anything leaves the laptop):
  - sender names -> "Customer" / "Chris"; the customer's name tokens are also
    replaced wherever they appear in the text
  - phone numbers, emails, NRIC/FIN, SG postcodes, unit numbers
  - media placeholders normalised ("image omitted" -> "[sent a photo]")
It can't catch everything (a child's name typed mid-sentence), so skim
chats.jsonl before running replay.py, and delete the raw exports after.

  python -m wa_agent.eval.redact --in ~/goji-exports --out ~/goji-eval
  [--business-name "Goji Physio"]   # auto-detected if omitted
"""
from __future__ import annotations

import argparse
import json
import re
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

# iPhone:  [18/11/2026, 14:05:33] Name: text      (may start with U+200E)
# Android: 18/11/2026, 14:05 - Name: text         (or "2:05 pm", 2-digit years)
LINE_IOS = re.compile(r"^‎?\[(\d{1,2}/\d{1,2}/\d{2,4}),\s*([\d:]+(?:\s?[apAP]\.?[mM]\.?)?)\]\s([^:]+?):\s(.*)$")
LINE_ANDROID = re.compile(r"^(\d{1,2}/\d{1,2}/\d{2,4}),\s*([\d:]+(?:\s?[apAP]\.?[mM]\.?)?)\s-\s([^:]+?):\s(.*)$")

MEDIA = [
    (re.compile(r"(image omitted|<Media omitted>|IMG-\S+ \(file attached\))", re.I), "[sent a photo]"),
    (re.compile(r"(video omitted)", re.I), "[sent a video]"),
    (re.compile(r"(audio omitted|PTT-\S+ \(file attached\))", re.I), "[sent a voice note]"),
    (re.compile(r"(document omitted|\S+\.pdf \(file attached\))", re.I), "[sent a document]"),
    (re.compile(r"(sticker omitted)", re.I), "[sent a sticker]"),
]
PII = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    (re.compile(r"(?<!\d)(?:\+?65[\s-]?)?[689]\d{3}[\s-]?\d{4}(?!\d)"), "[PHONE]"),
    (re.compile(r"\+\d[\d\s-]{7,}\d"), "[PHONE]"),
    (re.compile(r"\b[STFGM]\d{7}[A-Z]\b", re.I), "[NRIC]"),
    (re.compile(r"#\d{1,3}-\d{1,5}"), "[UNIT]"),
    (re.compile(r"(?<!\d)\d{6}(?!\d)"), "[POSTCODE]"),
]
SYSTEM_NOISE = re.compile(r"(end-to-end encrypted|security code|This message was deleted|"
                          r"You deleted this message|<This message was edited>|joined using|"
                          r"is a contact|Missed voice call|Missed video call)", re.I)


def _read_export(path: Path) -> str:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith(".txt"))
            return z.read(name).decode("utf-8", errors="replace")
    return path.read_text(encoding="utf-8", errors="replace")


def _ts(d: str, t: str) -> float:
    t = t.replace(".", "").replace(" ", " ").upper()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%y %H:%M:%S", "%d/%m/%y %H:%M",
                "%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %I:%M %p", "%d/%m/%y %I:%M %p",
                "%d/%m/%y %I:%M:%S %p"):
        try:
            return datetime.strptime(f"{d} {t}", fmt).timestamp()
        except ValueError:
            continue
    return 0.0


def parse(text: str) -> list[dict]:
    """[{sender, text, ts}], multi-line messages joined, system lines dropped."""
    out: list[dict] = []
    for line in text.splitlines():
        m = LINE_IOS.match(line) or LINE_ANDROID.match(line)
        if m:
            d, t, sender, body = m.groups()
            out.append({"sender": sender.strip("‎ ").strip(), "text": body, "ts": _ts(d, t)})
        elif out and line.strip():
            out[-1]["text"] += "\n" + line
    return [m for m in out if not SYSTEM_NOISE.search(m["text"])]


def redact(text: str, names: list[str]) -> str:
    text = text.replace("‎", "")
    for pat, repl in MEDIA:
        text = pat.sub(repl, text)
    for pat, repl in PII:
        text = pat.sub(repl, text)
    for name in names:
        if len(name) >= 3:
            text = re.sub(rf"\b{re.escape(name)}\b", "[NAME]", text, flags=re.I)
    return re.sub(r"\[NAME\](?:\s+\[NAME\])+", "[NAME]", text).strip()


def detect_business(chats: list[list[dict]]) -> str:
    """The business account is the one sender present in (nearly) every chat."""
    seen = Counter()
    for msgs in chats:
        seen.update({m["sender"] for m in msgs})
    return seen.most_common(1)[0][0] if seen else ""


def build(chats: list[list[dict]], business: str) -> tuple[list[dict], list[dict]]:
    all_chats, cases = [], []
    for i, msgs in enumerate(chats, 1):
        cid = f"c{i:03d}"
        customer_names = {m["sender"] for m in msgs if m["sender"] != business}
        tokens = sorted({tok for n in customer_names for tok in re.split(r"[\s~]+", n)
                         if tok and not tok.startswith("+")}, key=len, reverse=True)
        convo = [{"role": "staff" if m["sender"] == business else "customer",
                  "text": redact(m["text"], tokens), "ts": m["ts"]} for m in msgs]
        convo = [m for m in convo if m["text"]]
        all_chats.append({"chat": cid, "messages": convo})
        n = 0
        for j, m in enumerate(convo):
            nxt = convo[j + 1] if j + 1 < len(convo) else None
            if m["role"] == "customer" and nxt and nxt["role"] == "staff":
                n += 1
                # The agent answers the customer's latest burst, so the case
                # history runs to here and the "answer key" is Chris's next message.
                cases.append({"case": f"{cid}-{n}", "history": convo[: j + 1],
                              "goji_reply": nxt["text"]})
    return all_chats, cases


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--in", dest="inp", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--business-name", default="")
    args = ap.parse_args()

    files = sorted(p for p in args.inp.iterdir() if p.suffix in (".zip", ".txt"))
    chats = [m for m in (parse(_read_export(p)) for p in files) if m]
    business = args.business_name or detect_business(chats)
    all_chats, cases = build(chats, business)

    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "chats.jsonl").open("w") as f:
        f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in all_chats)
    with (args.out / "cases.jsonl").open("w") as f:
        f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in cases)
    n_msgs = sum(len(c["messages"]) for c in all_chats)
    print(f"{len(files)} exports -> {len(all_chats)} chats, {n_msgs} messages, "
          f"{len(cases)} cases. Business sender: {business!r}. Output: {args.out}")


if __name__ == "__main__":
    main()
