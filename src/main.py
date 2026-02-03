import os
import logging
import json
import math
import re
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse
from openrouter_embedder import OpenRouterEmbedder
from openai import OpenAI

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Keys & clients ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Embedding model (for Qdrant retrieval) via OpenRouter
embeddings = OpenRouterEmbedder(model="openai/text-embedding-3-small")

# Chat model setup
# If using OpenRouter, set base_url and a valid model slug
CHAT_MODEL = os.getenv("CHAT_MODEL", "openai/gpt-4o-mini")

if OPENROUTER_API_KEY:
    client = OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")
    logger.info("Chat client configured for OpenRouter with model: %s", CHAT_MODEL)
elif OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)
    # If using OpenAI direct, you may need to change CHAT_MODEL to a valid OpenAI model name (e.g., "gpt-4o-mini")
    logger.info("Chat client configured for OpenAI with model: %s", CHAT_MODEL)
else:
    logger.warning("No OPENROUTER_API_KEY or OPENAI_API_KEY found. Chat calls will fail.")

# --- Qdrant config ---
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_BASE = os.getenv("QDRANT_BASE_URL") or f"http://{QDRANT_HOST}:{QDRANT_PORT}"
DEFAULT_COLLECTION = os.getenv("QDRANT_COLLECTION", "sales_vol_staging")

app = FastAPI(title="Qdrant Chatbot (HTTP)")

# ---------------------------
# Static index + health check
# ---------------------------

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

# ---------------------------
# Qdrant HTTP search helpers
# ---------------------------

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

def retrieve_hits(user_input: str, collection_name: str = DEFAULT_COLLECTION, limit: int = 10):
    """Embed the query and fetch top-N hits from Qdrant."""
    try:
        query_vector = embeddings.embed_query(user_input)
        if not isinstance(query_vector, (list, tuple)):
            query_vector = list(query_vector)
    except Exception:
        logger.exception("Embedding failed")
        return []

    try:
        hits = http_search_collection(collection_name=collection_name, query_vector=query_vector, limit=limit, with_payload=True)
        return hits or []
    except Exception:
        logger.exception("Qdrant search failed")
        return []

def build_context_from_hits(hits: list) -> str:
    """Format retrieved hits into a compact context for the chat model."""
    lines = []
    for hit in hits:
        payload = hit.get("payload") or {}
        product_name = payload.get("product_name") or payload.get("product") or "Unknown product"
        sales = payload.get("sales") or payload.get("sales_amount") or "N/A"
        month_year = payload.get("month_year") or payload.get("date") or "Unknown date"
        sales_vol = payload.get("sales_vol") or payload.get("quantity") or payload.get("sales_volume") or "N/A"
        lines.append(f"- {product_name}: sales={sales}, date={month_year}, volume={sales_vol}")
    return "\n".join(lines)

# ---------------------------
# Deterministic aggregation
# ---------------------------

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
    """Sum revenue (sales or sales_amount) over a given month."""
    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="month must be 1..12")
    try:
        start_iso, end_iso = iso_month_range(year, month)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid year/month")

    filter_obj = {"must": [{"key": "month_year", "range": {"gte": start_iso, "lte": end_iso}}]}

    total_sales = 0.0
    count = 0
    bad_rows = 0

    try:
        for payload in scroll_query_with_filter(collection, filter_obj, batch_size=500):
            sales_val = payload.get("sales") or payload.get("sales_amount")
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

    return {"collection": collection, "year": year, "month": month, "records_aggregated": count, "records_skipped": bad_rows, "total_sales": total_sales}

@app.get("/aggregate/volume_by_month")
def aggregate_volume(year: int, month: int, collection: str = DEFAULT_COLLECTION):
    """Sum units sold (sales_vol or quantity) over a given month."""
    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="month must be 1..12")
    try:
        start_iso, end_iso = iso_month_range(year, month)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid year/month")

    filter_obj = {"must": [{"key": "month_year", "range": {"gte": start_iso, "lte": end_iso}}]}

    total_units = 0.0
    count = 0
    bad_rows = 0

    try:
        for payload in scroll_query_with_filter(collection, filter_obj, batch_size=500):
            vol_val = payload.get("sales_vol") or payload.get("quantity") or payload.get("sales_volume")
            if vol_val is None:
                bad_rows += 1
                continue
            try:
                if isinstance(vol_val, str):
                    vol_val = vol_val.replace(",", "")
                val = float(vol_val)
                if math.isfinite(val):
                    total_units += val
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

    return {"collection": collection, "year": year, "month": month, "records_aggregated": count, "records_skipped": bad_rows, "total_units": total_units}

# ---------------------------
# Intent detection utilities
# ---------------------------

MONTH_MAP = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}

