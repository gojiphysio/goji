"""
goji-wa-agent: the WhatsApp assistant's webhook service (Cloud Run).

  GET  /webhook                        Meta's subscription handshake
  POST /webhook                        messages, echoes, statuses (Meta-signed)
  POST /webhook/<token>                same, for providers that don't forward
                                       Meta's signature (secret URL instead)
  POST /admin/chats/<wa_id>/takeover   a person takes the chat (agent silent)
  POST /admin/chats/<wa_id>/handback   give the chat back to the agent
  POST /admin/chats/<wa_id>/pause      silence the agent here until handback
  POST /admin/chats/<wa_id>/forget     PDPA deletion: drop the chat doc and late changes
  GET  /admin/chats/<wa_id>            chat mode + transcript (Phase 0 testing)
  POST /admin/kill                     {"on": true|false}, all chats
  GET  /admin/rollout                  stage, contact scope, hours (Firestore, env default)
  POST /admin/rollout                  {"stage": 0-3, "contact_scope", "hours"}; null = env
  POST /admin/history-imported         {"on": true|false}: coexistence history is in
  POST /admin/go-live                  {"at": epoch | omitted = now | null = not live}
  GET  /admin/autonomy                 per-intent auto-send record, demotions
  POST /admin/autonomy/<intent>/promote  put a demoted intent back on auto
  GET  /feedback                       one-tap rating from a staff email (signed)
  POST /internal/booking-confirmed     goji-booking: a booking was made (token)
  POST /internal/morning-summary       daily email + staff one-liner (admin token)
  GET  /healthcheck

The webhook acks at once (Meta retries slow acks). Deployed, it queues each
event on Cloud Tasks and the work runs inside POST /tasks/run, so the service
scales to zero and is billed only while working (tasks.py); locally, without a
queue, it works on a background thread. One instance (--max-instances=1)
makes the per-chat locks authoritative.

The life of a customer message (handle_inbound):
  0. a staff number (WA_AGENT_STAFF) goes to handle_staff instead: commands, never a customer
  1. de-dupe, record, idle hand-back check, append to transcript, and the gate
     under the same lock: kill switch, always-human contacts, chat mode (Chris
     writing pauses a chat until she resumes it), not live yet, the go-live
     cut-off, agent hours, contact scope. A pass claims the chat for the agent
     (owner="agent"), so the rest of a burst passes too.
  3. agent.propose -> Proposal (the model never sends)
  4. policy.decide (stage preset + demotion) -> send | draft | escalate | silent
  5. send: wait until PRE_SEND_HOLD_S after the message arrived, then re-check
     under the lock that no person replied and no newer customer message came
     (that message's own run answers both). Only then send.
"""
from __future__ import annotations

import hmac
import json
from datetime import datetime
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, request

from . import (agent, booking_client, config, documents, events, learning, notify, staff,
               summary, tasks, tools)
from .policy import (AGENT, DRAFT, ESCALATE, HUMAN, LATE_CHANGE_H, OFF_TOPIC, PAUSED, SEND,
                     SGT, SILENT, WAITING, WATCHLIST, as_one_message, split_bubbles,
                     apply_idle_handback, apply_pause_expiry, apply_stage, handover_mode,
                     check_late_change, customer_message, customer_window_open, has_record,
                     note_off_topic,
                     out_of_scope,
                     pre_golive_chat,
                     decide, gate, human_replied_since, is_acknowledgement, on_human_message,
                     mask_customer_emails, reply_problems, set_mode)
from .state import ChatLocks, append_history, make_store, mark_seen, note_outcome, parse_code
from .whatsapp import (Echo, HistoryChunk, Inbound, Status, WhatsAppClient, parse_webhook,
                       verify_signature)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("wa_agent")

app = Flask(__name__)
events.check_salt()  # a deployed run without WA_AGENT_HASH_SALT logs loudly here

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
        if config.KEEP_WARM and not tasks.enabled():  # with a queue, warms are tasks
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
        return request.args.get("hub.challenge", ""), 200, {"Content-Type": "text/plain"}
    return "forbidden", 403


def _url_token_ok(token: str) -> bool:
    return bool(config.WA_WEBHOOK_URL_TOKEN
                and hmac.compare_digest(token, config.WA_WEBHOOK_URL_TOKEN))


@app.get("/webhook/<token>")
def verify_with_url_token(token: str):
    """The handshake on the secret-link URL (a provider such as Dualhook,
    whose webhooks Meta signs with the provider's app secret, not ours)."""
    if not _url_token_ok(token):
        return "forbidden", 403
    return verify()


@app.post("/webhook")
def webhook():
    if not verify_signature(request.get_data(), request.headers.get("X-Hub-Signature-256"),
                            config.WA_APP_SECRET):
        return "bad signature", 403
    return _dispatch()


@app.post("/webhook/<token>")
def webhook_with_url_token(token: str):
    """For providers that don't pass Meta's signature through."""
    if not _url_token_ok(token):
        return "forbidden", 403
    return _dispatch()


_HANDLERS = {"inbound": Inbound, "echo": Echo, "history": HistoryChunk}


def _run_event(kind: str, ev, received: float) -> None:
    if kind == "inbound":
        handle_inbound(ev, received)
    elif kind == "echo":
        handle_echo(ev)
    elif kind == "history":
        handle_history(ev)


def _queue_or_submit(kind: str, ev, received: float) -> None:
    """With a queue: Cloud Tasks calls /tasks/run, where the work runs inside
    a request (the service can scale to zero). Without one, or if queueing
    fails: a background thread on this instance."""
    if tasks.enabled():
        try:
            if tasks.enqueue(tasks.encode(kind, ev, received=received)):
                return
        except Exception as e:
            log.error("enqueue %s failed, running here: %s", kind, e)
    _submit(_run_event, kind, ev, received)


def _dispatch():
    received = time.time()
    for ev in parse_webhook(request.get_json(silent=True) or {}):
        kind = next((k for k, cls in _HANDLERS.items() if isinstance(ev, cls)), "")
        if kind:
            _queue_or_submit(kind, ev, received)
        elif isinstance(ev, Status):
            events.record("status", ev.wa_id, wa_msg_id=ev.msg_id, status=ev.status,
                          status_ts=ev.ts)
    return "ok", 200


@app.post("/tasks/run")
def run_task():
    """Cloud Tasks delivers a queued event (or a cache warm) here. Always 200:
    a retry could only repeat work the de-dupe would skip anyway."""
    body = request.get_data()
    if not tasks.valid(body, request.headers.get(tasks.SIGNATURE_HEADER, "")):
        return "forbidden", 403
    t = json.loads(body or b"{}")
    kind = t.get("kind", "")
    if kind == "warm":
        _safe(_warm_task)
    elif kind in _HANDLERS:
        _safe(_run_event, kind, _HANDLERS[kind](**t.get("event", {})),
              float(t.get("received") or time.time()))
    return "ok", 200


