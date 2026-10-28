"""Classify a PR's diff into an approval tier for the SEO loop (see ../AGENTS.md).

  A  safe to self-merge after CI: technical SEO, schema, meta, internal links,
     llms.txt, images, rewording copy that is already clinically reviewed.
  B  needs Cheryl's clinical review: new pages, blog posts, reviewer/date
     changes, new numeric or time claims, compliance-lint hits.
  C  needs the owner's approval: booking, CTAs/links, prices, NAP/hours,
     redirects, robots, build config, analytics, CI and this gate itself,
     or anything outside the site and SEO docs.

CI runs this on every PR. It only FAILS when the PR carries the `tier-a`
label but the diff is not tier A, so the loop can never self-merge a B/C
change by mislabelling it. Without the label it just reports the tier.

Usage: python3 tier_gate.py [--base origin/main] [--labels tier-a,...]
"""
import argparse
import fnmatch
import os
import re
import subprocess
import sys

SITE = "marketing/website/"

# Tier A may touch only these (modifications; new files are tier B).
ALLOW_A = [
    SITE + "src/content/conditions/*.md",
    SITE + "src/content/services/*.md",
    SITE + "src/content/team/*.md",
    SITE + "src/content/press/*.md",
    SITE + "src/pages/*.astro",
    SITE + "src/pages/**/*.astro",
    SITE + "src/components/*.astro",
    SITE + "src/lib/schema.ts",
    SITE + "src/lib/faq.ts",
    SITE + "src/styles/*.css",
    SITE + "public/llms.txt",
    SITE + "public/photos/**",
    SITE + "public/brand/**",
    "marketing/seo/seo-geo-review.md",
    "marketing/seo/aeo-queries.json",
    "marketing/seo/audits/**",
]
# Always tier C, even inside an allowed glob.
PROTECT_C = [
    SITE + "src/pages/book.astro",
    SITE + "src/components/booking/**",
    SITE + "src/layouts/**",
    SITE + "src/lib/links.ts",
    SITE + "src/lib/booking.ts",
    SITE + "src/lib/site.ts",
    SITE + "public/_redirects",
    SITE + "public/robots.txt",
    SITE + "astro.config.mjs",
    SITE + "package*.json",
    "marketing/seo/tools/**",
    "marketing/seo/AGENTS.md",
    ".github/**",
]
TIER_B_NEW_FILES = [SITE + "src/content/**", SITE + "src/pages/**"]
CONTENT = SITE + "src/"

# Compliance lint on ADDED lines of site copy (strategy/03-compliance-guardrails.md).
LINT = [
    (r"\b(best|leading|top[- ]rated|world[- ]class|award[- ]winning)\b", "superlative"),
    (r"\b(no\.? ?1|number one|#1|the only)\b", "superlative"),
    (r"\b(guarantee[sd]?|guaranteed)\b", "outcome guarantee"),
    (r"\b(cure[sd]?|curing)\b", "cure claim"),
    (r"\bpain[- ]free\b", "outcome claim"),
    (r"\b(fix(es)? your|permanently (fix|resolve))\b", "outcome claim"),
    (r"\bresults? in \d+", "time-bound outcome"),
    (r"\b100 ?%", "absolute claim"),
    (r"\b(better|more effective) than\b", "comparative claim"),
    (r"\b(testimonial|before and after|before/after)\b", "testimonial/before-after"),
    (r"\b(discount|% off|promo code|limited time)\b", "discount framing (Lane A)"),
]
NUMERIC_CLAIM = re.compile(r"\b\d+(\.\d+)?\s*(%|percent|per cent|weeks?|months?|days?|sessions?|years?|times)\b", re.I)
PRICE = re.compile(r"\$\s?\d[\d,]*")
REVIEW_FIELDS = re.compile(r"^\s*(reviewer|lastReviewed|reviewedBy|author)\s*:", re.I)


def git(*a):
    return subprocess.run(["git", *a], check=True, capture_output=True, text=True).stdout


def match(path, globs):
    return any(fnmatch.fnmatch(path, g) for g in globs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--labels", default=os.environ.get("PR_LABELS", ""))
    args = ap.parse_args()
    labels = {l.strip() for l in args.labels.split(",") if l.strip()}

    reasons = {"B": [], "C": []}
    for line in git("diff", "--name-status", f"{args.base}...HEAD").splitlines():
        status, *paths = line.split("\t")
        for path in paths:
            if match(path, PROTECT_C) or not match(path, ALLOW_A):
                reasons["C"].append(f"{path}: protected or outside the tier A allow-list")
            elif status.startswith(("A", "R", "C")) and match(path, TIER_B_NEW_FILES):
                reasons["B"].append(f"{path}: new page or content file")

        if not paths[-1].startswith(CONTENT) and not paths[-1].endswith("llms.txt"):
            continue
        path = paths[-1]
        diff = git("diff", "-U0", f"{args.base}...HEAD", "--", path)
        added = [l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
        removed = [l[1:] for l in diff.splitlines() if l.startswith("-") and not l.startswith("---")]
        old = " ".join(removed)
        for l in added:
            if REVIEW_FIELDS.match(l):
                reasons["B"].append(f"{path}: changes clinical review metadata: {l.strip()[:80]}")
            for rx, why in LINT:
                m = re.search(rx, l, re.I)
                if m:
                    reasons["B"].append(f"{path}: compliance lint ({why}): '{m.group(0)}' in: {l.strip()[:100]}")
        new_prices = set(PRICE.findall(" ".join(added))) - set(PRICE.findall(old))
        if new_prices:
            reasons["C"].append(f"{path}: new price figures {sorted(new_prices)}")
        new_claims = {m.group(0).lower() for m in NUMERIC_CLAIM.finditer(" ".join(added))}
        new_claims -= {m.group(0).lower() for m in NUMERIC_CLAIM.finditer(old)}
        if new_claims:
            reasons["B"].append(f"{path}: new numeric/time claims {sorted(new_claims)}")

    tier = "C" if reasons["C"] else "B" if reasons["B"] else "A"
    out = [f"## Tier gate: tier {tier}", ""]
    for t in ("C", "B"):
        out += [f"- **{t}** {r}" for r in reasons[t]]
    if tier == "A":
        out.append("Safe to self-merge after checks pass.")
    report = "\n".join(out)
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(report + "\n")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
            fh.write(f"tier={tier}\n")
    if "tier-a" in labels and tier != "A":
        print("\nFAIL: labelled tier-a but the diff is tier " + tier, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
