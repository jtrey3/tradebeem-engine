import logging
from core.supabase_db import search_records, update_record
from core.activity import log_event
from handlers.actions import send_sms, send_email

logger = logging.getLogger(__name__)


def _fields(record: dict) -> dict:
    return record.get("fields", {})


def _db(client: dict):
    sb = client["supabase"]
    return sb["url"], sb["key"], sb["table"]


def run_pickup_notification(client: dict):
    cfg = client["automations"]["pickup_notification"]
    twilio = client["twilio"]
    url, key, table = _db(client)

    records = search_records(url, key, table)
    for rec in records:
        f = _fields(rec)
        if f.get("status") != cfg["trigger_status"]:
            continue
        if f.get(cfg["sent_flag"]):
            continue

        name = f.get("caller_name", "Customer")
        vehicle = f.get("vehicle", "your vehicle")
        phone = f.get("phone", "")
        email = f.get("email", "")
        shop = client["name"]
        shop_phone = client["phone"]

        if phone:
            try:
                send_sms(
                    twilio["account_sid"], twilio["auth_token"], twilio["from_number"],
                    phone,
                    f"Hey {name}, your {vehicle} is ready for pickup at {shop}. "
                    f"Give us a call if you have any questions: {shop_phone}"
                )
                logger.info(f"[{client['client_id']}] Pickup SMS sent to {name} ({phone})")
                log_event(client['client_id'], f"Pickup SMS sent to {name} ({phone})")
            except Exception as e:
                logger.error(f"[{client['client_id']}] Pickup SMS failed: {e}")
                log_event(client['client_id'], f"Pickup SMS failed: {e}", "ERROR")

        if email:
            try:
                send_email(
                    to=email,
                    subject=f"Your {vehicle} is Ready for Pickup — {shop}",
                    body=(
                        f"Hey {name},\n\n"
                        f"Great news — your {vehicle} is all done and ready for pickup at {shop}.\n\n"
                        f"Give us a call if you have any questions: {shop_phone}\n\n"
                        f"— {shop}"
                    ),
                    sender_email=client["gmail_sender"]
                )
                logger.info(f"[{client['client_id']}] Pickup email sent to {name} ({email})")
                log_event(client['client_id'], f"Pickup email sent to {name} ({email})")
            except Exception as e:
                logger.error(f"[{client['client_id']}] Pickup email failed: {e}")
                log_event(client['client_id'], f"Pickup email failed: {e}", "ERROR")

        try:
            send_sms(
                twilio["account_sid"], twilio["auth_token"], twilio["from_number"],
                client["owner_phone"],
                f"AUTO: Pickup notification sent to {name} for their {vehicle}."
            )
        except Exception as e:
            logger.error(f"[{client['client_id']}] Owner SMS failed: {e}")

        try:
            update_record(url, key, table, rec["id"], {cfg["sent_flag"]: True})
        except Exception as e:
            logger.error(f"[{client['client_id']}] Failed to mark {cfg['sent_flag']}: {e}")


def run_complete_notification(client: dict):
    cfg = client["automations"]["complete_notification"]
    url, key, table = _db(client)

    records = search_records(url, key, table)
    for rec in records:
        f = _fields(rec)
        if f.get("status") != cfg["trigger_status"]:
            continue
        if f.get(cfg["sent_flag"]):
            continue

        name = f.get("caller_name", "Customer")
        vehicle = f.get("vehicle", "your vehicle")
        email = f.get("email", "")
        shop = client["name"]
        shop_phone = client["phone"]

        if email:
            try:
                send_email(
                    to=email,
                    subject=f"Your {vehicle} Service is Complete — {shop}",
                    body=(
                        f"Hey {name},\n\n"
                        f"Your {vehicle} service has been completed at {shop}.\n\n"
                        f"If you have any questions, give us a call: {shop_phone}\n\n"
                        f"— {shop}"
                    ),
                    sender_email=client["gmail_sender"]
                )
                logger.info(f"[{client['client_id']}] Complete email sent to {name} ({email})")
                log_event(client['client_id'], f"Complete email sent to {name} ({email})")
            except Exception as e:
                logger.error(f"[{client['client_id']}] Complete email failed: {e}")
                log_event(client['client_id'], f"Complete email failed: {e}", "ERROR")

        try:
            update_record(url, key, table, rec["id"], {cfg["sent_flag"]: True})
        except Exception as e:
            logger.error(f"[{client['client_id']}] Failed to mark {cfg['sent_flag']}: {e}")


