# Careers pages: managing vacancies

The careers section is `/careers/` (overview + vacancy list), one page per role
at `/careers/<role>/`, and `/careers/expression-of-interest/`. Applications go
to the `goji-careers` backend. Setup, privacy, retention and deletion are covered in
`business-intelligence/scripts/careers/README.md`.

## One file per role

Each role is a YAML file in `src/content/careers/`. The file name is the URL:
`physiotherapist.yaml` becomes `/careers/physiotherapist/`.

| Field | What it does |
|---|---|
| `jobId` | Stable ID sent with every application and analytics event. Keep it equal to the file name and **never change it** once the role has been live. |
| `status` | `open` (listed, form on, JobPosting schema), `closed` (page kept with an "applications closed" notice, no form, `noindex`, out of the sitemap and the list), `draft` (no page at all). |
| `closingDate` | Optional. After this date the role behaves as `closed`, but only once the site is rebuilt (the site is static and no scheduled rebuild runs). The backend starts refusing applications within 5 minutes of that build. To close a role on a fixed day, merge `status: closed` that day. |
| `featured` | Sorts the role first in the list. |
| `title`, `shortDescription` | H1 and the card text on `/careers/`. |
| `metaTitle` (≤65), `description` (≤160) | `<title>` and meta description. The build fails if they are too long. |
| `department`, `location`, `employmentLabel`, `minCommitment`, `clinicalFocus`, `experience` | The facts list on the role page and the vacancy card. |
| `employmentTypes`, `experienceMonths`, `datePublished` | JobPosting schema only (Google for Jobs). Set `datePublished` to the day the role goes live. |
| `minDaysPerWeek` | Part-time minimum. Below it, the form shows a note and the tracker flags it. It never blocks an application. |
| `form` | `physio` adds the AHPC and clinical-experience questions; `general` leaves them out. |
| `driveFolder` | Name of the role's folder in Drive (`Applications/<year>/<driveFolder>/`). |
| `sections` | The job description: `heading`, `paragraphs`, `items` (bullets). |
| `source` | Where the wording came from. `status: approved` only once it matches the approved document. |

## Common jobs

- **Close a role:** set `status: closed` and merge. The page stays up (old links
  and shared posts still work) and tells people to see current roles or
  register interest.
- **Reopen it:** set `status: open`, update `datePublished`, merge.
- **Add a role:** copy `physiotherapist.yaml`, rename it, change every field,
  keep `status: draft` until the wording is approved, then `open`. Add its URL
  to `public/llms.txt` (the SEO check fails otherwise).
- **No open roles:** the list shows an empty state that points to the
  expression-of-interest form. You don't need to do anything else.

## Rules for job copy

- Wording comes from the approved job description document. Don't write
  generic filler.
- Never publish salary figures, commission percentages or thresholds, earnings
  projections, sign-on incentives, salary reviews, "boutique", or any benefit
  that isn't in the approved document. The JobPosting schema carries no salary.
- Use the house style: British English, regular dashes, no italics, none of the
  banned words in `AGENTS.md`.
- Life-at-Goji photos must be real Goji photos. Don't use stock or generated
  images, and don't use staff quotes unless the person has approved them in
  writing.
