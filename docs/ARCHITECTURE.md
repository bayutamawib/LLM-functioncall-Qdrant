# Architecture Overview

## System Design

This is a **Retrieval-Augmented Generation (RAG)** system that combines:

1. **Vector Search** - Semantic similarity matching
2. **LLM Integration** - Natural language understanding & generation
3. **Deterministic Aggregation** - Exact calculations for financial metrics

## Data Flow

```
User Query
    ↓
[Intent Detection]
    ├─→ Aggregation Query (e.g., "revenue in January")
    │   ↓
    │   [Filter by date range]
    │   ↓
    │   [Sum sales/volume]
    │   ↓
    │   Return exact number
    │
    └─→ Retrieval Query (e.g., "top products")
        ↓
        [Embed query]
        ↓
        [Vector search in Qdrant]
        ↓
        [Retrieve top 10 results]
        ↓
        [Pass to LLM with context]
        ↓
        [Generate natural language response]
```

## Components

### 1. Data Ingestion (`scripts/ingest_data.py`)

- Reads from PostgreSQL staging tables
- Normalizes dates, numbers, strings
- Embeds text fields using OpenRouter
- Upserts into Qdrant collections
- Batch processing (500 rows/batch)

**Collections:**
- `product_cost_staging` - Product financials
- `transactions_main_staging` - Order details
- `sales_vol_staging` - Revenue & volume (primary)
- `product_inventory_init_staging` - Inventory
- `target_cost_staging` - Benchmarks

### 2. Embedding Service (`src/openrouter_embedder.py`)

Wrapper around OpenRouter API for text embeddings.

- Model: `openai/text-embedding-3-small`
- Dimension: 1536
- Batch processing support

### 3. Chat API (`src/main.py`)

FastAPI application with:

**Endpoints:**
- `POST /chat` - Main chat endpoint
- `GET /aggregate/sales_by_month` - Revenue aggregation
- `GET /aggregate/volume_by_month` - Volume aggregation
- `GET /health` - Health check
- `GET /` - Web UI

**Features:**
- Intent detection (aggregation vs retrieval)
- Date/month parsing from natural language
- Vector search with Qdrant
- LLM response generation
- Error handling & fallbacks

### 4. Qdrant Vector Database

- Stores embeddings + metadata
- Supports filtering by date, product, etc.
- Persistent storage via Docker volume
- REST API on port 6333

### 5. Frontend (`templates/index.html`)

Simple HTML form for chat interface.

## Key Algorithms

### Intent Detection

```python
if "revenue" in query or "sales" in query or "total" in query:
    # Aggregation query
    extract_date_range()
    sum_sales()
else:
    # Retrieval query
    embed_query()
    vector_search()
    llm_response()
```

### Date Parsing

Extracts year/month from natural language:
- "January 2024" → (2024, 1)
- "last month" → (current_year, current_month - 1)
- "Q1 2024" → Multiple months

### Vector Search

```python
query_embedding = embed(user_question)
results = qdrant.search(
    collection="sales_vol_staging",
    query_vector=query_embedding,
    limit=10,
    filters=optional_date_filters
)
```

### LLM Response Generation

```python
context = format_search_results(results)
prompt = f"""
You are a retail analyst. Answer based on this data:
{context}

Question: {user_question}
"""
response = llm.chat(prompt)
```

## Deployment

### Local Development

```bash
# Terminal 1: Qdrant
docker run -p 6333:6333 qdrant/qdrant

# Terminal 2: FastAPI
uvicorn src.main:app --reload
```

### Docker Compose

```bash
docker-compose up
```

Services:
- `qdrant` - Vector DB (port 6333)
- `gateway` - FastAPI app (port 8000)

## Performance Considerations

### Optimization Tips

1. **Batch Ingestion** - Process 500 rows at a time
2. **Vector Indexing** - Qdrant uses HNSW for fast search
3. **Caching** - Consider caching common queries
4. **Filtering** - Use date filters to reduce search space
5. **Aggregation** - Use deterministic calculations for exact numbers

### Scaling

For production:

1. **Qdrant Cluster** - Enable clustering for HA
2. **Load Balancer** - Distribute requests across API instances
3. **Database Replication** - PostgreSQL replication for data source
4. **API Rate Limiting** - Implement rate limits for OpenRouter
5. **Monitoring** - Add logging, metrics, alerts

## Error Handling

- **Missing API Keys** - Fallback to basic retrieval
- **Qdrant Unavailable** - Return 502 error
- **Invalid Dates** - Return 400 error
- **No Results** - Return helpful message
- **LLM Errors** - Return raw search results

## Security

- API keys in `.env` (never commit)
- Input validation on all endpoints
- CORS headers for web UI
- Rate limiting recommended for production
