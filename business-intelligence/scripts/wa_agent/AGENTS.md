# wa_agent: conventions

The WhatsApp assistant. What it is and how to run it: [`README.md`](README.md).

- **The model proposes, the code disposes.** Claude returns a Proposal (reply,
  intent, confidence, escalate). Whether anything reaches a customer is decided
  in `policy.py` and `app.py`, never by the prompt. A new rule (hours, contacts,
  intents) goes in code with a test, not in `INSTRUCTIONS`.
- **The model never writes.** Its tools are read-only. Direct booking happens
  in code (`app._book_pending` → goji-booking `/internal/book`) only after the
  customer confirms, in a later message, the details stated back to them; the
  confirmation text is built from goji-booking's answer and names no one (a
  couple sharing one session is booked under one of them, so a name greeted
  the wrong person: owner, 25 Nov 2026). Dry run until go-live
  (`WA_AGENT_BOOKING_DRY_RUN`). Moves with 24h+ notice go the same way
  (`_move_pending` → `/internal/reschedule`); cancellations with 24h+ notice
  go out in the same turn (`_cancel_now` → `/internal/cancel`). Inside 24
  hours both are drafts for Chris (fee policy).
- **Bookings ask for an email** (owner, 25 Nov 2026): with one on the
  booking, Plato sends its own confirmation (with the clinic's registration
  form) and goji-booking sends Goji's. The agent asks once, with the times,
  or before booking if a time was picked first; a no books without it. Only
  numbers with no email on file are asked: otherwise the booking takes the
  patient's own email, else the texter's (the person chatting is the
  contact, as with the phone), unless they give another
  (`tools.contact_email`, from `dim_patient_contact`, never shown to the
  model). A malformed or mistyped email
  (goji-booking's `bad_email`) is asked again with the time kept, not handed
  to Chris; a bad one on file books without it.
- **Cancelling is the agent's with 24h+ notice** (owner, 24 Nov 2026: a test
  cancel more than 24 hours out was handed to Chris). No "shall I?" first:
  when it knows which appointment, it fills `cancel` and the code cancels in
  that turn (several booked: it asks which). The reply is the code's
  confirmation plus the model's follow-up: a gentle "what came up?" if no
  reason was given, since "away" or "unwell" shapes the follow-up, or a word
  on the reason if one was, and an offer to rebook. A follow-up that claims
  the cancellation itself or fails the check gives way to the default
  (`booking_client.cancel_text`); a model reply that says it's cancelled
  with nothing for the code to cancel is never sent
  (`policy.claims_cancelled`).
- **Never call Plato from here.** Availability comes from goji-booking's API,
  which serves its 5-minute snapshot. Plato allows 20 requests/min for the
  whole clinic (`booking/README.md`).
- **Facts come only from the website, plus `house_rules.md`.** `kb.py` builds
  the knowledge base from `marketing/website` at deploy time. A wrong price is
  fixed on the site, not in the prompt. A practice Chris confirms that doesn't
  belong on the site (physio isn't sold as packages) goes in `house_rules.md`,
  one dated line each. Service ids mirror `booking/config.py` (`test_tools.py` checks).
- **The full names on the chat's own number reach the model**
  (`tools.describe_patient`), so it books a returning patient under the name
  on file instead of asking (owner, 25 Nov 2026). It uses one only for
  someone the customer named or who is writing, and never mentions the others.
- **Patient lookup is keyed on the chat's own number.** The one exception,
  `find_booking` (no record for this number), needs the full name AND the
  booking's number to match the same patient, returns only the next
  appointment, and is capped at 3 tries per chat. A number alone or a name
  alone never reveals anything.
- **`dim_patient_contact` is current within seconds.** goji-booking updates
  it when staff change a patient in Plato (webhook) and when it creates one
  (`booking/patient_contacts.py`); the nightly rebuild repairs and reports
  drift. Read only that table. "No record" is cached 10 minutes, a match 6
  hours, and a booking clears the cache (a 6-hour "no record" handed over a
  booking the agent had made itself, 24 Nov 2026).
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
  `same_day=1` with the internal token (offered from 2 hours ahead, booked
  if at least 90 minutes ahead: owner, 24 Nov 2026). Without that it told a customer "fully booked
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
- **At most two website page links per conversation.** A link at the end
  of every answer read as a bot (owner, 25 Nov 2026). Once two page links
  have gone out in the last day, `policy.drop_repeat_page_links` takes any
  further page link and its "read more here:" line out of the reply before
  it's sent. Booking links don't count and aren't touched: the prompt's
  once-per-conversation rule covers them.
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
- **"The team will take a look" means staff are pinged.** A photo, video,
  voice note or document the agent answers pings staff on WhatsApp (email
  only if the ping fails); several within 10 minutes get one ping
  (`policy.media_ping_due`). The chat stays with the agent. Before this the
  agent promised a customer the team would look at her referral photos and
  nobody was told (25 Nov 2026).
- **An emoji reaction is never a message.** A customer's reaction gets no
  model call or reply and isn't added to history. A positive one (👍 😊 🙏,
  `policy.POSITIVE_REACTIONS`) pings nobody; a negative or neutral one
  pings staff when the chat is the agent's (owner, 25 Nov 2026, after a 👍
  pinged Chris). A staff reaction to a ping gets no reply; Chris reacting in
  the Business app isn't an echo, so it doesn't pause the chat.
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
  it (`RESUME <code>`), or for 14 days after her last message: the customer's
  next message after that goes to the agent (`policy.apply_pause_expiry`;
  owner, 24 Nov 2026). Deliberate pauses (`PAUSE <code>`, admin, watch list)
  never lapse; chats she had in the 30 days before go-live pause on
  their next message (`policy.pre_golive_chat`). Any new path that messages a
  customer (confirmations, reminders, pings) checks the kill switch, go-live
  and the chat's mode first.
- **The team's answer goes through the agent.** Chris swipe-replies to a
  ping with the answer (the ping's message id maps to the chat for 7 days,
  `<collection>_pings`), or texts `ANSWER 004 ...`. The agent passes it on in
  its own voice (`agent.relay_note`), sends it and takes the chat back, then
  shows her what it sent (`app._staff_answer`; owner, 24 Nov 2026). Any mode,
  red flags included: it's her explicit call. Never past the kill switch,
  before go-live, or outside the customer's 24h window. Nothing is sent if
  the model says it isn't an answer for that chat or the write-up fails
  `reply_problems`; a partial answer leaves the rest `waiting`. Only pings
  about a named chat are mapped, so a swipe-reply can't reach the wrong
  customer. The answer is kept as a `team` history line for follow-ups.
  Check prompt changes with `python -m wa_agent.eval.relay` on the CLI.
- **Staff numbers are never customers.** `WA_AGENT_STAFF` messages go to
  `handle_staff` before any lookup, model call or metric; the numbers live in
  a private env file, never the repo. Pings name customers by first name or
  last 4 digits only.
