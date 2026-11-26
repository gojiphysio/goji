"""
Recruitment emails, sent as hello@gojiphysio.com over Gmail SMTP (the same
app password, `gmail-app-password`, as goji-booking's mailer).

  send_internal_notification      -> hello@ (no CV attached; links to Drive)
  send_applicant_acknowledgement  -> the applicant (or the test recipient)

Both return True when the message was handed to Gmail and never raise: an
email failure must never undo or repeat a stored application (the pipeline
records which emails went out and `admin.py reconcile` resends the rest).

Header safety: every header value is built from validated data (the email
address passed validation.EMAIL_RE; names have CR/LF stripped), and Python's
EmailMessage refuses any header containing a newline as a second guard.
"""
from __future__ import annotations

import logging
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from html import escape

from . import config

log = logging.getLogger("careers.mailer")


def _password() -> str | None:
    return os.environ.get("GMAIL_APP_PASSWORD")


def _one_line(v) -> str:
    return re.sub(r"[\r\n]+", " ", str(v or "")).strip()


def _send(msg: EmailMessage, what: str, ref: str) -> bool:
    pw = _password()
    if not pw:
        log.info("%s: SMTP not configured; %s email skipped", ref, what)
        return False
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(config.SMTP_USER, pw)
            s.send_message(msg)
    except Exception as e:
        log.warning("%s: %s email failed: %s", ref, what, type(e).__name__)
        return False
    log.info("%s: %s email sent", ref, what)
    return True


def internal_subject(summary: dict) -> str:
    if summary["application_type"] == "expression_of_interest":
        return f"[Goji Careers] New expression of interest - {_one_line(summary['role'])}"
    return f"[Goji Careers] New application - {_one_line(summary['role'])}"


def internal_body(summary: dict, links: dict) -> str:
    a, ans = summary["applicant"], summary["answers"]
    pref = config.EMPLOYMENT.get(ans.get("employment_pref") or "", "")
    if ans.get("days_per_week") is not None:
        pref += f", {ans['days_per_week']} days/week"
        if ans.get("below_min_days"):
            pref += " (below the stated minimum)"
    kind = ("expression of interest" if summary["application_type"] == "expression_of_interest"
            else "application")
    lines = [
        f"A new {kind} has been received through the Goji Careers page.",
        "",
        f"Application reference: {summary['reference']}",
        f"Candidate: {_one_line(a['full_name'])}",
        f"Role: {_one_line(summary['role'])}",
        f"Employment preference: {pref}",
        f"Years of experience: {config.YEARS.get(ans.get('years_experience') or '', '')}",
    ]
    if ans.get("ahpc_status"):
        lines.append(f"AHPC registration status: {config.AHPC.get(ans['ahpc_status'], '')}")
    lines += [
        f"Earliest availability: {_one_line(ans.get('start_availability'))}",
        "",
        f"View application: {links['folder']}",
        f"View applicant tracker: {links['tracker']}",
        "",
        "The CV is in the application folder (not attached). Both links are "
        "private to the Goji Recruitment folder.",
    ]
    return "\n".join(lines)


def send_internal_notification(summary: dict, links: dict) -> bool:
    ref = summary["reference"]
    try:
        msg = EmailMessage()
        msg["Subject"] = internal_subject(summary)
        msg["From"] = formataddr(("Goji Careers", config.SMTP_USER))
        msg["To"] = config.ADMIN_EMAIL
        msg.set_content(internal_body(summary, links))
    except Exception as e:
        log.warning("%s: could not build internal email: %s", ref, type(e).__name__)
        return False
    return _send(msg, "internal notification", ref)


def applicant_lines(summary: dict) -> tuple[str, list[str]]:
    first = _one_line(summary["applicant"]["full_name"]).split(" ")[0] or "there"
    if summary["application_type"] == "expression_of_interest":
        middle = [
            "Thank you for taking the time to get in touch with us at Goji!",
            "",
            "We've received your expression of interest and look forward to "
            "learning more about you. We'll keep your details on file for "
            "suitable opportunities as they come up.",
        ]
    else:
        middle = [
            "Thank you for taking the time to apply to join us at Goji!",
            "",
            f"We've received your application for the {_one_line(summary['role'])} "
            "position and look forward to learning more about you.",
        ]
    lines = [
        f"Hi {first},",
        "",
        *middle,
        "",
        "Our team will review your application and be in touch should there "
        "be a suitable next step.",
        "",
        f"Your application reference is {summary['reference']}.",
        "",
        f"In the meantime, if you have any questions, feel free to reach us at "
        f"{config.SMTP_USER}.",
        "",
        "Thank you again for your interest in growing with us.",
        "",
        "Cheers,",
        "The Goji Team",
    ]
    return first, lines


def send_applicant_acknowledgement(summary: dict, links: dict) -> bool:
    ref = summary["reference"]
    to = summary["applicant"]["email"]
    if config.TEST_MODE:
        if not config.TEST_RECIPIENT:
            log.info("%s: test mode with no CAREERS_TEST_RECIPIENT; acknowledgement "
                     "not sent", ref)
            return False
        to = config.TEST_RECIPIENT
    try:
        _, lines = applicant_lines(summary)
        msg = EmailMessage()
        msg["Subject"] = "Thank you for your interest in Goji!"
        msg["From"] = formataddr((config.FROM_NAME, config.SMTP_USER))
        msg["To"] = to
        msg["Reply-To"] = config.SMTP_USER
        msg.set_content("\n".join(lines))
        html = "".join(f"<p>{escape(p).replace(chr(10), '<br>')}</p>"
                       for p in "\n".join(lines).split("\n\n"))
        msg.add_alternative(
            '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;'
            f'line-height:1.5;color:#3c1e1f">{html}</div>', subtype="html")
    except Exception as e:
        log.warning("%s: could not build acknowledgement: %s", ref, type(e).__name__)
        return False
    return _send(msg, "applicant acknowledgement", ref)