def run_google_review(client: dict):
    cfg = client["automations"]["google_review"]
    url, key, table = _db(client)

    records = search_records(url, key, table)
    for rec in records:
        f = _fields(rec)
        if f.get("status") != cfg["trigger_status"]:
            continue
        if f.get(cfg["sent_flag"]):
            continue
        if not f.get(cfg["required_field"]):
            continue

        name = f.get("caller_name", "Customer")
        vehicle = f.get("vehicle", "your vehicle")
        email = f.get("email", "")
        shop = client["name"]
        review_link = client["google_review_link"]

        if email:
            try:
                send_email(
                    to=email,
                    subject=f"Thanks for trusting {shop}, {name}!",
                    body=(
                        f"Hey {name},\n\n"
                        f"Thanks for bringing your {vehicle} to {shop}. We hope everything is running great!\n\n"
                        f"If we took care of you, a quick Google review would mean the world to us — "
                        f"it helps other truck owners find a shop they can trust:\n\n"
                        f"{review_link}\n\n"
                        f"Takes less than a minute and means a lot. Thank you!\n\n"
                        f"— {shop}\n{client['phone']}"
                    ),
                    sender_email=client["gmail_sender"]
                )
                logger.info(f"[{client['client_id']}] Review email sent to {name} ({email})")
                log_event(client['client_id'], f"Google review email sent to {name} ({email})")
            except Exception as e:
                logger.error(f"[{client['client_id']}] Review email failed: {e}")
                log_event(client['client_id'], f"Review email failed: {e}", "ERROR")

        try:
            update_record(url, key, table, rec["id"], {cfg["sent_flag"]: True})
        except Exception as e:
            logger.error(f"[{client['client_id']}] Failed to mark {cfg['sent_flag']}: {e}")


def run_declined_followup(client: dict):
    cfg = client["automations"]["declined_followup"]
    url, key, table = _db(client)

    records = search_records(url, key, table)
    for rec in records:
        f = _fields(rec)
        if f.get("status") != cfg["trigger_status"]:
            continue
        if f.get(cfg["sent_flag"]):
            continue
        declined = f.get(cfg["required_field"], "")
        if not declined:
            continue

        name = f.get("caller_name", "Customer")
        vehicle = f.get("vehicle", "your vehicle")
        email = f.get("email", "")
        shop = client["name"]
        shop_phone = client["phone"]

        if email:
            try:
                send_email(
                    to=email,
                    subject=f"Following up on your {vehicle} — {shop}",
                    body=(
                        f"Hey {name},\n\n"
                        f"Just checking in from {shop}. We wanted to follow up on the repairs "
                        f"that were recommended during your last visit on your {vehicle}:\n\n"
                        f"{declined}\n\n"
                        f"We want to keep your truck running strong. Want to get that scheduled "
                        f"before it becomes a bigger issue?\n\n"
                        f"Call or reply to this email: {shop_phone}\n\n"
                        f"— {shop}"
                    ),
                    sender_email=client["gmail_sender"]
                )
                logger.info(f"[{client['client_id']}] Declined follow-up sent to {name} ({email})")
                log_event(client['client_id'], f"Declined follow-up sent to {name} ({email})")
            except Exception as e:
                logger.error(f"[{client['client_id']}] Declined follow-up failed: {e}")
                log_event(client['client_id'], f"Declined follow-up failed: {e}", "ERROR")

        try:
            send_sms(
                client["twilio"]["account_sid"], client["twilio"]["auth_token"],
                client["twilio"]["from_number"], client["owner_phone"],
                f"AUTO: Declined follow-up sent to {name} re: {declined} on their {vehicle}."
            )
        except Exception as e:
            logger.error(f"[{client['client_id']}] Owner declined SMS failed: {e}")

        try:
            update_record(url, key, table, rec["id"], {cfg["sent_flag"]: True})
        except Exception as e:
            logger.error(f"[{client['client_id']}] Failed to mark {cfg['sent_flag']}: {e}")
