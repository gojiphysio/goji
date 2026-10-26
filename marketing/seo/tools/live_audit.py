"""Live-site SEO/AEO checks against https://www.gojiphysio.com (read-only).

Runs weekly in CI (.github/workflows/site-checks.yml) and in the monthly SEO
loop. Stdlib only. Exit 1 when any ERROR-level check fails.

  - every sitemap URL returns 200 with a self-referencing canonical
  - every internal link target resolves (redirect hops are counted, not errors)
  - AI and search crawlers get 200 with no Cloudflare challenge, and the live
    robots.txt does not disallow them
  - llms.txt is served
  - Core Web Vitals via PageSpeed Insights when PSI_API_KEY is set

Usage: python3 live_audit.py --out DIR
"""
import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_dist import Page  # noqa: E402

BASE = "https://www.gojiphysio.com"
UA = "Mozilla/5.0 (compatible; GojiSiteAudit/1.0; +https://www.gojiphysio.com)"
BOTS = {
    "GPTBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)",
    "OAI-SearchBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)",
    "ChatGPT-User": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot",
    "PerplexityBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)",
    "ClaudeBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
    "Claude-SearchBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-SearchBot/1.0; +https://www.anthropic.com)",
    "Googlebot": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Bingbot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
    "meta-externalagent": "meta-externalagent/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler)",
    "meta-webindexer": "meta-webindexer/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler)",
}
BOT_PAGES = ["/", "/services/pelvic-floor-physiotherapy/", "/conditions/diastasis-recti/", "/llms.txt"]
PSI_PAGES = ["/", "/womens-health-physiotherapy-singapore/", "/services/pelvic-floor-physiotherapy/",
             "/conditions/diastasis-recti/", "/book/"]
CHALLENGE = ("cf-chl", "challenge-platform", "just a moment", "cf_chl_opt")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


try:  # python.org builds on macOS ship without a CA bundle
    import certifi
    SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL = ssl.create_default_context()
OPENER = urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=SSL))


