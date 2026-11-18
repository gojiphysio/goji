"""
goji-wa-agent: the WhatsApp assistant's webhook service (Cloud Run).

  GET  /webhook                        Meta's subscription handshake
  POST /webhook                        messages, echoes, statuses (Meta-signed)
  POST /webhook/<token>                same, for providers that don't forward
                                       Meta's signature (secret URL instead)
  POST /admin/chats/<wa_id>/takeover   a person takes the chat (agent silent)
  POST /admin/chats/<wa_id>/handback   give the chat back to the agent
  POST /admin/chats/<wa_id>/pause      silence the agent here until handback
  GET  /admin/chats/<wa_id>            chat mode + transcript (Phase 0 testing)
  POST /admin/kill                     {"on": true|false}, all chats
  GET  /healthcheck

The webhook acks at once and works on a background thread (Meta retries slow
acks), so the service runs with CPU always allocated and one warm instance.
One instance also makes the per-chat locks authoritative.

The life of a customer message (handle_inbound):
  1. de-dupe, record, idle hand-back check, append to transcript
  2. gate: kill switch, always-human contacts, chat mode, agent hours
  3. agent.propose -> Proposal (the model never sends)
  4. policy.decide -> send | draft | escalate
  5. send: wait until PRE_SEND_HOLD_S after the message arrived, then re-check
     under the lock that no person replied and no newer customer message came
     (that message's own run answers both). Only then send.
"""
from __future__ import annotations

import hmac
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, request

from . import agent, config, events, notify
from .policy import (AGENT, DRAFT, ESCALATE, HUMAN, PAUSED, SEND, SGT, apply_idle_handback,
                     decide, gate, human_replied_since, is_acknowledgement, on_human_message,
                     reply_problems, set_mode)
from .state import ChatLocks, append_history, make_store, mark_seen
from .whatsapp import Echo, Inbound, Status, WhatsAppClient, parse_webhook, verify_signature

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("wa_agent")

app = Flask(__name__)

_executor = ThreadPoolExecutor(max_workers=8)
locks = ChatLocks()
store = None
wa = None
claude = None


def _deps():
    """Lazy singletons; tests assign the module globals directly."""
    global store, wa, claude
    if store is None:
        store = make_store()
    if wa is None:
        wa = WhatsAppClient()
    if claude is None and config.BACKEND == "api":
        import anthropic
        claude = anthropic.Anthropic()
        if config.KEEP_WARM:
            threading.Thread(target=_keep_warm, daemon=True).start()
    return store, wa, claude


def _keep_warm() -> None:
    """Refresh the prompt cache during the day when no real turn has in the
    last WARM_EVERY_S. One cache read + 1 output token each, well under a cent."""
    from datetime import datetime
    while True:
        try:
            hour = datetime.now(SGT).hour
            idle = time.time() - agent.last_call_at
            if config.WARM_HOURS[0] <= hour < config.WARM_HOURS[1] and idle >= config.WARM_EVERY_S:
                events.record("warm", "", **agent.warm_cache(claude))
        except Exception as e:
            log.warning("cache warm failed: %s", e)
        time.sleep(60)


def _submit(fn, *args):
    _executor.submit(_safe, fn, *args)


def _safe(fn, *args):
    try:
        fn(*args)
    except Exception:
        log.exception("handler %s failed", fn.__name__)


_sleep = time.sleep


def _mode_event(state, old_mode: str, now: float) -> None:
    if state.mode != old_mode:
        events.record("mode", state.wa_id, mode_from=old_mode, mode_to=state.mode,
                      reason=state.mode_reason)


# --- webhook ------------------------------------------------------------------

@app.get("/webhook")
def verify():
    if (request.args.get("hub.mode") == "subscribe" and config.WA_VERIFY_TOKEN
            and request.args.get("hub.verify_token") == config.WA_VERIFY_TOKEN):
        return request.args.get("hub.challenge", ""), 200
    return "forbidden", 403


