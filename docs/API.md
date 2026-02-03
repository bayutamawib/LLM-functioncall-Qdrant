# API Documentation

## Base URL

```
http://localhost:8000
```

## Endpoints

### 1. Chat Endpoint

**POST** `/chat`

Main endpoint for asking questions about retail data.

**Request:**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "question=What are the top 5 products by revenue?"
```

**Parameters:**
- `question` (string, required) - Natural language question

**Response:**
```json
{
  "question": "What are the top 5 products by revenue?",
  "answer": "Based on the data, the top 5 products by revenue are...",
  "sources": [
    {
      "product_name": "Product A",
      "sales": 50000,
      "month_year": "2024-01-01"
    }
  ]
}
```

**Status Codes:**
- `200` - Success
- `400` - Invalid question
- `502` - Qdrant unavailable
- `500` - Internal error

---

### 2. Sales Aggregation Endpoint

**GET** `/aggregate/sales_by_month`

Sum total revenue for a specific month.

**Request:**
```bash
curl "http://localhost:8000/aggregate/sales_by_month?year=2024&month=1"
```

**Parameters:**
- `year` (integer, required) - Year (e.g., 2024)
- `month` (integer, required) - Month (1-12)
- `collection` (string, optional) - Qdrant collection name (default: sales_vol_staging)

**Response:**
```json
{
  "collection": "sales_vol_staging",
  "year": 2024,
  "month": 1,
  "records_aggregated": 1250,
  "records_skipped": 5,
  "total_sales": 1250000.50
}
```

**Status Codes:**
- `200` - Success
- `400` - Invalid year/month
- `502` - Qdrant error
- `500` - Internal error

---

### 3. Volume Aggregation Endpoint

**GET** `/aggregate/volume_by_month`

Sum total units sold for a specific month.

**Request:**
```bash
curl "http://localhost:8000/aggregate/volume_by_month?year=2024&month=1"
```

**Parameters:**
- `year` (integer, required) - Year (e.g., 2024)
- `month` (integer, required) - Month (1-12)
- `collection` (string, optional) - Qdrant collection name (default: sales_vol_staging)

**Response:**
```json
{
  "collection": "sales_vol_staging",
  "year": 2024,
  "month": 1,
  "records_aggregated": 1250,
  "records_skipped": 5,
  "total_volume": 5000
}
```

**Status Codes:**
- `200` - Success
- `400` - Invalid year/month
- `502` - Qdrant error
- `500` - Internal error

---

### 4. Health Check Endpoint

**GET** `/health`

Check if Qdrant is accessible.

**Request:**
```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "ok",
  "qdrant": "healthy"
}
```

**Status Codes:**
- `200` - Healthy
- `503` - Qdrant unavailable

---

### 5. Web UI Endpoint

**GET** `/`

Serves the web interface.

**Response:** HTML page with chat form

---

## Example Queries

### Revenue Questions

```bash
# Total revenue in January 2024
curl -X POST http://localhost:8000/chat \
  -d "question=What was the total revenue in January 2024?"

# Top products by revenue
curl -X POST http://localhost:8000/chat \
  -d "question=What are the top 10 products by revenue?"

# Revenue by region
curl -X POST http://localhost:8000/chat \
  -d "question=Show me revenue by region"
```

### Volume Questions

```bash
# Total units sold
curl -X POST http://localhost:8000/chat \
  -d "question=How many units were sold in Q1 2024?"

# Product volume
curl -X POST http://localhost:8000/chat \
  -d "question=Which products had the highest sales volume?"
```

### Profit Questions

```bash
# Profit analysis
curl -X POST http://localhost:8000/chat \
  -d "question=What was the total profit in February 2024?"

# Profit by product
curl -X POST http://localhost:8000/chat \
  -d "question=Which products are most profitable?"
```

### Inventory Questions

```bash
# Inventory levels
curl -X POST http://localhost:8000/chat \
  -d "question=What is the current inventory level for Product A?"

# Low stock alerts
curl -X POST http://localhost:8000/chat \
  -d "question=Which products have low inventory?"
```

---

## Error Responses

### 400 Bad Request

```json
{
  "detail": "month must be 1..12"
}
```

### 502 Bad Gateway

```json
{
  "detail": "Qdrant error: Connection refused"
}
```

### 500 Internal Server Error

```json
{
  "detail": "Internal error during aggregation"
}
```

---

## Rate Limiting

Currently no rate limiting. For production, implement:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/chat")
@limiter.limit("10/minute")
async def chat(question: str):
    ...
```

---

## Authentication

Currently no authentication. For production, add:

```python
from fastapi.security import HTTPBearer

security = HTTPBearer()

@app.post("/chat")
async def chat(question: str, credentials: HTTPAuthCredentials = Depends(security)):
    ...
```

---

## CORS

Currently allows all origins. For production:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Pagination

Aggregation endpoints return all results. For large datasets, consider pagination:

```python
@app.get("/aggregate/sales_by_month")
def aggregate_sales(
    year: int,
    month: int,
    limit: int = 100,
    offset: int = 0
):
    ...
```

---

## Caching

For frequently accessed data, implement caching:

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_monthly_sales(year: int, month: int):
    ...
```

---

## Webhooks

For real-time updates, consider webhooks:

```python
@app.post("/webhooks/data-updated")
async def on_data_updated(event: DataUpdateEvent):
    # Invalidate cache
    # Trigger re-indexing
    ...
```

---

## Versioning

Current version: `v1`

Future versions can be added:

```
/v1/chat
/v2/chat
```

---

## Support

For API issues:
1. Check logs: `docker-compose logs gateway`
2. Verify Qdrant: `curl http://localhost:6333/health`
3. Check environment variables: `cat .env`
4. Open GitHub issue with error details
