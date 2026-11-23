"""
Turn WhatsApp chat exports into a redacted test set (Phase 0, Track C).

Input: a folder of exports from the WhatsApp Business app, one per chat
(.zip from iPhone containing _chat.txt, or .txt from Android). Searched
recursively: a first-level subfolder is the chat's category (e.g.
new-enquiries/, rescheduling/). An unzipped copy next to its .zip
("X.zip" + "X/_chat.txt") counts once.
Output (written to --out, which must be OUTSIDE the repo):
  chats.jsonl  one chat per line: {"chat": "c007", "category": "regular",
               "b2b": false, "messages": [{role, text, ts}]}
  cases.jsonl  one case per customer turn that got a reply from Goji:
               {"case": "c007-3", "category": ..., "b2b": ..., "history":
               [...up to and including the customer's message...],
               "goji_reply": "what Chris actually sent"}
  b2b marks partner chats (category matching --b2b-pattern, by default
  doctors' referrals): replay.py skips them unless asked.

Redaction (deterministic, before anything leaves the laptop):
  - sender names -> "Customer" / "Chris"; the customer's name tokens are also
    replaced wherever they appear in the text
  - names typed in the text: after greetings, "my name is", titles (Dr, Mdm),
    relations ("my son ..."), "Name:" fields, before a phone number or a
    date of birth; clinicians' first names (KB team pages) and Chris are kept
  - phone numbers, emails, NRIC/FIN, SG postcodes, unit numbers, street
    addresses and residential buildings, long reference numbers, dates of
    birth, document file names, the path of any non-Goji link
  - system lines dropped (group created, member added, calls); media
    placeholders normalised ("image omitted" -> "[sent a photo]")
  - partner (b2b) chats also lose any capitalised word that isn't in the KB or
    the system word list (they name other patients)
It can't catch everything (a name mentioned once with no cue), so skim
chats.jsonl before running replay.py, add what it missed to --extra-names,
and delete the raw exports after.

  python -m wa_agent.eval.redact --in ~/goji-eval/chats --out ~/goji-eval
  [--extra-names ~/goji-eval/extra_names.txt]
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
    (re.compile(r"(image omitted|GIF omitted|<Media omitted>|IMG-\S+ \(file attached\))", re.I), "[sent a photo]"),
    (re.compile(r"(video omitted)", re.I), "[sent a video]"),
    (re.compile(r"(audio omitted|PTT-\S+ \(file attached\))", re.I), "[sent a voice note]"),
    (re.compile(r"(document omitted|\S+\.pdf \(file attached\))", re.I), "[sent a document]"),
    (re.compile(r"(sticker omitted)", re.I), "[sent a sticker]"),
    (re.compile(r"(Contact card omitted)", re.I), "[sent a contact]"),
]
# iOS document lines carry the file name ("Jane Tan memo.pdf • 1 page"),
# which often holds a name or date: drop it, keep "[sent a document]".
DOC_NAME = re.compile(r"[^\n]*\.(?:pdf|docx?|xlsx?|pptx?|jpe?g|png|heic)\s*•\s*\d+\s*pages?\s*", re.I)
EDITED = re.compile(r"\s*<This message was edited>", re.I)
URL = re.compile(r"https?://[^\s<>]+|www\.[^\s<>]+", re.I)
OWN_DOMAIN = "gojiphysio.com"
FIELD_NAME = re.compile(r"(?im)^([^\w\n]*(?:full\s+|patient'?s?\s+|baby'?s?\s+|child'?s?\s+|partner'?s?\s+)?name[ \t]*[:\-][ \t]*)(\S.*)$")
DOB = re.compile(r"(?i)\b(DOB|D\.O\.B\.?|date of birth)(\s*[:\-]?\s*)\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}")
PII = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    (re.compile(r"(?<!\d)(?:\+?65[\s-]?)?[689]\d{3}[\s-]?\d{4}(?!\d)"), "[PHONE]"),
    (re.compile(r"\+\d[\d\s-]{7,}\d"), "[PHONE]"),
    (re.compile(r"\b[STFGM]\d{7}[A-Z]\b", re.I), "[NRIC]"),
    (re.compile(r"#\d{1,3}-\d{1,5}"), "[UNIT]"),
    (re.compile(r"(?<!\d)\d{6}(?!\d)"), "[POSTCODE]"),
    # street address, block number, named residential building
    (re.compile(r"\b\d{1,4}[A-Za-z]?\s+(?:[A-Z][a-z]+\s+){1,3}(?:Road|Rd|Street|St|Avenue|Ave|"
                r"Drive|Boulevard|Blvd|Crescent|Cres|Lane|Close|Walk|Way|Place|Rise|Link|"
                r"Grove|Hill|Terrace|Central|View|Heights)\b\.?"), "[ADDRESS]"),
    (re.compile(r"\b(?:Blk|Block)\s*\d+[A-Za-z]?\b", re.I), "[ADDRESS]"),
    (re.compile(r"\b(?:The\s+)?(?:[A-Z][a-z]+\s+){1,3}(?:Residences?|Condo(?:minium)?|Suites|"
                r"Mansions?|Towers?|Lodge|Court|Gardens|Loft)\b"), "[ADDRESS]"),
    # account, policy or reference numbers (8+ digits, or 12345-6789)
    (re.compile(r"(?<![\w/.])\d{8,}(?![\w/])"), "[NUMBER]"),
    (re.compile(r"(?<!\d)\d{5,}-\d{3,}(?!\d)"), "[NUMBER]"),
]
# Names typed in the text, not just the senders' own: greetings ("Hi Mei
# Ling"), introductions ("my name is ..."), titles ("Dr Tan"), relations ("my
# son Ethan"). Collected per chat from the raw text, then redacted everywhere
# in that chat like the sender's name.
_CAP = r"[A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){0,2}"
NAME_CUES = [
    re.compile(r"\b(?i:hi|hello|hey|dear|hihi|morning|thanks|thank you|bye)[ \t,]+(" + _CAP + ")"),
    re.compile(r"\b(?i:my name is|my name's|name is)[ \t]+([A-Za-z]+(?:[ \t]+[A-Z][a-z]+){0,2})"),
    re.compile(r"\b(?:Dr|Mdm|Mrs|Mr|Ms|Miss|Madam)\.?[ \t]+(" + _CAP + ")"),
    re.compile(r"\b(?i:my|our|her|his)[ \t]+(?i:son|daughter|baby|boy|girl|kid|child|husband|hubby|"
               r"wife|partner|sis|sister|brother|bro|mum|mom|mother|dad|father|helper|maid|"
               r"grandma|grandmother|niece|nephew|friend)\b[ \t,]*([A-Z][a-z]+)"),
    # a name right before a phone number (a shared contact: "Melissa 9123 4567")
    re.compile(r"(" + _CAP + r")[ \t:,-]+(?:\+?65[ \t-]?)?[689]\d{3}[ \t-]?\d{4}(?!\d)"),
    # a line of just a name, then a date of birth (a baby's or child's details)
    re.compile(r"(?m)^[ \t]*([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){0,3})[ \t]*\n[^\w\n]*(?i:dob|d\.o\.b|date of birth)"),
    # introductions and babies ("this is Mei", "baby Ethan"); common words
    # after a cue are skipped ("I'm Looking", "Baby Assessment"), see cue_names
    re.compile(r"\b(?i:this is|i am|i'm|im)[ \t]+(" + _CAP + ")"),
    re.compile(r"\b(?i:baby|little|son|daughter)[ \t]+([A-Z][a-z]+)"),
]
# Two-letter words that are never taken as a name token (names like "Ai" or
# "Wu" are; most two-letter English words aren't names).
TWO_LETTER_WORDS = set("""
am an as at be by do go he hi if in is it me my no of oh ok on or so to up us we ya ye yo eh ah
uh um hm pm dr ms mr st rd ma pa la lo ha
""".split())
# Never treated as a name found by a cue (staff first names are added from
# the KB's team pages, see staff_names).
STOP = set("""
chris goji physio physiotherapy team all everyone there guys again mama mamas mummy mummies
dear doc doctor dr mdm mrs mr ms miss madam sir good morning afternoon evening night both you
the our my from here just so ok okay yes no sorry thanks thank welcome noted sure great happy
hope regards with at in on for and but not also still back now going looking interested
available free running checking doing post week monday tuesday wednesday thursday friday
saturday sunday mon tue tues wed thu thur thurs fri sat sun january february march april may
june july august september october november december jan feb mar apr jun jul aug sep sept
oct nov dec singapore whatsapp google instagram mobile phone contact number email tel hp address
""".split())
STRICT_WORD = re.compile(r"\b[A-Z][a-z]+\b")
# Bidi and direction marks WhatsApp wraps around phone numbers and names
# (U+200E/F, U+202A-E, U+2066-9).
BIDI = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
B2B_PATTERN = r"doctor|referral|partner|b2b"
SYSTEM_NOISE = re.compile(r"(end-to-end encrypted|security code|This message was deleted|"
                          r"You deleted this message|joined using|"
                          r"is a contact|Missed voice call|Missed video call)", re.I)


def find_exports(root: Path) -> list[tuple[Path, str]]:
    """[(export file, category)] under root, sorted. The category is the
    first-level folder the export sits in ("" at the top level). An unzipped
    folder whose .zip sits next to it is skipped: it's the same chat."""
    found: dict[Path, tuple[Path, str]] = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if not p.is_file() or p.suffix not in (".zip", ".txt") or any(
                part.startswith((".", "__MACOSX")) for part in rel.parts):
            continue
        # The chat "unit" is the zip itself, or the folder an unzipped
        # _chat.txt sits in, or a loose Android .txt.
        unit = p.parent if p.name == "_chat.txt" and p.parent != root else p
        key = unit.with_suffix("") if unit.suffix == ".zip" else unit
        if p.suffix == ".txt" and unit != p and unit.with_name(unit.name + ".zip").exists():
            continue
        if key in found:
            continue
        parts = unit.relative_to(root).parts
        found[key] = (p, parts[0] if len(parts) > 1 else "")
    return sorted(found.values())


