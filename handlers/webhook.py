import logging
from core.supabase_db import insert_record, search_records
from handlers.actions import send_sms, send_email

logger = logging.getLogger(__name__)


def handle_retell_post_call(payload: dict, client: dict):
    """Process Retell AI post-call webhook and log to Supabase + send notifications."""
    event = payload.get("event")
    if event != "call_analyzed":
        logger.info(f"[{client['client_id']}] Ignoring event: {event}")
        return

    sb = client["supabase"]
    twilio = client["twilio"]

    logger.info(f"[{client['client_id']}] Raw webhook payload keys: {list(payload.keys())}")
    call = payload.get("call", {})
    call_analysis = call.get("call_analysis") or payload.get("call_analysis") or {}
    logger.info(f"[{client['client_id']}] call_analysis keys: {list(call_analysis.keys()) if call_analysis else 'EMPTY'}")
    custom_analysis = call_analysis.get("custom_analysis_data", {})

    caller_name = custom_analysis.get("caller_name", "")
    phone = call.get("from_number", custom_analysis.get("phone_number", ""))
    email = custom_analysis.get("email", "")
    company = custom_analysis.get("company_name", "")
    vehicle_year = custom_analysis.get("vehicle_year", "")
    vehicle_make = custom_analysis.get("vehicle_make", "")
    vehicle_model = custom_analysis.get("vehicle_model", "")
    engine = custom_analysis.get("engine_type", "")
    mileage = custom_analysis.get("mileage", "")
    vin = custom_analysis.get("vin", "")
    issue = custom_analysis.get("issue_description", "")
    fault_codes = custom_analysis.get("fault_codes", "")
    is_drivable = custom_analysis.get("is_drivable", "unknown")
    urgency = custom_analysis.get("urgency", "medium")
    scheduling = custom_analysis.get("preferred_schedule", "")
    call_type = custom_analysis.get("call_type", "repair")
    bucket = custom_analysis.get("bucket", "shop_service")
    is_new = custom_analysis.get("is_new_customer", True)
    summary = call_analysis.get("call_summary", "")
    duration = call.get("duration_ms", 0) // 1000
    call_id = call.get("call_id", "")
    timestamp = call.get("start_timestamp", "")
    recording_url = call.get("recording_url", "")

    vehicle = f"{vehicle_year} {vehicle_make} {vehicle_model}".strip()
    first_name = caller_name.split()[0] if caller_name else "there"

    fields = {
        "caller_name": caller_name,
        "phone": phone,
        "email": email,
        "company": company,
        "vehicle": vehicle,
        "engine": engine,
        "mileage": str(mileage) if mileage else None,
        "vin": vin,
        "issue": issue,
        "fault_codes": fault_codes,
        "is_drivable": str(is_drivable),
        "urgency": urgency,
        "scheduling": scheduling,
        "call_type": call_type,
        "bucket": bucket,
        "is_new_customer": is_new,
        "summary": summary,
        "duration_s": duration,
        "call_id": call_id,
        "timestamp": str(timestamp),
        "recording_url": recording_url,
        "photo_uploaded": "No",
        "status": "New",
    }

    fields = {k: v for k, v in fields.items() if v not in (None, "", 0)}

    # Prevent duplicate inserts for same call_id
    if call_id:
        existing = search_records(sb["url"], sb["key"], sb["table"])
        for rec in existing:
            if rec.get("fields", {}).get("call_id") == call_id or rec.get("call_id") == call_id:
                logger.info(f"[{client['client_id']}] Duplicate call_id {call_id}, skipping insert")
                return

    try:
        record_id = insert_record(sb["url"], sb["key"], sb["table"], fields)
        logger.info(f"[{client['client_id']}] Call logged: {caller_name} ({record_id})")
    except Exception as e:
        logger.error(f"[{client['client_id']}] Failed to log call to Supabase: {e}")
        return

    photo_upload_url = (
        f"https://johnc3.app.n8n.cloud/webhook/photo-upload"
        f"?record_id={record_id}&name={caller_name}&phone={phone}"
    )
    if phone:
        try:
            send_sms(
                twilio["account_sid"], twilio["auth_token"], twilio["from_number"],
                phone,
                f"Hey {first_name}, thanks for calling {client['name']}! "
                f"Here's a link to upload any photos of your truck or dash codes — "
                f"it helps our team get a head start: {photo_upload_url} "
                f"We'll be in touch shortly."
            )
            logger.info(f"[{client['client_id']}] Photo upload SMS sent to {phone}")
        except Exception as e:
            logger.error(f"[{client['client_id']}] Photo upload SMS failed: {e}")

    urgency_flag = " 🚨 TRUCK DOWN" if urgency in ("truck_down", "emergency") else ""
    try:
        send_sms(
            twilio["account_sid"], twilio["auth_token"], twilio["from_number"],
            client["owner_phone"],
            f"New call from {caller_name}{urgency_flag} — {vehicle} ({engine}). "
            f"Issue: {issue}. Fault codes: {fault_codes or 'none'}. "
            f"Drivable: {is_drivable}. Urgency: {urgency}. "
            f"Call back: {phone}"
        )
        logger.info(f"[{client['client_id']}] Owner notified for call from {caller_name}")
    except Exception as e:
        logger.error(f"[{client['client_id']}] Owner notification failed: {e}")
