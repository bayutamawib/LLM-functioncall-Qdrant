import os
import logging
import psycopg2
import datetime
import uuid
from dotenv import load_dotenv
from tqdm import tqdm
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from openrouter_embedder import OpenRouterEmbedder

# --- Load environment variables ---
load_dotenv()

# --- Logging setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- Connect to Postgres ---
conn = psycopg2.connect(
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASS"),
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT")
)
cur = conn.cursor()

# --- Initialize OpenRouter embedding model ---
embeddings = OpenRouterEmbedder(model="openai/text-embedding-3-small")
VECTOR_SIZE = 1536  # adjust if your embedding model uses a different dimension

# --- Connect to Qdrant ---
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

# --- Schema definitions (same as before) ---
SCHEMAS = {
    "product_cost": {
        "class": "product_cost_staging",
        "vectorizer": "none",
        "properties": [
            {"name": "month_year", "dataType": ["date"]},
            {"name": "sales_vol", "dataType": ["int"]},
            {"name": "sum_profit", "dataType": ["number"]},
            {"name": "cost_per_unit", "dataType": ["string"]},
            {"name": "rsp_per_unit", "dataType": ["string"]},
            {"name": "product_name", "dataType": ["string"]}
        ]
    },
    "transactions_main": {
        "class": "transactions_main_staging",
        "vectorizer": "none",
        "properties": [
            {"name": "sub_category", "dataType": ["string"]},
            {"name": "city", "dataType": ["string"]},
            {"name": "order_id", "dataType": ["string"]},
            {"name": "sales", "dataType": ["string"]},
            {"name": "product_name", "dataType": ["string"]},
            {"name": "country", "dataType": ["string"]},
            {"name": "state", "dataType": ["string"]},
            {"name": "quantity", "dataType": ["int"]},
            {"name": "product_id", "dataType": ["string"]},
            {"name": "ship_date", "dataType": ["date"]},
            {"name": "discount", "dataType": ["number"]},
            {"name": "postal_code", "dataType": ["string"]},
            {"name": "ship_mode", "dataType": ["string"]},
            {"name": "customer_name", "dataType": ["string"]},
            {"name": "month_year", "dataType": ["date"]},
            {"name": "region", "dataType": ["string"]},
            {"name": "order_date", "dataType": ["date"]},
            {"name": "customer_id", "dataType": ["string"]},
            {"name": "segment", "dataType": ["string"]},
            {"name": "category", "dataType": ["string"]},
            {"name": "profit", "dataType": ["number"]},
            {"name": "row_id", "dataType": ["int"]}
        ]
    },
    "target_cost": {
        "class": "target_cost_staging",
        "vectorizer": "none",
        "properties": [
            {"name": "target_cost", "dataType": ["string"]},
            {"name": "product_name", "dataType": ["string"]},
            {"name": "month_year", "dataType": ["date"]}
        ]
    },
    "sales_vol": {
        "class": "sales_vol_staging",
        "vectorizer": "none",
        "properties": [
            {"name": "sales", "dataType": ["string"]},
            {"name": "product_name", "dataType": ["string"]},
            {"name": "sales_vol", "dataType": ["int"]},
            {"name": "month_year", "dataType": ["date"]}
        ]
    },
    "product_inventory_init": {
        "class": "product_inventory_init_staging",
        "vectorizer": "none",
        "properties": [
            {"name": "product_name", "dataType": ["string"]},
            {"name": "inventory_stock_init", "dataType": ["int"]},
            {"name": "month_year", "dataType": ["date"]}
        ]
    }
}

# --- Utility: build type map for normalization from SCHEMAS ---
def build_type_map(schemas: dict) -> dict:
    type_map = {}
    for tbl, cfg in schemas.items():
        props = cfg["properties"]
        type_map[cfg["class"]] = {p["name"]: p["dataType"][0] for p in props}
    return type_map

TYPE_MAP = build_type_map(SCHEMAS)  # {class_name: {property: type}}

def excel_serial_to_date(serial: int) -> str:
    """Convert Excel serial date (days since 1899-12-30) to RFC3339."""
    base = datetime.datetime(1899, 12, 30)
    dt = base + datetime.timedelta(days=int(serial))
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

