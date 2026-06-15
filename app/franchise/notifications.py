from datetime import date, datetime, timezone
from flask import current_app
from flask_mail import Message
from app.extensions import db, mail
from app.models import Franchise


def send_agreement_expiry_reminders():
    """Send 60-day and 30-day franchise agreement expiry reminders.

    This is designed to be called by a scheduled job such as cron:
    flask check-franchise-expiry
    """
    today = date.today()
    sent_count = 0
    franchises = Franchise.query.filter(Franchise.agreement_end_date.isnot(None)).all()

    for franchise in franchises:
        days_left = (franchise.agreement_end_date - today).days
        recipients = [email for email in [franchise.regional_manager_email, franchise.finance_manager_email] if email]
        if not recipients:
            continue

        if days_left == 60 and not franchise.notification_60_sent_at:
            _send_email(franchise, recipients, 60)
            franchise.notification_60_sent_at = datetime.now(timezone.utc)
            sent_count += 1
        elif days_left == 30 and not franchise.notification_30_sent_at:
            _send_email(franchise, recipients, 30)
            franchise.notification_30_sent_at = datetime.now(timezone.utc)
            sent_count += 1

    db.session.commit()
    return sent_count


def _send_email(franchise, recipients, days_left):
    subject = f"Franchise Agreement Expiry Reminder: {franchise.business_name}"
    body = f"""
Good day,

This is an automated reminder from the Martins Funerals System.

The franchise agreement for {franchise.business_name} expires in {days_left} days.

Agreement end date: {franchise.agreement_end_date}
Franchisee: {franchise.franchisee_full_name or 'Not captured'}
Office number: {franchise.office_number or 'Not captured'}
24-hour number: {franchise.after_hours_number or 'Not captured'}

Please review the agreement and take the required action.

Kind regards,
Martins Funerals System
""".strip()
    message = Message(subject=subject, recipients=recipients, body=body, sender=current_app.config.get("MAIL_DEFAULT_SENDER"))
    mail.send(message)