def _schedule_warm() -> None:
    """Keep the prompt cache warm through the day without an always-on
    instance: a named task one WARM_EVERY_S slot ahead (names de-duplicate)."""
    if not (tasks.enabled() and config.BACKEND == "api" and config.KEEP_WARM):
        return
    from datetime import datetime
    later = time.time() + config.WARM_EVERY_S
    if not config.WARM_HOURS[0] <= datetime.fromtimestamp(later, SGT).hour < config.WARM_HOURS[1]:
        return
    try:
        tasks.enqueue(tasks.encode("warm"), delay_s=config.WARM_EVERY_S,
                      name=tasks.warm_name(time.time()))
    except Exception as e:
        log.warning("warm scheduling failed: %s", e)


def _warm_task() -> None:
    _, _, model = _deps()
    if model is not None and time.time() - agent.last_call_at >= config.WARM_EVERY_S - 60:
        events.record("warm", "", **agent.warm_cache(model))
    _schedule_warm()


def handle_echo(ev: Echo) -> None:
    """A person wrote from the WhatsApp Business app: the chat pauses, and the
    agent stays out of it until they resume it ("resume 004"), or until the
    customer writes 14 days after the person's last message."""
    if ev.wa_id in config.STAFF:
        return  # the business number writing to a staff phone: not a customer chat
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
        state.code = state.code or st.next_code()
        state.last_staff_at = max(state.last_staff_at, ev.ts or now)
        append_history(state, "staff", ev.text, ev.ts, ev.msg_id)
        st.save(state)
    meta = signal.pop("_draft_meta", {}) or {}
    draft_text = signal.pop("_draft_text", None)
    if draft_text is not None:
        signal["draft_similarity"], signal["draft_outcome"] = \
            learning.draft_outcome(draft_text, ev.text)
    events.record("echo", ev.wa_id, echo_lag_s=round(time.time() - ev.ts, 1), **signal)
    if meta.get("waives_fee") and signal.get("draft_outcome") == "sent_unchanged":
        _submit(_tag_waiver_used, st, ev.wa_id, state.patient)
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
        _alert("demoted", customer="", wa_id=wa_id, who="",
                    staff_note=f"'{intent}' messages now come to you as drafts instead of "
                               f"being sent automatically, because you stepped in "
                               f"{learning.DEMOTE_RESCUES} times recently.",
                    suggested_reply="", reason=reason, last_message="")


def _ping_staff(who: str, note: str, wa_id: str = "") -> bool:
    """A short WhatsApp to each staff number (WA_AGENT_STAFF): free-form inside
    their 24h window, else the approved template. True if any ping went out.
    Never a customer's full number (staff.label / staff.redact). With the
    chat's `wa_id`, each ping's message id is kept so a swipe-reply to it
    finds the chat (_staff_answer)."""
    if not config.STAFF:
        return False
    st, client, _ = _deps()
    windows, now, ok = st.get_staff_windows(), time.time(), False
    for number in sorted(config.STAFF):
        try:
            if staff.window_open(windows.get(number, 0.0), now):
                ping_id = client.send_text(number, staff.ping_text(who, note))
                how = "text"
            else:
                ping_id = client.send_template(number, config.STAFF_TEMPLATE,
                                               staff.template_params(who, note))
                how = "template"
            ok = True
            if wa_id:
                try:
                    st.note_ping(ping_id, wa_id)
                except Exception as e:  # the ping went out; only swipe-reply is lost
                    log.warning("ping id not kept: %s", e)
            events.record("staff_ping", "", reason=how)
        except Exception as e:
            log.warning("staff ping failed: %s", e)
            events.record("staff_ping_failed", "", reason=type(e).__name__)
    return ok


def _alert(kind: str, *, customer: str, wa_id: str, who: str | None = None, **kw) -> None:
    """A chat needs a person. Staff are pinged on WhatsApp first; email stays
    the backup for red flags and sensitive topics, and the only channel when
    no staff number is set or every ping failed."""
    if who is None:
        st, _, _ = _deps()
        who = staff.label(customer, wa_id, st.load(wa_id).code if wa_id else "")
    # A ping about a chat (named) can be answered by swipe-reply; one that
    # isn't (a demotion notice, who="") must never route an answer to a customer.
    pinged = _ping_staff(who, kw.get("staff_note") or kw.get("reason") or "",
                         wa_id if who else "")
    if kind in ("urgent", "sensitive", "priority") or not pinged:
        notify.send(kind, customer=customer, wa_id=wa_id, **kw)


def _sgt_day_start(now: float) -> float:
    from datetime import datetime
    return datetime.fromtimestamp(now, SGT).replace(hour=0, minute=0, second=0,
                                                    microsecond=0).timestamp()


def handle_staff(ev: Inbound) -> None:
    """A staff number wrote to the business number: never a customer (no
    lookup or metrics for them). Opens their 24h window; stop / start /
    status work even with the kill switch on. The model runs only for the
    team's answer, on the chat it's for (_staff_answer)."""
    st, client, model = _deps()
    now = time.time()
    with locks(ev.wa_id):
        state = st.load(ev.wa_id)  # only for webhook de-dupe
        if not mark_seen(state, ev.msg_id):
            return
        st.save(state)
    st.note_staff_inbound(ev.wa_id, ev.ts or now)
    cmd, code = staff.parse_command(ev.text)
    answer = staff.parse_answer(ev.text)
    pinged_chat = st.ping_chat(ev.reply_to) if ev.reply_to else ""
    if answer is not None:  # "answer 004 ...": the code wins over a quoted ping
        wa_id = st.find_by_code(answer[0])
        reply = (_staff_answer(st, client, model, wa_id, answer[1]) if wa_id else
                 f"I can't find chat #{answer[0]}. The number is in the ping or the morning summary.")
    elif pinged_chat and staff.bare_command(ev.text) in ("resume", "pause"):
        reply = _staff_resume_pause(st, staff.bare_command(ev.text), "", now,
                                    wa_id=pinged_chat)
    elif pinged_chat and not staff.bare_command(ev.text):
        # A swipe-reply to a ping: whatever she wrote is the team's answer.
        reply = _staff_answer(st, client, model, pinged_chat, ev.text or "")
    elif not st.staff_welcomed(ev.wa_id) and cmd == "help":
        # Their first message: the walkthrough is the first thing they get from us.
        st.mark_staff_welcomed(ev.wa_id)
        reply = staff.WELCOME
    elif cmd in ("resume", "pause"):
        reply = _staff_resume_pause(st, cmd, code, now)
    elif cmd in ("stop", "start"):
        st.set_kill(cmd == "stop")
        events.record("kill_switch", "", kill_on=cmd == "stop", reason="staff")
        reply = ("Goji assistant stopped in every chat. Text START to turn it back on."
                 if cmd == "stop" else "Goji assistant is back on.")
        if cmd == "start" and config.KILL_SWITCH:
            reply = "The assistant is switched off in its settings (WA_AGENT_KILL), so START can't turn it on. Ask Charles."
    elif cmd == "status":
        day = _sgt_day_start(now)
        chats = [c for c in st.recent_chats(day) if c.wa_id not in config.STAFF]
        paused = [c for c in st.paused_chats() if c.wa_id not in config.STAFF
                  and c.mode_reason != WATCHLIST]  # the watch list is in the summary
        reply = staff.status_text(kill=config.KILL_SWITCH or st.get_kill(),
                                  rollout=config.resolve_rollout(st.get_rollout()),
                                  waiting=summary.waiting_for_chris(chats, day),
                                  paused=summary.paused_labels(paused),
                                  live=not _not_live(st))
    else:
        reply = staff.HELP
    try:
        client.send_text(ev.wa_id, reply)
    except Exception as e:
        log.warning("staff reply failed: %s", e)


