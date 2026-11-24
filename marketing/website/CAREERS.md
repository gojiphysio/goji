# Careers pages: how to run them

Pages: `/careers/` (overview + open roles), `/careers/<id>/` (one per role),
`/careers/expression-of-interest/`. All roles live in one file,
`src/lib/vacancies.ts`. The backend (`business-intelligence/scripts/careers/`)
reads the built `/careers/vacancies.json`, so the site is the single source of
truth for which roles accept applications.

## Close a role

Set `active: false` (or a `closingDate`, `YYYY-MM-DD`, Singapore time: the role
closes at the end of that day). On the next build:

- it drops off `/careers/` (if none are open, the page says so and points to
  the expression-of-interest form);
- its page stays up with "Applications for this role are now closed", no form,
  no JobPosting schema, `noindex`, and leaves the sitemap;
- the backend refuses new applications for it within 5 minutes (409).

Don't delete a closed role's entry: the page keeps old links working. Delete
it only when the URL no longer gets traffic.

## Reopen or change a role

Set `active: true`, clear `closingDate`, and set `datePosted` to the reopening
date (Google treats `datePosted` as freshness). Edit any of the description
lists in place; the page and the JobPosting schema read the same fields, so
they can't disagree.

## Add a role

Copy an entry and give it a new `id` (this is the URL slug and the value
stored in the tracker; never change it after launch). Set `order`,
`driveFolder` (the folder name under `Applications/<year>/`; the backend
creates it on first use), `minYearsExperience`, `form: "physio"` for a clinical role, and
`alsoConsiderFor` if there is a sibling level. Then:

- add the page to `public/llms.txt` (`check_dist.py` fails otherwise);
- add the role folder to `ROLE_FOLDERS` in `careers/setup_workspace.py` if you
  want it pre-created, and the id to the tests' `VACANCIES` fixture if it has
  new behaviour;
- a non-physio role needs its own question set: today the form knows
  `physio` and the general expression of interest only.

## Rules

- No salary figures, commission or earnings, and no difference in pay between
  levels, anywhere: copy, schema (no `baseSalary`), emails.
- Copy follows the site voice rules in `AGENTS.md` (British English, never
  "boutique").
- The form is rendered only when `PUBLIC_CAREERS_API` is set at build time.
  Without it, each page shows "Apply by email" to hello@gojiphysio.com.
- Analytics events (`careers_page_view`, `job_detail_view`, `apply_now_clicked`,
  `application_started`, `application_submitted`,
  `expression_of_interest_submitted`, `application_error`) carry the role id,
  error codes and UTM tags only. Never add a personal field to them.
