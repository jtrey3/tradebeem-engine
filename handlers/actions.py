import httpx
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os


def send_sms(account_sid: str, auth_token: str, from_number: str, to_number: str, body: str):
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    resp = httpx.post(
        url,
        auth=(account_sid, auth_token),
        data={"From": from_number, "To": to_number, "Body": body},
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()


def send_email(to: str, subject: str, body: str, sender_email: str = None):
    """Send email via Gmail SMTP using app password from env."""
    gmail_user = sender_email or os.getenv("GMAIL_USER") or "tyb.447@gmail.com"
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD") or "esiiOsfaycodhvkv"

    if not gmail_user or not gmail_pass:
        raise ValueError("GMAIL_USER and GMAIL_APP_PASSWORD must be set in environment")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = to
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_pass)
        server.sendmail(gmail_user, to, msg.as_string())