@app.post("/webhook")
def webhook():
    if not verify_signature(request.get_data(), request.headers.get("X-Hub-Signature-256"),
                            config.WA_APP_SECRET):
        return "bad signature", 403
    return _dispatch()


@app.post("/webhook/<token>")
def webhook_with_url_token(token: str):
    """For providers that don't pass Meta's signature through."""
    if not (config.WA_WEBHOOK_URL_TOKEN
            and hmac.compare_digest(token, config.WA_WEBHOOK_URL_TOKEN)):
        return "forbidden", 403
    return _dispatch()


def _dispatch():
    received = time.time()
    for ev in parse_webhook(request.get_json(silent=True) or {}):
        if isinstance(ev, Inbound):
            _submit(handle_inbound, ev, received)
        elif isinstance(ev, Echo):
            _submit(handle_echo, ev)
        elif isinstance(ev, Status):
            events.record("status", ev.wa_id, wa_msg_id=ev.msg_id, status=ev.status,
                          status_ts=ev.ts)
    return "ok", 200


def handle_echo(ev: Echo) -> None:
    """A person wrote from the WhatsApp Business app: they have the chat now."""
    st, _, _ = _deps()
    with locks(ev.wa_id):
        state = st.load(ev.wa_id)
        if not mark_seen(state, ev.msg_id):
            return
        old = state.mode
        on_human_message(state, time.time())
        append_history(state, "staff", ev.text, ev.ts, ev.msg_id)
        st.save(state)
    events.record("echo", ev.wa_id, echo_lag_s=round(time.time() - ev.ts, 1))
    _mode_event(state, old, time.time())


def handle_inbound(ev: Inbound, received: float) -> None:
    st, client, model = _deps()
    now = time.time()
    with locks(ev.wa_id):
        state = st.load(ev.wa_id)
        if not mark_seen(state, ev.msg_id):
            return
        old = state.mode
        apply_idle_handback(state, now)
        append_history(state, "customer", ev.text, ev.ts, ev.msg_id)
        st.save(state)
        history = list(state.history)
    _mode_event(state, old, now)
    events.record("inbound", ev.wa_id, kind=ev.kind, webhook_lag_s=round(received - ev.ts, 1))

    blocked = gate(state, now, kill_switch=config.KILL_SWITCH or st.get_kill())
    if blocked:
        events.record("silent", ev.wa_id, reason=blocked.reason)
        return
    if is_acknowledgement(ev.text, history):
        events.record("silent", ev.wa_id, reason="acknowledgement")
        return

    # Debounce: let the customer finish typing. If they send more, that
    # message's run answers everything; this one stops before the model.
    if config.DEBOUNCE_S > 0:
        _sleep(config.DEBOUNCE_S)
        with locks(ev.wa_id):
            state = st.load(ev.wa_id)
            history = list(state.history)
        latest = next((h["id"] for h in reversed(history) if h["role"] == "customer"), "")
        if latest != ev.msg_id:
            events.record("superseded", ev.wa_id, reason="debounced")
            return
        blocked = gate(state, time.time(), kill_switch=config.KILL_SWITCH or st.get_kill())
        if blocked:
            events.record("silent", ev.wa_id, reason=blocked.reason)
            return

    client.mark_read_typing(ev.msg_id)
    res = agent.propose(history, wa_id=ev.wa_id, now=now, customer_name=ev.name,
                        client=model)
    p = res.proposal
    d = decide(p)
    events.record("proposal", ev.wa_id, intent=p.intent, confidence=p.confidence,
                  escalate=p.escalate, decision=d.action, reason=d.reason,
                  agent_ms=res.total_ms, steps=[s.__dict__ for s in res.steps],
                  tools=",".join(res.tools_used), model=res.model_served, stop=res.stop,
                  input_tokens=res.input_tokens, output_tokens=res.output_tokens,
                  cache_read_tokens=res.cache_read_tokens,
                  cache_write_tokens=res.cache_write_tokens, cost_usd=round(res.cost_usd, 5))

    notice = dict(customer=ev.name, wa_id=ev.wa_id, staff_note=p.staff_note,
                  suggested_reply=p.reply, reason=d.reason, last_message=ev.text)

    if d.action == DRAFT:
        notify.send("drafted", **notice)
        events.record("drafted", ev.wa_id, reason=d.reason)
        return

    if d.action == SEND:
        wait = config.PRE_SEND_HOLD_S - (time.time() - received)
        if wait > 0:
            _sleep(wait)

    with locks(ev.wa_id):
        state = st.load(ev.wa_id)
        latest = next((h["id"] for h in reversed(state.history) if h["role"] == "customer"), "")
        if human_replied_since(state, received):
            events.record("superseded", ev.wa_id, reason="human_replied")
            return
        if latest and latest != ev.msg_id:
            events.record("superseded", ev.wa_id, reason="newer_customer_message")
            return
        if config.KILL_SWITCH or st.get_kill():
            events.record("silent", ev.wa_id, reason="kill_switch")
            return
        reply = p.reply.strip()
        if not reply or reply_problems(reply):  # escalations skip decide()'s content check
            reply = agent._escalation("unsafe_or_empty").reply
        try:
            wa_msg_id = client.send_text(ev.wa_id, reply)
        except Exception as e:
            log.warning("send failed: %s", e)
            events.record("send_failed", ev.wa_id, reason=type(e).__name__)
            notify.send("escalated", **{**notice, "reason": f"send failed: {e}"})
            return
        sent_at = time.time()
        append_history(state, "agent", reply, sent_at, wa_msg_id)
        old = state.mode
        if d.action == ESCALATE:
            set_mode(state, HUMAN, f"escalated:{d.reason}", sent_at)
        st.save(state)

    events.record("sent" if d.action == SEND else "escalated", ev.wa_id, wa_msg_id=wa_msg_id,
                  intent=p.intent, reason=d.reason,
                  e2e_ms=int((sent_at - received) * 1000))
    _mode_event(state, old, sent_at)
    if d.action == ESCALATE:
        notify.send("urgent" if p.intent == "urgent" else "escalated", **notice)