def get(url, ua=UA, max_hops=5):
    """GET without auto-redirect; returns (status, final_url, hops, body)."""
    hops = []
    for _ in range(max_hops + 1):
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        try:
            with OPENER.open(req, timeout=30) as r:
                return r.status, url, hops, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                hops.append(f"{e.code} {url}")
                url = urllib.parse.urljoin(url, e.headers["Location"])
                continue
            return e.code, url, hops, e.read().decode("utf-8", "replace")
        except Exception as e:  # network error
            return f"ERR {type(e).__name__}", url, hops, ""
    return "TOO_MANY_REDIRECTS", url, hops, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    findings, data = [], {"pages": {}, "links": {}, "bots": [], "psi": {}}

    def add(level, check, target, detail):
        findings.append({"level": level, "check": check, "target": target, "detail": detail})

    # Sitemap pages
    _, _, _, idx = get(BASE + "/sitemap-index.xml")
    urls = []
    for sm in re.findall(r"<loc>([^<]+)</loc>", idx):
        urls += re.findall(r"<loc>([^<]+)</loc>", get(sm)[3])
    if not urls:
        add("ERROR", "sitemap", "/sitemap-index.xml", "no URLs found")
    internal = set()
    external = {}  # url -> first page linking to it
    for u in urls:
        status, final, hops, body = get(u)
        time.sleep(0.3)
        pg = Page()
        pg.feed(body)
        data["pages"][u] = {"status": status, "hops": hops, "canonical": pg.canonical, "title": pg.title}
        if status != 200:
            add("ERROR", "sitemap_status", u, f"{status} {hops}")
            continue
        if hops:
            add("WARN", "sitemap_redirect", u, " -> ".join(hops))
        if pg.canonical != u:
            add("ERROR", "canonical", u, f"canonical {pg.canonical!r}")
        for href in pg.links:
            p = urllib.parse.urlparse(urllib.parse.urljoin(u, href))
            if p.netloc == "www.gojiphysio.com" and not p.path.startswith("/pagefind"):
                internal.add(p.path)
            elif p.scheme in ("http", "https") and p.netloc:
                external.setdefault(p.geturl(), u)

    # Internal link targets
    redirected = 0
    for path in sorted(internal):
        status, final, hops, _ = get(BASE + path)
        time.sleep(0.2)
        data["links"][path] = {"status": status, "hops": hops}
        if status != 200:
            add("ERROR", "internal_link", path, f"{status}")
        elif hops:
            redirected += 1
    if redirected:  # ratcheted to ERROR on 2026-10-20 once the site had none
        add("ERROR", "internal_link_redirects", f"{redirected} targets",
            "internal links that redirect before 200 (usually missing trailing slash)")

    # Outbound links. Tracked CTAs (go.gojiphysio.com) must redirect; other
    # sites only count as broken on 404/410/5xx, since social sites refuse bots.
    for url, src in sorted(external.items()):
        status, final, hops, _ = get(url, max_hops=0 if "go.gojiphysio.com" in url else 5)
        time.sleep(0.2)
        data["links"][url] = {"status": status, "from": src}
        if "go.gojiphysio.com" in url:
            if not hops:  # max_hops=0: a working slug records one redirect hop
                add("ERROR", "tracked_cta", url, f"{status} (expected a redirect) on {src}")
        elif status in (404, 410) or (isinstance(status, int) and status >= 500):
            add("WARN", "external_link_broken", url, f"{status} on {src}")

    # Crawlers
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(get(BASE + "/robots.txt")[3].splitlines())
    for name, ua in BOTS.items():
        if not rp.can_fetch(name, BASE + "/"):
            add("ERROR", "robots", name, "live robots.txt disallows /")
        for p in BOT_PAGES:
            status, _, _, body = get(BASE + p, ua=ua)
            challenged = any(s in body[:20000].lower() for s in CHALLENGE)
            data["bots"].append({"bot": name, "path": p, "status": status, "challenge": challenged})
            if status != 200 or challenged:
                add("ERROR", "crawler_access", f"{name} {p}", f"{status} challenge={challenged}")
            time.sleep(0.3)

    # Hosts (informational)
    for h in ("https://gojiphysio.com/", "http://www.gojiphysio.com/"):
        status, final, hops, _ = get(h)
        # The apex forward sends `Location: https://www.gojiphysio.com` with no
        # path, which browsers treat as "/". Compare it as such.
        if final and not urllib.parse.urlsplit(final).path:
            final += "/"
        data.setdefault("hosts", {})[h] = {"status": status, "final": final, "hops": hops}
        if status != 200 or final != BASE + "/":
            add("ERROR", "host", h, f"{status} -> {final}")
        elif any(x.split(" ", 1)[1].startswith("http://") for x in hops[1:]):
            add("WARN", "host_insecure_hop", h, " -> ".join(hops))

    # PageSpeed Insights (mobile), only with a key: the keyless quota is shared and often 429s.
    key = os.environ.get("PSI_API_KEY")
    for p in PSI_PAGES if key else []:
        q = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed?" + urllib.parse.urlencode(
            {"url": BASE + p, "strategy": "mobile", "category": "performance", "key": key})
        try:
            with urllib.request.urlopen(q, timeout=180, context=SSL) as r:
                d = json.load(r)
            a = d["lighthouseResult"]["audits"]
            rec = {
                "score": d["lighthouseResult"]["categories"]["performance"]["score"],
                "lcp_ms": a["largest-contentful-paint"]["numericValue"],
                "cls": a["cumulative-layout-shift"]["numericValue"],
                "tbt_ms": a["total-blocking-time"]["numericValue"],
                "field": (d.get("loadingExperience") or {}).get("overall_category"),
            }
            data["psi"][p] = rec
            if rec["lcp_ms"] > 2500 or rec["cls"] > 0.1 or rec["score"] < 0.7:
                add("WARN", "core_web_vitals", p, json.dumps(rec))
        except Exception as e:
            add("WARN", "psi", p, f"PageSpeed Insights failed: {e}")
    if not key:
        add("WARN", "psi", "-", "PSI_API_KEY not set; Core Web Vitals not measured")

    errors = [f for f in findings if f["level"] == "ERROR"]
    lines = [f"## Live audit: {len(urls)} sitemap URLs, {len(internal)} link targets, "
             f"{len(errors)} errors, {len(findings) - len(errors)} warnings", ""]
    if findings:
        lines += ["| level | check | target | detail |", "|---|---|---|---|"]
        lines += [f"| {f['level']} | {f['check']} | `{f['target']}` | {f['detail']} |" for f in findings]
    report = "\n".join(lines)
    print(report)
    (out / "live.md").write_text(report + "\n")
    (out / "live.json").write_text(json.dumps({"findings": findings, **data}, indent=1))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(report + "\n")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
