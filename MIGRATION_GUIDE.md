# Migration Guide: Cleanup & Reorganization

## What Changed

This project has been reorganized for production readiness and GitHub portfolio standards.

### File Reorganization

| Old Location | New Location | Status |
|---|---|---|
| `main3.py` | `src/main.py` | ✅ Renamed (primary) |
| `embed.py` | `scripts/ingest_data.py` | ✅ Renamed |
| `validate_ingestion.py` | `src/utils/validators.py` | ✅ Moved |
| `openrouter_embedder.py` | `src/openrouter_embedder.py` | ✅ Moved |
| `gateway_app.py` | `src/gateway_app.py` | ✅ Moved |
| `templates/index.html` | `templates/index.html` | ✅ No change |
| `docker-compose.yml` | `docker-compose.yml` | ✅ No change |
| `Dockerfile.gateway` | `Dockerfile.gateway` | ✅ No change |

### Files Deleted (Obsolete)

```
❌ main.py       → Superseded by main3.py
❌ main2.py      → Superseded by main3.py
❌ main4.py      → Superseded by main3.py
❌ scripts/fix_qdrant_payloads_client.py → Incomplete, use fix_qdrant_payloads.py
```

### New Files Added

```
✅ README.md                    → Project overview
✅ requirements.txt             → Python dependencies
✅ .env.example                 → Environment template
✅ .gitignore                   → Git ignore rules
✅ docs/ARCHITECTURE.md         → System design
✅ docs/API.md                  → API documentation
✅ docs/SETUP.md                → Setup instructions
✅ src/__init__.py              → Package marker
✅ src/utils/__init__.py        → Utils package marker
✅ scripts/__init__.py          → Scripts package marker
```

## Migration Steps

### Step 1: Backup Current Project

```bash
git add .
git commit -m "Backup before reorganization"
git branch backup/before-reorganization
```

### Step 2: Update Imports

If you have custom scripts importing from old locations, update them:

**Before:**
```python
from embed import *
from main3 import app
from validate_ingestion import *
```

**After:**
```python
from scripts.ingest_data import *
from src.main import app
from src.utils.validators import *
```

### Step 3: Update Docker Compose

The `docker-compose.yml` already references the correct paths. No changes needed.

### Step 4: Update Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

### Step 5: Reinstall Dependencies

```bash
pip install -r requirements.txt
```

### Step 6: Test Everything

```bash
# Test data ingestion
python scripts/ingest_data.py

# Test validation
python src/utils/validators.py

# Test API
uvicorn src.main:app --reload
```

### Step 7: Delete Old Files

```bash
rm main.py main2.py main4.py
rm scripts/fix_qdrant_payloads_client.py
```

### Step 8: Commit Changes

```bash
git add .
git commit -m "Reorganize project structure for production"
git push origin main
```

## Docker Compose Issue Resolution

### Problem: Two docker-compose.yml Files

You mentioned having docker-compose files in two locations:
1. Current folder (root)
2. Parent folder

### Solution

**Keep only ONE:**

```bash
# Check both locations
ls docker-compose.yml
ls ../docker-compose.yml

# Keep the root one, delete parent
rm ../docker-compose.yml

# Verify only one exists
find . -name "docker-compose.yml" -type f
```

**Why this matters:**
- Running `docker-compose up` from different directories creates separate stacks
- This causes duplicate containers, port conflicts, and data inconsistency
- For scaling, you need a single source of truth

### For Multiple Environments

If you need different configs for dev/staging/prod, use overrides:

```bash
# Development (default)
docker-compose up

# Staging
docker-compose -f docker-compose.yml -f docker-compose.staging.yml up

# Production
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up
```

Create `docker-compose.staging.yml`:
```yaml
version: "3.8"
services:
  gateway:
    environment:
      CHAT_MODEL: openai/gpt-4-turbo
      QDRANT_HOST: staging-qdrant.example.com
```

## Verification Checklist

After migration, verify:

- [ ] All imports updated
- [ ] `python scripts/ingest_data.py` works
- [ ] `python src/utils/validators.py` works
- [ ] `uvicorn src.main:app --reload` starts without errors
- [ ] Web UI loads at `http://localhost:8000`
- [ ] Chat endpoint responds: `curl -X POST http://localhost:8000/chat -d "question=test"`
- [ ] `docker-compose up` works
- [ ] Only ONE docker-compose.yml exists
- [ ] `.env` file is in `.gitignore`
- [ ] Old files (main.py, main2.py, main4.py) are deleted

## Troubleshooting

### Import Errors

```
ModuleNotFoundError: No module named 'embed'
```

**Solution:** Update import to `from scripts.ingest_data import ...`

### Docker Port Conflicts

```
Error: bind: address already in use
```

**Solution:** 
```bash
# Stop all containers
docker-compose down

# Or remove old containers
docker rm qdrant qdrant-gateway
```

### Qdrant Data Loss

If you had Qdrant running from parent folder, data might be in different volume:

```bash
# List volumes
docker volume ls | grep qdrant

# Inspect volume
docker volume inspect qdrant_storage

# If multiple volumes, migrate data:
docker run --rm -v old_volume:/from -v new_volume:/to alpine cp -r /from /to
```

## Next Steps

1. Read [docs/SETUP.md](docs/SETUP.md) for detailed setup
2. Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for system design
3. Read [docs/API.md](docs/API.md) for API documentation
4. Push to GitHub with clean structure
5. Update GitHub README with project description

## Questions?

Refer to the documentation:
- **Setup issues?** → [docs/SETUP.md](docs/SETUP.md)
- **Architecture questions?** → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **API questions?** → [docs/API.md](docs/API.md)