# --- admin (Phase 0: token; Phase 1: front-desk portal auth) -------------------

def _authorised() -> bool:
    return bool(config.ADMIN_TOKEN) and request.headers.get("X-Admin-Token") == config.ADMIN_TOKEN


def _set_chat_mode(wa_id: str, mode: str, reason: str):
    if not _authorised():
        return jsonify({"error": "forbidden"}), 403
    st, _, _ = _deps()
    with locks(wa_id):
        state = st.load(wa_id)
        old = state.mode
        set_mode(state, mode, reason, time.time())
        st.save(state)
    _mode_event(state, old, time.time())
    return jsonify({"wa_id": wa_id, "mode": state.mode})


@app.post("/admin/chats/<wa_id>/takeover")
def takeover(wa_id: str):
    return _set_chat_mode(wa_id, HUMAN, "admin_takeover")


@app.post("/admin/chats/<wa_id>/handback")
def handback(wa_id: str):
    return _set_chat_mode(wa_id, AGENT, "admin_handback")


@app.post("/admin/chats/<wa_id>/pause")
def pause(wa_id: str):
    return _set_chat_mode(wa_id, PAUSED, "admin_pause")


@app.get("/admin/chats/<wa_id>")
def chat(wa_id: str):
    if not _authorised():
        return jsonify({"error": "forbidden"}), 403
    st, _, _ = _deps()
    return jsonify(st.load(wa_id).to_dict())


@app.post("/admin/kill")
def kill():
    if not _authorised():
        return jsonify({"error": "forbidden"}), 403
    on = bool((request.get_json(silent=True) or {}).get("on"))
    st, _, _ = _deps()
    st.set_kill(on)
    events.record("kill_switch", "", kill_on=on)
    return jsonify({"kill_switch": on})


@app.get("/healthcheck")
def healthcheck():
    return jsonify({"ok": True})
