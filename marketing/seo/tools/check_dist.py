"""Static SEO/AEO checks over the built site (marketing/website/prototype/dist).

Runs in CI on every site PR (.github/workflows/site-checks.yml) and in the
monthly SEO loop. No network. Exit 1 when any ERROR-level rule fails.

Rules are a ratchet: a rule starts as WARN while existing pages still break
it, and moves to ERROR in the PR that fixes the last offender, so it can
never regress. See ../AGENTS.md.

Usage: python3 check_dist.py [--dist PATH] [--json OUT]
"""
import argparse
import html
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
SITE_DIR = HERE.parent.parent / "website" / "prototype"
ORIGIN = "https://www.gojiphysio.com"

# rule -> level. Promote WARN -> ERROR once the site is clean for that rule.
LEVEL = {
    "jsonld_invalid": "ERROR",
    "broken_internal_link": "ERROR",
    "internal_link_slash": "ERROR",
    "sitemap_noindex": "ERROR",
    "canonical": "ERROR",
    "schema_required": "ERROR",
    "llms_dead_url": "ERROR",
    "prices_as_of": "ERROR",
    "faq_not_visible": "ERROR",
    "meta_description": "ERROR",
    "h1_count": "ERROR",
    "schema_recommended": "WARN",
    "llms_missing_page": "ERROR",
    "img_alt": "ERROR",
    "title_length": "WARN",
}

# Required / recommended JSON-LD @type per page type (website AGENTS.md).
SCHEMA = {
    "conditions": (["MedicalWebPage", "BreadcrumbList", "FAQPage"], []),
    "services": (["Service", "BreadcrumbList"], ["FAQPage"]),
    "team": (["Person"], []),
    "blog": (["BlogPosting", "BreadcrumbList"], ["FAQPage"]),
    "press": (["WebPage"], []),
}
SKIP = ("404.html", "styleguide", "search", "pagefind", "_astro")


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title, self.desc, self.canonical, self.robots = "", None, None, ""
        self.h1 = 0
        self.links, self.jsonld, self.img_no_alt = [], [], []
        self._in = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in, self._buf = "title", []
        elif tag == "meta" and a.get("name") == "description":
            self.desc = a.get("content") or ""
        elif tag == "meta" and a.get("name") == "robots":
            self.robots = a.get("content") or ""
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")
        elif tag == "h1":
            self.h1 += 1
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "img" and a.get("alt") is None:
            self.img_no_alt.append(a.get("src"))
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._in, self._buf = "jsonld", []

    def handle_data(self, data):
        if self._in:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "title" and self._in == "title":
            self.title = "".join(self._buf).strip()
            self._in = None
        elif tag == "script" and self._in == "jsonld":
            self.jsonld.append("".join(self._buf))
            self._in = None


def url_path(f: Path, dist: Path) -> str:
    rel = f.relative_to(dist).as_posix()
    if rel == "index.html":
        return "/"
    return "/" + rel[: -len("index.html")] if rel.endswith("/index.html") else "/" + rel


def resolves(path: str, dist: Path, redirects: set) -> bool:
    path = path.split("#")[0].split("?")[0] or "/"
    if path.rstrip("/") in redirects or path in redirects:
        return True
    p = dist / path.lstrip("/")
    return p.is_file() or (p / "index.html").is_file() or p.with_suffix(".html").is_file()


def needs_slash(path: str, dist: Path) -> bool:
    # Cloudflare Pages 308s /foo to /foo/ when foo/index.html is the page.
    path = path.split("#")[0].split("?")[0]
    if not path or path.endswith("/"):
        return False
    p = dist / path.lstrip("/")
    return not p.is_file() and (p / "index.html").is_file()


