# goji-wa-agent: the WhatsApp assistant

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
| The agent hands a topic to Chris (holding reply + email to hello@) | Chris writes in the chat from the app (`smb_message_echoes`) | 24h with no message from a person (`WA_AGENT_HUMAN_IDLE_S`) |
| | A red flag (`urgent`) or `sensitive` handover | `POST /admin/chats/<id>/handback` |
| | `POST /admin/chats/<id>/takeover` | |

While `waiting`, the model is told what's with Chris (`pending_for_chris`, the
staff note), so it answers everything else but not that, says once that Chris
has it if asked, and adds any new topic for Chris to the list without a second
standby message (19 Nov 2026, Charles: a handover shouldn't stop the front desk).

`paused` only leaves by hand-back. Across all chats: `POST /admin/kill` and the
`WA_AGENT_KILL_SWITCH` env var. Contacts in `WA_AGENT_ALWAYS_HUMAN` are never
answered. `WA_AGENT_HOURS=after_hours` limits the agent to outside Mon-Sat
8am-8pm.

What happens to a proposal: `config.INTENT_POLICY` maps each intent to
auto / auto_notify / draft / escalate; below `WA_AGENT_MIN_CONFIDENCE` it's a
draft. Chris's routing (18 Nov): booking requests send on their own;
rescheduling sends new times and emails Chris to move the booking (the agent
can't change appointments); "is this Chris?" answers as the front desk and
sends her an FYI; cancelling, billing, clinical and complaints are drafts she
checks, even if the model wanted to hand over; a reschedule less than 24
hours before the appointment (the site's cancellation policy) is a draft, and
late-change drafts waive the $50 fee as a first-time courtesy for Chris to
keep or remove; asking for a person, sensitive
topics and urgent red flags escalate with a holding reply. A reply
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
| Cloud Run (1 warm instance, CPU always on) + Firestore | ~$5 | ~$5-10 |
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
