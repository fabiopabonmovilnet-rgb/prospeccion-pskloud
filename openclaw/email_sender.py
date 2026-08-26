"""
Email sender module for PSKloud Prospector.
Supports SMTP with TLS, HTML/text, and open tracking.
"""
from __future__ import annotations

import logging
import smtplib
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from models import EmailChannel

logger = logging.getLogger("openclaw.email")

TRACKING_PIXEL = (
    "<img src='https://openclaw:9000/track/open/{email_id}' "
    "width='1' height='1' style='display:none' />"
)


def send_email(
    channel: EmailChannel,
    to_email: str,
    to_name: str,
    subject: str,
    body_text: str,
) -> bool:
    try:
        email_id = uuid.uuid4().hex[:12]

        msg = MIMEMultipart("alternative")
        msg["From"] = f"{channel.from_name} <{channel.from_email}>"
        msg["To"] = f"{to_name} <{to_email}>"
        msg["Subject"] = subject

        html_body = body_text.replace("\n", "<br>")
        html = f"""<!DOCTYPE html>
<html><body style="font-family:sans-serif;color:#333;line-height:1.6;">
{html_body}
<br><br>
<small style="color:#999;">— {channel.from_name}</small>
{TRACKING_PIXEL.format(email_id=email_id)}
</body></html>"""

        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(channel.smtp_host, channel.smtp_port, timeout=15) as server:
            server.starttls()
            server.login(channel.smtp_user, channel.smtp_password)
            server.sendmail(channel.from_email, [to_email], msg.as_string())

        logger.info(f"Email sent to {to_name} <{to_email}> (id={email_id})")
        return True

    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False
