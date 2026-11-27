# Applicant data retention

**Status: proposed. Needs management approval before anyone relies on it.**
Nothing is deleted automatically, and nothing will be until management has
approved both the periods and an automated process.

## Proposed periods

| Applicant | Keep until |
|---|---|
| Not hired, no talent-pool consent | 6 months after the recruitment process for that role concludes |
| Not hired, ticked "keep me in mind" (talent pool) | 12 months after the process concludes |
| Hired | moves to the employee record; the recruitment copy is deleted once the personnel file has what it needs |
| Withdrew / asked to be deleted | as soon as practical (aim: 30 days), unless a legal reason to keep it |

The tracker's **Retention review date** column is filled at submission as
received + 180 days, a provisional placeholder. The reviewer sets it properly
when the process concludes (concluded date + 6 or + 12 months).

## Monthly review (manual)

1. Filter the tracker on **Retention review date** on or before today.
2. For each row, confirm with the hiring lead that the process has concluded
   and there is no reason to keep it (for example a dispute, or a pending
   offer).
3. Delete, in this order:
   - the CV in Drive (`Applications/<reference> - <name> - CV.<ext>`), then
     empty it from the Shared Drive's trash;
   - email: the "[Goji Careers]" internal notification and any correspondence
     with the applicant in hello@ (search by the reference and the name), then
     empty Gmail's trash;
   - any downloaded copies of the CV on personal devices or desktops;
   - the tracker row: replace the name, email, phone, LinkedIn and
     introduction cells with "Deleted <date>" and keep only the reference,
     role, dates and status, so hiring numbers stay countable. (Or delete the
     row if management prefers.)
4. Note the date in the row's **Notes** column.

## Access requests and withdrawals

Requests come to hello@gojiphysio.com. Find the applicant by reference or
email in the tracker. An access request is answered with the stored
tracker row and CV. A withdrawal or deletion request follows step 3
straight away.

## What the system already limits

- Only what the form asks for is stored: no NRIC, date of birth, photo,
  marital status, religion, salary history or references.
- CVs are never attached to emails or written to logs. Logs carry the
  reference and error codes only.
- No public or "anyone with the link" sharing. Access is the Shared Drive's
  membership; review it when someone leaves.
- Analytics events carry the role id and error codes only, never personal
  details.