def types_of(blocks):
    out = set()
    for b in blocks:
        for item in b if isinstance(b, list) else [b]:
            t = item.get("@type") if isinstance(item, dict) else None
            out.update(t if isinstance(t, list) else [t])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", default=str(SITE_DIR / "dist"))
    ap.add_argument("--json")
    args = ap.parse_args()
    dist = Path(args.dist)
    if not dist.is_dir():
        sys.exit(f"no build at {dist} - run `npm run build` first")

    redirects = set()
    rp = SITE_DIR / "public" / "_redirects"
    if rp.exists():
        for line in rp.read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                redirects.add(line.split()[0].rstrip("/"))

    sitemap = set()
    for sm in dist.glob("sitemap-*.xml"):
        if sm.name == "sitemap-index.xml":  # lists sitemaps, not pages
            continue
        sitemap.update(urlparse(u).path for u in re.findall(r"<loc>([^<]+)</loc>", sm.read_text()))
    sitemap.discard("")

    findings = []

    def add(rule, path, detail):
        findings.append({"level": LEVEL[rule], "rule": rule, "path": path, "detail": detail})

    for f in sorted(dist.rglob("*.html")):
        rel = f.relative_to(dist).as_posix()
        if any(s in rel for s in SKIP):
            continue
        path = url_path(f, dist)
        page_html = f.read_text(errors="replace")
        pg = Page()
        pg.feed(page_html)
        noindex = "noindex" in pg.robots.lower()
        if noindex and path in sitemap:
            add("sitemap_noindex", path, "noindexed page is listed in the sitemap")
        if noindex:
            continue

        blocks = []
        for raw in pg.jsonld:
            try:
                blocks.append(json.loads(raw))
            except ValueError as e:
                add("jsonld_invalid", path, str(e))

        if pg.canonical != ORIGIN + path:
            add("canonical", path, f"canonical is {pg.canonical!r}, expected {ORIGIN + path!r}")
        if not pg.desc or len(pg.desc) > 160:
            add("meta_description", path, f"{len(pg.desc or '')} chars (max 160)")
        if not 0 < len(pg.title) <= 65:
            add("title_length", path, f"{len(pg.title)} chars (max 65)")
        if pg.h1 != 1:
            add("h1_count", path, f"{pg.h1} <h1> elements")
        if pg.img_no_alt:
            add("img_alt", path, f"{len(pg.img_no_alt)} <img> without alt")

        seen = set()
        for href in pg.links:
            u = urlparse(href)
            if u.scheme in ("mailto", "tel", "javascript", "sms") or href.startswith("#"):
                continue
            if u.netloc and u.netloc not in ("www.gojiphysio.com", "gojiphysio.com"):
                continue
            if u.path.startswith("/pagefind") or u.path in seen:
                continue
            seen.add(u.path)
            if not resolves(u.path, dist, redirects):
                add("broken_internal_link", path, f"links to {u.path} which is not in the build")
            elif needs_slash(u.path, dist):
                add("internal_link_slash", path, f"links to {u.path}, which redirects to {u.path}/")

        # FAQPage JSON-LD must mirror visible content (Google's structured-data
        # rules); every question has to appear in the page text outside scripts.
        visible = html.unescape(re.sub(r"<script\b.*?</script>|<[^>]+>", " ", page_html, flags=re.S))
        # Markdown curls quotes on the page; JSON-LD keeps them straight.
        straight = str.maketrans({"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'"})
        visible = " ".join(visible.translate(straight).split())
        for b in blocks:
            for item in b if isinstance(b, list) else [b]:
                if isinstance(item, dict) and item.get("@type") == "FAQPage":
                    for q in item.get("mainEntity", []):
                        name = " ".join(str(q.get("name", "")).translate(straight).split())
                        if name and name not in visible:
                            add("faq_not_visible", path, f"FAQ in JSON-LD but not on the page: {name[:70]}")

        section = path.strip("/").split("/")[0] if path.count("/") > 2 else None
        if section in SCHEMA:
            have = types_of(blocks)
            req, rec = SCHEMA[section]
            for t in req:
                if t not in have:
                    add("schema_required", path, f"missing {t} JSON-LD")
            for t in rec:
                if t not in have:
                    add("schema_recommended", path, f"missing {t} JSON-LD")
            if section == "conditions" and '"reviewedBy"' not in "".join(pg.jsonld):
                add("schema_required", path, "MedicalWebPage has no reviewedBy")

    llms = dist / "llms.txt"
    if llms.exists():
        text = llms.read_text()
        # Dated prices must agree between the site (SITE.pricesAsOf) and llms.txt.
        svc = dist / "services" / "index.html"
        site_m = re.search(r"Prices as of ([A-Z][a-z]+ \d{4})", svc.read_text()) if svc.exists() else None
        llms_m = re.search(r"as of ([A-Z][a-z]+ \d{4})", text)
        if site_m and (not llms_m or llms_m.group(1) != site_m.group(1)):
            add("prices_as_of", "/llms.txt", f"site says prices as of {site_m.group(1)}, "
                f"llms.txt says {llms_m.group(1) if llms_m else 'nothing'}")
        listed = {urlparse(u).path for u in re.findall(r"https://www\.gojiphysio\.com[^\s)>\]]*", text)}
        for p in sorted(listed):
            if not resolves(p, dist, redirects):
                add("llms_dead_url", p, "llms.txt lists a URL that is not in the build")
        norm = {p.rstrip("/") or "/" for p in listed}
        for p in sorted(sitemap):
            if (p.rstrip("/") or "/") not in norm:
                add("llms_missing_page", p, "sitemap page not listed in llms.txt")

    errors = [x for x in findings if x["level"] == "ERROR"]
    lines = [f"## Site checks: {len(errors)} errors, {len(findings) - len(errors)} warnings", ""]
    for lvl in ("ERROR", "WARN"):
        rows = [x for x in findings if x["level"] == lvl]
        if rows:
            lines += [f"### {lvl}", "", "| rule | path | detail |", "|---|---|---|"]
            lines += [f"| {x['rule']} | `{x['path']}` | {x['detail']} |" for x in rows]
            lines.append("")
    report = "\n".join(lines)
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(report + "\n")
    if args.json:
        Path(args.json).write_text(json.dumps(findings, indent=1))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
