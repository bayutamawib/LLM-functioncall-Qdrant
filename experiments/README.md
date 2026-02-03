# Experiments & Development Iterations

This folder documents the evolution of the chatbot's main application logic. It shows different architectural approaches and feature combinations tested during development.

## Overview

The production application uses **main_v3_full_featured.py** (in `src/main.py`). This folder contains earlier iterations that explore different design patterns and feature sets.

## Files

### 1. main_v1_basic_retrieval.py
**Status**: ❌ Deprecated (superseded by v3)

**Features**:
- Vector search via Qdrant HTTP API
- Plain text formatting of results
- No LLM integration
- No aggregation

**Endpoints**:
- `GET /` - Serve web UI
- `GET /health` - Health check
- `POST /chat` - Vector search only

**Retrieval Limit**: 3 results

**Use Case**: Minimal proof-of-concept for vector search

**Key Code**:
```python
def query_qdrant(user_input: str, collection_name: str, limit: int = 3) -> str:
    # Embed query
    # Search Qdrant
    # Format results as plain text
    return formatted_results
```

**Lessons Learned**:
- Plain text responses lack context and nuance
- Users need aggregation for business questions
- LLM enhancement significantly improves UX

---

### 2. main_v2_retrieval_aggregation.py
**Status**: ⚠️ Partial (missing LLM)

**Features**:
- Vector search via Qdrant HTTP API
- Deterministic aggregation by month
- Date range filtering
- Batch scrolling through results
- No LLM integration

**Endpoints**:
- `GET /` - Serve web UI
- `GET /health` - Health check
- `POST /chat` - Vector search only
- `GET /aggregate/sales_by_month?year=2024&month=1` - Sum revenue
- (No volume aggregation)

**Retrieval Limit**: 10 results

**New Functions**:
- `iso_month_range()` - Calculate ISO date ranges
- `scroll_query_with_filter()` - Batch retrieval with Qdrant filters
- `aggregate_sales()` - Sum revenue by month

**Use Case**: Deterministic calculations without LLM hallucination

**Key Code**:
```python
def scroll_query_with_filter(collection_name: str, filter_obj: dict, batch_size: int = 500):
    # Paginate through all matching records
    # Apply Qdrant filters
    # Yield payloads in batches
    
def aggregate_sales(year: int, month: int, collection: str):
    # Calculate exact revenue for a month
    # Handle NaN/infinity values
    # Return count + total
```

**Lessons Learned**:
- Aggregation is critical for business intelligence
- Batch scrolling needed for large datasets
- Date parsing is complex (multiple formats)
- Users still want natural language answers, not just JSON

---

### 3. main_v4_simplified_llm.py
**Status**: ⚠️ Partial (missing aggregation)

**Features**:
- Vector search via Qdrant HTTP API
- LLM-powered chat (OpenRouter or OpenAI)
- Context-aware responses
- No aggregation endpoints
- No intent detection

**Endpoints**:
- `GET /` - Serve web UI
- `GET /health` - Health check
- `POST /chat` - LLM chat with retrieval context

**Retrieval Limit**: 5 results

**New Functions**:
- `retrieve_hits()` - Separate retrieval function
- `build_context_from_hits()` - Format context for LLM
- LLM integration via OpenAI client

**Use Case**: Lightweight LLM-only chat without aggregation

**Key Code**:
```python
def retrieve_hits(user_input: str, collection_name: str, limit: int = 5):
    # Embed query
    # Search Qdrant
    # Return structured hits
    
# In chat endpoint:
hits = retrieve_hits(question)
context = build_context_from_hits(hits)
completion = chat_client.chat.completions.create(
    model=CHAT_MODEL,
    messages=[
        {"role": "system", "content": "Answer using only the context"},
        {"role": "user", "content": f"Question: {question}\nContext: {context}"}
    ]
)
```

**Lessons Learned**:
- LLM significantly improves response quality
- Context-aware prompting prevents hallucination
- Users need both retrieval AND aggregation
- Intent detection would improve routing

---

### 4. main_v3_full_featured.py (Production)
**Status**: ✅ Production Ready

**Location**: `src/main.py`

**Features**:
- Vector search via Qdrant HTTP API
- LLM-powered chat (OpenRouter or OpenAI)
- Deterministic aggregation (revenue + volume)
- Intent detection (revenue vs volume vs retrieval)
- Natural language date parsing
- Smart routing based on query intent

**Endpoints**:
- `GET /` - Serve web UI
- `GET /health` - Health check
- `POST /chat` - Intelligent routing
- `GET /aggregate/sales_by_month?year=2024&month=1` - Sum revenue
- `GET /aggregate/volume_by_month?year=2024&month=1` - Sum units

**Retrieval Limit**: 10 results

**New Functions** (combines all previous + adds):
- `parse_year_month_from_text()` - Extract dates from natural language
- `is_revenue_aggregation()` - Detect revenue queries
- `is_volume_aggregation()` - Detect volume queries
- Smart routing in `/chat` endpoint

**Use Case**: Production-ready intelligent chatbot