def _staff_resume_pause(st, cmd: str, code: str, now: float, wa_id: str = "") -> str:
    """"resume 004": the agent watches chat #004 again from the customer's next
    message (nothing is sent to them). "pause 004": it stays out of it. A
    bare "resume" swipe-replied to a ping passes that ping's chat as `wa_id`."""
    wa_id = wa_id or (st.find_by_code(code) if code else "")
    if not wa_id:
        return f"I can't find chat #{code}. The number is in the ping or the morning summary."
    with locks(wa_id):
        state = st.load(wa_id)
        old = state.mode
        if cmd == "resume":
            set_mode(state, AGENT, "staff_resumed", now)
            state.owner = "agent"
            state.off_topic_strikes = 0
            state.pending_for_chris, state.pending_draft, state.last_auto = "", {}, {}
        else:
            set_mode(state, PAUSED, "staff_paused", now)
            state.owner = ""
        st.save(state)
    _mode_event(state, old, now)
    who = staff.label(state.name, wa_id, state.code)
    if cmd == "resume":
        return (f"OK, I'm looking after {who} again. I won't message them now; I'll answer "
                f"their next message.")
    return f"OK, I'll stay out of {who} until you text RESUME {state.code}."


def _staff_answer(st, client, model, wa_id: str, answer: str) -> str:
    """The team's answer for chat `wa_id` (Chris's swipe-reply to a ping, or
    "answer 004 ..."): the agent writes it up in its own voice, sends it, and
    takes the chat back, so Chris doesn't type it out and then RESUME (owner,
    24 Nov 2026). Any mode, red flags included: it's her explicit instruction.
    Never past the kill switch, before go-live, or outside the customer's 24h
    window (only the Business app can write then). If the model says it isn't
    an answer for this chat, or its write-up fails the reply check, nothing is
    sent and Chris is told why. Returns the message for Chris."""
    state = st.load(wa_id)
    who = staff.label(state.name, wa_id, state.code)

    def refuse(why: str, reason: str) -> str:
        events.record("staff_answer", wa_id, reason=f"refused:{reason}")
        return staff.answer_refused_text(who, why)

    if not answer.strip():
        return (f"What should I tell {who}? Swipe-reply to the ping with the answer, or text "
                f"ANSWER {state.code} and the answer.")
    if config.KILL_SWITCH or st.get_kill():
        return refuse("the assistant is stopped (text START first)", "kill_switch")
    if _not_live(st):
        return refuse("the assistant isn't live yet", "not_live")
    if wa_id in config.ALWAYS_HUMAN:
        return refuse("this number is set to always go to you", "always_human")
    if not any(h["role"] == "customer" for h in state.history):
        return refuse("I no longer have this chat's messages", "no_history")
    if not customer_window_open(state, time.time()):
        return refuse("their last message was over a day ago, so WhatsApp only lets the "
                      "Business app message them now", "window_closed")
    for _attempt in range(2):
        started = time.time()
        history = list(state.history)
        latest = next((h["id"] for h in reversed(history) if h["role"] == "customer"), "")
        patient = _patient_for(st, wa_id, state)
        res = agent.propose(history, wa_id=wa_id, now=started, customer_name=state.name,
                            client=model, patient=tools.describe_patient(patient),
                            team_answer=answer)
        p = res.proposal
        events.record("proposal", wa_id, intent=p.intent, confidence=p.confidence,
                      escalate=p.escalate, decision="staff_answer", reason="staff_answer",
                      agent_ms=res.total_ms, steps=[s.__dict__ for s in res.steps],
                      tools=",".join(res.tools_used), model=res.model_served, stop=res.stop,
                      input_tokens=res.input_tokens, output_tokens=res.output_tokens,
                      cache_read_tokens=res.cache_read_tokens,
                      cache_write_tokens=res.cache_write_tokens, cost_usd=round(res.cost_usd, 5))
        reply = (p.reply or "").strip()
        if p.failed:
            return refuse("I couldn't write it up just now", "model_failed")
        if p.escalate:
            return refuse(p.escalation_reason or "it doesn't look like an answer for this chat",
                          "not_an_answer")
        problems = reply_problems(reply) if reply else ["empty"]
        if problems:
            return refuse("my write-up didn't pass the checks (" + ", ".join(problems) + ")",
                          "reply_check")
        with locks(wa_id):
            state = st.load(wa_id)
            if state.last_human_at > started:
                return refuse("you've written in the chat yourself since", "human_replied")
            if config.KILL_SWITCH or st.get_kill():
                return refuse("the assistant was stopped", "kill_switch")
            newest = next((h["id"] for h in reversed(state.history)
                           if h["role"] == "customer"), "")
            if newest != latest:
                continue  # they wrote again while it was thinking: write it up again
            try:
                mid = _send_bubbles(client, Inbound(wa_id=wa_id, msg_id=newest,
                                                    ts=time.time(), text=""), reply)
            except Exception as e:
                log.warning("staff answer send failed: %s", e)
                events.record("send_failed", wa_id, reason=type(e).__name__)
                return refuse("WhatsApp wouldn't send it", "send_failed")
            sent_at = time.time()
            append_history(state, "team", answer.strip(), sent_at)
            append_history(state, "agent", as_one_message(reply), sent_at, mid)
            old = state.mode
            # Part still open: the agent keeps the chat but not that topic.
            still_open = (p.staff_note or "").strip()
            mode = WAITING if still_open else AGENT
            if not set_mode(state, mode, "staff_answered", sent_at):
                state.mode_reason, state.mode_since = "staff_answered", sent_at
            state.pending_for_chris = still_open[:600]
            state.owner = "agent"
            state.off_topic_strikes = 0
            state.pending_draft, state.last_auto = {}, {}
            note_outcome(state, "staff_answer",
                         summary.TEAM_PARTIAL if still_open else summary.TEAM_ANSWER, sent_at)
            st.save(state)
        _mode_event(state, old, sent_at)
        events.record("staff_answer", wa_id, wa_msg_id=mid,
                      reason="sent_partial" if still_open else "sent")
        return staff.answer_sent_text(who, as_one_message(reply), still_open)
    return refuse("they kept writing while I was writing it up", "superseded")


def handle_history(chunk: HistoryChunk) -> None:
    """Coexistence history: who wrote last, and when, per customer (never the
    text). The go-live cut-off reads these times (pre_golive_chat)."""
    st, _, _ = _deps()
    for wa_id, (cust_ts, biz_ts) in chunk.threads.items():
        if wa_id in config.STAFF:
            continue
        with locks(wa_id):
            state = st.load(wa_id)
            state.last_customer_at = max(state.last_customer_at, cust_ts or 0.0)
            state.last_staff_at = max(state.last_staff_at, biz_ts or 0.0)
            st.save(state)
    if chunk.declined:
        events.record("history_import", "", reason=f"declined:{chunk.error_code}")
        return
    events.record("history_import", "", reason=f"progress:{chunk.progress}")
    if chunk.progress >= 100:
        st.set_history_imported(True, source="webhook")


