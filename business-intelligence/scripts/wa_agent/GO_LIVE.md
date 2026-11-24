# Go-live runbook (status: LIVE since 24 Nov 2026, 09:50 SGT)

Where things stand, and the steps left to put the assistant on Goji's real
number. Design detail lives in [`README.md`](README.md); this file is the
checklist. Update the status line and tick items as they're done.

## Live (24 Nov 2026)

- Number connected through Dualhook (`WA_API_BASE=https://api.dualhook.com/v25.0`,
  phone number id `1010651355469604`), history shared and imported, payment
  method on the WhatsApp account. Booking dry run off, stage 2.
- Echo test passed (Chris's Business-app message arrived in 2.7 s and paused
  the chat). Rehearsal from a non-staff phone: greeting, service fit,
  packages, a real booking and "is Chris around?", all answered.
- Templates submitted on the real account 24 Nov, pending at go-live. Until
  `goji_staff_alert_v2` is approved, pings reach staff only inside the 24 h
  window: each staff phone texts the Goji number once a day.
- Learned on the day: a tester number does NOT bypass the kill switch or
  "not live" (it only unlocks `/reset` and `/turbo`), so the real-number
  rehearsal happens after go-live. Staff numbers are never customers, so
  rehearse from a phone that isn't in `WA_AGENT_STAFF`. Commands only count
  from a staff phone to the Goji number.
- Open: Meta sends history in phases and `progress` reaches 100 per phase;
  `handle_history` marks the import done at the first 100. Wait for the
  history traffic to stop before go-live until that's fixed.

## Done

- **Deployed** `goji-wa-agent` on Cloud Run (goji-bi, asia-southeast1):
  one idle instance with CPU only during requests, work queued on Cloud
  Tasks (queue `wa-agent`), morning-summary job at 07:30 SGT, Firestore with
  TTLs, events table and views. Secrets all in Secret Manager (`deploy.sh`
  header lists them; `wa-webhook-url-token` for the provider's secret link).
- **Current state of the service:** `go_live` unset (not live: records
  message times, answers nobody) and the kill switch ON. Stage 2, contact
  scope `quiet`, booking dry run ON, no staff numbers yet (the test setup).
  Check with `GET /admin/rollout` (admin token on the operator's machine).
- **Dualhook:** the webhook URL (secret link) and verify token are entered
  and Dualhook's endpoint test passed (348 ms). Signup itself is NOT done.
- **Live Plato test** on the test patient "ZZ Goji Shop Test": booking and
  moving an appointment work end to end (cleaned up after). Writing a patient
  tag does not: Plato accepts `PUT /patient` with `tag` and saves nothing, so
  `WA_AGENT_PLATO_TAG_WRITES` is off and Chris is asked to add the waiver tag.
- **Templates (test account only):** `goji_staff_alert` was recategorised
  as marketing by Meta; `goji_staff_alert_v2` submitted (the code uses v2).
- **Model:** Opus 5.5 kept (owner's call). Scenario suite: Opus 50/50,
  Sonnet 47/50 at half the cost (19 Nov).
- **Handoff review (#257, merged and deployed 23 Nov):** evals judge at
  stage 2; off-topic messages are answered with no ping and the number is
  watch-listed after 3 in a row; every handover sends the customer a specific
  holding reply and gives Chris a draft with [brackets] to fill in (pings show
  both); the agent links the page that answers a question and adds a smiley
  now and then; late changes are worked out from the patient record too.
  Review doc with the owner's grades:
  https://claude.ai/artifact/CJMz4mprhvrDin1MmNuU1i

## Next: connect Goji's number (needs Chris and the clinic phone)

Dualhook's pre-signup checklist, applied to Goji:

1. On the phone that holds 8377 0401: WhatsApp **Business** app, updated
   (2.24.17 or later). Not WhatsApp Web or a linked device.
2. Business app → Settings → Account → Business Platform: disconnect "Inbox
   in Meta Business Suite" (Chris then replies from the app), wait 15 min.
3. Auto labels and auto lists off; Instagram unlinked; Business AI unlinked
   (deletes its setup; our assistant replaces it, confirm with Chris).
4. Portfolio: **Goji Physiotherapy 1** (where the app and templates are),
   legal business name filled in.
5. Chrome or Edge, popups allowed, no ad blocker or VPN.
6. **Share chat history: yes** (one-time choice). The go-live cut-off needs
   it; only message times are kept, never text.

## After the number connects

1. Send the Dualhook API key / token and base URL. Then: update `wa-token`,
   set `WA_API_BASE` / `WA_SEND_PATH` / `WA_AUTH_HEADER` / `WA_AUTH_PREFIX` /
   `WA_PHONE_NUMBER_ID` for the provider, redeploy (`deploy.sh` keeps every
   other live value).
2. Check from the logs and Firestore: Chris's replies arrive as echoes
   (`smb_message_echoes`), the `history` import arrives and reaches 100%
   (`GET /admin/rollout` shows `history_imported`). Confirm the history
   payload shape against `whatsapp.parse_history`.
3. Resubmit the templates on the real account: appointment confirmed,
   appointment reminder, referral received, `goji_staff_alert_v2`.
4. Set `WA_AGENT_STAFF` (Chris + Charles, from the private `prod.env`),
   `WA_AGENT_TESTERS` (empty or Charles), and `WA_AGENT_BOOKING_DRY_RUN=0`
   once you're happy; redeploy.
5. GitHub repo variable `WA_AGENT_URL` (set at merge) gives goji-booking
   the shared token for `/internal/book` and `/internal/reschedule`.

## Before go-live day

1. ~~Full scenario run on Opus (the production model) through the CLI~~
   Done 23 Nov: 88/89 (the one failure was the eval checking Chris's draft
   for length; fixed). Re-run after any prompt change:
   `WA_AGENT_BACKEND=cli WA_AGENT_MODEL=claude-opus-5-5 python -m
   wa_agent.eval.scenarios --jobs 4`, through the CLI, not the API key.
2. Show Chris one handover ping before go-live: what the customer got, and
   her draft with [brackets] to fill in before sending.
3. Still open from the review doc (not blockers): send-and-tell for late
   arrivals, cancels with notice and admin requests; a house rule on bringing
   a baby; the 0.75 confidence bar.

## Go-live day

1. Chris turns OFF the Business app's away and greeting messages.
2. Kill switch off: `POST /admin/kill {"on": false}`.
3. Go live: `POST /admin/go-live {}` (now). From here, chats with a
   message in the 30 days before it are Chris's and pause on their next
   message; new chats are the assistant's.
4. Chris texts "hi" to the Goji number from her phone: the reply is the
   walkthrough (RESUME / PAUSE / STOP / START / STATUS, pings, summary).
5. Watch the first day: the Agent tab, the morning summary, staff pings.
   Daily learning review for the first month, then weekly.

## Later (cost, not urgent)

Measured cost per conversation after two weeks live, then: pre-fetch
availability in code (fewer tool round-trips), 5-minute cache on the
conversation tail, faster startup so the idle instance can go. Estimated
~$55-80/month now, ~$40-55 after those. See the cost table in `README.md`.
