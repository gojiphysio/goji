#!/usr/bin/env python3
"""
Cloud Run Job: republish new Instagram posts as Google Business Profile posts.

Instagram is where the clinic already posts 2-3 times a week; GBP "Updates"
want the same cadence. Rather than post twice, this job reads recent IG media
(Meta Graph API, same token as marketing_ingest) and creates one GBP localPost
per new IG post (Business Profile API v4 `localPosts.create`).

It writes outward, unlike the ingestion jobs beside it, but follows their shape
(env() helper, exit codes, append-only raw table) because the same deploy and
scheduler machinery runs it.

### Safety
- **Ships with GBP_DRY_RUN=true.** A dry run reads Instagram, decides, and logs
  the post it *would* create (status 'dry_run'), without touching GBP or needing
  any GBP credential. Live mode is a deliberate repo-var flip (README).
- **Ledger before trust.** `raw_marketing.gbp_post_sync_raw` records every
  decision. IG media already marked 'posted' or 'skipped' is never re-evaluated,
  so re-running after a partial failure can't double-post. Each live post is
  ledgered the moment GBP accepts it (one small load per post), not buffered to
  the end like the ingestion jobs — a crash between posts must not forget one.
- **Lookback window + per-run cap.** Only media from the last GBP_LOOKBACK_DAYS
  is considered, so going live never backfills the whole IG history, and at most
  GBP_MAX_POSTS are created per run; the rest wait for the next run.

### Caption cleaning
GBP rejects posts containing phone numbers and shows links as plain text, and a
trailing hashtag block reads as spam on Google. `clean_caption` strips those and
trims to GBP's 1,500-character limit. The CTA button carries the tracked
`go.gojiphysio.com/gbp-post-book` link instead.

Env vars:
  IG_USER_ID               Instagram Business/Creator id        (required)
  META_GRAPH_TOKEN         Long-lived Meta access token          (required; secret)
  GRAPH_API_VERSION        Graph API version                     default: v21.0
  GBP_DRY_RUN              'true' logs only; 'false' posts       default: true
  GBP_LOCATION             accounts/<id>/locations/<id>          (required when live)
  GBP_OAUTH_JSON           authorized-user JSON for hello@, scope business.manage
                                                                 (required when live; secret)
  GBP_CTA_URL              Post button URL     default: https://go.gojiphysio.com/gbp-post-book
  GBP_LOOKBACK_DAYS        Only consider IG media this recent    default: 3
  GBP_MAX_POSTS            Max GBP posts per run                 default: 2
  GBP_SKIP_PATTERN         Case-insensitive regex; captions matching it are skipped
                                                                 default: (none)
  BQ_PROJECT               Target BQ project                     default: goji-bi
  BQ_DATASET               Target dataset                        default: raw_marketing

Exit codes: 0 on success, 1 on config error, 2 on BQ failure, 3 on API failure.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import requests
from google.cloud import bigquery

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("gbp-post-sync")

GRAPH_BASE = "https://graph.facebook.com"
GBP_BASE = "https://mybusiness.googleapis.com/v4"
GBP_SCOPE = "https://www.googleapis.com/auth/business.manage"
GBP_SUMMARY_MAX = 1500
TIMEOUT_S = 30
TABLE = "gbp_post_sync_raw"

SCHEMA = [
    bigquery.SchemaField("_loaded_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("ig_media_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("ig_permalink", "STRING"),
    bigquery.SchemaField("ig_timestamp", "TIMESTAMP"),
    bigquery.SchemaField("status", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("reason", "STRING"),
    bigquery.SchemaField("gbp_post_name", "STRING"),
    bigquery.SchemaField("payload", "JSON"),
]


def env(name: str, default: str | None = None, required: bool = True) -> str:
    v = os.environ.get(name, default)
    if required and not v:
        log.error(f"missing env var: {name}")
        sys.exit(1)
    return v  # type: ignore[return-value]


# --- Pure helpers (unit-tested) -------------------------------------------

_URL_RE = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)
# Singapore numbers: 8 digits starting 3/6/8/9, optional +65 and one space or
# dash in the middle — "+65 8377 0401", "8377-0401", "83770401". Narrow on
# purpose so prices, dates and year ranges survive.
_PHONE_RE = re.compile(r"(\+?65[\s-]?)?(?<!\d)[3689]\d{3}[\s-]?\d{4}(?!\d)")
_TAG_LINE_RE = re.compile(r"^\s*([#@][\w.]+\s*)+$")


def clean_caption(caption: str | None) -> str:
    """Turn an IG caption into a GBP post summary. Pure.

    Drops URLs, phone numbers, trailing lines made only of #hashtags/@mentions,
    and any "link in bio" line (meaningless on Google); collapses blank-line runs;
    trims to GBP's 1,500-char limit at a word boundary. Inline hashtags mid-
    sentence are kept — removing them can break the sentence.
    """
    if not caption:
        return ""
    lines = caption.replace("\r\n", "\n").split("\n")
    while lines and (not lines[-1].strip() or _TAG_LINE_RE.match(lines[-1])):
        lines.pop()
    lines = [ln for ln in lines if "link in bio" not in ln.lower()]
    text = "\n".join(lines)
    text = _URL_RE.sub("", text)
    text = _PHONE_RE.sub("", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > GBP_SUMMARY_MAX:
        cut = text[: GBP_SUMMARY_MAX - 1]
        cut = cut[: cut.rfind(" ")] if " " in cut else cut
        text = cut.rstrip(" ,.;:-") + "…"
    return text


def pick_image(media: dict) -> str | None:
    """Best still image for a GBP post (the API takes photos, not video). Pure.

    IMAGE -> media_url; VIDEO/REELS -> thumbnail_url (the cover frame);
    CAROUSEL_ALBUM -> the first child's image (or cover frame if it's a video).
    """
    kind = media.get("media_type")
    if kind == "IMAGE":
        return media.get("media_url")
    if kind == "VIDEO":
        return media.get("thumbnail_url")
    if kind == "CAROUSEL_ALBUM":
        for child in (media.get("children") or {}).get("data") or []:
            url = pick_image(child)
            if url:
                return url
        return media.get("media_url")
    return None


def parse_ig_timestamp(ts: str) -> datetime:
    """Meta returns '2026-10-27T10:15:00+0000'; BigQuery wants '+00:00'."""
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")


def build_local_post(summary: str, image_url: str, cta_url: str) -> dict:
    """localPosts.create body. Pure."""
    return {
        "languageCode": "en",
        "topicType": "STANDARD",
        "summary": summary,
        "callToAction": {"actionType": "BOOK", "url": cta_url},
        "media": [{"mediaFormat": "PHOTO", "sourceUrl": image_url}],
    }


def decide(media_list: list[dict], done_ids: set[str], now: datetime,
           lookback_days: int, skip_re: re.Pattern | None, max_posts: int,
           cta_url: str) -> list[dict]:
    """Decide what to do with each recent IG post. Pure — the part worth testing.

    Returns decisions oldest-first (so GBP shows them in the order they went up
    on IG), each {"media", "action": "post"|"skip", "reason", "body"}. Media that
    is already ledgered, older than the lookback window, or beyond the per-run
    cap is left out entirely — it is not a decision, just not this run's work.
    """
    cutoff = now - timedelta(days=lookback_days)
    fresh = [m for m in media_list
             if m.get("id") not in done_ids
             and parse_ig_timestamp(m["timestamp"]) >= cutoff]
    fresh.sort(key=lambda m: parse_ig_timestamp(m["timestamp"]))

    out: list[dict] = []
    posts = 0
    for m in fresh:
        caption = m.get("caption") or ""
        summary = clean_caption(caption)
        image = pick_image(m)
        reason = None
        if not summary:
            reason = "no_caption"
        elif skip_re and skip_re.search(caption):
            reason = "skip_pattern"
        elif not image:
            reason = "no_image"
        if reason:
            out.append({"media": m, "action": "skip", "reason": reason, "body": None})
            continue
        if posts >= max_posts:
            continue
        posts += 1
        out.append({"media": m, "action": "post", "reason": None,
                    "body": build_local_post(summary, image, cta_url)})
    return out


# --- Side effects ---------------------------------------------------------

def fetch_recent_media(ig_user_id: str, token: str, version: str) -> list[dict]:
    """Most recent 25 IG media. Never logs the response — it can echo the token."""
    fields = ("id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,"
              "children{media_type,media_url,thumbnail_url}")
    r = requests.get(f"{GRAPH_BASE}/{version}/{ig_user_id}/media",
                     params={"fields": fields, "limit": 25, "access_token": token},
                     timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.json().get("data") or []


def fetch_done_ids(bq: bigquery.Client, project: str, dataset: str) -> set[str]:
    """IG media ids already posted or deliberately skipped. Dry runs don't count."""
    sql = (f"SELECT DISTINCT ig_media_id FROM `{project}.{dataset}.{TABLE}` "
           "WHERE status IN ('posted', 'skipped')")
    return {row.ig_media_id for row in bq.query(sql).result()}


