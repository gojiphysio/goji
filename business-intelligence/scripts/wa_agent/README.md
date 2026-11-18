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

Each chat is in one mode: `agent`, `human` or `paused` (`policy.py`).

| Goes to `human` (agent silent) | Goes back to `agent` |
|---|---|
| Chris writes in the chat from the app (`smb_message_echoes`) | 24h with no message from a person (`WA_AGENT_HUMAN_IDLE_S`) |
| The agent escalates (holding reply + email to hello@) | `POST /admin/chats/<id>/handback` |
| `POST /admin/chats/<id>/takeover` | |

`paused` only leaves by hand-back. Across all chats: `POST /admin/kill` and the
`WA_AGENT_KILL_SWITCH` env var. Contacts in `WA_AGENT_ALWAYS_HUMAN` are never
answered. `WA_AGENT_HOURS=after_hours` limits the agent to outside Mon-Sat
8am-8pm.

What happens to a proposal: `config.INTENT_POLICY` maps each intent to
auto / draft / escalate; below `WA_AGENT_MIN_CONFIDENCE` it's a draft. A reply
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
| Claude | < $20 | ~$15-60 (~$0.03-0.06 per inbound message; `cost_usd` in the events table is the real figure) |
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
reply with an untracked booking link. Cost note: the ~30K-token knowledge base
is a cache write (~$0.25) on the first message after an idle hour, so sporadic
traffic costs more than the per-message estimate; measure on the API.

### Track C: offline test set

Keep everything outside the repo; delete raw exports after redacting.

```bash
cd business-intelligence/scripts
python -m wa_agent.kb --site ../../marketing/website --out wa_agent/_build/kb.json
python -m wa_agent.eval.redact --in ~/goji-exports --out ~/goji-eval
# skim ~/goji-eval/chats.jsonl for anything the redactor missed, then:
ANTHROPIC_API_KEY=... python -m wa_agent.eval.replay \
    --cases ~/goji-eval/cases.jsonl --out ~/goji-eval/replay.csv --sample 30
```

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

## Tests

```bash
cd business-intelligence/scripts && python -m pytest wa_agent -q
```

No network: fakes stand in for Claude and WhatsApp (`tests/fakes.py`), the KB
is built from the repo's website content, and `test_tools.py` fails if the
service list drifts from `booking/config.py`.
