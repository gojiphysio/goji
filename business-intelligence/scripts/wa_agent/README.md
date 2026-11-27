# goji-wa-agent: the WhatsApp assistant

> **Status (23 Nov 2026):** deployed, not live, kill switch on; waiting to
> connect Goji's number through Dualhook. Checklist: [`GO_LIVE.md`](GO_LIVE.md).

Answers routine WhatsApp questions (prices, services, hours, availability,
booking links) on Goji's number, and hands everything else to Chris. Chris
keeps the WhatsApp Business app on her phone; the agent works the same chats
through the Cloud API (Meta's "coexistence") and steps back the moment she
replies.

Status: **Phase 0, prototype.** Runs on test numbers only. Nothing here touches
the clinic's real number until Phase 0's go / no-go.

```
Customer ──► Goji number ──┬─► Chris's WhatsApp Business app (unchanged)
                           └─► provider ─► POST /webhook (Cloud Run goji-wa-agent)
                                             ├ gate: kill switch, mode, contact, hours
                                             ├ agent.propose (Claude + read-only tools)
                                             │   find_available_dates / get_times ─► goji-booking snapshot
                                             │   booking_link ─► go.gojiphysio.com/wa-book
                                             │   read_page ─► website condition/blog pages
                                             │   my_appointments ─► BigQuery (off in Phase 0)
                                             ├ policy.decide ─► send | draft | escalate
                                             ├ hold, re-check for Chris / newer message, send
                                             ├ Firestore: chat mode + transcript (30-day TTL)
                                             └ BigQuery: marts.wa_agent_events (no text, no numbers)
```

Rules for changing this code: [`AGENTS.md`](AGENTS.md).

## How a chat is shared between the agent and Chris

Each chat is in one mode: `agent`, `waiting`, `human` or `paused` (`policy.py`).

| Goes to `waiting` (agent keeps answering, not the handed-over topic) | Goes to `human` (agent silent) | Goes back to `agent` |
|---|---|---|
| The agent hands a topic to Chris (holding reply + email to hello@) | A red flag (`urgent`) or `sensitive` handover | 24h with no message from a person (`WA_AGENT_HUMAN_IDLE_S`), only for the agent's own handovers |
| | `POST /admin/chats/<id>/takeover` | `POST /admin/chats/<id>/handback` |

Chris writing in a chat from the app (`smb_message_echoes`) pauses it: `paused`
leaves when she texts `RESUME <code>`, an admin hands it back (see Go-live
controls), or the customer writes 14 days or more after the last person's
message (`WA_AGENT_HUMAN_PAUSE_S`, `policy.apply_pause_expiry`; owner, 24 Nov
2026). That message goes to the agent like any other; nothing is sent before it.
`PAUSE <code>`, the admin pause and the watch list never lapse.

While `waiting`, the model is told what's with Chris (`pending_for_chris`, the
staff note), so it answers everything else but not that, says once that Chris
has it if asked, and adds any new topic for Chris to the list without a second
standby message (19 Nov 2026, Charles: a handover shouldn't stop the front desk).

`paused` leaves by hand-back, or by the 14-day lapse above. Across all chats: `POST /admin/kill` and the
`WA_AGENT_KILL_SWITCH` env var. Contacts in `WA_AGENT_ALWAYS_HUMAN` are never
answered. `WA_AGENT_HOURS=after_hours` limits the agent to outside Mon-Sat
8am-8pm.

What happens to a proposal: `config.INTENT_POLICY` maps each intent to
auto / auto_notify / draft / escalate; below `WA_AGENT_MIN_CONFIDENCE` (0.7) it's a
draft. Chris's routing (18-19 Nov): booking requests, appointment checks and
routine moves and cancellations (24h+ notice) are handled by the agent end to
end, with no email to Chris (a cancellation is done in the same turn, no
"shall I?"; the confirmation asks gently what came up, or answers the reason
they gave, and offers another time: owner, 24 Nov 2026); "is this Chris?" answers as the front desk
and asks for a message; billing, clinical and complaints are drafts she
checks, even if the model wanted to hand over; a reschedule or cancellation
less than 24 hours before the appointment (the site's cancellation policy) is
a draft, with the first-time fee waiver; asking for a person about something the agent can't handle,
sensitive topics and urgent red flags escalate with a holding reply.

**Long replies go out as 2 messages** (owner, 24 Nov 2026), the way Chris
writes: the opening line (greeting, or concern) first, then the substance.
`policy.split_bubbles` does it in code, at the first blank line, only for
replies of `WA_AGENT_SPLIT_MIN_WORDS` (60) words or more, never more than
`WA_AGENT_MAX_BUBBLES` (2); the prompt doesn't ask for it, so it doesn't nudge
replies longer. Meta bills each delivered service message past 1,000 a month
per number (since 1 Oct 2026, about US$0.016 each in Singapore), so this is
capped: about +$15/month at the 24 Nov volume. `WA_AGENT_MAX_BUBBLES=1` turns
it off. (Walked back on 19 Nov over the same pricing, before it was costed.)

**Chris gets an email only when she has to act** (Charles, 19 Nov: "only if it
gets escalated"): a draft to check, a handover, a red flag or sensitive
handover, a failed booking or move, an intent demoted to drafts, or a waiver
tag the agent couldn't place. Never for routine bookings, moves, appointment
checks, photos or documents (she sees those in the WhatsApp Business app). A reply
that will be sent waits until `WA_AGENT_PRE_SEND_HOLD_S` (20s) after the
customer's message arrived, then sends only if no person wrote in the chat and
no newer customer message came in meanwhile (that message's own run answers
both). Drafts and escalations email hello@ (`notify.py`).

## Phase 0 plan (about 2 weeks)

Three questions to answer before Chris's real number is connected: is Plato
availability right, is it fast enough, and does takeover work.

**Track A, days 1-4: whole flow on Meta's free test number.** Up to 5 tester
phones. Proves availability reads, booking links, escalation emails, admin
takeover, and latency (target p50 < 6s, p90 < 12s for `agent_ms`; `e2e_ms`
adds the deliberate 20s hold). About 50 scripted messages.

**Track B, days 3-10: real takeover on a spare number.** Prepaid SG SIM + spare
Android phone with the WhatsApp Business app ("Goji Test"), connected with
coexistence through free trials of two providers (shortlist: Dualhook,
360dialog). One hour with Chris:

| # | Scenario | Pass |
|---|---|---|
| 1 | Chris replies first from her phone | agent silent in that chat for 24h |
| 2 | Chris and agent reply within seconds | pre-send re-check catches it, no double reply |
| 3 | Chris replies from WhatsApp Web/Desktop | find out if an echo arrives; if not, rule is "phone or admin takeover" |
| 4 | Customer asks for a person / sends a red flag | holding reply + email within 30s |
| 5 | Chris goes quiet past the timeout | agent resumes; hand-back works |
| 6 | Kill switch | agent stops within one message |

**Track C, days 1-8: offline test set from real chats.** Chris exports about 50
chats; `eval/redact.py` strips names and numbers; `eval/replay.py` runs the
agent over each customer turn and writes a grading sheet next to Chris's real
reply. Chris grades about 30 (good / ok / wrong / unsafe).

**Go / no-go:** ≥ 90% good-or-ok on auto-send intents and **zero unsafe**;
latency targets met; echoes arrive in 100% of Track B phone tests; provider
chosen.

**Things to confirm against real traffic** (coded from docs, not yet seen live):
the `smb_message_echoes` payload shape, the typing indicator, whether each
provider forwards Meta's signature (if not: `USE_URL_TOKEN=1`, below), and the
24h service window behaviour after an escalation.

### Costs (estimates; volume assumed ~40 inbound messages/day)

| | Phase 0 | Running, per month |
|---|---|---|
| Provider | $0 (trials) | $12 (Dualhook) to ~$55 (360dialog) |
| Meta | $0 | first 1,000 service replies free per number, then the SG service rate (since 1 Oct 2026) |
| Claude | < $20 | ~$25-35 at ~$0.02-0.03 per message after the cost controls below (`cost_usd` in the events table is the real figure) |
| Cloud Run (one idle instance, CPU billed only during requests; work runs inside Cloud Tasks requests) + Cloud Tasks + Firestore | ~$5-10 | ~$5-10 (always-on CPU would be ~$45; zero instances means 19s cold starts, past Meta's ~5s webhook limit) |
| SIM + spare phone | S$15, + up to S$150 | - |

### Lead times (start now)

| Item | Who | Lead time |
|---|---|---|
| Admin on Goji's Meta Business Portfolio | Charles | same day |
| Meta developer app + test number | Charles + agent | same day |
| Anthropic API key (Goji workspace) | Charles | same day |
| Zero data retention request to Anthropic | Charles | unknown: ask now |
| Chat exports | Chris | 30 min |
| SIM, spare phone, 2 provider trials | Charles | 1-2 days |
| Meta business verification (Goji Health Pte. Ltd.) | Charles | 2-5 business days |
| Provider contract + DPA | Charles | 1-2 weeks |
| Privacy policy line on AI-assisted replies | draft here, Charles approves | 1 day |

## Go-live controls (built 19 Nov 2026)

**Chris stays primary** (Chris, 19 Nov 2026).

- *Chris writes in a chat → the assistant is fully silent there* (mode
  `paused`, no 24h idle hand-back) until she resumes it, or until the
  customer writes 14+ days after her last message (owner, 24 Nov 2026). The
  idle hand-back is only for handovers the assistant made that nobody answered.
- *Resume over WhatsApp.* Every chat has a short code (`#004`) shown in pings,
  the STATUS reply and the morning summary, which lists every paused chat.
  Chris texts `RESUME 004` (or `PAUSE 004`) to the Goji number from her phone.
  Resuming sends the customer nothing: the assistant just answers their next
  message. The admin hand-back route does the same.
- *Answer through the assistant* (owner, 24 Nov 2026). Once the team has the
  answer, Chris swipe-replies to the ping with it (or texts `ANSWER 004 ...`).
  The assistant writes it up, sends it, looks after the chat again and shows
  her what it sent. If the answer only covers part of what the customer
  asked, the chat stays waiting on the rest. Nothing is sent if it isn't an
  answer for that chat, the write-up fails the reply check, the assistant is
  stopped, or the customer's last message was over a day ago (only the
  Business app can message them then).
- *Off-topic never reaches Chris* (owner, 23 Nov 2026). Wrong numbers,
  unrelated questions, attempts to misuse the chat and cold sales pitches
  (intent `off_topic`) get a short front-desk reply whatever the confidence,
  and no ping: they're listed in the morning summary. After
  `WA_AGENT_OFF_TOPIC_LIMIT` (3) off-topic messages in a row the chat is
  paused on the watch list (`mode_reason` `watchlist`, kept 365 days like any
  pause): no replies and no model calls. The summary lists newly watched chats
  with their code, so `RESUME 004` brings back a real customer. Partnerships,
  press and jobs are not off-topic; they still go to Chris.
- *Go-live cut-off.* Go-live is a moment someone sets (`POST /admin/go-live`;
  `WA_AGENT_GO_LIVE` is the fallback). Until then a deployed service answers
  nobody and only records message times (`not_live`). At go-live, a chat with
  a message from either side in the `WA_AGENT_GOLIVE_LOOKBACK_DAYS` (30) before
  go-live is Chris's: its next message pauses it (`pre_golive_chat`), so it
  stays hers however long it then goes quiet. A chat whose last message was
  over 30 days before go-live, or that starts after it, is the assistant's.

The times before go-live come from the webhook once the number is connected
and from Meta's coexistence `history` webhook (subscribe the field), which
`whatsapp.parse_history` reduces to timestamps per customer, never text.
`history_imported` is set when the import reports 100% (shown by
`GET /admin/rollout`); set go-live after it. The history payload shape is
coded from Meta's docs: check it against the real import when Goji's number
is onboarded.

**Rollout stages** (`WA_AGENT_STAGE` 0-3, `config.stage_policy`). No stage
drafts (owner's call: the assistant drives by itself).

| Stage | Answers itself | Everything else |
|---|---|---|
| 0 | greeting, faq, pricing, location/hours, availability, service fit, person check, media, booking | left to Chris silently (`stage_leave`); red flags still get the 995/A&E reply and alert staff; failures still alert |
| 1 | as stage 0 | handover with a holding reply |
| 2 | + appointment checks and moves | handover with a holding reply |
| 3 | today's policy | today's drafts become handovers |
| unset | today's policy, drafts included (local testing) | |

`WA_AGENT_CONTACT_SCOPE=new_only` also leaves out any number with a patient
record or an earlier chat (`out_of_scope`); `quiet` (default) is the go-live
cut-off and paused chats alone. Stage, scope and hours live in the Firestore flags doc `rollout`
(`GET/POST /admin/rollout`, null = back to env), so a redeploy can't reset
them. Demotion still applies on top.

**Staff on WhatsApp.** `WA_AGENT_STAFF` lists staff personal numbers (kept in
`~/.config/goji-wa-agent/prod.env`, never the repo). Their messages never go
through the customer flow: `handle_staff` answers `stop` (kill switch on),
`start` (off) and `status` (switch, stage, chats waiting today), anything else
gets a help line, and every message opens that number's 24h window. Handovers,
red flags, sensitive topics, failed bookings and moves, demotions and the
waiver-tag request ping each staff number: free text inside their window, the
approved `goji_staff_alert_v2` template outside it (v1 was recategorised as marketing) (`WA_AGENT_STAFF_TEMPLATE`).
A ping names the customer by first name or last 4 digits, plus the chat code. Email stays
the backup for red flags and sensitive topics, and the only channel when no
staff number is set or a ping failed. Drafts (unset stage only) still email.

**Morning summary.** A Cloud Run job, scheduled 07:30 SGT by `deploy.sh`, calls
`POST /internal/morning-summary` (admin token): an email to hello@ with what
the assistant answered, what it left or handed to Chris (until she replies)
and any failures, from each chat's `outcomes` (`summary.py`); a one-line
version goes to staff whose window is open.

**Also:** the reminder Confirm tap and booking confirmations respect the kill
switch, go-live and paused chats; a deployed run without `WA_AGENT_HASH_SALT`
records events with no `chat_key` (the public default salt would make them
reversible) and logs an error at startup; `POST /admin/chats/<id>/forget`
deletes a chat and its late-change record (PDPA).

## Runbook

### Track A: Meta test number

1. developers.facebook.com → Create app → type **Business** → attach Goji's
   business portfolio → add the **WhatsApp** product. API Setup shows a test
   number and its **Phone number ID**; add up to 5 recipient phones there.
2. Business settings → System users → add one (admin) → assign the app →
   generate a token with `whatsapp_business_messaging` and
   `whatsapp_business_management`. That's `wa-token` (the API Setup token
   expires in 24h). App settings → Basic → **App secret** is `wa-app-secret`.
3. Create the secrets listed at the top of `deploy.sh`, then from the repo root:
   `WA_PHONE_NUMBER_ID=<id> bash business-intelligence/scripts/wa_agent/deploy.sh`
4. Meta app → WhatsApp → Configuration → Webhook: callback URL printed by the
   deploy, verify token = `wa-verify-token`. Subscribe **messages**.
5. From a tester phone, message the test number. (Meta requires the business
   to send `hello_world` to a new tester first; API Setup has the button.)
6. Watch it: `gcloud run services logs tail goji-wa-agent --region asia-southeast1`

Admin calls (`$T` = the admin token, `$U` = service URL, numbers in E.164 digits):

```bash
curl -s -H "X-Admin-Token: $T" $U/admin/chats/6591234567           # mode + transcript
curl -s -XPOST -H "X-Admin-Token: $T" $U/admin/chats/6591234567/takeover
curl -s -XPOST -H "X-Admin-Token: $T" $U/admin/chats/6591234567/handback
curl -s -XPOST -H "X-Admin-Token: $T" -H 'Content-Type: application/json' \
     -d '{"on": true}' $U/admin/kill
```

### Track B: coexistence through a provider

1. Spare phone: install WhatsApp Business (app ≥ 2.24.17), register the SIM's
   number, business name "Goji Test".
2. In the provider's trial, connect an **existing WhatsApp Business app number**
   (coexistence / Embedded Signup); scan the QR from the phone.
3. Point the provider's webhook at the service: Dualhook-style (Meta's webhook
   forwarded as is) → `/webhook`; providers without Meta's signature →
   `USE_URL_TOKEN=1` and `/webhook/<wa-webhook-url-token>`.
4. Transport env for the deploy, e.g. 360dialog-style:
   `WA_API_BASE=https://waba-v2.360dialog.io WA_SEND_PATH=/messages WA_AUTH_HEADER=D360-API-KEY WA_AUTH_PREFIX=`
   (`wa-token` = the provider's key). Check each provider's docs for the exact values.
5. Subscribe **messages** and **smb_message_echoes**. Run the six scenarios.
6. **Before go-live on Goji's real number:** turn off the WhatsApp Business
   app's automatic replies on Chris's phone (Settings → Business tools →
   Away message, and Greeting message). The current away message ("👋 Thank you
   for your interest… We're not available right now…") comes from the app, not
   from Meta's API or Plato, and fires mid-conversation even while Chris is
   replying. Left on, customers get it as well as the assistant's reply.

### Testing with the Claude CLI instead of the API (temporary)

Until the Goji API key is set up, `WA_AGENT_BACKEND=cli` runs the agent through
the local `claude -p`, logged in as you (`cli_backend.py`). Same instructions,
knowledge base, tools (served over MCP by `mcp_server.py`), schema and policy.
The CLI is isolated: no built-in tools, no settings/skills/CLAUDE.md, only our
MCP server. **Local only and test numbers only:** a personal subscription is
not for answering real customers, and the image doesn't ship the CLI. Latency
includes CLI start-up and cost is the CLI's list-price estimate, so re-measure
both on the API.

```bash
cd business-intelligence/scripts
python -m wa_agent.kb --site ../../marketing/website --out wa_agent/_build/kb.json
# offline replay (Track C) through the CLI:
WA_AGENT_BACKEND=cli python -m wa_agent.eval.replay --cases ~/goji-eval/cases.jsonl \
    --out ~/goji-eval/replay.csv --sample 30
# live test number (Track A) from a laptop: run the service, expose it, and
# point Meta's webhook at https://<tunnel>/webhook
WA_AGENT_BACKEND=cli WA_AGENT_STATE=memory WA_AGENT_LOG_EVENTS=false \
WA_PHONE_NUMBER_ID=... WA_TOKEN=... WA_APP_SECRET=... WA_VERIFY_TOKEN=... \
WA_AGENT_ADMIN_TOKEN=... gunicorn -w 1 --threads 8 -b :8080 wa_agent.app:app
cloudflared tunnel --url http://localhost:8080      # free quick tunnel
```

First live run (18 Nov 2026, 5 messages): prices, referral and Medisave answers
correct; real availability offered with clinicians; a pregnancy red flag got
995/A&E and an urgent escalation; a prompt injection was declined; a
reschedule was handed over. Each reply took 6-11s. One fix came out of it: the
model wrote the raw `/book` URL once, so `policy.reply_problems` now drafts any
reply with an untracked booking link. That run cost ~$0.38 a message, almost
all of it the ~30K-token knowledge base written to the prompt cache.

### Cost controls (and what they measured)

| Control | Where |
|---|---|
| Compact always-on knowledge base (~7K tokens: llms.txt, one line per service, clinician summaries, page index); full pages via `read_page` | `kb.py` |
| Keep the 1-hour cache warm 7am-10pm SGT when real traffic hasn't (identical request, `max_tokens=1`: `max_tokens=0` is rejected with structured outputs) | `agent.warm_cache`, `app._keep_warm`, `WA_AGENT_KEEP_WARM` |
| Debounce: wait `WA_AGENT_DEBOUNCE_S` (6s) so a burst of lines is one model run | `app.handle_inbound` |
| `next_slots`: next open times across days in one tool call | `tools.py` |
| Bare "ok" / "thanks" / 👍 after our reply: no model call | `policy.is_acknowledgement` |

Re-run on the CLI (same 5 kinds of message, in sequence): **$0.048 a message on
average**, first message $0.13 (cold cache), then $0.017-0.04; 5.5-8.3s each;
availability in one `next_slots` call. Still to try: the same test set on
cheaper models, judged by Chris's grades (a product decision, not a default).

### Track C: offline test set

Keep everything outside the repo, in `~/goji-eval/` (`chmod 700`); delete raw
exports once you no longer need to rebuild.

Layout: one folder per category under `~/goji-eval/chats/` (e.g.
`new-enquiries/`, `regular/`, `rescheduling/`, `sensitive-doctors-referral/`),
each export's `.zip` (an unzipped copy beside it is counted once). The folder
becomes each chat's `category`; doctor-referral (partner) chats are marked
`b2b` and replay skips them unless `--include-b2b`. Names the patterns miss
go in `~/goji-eval/extra_names.txt`, one per line.

How to rebuild and re-run:

```bash
cd business-intelligence/scripts
python -m wa_agent.kb --site ../../marketing/website --out wa_agent/_build/kb.json
python -m wa_agent.eval.redact --in ~/goji-eval/chats --out ~/goji-eval \
    --extra-names ~/goji-eval/extra_names.txt
chmod 600 ~/goji-eval/*.jsonl
# skim ~/goji-eval/chats.jsonl for anything the redactor missed, then
# (API: ANTHROPIC_API_KEY=...; or locally through the CLI as here):
WA_AGENT_BACKEND=cli WA_AGENT_STATE=memory WA_AGENT_LOG_EVENTS=false \
python -m wa_agent.eval.replay --cases ~/goji-eval/cases.jsonl \
    --out ~/goji-eval/replay.csv --sample 25    # stratified by category, seeded
# narrower: --category new-enquiries   all cases: drop --sample
```

The sheet has `ai_grade`/`ai_note` (first pass) and `grade`/`notes` (Chris).

### Scenario suite (behaviour tests)

`eval/scenarios.py`: 92 scripted conversations against the real model with
automatic pass/fail checks (intent, policy decision, required and forbidden
phrases, one question per message, no repeat greeting or booking link, word
caps). Groups: new enquiry, returning patient, booking, reschedule/cancel,
handover, clinical (incl. red flags), malicious, media, and handoff (long
conversations where the right call changes partway through, plus judgement
calls marked "judgement:" for the owner to rule on). Made-up people only.

Decisions are judged at the stage the service runs (`WA_AGENT_STAGE`, else 2),
the way `app.py` does it: from stage 1 a draft is a handover with the holding
reply. The conversation is played as it would be live: only replies that would
go out stay in the history, and a handover puts the chat in `waiting` (later
turns see "waiting for Chris on: ...") or, for a red flag or sensitive topic,
silences the rest. `at={n: Expect(...)}` checks a middle turn.

Run it after any change to the instructions, policy or knowledge base:

```bash
WA_AGENT_BACKEND=cli python -m wa_agent.eval.scenarios --jobs 4 \
  --out ~/goji-eval/scenarios.csv --turns-out ~/goji-eval/turns.csv     # one row per turn, decision at 0.5-0.9
WA_AGENT_BACKEND=cli python -m wa_agent.eval.scenarios --only booking   # one group
WA_AGENT_BACKEND=cli python -m wa_agent.eval.scenarios --stage none        # the unstaged policy (drafts)
```

Use the CLI backend (subscription), not the API key, for evals. `--turns-out` gives each turn's confidence and what would happen at each
`WA_AGENT_MIN_CONFIDENCE` from 0.5 to 0.9, for choosing the threshold. Later
turns are judged on the earlier turns' outcomes at the current threshold.

When a real chat goes wrong, add it here as a scenario (made-up details) so
it stays fixed.

### Readout (BigQuery)

```sql
-- latency and cost per turn
SELECT decision, outcome, COUNT(*) n,
       APPROX_QUANTILES(agent_ms, 10)[OFFSET(5)] p50_ms,
       APPROX_QUANTILES(agent_ms, 10)[OFFSET(9)] p90_ms,
       ROUND(SUM(cost_usd), 2) cost
FROM `goji-bi.marts.wa_agent_turns`
WHERE proposed_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY 1, 2 ORDER BY n DESC;

-- takeovers and hand-backs
SELECT reason, mode_to, COUNT(*) FROM `goji-bi.marts.wa_agent_events`
WHERE event = 'mode' GROUP BY 1, 2;
```

The dashboard's Agent page reads the two views below.

## Direct booking (built 19 Nov 2026, dry run until go-live)

The agent books new appointments in the chat. The model never books:
1. It checks the slot (`get_times`), collects service, date, time, clinic or
   home (+ address) and full name (phone = the chat; **email optional** for
   WhatsApp bookings), states it back and fills `booking` in its proposal.
   The service stores it as the chat's `pending_booking`.
2. Only when the customer confirms in a **later** message (`confirm_booking`)
   does `app._book_pending` call `booking_client.book`, which posts the stated
   details to goji-booking's private `/internal/book` (shared token
   `wa-agent-internal-token`; the website's `/api/book` bot checks can't be
   passed by a server). A pending booking expires after 30 minutes.
3. The confirmation the customer sees is built in code from goji-booking's
   answer (`confirmation_text`), so it can't claim a booking that didn't happen.
   A taken slot gets an apology and Chris an email.

**Booking for someone else** (a husband for his wife, a parent for a child):
the agent asks the patient's own full name (and a child's age) and books under
it, with the texter's number as the contact; the Plato note says who booked.
The appointment is linked to the patient's own record when one exists on the
number in their name (`tools.record_for_booking`), never the texter's record by
phone. A new patient gets no record (since 26 Nov 2026, like a website
booking): the confirmation and the 48-hour reminder send them Plato's
pre-registration form, which creates the profile and links the appointment.
`my_appointments` finds these unlinked bookings by the number on them.

**Dry run by default** (`WA_AGENT_BOOKING_DRY_RUN`, deploy sets 1): goji-booking
validates and checks the slot but writes nothing to Plato, and the
confirmation says so. Set it to 0 at go-live. `WA_AGENT_BOOKING_SIMULATE=1`
(local only) checks the slot against the public availability API instead,
for testing before goji-booking has the private route.

**Without an email**, WhatsApp does email's jobs: the confirmation is in the
chat; pre-registration links go in the chat; the 48-hour reminder needs an
approved WhatsApp utility template from the clinic number (per-message fee,
needs coexistence). Until then the reminder job's digest lists no-email
patients for a manual WhatsApp. goji-booking skips Plato's portal invite
without an email.

## Booking confirmations in the chat (built 19 Nov 2026)

goji-booking calls `POST /internal/booking-confirmed` (same token) after every
real booking, website or agent. The service matches the booking's phone to a
chat; for a website booking inside the 24-hour window it says "Thanks for
booking! You're all set for ..." in the chat. Either way the chat's `booked`
note tells the model not to offer times for it again, and the learning loop
records `booked` straight away. Needs goji-booking's `WA_AGENT_URL`.

## Late changes and the first-time fee waiver (built 19 Nov 2026)

Plato deletes cancellations, so late-change history is built from go-live:
- **System of record: the Plato patient tag "Late change waiver used".** It's
  on the patient (not a phone number), staff see it in Plato, and the nightly
  patient sync copies tags to `marts.dim_patient`, which the patient lookup
  reads. Not Plato notes: those are the clinical record.
- **Who writes it:** when Chris sends the agent's late-change draft that
  waives the fee unchanged, the service asks goji-booking to add the tag
  (`POST /internal/patient-tag`, allowlisted tags only, reads the current tags
  and writes them back with the new one). If several patients share the number,
  or there's no record, Chris gets an email to tag the right patient herself.
  If she edits the draft, the decision (and the tag) is hers.
- **Cache:** the service also records each late change against the chat's
  hash (`wa_agent_late_changes`, dates and hours of notice only), which covers
  the gap until the nightly sync and people who aren't patients yet.
- Dry run while bookings are (`WA_AGENT_BOOKING_DRY_RUN`): goji-booking reads
  the patient but doesn't write the tag.

## Appointment confirmations and reminders on WhatsApp

All four templates are approved on Goji's number (checked 25 Nov 2026):
`goji_appointment_confirmed` (name, service, date and time, clinician, plus a
"Get directions" button), `goji_appointment_reminder` (same fields, Confirm
and Reschedule quick replies), `goji_referral_received`, `goji_staff_alert_v2`.

- **New Maps link pending:** `goji_appointment_confirmed_v2` (same wording,
  "Get directions" to the clinic's chosen Maps link,
  https://maps.app.goo.gl/Mm3eYLNMUwwx8USv8) was submitted to Meta on
  25 Nov 2026. Once approved, switch with
  `gcloud run services update goji-wa-agent --update-env-vars
  WA_AGENT_CONFIRM_TEMPLATE=goji_appointment_confirmed_v2` (the deploy carries
  env vars forward). Same four parameters, so no code change.
- **Registration-form versions pending:** `goji_appointment_confirmed_form`
  and `goji_appointment_reminder_form` (submitted 25 Nov 2026) add a
  "Registration form" URL button for patients who haven't filled in Plato's
  form; its URL ends in goji-booking's signed form token. Once approved: set
  `WA_AGENT_CONFIRM_FORM_TEMPLATE=goji_appointment_confirmed_form` on the
  agent (`gcloud run services update ... --update-env-vars`) and the repo
  variable `WA_REMINDER_FORM_TEMPLATE=goji_appointment_reminder_form` (read at
  the reminder job's deploy).
- **Home visits** get their own confirmation, with no "📍 Lentor Modern" or
  Get directions button (owner, 27 Nov 2026): `goji_home_visit_confirmed`
  and `goji_home_visit_confirmed_form` (name, date and time, clinician; no
  service), submitted 27 Nov 2026. goji-booking puts `home` on the
  booking-confirmed callback. Until they're approved and set
  (`WA_AGENT_CONFIRM_HOME_TEMPLATE`, `WA_AGENT_CONFIRM_HOME_FORM_TEMPLATE`), a
  home visit gets no WhatsApp template, only the email.
- **Confirmations** go live with goji-booking's confirmation email: goji-booking
  puts `send_template: true` on the booking-confirmed callback only when
  `CONFIRMATIONS_MODE=live`, and the agent sends the template only then
  (`WA_AGENT_CONFIRMATIONS`, default on, is the agent-side off switch). It
  covers website bookings and, since 25 Nov 2026, front-desk bookings
  (`source: "staff"`, from goji-booking's Plato webhook and sweep), for a
  number with no chat in the last 24 hours. Inside the window a website or
  front-desk booking gets the free-form acknowledgement; chat bookings are
  confirmed in the chat. Kill switch, go-live and Chris's paused chats stop
  all of it.
- **Reminders:** the reminders job (`reminders/README.md`) sends
  `goji_appointment_reminder` alongside the reminder email, except to a
  patient who has already confirmed and has an email. A Confirm tap gets a
  thank-you with no model call and marks the appointment Confirmed in Plato
  (goji-booking `/internal/confirm`); Reschedule goes to the agent's move flow.
- **Opt-in:** the website booking form says, by default, that Goji may send
  the confirmation and reminders on WhatsApp (Meta needs opt-in naming the
  business). Chat bookings: the customer messaged us, and the confirmation
  says a reminder will follow. Front-desk bookings: existing patients who
  gave the clinic their number.

## Returning-patient recognition (built 19 Nov 2026)

`tools.patient_context` + `app._patient_for`, cached on the chat for 6 hours; on with
`WA_AGENT_PATIENT_LOOKUP=1`. `WA_AGENT_TEST_PATIENTS` (JSON, local only) gives
test numbers a made-up record. If several patients share a number (a parent
and children) the agent is told so and doesn't assume who's writing.


- **Lookup at the start of each conversation, in code**: match the chat's own
  number to the patient records (`dim_patient_contact`, as `my_appointments`
  does). The agent gets "returning patient, first name, next appointment, last
  visit date". `_LOOKUP_SQL` only covers upcoming appointments, so the last
  visit date needs a small query change. Never past clinical notes, and never
  anyone else's number.
- **Warm greeting**: "Hi Sarah! Good to hear from you again", with nothing
  clinical unless the patient raises it.
- **Turn on the lookup** (`WA_AGENT_PATIENT_LOOKUP`, off today) once the
  service has BigQuery access (`wa-agent-sa`).
- **Testing**: first a test-only stand-in that returns a made-up patient for
  the two test numbers, to check the greeting and tone. Then one end-to-end
  test against real data before go-live, with a test patient in Plato.

## Learning loop

Every conversation is scored by how it ended, and a change to the agent
(instructions, knowledge base, policy) is kept only if it does better. The
model isn't retrained; what improves is everything around it.

**Scoring** (`marts.wa_agent_conversations`, one row per conversation: a
customer message after 24h of quiet starts one):

| Outcome | Score |
|---|---|
| booked (through the agent's `wa-book` link, within 7 days) | success |
| resolved (agent answered, no person needed) | success |
| handover (policy escalation), draft_sent (Chris sent the draft unchanged) | neutral |
| rescued (Chris stepped into a chat the agent was answering), draft_edited, asked_for_human, unanswered (draft nobody replied to) | failure |
| dropped (agent gave times and the link, no booking) | soft failure |

**Signals** (`learning.py`, worked out when they happen so only labels reach
BigQuery): how close Chris's reply was to the agent's draft; whether her
message rescued an auto-handled chat; her 👍/👎 from the staff email
(`/feedback`, signed links; needs `WA_AGENT_PUBLIC_URL`); and bookings, via
`?ref=<chat_key>` on the booking link, logged by the links service
(`link_click_events.chat_ref`) and joined through `/book?cid=`.

**What uses the scores**
- The dashboard's Agent page: pure-agent success rate, rescue rate, bookings,
  first reply time, cost, outcome mix, and autonomy by intent
  (`marts.wa_agent_intent_autonomy`).
- Automatic demotion: an intent with 3 rescues in its last 20 auto-sent
  replies drafts instead of sending, and Chris gets an email. Only a person
  turns it back (`POST /admin/autonomy/<intent>/promote`), because draft to auto
  is the risky direction.
- Promotion: an intent whose drafts Chris sends unchanged (90% of at least 20)
  shows "ready to promote" on the dashboard. Promoting it is a change to
  `config.INTENT_POLICY` with a test.
- Regression set: failures and Chris's edits become Track C replay cases (names
  and numbers removed before the 30-day transcript expiry). A change must
  match or beat the previous version on them before it merges.
- Weekly review (to set up once live): a scheduled agent reads the week's
  failures and opens a PR with the fix and its replay score.

**Tester commands from WhatsApp** (any number on a local run; on a deployed
service only numbers in `WA_AGENT_TESTERS`): `/reset` forgets the chat
(transcript, mode, pending bookings, cached patient record, late changes) so
the next message starts fresh; `/turbo` (or `/turbo off`) drops the 20s
pre-send hold and shortens the debounce to 1.5s for the whole service.
`WA_AGENT_TURBO=1` starts a local run in turbo. Never turbo with real
customers: the hold is what lets Chris reply first.

**Battle testing on the test number** (no email locally): add
`WA_AGENT_TEST_SHOW_DRAFTS=1` with `WA_AGENT_STATE=memory`, and drafts and
handover notices are also sent to the tester, marked 🧪 TEST MODE. They're
never stored in the transcript, and the flag does nothing on a deployed
service.

## Tests

```bash
cd business-intelligence/scripts && python -m pytest wa_agent -q
```

No network: fakes stand in for Claude and WhatsApp (`tests/fakes.py`), the KB
is built from the repo's website content, and `test_tools.py` fails if the
service list drifts from `booking/config.py`.
