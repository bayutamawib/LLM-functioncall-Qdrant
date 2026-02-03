# Experiments & Development Guide

## Quick Overview

This project demonstrates the evolution of a RAG chatbot through multiple iterations. The **production version** is in `src/main.py`, while earlier experimental versions are documented in the `experiments/` folder.

## Project Structure

```
retail-inventory-chatbot/
├── src/main.py                          ← PRODUCTION (v3 - Full Featured)
├── experiments/                         ← DEVELOPMENT ITERATIONS
│   ├── README.md                        ← Detailed comparison
│   ├── main_v1_basic_retrieval.py       ← Proof of concept
│   ├── main_v2_retrieval_aggregation.py ← Add aggregation
│   └── main_v4_simplified_llm.py        ← LLM-only approach
└── [other project files...]
```

## What's in Each Version?

### Production: src/main.py (v3 - Full Featured) ✅
**Use this for deployment**

Features:
- ✅ Vector search (Qdrant)
- ✅ LLM chat (OpenRouter/OpenAI)
- ✅ Revenue aggregation by month
- ✅ Volume aggregation by month
- ✅ Intent detection (smart routing)
- ✅ Natural language date parsing

Example queries it handles:
```
"What were total sales in January 2024?"
→ Detects aggregation intent → Calls /aggregate/sales_by_month → LLM enhancement

"Tell me about Product X"
→ Detects retrieval intent → Vector search → LLM summarization

"How many units sold in Q1 2024?"
→ Detects volume aggregation → Calls /aggregate/volume_by_month → LLM response
```

---

### Experiments: experiments/ (Development Iterations)

#### v1: Basic Retrieval
- Vector search only
- Plain text responses
- No LLM, no aggregation
- **Purpose**: Proof of concept

#### v2: Retrieval + Aggregation
- Vector search + deterministic aggregation
- No LLM integration
- **Purpose**: Show aggregation logic

#### v4: Simplified LLM
- Vector search + LLM chat
- No aggregation
- **Purpose**: Show LLM integration

---

## Why Multiple Versions?

This demonstrates:
1. **Iterative development** - Start simple, add features
2. **Problem-solving** - Each version solves a gap
3. **Trade-offs** - Simplicity vs features
4. **Integration** - Combining multiple technologies
5. **Production readiness** - Final version is battle-tested

## For Your Portfolio

**Talking Points**:
- "Started with basic vector search to validate the approach"
- "Added aggregation to handle business intelligence queries"
- "Integrated LLM to improve response quality"
- "Implemented intent detection for intelligent routing"
- "Final version combines all learnings into production-ready system"

**What Interviewers See**:
- ✅ Systematic problem-solving
- ✅ Understanding of trade-offs
- ✅ Integration of multiple technologies
- ✅ Production-ready thinking
- ✅ Clear documentation

---

## Quick Start

### Run Production Version
```bash
cp .env.example .env
# Edit .env with your API keys

pip install -r requirements.txt
python scripts/ingest_data.py

# Run production
uvicorn src.main:app --reload
# Visit http://localhost:8000
```

### Compare All Versions
```bash
# Terminal 1: Production (v3)
uvicorn src.main:app --port 8000

# Terminal 2: v1 (Basic)
cd experiments && python -m uvicorn main_v1_basic_retrieval:app --port 8001

# Terminal 3: v2 (Aggregation)
cd experiments && python -m uvicorn main_v2_retrieval_aggregation:app --port 8002

# Terminal 4: v4 (Simplified LLM)
cd experiments && python -m uvicorn main_v4_simplified_llm:app --port 8004

# Test same query on all versions:
curl -X POST http://localhost:8000/chat -d "question=What about Product X?"
curl -X POST http://localhost:8001/chat -d "question=What about Product X?"
curl -X POST http://localhost:8002/chat -d "question=What about Product X?"
curl -X POST http://localhost:8004/chat -d "question=What about Product X?"
```

---

## Detailed Comparison

See `experiments/README.md` for:
- Feature-by-feature comparison
- Code examples from each version
- Lessons learned
- Design decisions
- Testing instructions

---

## Key Learnings

### What Worked
1. **Qdrant HTTP API** - Reliable, no client library needed
2. **Batch scrolling** - Efficient for large datasets
3. **LLM enhancement** - Dramatically improves UX
4. **Intent detection** - Smart query routing
5. **Deterministic aggregation** - Prevents hallucination

### What Didn't Work
1. **Plain text responses** - Lack context
2. **No aggregation** - Can't answer business questions
3. **No intent detection** - Treats all queries the same
4. **No date parsing** - Poor UX

### Final Architecture (v3)
```
User Query
    ↓
Intent Detection (revenue/volume/retrieval?)
    ↓
Route 1: Aggregation → LLM Enhancement
Route 2: Retrieval → LLM Summarization
    ↓
Natural Language Response
```

---

## GitHub Portfolio Value

This structure shows:
- **Systematic thinking** - Problem → Solution → Iteration
- **Technical depth** - Multiple technologies integrated
- **Production mindset** - Handling edge cases, fallbacks
- **Clear communication** - Well-documented decisions
- **Continuous improvement** - Each version builds on learnings

---

## Next Steps

1. **Review** - Read through each version's code
2. **Test** - Run all versions and compare outputs
3. **Understand** - Study the design decisions
4. **Deploy** - Use v3 in production
5. **Discuss** - Be ready to explain the evolution

---

## Questions to Prepare For

**"Why multiple versions?"**
- "Each version solved a specific problem. This shows iterative development."

**"Why is v3 better?"**
- "It combines all features: search, aggregation, and LLM. Plus intent detection for smart routing."

**"What would you do differently?"**
- "I'd add caching for aggregations, implement rate limiting, and add monitoring."

**"How does it scale?"**
- "Qdrant handles large datasets efficiently. Aggregation uses batch scrolling. LLM calls are cached."

---

## Support

- **Setup issues?** → See `docs/SETUP.md`
- **Architecture questions?** → See `docs/ARCHITECTURE.md`
- **API questions?** → See `docs/API.md`
- **Version comparison?** → See `experiments/README.md`

