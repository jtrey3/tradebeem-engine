import json
import logging
import os
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from handlers.poller import (
    run_pickup_notification,
    run_complete_notification,
    run_google_review,
    run_declined_followup,
)
from handlers.webhook import handle_retell_post_call
from handlers.cal import get_available_slots, create_booking
from core.activity import get_activity, get_counts
from core.supabase_db import get_raw_records, update_record

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="TradeBeem Engine")
scheduler = BackgroundScheduler()
templates = Jinja2Templates(directory="templates")

CLIENTS_DIR = Path(__file__).parent / "clients"


def load_clients() -> list:
    clients = []
    for f in CLIENTS_DIR.glob("*.json"):
        with open(f) as fh:
            clients.append(json.load(fh))
    return clients


CLIENTS = load_clients()
logger.info(f"Loaded {len(CLIENTS)} client(s): {[c['client_id'] for c in CLIENTS]}")


def schedule_client(client: dict):
    cid = client["client_id"]
    automations = client.get("automations", {})

    jobs = {
        "pickup_notification": run_pickup_notification,
        "complete_notification": run_complete_notification,
        "google_review": run_google_review,
        "declined_followup": run_declined_followup,
    }

    for name, fn in jobs.items():
        cfg = automations.get(name, {})
        if not cfg.get("enabled", False):
            continue
        interval = cfg.get("poll_interval_seconds", 300)
        scheduler.add_job(
            fn,
            "interval",
            seconds=interval,
            args=[client],
            id=f"{cid}_{name}",
            replace_existing=True
        )
        logger.info(f"Scheduled {cid}/{name} every {interval}s")


@app.on_event("startup")
def startup():
    for client in CLIENTS:
        schedule_client(client)
    scheduler.start()
    logger.info("Scheduler started")


@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown()


# ── Dashboard ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    jobs = [
        {
            "id": j.id,
            "next_run": j.next_run_time.strftime("%H:%M:%S") if j.next_run_time else "paused"
        }
        for j in scheduler.get_jobs()
    ]
    fired_today, errors_today = get_counts()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "clients": CLIENTS,
        "jobs": jobs,
        "activity": get_activity(),
        "fired_today": fired_today,
        "errors_today": errors_today,
        "current_time": datetime.now().strftime("%b %d, %Y %H:%M"),
    })


@app.post("/dashboard/toggle")
def toggle_automation(client_id: str = Form(...), automation: str = Form(...)):
    client_file = CLIENTS_DIR / f"{client_id}.json"
    if not client_file.exists():
        raise HTTPException(status_code=404, detail="Client not found")

    with open(client_file) as f:
        config = json.load(f)

    cfg = config["automations"].get(automation)
    if not cfg:
        raise HTTPException(status_code=404, detail="Automation not found")

    cfg["enabled"] = not cfg.get("enabled", False)

    with open(client_file, "w") as f:
        json.dump(config, f, indent=2)

    for c in CLIENTS:
        if c["client_id"] == client_id:
            c["automations"][automation]["enabled"] = cfg["enabled"]
            break

    job_id = f"{client_id}_{automation}"
    if cfg["enabled"]:
        fn_map = {
            "pickup_notification": run_pickup_notification,
            "complete_notification": run_complete_notification,
            "google_review": run_google_review,
            "declined_followup": run_declined_followup,
        }
        fn = fn_map.get(automation)
        if fn:
            client = next(c for c in CLIENTS if c["client_id"] == client_id)
            interval = cfg.get("poll_interval_seconds", 300)
            scheduler.add_job(fn, "interval", seconds=interval, args=[client],
                              id=job_id, replace_existing=True)
    else:
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass

    return RedirectResponse("/", status_code=303)


@app.post("/dashboard/add-client")
def add_client(
    client_id: str = Form(...),
    name: str = Form(...),
    phone: str = Form(...),
    owner_phone: str = Form(...),
    airtable_base_id: str = Form(...),
    airtable_table_id: str = Form(...),
    airtable_token: str = Form(...),
    twilio_sid: str = Form(...),
    twilio_token: str = Form(default=""),
    twilio_from: str = Form(...),
    gmail_sender: str = Form(...),
):
    config = {
        "client_id": client_id,
        "name": name,
        "phone": phone,
        "owner_phone": owner_phone,
        "owner_email": gmail_sender,
        "google_review_link": "",
        "airtable": {
            "base_id": airtable_base_id,
            "table_id": airtable_table_id,
            "token": airtable_token,
        },
        "twilio": {
            "account_sid": twilio_sid,
            "auth_token": twilio_token,
            "from_number": twilio_from,
        },
        "gmail_sender": gmail_sender,
        "automations": {
            "pickup_notification": {
                "enabled": True,
                "poll_interval_seconds": 120,
                "trigger_status": "Ready For Pickup",
                "sent_flag": "pickup_notification_sent"
            },
            "complete_notification": {
                "enabled": True,
                "poll_interval_seconds": 120,
                "trigger_status": "Complete",
                "sent_flag": "complete_notification_sent"
            },
            "google_review": {
                "enabled": True,
                "poll_interval_seconds": 300,
                "trigger_status": "Complete",
                "required_field": "work_performed",
                "sent_flag": "review_requested"
            },
            "declined_followup": {
                "enabled": True,
                "poll_interval_seconds": 300,
                "trigger_status": "Complete",
                "required_field": "declined_work",
                "sent_flag": "declined_followup_sent"
            }
        }
    }

    client_file = CLIENTS_DIR / f"{client_id}.json"
    with open(client_file, "w") as f:
        json.dump(config, f, indent=2)

    CLIENTS.append(config)
    schedule_client(config)
    logger.info(f"New client added via dashboard: {client_id}")

    return RedirectResponse("/", status_code=303)


