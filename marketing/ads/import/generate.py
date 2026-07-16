#!/usr/bin/env python3
"""Generate Google Ads Editor bulk-import CSVs from google-ads-campaign-plan.md.

The plan is the source of truth; these CSVs are derived. Run from marketing/ads/:
    python3 import/generate.py
AG1 (pelvic floor) is excluded while its landing page is held — add it to AG
below once the page is live (draft: false).
"""
import re, csv, os

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN = os.path.join(HERE, "..", "google-ads-campaign-plan.md")
OUT = HERE
CAMP = "Goji - Search - Non-brand"

# Ad group -> final URL. All live as of 2026-07-16 (pelvic-floor page un-held).
AG = {
    "Pelvic floor / women's health": "https://www.gojiphysio.com/services/pelvic-floor-physiotherapy",
    "Postnatal / postpartum":     "https://www.gojiphysio.com/services/postpartum-physiotherapy",
    "Prenatal / pregnancy":       "https://www.gojiphysio.com/services/prenatal-physiotherapy",
    "General / near me / Lentor": "https://www.gojiphysio.com/physiotherapy-lentor",
}

def ag_of(header):
    return next((k for k in AG if k in header), None)

def section(txt, start, end):
    return txt.split(start, 1)[1].split(end, 1)[0]

txt = open(PLAN).read()

# --- keywords (§4): "phrase" = Phrase, [exact] = Exact, two-col layout ---
kw_rows = []
chunks = re.split(r'\*\*(AG\d[^\*]*)\*\*', section(txt, "## 4.", "## 5."))
for i in range(1, len(chunks), 2):
    key = ag_of(chunks[i])
    if not key:
        continue
    m = re.search(r'```(.*?)```', chunks[i + 1], re.S)
    for line in (m.group(1).splitlines() if m else []):
        # Extract each "phrase" or [exact] token by its own delimiters, never by
        # whitespace. A single space between two quoted keywords must not fuse
        # them (bug 2026-07-16: `"pregnancy pelvic pain treatment" "physio for
        # pregnant women"` imported as one mangled keyword).
        for tok in re.findall(r'"[^"]+"|\[[^\]]+\]', line):
            if tok[0] == '[':
                kw_rows.append([CAMP, key, tok[1:-1], "Exact"])
            else:
                kw_rows.append([CAMP, key, tok.strip('"'), "Phrase"])

# --- RSAs (§6) ---
maxH, maxD = 15, 4
hdr = ["Campaign", "Ad group"] + [f"Headline {i}" for i in range(1, maxH + 1)] \
    + [f"Description {i}" for i in range(1, maxD + 1)] + ["Final URL"]
rsa_rows = []
chunks = re.split(r'\*\*(AG\d[^\*]*)\*\*', section(txt, "## 6.", "## 7."))
for i in range(1, len(chunks), 2):
    key = ag_of(chunks[i])
    if not key:
        continue
    body = chunks[i + 1]
    def blk(after):
        m = re.search(after + r'.*?```(.*?)```', body, re.S)
        return m.group(1) if m else ""
    heads = [h.strip() for line in blk(r'Headlines[^\n]*\n').splitlines()
             for h in re.split(r'\s{2,}', line.strip()) if h.strip()]
    descs = [d.strip() for d in blk(r'Descriptions[^\n]*\n').splitlines() if d.strip()]
    rsa_rows.append([CAMP, key] + (heads + [""] * maxH)[:maxH]
                    + (descs + [""] * maxD)[:maxD] + [AG[key]])

# --- negatives (§5): bare = broad, "quoted" = phrase ---
# NOT a CSV. Campaign negatives can't be file-imported into Editor cleanly — a
# Keyword column is read as ad-group keywords, so Editor invents an ad group
# (bug 2026-07-16). Emit a plain paste list for Editor's "Make multiple changes
# -> Add as campaign-level negative keywords" dialog instead.
neg = []
for b in re.findall(r'```(.*?)```', section(txt, "## 5.", "## 6."), re.S):
    for line in b.splitlines():
        for tok in re.split(r'\s{2,}', line.strip()):
            tok = tok.strip()
            if tok:
                neg.append(tok)  # keep "quotes" (phrase); bare stays broad

def write_csv(name, header, rows):
    with open(os.path.join(OUT, name), "w", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)

write_csv("keywords.csv", ["Campaign", "Ad group", "Keyword", "Match type"], kw_rows)
write_csv("responsive-search-ads.csv", hdr, rsa_rows)
with open(os.path.join(OUT, "negative-keywords.txt"), "w") as f:
    f.write("\n".join(neg) + "\n")
print(f"keywords.csv: {len(kw_rows)} | responsive-search-ads.csv: {len(rsa_rows)} | negative-keywords.txt: {len(neg)}")
