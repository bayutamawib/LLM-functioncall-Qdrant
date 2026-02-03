import os
import logging
import json
import math
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse
from openrouter_embedder import OpenRouterEmbedder

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
embeddings = OpenRouterEmbedder(model="openai/text-embedding-3-small")

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_BASE = os.getenv("QDRANT_BASE_URL") or f"http://{QDRANT_HOST}:{QDRANT_PORT}"
DEFAULT_COLLECTION = os.getenv("QDRANT_COLLECTION", "sales_vol_staging")

app = FastAPI(title="Qdrant Chatbot (HTTP)")

@app.get("/")
async def read_index():
    index_path = os.path.join("templates", "index.html")
    if not os.path.exists(index_path):
        return JSONResponse({"error": "index.html not found in templates/ directory"}, status_code=404)
    return FileResponse(index_path)

@app.get("/health")
async def health():
    try:
        resp = requests.get(f"{QDRANT_BASE}/collections", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        collections = data.get("collections") if isinstance(data, dict) else []
        return {"status": "ok", "collections_count": len(collections)}
    except Exception as e:
        logger.exception("Qdrant health check failed")
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)

def http_search_collection(collection_name: str, query_vector: list, limit: int = 10, with_payload: bool = True):
    headers = {"Content-Type": "application/json"}
    body_search = {"vector": query_vector, "limit": limit, "with_payload": with_payload}
    search_url = f"{QDRANT_BASE}/collections/{collection_name}/points/search"
    try:
        r = requests.post(search_url, headers=headers, data=json.dumps(body_search), timeout=10)
        if r.status_code == 200:
            resp = r.json()
            result = resp.get("result")
            if isinstance(result, dict) and "points" in result:
                points = result["points"]
            elif isinstance(result, list):
                points = result
            else:
                points = resp.get("result", [])
            hits = []
            for p in points:
                pid = p.get("id") if isinstance(p, dict) else None
                payload = p.get("payload") if isinstance(p, dict) else {}
                score = p.get("score") if isinstance(p, dict) else None
                hits.append({"id": pid, "score": score, "payload": payload or {}})
            logger.debug("http_search_collection used /points/search")
            return hits
        else:
            logger.debug("points/search returned status %s: %s", r.status_code, r.text)
    except Exception:
        logger.debug("points/search failed, trying /points/query", exc_info=True)

    query_url = f"{QDRANT_BASE}/collections/{collection_name}/points/query"
    body_query = {"vector": query_vector, "limit": limit, "with_payload": with_payload}
    try:
        r = requests.post(query_url, headers=headers, data=json.dumps(body_query), timeout=10)
        r.raise_for_status()
        resp = r.json()
        result = resp.get("result")
        if isinstance(result, dict) and "points" in result:
            points = result["points"]
        elif isinstance(result, list):
            points = result
        else:
            points = resp.get("result", [])
        hits = []
        for p in points:
            pid = p.get("id") if isinstance(p, dict) else None
            payload = p.get("payload") if isinstance(p, dict) else {}
            score = p.get("score") if isinstance(p, dict) else None
            hits.append({"id": pid, "score": score, "payload": payload or {}})
        logger.debug("http_search_collection used /points/query")
        return hits
    except Exception:
        logger.exception("points/query failed")

    raise RuntimeError("No compatible HTTP search endpoint available on Qdrant")

def query_qdrant(user_input: str, collection_name: str = DEFAULT_COLLECTION, limit: int = 10) -> str:
    try:
        query_vector = embeddings.embed_query(user_input)
        if not isinstance(query_vector, (list, tuple)):
            query_vector = list(query_vector)
    except Exception:
        logger.exception("Embedding failed")
        return "Sorry, I couldn't create an embedding for your query."

    try:
        hits = http_search_collection(collection_name=collection_name, query_vector=query_vector, limit=limit, with_payload=True)
    except Exception:
        logger.exception("Qdrant search failed")
        return "Sorry, I couldn't search the dataset right now."

    if not hits:
        return "I couldn’t find anything relevant in the dataset."

    response_lines = []
    for hit in hits:
        payload = hit.get("payload") or {}
        product_name = payload.get("product_name") or payload.get("product") or "Unknown product"
        sales = payload.get("sales") or payload.get("sales_amount") or "N/A"
        month_year = payload.get("month_year") or payload.get("date") or "Unknown date"
        sales_vol = payload.get("sales_vol") or payload.get("quantity") or payload.get("sales_volume") or "N/A"
        line = f"{product_name} had sales {sales} in {month_year} with volume {sales_vol}."
        response_lines.append(line)

    return "Here’s what I found:\n" + "\n".join(response_lines)

@app.post("/chat")
async def chat(question: str = Form(...), collection: str = Form(DEFAULT_COLLECTION)):
    answer = query_qdrant(question, collection_name=collection)
    return PlainTextResponse(answer)

def iso_month_range(year: int, month: int):
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(seconds=1)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(seconds=1)
    return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")

def scroll_query_with_filter(collection_name: str, filter_obj: dict, batch_size: int = 500):
    headers = {"Content-Type": "application/json"}
    url = f"{QDRANT_BASE}/collections/{collection_name}/points/scroll"
    offset = None
    while True:
        body = {"limit": batch_size, "with_payload": True, "filter": filter_obj}
        if offset is not None:
            body["offset"] = offset
        r = requests.post(url, headers=headers, data=json.dumps(body), timeout=30)
        r.raise_for_status()
        resp = r.json()
        result = resp.get("result")
        if isinstance(result, dict) and "points" in result:
            points = result["points"]
        elif isinstance(result, list):
            points = result
        elif isinstance(resp.get("points"), list):
            points = resp["points"]
        elif isinstance(resp, list):
            points = resp
        else:
            points = []
        if not points:
            break
        for p in points:
            yield p.get("payload", {}) if isinstance(p, dict) else {}
        next_offset = None
        if isinstance(result, dict):
            next_offset = result.get("next_page") or result.get("next_page_offset") or result.get("offset")
        next_offset = next_offset or resp.get("next_page") or resp.get("next_page_offset") or resp.get("offset")
        if not next_offset:
            break
        offset = next_offset

@app.get("/aggregate/sales_by_month")
def aggregate_sales(year: int, month: int, collection: str = DEFAULT_COLLECTION):
    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="month must be 1..12")
    try:
        start_iso, end_iso = iso_month_range(year, month)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid year/month")

    filter_obj = {
        "must": [
            {
                "key": "month_year",
                "range": {
                    "gte": start_iso,
                    "lte": end_iso
                }
            }
        ]
    }

    total_sales = 0.0
    count = 0
    bad_rows = 0

    try:
        for payload in scroll_query_with_filter(collection, filter_obj, batch_size=500):
            sales_val = payload.get("sales") or payload.get("sales_amount") or payload.get("sales_vol")
            if sales_val is None:
                bad_rows += 1
                continue
            try:
                if isinstance(sales_val, str):
                    sales_val = sales_val.replace(",", "")
                val = float(sales_val)
                if math.isfinite(val):
                    total_sales += val
                    count += 1
                else:
                    bad_rows += 1
            except Exception:
                bad_rows += 1
    except requests.HTTPError as e:
        logger.exception("Qdrant HTTP error during aggregation")
        raise HTTPException(status_code=502, detail=f"Qdrant error: {e}")
    except Exception:
        logger.exception("Unexpected error during aggregation")
        raise HTTPException(status_code=500, detail="Internal error during aggregation")

    return {
        "collection": collection,
        "year": year,
        "month": month,
        "records_aggregated": count,
        "records_skipped": bad_rows,
        "total_sales": total_sales
    }

