# wa_agent: conventions

The WhatsApp assistant. What it is and how to run it: [`README.md`](README.md).

- **The model proposes, the code disposes.** Claude returns a Proposal (reply,
  intent, confidence, escalate). Whether anything reaches a customer is decided
  in `policy.py` and `app.py`, never by the prompt. A new rule (hours, contacts,
  intents) goes in code with a test, not in `INSTRUCTIONS`.
- **Tools are read-only.** Nothing the agent can call books, cancels or edits.
  Writing tools (direct booking, rescheduling) are a Phase 3 decision and need
  their own gate in `policy.py`.
- **Never call Plato from here.** Availability comes from goji-booking's API,
  which serves its 5-minute snapshot. Plato allows 20 requests/min for the
  whole clinic (`booking/README.md`).
- **Facts come only from the website.** `kb.py` builds the knowledge base from
  `marketing/website` at deploy time. A wrong price is fixed on the site, not in
  the prompt. Service ids mirror `booking/config.py` (`test_tools.py` checks).
- **Patient lookup is keyed on the chat's own number**, never on a number in
  the conversation, so a customer only ever sees their own appointments.
- **No message text or phone numbers in BigQuery.** `marts.wa_agent_events`
  uses a salted hash per chat. Transcripts live only in Firestore with a 30-day
  TTL. Don't add text columns.
- **Every failure becomes an escalation.** A model error, refusal, tool crash
  or send failure gives the customer a holding reply and emails a person. The
  customer is never left with silence.
- **One instance.** Per-chat locks are in-process (`--max-instances=1`). Moving
  to more instances needs the lock in Firestore first.
- **Its own service account** (`wa-agent-sa`): it holds chat transcripts, so it
  doesn't share dashboard-sa. Its only BigQuery write grant is on
  `marts.wa_agent_events` (set by `deploy.sh`, not the dashboard grant loops).
- **Booking links use the `wa-book` go-link** (`dashboard/app.py` LINK_SLUGS),
  which forwards `service`/`focus` to `/book`.
- **Learning signals are labels, never text.** Draft similarity, rescues and
  ratings are worked out in `learning.py` when they happen, so BigQuery gets
  `draft_outcome` / `rescue` / `rating`, not the messages. Demotion (auto to
  draft) is automatic; promotion is a person's call and a code change.
- **Every request pays for the always-on prompt.** Keep `kb.build`'s core
  small (`test_kb.py` caps it); new content goes behind `read_page`. Build
  every request with `agent.request_kwargs` so the warm-up and real turns
  share one cached prefix.
- **Replies are checked in code** (`policy.reply_problems`): only Goji's own
  links, email and numbers (plus 995/1767), and booking links only via the
  `wa-book` go-link. Anything else is drafted, never sent.
- **The CLI backend is temporary** (`WA_AGENT_BACKEND=cli`, local testing on
  test numbers). Production is the Messages API. Keep both backends returning
  the same Proposal, and keep the CLI isolated (`--tools ""`,
  `--strict-mcp-config`, `--setting-sources ""`).
- **Paid vendor, flagged:** the WhatsApp provider (needed for coexistence) is
  this repo's one exception to "free / DIY first". Code speaks Cloud API
  payloads only, so the provider is a config change (`WA_API_BASE`, ...).
