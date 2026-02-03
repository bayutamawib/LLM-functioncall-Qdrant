# save as validate_ingestion.py and run: python validate_ingestion.py
import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_BASE = os.getenv("QDRANT_BASE_URL") or f"http://{QDRANT_HOST}:{QDRANT_PORT}"
COLLECTION = os.getenv("QDRANT_COLLECTION", "sales_vol_staging")
BATCH = int(os.getenv("VALIDATOR_BATCH", "500"))

def parse_iso_date(s):
    if not s:
        return None
    try:
        # accept "YYYY-MM" or full ISO
        if len(s) == 7 and s[4] == "-":
            return datetime.strptime(s, "%Y-%m")
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

def scroll_points(collection, batch_size=500):
    url = f"{QDRANT_BASE}/collections/{collection}/points/scroll"
    headers = {"Content-Type": "application/json"}
    offset = None
    while True:
        body = {"limit": batch_size, "with_payload": True}
        if offset:
            body["offset"] = offset
        r = requests.post(url, headers=headers, data=json.dumps(body), timeout=30)
        r.raise_for_status()
        resp = r.json()
        points = resp.get("result") or resp.get("result", {}).get("points") or resp.get("points") or []
        if not points:
            break
        for p in points:
            yield p
        offset = resp.get("next_page") or resp.get("offset") or None
        if not offset:
            break

def validate():
    total = 0
    bad_date = 0
    bad_sales = 0
    missing_sales = 0
    missing_date = 0
    samples = []

    for p in scroll_points(COLLECTION, BATCH):
        total += 1
        pid = p.get("id")
        payload = p.get("payload", {}) or {}
        month_year = payload.get("month_year")
        sales = payload.get("sales") or payload.get("sales_amount") or payload.get("sales_vol")

        date_ok = parse_iso_date(month_year) is not None
        if not month_year:
            missing_date += 1
        if not date_ok and month_year:
            bad_date += 1

        if sales is None:
            missing_sales += 1
        else:
            try:
                if isinstance(sales, str):
                    sales_clean = sales.replace(",", "")
                else:
                    sales_clean = sales
                float(sales_clean)
            except Exception:
                bad_sales += 1

        if (not date_ok) or (sales is None) or (bad_sales > 0 and total <= 10):
            samples.append({"id": pid, "month_year": month_year, "sales": sales})

    print("collection,", COLLECTION)
    print("total_points,", total)
    print("missing_date,", missing_date)
    print("bad_date_format,", bad_date)
    print("missing_sales,", missing_sales)
    print("bad_sales_format,", bad_sales)
    print("\nSAMPLE_PROBLEMS (first 20):")
    for s in samples[:20]:
        print(json.dumps(s))

if __name__ == "__main__":
    validate()
