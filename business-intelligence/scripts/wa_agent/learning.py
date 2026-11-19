"""
Learning signals: how each conversation went, so the agent gets better over time.

Three signals are worked out here, at the moment they happen, so that only
labels (never text) reach BigQuery:

- Draft outcome. When Chris replies after the agent drafted, how close her
  reply is to the draft: sent unchanged, edited, or replaced. Unchanged drafts
  are evidence an intent could be answered on its own; edits are the
  preference data the offline replay is scored against.
- Rescue. Chris writes in a chat the agent was handling on its own (it
  auto-sent, nothing was drafted or escalated). That is a failure.
- Demotion. An intent that keeps getting rescued drops back to draft by
  itself: of its last DEMOTE_WINDOW auto-sent replies, DEMOTE_RESCUES or more
  were rescued. Only a person promotes it again (admin route), because going
  from draft to auto is the risky direction.

Pure functions over plain data; app.py records the events and stores state.
"""
from __future__ import annotations

import difflib
import hashlib
import hmac
import re

from . import config

DRAFT_MATCH_WINDOW_S = 24 * 3600
RESCUE_WINDOW_S = 24 * 3600
UNCHANGED_AT = 0.9
EDITED_AT = 0.5
DEMOTE_WINDOW = 20
DEMOTE_RESCUES = 3

_SPACE = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _SPACE.sub(" ", (text or "").strip().lower())


def draft_outcome(draft: str, sent: str) -> tuple[float, str]:
    """(similarity 0-1, sent_unchanged | edited | replaced)."""
    ratio = difflib.SequenceMatcher(None, _norm(draft), _norm(sent)).ratio()
    label = ("sent_unchanged" if ratio >= UNCHANGED_AT
             else "edited" if ratio >= EDITED_AT else "replaced")
    return round(ratio, 3), label


def classify_echo(state, now: float) -> dict:
    """What Chris's message means for learning. Reads and clears the pending
    draft / last auto-send on `state`. Returns event fields to record."""
    draft = state.pending_draft or {}
    if draft and now - draft.get("at", 0) <= DRAFT_MATCH_WINDOW_S:
        state.pending_draft = {}
        return {"intent": draft.get("intent"), "_draft_text": draft.get("text", ""),
                "_draft_meta": draft}
    auto = state.last_auto or {}
    if auto and now - auto.get("at", 0) <= RESCUE_WINDOW_S:
        state.last_auto = {}
        return {"intent": auto.get("intent"), "rescue": True}
    return {}


# --- automatic demotion --------------------------------------------------------

def note_auto_send(autonomy: dict, intent: str, msg_id: str) -> None:
    """autonomy: {intent: {"recent": [{"id", "rescued"}], "demoted": bool}}"""
    a = autonomy.setdefault(intent, {"recent": [], "demoted": False})
    a["recent"].append({"id": msg_id, "rescued": False})
    del a["recent"][:-DEMOTE_WINDOW]


def note_rescue(autonomy: dict, intent: str) -> bool:
    """Mark the latest auto-send of `intent` as rescued. Returns True if this
    rescue demotes the intent (it wasn't demoted before)."""
    a = autonomy.setdefault(intent, {"recent": [], "demoted": False})
    for r in reversed(a["recent"]):
        if not r["rescued"]:
            r["rescued"] = True
            break
    if not a["demoted"] and sum(r["rescued"] for r in a["recent"]) >= DEMOTE_RESCUES:
        a["demoted"] = True
        return True
    return False


def promote(autonomy: dict, intent: str) -> None:
    """A person puts the intent back on auto; its rescue history starts fresh."""
    autonomy[intent] = {"recent": [], "demoted": False}


def effective_policy(base: dict[str, str], autonomy: dict) -> dict[str, str]:
    """Demoted intents draft instead of auto-sending. Escalations never relax."""
    return {intent: ("draft" if rule in ("auto", "auto_notify")
                     and autonomy.get(intent, {}).get("demoted")
                     else rule)
            for intent, rule in base.items()}


# --- one-tap feedback from the notification email ------------------------------

def _secret() -> bytes:
    return (config.FEEDBACK_SECRET or config.ADMIN_TOKEN).encode()


def feedback_sig(chat_key: str, ts: int, rating: str) -> str:
    return hmac.new(_secret(), f"{chat_key}.{ts}.{rating}".encode(),
                    hashlib.sha256).hexdigest()[:24]


def feedback_links(chat_key: str, ts: int) -> dict[str, str]:
    """{"up": url, "down": url}, or {} when there's no public URL or secret."""
    if not (config.PUBLIC_URL and (config.FEEDBACK_SECRET or config.ADMIN_TOKEN)):
        return {}
    base = config.PUBLIC_URL.rstrip("/")
    return {r: f"{base}/feedback?c={chat_key}&t={ts}&r={r}&s={feedback_sig(chat_key, ts, r)}"
            for r in ("up", "down")}


def feedback_valid(chat_key: str, ts: str, rating: str, sig: str) -> bool:
    if rating not in ("up", "down") or not re.fullmatch(r"[0-9a-f]{16}", chat_key or "") \
            or not (ts or "").isdigit() or not (config.FEEDBACK_SECRET or config.ADMIN_TOKEN):
        return False
    return hmac.compare_digest(feedback_sig(chat_key, int(ts), rating), sig or "")