def parse_year_month_from_text(text: str):
    """Extract (year, month) if present; return (None, None) if not found."""
    t = text.lower()

    m = re.search(r"(20\d{2})[-/\.](\d{1,2})", t)
    if m:
        year = int(m.group(1))
        month = int(m.group(2))
        if 1 <= month <= 12:
            return year, month

    m2 = re.search(r"\b(" + "|".join(MONTH_MAP.keys()) + r")\b[\s,]+(20\d{2})", t)
    if m2:
        month = MONTH_MAP[m2.group(1)]
        year = int(m2.group(2))
        return year, month

    m3 = re.search(r"(20\d{2})[\s,]+\b(" + "|".join(MONTH_MAP.keys()) + r")\b", t)
    if m3:
        year = int(m3.group(1))
        month = MONTH_MAP[m3.group(2)]
        return year, month

    return None, None

def is_revenue_aggregation(text: str) -> bool:
    t = text.lower()
    revenue_keywords = [
        "total sales", "sum of sales", "aggregate sales", "revenue",
        "sales amount", "total revenue", "how much sales", "overall sales"
    ]
    return any(k in t for k in revenue_keywords)

def is_volume_aggregation(text: str) -> bool:
    t = text.lower()
    volume_keywords = [
        "total units", "units sold", "sales volume", "quantity sold",
        "total quantity", "overall volume"
    ]
    return any(k in t for k in volume_keywords)

# ---------------------------
# Chat endpoint (router)
# ---------------------------

@app.post("/chat")
async def chat(question: str = Form(...), collection: str = Form(DEFAULT_COLLECTION)):
    year, month = parse_year_month_from_text(question)

    # Revenue aggregation
    if is_revenue_aggregation(question) and year and month:
        try:
            agg = aggregate_sales(year=year, month=month, collection=collection)
            try:
                completion = client.chat.completions.create(
                    model=CHAT_MODEL,
                    messages=[
                        {"role": "system", "content": "You summarize sales revenue clearly and concisely."},
                        {"role": "user", "content": f"Question: {question}\nResult: {json.dumps(agg)}\nRespond in one sentence with the total revenue and records_aggregated."}
                    ]
                )
                answer = completion.choices[0].message.content
            except Exception as e:
                logger.error("Chat model error: %s", e)
                answer = f"Total revenue in {year}-{month:02d}: {agg['total_sales']} across {agg['records_aggregated']} records."
            return PlainTextResponse(answer)
        except HTTPException as e:
            return PlainTextResponse(f"Aggregation error: {e.detail}", status_code=e.status_code)
        except Exception:
            logger.exception("Revenue aggregation pipeline failed")
            return PlainTextResponse("Sorry, I couldn’t compute the total revenue right now.", status_code=500)

    # Volume aggregation
    if is_volume_aggregation(question) and year and month:
        try:
            agg = aggregate_volume(year=year, month=month, collection=collection)
            try:
                completion = client.chat.completions.create(
                    model=CHAT_MODEL,
                    messages=[
                        {"role": "system", "content": "You summarize sales volume clearly and concisely."},
                        {"role": "user", "content": f"Question: {question}\nResult: {json.dumps(agg)}\nRespond in one sentence with the total units and records_aggregated."}
                    ]
                )
                answer = completion.choices[0].message.content
            except Exception as e:
                logger.error("Chat model error: %s", e)
                answer = f"Total units in {year}-{month:02d}: {agg['total_units']} across {agg['records_aggregated']} records."
            return PlainTextResponse(answer)
        except HTTPException as e:
            return PlainTextResponse(f"Aggregation error: {e.detail}", status_code=e.status_code)
        except Exception:
            logger.exception("Volume aggregation pipeline failed")
            return PlainTextResponse("Sorry, I couldn’t compute the total units right now.", status_code=500)

    # Retrieval path
    hits = retrieve_hits(question, collection_name=collection, limit=10)
    if not hits:
        try:
            completion = client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": "You assist with sales data questions."},
                    {"role": "user", "content": f"Question: {question}\nNo relevant records were found. Respond briefly and ask a clarifying follow-up (e.g., month/year or product)."}
                ]
            )
            answer = completion.choices[0].message.content
        except Exception as e:
            logger.error("Chat model error: %s", e)
            answer = "No relevant records found. Please specify the month/year or product."
        return PlainTextResponse(answer)

    context = build_context_from_hits(hits)
    try:
        completion = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": "You answer questions about sales data using only the provided context. If asked for totals, request a month/year to compute deterministically."},
                {"role": "user", "content": f"Question: {question}\nContext:\n{context}\nAnswer succinctly using only the context."}
            ]
        )
        answer = completion.choices[0].message.content
    except Exception as e:
        logger.error("Chat model error: %s", e)
        answer = "I retrieved relevant records. What month/year or product should I focus on?"

    return PlainTextResponse(answer)