def _test_show(client, wa_id: str, text: str) -> None:
    """Local battle-testing: show the tester what would otherwise only reach
    staff. Never on a deployed service, never stored in the transcript."""
    if config.TEST_SHOW_DRAFTS and config.STATE_BACKEND == "memory":
        try:
            client.send_text(wa_id, "🧪 TEST MODE (customers never see this)\n\n" + text)
        except Exception as e:
            log.warning("test-mode send failed: %s", e)


def _tag_waiver_used(st, wa_id: str, patient: dict) -> None:
    """Chris sent the late-change draft that waives the fee as is: record the
    waiver on the patient in Plato (the system of record), so it's used once."""
    ids = (patient or {}).get("patient_ids") or []
    if len(ids) != 1 or not config.PLATO_TAG_WRITES:
        reason = ("tag_writes_off" if config.PLATO_TAG_WRITES is False and len(ids) == 1
                  else "no_patient_record" if not ids else "several_patients_on_number")
        events.record("patient_tag_skipped", wa_id, reason=reason)
        why = ("" if reason == "tag_writes_off"
               else " (the assistant couldn't tell which one)")
        _alert("fyi", customer="", wa_id=wa_id, suggested_reply="",
                    staff_note="You sent the late-change draft that waives the fee. Please "
                               "add the 'Late change waiver used' tag to the right patient "
                               f"in Plato{why}.",
                    reason=reason, last_message="")
        return
    try:
        res = booking_client.tag_patient(ids[0])
        events.record("patient_tagged", wa_id, reason="dry_run" if res.get("dry_run")
                      else ("added" if res.get("added") else "already_tagged"))
    except booking_client.BookingFailed as e:
        events.record("patient_tag_failed", wa_id, reason=e.code)


def _book_pending(state, ev: Inbound, received: float, fallback: str,
                  chosen: dict | None = None) -> tuple[str, dict | None, bool]:
    """The customer confirmed: book what was stated back to them, if it was
    stated in an earlier message and recently. The model can't book on its
    own say-so in the same turn. Returns (reply, booking or None, failed)."""
    chosen = chosen or {}
    pending = state.pending_booking or {}
    if not pending or pending.get("at", 0) >= received \
            or received - pending.get("at", 0) > config.BOOKING_CONFIRM_WINDOW_S:
        events.record("book_skipped", ev.wa_id, reason="no_pending_booking")
        return fallback, None, False
    # The customer either said yes to the booking stated back, or picked one of
    # the times offered in that earlier message. Nothing else gets booked.
    pick = (chosen.get("date", ""), chosen.get("time", ""))
    if pick != (pending.get("date"), pending.get("time")):
        if pick not in booking_client.offered(pending.get("options", "")):
            events.record("book_skipped", ev.wa_id, reason="time_not_offered")
            return fallback, None, False
        pending = {**pending, "date": pick[0], "time": pick[1],
                   "full_name": pending.get("full_name") or chosen.get("full_name", "")}
    # An email given with the pick (or as the corrected one) counts too.
    if (chosen.get("email") or "").strip():
        pending = {**pending, "email": chosen["email"].strip()}
    if not booking_client.complete(pending):
        events.record("book_skipped", ev.wa_id, reason="details_missing")
        return fallback, None, False
    patient_id = tools.record_for_booking(state.patient or {}, pending.get("full_name", ""),
                                          pending.get("for_whom", ""))
    check = booking_client.email_check(pending.get("email", ""))
    if check:
        # A mistyped email would bounce the confirmation: ask, and keep the
        # time so their answer books it.
        return _ask_email_again(state, ev, pending, check)
    on_file = "" if (pending.get("email") or "").strip() else \
        tools.record_email(state.patient or {}, patient_id)
    # A returning patient's email on file, so Plato's confirmation (and the
    # registration form) still goes out.
    sent = {**pending, "email": on_file} if on_file else pending
    try:
        try:
            res = booking_client.book(sent, wa_id=ev.wa_id, patient_id=patient_id)
        except booking_client.BookingFailed as e:
            if e.code != "bad_email":
                raise
            if on_file:   # Plato's own copy is off: book without it, ask nobody
                sent = pending
                res = booking_client.book(sent, wa_id=ev.wa_id, patient_id=patient_id)
            else:
                return _ask_email_again(state, ev, pending, booking_client.email_check(
                    pending.get("email", ""), str(e)))
    except booking_client.BookingFailed as e:
        state.pending_booking = {}
        events.record("book_failed", ev.wa_id, reason=e.code)
        _alert("escalated", customer=ev.name, wa_id=ev.wa_id,
                    staff_note=f"Booking failed ({e.code}): {pending.get('service')} "
                               f"{pending.get('date')} {pending.get('time')}",
                    suggested_reply="", reason=f"booking failed: {e}", last_message=ev.text)
        if e.code == "slot_taken":
            return ("Sorry, that time was just taken! Would you like me to find the next "
                    "open one?"), None, True
        return ("Sorry, I couldn't complete the booking just now. I've let the team "
                "know and they'll sort it out with you shortly."), None, True
    events.record("booked", ev.wa_id, intent="booking",
                  reason="dry_run" if res.get("dry_run") else "agent")
    first = (pending.get("full_name") or "").split(" ")[0]
    for_other = (pending.get("for_whom") or "self").strip().lower() not in ("", "self")
    return (booking_client.confirmation_text(res, first_name="" if for_other else first,
                                             patient=first if for_other else "",
                                             emailed=bool((sent.get("email") or "").strip())),
            {"reference": res["reference"], "date": res["date"], "time": res["time"],
             "with": res.get("clinician_name", ""), "service": res.get("service", ""),
             "dry_run": bool(res.get("dry_run")), "at": time.time(), "source": "whatsapp"},
            False)


def _ask_email_again(state, ev: Inbound, pending: dict, question: str):
    """The email given wouldn't reach them: ask again and keep the time, so the
    answer books it (the pick is already their yes). Not a failure: no alert."""
    state.pending_booking = {**pending, "email": "", "options": "", "at": time.time()}
    events.record("book_skipped", ev.wa_id, reason="email_check")
    return question, None, False


BUBBLE_PAUSE_S = 1.2


def _send_bubbles(client, ev: Inbound, reply: str) -> str:
    """Send a reply as up to 2 WhatsApp bubbles, with the typing indicator
    and a short pause between them so they read like a person typing.
    Returns the last message id."""
    bubbles = split_bubbles(reply) or [reply]
    msg_id = ""
    for i, bubble in enumerate(bubbles):
        if i:
            client.mark_read_typing(ev.msg_id)
            _sleep(BUBBLE_PAUSE_S)
        msg_id = client.send_text(ev.wa_id, bubble)
    return msg_id


