# Setup Guide

## Prerequisites

- Python 3.9+
- Docker & Docker Compose
- PostgreSQL (for data ingestion)
- OpenRouter API key (or OpenAI key)

## Step 1: Clone & Setup

```bash
git clone https://github.com/yourusername/retail-inventory-chatbot.git
cd retail-inventory-chatbot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Step 2: Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# Required: OpenRouter API
OPENROUTER_API_KEY=sk-or-...

# Optional: OpenAI API (fallback)
OPENAI_API_KEY=sk-...

# Database (for data ingestion)
DB_NAME=retail_db
DB_USER=postgres
DB_PASS=your_password
DB_HOST=localhost
DB_PORT=5432
```

## Step 3: Prepare Data

### Option A: Local PostgreSQL

```bash
# Create database
createdb retail_db

# Load your staging tables into PostgreSQL
# Tables needed:
# - product_cost
# - transactions_main
# - sales_vol
# - product_inventory_init
# - target_cost
```

### Option B: Docker PostgreSQL

```bash
docker run -d \
  --name postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  postgres:15
```

## Step 4: Ingest Data

```bash
# Start Qdrant (if not using Docker Compose)
docker run -d -p 6333:6333 qdrant/qdrant

# Run ingestion
python scripts/ingest_data.py

# Validate data
python src/utils/validators.py
```

## Step 5: Run Chatbot

### Local Development

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Visit: `http://localhost:8000`

### Docker Compose

```bash
docker-compose up
```

Visit: `http://localhost:8000`

## Step 6: Test

```bash
# Test chat endpoint
curl -X POST http://localhost:8000/chat \
  -d "question=What are the top products by revenue?"

# Test aggregation
curl "http://localhost:8000/aggregate/sales_by_month?year=2024&month=1"

# Health check
curl http://localhost:8000/health
```

## Troubleshooting

### Qdrant Connection Error

```
Error: Failed to connect to Qdrant at localhost:6333
```

**Solution:**
```bash
# Check if Qdrant is running
docker ps | grep qdrant

# Start Qdrant
docker run -d -p 6333:6333 qdrant/qdrant
```

### PostgreSQL Connection Error

```
Error: could not connect to server: Connection refused
```

**Solution:**
```bash
# Check PostgreSQL
psql -U postgres -h localhost

# Or use Docker
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15
```

### API Key Error

```
Error: OPENROUTER_API_KEY not found
```

**Solution:**
```bash
# Check .env file
cat .env | grep OPENROUTER_API_KEY

# Get key from https://openrouter.ai/keys
```

### No Results from Chat

**Possible causes:**
1. Data not ingested - Run `python scripts/ingest_data.py`
2. Wrong collection name - Check `QDRANT_COLLECTION` in `.env`
3. Embeddings failed - Check OpenRouter API key

**Debug:**
```bash
# Check collections
curl http://localhost:6333/collections

# Check collection size
curl http://localhost:6333/collections/sales_vol_staging
```

## Development Workflow

### Adding New Features

1. Create feature branch: `git checkout -b feature/my-feature`
2. Make changes
3. Test locally: `uvicorn src.main:app --reload`
4. Run tests: `pytest tests/`
5. Commit & push
6. Create PR

### Running Tests

```bash
pytest tests/ -v
```

### Code Style

```bash
# Format code
black src/ scripts/

# Lint
flake8 src/ scripts/

# Type checking
mypy src/
```

## Production Deployment

### Using Docker Compose

```bash
# Build images
docker-compose build

# Start services
docker-compose up -d

# View logs
docker-compose logs -f gateway

# Stop services
docker-compose down
```

### Environment Variables for Production

```env
# Use production API keys
OPENROUTER_API_KEY=sk-or-prod-...

# Use production database
DB_HOST=prod-db.example.com
DB_NAME=retail_prod

# Qdrant cluster
QDRANT_HOST=qdrant-cluster.example.com
QDRANT_PORT=6333

# Chat model
CHAT_MODEL=openai/gpt-4-turbo
```

### Monitoring

```bash
# Check Qdrant health
curl http://localhost:6333/health

# Check API health
curl http://localhost:8000/health

# View logs
docker-compose logs -f
```

## Backup & Recovery

### Backup Qdrant Data

```bash
# Backup volume
docker run --rm -v qdrant_storage:/data -v $(pwd):/backup \
  alpine tar czf /backup/qdrant-backup.tar.gz -C /data .
```

### Restore Qdrant Data

```bash
# Restore volume
docker run --rm -v qdrant_storage:/data -v $(pwd):/backup \
  alpine tar xzf /backup/qdrant-backup.tar.gz -C /data
```

## Next Steps

- Read [ARCHITECTURE.md](ARCHITECTURE.md) for system design
- Check [API.md](API.md) for endpoint documentation
- Explore example queries in the web UI
