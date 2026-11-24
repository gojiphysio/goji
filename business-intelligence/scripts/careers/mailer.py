"""
Recruitment emails, sent via Gmail SMTP as hello@gojiphysio.com (the same
Workspace app password the booking service uses, `gmail-app-password`).

Both are best-effort and run only AFTER the application is stored: a failed
send is logged and retried on the candidate's next retry (if any), but never
undoes or repeats the stored application.

  send_internal(): heads-up to hello@ with private Drive/Sheets links.
                   Never attaches the CV.
  send_ack():      acknowledgement to the applicant. No response-time promise.

Header safety: every header value is built from validated, single-line data
(email/phone are pattern-checked; names have CR/LF stripped), and
email.message refuses header values containing newlines anyway.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from . import config
from .workspace import folder_url, sheet_url

log = logging.getLogger("careers.mailer")


def _send(msg: EmailMessage) -> None:
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(config.SMTP_USER, config.SMTP_PASS)
        s.send_message(msg)


def _one_line(v) -> str:
    return " ".join(str(v or "").split())


def internal_message(ref: str, role: dict, app: dict, folder_id: str) -> EmailMessage:
    general = role["id"] == config.GENERAL_ID
    msg = EmailMessage()
    msg["Subject"] = ("[Goji Careers] New expression of interest" if general
                      else f"[Goji Careers] New application — {role['title']}")
    msg["From"] = formataddr(("Goji Careers", config.SMTP_USER))
    msg["To"] = config.ADMIN_TO
    lines = [
        "A new expression of interest has been received through the Goji Careers page."
        if general else "A new application has been received through the Goji Careers page.",
        "",
        f"Application reference: {ref}",
        f"Candidate: {_one_line(app.get('full_name'))}",
        f"Role: {role['title']}",
    ]
    if general:
        area = app.get("interest_area") or ""
        lines.append(f"Interested in: {area}" + (f" ({_one_line(app['interest_detail'])})"
                                                 if app.get("interest_detail") else ""))
    elif app.get("also_consider") == "Yes":
        lines.append("Also open to the other seniority level: Yes")
    lines += [
        f"Employment preference: {app.get('employment')}",
        f"Years of experience: {app.get('years_experience')}",
    ]
    if app.get("ahpc_status"):
        lines.append(f"AHPC registration status: {app['ahpc_status']}")
    lines += [
        f"Earliest availability: {_one_line(app.get('start_availability'))}",
        "",
        f"View application: {folder_url(folder_id)}",
        f"View applicant tracker: {sheet_url()}",
        "",
        "The CV is in the application folder (not attached). Both links need a "
        "Goji Google account with access to the recruitment folder.",
    ]
    if config.TEST_MODE:
        lines += ["", "[TEST MODE] This application was made against the test folder/tracker."]
    msg.set_content("\n".join(lines))
    return msg


def ack_message(ref: str, role: dict, app: dict) -> EmailMessage | None:
    to = app.get("email") or ""
    if config.TEST_MODE:
        if not config.TEST_EMAIL:
            log.info("test mode with no CAREERS_TEST_EMAIL: acknowledgement not sent (%s)", ref)
            return None
        to = config.TEST_EMAIL
    general = role["id"] == config.GENERAL_ID
    first = (_one_line(app.get("full_name")).split() or ["there"])[0]
    msg = EmailMessage()
    msg["Subject"] = "Thank you for your interest in Goji!"
    msg["From"] = formataddr((config.FROM_NAME, config.SMTP_USER))
    msg["To"] = to
    msg["Reply-To"] = config.CONTACT_EMAIL
    if general:
        body = [
            f"Hi {first},",
            "",
            "Thank you for taking the time to get in touch with us at Goji!",
            "",
            "We've received your expression of interest and look forward to learning more about you. "
            "While we don't have a matching role open right now, we'll keep your details on file and "
            "be in touch should a suitable opportunity come up.",
        ]
    else:
        body = [
            f"Hi {first},",
            "",
            "Thank you for taking the time to apply to join us at Goji!",
            "",
            f"We've received your application for the {role['title']} position and look forward to "
            "learning more about you.",
            "",
            "Our team will review your application and be in touch should there be a suitable next step.",
        ]
    body += [
        "",
        f"In the meantime, if you have any questions, feel free to reach us at {config.CONTACT_EMAIL}.",
        "",
        "Thank you again for your interest in growing with us.",
        "",
        "Cheers,",
        "The Goji Team",
    ]
    if config.TEST_MODE:
        body = [f"[TEST MODE] Intended for the applicant's address on the form.", ""] + body
    msg.set_content("\n".join(body))
    return msg


def send_internal(ref: str, role: dict, app: dict, folder_id: str) -> bool:
    if not config.SMTP_PASS:
        log.info("SMTP not configured; internal email skipped (%s)", ref)
        return False
    try:
        _send(internal_message(ref, role, app, folder_id))
        log.info("internal email sent (%s)", ref)
        return True
    except Exception as e:
        log.warning("internal email failed (%s): %s", ref, type(e).__name__)
        return False


def send_ack(ref: str, role: dict, app: dict) -> bool:
    if not config.SMTP_PASS:
        log.info("SMTP not configured; acknowledgement skipped (%s)", ref)
        return False
    try:
        msg = ack_message(ref, role, app)
        if msg is None:
            return False
        _send(msg)
        log.info("acknowledgement sent (%s)", ref)
        return True
    except Exception as e:
        log.warning("acknowledgement failed (%s): %s", ref, type(e).__name__)
        return False
