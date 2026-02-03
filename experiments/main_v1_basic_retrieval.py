import os
import logging
import json
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Form
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse
from openrouter_embedder import OpenRouterEmbedder

# --- Load environment variables ---
load_dotenv()

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Embeddings client (OpenRouter) ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
embeddings = OpenRouterEmbedder(model="openai/text-embedding-3-small")  # pass api_key if your embedder supports it

# --- Qdrant HTTP config (use REST directly) ---
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_BASE = os.getenv("QDRANT_BASE_URL") or f"http://{QDRANT_HOST}:{QDRANT_PORT}"

DEFAULT_COLLECTION = os.getenv("QDRANT_COLLECTION", "sales_vol_staging")

app = FastAPI(title="Qdrant Chatbot (HTTP)")

# --- Serve index.html ---
@app.get("/")
async def read_index():
    index_path = os.path.join("templates", "index.html")
    if not os.path.exists(index_path):
        return JSONResponse({"error": "index.html not found in templates/ directory"}, status_code=404)
    return FileResponse(index_path)

# --- Health endpoint ---
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

# --- Low-level HTTP search helper ---
def http_search_collection(collection_name: str, query_vector: list, limit: int = 3, with_payload: bool = True):
    """
    Use Qdrant REST endpoints to perform a vector search.
    Tries /collections/{name}/points/search first, then /collections/{name}/points/query.
    Returns normalized list of hits: [{'id':..., 'score':..., 'payload': {...}}, ...]
    """
    headers = {"Content-Type": "application/json"}
    body_search = {
        "vector": query_vector,
        "limit": limit,
        "with_payload": with_payload
    }
    # 1) Try /collections/{name}/points/search
    search_url = f"{QDRANT_BASE}/collections/{collection_name}/points/search"
    try:
        r = requests.post(search_url, headers=headers, data=json.dumps(body_search), timeout=10)
        if r.status_code == 200:
            resp = r.json()
            # Qdrant /points/search returns {"result": [...]} or {"result": {"points": [...]}} depending on version
            results = resp.get("result")
            if results is None and "result" in resp:
                results = resp["result"]
            # Some versions return {"result": {"points": [...]}}
            if isinstance(results, dict) and "points" in results:
                points = results["points"]
            elif isinstance(results, list):
                points = results
            else:
                points = resp.get("result", [])
            hits = []
            for p in points:
                # p may be dict with 'id', 'payload', 'score' or nested under 'payload'
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

    # 2) Try /collections/{name}/points/query (modern endpoint)
    query_url = f"{QDRANT_BASE}/collections/{collection_name}/points/query"
    body_query = {
        "vector": query_vector,
        "limit": limit,
        "with_payload": with_payload
    }
    try:
        r = requests.post(query_url, headers=headers, data=json.dumps(body_query), timeout=10)
        r.raise_for_status()
        resp = r.json()
        # /points/query typically returns {"result": [...]} or {"result": {"points": [...]}}
        results = resp.get("result")
        if isinstance(results, dict) and "points" in results:
            points = results["points"]
        elif isinstance(results, list):
            points = results
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

    # 3) If both endpoints fail, raise
    raise RuntimeError("No compatible HTTP search endpoint available on Qdrant")

# --- Query Qdrant ---
def query_qdrant(user_input: str, collection_name: str = DEFAULT_COLLECTION, limit: int = 3) -> str:
    """
    Embed the user input, run a vector search via HTTP, and format a plain-text reply.
    """
    # 1) Embed the query
    try:
        query_vector = embeddings.embed_query(user_input)
        if not isinstance(query_vector, (list, tuple)):
            # Some embedders return nested structures; try to coerce
            query_vector = list(query_vector)
    except Exception:
        logger.exception("Embedding failed")
        return "Sorry, I couldn't create an embedding for your query."

    # 2) Run vector search using low-level HTTP
    try:
        hits = http_search_collection(collection_name=collection_name, query_vector=query_vector, limit=limit, with_payload=True)
    except Exception:
        logger.exception("Qdrant search failed")
        return "Sorry, I couldn't search the dataset right now."

    # 3) Format results
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

# --- Chat endpoint ---
@app.post("/chat")
async def chat(question: str = Form(...), collection: str = Form(DEFAULT_COLLECTION)):
    """
    Accepts form field 'question' and optional 'collection' to override default.
    Returns plain text answer.
    """
    answer = query_qdrant(question, collection_name=collection)
    return PlainTextResponse(answer)