def _move_pending(state, ev: Inbound, received: float, fallback: str,
                  chosen: dict | None = None) -> tuple[str, dict | None, bool]:
    """The customer confirmed the move stated back to them in an earlier message:
    move it through goji-booking. Chris is only told if it fails.
    Returns (reply, booking or None, failed)."""
    pending = state.pending_move or {}
    if not pending or pending.get("at", 0) >= received \
            or received - pending.get("at", 0) > config.BOOKING_CONFIRM_WINDOW_S:
        events.record("move_skipped", ev.wa_id, reason="no_pending_move")
        return fallback, None, False
    chosen = chosen or {}
    pick = (chosen.get("new_date", ""), chosen.get("new_time", ""))
    if pick != (pending.get("new_date"), pending.get("new_time")):
        if pick not in booking_client.offered(pending.get("options", "")):
            events.record("move_skipped", ev.wa_id, reason="time_not_offered")
            return fallback, None, False
        pending = {**pending, "new_date": pick[0], "new_time": pick[1]}
    if not booking_client.move_complete(pending):
        events.record("move_skipped", ev.wa_id, reason="details_missing")
        return fallback, None, False
    ids = (state.patient or {}).get("patient_ids") or []
    try:
        res = booking_client.move(pending, wa_id=ev.wa_id,
                                  patient_id=ids[0] if len(ids) == 1 else "")
    except booking_client.BookingFailed as e:
        state.pending_move = {}
        events.record("move_failed", ev.wa_id, reason=e.code)
        if e.code == "slot_taken":
            return ("Sorry, that time was just taken! Would you like me to find another "
                    "one?"), None, False  # it offers another time: not a failure
        _alert("escalated", customer=ev.name, wa_id=ev.wa_id,
                    staff_note=f"Couldn't move their appointment ({e.code}): "
                               f"{pending.get('old_date')} {pending.get('old_time')} -> "
                               f"{pending.get('new_date')} {pending.get('new_time')}",
                    suggested_reply="", reason=f"move failed: {e}", last_message=ev.text)
        return ("Sorry, I couldn't move it just now. I've let the team know and they'll "
                "sort it out with you shortly."), None, True
    events.record("moved", ev.wa_id, intent="reschedule",
                  reason="dry_run" if res.get("dry_run") else "agent")
    return (booking_client.move_text(res),
            {"reference": res["reference"], "date": res["new_date"], "time": res["new_time"],
             "with": res.get("clinician_name", ""), "service": res.get("service", ""),
             "dry_run": bool(res.get("dry_run")), "at": time.time(), "source": "whatsapp"},
            False)


def _cancel_now(state, ev: Inbound, cancel: dict, follow_up: str) -> tuple[str, bool, bool]:
    """Cancel the appointment the customer asked to cancel, in the same turn
    (owner, 24 Nov 2026: no "shall I?" first). goji-booking checks it is
    theirs and 24h+ away. The reply is the confirmation built from its answer
    plus the model's follow-up line. Chris is only told if it fails.
    Returns (reply, cancelled, failed)."""
    ids = (state.patient or {}).get("patient_ids") or []
    try:
        res = booking_client.cancel(cancel, wa_id=ev.wa_id,
                                    patient_id=ids[0] if len(ids) == 1 else "")
    except booking_client.BookingFailed as e:
        events.record("cancel_failed", ev.wa_id, reason=e.code)
        _alert("escalated", customer=ev.name, wa_id=ev.wa_id,
               staff_note=f"Couldn't cancel their appointment ({e.code}): "
                          f"{cancel.get('date')} {cancel.get('time')}",
               suggested_reply="", reason=f"cancel failed: {e}", last_message=ev.text)
        if e.code == "late_change":
            return ("Thanks for letting us know. As it's within 24 hours of your "
                    "appointment, I've passed this to the team and they'll sort it out "
                    "with you shortly."), False, True
        return ("Sorry, I couldn't cancel it just now. I've let the team know and they'll "
                "sort it out with you shortly."), False, True
    events.record("cancelled", ev.wa_id, intent="cancel",
                  reason="dry_run" if res.get("dry_run") else "agent")
    if (state.booked or {}).get("date") == res.get("date") \
            and (state.booked or {}).get("time") == res.get("time"):
        state.booked = {}
    state.patient_at = 0.0  # the record's next appointment has changed: look it up again
    return booking_client.cancel_text(res, follow_up), True, False


def _read_document(client, ev: Inbound) -> str:
    try:
        data, mime = client.download_media(ev.media_id)
    except Exception as e:
        log.warning("document download failed: %s", e)
        return ""
    return documents.extract_text(data, mime or ev.mime, ev.filename)


PATIENT_CACHE_S = 6 * 3600
# "No record" is kept only briefly: the number may become a patient minutes
# later (booked here, on the website or at the desk), and a 6-hour "no record"
# made the agent hand over a booking it had made itself (24 Nov 2026).
NO_RECORD_CACHE_S = 10 * 60


def _booked_note(state) -> str:
    b = state.booked or {}
    if not b or time.time() - b.get("at", 0) > 14 * 86400:
        return ""
    return (f"just booked ({b.get('source')}): {b.get('service')} {b.get('date')} "
            f"{b.get('time')} with {b.get('with') or 'the team'}, ref {b.get('reference')}"
            f"{' (test dry run)' if b.get('dry_run') else ''}; don't offer times for it again")


def _late_change_note(changes: list[dict], tagged: bool = False) -> str:
    """Earlier late changes from this number (tracked since go-live) or the
    Plato tag, so the agent only offers the first-time fee waiver once."""
    if tagged and not changes:
        return ""  # describe_patient already says the waiver was used
    if not changes:
        return "no earlier late changes on record (first-time waiver applies)"
    last = datetime.fromtimestamp(max(c["at"] for c in changes), SGT)
    return (f"{len(changes)} earlier late change(s) on record, last {last:%d %b %Y} "
            "(first-time waiver already used)")


def _patient_for(st, wa_id: str, state) -> dict:
    """Who this number is (returning-patient recognition), looked up in code by
    the chat's own number and cached on the chat for a few hours."""
    ttl = PATIENT_CACHE_S if (state.patient or {}).get("returning") else NO_RECORD_CACHE_S
    if state.patient_at and time.time() - state.patient_at < ttl:
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


RESET_COMMAND = "/reset"
TURBO = {"hold": 0.0, "debounce": 1.5}   # /turbo on: no pre-send hold, short debounce
_NORMAL = {"hold": config.PRE_SEND_HOLD_S, "debounce": config.DEBOUNCE_S}
if config.TURBO_AT_START and config.STATE_BACKEND == "memory":  # local test runs only
    config.PRE_SEND_HOLD_S, config.DEBOUNCE_S = TURBO["hold"], TURBO["debounce"]


def _tester(ev: Inbound) -> bool:
    return config.STATE_BACKEND == "memory" or ev.wa_id in config.TESTERS


def _is_reset(ev: Inbound) -> bool:
    return (ev.text or "").strip().lower() == RESET_COMMAND and _tester(ev)


