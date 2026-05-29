# Goji BI - Claude Desktop Setup Guide

Set up live BigQuery access from Claude Desktop so [wife] can ask plain-English questions about the clinic's data.

**Architecture:** Claude Desktop -> local `mcp-server-bigquery` (runs on demand via `uvx`) -> BigQuery, authenticated as her Google account (`hello@gojiphysio.com`) with read-only access scoped to the curated `marts` dataset.

We use Application Default Credentials (ADC) rather than a service account key file because the GCP org policy `iam.disableServiceAccountKeyCreation` blocks key creation, and ADC is the cleaner architecture for a small team anyway - no key files to manage or leak.

**Time budget:** ~10 min on your side (GCP), ~10 min on her machine, ~2 min for the Claude Project.

---

## Part 1 - GCP setup (you do this once)

Easiest path: just run `gcp-setup.sh` in this folder. It grants `bigquery.jobUser` at project level + `bigquery.dataViewer` on the curated dataset to `hello@gojiphysio.com`. Idempotent and safe to re-run.

```bash
gcloud config set project goji-bi
bash gcp-setup.sh
```

If you'd rather run the commands manually:

```bash
EMAIL=hello@gojiphysio.com

# Job runner - project-wide
gcloud projects add-iam-policy-binding goji-bi \
  --member="user:${EMAIL}" \
  --role="roles/bigquery.jobUser"

# Data viewer - marts dataset only
bq add-iam-policy-binding \
  --member="user:${EMAIL}" \
  --role="roles/bigquery.dataViewer" \
  goji-bi:marts
```

`marts` currently has two views (`fct_invoice_line`, `fct_service_delivered`). As you add more, the grant carries over automatically.

**Do not** grant her access to `raw` or `stg`. If a question can't be answered from `marts`, build a new view in `marts` - never widen perms.

### 1.4 Cost guardrails (the important part)

Two layers. Both take 1 minute in the Console.

**A. Daily query quota.** Cloud Console -> IAM & Admin -> Quotas & System Limits -> filter "BigQuery API" -> find **"Query usage per day"**. Edit -> set to **10 GiB/day**.

That's about 5000x what her typical question scans. Worst case if she hits the cap: ~$0.06 of BQ cost for the day, then queries fail until tomorrow. You'll know something is wrong before the bill notices.

**B. Billing budget alert.** Cloud Console -> Billing -> Budgets & Alerts -> Create Budget. Scope: this project, BigQuery service only. Amount: **$5/month**. Alert thresholds: 50%, 90%, 100%. You get an email the moment anything weird happens.

With these two layers the realistic worst-case BQ bill is $0-$2/month, and the absolute ceiling is bounded.

---

## Part 2 - Her machine setup (~10 min)

### 2.1 Install Claude Desktop

https://claude.ai/download. Sign her in.

### 2.2 Install uv (needed to launch the MCP server)

Mac, in Terminal:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows, in PowerShell:
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close and reopen Terminal/PowerShell so `uvx` is on PATH.

### 2.3 Install the gcloud SDK and sign her in

The MCP server authenticates using her own Google account via Application Default Credentials. She needs `gcloud` installed once.

Mac:
```bash
brew install --cask google-cloud-sdk
```

Windows: download installer from https://cloud.google.com/sdk/docs/install

Once installed, she runs the ADC login in Terminal:
```bash
gcloud auth application-default login
```

A browser opens. She signs in as `hello@gojiphysio.com`. That writes ADC credentials to:
- Mac/Linux: `~/.config/gcloud/application_default_credentials.json`
- Windows: `%APPDATA%\gcloud\application_default_credentials.json`

The MCP server picks these up automatically. Tokens refresh transparently as long as the file exists. If she ever needs to revoke, you remove her IAM binding in Part 1 and the access is gone immediately.

### 2.4 Configure Claude Desktop

Open or create the config file:
- Mac: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Paste:

```json
{
  "mcpServers": {
    "bigquery": {
      "command": "uvx",
      "args": [
        "mcp-server-bigquery",
        "--project", "goji-bi",
        "--dataset", "marts",
        "--location", "asia-southeast1"
      ]
    }
  }
}
```

