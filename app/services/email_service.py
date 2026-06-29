import os
import smtplib
from email.message import EmailMessage


def send_email(to_email, subject, body, attachments=None):
    user = os.getenv("GMAIL_SMTP_USER")
    password = os.getenv("GMAIL_SMTP_PASSWORD")
    mail_from = os.getenv("MAIL_FROM", user or "no-reply@example.com")
    if not user or not password:
        print("EMAIL NOT SENT - configure GMAIL_SMTP_USER and GMAIL_SMTP_PASSWORD")
        print(to_email, subject, body)
        return False

    msg = EmailMessage()
    msg["From"] = mail_from
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    for path in attachments or []:
        if not path or not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            data = f.read()
        filename = os.path.basename(path)
        msg.add_attachment(data, maintype="application", subtype="octet-stream", filename=filename)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    return True
