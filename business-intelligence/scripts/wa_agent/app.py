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
  GET  /admin/autonomy                 per-intent auto-send record, demotions
  POST /admin/autonomy/<intent>/promote  put a demoted intent back on auto
  GET  /feedback                       one-tap rating from a staff email (signed)
  POST /internal/booking-confirmed     goji-booking: a booking was made (token)
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
from datetime import datetime
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, request

from . import agent, booking_client, config, documents, events, learning, notify, tools
from .policy import (AGENT, DRAFT, ESCALATE, HUMAN, LATE_CHANGE_H, PAUSED, SEND, SGT, WAITING,
                     apply_idle_handback, handover_mode,
                     decide, gate, human_replied_since, is_acknowledgement, on_human_message,
                     reply_problems, set_mode)
from .state import ChatLocks, append_history, make_store, mark_seen
from .whatsapp import Echo, Inbound, Status, WhatsAppClient, parse_webhook, verify_signature

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("wa_agent")

app = Flask(__name__)

_executor = ThreadPoolExecutor(max_workers=8)
locks = ChatLocks()
_autonomy_lock = threading.Lock()
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
        now = time.time()
        if old == AGENT:
            signal = learning.classify_echo(state, now)
        else:  # a planned handover or admin takeover: Chris was meant to reply
            signal, state.pending_draft, state.last_auto = {}, {}, {}
        on_human_message(state, now)
        append_history(state, "staff", ev.text, ev.ts, ev.msg_id)
        st.save(state)
    draft_text = signal.pop("_draft_text", None)
    if draft_text is not None:
        signal["draft_similarity"], signal["draft_outcome"] = \
            learning.draft_outcome(draft_text, ev.text)
    events.record("echo", ev.wa_id, echo_lag_s=round(time.time() - ev.ts, 1), **signal)
    _mode_event(state, old, time.time())
    if signal.get("rescue") and signal.get("intent"):
        _note_rescue(st, signal["intent"], ev.wa_id)


def _note_rescue(st, intent: str, wa_id: str) -> None:
    with _autonomy_lock:
        autonomy = st.get_autonomy()
        demoted = learning.note_rescue(autonomy, intent)
        st.save_autonomy(autonomy)
    if demoted:
        reason = f"demoted:{learning.DEMOTE_RESCUES}_rescues_in_last_{learning.DEMOTE_WINDOW}"
        events.record("autonomy", wa_id, intent=intent, reason=reason)
        notify.send("demoted", customer="", wa_id=wa_id,
                    staff_note=f"'{intent}' messages now come to you as drafts instead of "
                               f"being sent automatically, because you stepped in "
                               f"{learning.DEMOTE_RESCUES} times recently.",
                    suggested_reply="", reason=reason, last_message="")


def _test_show(client, wa_id: str, text: str) -> None:
    """Local battle-testing: show the tester what would otherwise only reach
    staff. Never on a deployed service, never stored in the transcript."""
    if config.TEST_SHOW_DRAFTS and config.STATE_BACKEND == "memory":
        try:
            client.send_text(wa_id, "🧪 TEST MODE (customers never see this)\n\n" + text)
        except Exception as e:
            log.warning("test-mode send failed: %s", e)


def _book_pending(state, ev: Inbound, received: float, fallback: str) -> tuple[str, dict | None]:
    """The customer confirmed: book what was stated back to them, if it was
    stated in an earlier message and recently. The model can't book on its
    own say-so in the same turn. Returns (reply, booking or None)."""
    pending = state.pending_booking or {}
    if not pending or pending.get("at", 0) >= received \
            or received - pending.get("at", 0) > config.BOOKING_CONFIRM_WINDOW_S:
        events.record("book_skipped", ev.wa_id, reason="no_pending_booking")
        return fallback, None
    try:
        res = booking_client.book(pending, wa_id=ev.wa_id)
    except booking_client.BookingFailed as e:
        state.pending_booking = {}
        events.record("book_failed", ev.wa_id, reason=e.code)
        notify.send("escalated", customer=ev.name, wa_id=ev.wa_id,
                    staff_note=f"Booking failed ({e.code}): {pending.get('service')} "
                               f"{pending.get('date')} {pending.get('time')}",
                    suggested_reply="", reason=f"booking failed: {e}", last_message=ev.text)
        if e.code == "slot_taken":
            return ("Sorry, that time was just taken! Would you like me to find the next "
                    "open one?"), None
        return ("Sorry, I couldn't complete the booking just now. I've let the team "
                "know and they'll sort it out with you shortly."), None
    events.record("booked", ev.wa_id, intent="booking",
                  reason="dry_run" if res.get("dry_run") else "agent")
    first = (pending.get("full_name") or "").split(" ")[0]
    return (booking_client.confirmation_text(res, first_name=first),
            {"reference": res["reference"], "date": res["date"], "time": res["time"],
             "with": res.get("clinician_name", ""), "service": res.get("service", ""),
             "dry_run": bool(res.get("dry_run")), "at": time.time(), "source": "whatsapp"})