def gbp_session(oauth_json: str):
    """AuthorizedSession for hello@'s refresh token (GBP has no service-account
    path: managers must be real Google accounts)."""
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2.credentials import Credentials
    creds = Credentials.from_authorized_user_info(json.loads(oauth_json), scopes=[GBP_SCOPE])
    return AuthorizedSession(creds)


def ledger(bq: bigquery.Client, rows: list[dict], project: str, dataset: str) -> None:
    """Append rows to the ledger. Exit 2 on failure — an unledgered post risks a
    duplicate on the next run, so stop rather than carry on posting."""
    if not rows:
        return
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema=SCHEMA,
    )
    try:
        bq.load_table_from_json(rows, f"{project}.{dataset}.{TABLE}",
                                job_config=job_config).result()
    except Exception as e:
        log.exception("bq ledger load failed: %s", e)
        sys.exit(2)
    log.info("ledgered %d row(s)", len(rows))


def ledger_row(decision: dict, status: str, gbp_post_name: str | None = None,
               reason: str | None = None) -> dict:
    m = decision["media"]
    return {
        "_loaded_at": datetime.now(timezone.utc).isoformat(),
        "ig_media_id": m["id"],
        "ig_permalink": m.get("permalink"),
        "ig_timestamp": parse_ig_timestamp(m["timestamp"]).isoformat(),
        "status": status,
        "reason": reason if reason is not None else decision["reason"],
        "gbp_post_name": gbp_post_name,
        "payload": decision["body"],
    }