def _turbo_command(st, client, ev: Inbound) -> bool:
    """Testing: '/turbo on' drops the 20s pre-send hold and shortens the
    debounce for the whole service (so a person can't step in first: test
    numbers only); '/turbo off' restores them. Returns True if handled."""
    words = (ev.text or "").strip().lower().split()
    if not words or words[0] != "/turbo" or not _tester(ev):
        return False
    on = len(words) < 2 or words[1] != "off"
    vals = TURBO if on else _NORMAL
    config.PRE_SEND_HOLD_S, config.DEBOUNCE_S = vals["hold"], vals["debounce"]
    events.record("turbo", ev.wa_id, reason="on" if on else "off")
    try:
        client.send_text(ev.wa_id, f"🧪 Turbo {'on: replies as soon as they are ready' if on else 'off: normal 20s hold'}.")
    except Exception as e:
        log.warning("turbo reply failed: %s", e)
    return True


def _reset_chat(st, client, ev: Inbound) -> None:
    """Testing: forget this chat (transcript, mode, pending bookings, cached
    patient record, late-change record) so the next message starts fresh.
    Kept: autonomy and everything outside this chat."""
    with locks(ev.wa_id):
        state = st.load(ev.wa_id)
        fresh = state.__class__(wa_id=ev.wa_id, seen_ids=state.seen_ids)
        mark_seen(fresh, ev.msg_id)
        st.save(fresh)
    st.clear_late_changes(events.chat_key(ev.wa_id))
    events.record("reset", ev.wa_id, reason="tester")
    try:
        client.send_text(ev.wa_id, "🧪 Reset done. This chat starts fresh from your next message.")
    except Exception as e:
        log.warning("reset reply failed: %s", e)


def _go_live(st) -> float:
    return st.get_go_live() or config.GO_LIVE


def _not_live(st) -> bool:
    """A deployed run answers nobody until go-live is set; it only records
    message times, which the go-live cut-off reads. Local runs are live."""
    return config.STATE_BACKEND == "firestore" and not _go_live(st)


def _gate_now(st, state, now: float, rollout: dict, *, prior_last_at: float = 0.0,
              had_record: bool = True, patient: dict | None = None):
    """policy.gate with the live switches: kill switch, not live yet, the
    go-live cut-off, rollout hours and scope."""
    return gate(state, now, kill_switch=config.KILL_SWITCH or st.get_kill(),
                agent_hours=rollout["hours"], not_live=_not_live(st),
                pre_golive=pre_golive_chat(state, prior_last_at, _go_live(st)),
                scope_out=out_of_scope(rollout["contact_scope"], state, had_record,
                                       patient or {}))


def _hold_pre_golive(state, blocked, now: float) -> None:
    """Chris was handling this chat at go-live: pause it, so it stays hers
    until she resumes it, however long it goes quiet."""
    if blocked and blocked.reason == "pre_golive_chat":
        set_mode(state, PAUSED, "pre_golive_chat", now)


