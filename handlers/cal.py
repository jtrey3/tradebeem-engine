import httpx
import logging

logger = logging.getLogger(__name__)

CAL_BASE = "https://api.cal.com/v2"


def get_available_slots(api_key: str, event_type_id: int, start: str, end: str) -> list:
    """
    Returns available slots between start and end.
    start/end should be YYYY-MM-DD strings (e.g. "2026-03-12").
    """
    # Strip time component if passed as ISO datetime
    start_date = start[:10] if start else ""
    end_date = end[:10] if end else ""
    headers = {"Authorization": f"Bearer {api_key}", "cal-api-version": "2024-09-04"}
    params = {
        "eventTypeId": event_type_id,
        "start": start_date,
        "end": end_date,
    }
    resp = httpx.get(f"{CAL_BASE}/slots", headers=headers, params=params, timeout=10)
    logger.info(f"Cal slots response {resp.status_code}: {resp.text[:500]}")
    resp.raise_for_status()
    data = resp.json()
    # Flatten the date-keyed dict into a list of slot start times
    slots_by_date = data.get("data", {})
    flat = []
    for date_key, slot_list in slots_by_date.items():
        for slot in slot_list:
            flat.append(slot.get("start", ""))
    return [s for s in flat if s]


def create_booking(api_key: str, event_type_id: int, start: str, name: str, email: str = None, timezone: str = "America/Chicago") -> dict:
    """
    Books a slot. start is ISO 8601 e.g. "2026-03-13T10:00:00Z"
    Returns the booking object.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "cal-api-version": "2024-08-13",
        "Content-Type": "application/json",
    }
    payload = {
        "eventTypeId": event_type_id,
        "start": start,
        "attendee": {
            "name": name,
            "email": email or "noemail@placeholder.com",
            "timeZone": timezone,
        },
    }
    resp = httpx.post(f"{CAL_BASE}/bookings", headers=headers, json=payload, timeout=10)
    logger.info(f"Cal booking response {resp.status_code}: {resp.text[:500]}")
    resp.raise_for_status()
    return resp.json().get("data", {})
