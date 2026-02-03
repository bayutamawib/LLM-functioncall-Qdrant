import os
import logging
import json
import math
import requests
import re
from datetime import datetime, timezone
from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse
from openrouter_embedder import OpenRouterEmbedder
from openai import OpenAI

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Configuration ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# Default model names: use OpenRouter slug when using OpenRouter, otherwise OpenAI model name
CHAT_MODEL = os.getenv("CHAT_MODEL") or ( "openai/gpt-4o-mini" if OPENROUTER_API_KEY else "gpt-4o-mini" )

# --- Clients ---
# Embeddings (kept as an embedding model for Qdrant retrieval)
embeddings = OpenRouterEmbedder(model="openai/text-embedding-3-small")

# Chat client: prefer OpenRouter if key present, otherwise OpenAI
if OPENROUTER_API_KEY:
    chat_client = OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")
    logger.info("Using OpenRouter chat client with model: %s", CHAT_MODEL)
elif OPENAI_API_KEY:
    chat_client = OpenAI(api_key=OPENAI_API_KEY)
    logger.info("Using OpenAI chat client with model: %s", CHAT_MODEL)
else:
    chat_client = None
    logger.warning("No API key found for OpenRouter or OpenAI. Chat calls will fail until a key is provided.")

# --- Qdrant config ---
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_BASE = os.getenv("QDRANT_BASE_URL") or f"http://{QDRANT_HOST}:{QDRANT_PORT}"
DEFAULT_COLLECTION = os.getenv("QDRANT_COLLECTION", "sales_vol_staging")

app = FastAPI(title="Simple Qdrant Chatbot (No Aggregation)")

# ---------------------------
# Helpers: Qdrant retrieval
# ---------------------------

def http_search_collection(collection_name: str, query_vector: list, limit: int = 5, with_payload: bool = True):
    headers = {"Content-Type": "application/json"}
    body = {"vector": query_vector, "limit": limit, "with_payload": with_payload}
    # Try /points/search then /points/query for compatibility
    for endpoint in ("search", "query"):
        url = f"{QDRANT_BASE}/collections/{collection_name}/points/{'search' if endpoint=='search' else 'query'}"
        try:
            r = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
            r.raise_for_status()
            resp = r.json()
            result = resp.get("result")
            if isinstance(result, dict) and "points" in result:
                points = result["points"]
            elif isinstance(result, list):
                points = result
            else:
                points = resp.get("result", []) or resp.get("points", []) or []
            hits = []
            for p in points:
                if not isinstance(p, dict):
                    continue
                hits.append({
                    "id": p.get("id"),
                    "score": p.get("score"),
                    "payload": p.get("payload", {})
                })
            return hits
        except Exception:
            logger.debug("Qdrant %s endpoint failed or returned non-200; trying fallback", endpoint, exc_info=True)
    raise RuntimeError("No compatible Qdrant search endpoint available")

def retrieve_hits(user_input: str, collection_name: str = DEFAULT_COLLECTION, limit: int = 5):
    try:
        vec = embeddings.embed_query(user_input)
        if not isinstance(vec, (list, tuple)):
            vec = list(vec)
    except Exception:
        logger.exception("Embedding failed")
        return []
    try:
        hits = http_search_collection(collection_name, vec, limit=limit, with_payload=True)
        return hits or []
    except Exception:
        logger.exception("Qdrant search failed")
        return []

def build_context_from_hits(hits: list) -> str:
    lines = []
    for h in hits:
        payload = h.get("payload") or {}
        product = payload.get("product_name") or payload.get("product") or "Unknown product"
        sales = payload.get("sales") or payload.get("sales_amount") or "N/A"
        date = payload.get("month_year") or payload.get("date") or "Unknown date"
        vol = payload.get("sales_vol") or payload.get("quantity") or payload.get("sales_volume") or "N/A"
        lines.append(f"{product} | date: {date} | sales: {sales} | volume: {vol}")
    return "\n".join(lines)

# ---------------------------
# Endpoints
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
        logger.exception("Health check failed")
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)

@app.post("/chat")
async def chat(question: str = Form(...), collection: str = Form(DEFAULT_COLLECTION)):
    """
    Retrieval-augmented chat:
    - embed the question
    - retrieve top-N hits from Qdrant
    - ask the chat model to answer using only the retrieved context
    No aggregation or function calling is performed.
    """
    if chat_client is None:
        raise HTTPException(status_code=500, detail="Chat client not configured (missing API key)")

    # Retrieve context
    hits = retrieve_hits(question, collection_name=collection, limit=5)
    if not hits:
        # Ask the model to respond gracefully when no context is available
        try:
            completion = chat_client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that answers questions about sales data."},
                    {"role": "user", "content": f"Question: {question}\nNo relevant records were found. Respond briefly and ask a clarifying question."}
                ]
            )
            answer = completion.choices[0].message.content
        except Exception as e:
            logger.error("Chat model error when no hits: %s", e)
            answer = "I couldn't find relevant records. Could you provide more details (month, product, or date range)?"
        return PlainTextResponse(answer)

    # Build compact context and call chat model
    context = build_context_from_hits(hits)
    prompt_user = (
        f"Question: {question}\n\n"
        f"Context (use only this context to answer):\n{context}\n\n"
        "Answer succinctly and cite any values using the context. If the question requires calculations or aggregations, say you cannot compute them here."
    )

    try:
        completion = chat_client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": "You answer questions about sales records using only the provided context. Do not invent facts."},
                {"role": "user", "content": prompt_user}
            ],
            max_tokens=512
        )
        answer = completion.choices[0].message.content
    except Exception as e:
        logger.error("Chat model error: %s", e)
        answer = "I retrieved relevant records but couldn't generate a response right now."

    return PlainTextResponse(answer)