def _read_export(path: Path) -> str:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist()
                        if n.endswith(".txt") and not n.startswith("__MACOSX"))
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
    """[{sender, text, ts}], multi-line messages joined, system lines dropped.
    On iPhone a system line (group created, member added or left, calls,
    "pinned a message") starts with U+200E; so does a media placeholder,
    which is kept."""
    out: list[dict] = []
    for line in text.splitlines():
        m = LINE_IOS.match(line) or LINE_ANDROID.match(line)
        if m:
            d, t, sender, body = m.groups()
            system = body.startswith("‎") and "omitted" not in body
            out.append({"sender": BIDI.sub("", sender).strip(), "text": body, "ts": _ts(d, t),
                        "system": system})
        elif out and line.strip():
            out[-1]["text"] += "\n" + line
    return [{k: v for k, v in m.items() if k != "system"} for m in out
            if not m["system"] and not SYSTEM_NOISE.search(m["text"])]


def _link(m: re.Match) -> str:
    url = m.group(0)
    host = re.sub(r"^(?:https?://)?", "", url, flags=re.I).split("/")[0].split("?")[0].lower()
    if host == OWN_DOMAIN or host.endswith("." + OWN_DOMAIN):
        return url
    # Keep where it points, drop the path: tokens and slugs can identify someone.
    return f"[link: {'.'.join(host.split('.')[-2:])}]"


