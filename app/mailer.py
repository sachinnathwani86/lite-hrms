import smtplib
from email.message import EmailMessage

from flask import current_app


def mail_configured():
    return bool(current_app.config.get("MAIL_SERVER"))


def send_email(to_address, subject, body):
    """Send a plain-text email using the configured SMTP server."""
    config = current_app.config
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.get("MAIL_DEFAULT_SENDER") or config.get("MAIL_USERNAME")
    message["To"] = to_address
    message.set_content(body)

    smtp_class = smtplib.SMTP_SSL if config.get("MAIL_USE_SSL") else smtplib.SMTP
    with smtp_class(config["MAIL_SERVER"], config.get("MAIL_PORT"), timeout=15) as server:
        if config.get("MAIL_USE_TLS") and not config.get("MAIL_USE_SSL"):
            server.starttls()
        if config.get("MAIL_USERNAME"):
            server.login(config["MAIL_USERNAME"], config.get("MAIL_PASSWORD") or "")
        server.send_message(message)