def main() -> None:
    ig_user_id = env("IG_USER_ID")
    token = env("META_GRAPH_TOKEN")
    version = env("GRAPH_API_VERSION", "v21.0", required=False)
    dry_run = env("GBP_DRY_RUN", "true", required=False).strip().lower() != "false"
    cta_url = env("GBP_CTA_URL", "https://go.gojiphysio.com/gbp-post-book", required=False)
    lookback = int(env("GBP_LOOKBACK_DAYS", "3", required=False))
    max_posts = int(env("GBP_MAX_POSTS", "2", required=False))
    pattern = env("GBP_SKIP_PATTERN", "", required=False)
    project = env("BQ_PROJECT", "goji-bi", required=False)
    dataset = env("BQ_DATASET", "raw_marketing", required=False)

    try:
        skip_re = re.compile(pattern, re.IGNORECASE) if pattern else None
    except re.error as e:
        log.error("bad GBP_SKIP_PATTERN: %s", e)
        sys.exit(1)

    session = location = None
    if not dry_run:
        location = env("GBP_LOCATION")
        if not re.fullmatch(r"accounts/\d+/locations/\d+", location):
            log.error("GBP_LOCATION must look like accounts/<id>/locations/<id>")
            sys.exit(1)
        try:
            session = gbp_session(env("GBP_OAUTH_JSON"))
        except (ValueError, KeyError) as e:
            log.error("bad GBP_OAUTH_JSON: %s", e)
            sys.exit(1)
    log.info("mode: %s", "DRY RUN (no GBP calls)" if dry_run else f"LIVE -> {location}")

    bq = bigquery.Client(project=project)
    try:
        done = fetch_done_ids(bq, project, dataset)
    except Exception as e:
        log.exception("reading ledger failed (did you run schema.sql?): %s", e)
        sys.exit(2)

    try:
        media = fetch_recent_media(ig_user_id, token, version)
    except requests.RequestException as e:
        log.error("meta graph media fetch failed: %s", type(e).__name__)
        sys.exit(3)

    decisions = decide(media, done, datetime.now(timezone.utc), lookback,
                       skip_re, max_posts, cta_url)
    log.info("%d recent IG media, %d already ledgered, %d decision(s)",
             len(media), len(done), len(decisions))

    deferred: list[dict] = []
    failed = 0
    for d in decisions:
        mid = d["media"]["id"]
        if d["action"] == "skip":
            log.info("skip %s (%s)", mid, d["reason"])
            # A dry run records skips as dry_run too, so nothing it decides is final.
            deferred.append(ledger_row(d, "dry_run" if dry_run else "skipped"))
            continue
        if dry_run:
            log.info("would post %s: %s", mid, json.dumps(d["body"], ensure_ascii=False))
            deferred.append(ledger_row(d, "dry_run"))
            continue
        try:
            r = session.post(f"{GBP_BASE}/{location}/localPosts", json=d["body"], timeout=TIMEOUT_S)
            r.raise_for_status()
            name = r.json().get("name")
        except requests.RequestException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            detail = getattr(getattr(e, "response", None), "text", "")[:500]
            log.error("gbp post failed for %s (HTTP %s): %s", mid, status, detail)
            deferred.append(ledger_row(d, "error", reason=f"http_{status}"))
            failed += 1
            continue
        log.info("posted %s -> %s", mid, name)
        ledger(bq, [ledger_row(d, "posted", gbp_post_name=name)], project, dataset)

    ledger(bq, deferred, project, dataset)
    if failed:
        sys.exit(3)


if __name__ == "__main__":
    main()
