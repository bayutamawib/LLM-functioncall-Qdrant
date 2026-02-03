import os
from typing import List, Optional
from fastapi import FastAPI
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
VECTOR_SIZE = int(os.getenv("VECTOR_SIZE", "1536"))

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
app = FastAPI(title="Qdrant Gateway", version="1.0")

class CreateCollectionRequest(BaseModel):
    name: str
    size: Optional[int] = None
    distance: str = "Cosine"  # or "Dot", "Euclid"

class Point(BaseModel):
    id: str
    vector: List[float]
    payload: dict

class UpsertRequest(BaseModel):
    collection: str
    points: List[Point]
    wait: bool = True

class SearchRequest(BaseModel):
    collection: str
    vector: List[float]
    limit: int = 5
    filter_equals: Optional[dict] = None  # e.g., {"month_year": "2017-01-01T00:00:00Z"}

@app.get("/health")
def health():
    try:
        r = client.get_locks()
        return {"status": "ok", "qdrant": "reachable"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.post("/collections/create")
def create_collection(req: CreateCollectionRequest):
    size = req.size or VECTOR_SIZE
    client.recreate_collection(
        collection_name=req.name,
        vectors_config=qm.VectorParams(size=size, distance=getattr(qm.Distance, req.distance))
    )
    return {"status": "created", "collection": req.name, "size": size, "distance": req.distance}

@app.post("/points/upsert")
def upsert_points(req: UpsertRequest):
    points = [
        qm.PointStruct(id=p.id, vector=p.vector, payload=p.payload) for p in req.points
    ]
    client.upsert(collection_name=req.collection, points=points, wait=req.wait)
    return {"status": "upserted", "count": len(points), "collection": req.collection}

@app.post("/points/search")
def search_points(req: SearchRequest):
    qfilter = None
    if req.filter_equals:
        qfilter = qm.Filter(
            must=[
                qm.FieldCondition(key=k, match=qm.MatchValue(value=v))
                for k, v in req.filter_equals.items()
            ]
        )
    hits = client.search(
        collection_name=req.collection,
        query_vector=req.vector,
        limit=req.limit,
        query_filter=qfilter
    )
    return {"status": "ok", "results": [h.dict() for h in hits]}