def redact(text: str, names: list[str], strict_vocab: set[str] | None = None) -> str:
    """strict_vocab: also replace any capitalised word not in this vocabulary
    (used for partner chats, which name other patients)."""
    text = BIDI.sub("", text)
    text = EDITED.sub("", text)
    text = DOC_NAME.sub("", text)
    for pat, repl in MEDIA:
        text = pat.sub(repl, text)
    text = URL.sub(_link, text)
    text = FIELD_NAME.sub(lambda m: m.group(1) + "[NAME]", text)
    text = DOB.sub(lambda m: m.group(1) + m.group(2) + "[DOB]", text)
    for pat, repl in PII:
        text = pat.sub(repl, text)
    for name in names:
        if len(name) >= 3 or (len(name) == 2 and name.lower() not in TWO_LETTER_WORDS):
            text = re.sub(rf"\b{re.escape(name)}\b", "[NAME]", text, flags=re.I)
    if strict_vocab is not None:
        text = STRICT_WORD.sub(lambda m: m.group(0) if m.group(0).lower() in strict_vocab
                               or m.group(0).lower() in STOP else "[NAME]", text)
    return re.sub(r"\[NAME\](?:\s+\[NAME\])+", "[NAME]", text).strip()


def name_tokens(name: str) -> set[str]:
    """Letter-only tokens of a name, minus titles and staff/clinic words."""
    return {t for t in re.findall(r"[^\W\d_]+", name)
            if (len(t) >= 3 or (len(t) == 2 and t.lower() not in TWO_LETTER_WORDS))
            and t.lower() not in STOP}


