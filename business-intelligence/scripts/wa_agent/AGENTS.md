# wa_agent: conventions

The WhatsApp assistant. What it is and how to run it: [`README.md`](README.md).

- **The model proposes, the code disposes.** Claude returns a Proposal (reply,
  intent, confidence, escalate). Whether anything reaches a customer is decided
  in `policy.py` and `app.py`, never by the prompt. A new rule (hours, contacts,
  intents) goes in code with a test, not in `INSTRUCTIONS`.
- **The model never writes.** Its tools are read-only. Direct booking happens
  in code (`app._book_pending` → goji-booking `/internal/book`) only after the
  customer confirms, in a later message, the details stated back to them; the
  confirmation text is built from goji-booking's answer. Dry run until go-live
  (`WA_AGENT_BOOKING_DRY_RUN`). Changing or cancelling bookings stays with staff.
- **Never call Plato from here.** Availability comes from goji-booking's API,
  which serves its 5-minute snapshot. Plato allows 20 requests/min for the
  whole clinic (`booking/README.md`).
- **Facts come only from the website, plus `house_rules.md`.** `kb.py` builds
  the knowledge base from `marketing/website` at deploy time. A wrong price is
  fixed on the site, not in the prompt. A practice Chris confirms that doesn't
  belong on the site (physio isn't sold as packages) goes in `house_rules.md`,
  one dated line each. Service ids mirror `booking/config.py` (`test_tools.py` checks).
- **Patient lookup is keyed on the chat's own number.** The one exception,
  `find_booking` (no record for this number), needs the full name AND the
  booking's number to match the same patient, returns only the next
  appointment, and is capped at 3 tries per chat. A number alone or a name
  alone never reveals anything.
- **No message text or phone numbers in BigQuery.** `marts.wa_agent_events`
  uses a salted hash per chat. Transcripts live only in Firestore with a 30-day
  TTL. Don't add text columns.
- **Email Chris only when she must act.** Drafts, handovers, red flags,
  failures, demotions. A new `notify.send` for anything routine needs a reason
  she can't see it in the WhatsApp Business app.
- **Every failure becomes an escalation.** A model error, refusal, tool crash
  or send failure gives the customer a holding reply and emails a person. The
  customer is never left with silence.
- **No always-on CPU.** One idle instance (cold starts take ~19s, past Meta's
  ~5s webhook limit) with CPU only during requests: work runs inside Cloud
  Tasks requests (`tasks.py`, `/tasks/run`), never on a thread after a response
  when a queue is set. Anything scheduled (warms, summaries) is a task or a
  job, not a loop in the process.
- **One instance.** Per-chat locks are in-process (`--max-instances=1`). Moving
  to more instances needs the lock in Firestore first.
- **Its own service account** (`wa-agent-sa`): it holds chat transcripts, so it
  doesn't share dashboard-sa. Its only BigQuery write grant is on
  `marts.wa_agent_events` (set by `deploy.sh`, not the dashboard grant loops).
- **Same-day slots are WhatsApp-only.** Plato's online rule (`min_days`)
  hides today from the website, so the slot tools ask goji-booking for
  `same_day=1` with the internal token (60 min lead; booking the slot only
  rules out past times). Without that it told a customer "fully booked
  today" while the clinic had a slot free (24 Nov 2026). The public API
  refuses `same_day` without the token.
- **Getting worse is `priority`, sent and flagged at once.** Symptoms
  getting worse short of the 995 list (harder to walk, spreading numbness or
  weakness): calm, proportionate concern (never "sounds serious": owner),
  "I've let the team know", the earliest slots with today's first. The reply
  goes out and staff are pinged in the same step (`send_alert`, every stage);
  the chat stays with the agent so it can book. A reply that fails the check
  is a handover, never a draft.
- **Booking links use the `wa-book` go-link** (`dashboard/app.py` LINK_SLUGS),
  which forwards `service`/`focus` to `/book`.
- **Disclosure: don't lead with it, never hide it.** The agent introduces
  itself as Goji's front desk; asked whether it's a person, a bot or Chris, it
  says it's Goji's WhatsApp assistant. It never claims to be a named person.
- **Learning signals are labels, never text.** Draft similarity, rescues and
  ratings are worked out in `learning.py` when they happen, so BigQuery gets
  `draft_outcome` / `rescue` / `rating`, not the messages. Demotion (auto to
  draft) is automatic; promotion is a person's call and a code change.
- **Every request pays for the always-on prompt.** Keep `kb.build`'s core
  small (`test_kb.py` caps it); new content goes behind `read_page`. Build
  every request with `agent.request_kwargs` so the warm-up and real turns
  share one cached prefix.
- **Chris's time is for what needs a person.** Junk (`off_topic`) is
  answered and goes to the morning summary, never a ping; it persists past
  `OFF_TOPIC_LIMIT` and the number is watch-listed (`policy.note_off_topic`).
  Don't route something to Chris just because it's unusual.
- **A handover splits two messages.** The customer gets the model's
  `holding_reply` (acknowledges the ask, apologises if they're unhappy,
  promises nothing a person must decide); Chris's ping carries `reply`, the
  draft answer she can send or edit (`policy.customer_message`), written as
  the clinic answering with [brackets] for what only she knows, never "let me
  check with the team". A [bracket] in any customer-bound text is held
  (`reply_problems`: placeholder). Only red flags
  and sensitive topics send `reply` at once. A holding reply is checked like
  any reply; the generic line is only the fallback. (Before 23 Nov 2026 a model
  handover sent its holding message to the customer AND to Chris as her
  "suggestion", so she got nothing usable.)
- **Evals judge at the deployed stage.** `eval/scenarios.py` decides with
  `stage_policy` + `apply_stage` as `app.py` does, so a "draft" in a scenario
  is a handover from stage 1. Judging with the bare `INTENT_POLICY` hid that
  every low-confidence answer reaches Chris (23 Nov 2026).
- **Replies are checked in code** (`policy.reply_problems`): only Goji's own
  links, email and numbers (plus 995/1767), booking links only via the
  `wa-book` go-link, and gojiphysio.com page links only to pages the knowledge
  base has (`kb.site_paths`; a guessed URL is a 404). The agent links the
  page that answers a question (owner, 23 Nov 2026). Anything else is drafted, never sent.
- **The CLI backend is temporary** (`WA_AGENT_BACKEND=cli`, local testing on
  test numbers). Production is the Messages API. Keep both backends returning
  the same Proposal, and keep the CLI isolated (`--tools ""`,
  `--strict-mcp-config`, `--setting-sources ""`).
- **Paid vendor, flagged:** the WhatsApp provider (needed for coexistence) is
  this repo's one exception to "free / DIY first". Code speaks Cloud API
  payloads only, so the provider is a config change (`WA_API_BASE`, ...).
- **Chris stays primary.** Her writing in a chat pauses it until she resumes
  it (`RESUME <code>`); chats she had in the 30 days before go-live pause on
  their next message (`policy.pre_golive_chat`). Any new path that messages a
  customer (confirmations, reminders, pings) checks the kill switch, go-live
  and the chat's mode first.
- **Staff numbers are never customers.** `WA_AGENT_STAFF` messages go to
  `handle_staff` before any lookup, model call or metric; the numbers live in
  a private env file, never the repo. Pings name customers by first name or
  last 4 digits only.
