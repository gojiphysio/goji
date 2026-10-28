#!/usr/bin/env python3
"""
One-off: Plato clinical notes -> aggregate, de-identified counts for blog/press.

Spec and hard rules: business-intelligence/architecture/clinical-notes-insights-plan.md

PRIVACY BOUNDARY: note text exists only inside this process. Nothing is written
to disk, BigQuery or a log file, and nothing is sent anywhere but Plato. stdout
gets field names (shape), patient ids + yes/no flags (spot-check) or suppressed
counts (run), never note text or a matched snippet. Errors name fields and
types, never values. Don't paste spot-check output anywhere: an id plus flags is
still health data about a person.

Modes:
  shape        2 requests. Note count, each field's name/type, and the values of
               type-like fields only (note type/category), to pick --text-field etc.
  spot-check   Per-patient flags for the first --patients patients, to compare
               by hand against their notes in Plato. ~1 request per patient.
  run          Full pull, 11 pm - 6 am SGT only. Prints the counts table.

Rate limit: Plato allows 20 req/min clinic-wide, shared with /book and the
ingestion jobs. We take 1 request / 15 s, pause a minute when
x-ratelimit-remaining < 8, back off 5 min on a 429 and stop after 3 in a row.

Env vars:
  PLATO_DB       Plato database name   default: gojihealth
  PLATO_API_KEY  Plato bearer token    (required; set in the shell, never a file)

Exit codes: 0 on success, 1 on config error, 3 on Plato failure / unexpected shape.
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterator

import requests

PLATO_BASE = "https://clinic.platomedical.com/api"
TIMEOUT_S = 30
REQUEST_INTERVAL_S = 15
LOW_REMAINING = 8
BACKOFF_429_S = 300
MAX_CONSECUTIVE_429 = 3
MAX_5XX_RETRIES = 3
SUPPRESS_BELOW = 5
PAGE_SIZE = 20

SGT = timezone(timedelta(hours=8))
# Window opens 23:00; last start 05:30 so a ~25 min run is done by 06:00.
WINDOW_OPEN_HOUR = 23
WINDOW_LAST_START = (5, 30)


class PlatoError(Exception):
    """Plato failed or returned something we don't recognise. Message names
    paths, fields and types only, never values."""


def log(msg: str) -> None:
    # stderr, so a redirected stdout holds only the result table.
    print(f"{datetime.now(SGT):%H:%M:%S} {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Plato client: paced, shape-checked, never echoes a response body.
# ---------------------------------------------------------------------------

class Plato:
    def __init__(self, db: str, key: str, session: requests.Session | None = None,
                 interval: float = REQUEST_INTERVAL_S,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.db = db
        self.session = session or requests.Session()
        self.session.headers.update({
            "accept": "application/json",
            "Authorization": f"Bearer {key}",
        })
        self.interval = interval
        self.sleep = sleep
        self.clock = clock
        self.requests = 0
        self._last: float | None = None

    def _pace(self) -> None:
        if self._last is not None:
            gap = self.interval - (self.clock() - self._last)
            if gap > 0:
                self.sleep(gap)

    def get(self, path: str, params: dict | None = None):
        consecutive_429 = 0
        server_errors = 0
        while True:
            self._pace()
            try:
                r = self.session.get(f"{PLATO_BASE}/{self.db}{path}", params=params,
                                     timeout=TIMEOUT_S)
            except (requests.ConnectionError, requests.Timeout) as e:
                # Dropped connections happen; retry like a 5xx.
                self._last = self.clock()
                server_errors += 1
                if server_errors > MAX_5XX_RETRIES:
                    raise PlatoError(f"{path}: {type(e).__name__} after {MAX_5XX_RETRIES} retries") from None
                log(f"{type(e).__name__} on {path}, retrying in 30s")
                self.sleep(30)
                continue
            self._last = self.clock()
            self.requests += 1
            if r.status_code == 429:
                consecutive_429 += 1
                if consecutive_429 >= MAX_CONSECUTIVE_429:
                    raise PlatoError(f"{path}: {MAX_CONSECUTIVE_429} consecutive 429s, stopping")
                log(f"429 on {path}, backing off {BACKOFF_429_S}s")
                self.sleep(BACKOFF_429_S)
                continue
            if r.status_code >= 500:
                server_errors += 1
                if server_errors > MAX_5XX_RETRIES:
                    raise PlatoError(f"{path}: HTTP {r.status_code} after {MAX_5XX_RETRIES} retries")
                self.sleep(30)
                continue
            if r.status_code != 200:
                raise PlatoError(f"{path}: HTTP {r.status_code}")
            rem = r.headers.get("x-ratelimit-remaining")
            if rem and rem.isdigit() and int(rem) < LOW_REMAINING:
                log(f"x-ratelimit-remaining={rem}, pausing 60s")
                self.sleep(60)
            try:
                return r.json()
            except ValueError:
                raise PlatoError(f"{path}: response is not JSON") from None

    def count(self, path: str) -> int:
        body = self.get(f"{path}/count")
        if isinstance(body, int):
            return body
        if isinstance(body, dict):
            # Plato returns {records, per_page, pages}.
            for k in ("records", "count", "total"):
                if isinstance(body.get(k), int):
                    return body[k]
            shape = ", ".join(f"{k}:{type(v).__name__}" for k, v in body.items())
            raise PlatoError(f"{path}/count: unexpected shape {{{shape}}}")
        raise PlatoError(f"{path}/count: unexpected shape {type(body).__name__}")

    def pages(self, path: str, max_pages: int | None = None) -> Iterator[list]:
        page = 1
        prev_ids = None
        while True:
            if max_pages is not None and page > max_pages:
                raise PlatoError(f"{path}: more than {max_pages} pages, stopping")
            batch = self.get(path, {"current_page": page})
            if not isinstance(batch, list):
                raise PlatoError(f"{path} page {page}: expected a list, got {type(batch).__name__}")
            if not batch:
                return
            ids = [str(r.get("_id") or r.get("id")) for r in batch if isinstance(r, dict)]
            if ids and ids == prev_ids:
                raise PlatoError(f"{path}: page {page} repeats page {page - 1}, paging ignored?")
            prev_ids = ids
            yield batch
            if len(batch) < PAGE_SIZE:
                return  # short page is the last; saves a request
            page += 1


# ---------------------------------------------------------------------------
# Note normalisation
# ---------------------------------------------------------------------------

def dig(obj, dotted: str):
    """obj['a']['b'] for 'a.b'; None if any step is missing."""
    for part in dotted.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


_TAG = re.compile(r"<[^>]+>")


def to_text(value) -> str:
    """Plain text from a note body: Plato rich-text is HTML; lists are joined."""
    if isinstance(value, list):
        return "\n".join(to_text(v) for v in value)
    if isinstance(value, dict):
        return "\n".join(to_text(v) for v in value.values())
    if not isinstance(value, str):
        return ""
    return html.unescape(_TAG.sub(" ", value.replace("<br", "\n<br").replace("</p>", "\n</p>")))


class Fields:
    def __init__(self, patient: str, date: str, text: str,
                 type_field: str | None = None, types: set[str] | None = None):
        self.patient, self.date, self.text = patient, date, text
        self.type_field, self.types = type_field, types

    def parse(self, note, where: str) -> tuple[str, str, str] | None:
        """(patient_id, date, text) or None if filtered out by --types.
        Raises PlatoError naming the field if the shape is wrong."""
        if not isinstance(note, dict):
            raise PlatoError(f"{where}: note is {type(note).__name__}, not an object")
        if note.get("cancel"):
            return None  # cancelled notes don't count
        if self.type_field and self.types is not None:
            if str(dig(note, self.type_field)) not in self.types:
                return None
        pid = dig(note, self.patient)
        if pid in (None, ""):
            raise PlatoError(f"{where}: field '{self.patient}' missing (see `shape`)")
        if dig(note, self.text) is None:
            raise PlatoError(f"{where}: field '{self.text}' missing (see `shape`)")
        when = dig(note, self.date)
        return str(pid), str(when) if when else "~", to_text(dig(note, self.text))


# ---------------------------------------------------------------------------
# Codebook. Each rule reads a patient's notes and returns a set of labels; an
# empty set means "not mentioned". Edit here after the spot-check.
# ---------------------------------------------------------------------------

I = re.IGNORECASE
NUM = r"(\d{1,2}(?:\.\d)?)"
UNIT = r"(weeks?|wks?|w|months?|mths?|mos?|m|years?|yrs?|y)"
PP = r"(?:pp|post[- ]?partum|post[- ]?natal|post[- ]?delivery|post[- ]?birth|after (?:birth|delivery))"
WEEKS_PER = {"w": 1, "m": 4.35, "y": 52}

PP_TIMING = [
    re.compile(rf"\b{NUM}\s*{UNIT}\b\.?\s*(?:old\s+)?{PP}\b", I),          # 6 weeks postpartum
    re.compile(rf"\b{PP}\b\s*[:\-]?\s*{NUM}\s*{UNIT}\b", I),               # PP 6wks
    re.compile(rf"\b(?:baby|bb|LO|infant)\b[^.\n]{{0,15}}?\b{NUM}\s*{UNIT}\b", I),  # baby is 4 months
]
PP_FRACTION = [                                                            # 6/52 PP, 3/12 postnatal
    re.compile(rf"\b(\d{{1,2}})/(52|12)\s*{PP}\b", I),
    re.compile(rf"\b{PP}\b\s*[:\-]?\s*(\d{{1,2}})/(52|12)\b", I),
]
POSTPARTUM_ANY = re.compile(rf"\b{PP}\b|\bpost[- ]?baby\b", I)

PREG_WEEKS = [
    re.compile(r"\b(\d{1,2})\s*(?:weeks?|wks?|w)\s*(?:\+\s*\d\s*d(?:ays?)?\s*)?(?:pregnant|preg|gestation|GA)\b", I),
    re.compile(r"\bGA\s*:?\s*(\d{1,2})\b", I),
    re.compile(r"\b(\d{1,2})/40\b"),
    re.compile(r"\b(?:pregnant|preg)\b[^.\n]{0,10}?\b(\d{1,2})\s*(?:weeks?|wks?|w)\b", I),
]
TRIMESTER_WORD = re.compile(r"\b(1st|first|2nd|second|3rd|third)\s+trimester\b", I)

BIRTH = {
    "c-section": re.compile(r"\b(?:c[- ]?section|c(?:a)?esarean|LSCS|EMCS|ELCS|EMLSCS|ELLSCS|C/S)\b", I),
    "instrumental": re.compile(r"\b(?:forceps|vacuum|ventouse|instrumental)\b", I),
    "vaginal": re.compile(r"\b(?:SVD|NVD|NVB|VBAC|(?:vaginal|natural|normal) (?:delivery|birth))\b", I),
}

LEAKING = re.compile(r"\b(?:leak(?:s|ing|age|ed)?|incontinen(?:ce|t)|SUI|UUI|MUI|urgency)\b", I)
LEAK_NOT_BLADDER = re.compile(r"\b(?:milk|breast|nipple|colostrum)\b[^.\n]{0,15}$", I)

DIASTASIS = [
    re.compile(r"\b(?:DRAM?|diastasis(?: recti)?|IRD)\b[^.\n]{0,40}?\b\d+(?:\.\d+)?\s*(?:fw|f/w|fb|fingers?|finger\s*widths?|cm)\b", I),
    re.compile(r"\b\d+(?:\.\d+)?\s*(?:fw|f/w|fb|fingers?|finger\s*widths?|cm)\b[^.\n]{0,20}?\b(?:DRAM?|diastasis|gap|separation)\b", I),
]

PAIN = {
    "wrist/thumb": re.compile(r"\b(?:wrists?|de ?quervain'?s?|thumbs?)\b", I),
    "neck": re.compile(r"\b(?:neck|c[- ]?spine)\b", I),
    "back": re.compile(r"\b(?:back pain|low(?:er)? back|upper back|mid back|LBP|thoracic|lumbar|t[- ]?spine|l[- ]?spine)\b", I),
    "pelvic girdle": re.compile(r"\b(?:PGP|pelvic girdle|SIJ|sacroiliac|pubic symphysis|symphysis pubis|SPD|coccyx|tailbone)\b", I),
    "shoulder": re.compile(r"\bshoulders?\b", I),
}
# Case-note templates name body parts in every exam ("shoulder flexion full"),
# so a body part counts only with a pain word on the same line, close by.
# Shorthand that already means pain counts on its own.
PAIN_WORD = re.compile(r"\b(?:pain\w*|ache\w*|aching|sore\w*|tender\w*|stiff\w*|injur\w*|strain\w*|sprain\w*|hurt\w*|discomfort|niggl\w*|c/o)\b", I)
PAIN_NEAR = 40
PAIN_SHORTHAND = re.compile(r"^(?:LBP|PGP|SPD|de ?quervain'?s?)$", I)


def painful(pattern: re.Pattern, text: str) -> bool:
    """Body part mentioned with pain nearby (same line), and not negated."""
    for m in pattern.finditer(text):
        before = text[max(0, m.start() - 30):m.start()]
        after = text[m.end():m.end() + 12]
        if NEG_BEFORE.search(before) or NEG_AFTER.search(after):
            continue
        if PAIN_SHORTHAND.match(m.group(0)):
            return True
        lo = text.rfind("\n", 0, m.start()) + 1
        hi = text.find("\n", m.end())
        hi = len(text) if hi == -1 else hi
        near = text[max(lo, m.start() - PAIN_NEAR):min(hi, m.end() + PAIN_NEAR)]
        if PAIN_WORD.search(near):
            return True
    return False

GOAL_INTRO = re.compile(r"\b(?:goals?|aims?|wants? to|would like to|hopes? to)\b\s*[:\-]?", I)
GOAL_WINDOW = 200
GOALS = {
    "running": re.compile(r"\b(?:run|running|jog|jogging|marathon|\d+\s?km)\b", I),
    "exercise/sport": re.compile(r"\b(?:exercise|gym|work ?out|training|pilates|yoga|sports?|tennis|swim(?:ming)?|cycling|hiit|crossfit|weights)\b", I),
    "lifting/carrying baby": re.compile(r"\b(?:lift|lifting|carry|carrying|pick(?:ing)? up)\b[^.\n]{0,20}\b(?:baby|bb|LO|child|kids?|toddler)\b", I),
    "sleep": re.compile(r"\bsleep", I),
    "work": re.compile(r"\b(?:RTW|work)\b", I),
}
AGEING_GOALS = {
    "balance": re.compile(r"\bbalance\b", I),
    "falls": re.compile(r"\bfall(?:s|ing)?\b", I),
    "strength": re.compile(r"\b(?:strength|stronger|strengthen\w*)\b", I),
    "travel": re.compile(r"\b(?:travel\w*|trips?|hik(?:e|es|ing))\b", I),
}

NEG_BEFORE = re.compile(r"\b(?:no|nil|denies|denied|not|without|neg(?:ative)?\s+for|absent|resolved)\b[^.,;\n]{0,20}$", I)
NEG_AFTER = re.compile(r"^\s*[:\-=]?\s*(?:nil|none|no|neg|negative|-ve|absent)\b", I)


def affirmed(pattern: re.Pattern, text: str, exclude_before: re.Pattern | None = None) -> bool:
    """True if pattern matches somewhere that isn't negated ("no leaking",
    "leaking: nil") or excluded by context (e.g. milk leaking)."""
    for m in pattern.finditer(text):
        before = text[max(0, m.start() - 30):m.start()]
        after = text[m.end():m.end() + 12]
        if NEG_BEFORE.search(before) or NEG_AFTER.search(after):
            continue
        if exclude_before and exclude_before.search(before):
            continue
        return True
    return False


def weeks_postpartum(text: str) -> float | None:
    for p in PP_FRACTION:
        m = p.search(text)
        if m:
            n, base = int(m.group(1)), m.group(2)
            return float(n) if base == "52" else n * WEEKS_PER["m"]
    for p in PP_TIMING:
        m = p.search(text)
        if m:
            return float(m.group(1)) * WEEKS_PER[m.group(2)[0].lower()]
    return None


def pp_bucket(weeks: float) -> str:
    if weeks < 6:
        return "under 6 weeks"
    if weeks < 13:
        return "6-12 weeks"
    if weeks < 26:
        return "3-6 months"
    if weeks < 52:
        return "6-12 months"
    return "1 year+"


def trimester(text: str) -> str | None:
    m = TRIMESTER_WORD.search(text)
    if m:
        return {"1": "1st", "f": "1st", "2": "2nd", "s": "2nd", "3": "3rd", "t": "3rd"}[m.group(1)[0].lower()]
    for p in PREG_WEEKS:
        m = p.search(text)
        if m:
            w = int(m.group(1))
            if 1 <= w <= 13:
                return "1st"
            if 14 <= w <= 27:
                return "2nd"
            if 28 <= w <= 42:
                return "3rd"
    return None


def goal_text(text: str) -> str:
    return "\n".join(text[m.end():m.end() + GOAL_WINDOW] for m in GOAL_INTRO.finditer(text))


def derive(notes: list[tuple[str, str]]) -> dict[str, set[str]]:
    """Per-patient labels from [(date, text), ...]. The first note (earliest
    date) is the first visit; other features look across all notes."""
    notes = sorted(notes)
    first = notes[0][1]
    every = "\n".join(t for _, t in notes)
    goals = goal_text(every)
    out: dict[str, set[str]] = {}
    wk = weeks_postpartum(first)
    out["weeks postpartum at first visit"] = {pp_bucket(wk)} if wk is not None else set()
    tri = trimester(first)
    out["trimester at first visit"] = {tri} if tri else set()
    out["postpartum"] = {"yes"} if wk is not None or POSTPARTUM_ANY.search(every) else set()
    out["birth type mentioned"] = {k for k, p in BIRTH.items() if p.search(every)}
    out["leaking/urgency reported"] = {"yes"} if affirmed(LEAKING, every, LEAK_NOT_BLADDER) else set()
    out["diastasis measured"] = {"yes"} if any(p.search(every) for p in DIASTASIS) else set()
    # First note only: what they came in with, not every region treated since.
    out["pain location"] = {k for k, p in PAIN.items() if painful(p, first)}
    out["goal recorded"] = {"yes"} if goals else set()
    out["main goal"] = {k for k, p in GOALS.items() if p.search(goals)}
    out["active-ageing goal"] = {k for k, p in AGEING_GOALS.items() if p.search(goals)}
    return out


# ---------------------------------------------------------------------------
# Aggregation + suppression
# ---------------------------------------------------------------------------

# (feature, denominator group, group label). Group None = all patients.
REPORT = [
    ("weeks postpartum at first visit", "weeks postpartum at first visit", "postpartum timing in first note"),
    ("trimester at first visit", "trimester at first visit", "pregnancy timing in first note"),
    ("birth type mentioned", "birth type mentioned", "birth type in notes"),
    ("leaking/urgency reported", "postpartum", "postpartum patients"),
    ("diastasis measured", "postpartum", "postpartum patients"),
    ("pain location", "postpartum", "postpartum patients"),
    ("pain location", None, "all patients"),
    ("main goal", "goal recorded", "patients with a goal recorded"),
    ("active-ageing goal", "aged 60+ with goal", "aged 60+ with a goal recorded"),
]


def cell(n: int) -> str:
    return f"<{SUPPRESS_BELOW}" if n < SUPPRESS_BELOW else str(n)


def report(per_patient: dict[str, dict[str, set[str]]], ages: dict[str, int] | None) -> str:
    if ages is not None:
        for pid, f in per_patient.items():
            f["aged 60+"] = {"yes"} if ages.get(pid, 0) >= 60 else set()
            f["aged 60+ with goal"] = {"yes"} if f["aged 60+"] and f["goal recorded"] else set()
    lines = [f"Patients with notes: {cell(len(per_patient))}"]
    if ages is not None:
        n60 = sum(1 for f in per_patient.values() if f["aged 60+"])
        lines.append(f"Aged 60+ (from Plato DOB): {cell(n60)}")
    lines.append("")
    lines.append(f"{'feature':34} {'label':24} {'n':>5} {'%':>5}  of group")
    for feature, group, label in REPORT:
        if group and group.startswith("aged") and ages is None:
            continue
        members = [f for f in per_patient.values() if group is None or f.get(group)]
        g = len(members)
        counts = Counter(lbl for f in members for lbl in f[feature])
        lines.append(f"-- {feature}  [{label}: {cell(g)}]")
        if g < SUPPRESS_BELOW:
            continue
        for lbl, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            pct = f"{100 * n / g:.0f}" if n >= SUPPRESS_BELOW else ""
            lines.append(f"{'':34} {lbl:24} {cell(n):>5} {pct:>5}")
    return "\n".join(lines)


def age_on(dob: str | None, today: date) -> int | None:
    """Whole years from a Plato DOB string; None if missing or placeholder."""
    try:
        y, m, d = (int(x) for x in str(dob)[:10].split("-"))
        born = date(y, m, d)
    except (TypeError, ValueError):
        return None
    if born.year < 1900:
        return None
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

TYPE_LIKE = re.compile(r"type|category|kind|template|status|class|folder|cancel|draft", I)


def mode_shape(plato: Plato) -> None:
    print(f"notes in Plato: {plato.count('/patient/note')}")
    batch = plato.get("/patient/note", {"current_page": 1})
    if not isinstance(batch, list):
        raise PlatoError(f"/patient/note: expected a list, got {type(batch).__name__}")
    print(f"notes on page 1: {len(batch)}\n")
    types: dict[str, set[str]] = defaultdict(set)
    present: Counter = Counter()
    lengths: dict[str, int] = defaultdict(int)
    enums: dict[str, Counter] = defaultdict(Counter)
    for note in batch:
        if not isinstance(note, dict):
            continue
        for k, v in note.items():
            present[k] += 1
            types[k].add(type(v).__name__)
            if isinstance(v, dict):
                for kk, vv in v.items():
                    present[f"{k}.{kk}"] += 1
                    types[f"{k}.{kk}"].add(type(vv).__name__)
            if isinstance(v, str):
                lengths[k] = max(lengths[k], len(v))
            # Values only for type-like fields with short string values.
            if TYPE_LIKE.search(k) and isinstance(v, (str, int)) and len(str(v)) <= 40:
                enums[k][str(v)] += 1
    print(f"{'field':32} {'types':20} {'present':>7} {'max len':>8}")
    for k in sorted(present):
        print(f"{k:32} {','.join(sorted(types[k])):20} {present[k]:>7} {lengths.get(k, ''):>8}")
    for k, c in enums.items():
        print(f"\nvalues of {k}: " + ", ".join(f"{v} ({n})" for v, n in c.most_common()))


def mode_spot_check(plato: Plato, fields: Fields, n_patients: int) -> None:
    pids: list[str] = []
    for batch in plato.pages("/patient/note", max_pages=50):
        for note in batch:
            parsed = fields.parse(note, "/patient/note")
            if parsed and parsed[0] not in pids:
                pids.append(parsed[0])
        if len(pids) >= n_patients:
            break
    cols = ["weeks postpartum at first visit", "trimester at first visit", "birth type mentioned",
            "leaking/urgency reported", "diastasis measured", "pain location", "main goal",
            "active-ageing goal"]
    short = ["pp first", "trimester", "birth", "leak", "DRA", "pain", "goal", "60+ goal"]
    print("patient_id | notes | " + " | ".join(short))
    for pid in pids[:n_patients]:
        # This endpoint ignores current_page and returns every note in one go.
        batch = plato.get(f"/patient/{pid}/note")
        if not isinstance(batch, list):
            raise PlatoError(f"/patient/{{id}}/note: expected a list, got {type(batch).__name__}")
        notes = []
        for note in batch:
            parsed = fields.parse(note, "/patient/{id}/note")
            if parsed:
                notes.append(parsed[1:])
        if not notes:
            print(f"{pid} | 0 | (no matching notes)")
            continue
        f = derive(notes)
        print(f"{pid} | {len(notes)} | " + " | ".join(",".join(sorted(f[c])) or "-" for c in cols))


def in_window(now: datetime) -> bool:
    t = now.astimezone(SGT)
    return t.hour >= WINDOW_OPEN_HOUR or (t.hour, t.minute) <= WINDOW_LAST_START


def mode_run(plato: Plato, fields: Fields, now: datetime) -> None:
    if not in_window(now):
        raise SystemExit(f"run is allowed 23:00-05:30 SGT only (now {now.astimezone(SGT):%H:%M}); exiting")
    total = plato.count("/patient/note")
    max_pages = total // PAGE_SIZE + 5
    log(f"{total} notes, ~{max_pages} pages at 1 req/{plato.interval:.0f}s")

    by_patient: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for page, batch in enumerate(plato.pages("/patient/note", max_pages=max_pages), 1):
        for note in batch:
            parsed = fields.parse(note, f"/patient/note page {page}")
            if parsed:
                by_patient[parsed[0]].append(parsed[1:])
        if page % 10 == 0:
            log(f"page {page}/{max_pages - 5}")

    per_patient = {pid: derive(notes) for pid, notes in by_patient.items()}
    by_patient.clear()  # note text is no longer needed; drop it before the next fetch

    # Ages for the 60+ group: DOB -> whole years in memory, keep id -> age only.
    ages: dict[str, int] = {}
    today = now.astimezone(SGT).date()
    for batch in plato.pages("/patient", max_pages=200):
        for p in batch:
            if not isinstance(p, dict):
                raise PlatoError(f"/patient: row is {type(p).__name__}, not an object")
            pid = str(p.get("_id") or p.get("id") or "")
            a = age_on(p.get("dob"), today)
            if pid and a is not None:
                ages[pid] = a
    matched = sum(1 for pid in per_patient if pid in ages)
    log(f"{matched}/{len(per_patient)} note patients matched a patient record with a DOB")

    print(report(per_patient, ages))
    log(f"done, {plato.requests} requests")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("mode", choices=["shape", "spot-check", "run"])
    ap.add_argument("--patients", type=int, default=20, help="spot-check: how many patients")
    ap.add_argument("--patient-field", default="patient_id")
    ap.add_argument("--date-field", default="timestamp")
    ap.add_argument("--text-field", default="note")
    ap.add_argument("--type-field", help="keep only notes whose FIELD is in --types")
    ap.add_argument("--types", help="comma-separated values of --type-field to keep")
    args = ap.parse_args(argv)

    key = os.environ.get("PLATO_API_KEY")
    if not key:
        print("missing env var: PLATO_API_KEY", file=sys.stderr)
        return 1
    if bool(args.type_field) != bool(args.types):
        print("--type-field and --types go together", file=sys.stderr)
        return 1
    plato = Plato(os.environ.get("PLATO_DB", "gojihealth"), key)
    fields = Fields(args.patient_field, args.date_field, args.text_field, args.type_field,
                    set(args.types.split(",")) if args.types else None)
    try:
        if args.mode == "shape":
            mode_shape(plato)
        elif args.mode == "spot-check":
            mode_spot_check(plato, fields, args.patients)
        else:
            mode_run(plato, fields, datetime.now(timezone.utc))
    except (PlatoError, requests.RequestException) as e:
        # requests exceptions carry the URL, not the body.
        print(f"stopped: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
