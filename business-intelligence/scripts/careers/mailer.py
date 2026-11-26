"""
The two emails, sent via Gmail SMTP as hello@gojiphysio.com (the Workspace app
password booking also uses, `gmail-app-password`). Both are sent only AFTER the
application is stored, and a failed send is logged, never fatal.

  internal: heads-up to hello@ with links to the CV and the tracker (the CV is
            never attached).
  confirm:  confirmation to the applicant. In test mode it goes to
            CAREERS_TEST_EMAIL instead, or nowhere if that is empty.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from . import config
from .workspace import file_url, sheet_url

log = logging.getLogger("careers.mailer")


def _send(msg: EmailMessage) -> None:
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(config.SMTP_USER, config.SMTP_PASS)
        s.send_message(msg)


def _one_line(v) -> str:
    return " ".join(str(v or "").split())


def internal_message(ref: str, role: dict, app: dict, cv_id: str,
                     cert_ids: list[str] | None = None) -> EmailMessage:
    general = role["id"] == config.GENERAL_ID
    pilates = role.get("form") == "pilates"
    msg = EmailMessage()
    name = _one_line(app.get("full_name"))
    msg["Subject"] = (f"[Goji Careers] New expression of interest — {name}" if general
                      else f"[Goji Careers] New application — {role['title']} — {name}")
    msg["From"] = formataddr(("Goji Careers", config.SMTP_USER))
    msg["To"] = config.ADMIN_TO
    lines = [
        f"Application reference: {ref}",
        f"Candidate: {_one_line(app.get('full_name'))}",
        f"Role: {role['title']}",
    ]
    if general and app.get("interest_area"):
        lines.append(f"Interested in: {app['interest_area']}")
    if pilates:
        lines += [
            "Engagement: Freelance",
            f"Singapore work eligibility: {app.get('work_eligibility')}",
            f"Certification: {_one_line(app.get('certification'))}",
            f"Apparatus: {', '.join(app.get('apparatus') or [])}",
            f"Teaching experience: {app.get('teaching_years')}",
            f"Available days: {', '.join(app.get('preferred_days') or [])}",
            f"Earliest start date: {app.get('start_availability')}",
        ]
    else:
        lines += [
            f"Employment preference: {app.get('employment')}",
            f"Years of experience: {app.get('years_experience')}",
        ]
        if app.get("ahpc_status"):
            lines.append(f"AHPC registration status: {app['ahpc_status']}")
        lines.append(f"Earliest availability: {_one_line(app.get('start_availability'))}")
    lines += ["", f"CV: {file_url(cv_id)}"]
    lines += [f"Certificate: {file_url(i)}" for i in cert_ids or []]
    lines += [
        f"Applicant tracker: {sheet_url()}",
        "",
        "These links need a Goji Google account with access to the Goji Recruitment drive.",
    ]
    if config.TEST_MODE:
        lines += ["", "[TEST MODE] Stored in the test folder and tracker."]
    msg.set_content("\n".join(lines))
    return msg


def confirmation_message(role: dict, app: dict) -> EmailMessage | None:
    to = app.get("email") or ""
    if config.TEST_MODE:
        if not config.TEST_EMAIL:
            return None
        to = config.TEST_EMAIL
    first = (_one_line(app.get("full_name")).split() or ["there"])[0]
    msg = EmailMessage()
    msg["Subject"] = "Thank you for your interest in Goji!"
    msg["From"] = formataddr(("Goji Physiotherapy", config.SMTP_USER))
    msg["To"] = to
    msg["Reply-To"] = config.CONTACT_EMAIL
    if role["id"] == config.GENERAL_ID:
        middle = ["Thank you for taking the time to get in touch with us at Goji!", "",
                  "We've received your expression of interest and look forward to learning more "
                  "about you. While we don't have a matching role open right now, we'll keep your "
                  "details on file and be in touch should a suitable opportunity come up."]
    else:
        middle = ["Thank you for taking the time to apply to join us at Goji!", "",
                  f"We've received your application for the {role['title']} position and look "
                  "forward to learning more about you.", "",
                  "Our team will review your application and be in touch should there be a "
                  "suitable next step."]
    body = [f"Hi {first},", "", *middle, "",
            f"In the meantime, if you have any questions, feel free to reach us at "
            f"{config.CONTACT_EMAIL}.", "",
            "Thank you again for your interest in growing with us.", "",
            "Cheers,", "The Goji Team"]
    if config.TEST_MODE:
        body = ["[TEST MODE] In production this goes to the applicant's address.", "", *body]
    msg.set_content("\n".join(body))
    return msg


def send(kind: str, msg: EmailMessage | None, ref: str) -> None:
    if msg is None or not config.SMTP_PASS:
        log.info("%s email not sent (%s): %s", kind, ref,
                 "no SMTP password" if msg is not None else "test mode, no test address")
        return
    try:
        _send(msg)
        log.info("%s email sent (%s)", kind, ref)
    except Exception as e:
        log.warning("%s email failed (%s): %s", kind, ref, type(e).__name__)
