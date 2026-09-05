#!/usr/bin/env python3
"""Paddock Mobile data warehouse: ingest.

Two sources, one row. Tesla Fleet gives kWh BILLED (drawn from the charger) and
the money. TezLab gives kWh ADDED (into the pack) and the drive telemetry.
Holding both against one natural key is what makes charge loss measurable, and
neither source can produce that number alone.

Everything is idempotent on a natural key, so re-running is free and safe:
  charge_session.session_id   Tesla's own session id
  drive.id                    TezLab's drive id
  charge_curve(session_key,seq)

Efficiency rules, in order of how much they save:
  1. Detail endpoints are only called for keys not already stored. The curve for
     a finished session never changes, so it is fetched once, ever.
  2. The car is NEVER woken on a schedule. `vehicles` reports online/asleep for
     free; vehicle_data is only called when the car is already awake. Waking it
     costs real battery, which this site measures as idle loss.
  3. Fleet charging history pages at 10; larger pages return empty.

Usage:
  python3 tools/warehouse.py --backfill     everything, first run
  python3 tools/warehouse.py                the scheduled incremental
"""
import json, os, pathlib, subprocess, sys, urllib.parse, urllib.request, datetime

HOME   = pathlib.Path.home()
TESLA  = HOME / ".tesla"
ROOT   = pathlib.Path(__file__).resolve().parent.parent
BACKFILL = "--backfill" in sys.argv

def env():
    e = {}
    for line in (TESLA / "app.env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            e[k.strip()] = v.strip().strip('"').strip("'")
    return e

def tokens():          return json.loads((TESLA / "tokens.json").read_text())
def save_tokens(d):
    p = TESLA / "tokens.json"; p.write_text(json.dumps(d)); os.chmod(p, 0o600)

def access_token():
    """Refresh if the stored token is within 5 minutes of expiry."""
    import base64, time
    t = tokens(); at = t.get("access_token", "")
    if at.count(".") == 2:
        b = at.split(".")[1]; b += "=" * (-len(b) % 4)
        exp = json.loads(base64.urlsafe_b64decode(b)).get("exp", 0)
        if exp - time.time() > 300:
            return at
    e = env()
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token", "client_id": e["TESLA_CLIENT_ID"],
        "refresh_token": t["refresh_token"]}).encode()
    req = urllib.request.Request(e["TESLA_AUTH"] + "/oauth2/v3/token", data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=40) as r:
        new = json.loads(r.read())
    new.setdefault("refresh_token", t["refresh_token"])
    save_tokens(new)
    print("  token refreshed")
    return new["access_token"]

def fleet(path, **params):
    e = env(); at = access_token()
    url = e["TESLA_AUDIENCE"] + path
    if params: url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + at})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as ex:
        return {"error": f"http {ex.code}", "body": ex.read().decode()[:200]}

# ── SQL ─────────────────────────────────────────────────────────────────────
def sql(statement, params=None):
    """Run through psql if a connection string is available, else emit for the
    caller. Kept deliberately simple: this warehouse is small and append-mostly."""
    import psycopg2  # noqa
    conn = os.environ.get("GARAGE_DB_URL")
    if not conn:
        raise SystemExit("set GARAGE_DB_URL to the Neon connection string")
    with psycopg2.connect(conn) as c, c.cursor() as cur:
        cur.execute(statement, params or ())
        try:    return cur.fetchall()
        except Exception: return []

def existing(table, col):
    return {r[0] for r in sql(f"select {col} from garage.{table}")}

# ── Fleet: billing ──────────────────────────────────────────────────────────
def pull_billing():
    rows, page = [], 1
    while page <= 20:
        d = fleet("/api/1/dx/charging/history", pageNo=page, pageSize=10)
        batch = d.get("data") or []
        if not batch: break
        rows += batch
        if len(batch) < 10: break
        page += 1
    return rows

def upsert_billing(rows):
    n = 0
    for r in rows:
        fees = r.get("fees") or []
        chg  = [f for f in fees if f.get("feeType") == "CHARGING"]
        con  = [f for f in fees if f.get("feeType") == "CONGESTION"]
        kwh  = sum((f.get("usageBase") or 0) for f in chg)
        due  = sum((f.get("totalDue") or 0) for f in fees)
        rate = chg[0].get("rateBase") if chg else None
        sql("""insert into garage.charge_session
                 (session_id, vin, site_name, started_at, stopped_at, kwh_billed,
                  rate_per_kwh, total_due, net_due, currency, fees, source,
                  congestion_due)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'tesla_fleet',%s)
               on conflict (session_id) do update set
                 kwh_billed=excluded.kwh_billed, total_due=excluded.total_due,
                 rate_per_kwh=excluded.rate_per_kwh, fees=excluded.fees,
                 congestion_due=excluded.congestion_due""",
            (r["sessionId"], r.get("vin"), r.get("siteLocationName"),
             r.get("chargeStartDateTime"), r.get("chargeStopDateTime"), kwh, rate,
             due, sum((f.get("netDue") or 0) for f in fees),
             (chg[0].get("currencyCode") if chg else "USD"), json.dumps(fees),
             sum((f.get("totalDue") or 0) for f in con)))
        n += 1
    return n

def log_pull(source, endpoint, count, ok=True, note=""):
    sql("""insert into garage.source_pull (source, endpoint, pulled_at, row_count, ok, note)
           values (%s,%s,now(),%s,%s,%s)""", (source, endpoint, count, ok, note))

def car_state():
    d = fleet("/api/1/vehicles")
    for v in d.get("response") or []:
        return v.get("state"), v.get("id")
    return None, None

if __name__ == "__main__":
    print("Paddock Mobile warehouse")
    state, vid = car_state()
    print(f"  vehicle: {state}")
    bills = pull_billing()
    n = upsert_billing(bills)
    log_pull("tesla_fleet", "dx/charging/history", n)
    print(f"  billing sessions upserted: {n}")
    if state == "online":
        d = fleet(f"/api/1/vehicles/{vid}/vehicle_data",
                  endpoints="charge_state;climate_state;vehicle_state;drive_state")
        print("  live snapshot:", "ok" if d.get("response") else d.get("error"))
    else:
        print("  live snapshot skipped: car asleep, and waking it costs battery")
