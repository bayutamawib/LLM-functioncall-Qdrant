#!/usr/bin/env python3
import os
import math
from dotenv import load_dotenv
from qdrant_client import QdrantClient

load_dotenv()
client = QdrantClient(host=os.getenv("QDRANT_HOST","localhost"), port=int(os.getenv("QDRANT_PORT","6333")))
COLLECTION = os.getenv("QDRANT_COLLECTION", "sales_vol_staging")
BATCH = int(os.getenv("FIX_BATCH", "500"))

def normalize(payload):
    # same normalization logic as above; return normalized payload
    # (implement identical to parse_and_normalize)
    ...

def scroll_and_fix():
    offset = None
    while True:
        resp = client.scroll(collection_name=COLLECTION, limit=BATCH, with_payload=True, offset=offset)
        points = resp.get("result") or resp.get("points") or resp
        if not points:
            break
        to_upsert = []
        for p in points:
            pid = p.get("id")
            payload = p.get("payload", {}) or {}
            normalized = normalize(payload)
            if normalized != payload:
                to_upsert.append({"id": pid, "payload": normalized})
        if to_upsert:
            client.upsert(collection_name=COLLECTION, points=to_upsert)
        offset = resp.get("next_page") or resp.get("offset") or None
        if not offset:
            break

if __name__ == "__main__":
    scroll_and_fix()