def cue_names(text: str, keep: set[str] = frozenset(), vocab: set[str] = frozenset()) -> set[str]:
    """Names typed in a message (greetings, introductions, titles, relations,
    "Name:" fields, a name before a number or a date of birth). `keep`: staff
    first names, never redacted. `vocab`: common words (the KB's), never taken
    from a cue, so "Hi, Can I..." or "Thanks Mei Ling Got it" don't redact
    "can" or "got"."""
    text = BIDI.sub("", text)
    found: set[str] = set()
    for cue in NAME_CUES:
        for m in cue.finditer(text):
            words = re.findall(r"[^\W\d_]+", m.group(1))
            found |= name_tokens(" ".join(w for w in words if w.lower() not in vocab))
    for m in FIELD_NAME.finditer(text):
        found |= name_tokens(m.group(2))
    return {t for t in found if t.lower() not in keep}


def staff_names(kb_path: Path | None = None) -> set[str]:
    """Clinicians' first names from the KB's team pages (team/<first>-<last>),
    lowercased, plus Chris: public, and the agent needs them."""
    kb_path = kb_path or Path(__file__).resolve().parents[1] / "_build" / "kb.json"
    names = {"chris"}
    try:
        pages = json.loads(kb_path.read_text()).get("pages", {})
        names |= {k.split("/", 1)[1].split("-")[0] for k in pages if k.startswith("team/")}
    except (OSError, ValueError, AttributeError):
        pass
    return names


def common_words(kb_path: Path | None = None, dictionary: Path | None = None) -> set[str]:
    """Lowercase vocabulary: the KB's words, plus the lowercase entries of a
    word list if given (e.g. /usr/share/dict/words; lowercase only, so proper
    names stay out)."""
    kb_path = kb_path or Path(__file__).resolve().parents[1] / "_build" / "kb.json"
    words: set[str] = set()
    try:
        words |= {w.lower() for w in re.findall(r"[A-Za-z]+", kb_path.read_text())}
    except OSError:
        pass
    if dictionary:
        try:
            words |= {w for w in dictionary.read_text().split() if w.islower()}
        except OSError:
            pass
    return words


def read_extra_names(path: Path | None) -> list[str]:
    """One name or term per line (# comments), redacted in every chat. For what
    the patterns miss; keep the file next to the exports, never in the repo."""
    if not path:
        return []
    lines = [ln.split("#", 1)[0].strip() for ln in path.read_text().splitlines()]
    return [ln for ln in lines if ln]


def detect_business(chats: list[list[dict]]) -> str:
    """The business account is the one sender present in (nearly) every chat."""
    seen = Counter()
    for msgs in chats:
        seen.update({m["sender"] for m in msgs})
    return seen.most_common(1)[0][0] if seen else ""


