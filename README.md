# Retail Inventory Chatbot

A production-ready **Retrieval-Augmented Generation (RAG) chatbot** for retail sales data analysis. Combines vector embeddings, semantic search, and LLM-powered responses to answer questions about product sales, inventory, and financial metrics.

## Features

- 🤖 **LLM-Powered Chat** - Natural language Q&A using GPT-4o-mini
- 🔍 **Semantic Search** - Vector-based retrieval from Qdrant
- 📊 **Smart Aggregation** - Automatic revenue/volume calculations by month
- 🧠 **Intent Detection** - Routes queries to retrieval or aggregation
- 🐳 **Docker Ready** - One-command deployment
- 📈 **Data Validation** - Built-in data quality checks

## Tech Stack

- **Vector DB**: Qdrant
- **Embeddings**: OpenRouter (OpenAI text-embedding-3-small)
- **LLM**: OpenRouter or OpenAI (GPT-4o-mini)
- **Backend**: FastAPI
- **Data Source**: PostgreSQL
- **Containerization**: Docker Compose

## Quick Start

### Prerequisites

- Docker & Docker Compose
- OpenRouter API key (or OpenAI key)
- PostgreSQL with staging tables

### 1. Setup Environment

```bash
cp .env.example .env
# Edit .env with your API keys and database credentials
```

### 2. Install Dependencies (Local Development)

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Ingest Data

```bash
python scripts/ingest_data.py
python src/utils/validators.py  # Validate data quality
```

### 4. Run Chatbot

**Local:**
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

**Docker:**
```bash
docker-compose up
```

Visit `http://localhost:8000` in your browser.

## API Endpoints

### Chat
- `POST /chat` - Main chat endpoint
  - Query: `question` (string)
  - Returns: LLM response with context

### Aggregation
- `GET /aggregate/sales_by_month?year=2024&month=1` - Sum revenue for a month
- `GET /aggregate/volume_by_month?year=2024&month=1` - Sum units sold for a month

### Health
- `GET /health` - Qdrant health check
- `GET /` - Serves web UI

## Project Structure

```
retail-inventory-chatbot/
├── src/
│   ├── main.py                 # FastAPI app (primary)
│   ├── gateway_app.py          # Optional Qdrant gateway
│   ├── openrouter_embedder.py  # Embedding wrapper
│   └── utils/
│       └── validators.py       # Data validation
├── scripts/
│   ├── ingest_data.py          # ETL pipeline
│   └── fix_qdrant_payloads.py  # Data cleanup
├── templates/
│   └── index.html              # Web UI
├── docker-compose.yml
├── Dockerfile.gateway
├── requirements.txt
└── README.md
```

## Data Collections

The system manages 5 Qdrant collections:

1. **product_cost_staging** - Product costs, profit, RSP
2. **transactions_main_staging** - Full transaction records
3. **target_cost_staging** - Target cost benchmarks
4. **sales_vol_staging** - Sales volume and revenue (primary)
5. **product_inventory_init_staging** - Initial inventory levels

## Environment Variables

See `.env.example` for all required variables.

## Maintenance

### Fix Data Quality Issues

```bash
# Dry-run (preview changes)
python scripts/fix_qdrant_payloads.py

# Apply fixes
python scripts/fix_qdrant_payloads.py --apply --batch 200
```

## Architecture

```
PostgreSQL (staging tables)
    ↓
[ingest_data.py] → Normalize & embed
    ↓
Qdrant (vector DB)
    ↓
[main.py] ← User query
    ↓
OpenRouter (embeddings + LLM)
    ↓
Response (retrieval + aggregation)
```

## Contributing

1. Create a feature branch
2. Make changes
3. Test locally: `python -m pytest tests/`
4. Submit PR

## License

MIT

## Support

For issues or questions, open a GitHub issue.
