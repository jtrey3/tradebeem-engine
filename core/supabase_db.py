from supabase import create_client


def get_client(url: str, key: str):
    return create_client(url, key)


def search_records(url: str, key: str, table: str, status_filter: str = None) -> list:
    """Return records in Airtable-compatible shape: [{"id": ..., "fields": {...}}]"""
    client = get_client(url, key)
    query = client.table(table).select("*")
    resp = query.execute()
    rows = resp.data or []

    # Normalize to same shape the pollers expect
    records = []
    for row in rows:
        record_id = row.get("id")
        fields = {k: v for k, v in row.items() if k != "id"}
        records.append({"id": record_id, "fields": fields})

    return records


def update_record(url: str, key: str, table: str, record_id: str, fields: dict):
    """Update a record. Accepts display-name fields and maps to column names."""
    client = get_client(url, key)

    # Map any display-name keys to snake_case columns
    mapped = fields
    client.table(table).update(mapped).eq("id", record_id).execute()


def find_record_by_field(url: str, key: str, table: str, field: str, value: str) -> dict | None:
    """Return the first record matching field=value, or None."""
    client = get_client(url, key)
    resp = client.table(table).select("id").eq(field, value).limit(1).execute()
    return resp.data[0] if resp.data else None


def get_raw_records(url: str, key: str, table: str) -> list:
    """Return all records as raw dicts, ordered by timestamp desc."""
    client = get_client(url, key)
    resp = client.table(table).select("*").order("timestamp", desc=True).execute()
    return resp.data or []


def insert_record(url: str, key: str, table: str, fields: dict) -> str:
    """Insert a new record, return the new row id."""
    client = get_client(url, key)
    resp = client.table(table).insert(fields).execute()
    return resp.data[0]["id"] if resp.data else None


def upload_photo(url: str, key: str, bucket: str, path: str, data: bytes, content_type: str) -> str:
    """Upload a file to Supabase Storage. Returns the public URL."""
    client = get_client(url, key)
    try:
        client.storage.create_bucket(bucket, options={"public": True})
    except Exception:
        pass  # Bucket already exists
    client.storage.from_(bucket).upload(path, data, {"content-type": content_type, "upsert": "true"})
    return client.storage.from_(bucket).get_public_url(path)
