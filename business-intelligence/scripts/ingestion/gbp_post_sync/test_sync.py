"""Unit tests for gbp_post_sync's pure helpers. No network / no BQ."""
import re
from datetime import datetime, timezone

from main import (GBP_SUMMARY_MAX, build_local_post, clean_caption, decide,
                  parse_ig_timestamp, pick_image)

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
CTA = "https://go.gojiphysio.com/gbp-post-book"


def media(mid, ts="2026-10-28T02:00:00+0000", caption="Pelvic floor tips for new mums.",
          kind="IMAGE", **kw):
    return {"id": mid, "timestamp": ts, "caption": caption, "media_type": kind,
            "media_url": f"https://cdn.example/{mid}.jpg", **kw}


# --- clean_caption --------------------------------------------------------

def test_clean_caption_strips_trailing_hashtag_block():
    cap = "Three things to know after birth.\n\n#postpartum #pelvicfloor\n@gojiphysio"
    assert clean_caption(cap) == "Three things to know after birth."


def test_clean_caption_keeps_inline_hashtags():
    assert clean_caption("Our #pelvicfloor class is back.") == "Our #pelvicfloor class is back."


def test_clean_caption_strips_sg_phone_numbers_and_urls():
    cap = "WhatsApp +65 8377 0401 or 8377-0401, or visit https://www.gojiphysio.com/book today."
    out = clean_caption(cap)
    assert "8377" not in out and "http" not in out
    assert out.endswith("today.")


def test_clean_caption_keeps_prices_dates_and_years():
    cap = "Sessions from $180. Workshop 19 Sep 2026, 10am. Open 2026 - 2027."
    assert clean_caption(cap) == cap


def test_clean_caption_drops_link_in_bio_line():
    assert clean_caption("Book now.\nLink in bio 👆") == "Book now."


def test_clean_caption_truncates_to_gbp_limit_at_word_boundary():
    out = clean_caption("word " * 400)
    assert len(out) <= GBP_SUMMARY_MAX and out.endswith("…")
    assert not out[:-1].endswith(" ")


def test_clean_caption_empty():
    assert clean_caption(None) == "" and clean_caption("#tag #only") == ""


# --- pick_image -----------------------------------------------------------

def test_pick_image_by_type():
    assert pick_image({"media_type": "IMAGE", "media_url": "a.jpg"}) == "a.jpg"
    assert pick_image({"media_type": "VIDEO", "media_url": "v.mp4",
                       "thumbnail_url": "cover.jpg"}) == "cover.jpg"
    album = {"media_type": "CAROUSEL_ALBUM", "media_url": "x", "children": {"data": [
        {"media_type": "VIDEO", "thumbnail_url": "first.jpg"},
        {"media_type": "IMAGE", "media_url": "second.jpg"}]}}
    assert pick_image(album) == "first.jpg"
    assert pick_image({"media_type": "VIDEO"}) is None


def test_parse_ig_timestamp_is_bq_friendly():
    assert parse_ig_timestamp("2026-10-27T10:15:00+0000").isoformat() == "2026-10-27T10:15:00+00:00"


def test_build_local_post_shape():
    body = build_local_post("Hi", "img.jpg", CTA)
    assert body["callToAction"] == {"actionType": "BOOK", "url": CTA}
    assert body["media"] == [{"mediaFormat": "PHOTO", "sourceUrl": "img.jpg"}]
    assert body["topicType"] == "STANDARD" and body["summary"] == "Hi"


# --- decide ---------------------------------------------------------------

def test_decide_skips_ledgered_and_old_media():
    ms = [media("done"), media("old", ts="2026-10-20T02:00:00+0000"), media("new")]
    out = decide(ms, {"done"}, NOW, 3, None, 5, CTA)
    assert [d["media"]["id"] for d in out] == ["new"]


def test_decide_posts_oldest_first_and_caps_per_run():
    ms = [media("c", ts="2026-10-28T03:00:00+0000"),
          media("a", ts="2026-10-26T03:00:00+0000"),
          media("b", ts="2026-10-27T03:00:00+0000")]
    out = decide(ms, set(), NOW, 3, None, 2, CTA)
    assert [(d["media"]["id"], d["action"]) for d in out] == [("a", "post"), ("b", "post")]


def test_decide_skip_reasons_do_not_use_the_cap():
    ms = [media("nocap", caption="#tag", ts="2026-10-27T01:00:00+0000"),
          media("team", caption="Team lunch!", ts="2026-10-27T02:00:00+0000"),
          media("noimg", kind="VIDEO", ts="2026-10-27T03:00:00+0000"),
          media("ok", ts="2026-10-27T04:00:00+0000")]
    out = decide(ms, set(), NOW, 3, re.compile("team", re.I), 1, CTA)
    assert [(d["media"]["id"], d["action"], d["reason"]) for d in out] == [
        ("nocap", "skip", "no_caption"), ("team", "skip", "skip_pattern"),
        ("noimg", "skip", "no_image"), ("ok", "post", None)]
    assert out[-1]["body"]["media"][0]["sourceUrl"] == "https://cdn.example/ok.jpg"


# --- main() dry run: no GBP call, everything ledgered as dry_run -----------

def test_main_dry_run_never_touches_gbp(monkeypatch):
    import main as m

    loaded = []

    class FakeBQ:
        def __init__(self, project): pass

    monkeypatch.setattr(m.bigquery, "Client", FakeBQ)
    monkeypatch.setattr(m, "fetch_done_ids", lambda bq, p, d: set())
    monkeypatch.setattr(m, "fetch_recent_media", lambda *a: [
        media("p1", ts=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")),
        media("s1", caption="#only", ts=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")),
    ])
    monkeypatch.setattr(m, "ledger", lambda bq, rows, p, d: loaded.extend(rows))
    monkeypatch.setattr(m, "gbp_session", lambda *_: (_ for _ in ()).throw(AssertionError("GBP called")))
    for k, v in {"IG_USER_ID": "1", "META_GRAPH_TOKEN": "t"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("GBP_DRY_RUN", raising=False)

    m.main()
    assert sorted((r["ig_media_id"], r["status"]) for r in loaded) == [
        ("p1", "dry_run"), ("s1", "dry_run")]
    assert next(r for r in loaded if r["ig_media_id"] == "p1")["payload"]["callToAction"]["url"] == CTA