# --- Helper: normalize metadata values based on schema types ---
def normalize_metadata(doc: dict, class_name: str) -> dict:
    normalized = {}
    type_for_class = TYPE_MAP.get(class_name, {})

    for k, v in doc.items():
        if v is None or k not in type_for_class:
            # skip nulls and fields not defined in schema
            continue

        expected = type_for_class[k]  # "string" | "number" | "int" | "date"

        try:
            # Dates
            if expected == "date":
                if isinstance(v, (int, float)):
                    normalized[k] = excel_serial_to_date(int(v))
                elif isinstance(v, datetime.date):
                    dt = datetime.datetime.combine(v, datetime.time())
                    normalized[k] = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                else:
                    # try parse YYYY-MM-DD
                    dt = datetime.datetime.strptime(str(v), "%Y-%m-%d")
                    normalized[k] = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

            # Integers
            elif expected == "int":
                normalized[k] = int(float(v))  # handle "2.0" -> 2

            # Floats (number)
            elif expected == "number":
                normalized[k] = float(v)

            # Strings
            elif expected == "string":
                normalized[k] = str(v)

            else:
                # fallback: stringify
                normalized[k] = str(v)

        except Exception:
            # safe fallback defaults to avoid ingestion failure
            if expected == "int":
                normalized[k] = 0
            elif expected == "number":
                normalized[k] = 0.0
            elif expected == "date":
                normalized[k] = datetime.datetime(1970, 1, 1).strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                normalized[k] = str(v) if v is not None else ""

    return normalized

# --- Qdrant helpers ---
def ensure_collection(collection_name: str, vector_size: int = VECTOR_SIZE, distance: qm.Distance = qm.Distance.COSINE):
    """
    Recreate collection to ensure a clean state. If you prefer to keep existing data,
    replace recreate_collection with create_collection and guard existence.
    """
    try:
        qdrant.delete_collection(collection_name=collection_name)
    except Exception:
        pass

    qdrant.recreate_collection(
        collection_name=collection_name,
        vectors_config=qm.VectorParams(size=vector_size, distance=distance)
    )
    logging.info(f"✅ Created collection '{collection_name}' with vector size {vector_size} and distance {distance.name}")

# --- Batch embedding + insert into Qdrant ---
def populate_index_batch(table_name: str, batch_size: int = 500):
    # Postgres source table name (schema.staging)
    cur.execute(f"SELECT * FROM staging.{table_name};")
    rows = cur.fetchall()
    colnames = [desc[0] for desc in cur.description]

    class_name = SCHEMAS[table_name]["class"]  # use as Qdrant collection name

    # Ensure collection exists (recreate for a clean run)
    ensure_collection(class_name, vector_size=VECTOR_SIZE, distance=qm.Distance.COSINE)

    total_batches = (len(rows) + batch_size - 1) // batch_size

    for i in tqdm(range(0, len(rows), batch_size), total=total_batches, desc=f"Embedding {table_name}"):
        chunk = rows[i:i+batch_size]

        docs_for_embedding = []
        payloads = []
        ids = []

        for row in chunk:
            raw = dict(zip(colnames, row))
            meta = normalize_metadata(raw, class_name)

            # Choose text field for embedding; fallback to stringified meta
            text_input = meta.get("product_name") or meta.get("sales") or str(meta)
            docs_for_embedding.append(text_input)
            payloads.append(meta)

            # Prefer using row_id if present and valid, else generate UUID
            if "row_id" in meta:
                try:
                    pid = int(meta["row_id"])
                    ids.append(str(pid))
                except Exception:
                    ids.append(str(uuid.uuid4()))
            else:
                ids.append(str(uuid.uuid4()))

        # Embed the whole batch
        vectors = embeddings.embed_documents(docs_for_embedding)

        # Validate vector dimensions
        for vec in vectors:
            if len(vec) != VECTOR_SIZE:
                raise ValueError(f"Embedding dimension mismatch: expected {VECTOR_SIZE}, got {len(vec)}")

        # Build PointStruct list
        points = [
            qm.PointStruct(id=pid, vector=vec, payload=pl)
            for pid, vec, pl in zip(ids, vectors, payloads)
        ]

        # Upsert points
        qdrant.upsert(collection_name=class_name, points=points, wait=True)

    logging.info(f"🎯 Finished embedding {len(rows)} rows into collection '{class_name}'")

# --- Run embedding for all staging tables ---
if __name__ == "__main__":
    for table in SCHEMAS.keys():
        try:
            populate_index_batch(table)
        except Exception as e:
            logging.error(f"⚠️ Failed to embed {table}: {e}")
            conn.rollback()