def _read_document(client, ev: Inbound) -> str:
    try:
        data, mime = client.download_media(ev.media_id)
    except Exception as e:
        log.warning("document download failed: %s", e)
        return ""
    return documents.extract_text(data, mime or ev.mime, ev.filename)


PATIENT_CACHE_S = 6 * 3600


def _booked_note(state) -> str:
    b = state.booked or {}
    if not b or time.time() - b.get("at", 0) > 14 * 86400:
        return ""
    return (f"just booked ({b.get('source')}): {b.get('service')} {b.get('date')} "
            f"{b.get('time')} with {b.get('with') or 'the team'}, ref {b.get('reference')}"
            f"{' (test dry run)' if b.get('dry_run') else ''}; don't offer times for it again")


def _late_change_note(changes: list[dict]) -> str:
    """Earlier late changes from this number (tracked since go-live), so the
    agent only offers the first-time fee waiver once."""
    if not changes:
        return "no earlier late changes on record (first-time waiver applies)"
    last = datetime.fromtimestamp(max(c["at"] for c in changes), SGT)
    return (f"{len(changes)} earlier late change(s) on record, last {last:%d %b %Y} "
            "(first-time waiver already used)")


def _patient_for(st, wa_id: str, state) -> dict:
    """Who this number is (returning-patient recognition), looked up in code by
    the chat's own number and cached on the chat for a few hours."""
    if state.patient_at and time.time() - state.patient_at < PATIENT_CACHE_S:
        return state.patient
    patient = tools.patient_context(wa_id)
    if patient:
        with locks(wa_id):
            fresh = st.load(wa_id)
            fresh.patient, fresh.patient_at = patient, time.time()
            st.save(fresh)
        events.record("patient_lookup", wa_id, reason="returning" if patient.get("returning")
                      else "no_record")
    return patient


def handle_inbound(ev: Inbound, received: float) -> None:
    st, client, model = _deps()
    now = time.time()
    if ev.kind == "document" and ev.media_id:
        ev.text = documents.as_message(_read_document(client, ev), ev.filename, ev.caption)
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
    patient = _patient_for(st, ev.wa_id, state)
    key = events.chat_key(ev.wa_id)
    res = agent.propose(history, wa_id=ev.wa_id, now=now, customer_name=ev.name,
                        client=model,
                        pending_for_chris=state.pending_for_chris if state.mode == WAITING else "",
                        patient="; ".join(filter(None, [
                            tools.describe_patient(patient),
                            _late_change_note(st.get_late_changes(key)),
                            _booked_note(state)])))
    p = res.proposal
    d = decide(p, intent_policy=learning.effective_policy(config.INTENT_POLICY,
                                                          st.get_autonomy()))
    events.record("proposal", ev.wa_id, intent=p.intent, confidence=p.confidence,
                  escalate=p.escalate, decision=d.action, reason=d.reason,
                  agent_ms=res.total_ms, steps=[s.__dict__ for s in res.steps],
                  tools=",".join(res.tools_used), model=res.model_served, stop=res.stop,
                  input_tokens=res.input_tokens, output_tokens=res.output_tokens,
                  cache_read_tokens=res.cache_read_tokens,
                  cache_write_tokens=res.cache_write_tokens, cost_usd=round(res.cost_usd, 5))

    if p.intent in ("reschedule", "cancel") and 0 <= p.hours_to_appointment < LATE_CHANGE_H:
        st.add_late_change(key, {"at": round(time.time()), "kind": p.intent,
                                 "hours": round(p.hours_to_appointment, 1)})
        events.record("late_change", ev.wa_id, intent=p.intent,
                      reason=f"hours:{p.hours_to_appointment:.0f}")

    notice = dict(customer=ev.name, wa_id=ev.wa_id, staff_note=p.staff_note,
                  suggested_reply=p.reply, reason=d.reason, last_message=ev.text,
                  feedback=learning.feedback_links(events.chat_key(ev.wa_id), int(now)))

    if ev.kind in ("image", "document"):
        # The file itself is for the team: Chris opens it in the app.
        notify.send("media", **{**notice, "last_message": ev.text[:1500]})

    if d.action == DRAFT:
        with locks(ev.wa_id):
            state = st.load(ev.wa_id)
            state.pending_draft = {"text": p.reply, "intent": p.intent, "at": time.time()}
            state.last_auto = {}
            st.save(state)
        notify.send("drafted", **notice)
        events.record("drafted", ev.wa_id, intent=p.intent, reason=d.reason)
        _test_show(client, ev.wa_id,
                   f"Not sent. Chris gets this draft to check ({d.reason}):\n\n{p.reply}")
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
        booked = None
        if d.action == SEND and p.confirm_booking:
            reply, booked = _book_pending(state, ev, received, reply)
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
            # Most handovers wait for Chris while the agent keeps answering
            # routine questions; red flags and sensitive topics go fully quiet.
            mode = handover_mode(p.intent)
            if mode == WAITING and state.mode == WAITING:
                state.pending_for_chris = f"{state.pending_for_chris}; {p.staff_note}"[:600]
            else:
                state.pending_for_chris = p.staff_note[:600] if mode == WAITING else ""
                set_mode(state, mode, f"escalated:{d.reason}", sent_at)
            state.last_auto = {}
        else:
            state.last_auto = {"intent": p.intent, "at": sent_at}
        state.pending_draft = {}
        if booked:
            state.booked, state.pending_booking = booked, {}
        elif d.action == SEND and not p.confirm_booking and booking_client.complete(p.booking):
            # Stated back to the customer; only their next message can confirm it.
            state.pending_booking = {**{k: p.booking.get(k, "") for k in booking_client.FIELDS},
                                     "at": sent_at}
        st.save(state)
    if d.action == SEND:
        with _autonomy_lock:
            autonomy = st.get_autonomy()
            learning.note_auto_send(autonomy, p.intent, wa_msg_id)
            st.save_autonomy(autonomy)

    events.record("sent" if d.action == SEND else "escalated", ev.wa_id, wa_msg_id=wa_msg_id,
                  intent=p.intent, reason=d.reason,
                  e2e_ms=int((sent_at - received) * 1000))
    _mode_event(state, old, sent_at)
    if d.action == SEND and config.INTENT_POLICY.get(p.intent) == "auto_notify":
        kind = "reschedule" if p.intent == "reschedule" else "fyi"
        notify.send(kind, **notice)
        _test_show(client, ev.wa_id, f"Chris would get an email ({kind}): {p.staff_note}")
    if d.action == ESCALATE:
        notify.send(p.intent if p.intent in ("urgent", "sensitive") else "escalated", **notice)
        _test_show(client, ev.wa_id, f"Handed to Chris ({d.reason}). She'd get an email "
                                     f"saying: {p.staff_note}")


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


