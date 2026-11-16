import os, smtplib, ssl
from email.message import EmailMessage

def send_mail(to: str, subject: str, html: str, text: str = ""):
    msg = EmailMessage()
    msg["From"] = os.getenv("MAIL_FROM", os.getenv("SMTP_USER"))
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text or "Please view this email in an HTML-capable client.")
    msg.add_alternative(html, subtype="html")

    host = os.getenv("SMTP_HOST", "smtp.zoho.in")
    port = int(os.getenv("SMTP_PORT", "465"))
    user, pwd = os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")

    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=20) as s:
            s.login(user, pwd)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(user, pwd)
            s.send_message(msg)