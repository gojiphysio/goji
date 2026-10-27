"""Submit recently changed pages to IndexNow (Bing, Yandex, Seznam, Naver).

Bing feeds ChatGPT search, and IndexNow gets a new or changed URL crawled in
hours instead of waiting for the sitemap to be re-read. Runs daily in CI
(.github/workflows/indexnow.yml) and on demand after a content deploy.

Reads the LIVE sitemap, keeps URLs whose <lastmod> falls within --days, checks
each returns 200 (so a page that hasn't deployed yet is skipped, not burned),
and posts them in one batch. The key file is public by design: IndexNow
verifies ownership by fetching https://www.gojiphysio.com/<key>.txt, which
lives in website/prototype/public/. Stdlib only.

Usage: python3 indexnow_submit.py [--days 2] [--url URL ...] [--dry-run]
"""
import argparse
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://www.gojiphysio.com"
HOST = "www.gojiphysio.com"
KEY = "8a2d9555cf107ab15715192ad0c53463"
ENDPOINT = "https://api.indexnow.org/indexnow"
UA = "Mozilla/5.0 (compatible; GojiIndexNow/1.0; +https://www.gojiphysio.com)"

# python.org builds on macOS ship without system CA certs; use certifi when present.
try:
    import certifi

    SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL = ssl.create_default_context()


def get(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30, context=SSL) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def sitemap_entries() -> list[tuple[str, datetime | None]]:
    _, index = get(f"{BASE}/sitemap-index.xml")
    entries = []
    for sm in re.findall(r"<loc>(.*?)</loc>", index):
        _, body = get(sm)
        for block in re.findall(r"<url>(.*?)</url>", body, re.S):
            loc = re.search(r"<loc>(.*?)</loc>", block).group(1)
            lm = re.search(r"<lastmod>(.*?)</lastmod>", block)
            when = datetime.fromisoformat(lm.group(1).replace("Z", "+00:00")) if lm else None
            entries.append((loc, when))
    return entries


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=2, help="submit pages whose lastmod is this recent")
    ap.add_argument("--url", action="append", default=[], help="submit this URL as well (repeatable)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    status, body = get(f"{BASE}/{KEY}.txt")
    if status != 200 or body.strip() != KEY:
        print(f"ERROR: key file not served correctly ({status}); IndexNow would reject the batch")
        return 1

    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    urls = [u for u, when in sitemap_entries() if when and when >= since] + args.url
    live = [u for u in dict.fromkeys(urls) if get(u)[0] == 200]
    skipped = sorted(set(urls) - set(live))
    for u in skipped:
        print(f"skip (not 200 yet): {u}")
    if not live:
        print(f"Nothing changed in the last {args.days:g} days.")
        return 0

    print(f"Submitting {len(live)} URL(s):", *live, sep="\n  ")
    if args.dry_run:
        return 0
    payload = json.dumps(
        {"host": HOST, "key": KEY, "keyLocation": f"{BASE}/{KEY}.txt", "urlList": live}
    ).encode()
    req = urllib.request.Request(
        ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=30, context=SSL) as r:
            print(f"IndexNow: {r.status}")
    except urllib.error.HTTPError as e:
        # 200/202 are success; 422 means a URL isn't on this host; 403 a key problem.
        print(f"ERROR: IndexNow returned {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