def build(chats: list[list[dict]], business: str, categories: list[str] | None = None,
          b2b_pattern: str = B2B_PATTERN, keep: set[str] | None = None,
          vocab: set[str] | None = None, extra_names: list[str] = (),
          strict_vocab: set[str] | None = None) -> tuple[list[dict], list[dict]]:
    """strict_vocab: in partner (b2b) chats, also redact any capitalised word
    not in it (those chats name other patients)."""
    all_chats, cases = [], []
    categories = categories or [""] * len(chats)
    keep = staff_names() if keep is None else keep
    vocab = vocab or set()
    extra = {t for n in extra_names for t in [n, *name_tokens(n)]}
    for i, (msgs, category) in enumerate(zip(chats, categories), 1):
        cid = f"c{i:03d}"
        b2b = bool(category and re.search(b2b_pattern, category, re.I))
        meta = {"category": category, "b2b": b2b}
        found = {t for m in msgs if m["sender"] != business for t in name_tokens(m["sender"])}
        for m in msgs:
            found |= cue_names(m["text"], keep, vocab)
        tokens = sorted(found | extra, key=len, reverse=True)
        strict = (strict_vocab | keep) if (b2b and strict_vocab) else None
        convo = [{"role": "staff" if m["sender"] == business else "customer",
                  "text": redact(m["text"], tokens, strict), "ts": m["ts"]} for m in msgs]
        convo = [m for m in convo if m["text"]]
        all_chats.append({"chat": cid, **meta, "messages": convo})
        n = 0
        for j, m in enumerate(convo):
            nxt = convo[j + 1] if j + 1 < len(convo) else None
            if m["role"] == "customer" and nxt and nxt["role"] == "staff":
                n += 1
                # The agent answers the customer's latest burst, so the case
                # history runs to here and the "answer key" is Chris's next message.
                cases.append({"case": f"{cid}-{n}", **meta, "history": convo[: j + 1],
                              "goji_reply": nxt["text"]})
    return all_chats, cases


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--in", dest="inp", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--business-name", default="")
    ap.add_argument("--b2b-pattern", default=B2B_PATTERN,
                    help="regex on the category folder marking partner (B2B) chats")
    ap.add_argument("--extra-names", type=Path, default=None,
                    help="file of extra names/terms to redact (keep it outside the repo)")
    ap.add_argument("--no-strict-b2b", action="store_true",
                    help="don't redact unknown capitalised words in partner chats")
    args = ap.parse_args()

    files = find_exports(args.inp)
    parsed = [(parse(_read_export(p)), cat) for p, cat in files]
    parsed = [(m, cat) for m, cat in parsed if m]
    chats, categories = [m for m, _ in parsed], [cat for _, cat in parsed]
    business = args.business_name or detect_business(chats)
    all_chats, cases = build(chats, business, categories, args.b2b_pattern,
                             keep=staff_names(), vocab=common_words(),
                             extra_names=read_extra_names(args.extra_names),
                             strict_vocab=None if args.no_strict_b2b else common_words(
                                 dictionary=Path("/usr/share/dict/words")))

    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "chats.jsonl").open("w") as f:
        f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in all_chats)
    with (args.out / "cases.jsonl").open("w") as f:
        f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in cases)
    n_msgs = sum(len(c["messages"]) for c in all_chats)
    print(f"{len(files)} exports -> {len(all_chats)} chats, {n_msgs} messages, "
          f"{len(cases)} cases. Business sender: {business!r}. Output: {args.out}")
    per = Counter((c["category"] or "-", c["b2b"]) for c in all_chats)
    per_cases = Counter((c["category"] or "-", c["b2b"]) for c in cases)
    for (cat, b2b), n in sorted(per.items()):
        print(f"  {cat:28} {n:3} chats {per_cases[(cat, b2b)]:4} cases{'  (b2b)' if b2b else ''}")


if __name__ == "__main__":
    main()