Adjust:
- `--location` -> wherever the dataset lives. `asia-southeast1` is the Singapore region; change if Goji's BQ project lives elsewhere. If wrong, queries fail with a clear "dataset not found in location" error.
- `--dataset` -> change only if you renamed `marts`

No `GOOGLE_APPLICATION_CREDENTIALS` env var needed - the MCP server's `google-cloud-bigquery` library finds the ADC credentials on disk automatically.

### 2.5 Restart Claude Desktop

Quit fully (Cmd+Q on Mac, not just close the window). Reopen. Click the tools/slider icon in the input bar - you should see `bigquery` listed with tools like `execute-query`, `list-tables`, `describe-table`.

If it doesn't show up, check the MCP logs:
- Mac: `~/Library/Logs/Claude/mcp*.log`
- Windows: `%APPDATA%\Claude\logs\mcp*.log`

Most common failures:
- Wrong key path in the config
- `uvx` not on PATH (reopen Terminal/Claude after installing uv)
- Wrong `--location`
- SA not granted `bigquery.jobUser` at project level

---

## Part 3 - Create her Claude Project (~2 min)

This is what makes Claude actually understand her data, not just have access to it.

1. In Claude Desktop, sidebar -> Projects -> New project. Name: "Goji BI".
2. In the project's custom instructions / knowledge, paste the entire contents of `goji-bi-schema-glossary.md` (same folder as this guide).
3. Tell her: **always ask data questions inside the Goji BI project**, not in regular new chats. Regular chats won't have the schema context loaded.

---

## Part 4 - First test questions

Have her try these in order. They're designed to validate one thing each:

1. *"How many appointments were booked last month?"*
   Validates: date handling, fact table access.
2. *"What's the average age of patients who booked an appointment last month?"*
   Validates: patient dim join, age calc.
3. *"What's our recognised revenue for April 2026?"*
   Validates: she gets the right concept (recognised, not invoiced, not cash).
4. *"What's our deferred revenue balance right now?"*
   Validates: package accounting logic surfaces correctly.

If any answer looks wrong, the fix is almost always a clarification in the schema-glossary doc. Add a note explaining whichever concept tripped Claude up, then she re-asks.

---

## Troubleshooting cheat sheet

| Symptom | Fix |
|---|---|
| MCP tools don't appear in Claude Desktop | Restart fully (Cmd+Q). Check `~/Library/Logs/Claude/mcp*.log`. |
| "Could not automatically determine credentials" in logs | She hasn't run `gcloud auth application-default login` yet, or signed in as the wrong Google account. Re-run and sign in as `hello@gojiphysio.com`. |
| Worked yesterday, fails today with auth errors | Rare, but ADC refresh can fail. Re-run `gcloud auth application-default login`. |
| "Permission denied" on a query | She tried `raw.*` or `stg.*`. That's by design. Build the view in `marts`. |
| "Quota exceeded" | She hit the 10 GiB/day cap. Either a runaway query or genuinely heavy day. Check Cloud Console -> BigQuery -> Query history. |
| Wrong "last month" answer | Timezone. Confirm the glossary's timezone line matches the clinic's actual TZ. |
| Costs spiking | Budget alert email tells you which day. Open Query history for that day, find the offending query, harden the view it ran against. |
| `uvx: command not found` in logs | uv install didn't update PATH. Reinstall uv and restart Claude Desktop. |

---

## What to revisit later

- As you add new views to `marts` (patient dim, practitioner dim, revenue daily, etc.), append their descriptions to `goji-bi-schema-glossary.md`. She'll pick them up on her next chat.
- If she starts asking questions she can't answer, build a new view in `marts` and grant her `dataViewer` on it. Never widen to `raw`/`stg`.
- Once data passes ~10 GB, look at partitioning + clustering on the bigger fact tables.
- No key rotation needed (ADC handles refresh). If you ever need to revoke access immediately, remove her IAM bindings in the Console or re-run a tweaked `gcp-setup.sh` that removes them.
