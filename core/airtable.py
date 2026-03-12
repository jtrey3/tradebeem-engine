import httpx

BASE_URL = "https://api.airtable.com/v0"


def get_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def search_records(base_id: str, table_id: str, token: str) -> list:
    url = f"{BASE_URL}/{base_id}/{table_id}"
    records = []
    offset = None

    while True:
        params = {}
        if offset:
            params["offset"] = offset

        resp = httpx.get(url, headers=get_headers(token), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))

        offset = data.get("offset")
        if not offset:
            break

    return records


def update_record(base_id: str, table_id: str, record_id: str, token: str, fields: dict) -> dict:
    url = f"{BASE_URL}/{base_id}/{table_id}/{record_id}"
    resp = httpx.patch(url, headers=get_headers(token), json={"fields": fields}, timeout=30)
    resp.raise_for_status()
    return resp.json()