**Key Code**:
```python
@app.post("/chat")
async def chat(question: str = Form(...), collection: str = Form(DEFAULT_COLLECTION)):
    year, month = parse_year_month_from_text(question)
    
    # Route 1: Revenue aggregation
    if is_revenue_aggregation(question) and year and month:
        agg = aggregate_sales(year=year, month=month, collection=collection)
        # Enhance with LLM
        answer = llm_summarize(question, agg)
        return answer
    
    # Route 2: Volume aggregation
    if is_volume_aggregation(question) and year and month:
        agg = aggregate_volume(year=year, month=month, collection=collection)
        # Enhance with LLM
        answer = llm_summarize(question, agg)
        return answer
    
    # Route 3: Retrieval
    hits = retrieve_hits(question)
    context = build_context_from_hits(hits)
    answer = llm_answer_with_context(question, context)
    return answer
```

**Lessons Learned**:
- Intent detection is crucial for routing
- Combining aggregation + LLM gives best results
- Natural language date parsing improves UX
- Fallback to LLM when no context found

---

## Evolution Timeline

```
v1: Basic Retrieval
    ↓ (Problem: No aggregation, plain text responses)
    
v2: Add Aggregation
    ↓ (Problem: No LLM, responses still plain text)
    
v4: Add LLM (parallel branch)
    ↓ (Problem: No aggregation, can't handle business queries)
    
v3: Combine All + Intent Detection ✅
    ↓ (Solution: Smart routing, best of both worlds)
```

---

## Testing Each Version

### Test v1 (Basic Retrieval)
```bash
cd experiments
python -m uvicorn main_v1_basic_retrieval:app --reload --port 8001
# Test: curl -X POST http://localhost:8001/chat -d "question=What about Product X?"
```

### Test v2 (Retrieval + Aggregation)
```bash
cd experiments
python -m uvicorn main_v2_retrieval_aggregation:app --reload --port 8002
# Test retrieval: curl -X POST http://localhost:8002/chat -d "question=What about Product X?"
# Test aggregation: curl "http://localhost:8002/aggregate/sales_by_month?year=2024&month=1"
```

### Test v4 (Simplified LLM)
```bash
cd experiments
python -m uvicorn main_v4_simplified_llm:app --reload --port 8004
# Test: curl -X POST http://localhost:8004/chat -d "question=What about Product X?"
```

### Test v3 (Production - Recommended)
```bash
# From project root
python -m uvicorn src.main:app --reload
# Test all features
```

---

## Feature Comparison

| Feature | v1 | v2 | v4 | v3 |
|---------|----|----|----|----|
| Vector Search | ✅ | ✅ | ✅ | ✅ |
| LLM Chat | ❌ | ❌ | ✅ | ✅ |
| Revenue Aggregation | ❌ | ✅ | ❌ | ✅ |
| Volume Aggregation | ❌ | ❌ | ❌ | ✅ |
| Intent Detection | ❌ | ❌ | ❌ | ✅ |
| Date Parsing | ❌ | ❌ | ❌ | ✅ |
| Smart Routing | ❌ | ❌ | ❌ | ✅ |
| Production Ready | ❌ | ⚠️ | ⚠️ | ✅ |

---

## Key Insights

### What Worked
1. **Qdrant HTTP API** - Reliable, no client library needed
2. **Batch scrolling** - Handles large datasets efficiently
3. **LLM enhancement** - Dramatically improves response quality
4. **Intent detection** - Routes queries intelligently
5. **Deterministic aggregation** - Prevents LLM hallucination

### What Didn't Work
1. **Plain text responses** - Lack context and nuance
2. **No aggregation** - Can't answer business questions
3. **No intent detection** - Treats all queries the same
4. **No date parsing** - Users must specify exact format

### Design Decisions in v3
1. **Separate retrieval function** - Reusable, testable
2. **Context formatting** - Compact, LLM-friendly
3. **Fallback to LLM** - When no context found
4. **Deterministic aggregation** - Exact calculations
5. **Intent-based routing** - Smart query handling

---

## For Portfolio

This folder demonstrates:
- ✅ Iterative development process
- ✅ Problem-solving approach
- ✅ Feature evolution
- ✅ Trade-offs between simplicity and features
- ✅ Integration of multiple technologies (Qdrant, LLM, FastAPI)
- ✅ Production-ready architecture

**Talking Points**:
- "Started with basic retrieval, identified gaps"
- "Added aggregation for business intelligence"
- "Integrated LLM for natural language responses"
- "Implemented intent detection for smart routing"
- "Final version combines all learnings"

---

## Running All Versions Simultaneously

```bash
# Terminal 1: Production (v3)
uvicorn src.main:app --port 8000

# Terminal 2: v1
cd experiments && python -m uvicorn main_v1_basic_retrieval:app --port 8001

# Terminal 3: v2
cd experiments && python -m uvicorn main_v2_retrieval_aggregation:app --port 8002

# Terminal 4: v4
cd experiments && python -m uvicorn main_v4_simplified_llm:app --port 8004

# Compare responses:
curl -X POST http://localhost:8000/chat -d "question=What about Product X?"
curl -X POST http://localhost:8001/chat -d "question=What about Product X?"
curl -X POST http://localhost:8002/chat -d "question=What about Product X?"
curl -X POST http://localhost:8004/chat -d "question=What about Product X?"
```

---

## Next Steps

1. **Test each version** - See the differences in action
2. **Compare responses** - Understand trade-offs
3. **Review code** - Learn from each iteration
4. **Use v3 in production** - It's the most complete
5. **Document learnings** - For your portfolio

