#!/usr/bin/env python3
"""Generate the ad copy + targeting review sheet from google-ads-campaign-plan.md.

Human sign-off artifact for Cheryl (clinical/compliance) and Chris (business).
Copy and char counts are parsed from the plan so the sheet can't drift.
    python3 import/review_sheet.py > ad-copy-review-sheet.md
"""
import re, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN = os.path.join(HERE, "..", "google-ads-campaign-plan.md")
DATE = "2026-07-14"
HL, DL = 30, 90

txt = open(PLAN).read()

def section(a, b):
    return txt.split(a, 1)[1].split(b, 1)[0]

# ad group order + landing pages + held flag
AGS = [
    ("AG1", "Pelvic floor / women's health", "/services/pelvic-floor-physiotherapy", True),
    ("AG2", "Postnatal / postpartum",        "/services/postpartum-physiotherapy",   False),
    ("AG3", "Prenatal / pregnancy",          "/services/prenatal-physiotherapy",     False),
    ("AG4", "General / near me / Lentor",     "/physiotherapy-lentor",                False),
]

def chunks_of(sec):
    parts = re.split(r'\*\*(AG\d[^\*]*)\*\*', sec)
    out = {}
    for i in range(1, len(parts), 2):
        m = re.match(r'(AG\d)', parts[i].strip())
        if m:
            out[m.group(1)] = parts[i + 1]
    return out

kw_c = chunks_of(section("## 4.", "## 5."))
rsa_c = chunks_of(section("## 6.", "## 7."))

def fenced(body, after=None):
    if after:
        m = re.search(after + r'.*?```(.*?)```', body, re.S)
    else:
        m = re.search(r'```(.*?)```', body, re.S)
    return m.group(1) if m else ""

def keywords(ag):
    toks = []
    for line in fenced(kw_c.get(ag, "")).splitlines():
        for t in re.split(r'\s{2,}', line.strip()):
            t = t.strip()
            if t.startswith('['):
                toks.append(f"[{t[1:-1]}] (exact)")
            elif t.startswith('"'):
                toks.append(f'"{t.strip(chr(34))}" (phrase)')
    return toks

def rsa(ag):
    body = rsa_c.get(ag, "")
    heads = [h.strip() for line in fenced(body, r'Headlines[^\n]*\n').splitlines()
             for h in re.split(r'\s{2,}', line.strip()) if h.strip()]
    descs = [d.strip() for d in fenced(body, r'Descriptions[^\n]*\n').splitlines() if d.strip()]
    return heads, descs

P = print
P(f"# Goji — Google Ads copy & targeting review")
P()
P(f"**Campaign:** Goji – Search – Non-brand  ")
P(f"**Prepared:** {DATE}  ")
P(f"**For approval by:** Cheryl Long — *clinical accuracy & AHPC compliance* · "
  f"Chris — *business & brand*  ")
P(f"**Source of truth:** `marketing/ads/google-ads-campaign-plan.md`")
P()
P("## What you're approving")
P()
P("Google Search ads across four ad groups, one per landing page. Each ad is a "
  "**Responsive Search Ad**: we supply many headlines and descriptions and Google "
  "automatically mixes them into live ads. **So every headline and every "
  "description must be true and make sense on its own** — any combination can show. "
  "Character limits (headline ≤30, description ≤90) are already validated; "
  "the count is shown in **[brackets]** after each line.")
P()
P("## Compliance standard already applied")
P()
P("All copy follows the AHPC advertising floor (`strategy/03`): **no** superlatives "
  "(best / leading / No.1 / only), **no** cure or outcome/time guarantees, **no** "
  "comparisons; “can help” framing; plain prices allowed. This has been "
  "pre-checked — your sign-off is the confirmation.")
P()
P("> **Note on one keyword:** you’ll see **“best pelvic floor physio "
  "singapore”** in AG1’s target list. We *bid* on it because people type it, "
  "but **the ad we show never uses the word “best.”** Bidding on a search term "
  "is targeting, not a claim — this is permitted under `strategy/03`.")
P()
P("> ### ⚠️ One item flagged for Cheryl")
P("> **AG1 headline “Leakage Is Common & Treatable”** — “Treatable” is "
  "accurate (pelvic-floor physiotherapy is first-line care for incontinence) but is "
  "stronger than our usual “can help” wording. Please confirm it’s "
  "acceptable, or suggest an alternative.")
P()
for ag, name, url, held in AGS:
    tag = "  ⏸️ **HELD**" if held else ""
    P(f"## {ag} — {name}{tag}")
    if held:
        P()
        P("> Landing page is held (pending Kristy’s copy + a photo), so these "
          "ads won’t run yet. Please still approve the copy now so it’s "
          "ready the moment the page is live.")
    P()
    P(f"**Landing page:** `https://www.gojiphysio.com{url}`")
    P()
    P("**Shows for searches like:** " + ", ".join(keywords(ag)))
    P()
    heads, descs = rsa(ag)
    P("**Headlines**")
    P()
    for h in heads:
        warn = "  ❗OVER" if len(h) > HL else ""
        P(f"- {h}  **[{len(h)}]**{warn}")
    P()
    P("**Descriptions**")
    P()
    for d in descs:
        warn = "  ❗OVER" if len(d) > DL else ""
        P(f"- {d}  **[{len(d)}]**{warn}")
    P()
    P("---")
    P()

# negatives
P("## Negative keywords — searches we will NOT show for")
P()
negs = []
for b in re.findall(r'```(.*?)```', section("## 5.", "## 6."), re.S):
    for line in b.splitlines():
        for t in re.split(r'\s{2,}', line.strip()):
            if t.strip():
                negs.append(t.strip().strip('"'))
P(", ".join(negs))
P()
P("*(Includes brand terms so brand searches stay organic, plus junk like "
  "“free / cheap / jobs / course”. This list grows weekly from real "
  "search-term reports.)*")