# ── Leads CRM ──────────────────────────────────────────────────────────────────

@app.get("/clients/{client_id}/leads", response_class=HTMLResponse)
def leads_view(client_id: str, request: Request):
    client = next((c for c in CLIENTS if c["client_id"] == client_id), None)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    sb = client["supabase"]
    records = get_raw_records(sb["url"], sb["key"], sb["table"])
    return templates.TemplateResponse("leads.html", {
        "request": request,
        "client": client,
        "records": records,
    })


@app.post("/clients/{client_id}/leads/update")
def leads_update(
    client_id: str,
    record_id: str = Form(...),
    status: str = Form(default=""),
    work_performed: str = Form(default=""),
    declined_work: str = Form(default=""),
):
    client = next((c for c in CLIENTS if c["client_id"] == client_id), None)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    sb = client["supabase"]
    fields = {"status": status, "work_performed": work_performed, "declined_work": declined_work}
    update_record(sb["url"], sb["key"], sb["table"], record_id, fields)

    # Trigger automations immediately on save instead of waiting for next poll
    run_pickup_notification(client)
    run_complete_notification(client)
    run_google_review(client)
    run_declined_followup(client)

    return RedirectResponse(f"/clients/{client_id}/leads", status_code=303)


# ── Cal.com Tools (called by Retell agent during live calls) ───────────────────

@app.api_route("/tools/{client_id}/cal/slots", methods=["GET", "POST"])
async def cal_slots(client_id: str, request: Request):
    client = next((c for c in CLIENTS if c["client_id"] == client_id), None)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    params = dict(request.query_params)
    if request.method == "POST":
        try:
            body = await request.json()
            params.update(body)
        except Exception:
            pass
    start = params.get("start")
    end = params.get("end")
    cal = client.get("cal", {})
    slots = get_available_slots(cal["api_key"], cal["event_type_id"], start, end)
    return {"slots": slots}


@app.post("/tools/{client_id}/cal/book")
async def cal_book(client_id: str, request: Request):
    client = next((c for c in CLIENTS if c["client_id"] == client_id), None)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    body = await request.json()
    cal = client.get("cal", {})
    booking = create_booking(
        cal["api_key"],
        cal["event_type_id"],
        body["start"],
        body["name"],
        body.get("email"),
        body.get("timezone", "America/Chicago"),
    )
    logger.info(f"[{client_id}] Cal.com booking created: {booking.get('uid')}")
    return {"status": "booked", "booking": booking}


# ── Misc Tools (called by Retell agent during live calls) ──────────────────────

@app.get("/tools/{client_id}/lookup-job")
def lookup_job(client_id: str, phone: str = None, name: str = None):
    client = next((c for c in CLIENTS if c["client_id"] == client_id), None)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    sb = client["supabase"]
    records = get_raw_records(sb["url"], sb["key"], sb["table"])

    match = None
    for rec in records:
        if phone and rec.get("phone", "").replace(" ", "").replace("-", "") in phone.replace(" ", "").replace("-", ""):
            match = rec
            break
        if name and name.lower() in (rec.get("caller_name") or "").lower():
            match = rec
            break

    if not match:
        return {"found": False, "message": "No job found for that customer."}

    return {
        "found": True,
        "name": match.get("caller_name"),
        "vehicle": match.get("vehicle"),
        "status": match.get("status"),
        "issue": match.get("issue"),
        "work_performed": match.get("work_performed") or "Not yet documented",
    }


@app.api_route("/tools/{client_id}/todays-date", methods=["GET", "POST"])
def todays_date(client_id: str):
    from datetime import date
    today = date.today()
    return {
        "date": today.isoformat(),
        "formatted": today.strftime("%A, %B %d, %Y"),
        "day_of_week": today.strftime("%A"),
    }


@app.post("/tools/{client_id}/send-photo-link")
async def send_photo_link(client_id: str, request: Request):
    client = next((c for c in CLIENTS if c["client_id"] == client_id), None)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    body = await request.json()
    phone = body.get("phone", "")
    name = body.get("name", "there")
    record_id = body.get("record_id", "")
    first_name = name.split()[0] if name else "there"

    photo_url = (
        f"https://johnc3.app.n8n.cloud/webhook/photo-upload"
        f"?record_id={record_id}&name={name}&phone={phone}"
    )

    twilio = client["twilio"]
    from handlers.actions import send_sms
    try:
        send_sms(
            twilio["account_sid"], twilio["auth_token"], twilio["from_number"],
            phone,
            f"Hey {first_name}, here's a link to upload photos of your truck or dash codes — "
            f"it helps our team get a head start: {photo_url}"
        )
        logger.info(f"[{client_id}] Photo link SMS sent to {phone}")
        return {"status": "sent"}
    except Exception as e:
        logger.error(f"[{client_id}] Photo link SMS failed: {e}")
        return {"status": "failed", "error": str(e)}


# ── Webhook endpoints ──────────────────────────────────────────────────────────

@app.post("/webhook/{client_id}/retell-post-call")
async def retell_post_call(client_id: str, request: Request):
    client = next((c for c in CLIENTS if c["client_id"] == client_id), None)
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")

    payload = await request.json()
    handle_retell_post_call(payload, client)
    return {"status": "ok"}


@app.get("/health")
def health():
    jobs = [{"id": j.id, "next_run": str(j.next_run_time)} for j in scheduler.get_jobs()]
    return {"status": "ok", "clients": len(CLIENTS), "jobs": jobs}