@app.get("/admin/autonomy")
def autonomy_state():
    if not _authorised():
        return jsonify({"error": "forbidden"}), 403
    st, _, _ = _deps()
    return jsonify(st.get_autonomy())


@app.post("/admin/autonomy/<intent>/promote")
def promote_intent(intent: str):
    if not _authorised():
        return jsonify({"error": "forbidden"}), 403
    st, _, _ = _deps()
    with _autonomy_lock:
        autonomy = st.get_autonomy()
        learning.promote(autonomy, intent)
        st.save_autonomy(autonomy)
    events.record("autonomy", "", intent=intent, reason="promoted:admin")
    return jsonify({"intent": intent, "demoted": False})


@app.post("/internal/booking-confirmed")
def booking_confirmed():
    """goji-booking calls this after a real booking (website or this agent).
    If the booking's phone number has a chat here, note it on the chat and,
    for a website booking inside the 24-hour window, acknowledge it there."""
    if not (config.INTERNAL_TOKEN and hmac.compare_digest(
            request.headers.get("X-Internal-Token", ""), config.INTERNAL_TOKEN)):
        return "forbidden", 403
    b = request.get_json(silent=True) or {}
    digits = "".join(ch for ch in str(b.get("phone", "")) if ch.isdigit())
    if len(digits) < 8:
        return jsonify({"matched": False})
    wa_id = digits if len(digits) > 8 else "65" + digits
    st, client, _ = _deps()
    with locks(wa_id):
        state = st.load(wa_id)
        if not state.history:
            return jsonify({"matched": False})
        state.booked = {"reference": b.get("reference", ""), "date": b.get("date", ""),
                        "time": b.get("time", ""), "with": b.get("clinician_name", ""),
                        "service": b.get("service", ""), "dry_run": False,
                        "at": time.time(), "source": b.get("source", "web")}
        state.pending_booking = {}
        last_customer = max((h["ts"] for h in state.history if h["role"] == "customer"),
                            default=0)
        acked = False
        if (b.get("source") != "whatsapp" and state.mode in (AGENT, WAITING)
                and time.time() - last_customer < 23 * 3600 and b.get("date") and b.get("time")):
            text = booking_client.confirmation_text(
                {**b, "dry_run": False}, first_name="").replace(
                "You're booked!", "Thanks for booking! You're all set for", 1)
            try:
                msg_id = client.send_text(wa_id, text)
                append_history(state, "agent", text, time.time(), msg_id)
                acked = True
            except Exception as e:
                log.warning("booking acknowledgement failed: %s", e)
        st.save(state)
    events.record("booked", wa_id, intent="booking", reason=f"{b.get('source', 'web')}"
                  f"{':acknowledged' if acked else ''}")
    return jsonify({"matched": True, "acknowledged": acked})


@app.get("/feedback")
def feedback():
    """PUBLIC: the 👍/👎 link in a staff email. Signed, so it can only rate the
    conversation the email was about; repeat taps just add another row."""
    a = request.args
    if not learning.feedback_valid(a.get("c", ""), a.get("t", ""), a.get("r", ""), a.get("s", "")):
        return "This link isn't valid.", 403
    events.record("feedback", "", key=a["c"], rating=a["r"])
    msg = "Thanks, noted." if a["r"] == "up" else "Thanks. We'll look at what went wrong."
    return f"<!doctype html><meta name=viewport content='width=device-width'>" \
           f"<p style='font:18px system-ui;margin:2em'>{msg}</p>", 200


@app.get("/healthcheck")
def healthcheck():
    return jsonify({"ok": True})