def handle_inbound(ev: Inbound, received: float) -> None:
    if ev.wa_id in config.STAFF:
        handle_staff(ev)
        return
    st, client, model = _deps()
    now = time.time()
    rollout = config.resolve_rollout(st.get_rollout())
    if _is_reset(ev):
        _reset_chat(st, client, ev)
        return
    if _turbo_command(st, client, ev):
        return
    if ev.kind == "button" and (ev.text or "").strip().lower() == "confirm":
        # The reminder template's Confirm tap: thank them, no model call.
        # (Reschedule goes to the agent like any message.)
        with locks(ev.wa_id):
            state = st.load(ev.wa_id)
            if not mark_seen(state, ev.msg_id):
                return
            prior = max(state.last_customer_at, state.last_staff_at)
            old = state.mode
            apply_pause_expiry(state, now)
            state.last_customer_at = max(state.last_customer_at, ev.ts or now)
            append_history(state, "customer", "Confirm", ev.ts, ev.msg_id)
            state.code = state.code or st.next_code()
            blocked = _gate_now(st, state, now, rollout, prior_last_at=prior)
            if blocked:  # kill switch, Chris's chat, paused...: she sees the tap
                _hold_pre_golive(state, blocked, now)
                st.save(state)
                _mode_event(state, old, now)
                events.record("silent", ev.wa_id, reason=blocked.reason)
                return
            try:
                mid = client.send_text(ev.wa_id, "Thanks for confirming! See you then 😊")
                append_history(state, "agent", "Thanks for confirming! See you then 😊",
                               time.time(), mid)
            except Exception as e:
                log.warning("confirm reply failed: %s", e)
            st.save(state)
        _mode_event(state, old, now)
        events.record("reminder_confirmed", ev.wa_id, reason="button")
        return
    if ev.kind == "document" and ev.media_id:
        ev.text = documents.as_message(_read_document(client, ev), ev.filename, ev.caption)
    scope_patient = {}
    if rollout["contact_scope"] == "new_only":
        peek = st.load(ev.wa_id)
        if peek.owner != "agent":  # a chat the agent already took stays its own
            scope_patient = _patient_for(st, ev.wa_id, peek)
    with locks(ev.wa_id):
        state = st.load(ev.wa_id)
        if not mark_seen(state, ev.msg_id):
            return
        old = state.mode
        # The go-live cut-off reads the latest message BEFORE this one.
        prior_last_at = max(state.last_customer_at, state.last_staff_at)
        had_record = has_record(state)
        apply_idle_handback(state, now)
        apply_pause_expiry(state, now)
        state.last_customer_at = max(state.last_customer_at, ev.ts or now)
        state.name = ev.name or state.name
        state.code = state.code or st.next_code()
        append_history(state, "customer", ev.text, ev.ts, ev.msg_id)
        blocked = _gate_now(st, state, now, rollout, prior_last_at=prior_last_at,
                            had_record=had_record, patient=scope_patient)
        _hold_pre_golive(state, blocked, now)
        if not blocked:
            state.owner = "agent"  # claimed under the lock: the rest of a burst passes
        st.save(state)
        history = list(state.history)
    _mode_event(state, old, now)
    events.record("inbound", ev.wa_id, kind=ev.kind, webhook_lag_s=round(received - ev.ts, 1))
    if blocked:
        events.record("silent", ev.wa_id, reason=blocked.reason)
        return
    ack_closer = False
    if is_acknowledgement(ev.text, history):
        # One warm closer per conversation ("You're welcome! Were you thinking of
        # coming in...?"), then silence, so a thank-you loop ends. None at all
        # once they've booked or the chat is with Chris.
        last_agent = next((h for h in reversed(history) if h["role"] == "agent"), {})
        recently_booked = state.booked and time.time() - state.booked.get("at", 0) < 86400
        # Only a brief first exchange (one quick question, like opening hours)
        # earns the nudge; someone already deep in a conversation doesn't.
        day_ago = time.time() - 86400
        earlier = sum(1 for h in history[:-1] if h["role"] == "customer" and h["ts"] >= day_ago)
        if (last_agent.get("id") and last_agent.get("id") == state.closer_id) \
                or recently_booked or state.mode == WAITING or earlier > 2:
            events.record("silent", ev.wa_id, reason="acknowledgement")
            return
        ack_closer = True

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
        blocked = gate(state, time.time(), kill_switch=config.KILL_SWITCH or st.get_kill(),
                       agent_hours=rollout["hours"])
        if blocked:
            events.record("silent", ev.wa_id, reason=blocked.reason)
            return

    client.mark_read_typing(ev.msg_id)
    patient = _patient_for(st, ev.wa_id, state)
    key = events.chat_key(ev.wa_id)
    earlier_late = st.get_late_changes(key)
    waiver_used = bool(earlier_late) or bool(patient.get("waiver_used"))
    res = agent.propose(history, wa_id=ev.wa_id, now=now, customer_name=ev.name,
                        client=model,
                        pending_for_chris=state.pending_for_chris if state.mode == WAITING else "",
                        patient="; ".join(filter(None, [
                            tools.describe_patient(patient),
                            _late_change_note(earlier_late, patient.get("waiver_used")),
                            _booked_note(state)])))
    _schedule_warm()
    p = res.proposal
    p.reply = mask_customer_emails(p.reply, history)
    check_late_change(p, patient.get("next_appointment"), time.time())
    d = decide(p, intent_policy=learning.effective_policy(config.stage_policy(rollout["stage"]),
                                                          st.get_autonomy()))
    d = apply_stage(d, p, rollout["stage"])
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
                  suggested_reply=as_one_message(p.reply), reason=d.reason, last_message=ev.text,
                  feedback=learning.feedback_links(events.chat_key(ev.wa_id), int(now)))

    if d.action == SILENT:  # stage 0 leaves it to Chris: no reply, no notice
        with locks(ev.wa_id):
            state = st.load(ev.wa_id)
            if p.intent == OFF_TOPIC:  # junk whose reply failed the check: drop it
                _watch(st, state, ev.wa_id, p.intent, time.time())
                note_outcome(state, p.intent, "off-topic, no reply", time.time())
            else:
                note_outcome(state, p.intent, "left", time.time())
            st.save(state)
        events.record("silent", ev.wa_id, intent=p.intent, reason=d.reason)
        _test_show(client, ev.wa_id, f"Left for Chris, no reply ({d.reason}).")
        return

    if d.action == DRAFT:
        late = (p.intent in ("reschedule", "cancel")
                and 0 <= p.hours_to_appointment < LATE_CHANGE_H)
        with locks(ev.wa_id):
            state = st.load(ev.wa_id)
            state.pending_draft = {"text": as_one_message(p.reply), "intent": p.intent,
                                   "at": time.time(),
                                   "waives_fee": late and not waiver_used}
            state.last_auto = {}
            note_outcome(state, p.intent, "drafted", time.time())
            st.save(state)
        notify.send("drafted", **notice)
        events.record("drafted", ev.wa_id, intent=p.intent, reason=d.reason)
        _test_show(client, ev.wa_id,
                   f"Not sent. Chris gets this draft to check ({d.reason}):\n\n"
                   f"{as_one_message(p.reply)}")
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
        # A handover sends the holding reply; p.reply is Chris's draft (notice).
        reply = customer_message(d, p, time.time())
        booked, failed, cancelled = None, False, False
        if d.action == SEND and p.intent == "cancel" and booking_client.cancel_complete(p.cancel):
            reply, cancelled, failed = _cancel_now(state, ev, p.cancel, reply)
        elif d.action == SEND and p.confirm_booking:
            reply, booked, failed = _book_pending(state, ev, received, reply, p.booking)
        elif d.action == SEND and p.confirm_move:
            reply, booked, failed = _move_pending(state, ev, received, reply, p.move)
        try:
            wa_msg_id = _send_bubbles(client, ev, reply)
        except Exception as e:
            log.warning("send failed: %s", e)
            events.record("send_failed", ev.wa_id, reason=type(e).__name__)
            _alert("escalated", **{**notice, "reason": f"send failed: {e}",
                                   "staff_note": "The assistant couldn't send its reply. "
                                                 "Please answer this chat."})
            return
        sent_at = time.time()
        append_history(state, "agent", as_one_message(reply), sent_at, wa_msg_id)
        if ack_closer:
            state.closer_id = wa_msg_id
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
        watched = _watch(st, state, ev.wa_id, p.intent, sent_at)
        note_outcome(state, p.intent, "watch-listed" if watched
                     else "cancelled" if cancelled
                     else _outcome(d, p, reply, booked, failed), sent_at)
        if booked:
            state.booked, state.pending_booking, state.pending_move = booked, {}, {}
            state.patient_at = 0.0  # look again: the booking may have made a patient
        elif d.action == SEND and not p.confirm_move and p.move.get("old_date") and (
                booking_client.move_complete(p.move) or booking_client.offered(p.move.get("options", ""))):
            state.pending_move = {**{k: p.move.get(k, "") for k in booking_client.MOVE_FIELDS},
                                  "options": p.move.get("options", ""), "at": sent_at}
        elif d.action == SEND and not p.confirm_booking and (
                booking_client.complete(p.booking)
                or (p.booking.get("service") and booking_client.offered(p.booking.get("options", "")))):
            # Stated back, or times offered; only their next message can confirm.
            state.pending_booking = {**{k: p.booking.get(k, "") for k in booking_client.FIELDS},
                                     "options": p.booking.get("options", ""), "at": sent_at}
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
    if d.action == SEND and p.intent == "priority":
        # Sent and flagged at once: Chris hears as the customer gets the reply.
        _alert("priority", **{**notice, "sent_reply": as_one_message(reply),
                              "staff_note": f"Priority, getting worse: {p.staff_note}"})
        _test_show(client, ev.wa_id, f"Chris is pinged now (priority): {p.staff_note}")
    if d.action == SEND and config.INTENT_POLICY.get(p.intent) == "auto_notify":
        notify.send("fyi", **notice)
        _test_show(client, ev.wa_id, f"Chris would get an FYI email: {p.staff_note}")
    if d.action == ESCALATE:
        _alert(p.intent if p.intent in ("urgent", "sensitive") else "escalated",
               **{**notice, "sent_reply": as_one_message(reply)})
        _test_show(client, ev.wa_id, f"Handed to Chris ({d.reason}). She'd be told: "
                                     f"{p.staff_note}")


def _watch(st, state, wa_id: str, intent: str, now: float) -> bool:
    """The off-topic count (policy.note_off_topic); at the limit the chat is
    paused on the watch list with a code staff can RESUME. No ping: it's in
    the morning summary."""
    if not note_off_topic(state, intent, now):
        return False
    state.code = state.code or st.next_code()
    state.owner = ""
    events.record("watchlist", wa_id, reason=f"off_topic:{state.off_topic_strikes}")
    return True


def _outcome(d, p, reply: str, booked: dict | None, failed: bool) -> str:
    """For the morning summary."""
    if failed:
        return "failed"
    if p.intent == OFF_TOPIC:
        return "off-topic"
    if d.action == ESCALATE:
        return "handed over"
    if p.intent == "priority":
        return "booked, flagged" if booked else "flagged, times offered"
    if booked:
        return "moved" if p.confirm_move else "booked"
    return "link sent" if "wa-book" in reply else "answered"


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
        state.owner = "agent" if mode == AGENT else ""
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


