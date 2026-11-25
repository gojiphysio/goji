# Booking emails: for Chris to approve

25 Nov 2026 · prepared by Charles

![How the emails work](flow.png)

Every booking gets one confirmation email, whether it was made on the website, on WhatsApp or by the front desk. A patient counts as confirmed once they tap Confirm in an email or on WhatsApp, or the front desk marks them confirmed in Plato. A cancellation sends nothing. Today's Plato confirmation and Plato's own 48-hour reminder both stop on go-live day.

## What the test did

On 25 Nov we ran the new emails for real, with two test bookings on Fri 27 Nov with Kristy. Both went to Charles's personal email and were deleted afterwards. Everything worked.

1. **Booked a returning patient**, the way the WhatsApp assistant books: **email 1**, the booking confirmation.
2. **Moved that booking** from 6:30pm to 7:00pm: **email 2**, "your appointment has moved". The calendar entry moved too, so there was no second entry.
3. **Booked a new patient** through the website: **email 3**, the confirmation with Plato's registration form.
4. **Ran the 48-hour reminder** for both bookings: **emails 4 and 5**, each with a Confirm button.
5. **Confirmed both bookings:** one through Plato's Confirm link, one the way the WhatsApp Confirm button will. Plato showed both as Confirmed.
6. **Ran the 48-hour reminder again:** **emails 6 and 7** now thank the patient instead of asking again. WhatsApp was skipped for both, as planned.
7. **Deleted both bookings.** No email goes out on a cancellation.

We also checked that the same booking never gets a second confirmation, and that only new patients get the registration form.

## The emails

The test sent seven emails, in five designs. The samples below use made-up patient names.

| # | Email | Sent when |
| --- | --- | --- |
| 1 | Booking confirmation | Right after any booking: website, WhatsApp or front desk |
| 2 | Appointment moved | When the time changes |
| 3 | Booking confirmation, first visit | Any booking where the patient hasn't yet filled in Plato's registration form; adds the form |
| 4, 5 | 48-hour reminder, not yet confirmed | 12:00, two days before |
| 6, 7 | 48-hour reminder, already confirmed | Same, once they've confirmed |

Every booking confirmation also adds the appointment to the patient's calendar, with no alert. If the time moves, that calendar entry moves with it.

**New since the test:** if the patient still hasn't filled in Plato's registration form, the 48-hour reminder email asks again, with the form button under the Confirm button. "Filled in" means the patient has signed the Clinic Consent Form at the end of Plato's form, which Plato records on their profile. Both emails stop asking once that's signed. The WhatsApp reminder can't carry the form link, because its wording is fixed by Meta.

### Email 1: booking confirmation
![Email 1](email-1.png)

### Email 2: appointment moved
![Email 2](email-2.png)

### Email 3: booking confirmation, registration form not yet filled in
![Email 3](email-3.png)

### Emails 4 and 5: 48-hour reminder, not yet confirmed
![Emails 4 and 5](email-4.png)

### Emails 6 and 7: 48-hour reminder, already confirmed
![Emails 6 and 7](email-6.png)

### WhatsApp reminder (waiting for Meta's approval)

This goes out at the same time as the reminder email:

> Hi Sarah, a reminder of your physiotherapy appointment on Fri 27 Nov, 7:00pm with Kristy at Goji Women's and Family Physiotherapy.
>
> If you need to reschedule, please let us know at least 24 hours before.
>
> [Confirm] [Reschedule]

Patients who have already confirmed and have an email don't get the WhatsApp reminder.

## Please approve

Reply to Charles on each point:

- [ ] The booking confirmation wording and layout (emails 1 and 3)
- [ ] The "moved" email (email 2)
- [ ] The 48-hour reminder: today's Plato wording, plus a Confirm button or a thank-you (emails 4 to 7)
- [ ] Reminders go out by email and WhatsApp together, and confirmed patients get no WhatsApp reminder
- [ ] Cancellations send nothing to the patient, and the reminder asks again for a missing registration form
- [ ] Go-live date: _______

On go-live day, the front desk stops sending Plato's confirmation by hand. Plato's own 48-hour reminder is switched off the same day ours starts.

---

[How our reminder compares with Plato's today](README.md)