@app.post("/admin/chats/<wa_id>/forget")
def forget(wa_id: str):
    """PDPA deletion: the chat doc (transcript, state) and the late-change
    record. BigQuery holds no text or numbers, only the salted key."""
    if not _authorised():
        return jsonify({"error": "forbidden"}), 403
    st, _, _ = _deps()
    with locks(wa_id):
        st.delete_chat(wa_id)
    st.clear_late_changes(events.chat_key(wa_id))
    events.record("forgotten", wa_id, reason="admin")
    return jsonify({"wa_id": wa_id, "forgotten": True})


@app.get("/admin/rollout")
def rollout_get():
    if not _authorised():
        return jsonify({"error": "forbidden"}), 403
    st, _, _ = _deps()
    saved = st.get_rollout()
    return jsonify({**config.resolve_rollout(saved), "saved": saved,
                    "env": config.resolve_rollout({}), "go_live": _go_live(st),
                    "history_imported": st.get_history_imported()})


@app.post("/admin/rollout")
def rollout_set():
    """{"stage": 0-3, "contact_scope": "quiet"|"new_only", "hours":
    "all"|"after_hours"}; a key set to null goes back to the env default."""
    if not _authorised():
        return jsonify({"error": "forbidden"}), 403
    body = request.get_json(silent=True) or {}
    allowed = {"stage": config.STAGES, "contact_scope": config.CONTACT_SCOPES,
               "hours": config.HOURS_VALUES}
    bad = [k for k, v in body.items()
           if k not in allowed or (v is not None and (v not in allowed[k]
                                                      or isinstance(v, bool)))]
    if bad:
        return jsonify({"error": f"invalid: {', '.join(sorted(bad))}"}), 400
    st, _, _ = _deps()
    saved = st.get_rollout()
    for k, v in body.items():
        if v is None:
            saved.pop(k, None)
        else:
            saved[k] = v
    st.save_rollout(saved)
    live = config.resolve_rollout(saved)
    events.record("rollout", "", reason=f"stage:{live['stage']},scope:{live['contact_scope']},"
                                        f"hours:{live['hours']}")
    return jsonify({**live, "saved": saved})


@app.post("/admin/history-imported")
def history_imported():
    if not _authorised():
        return jsonify({"error": "forbidden"}), 403
    on = bool((request.get_json(silent=True) or {}).get("on", True))
    st, _, _ = _deps()
    st.set_history_imported(on, source="admin")
    events.record("history_import", "", reason=f"admin:{'on' if on else 'off'}")
    return jsonify({"history_imported": on})


@app.post("/admin/go-live")
def go_live():
    """Set the go-live moment: from then on the agent answers, and chats with
    a message in the 30 days before it stay Chris's. {"at": epoch} or omitted
    for now; {"at": null} takes it back to not live."""
    if not _authorised():
        return jsonify({"error": "forbidden"}), 403
    body = request.get_json(silent=True) or {}
    at = body.get("at", time.time())
    if at is not None and (isinstance(at, bool) or not isinstance(at, (int, float))):
        return jsonify({"error": "at must be epoch seconds or null"}), 400
    st, _, _ = _deps()
    st.set_go_live(at or 0, source="admin")
    events.record("go_live", "", reason=f"at:{int(at or 0)}")
    return jsonify({"go_live": float(at or 0), "lookback_days": config.GOLIVE_LOOKBACK_DAYS})


@app.post("/internal/morning-summary")
def morning_summary():
    """Cloud Scheduler, ~7:30 SGT: the last 24h by email, a one-liner to staff
    whose WhatsApp window is open (outside it a template would cost money and
    say less than the email)."""
    if not _authorised():
        return jsonify({"error": "forbidden"}), 403
    st, client, _ = _deps()
    now = time.time()
    chats = [c for c in st.recent_chats(now - summary.DAY_S) if c.wa_id not in config.STAFF]
    paused = [c for c in st.paused_chats() if c.wa_id not in config.STAFF]
    s = summary.build(chats, now, paused=paused)
    notify.send_plain(s["subject"], s["body"])
    windows, pinged = st.get_staff_windows(), 0
    for number in sorted(config.STAFF):
        if staff.window_open(windows.get(number, 0.0), now):
            try:
                client.send_text(number, s["line"])
                pinged += 1
            except Exception as e:
                log.warning("summary ping failed: %s", e)
    events.record("morning_summary", "", reason=f"answered:{s['answered']},left:{s['left']},"
                                                f"failed:{s['failed']}")
    return jsonify({k: s[k] for k in ("answered", "left", "failed", "paused")}
                   | {"staff_pinged": pinged})


def _send_confirmation_template(client, wa_id: str, b: dict) -> str:
    """A website booking from someone outside the 24-hour window: the
    approved confirmation template (the booking form carries the opt-in).
    Returns the message id, or "" when off or it failed."""
    if not (config.CONFIRMATIONS and b.get("date") and b.get("time")):
        return ""
    when = booking_client._when(b["date"], b["time"])
    params = [b.get("first_name") or "there", (b.get("service") or "physiotherapy").lower(),
              when, (b.get("clinician_name") or "our team").split(" ")[0]]
    try:
        msg_id = client.send_template(wa_id, config.CONFIRM_TEMPLATE, params)
    except Exception as e:
        log.warning("confirmation template failed: %s", e)
        events.record("confirmation_failed", wa_id, reason=type(e).__name__)
        return ""
    events.record("confirmation_sent", wa_id, reason="template")
    return msg_id


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
    # Kill switch or not live: note the booking, send nothing.
    quiet = config.KILL_SWITCH or st.get_kill() or _not_live(st)
    with locks(wa_id):
        state = st.load(wa_id)
        if not state.history:
            sent = "" if quiet else _send_confirmation_template(client, wa_id, b)
            if sent:
                state.booked = {"reference": b.get("reference", ""), "date": b.get("date", ""),
                                "time": b.get("time", ""), "with": b.get("clinician_name", ""),
                                "service": b.get("service", ""), "dry_run": False,
                                "at": time.time(), "source": b.get("source", "web")}
                append_history(state, "agent", "(appointment confirmation template sent)",
                               time.time(), sent)
                st.save(state)
            return jsonify({"matched": False, "template_sent": bool(sent)})
        state.booked = {"reference": b.get("reference", ""), "date": b.get("date", ""),
                        "time": b.get("time", ""), "with": b.get("clinician_name", ""),
                        "service": b.get("service", ""), "dry_run": False,
                        "at": time.time(), "source": b.get("source", "web")}
        state.pending_booking = {}
        last_customer = max((h["ts"] for h in state.history if h["role"] == "customer"),
                            default=0)
        acked = False
        in_window = time.time() - last_customer < 23 * 3600
        # A chat Chris has (she wrote, or was handling it at go-live) gets no
        # message from us.
        chris_has_it = state.mode in (HUMAN, PAUSED) or pre_golive_chat(
            state, max(state.last_customer_at, state.last_staff_at), _go_live(st))
        if quiet or chris_has_it:
            pass
        elif b.get("source") != "whatsapp" and not in_window:
            # An old chat, outside the 24-hour window: free-form isn't allowed.
            acked = bool(_send_confirmation_template(client, wa_id, b))
        if (not quiet and not chris_has_it and b.get("source") != "whatsapp"
                and state.mode in (AGENT, WAITING) and in_window
                and b.get("date") and b.get("time")):
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
