# Django RAG Backend

A production-ready **Retrieval-Augmented Generation (RAG)** API built with Django REST Framework, PostgreSQL + pgvector, and Google Gemini.

Upload a CSV of Q&A pairs, embed them into a vector store, then ask natural-language questions and get grounded answers backed by your documents — not hallucinations.

---

## What is RAG?

A normal LLM answers from what it memorized during training. It can't see your private documents, and it will happily invent an answer if it doesn't know.

**RAG fixes both problems** by giving the model your documents at question time:

```
INGESTION (run once)
  CSV rows → embed each row → store vectors in pgvector

QUERY TIME (every request)
  User question → embed question → cosine similarity search → top-K relevant chunks
                                                                        ↓
                                        build a grounded prompt → Gemini → answer
```

The two key ideas:

1. **Embeddings** turn text into a list of numbers (a *vector*) that captures meaning. Similar meaning → similar numbers. "How do I return an item?" and "What's your refund policy?" land near each other in vector space even though they share almost no words.
2. **Vector search** finds the chunks whose vectors are closest to the question's vector — those are the most *semantically relevant* pieces of your data.

We then stuff those chunks into the prompt and tell the model: *"Answer using ONLY this context."* If the context doesn't contain the answer, the model says so instead of guessing.

---

## Features

- CSV ingestion with automatic batch embedding + idempotency guard
- Cosine-similarity vector search via pgvector with relevance threshold
- Grounded answer generation (refuses to answer outside the data)
- REST API — `/query/`, `/ingest/`, `/health/`
- Management command for one-shot data loading
- Retry with exponential back-off on Gemini quota errors (429)
- Category filter on retrieval
- Clean service layer (ingestion / retrieval / generation separated)
- Celery async ingestion stub (disabled by default, ready to enable)

---

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Web framework | Django 6 + DRF | Batteries-included, fast to ship |
| Vector store | PostgreSQL + **pgvector** | No extra DB to run — vectors live next to your data |
| Embeddings | Gemini `gemini-embedding-001` (768-dim) | Free tier, strong quality |
| Generation | Gemini `gemini-2.5-flash` | Fast, cheap, free tier |
| Distance metric | Cosine distance | Standard for text embeddings |

---

## Project Structure

```
rag-django/
├── core/
│   ├── settings.py          # Django settings — all secrets via env vars
│   └── urls.py              # Root URL config
├── documents/
│   ├── models.py            # DocumentChunk (source, category, content, embedding)
│   ├── views.py             # QueryView, IngestView, HealthView
│   ├── urls.py              # /query/ /ingest/ /health/
│   ├── tasks.py             # Celery async task stub (disabled by default)
│   ├── migrations/
│   │   ├── 0001_enable_vector.py   # CREATE EXTENSION vector
│   │   └── ...
│   ├── management/commands/
│   │   └── ingest_csv.py    # python manage.py ingest_csv <file>
│   └── services/
│       ├── config.py        # All tuning constants (model names, TOP_K, thresholds)
│       ├── client.py        # Shared Gemini client singleton
│       ├── ingestion.py     # CSV validation, batch embedding, bulk insert
│       ├── retrieval.py     # Vector similarity search with threshold + category filter
│       └── rag.py           # Full RAG pipeline (retrieve → augment → generate)
├── Files/
│   └── CDC-COVID-FAQ.csv    # Sample dataset
├── .env.example
├── requirements.txt
└── manage.py
```

**Why a service layer?** The API, the management command, and Celery tasks all call the *same* `ingest_csv()` / `rag_query()` functions. Business logic lives in one place; the entry points are thin wrappers.

---

## Prerequisites

- Python 3.11+
- PostgreSQL 14+ with the **pgvector** extension
- A [Google AI Studio](https://aistudio.google.com/) API key (free tier works)

### Enable pgvector

```sql
-- Run once as a superuser in your target database
CREATE EXTENSION IF NOT EXISTS vector;
GRANT ALL ON SCHEMA public TO raguser;
ALTER USER raguser CREATEDB;
```

Migration `0001_enable_vector.py` also runs `CREATE EXTENSION IF NOT EXISTS vector` automatically on `migrate`.

---

## Getting Started

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd rag-django

# 2. Virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
copy .env.example .env       # Windows
# cp .env.example .env       # macOS / Linux
# Fill in SECRET_KEY, DB_*, and GEMINI_API_KEY

# 5. Run migrations
python manage.py migrate

# 6. Ingest the sample dataset
python manage.py ingest_csv Files/CDC-COVID-FAQ.csv

# 7. Start the server
python manage.py runserver
```

The API is live at `http://127.0.0.1:8000/api/documents/`.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in every value.

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Django secret key |
| `DEBUG` | No | `True` for local dev, `False` in production (default: `False`) |
| `ALLOWED_HOSTS` | No | Comma-separated hostnames (default: `*`) |
| `GEMINI_API_KEY` | Yes | Google Gemini API key from [aistudio.google.com](https://aistudio.google.com/) |
| `DB_NAME` | Yes | PostgreSQL database name |
| `DB_USER` | Yes | PostgreSQL username |
| `DB_PASSWORD` | Yes | PostgreSQL password |
| `DB_HOST` | No | Database host (default: `localhost`) |
| `DB_PORT` | No | Database port (default: `5432`) |

Generate a secret key:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## Management Commands

### Ingest a CSV file

```bash
python manage.py ingest_csv Files/CDC-COVID-FAQ.csv
```

**Re-ingestion is idempotent:** existing chunks for the same filename are deleted and replaced — no duplicates.

**Required CSV columns:** `name`, `category`, `question`, `answer`

Sample output:
```
Ingesting 'Files/CDC-COVID-FAQ.csv' …
Done.  source='CDC-COVID-FAQ.csv'  ingested=142  skipped=0
```

---

## API Reference

Base URL: `http://127.0.0.1:8000/api/documents/`

---

### `POST /query/`

Run a RAG query over the ingested documents.

**Request (JSON)**
```json
{
    "query": "How does COVID-19 spread?",
    "category": "Transmission"
}
```
`category` is optional — omit it to search all documents.

**Response 200**
```json
{
    "answer": "COVID-19 spreads mainly through respiratory droplets ...",
    "context": [
        "Q: How does COVID-19 spread?\nA: COVID-19 spreads mainly ...",
        "Q: Can I get COVID-19 from surfaces?\nA: ..."
    ],
    "source_count": 2
}
```

**Response 400** — missing or blank query
```json
{"error": "query is required and must not be blank."}
```

**Response 503** — Gemini API unavailable after retries
```json
{"error": "LLM generation failed after 3 attempt(s): ..."}
```

**cURL example**
```bash
curl -X POST http://127.0.0.1:8000/api/documents/query/ \
     -H "Content-Type: application/json" \
     -d "{\"query\": \"Who is at risk for COVID-19?\"}"
```

---

### `POST /ingest/`

Upload a CSV file and ingest it. Accepts `multipart/form-data`.

```bash
curl -X POST http://127.0.0.1:8000/api/documents/ingest/ \
     -F "file=@Files/CDC-COVID-FAQ.csv"
```

**Response 200**
```json
{
    "source": "CDC-COVID-FAQ.csv",
    "ingested": 142,
    "skipped": 0
}
```

**Response 400** — wrong file type or missing columns
```json
{"error": "CSV is missing required column(s): {'answer'}. Found: {'question', 'name', 'category'}"}
```

---

### `GET /health/`

Liveness/readiness probe. Checks DB connectivity and returns chunk count.

```bash
curl http://127.0.0.1:8000/api/documents/health/
```

**Response 200**
```json
{"status": "ok", "chunk_count": 142}
```

---

## Configuration Tuning

All RAG constants live in [`documents/services/config.py`](documents/services/config.py). Edit that file to tune behaviour without touching service code.

| Constant | Default | Effect |
|---|---|---|
| `TOP_K` | `5` | Maximum chunks returned per query |
| `DISTANCE_THRESHOLD` | `0.7` | Cosine distance cut-off — lower = stricter relevance filter |
| `EMBED_BATCH_SIZE` | `20` | Rows embedded per Gemini API call during ingestion |
| `MAX_RETRIES` | `3` | Retry attempts on Gemini 429 quota errors |
| `EMBED_DIM` | `768` | Embedding dimension — **do not change** without a new migration |

> Changing `EMBED_DIM` requires a migration to alter the `embedding` column **and** re-embedding every stored row. The dimension is baked into every vector.

---

## Deployment (Render)

1. Push the repo to GitHub.
2. Create a new **Web Service** on Render pointing to this repo.
3. **Build command:** `pip install -r requirements.txt && python manage.py migrate`
4. **Start command:** `gunicorn core.wsgi:application`
5. Add all environment variables in Render's dashboard.
6. Provision a **PostgreSQL** add-on and set `DB_*` vars.
7. After first deploy, run the ingest command via Render's shell tab:
   ```
   python manage.py ingest_csv Files/CDC-COVID-FAQ.csv
   ```

For large datasets, add an HNSW index for faster approximate search:
```sql
CREATE INDEX ON documents_documentchunk USING hnsw (embedding vector_cosine_ops);
```

---

## Async Ingestion with Celery

For large CSV files the synchronous `/ingest/` endpoint blocks a worker thread for minutes. See [`documents/tasks.py`](documents/tasks.py) for a ready-to-uncomment Celery task and full setup instructions.

Quick summary:
```bash
# 1. Start Redis
docker run -p 6379:6379 redis

# 2. Uncomment CELERY_* settings in core/settings.py

# 3. Uncomment the task in documents/tasks.py

# 4. Start the worker alongside Django
celery -A core worker --loglevel=info
```

---

## Production Checklist

- [ ] Set `DEBUG=False` and narrow `ALLOWED_HOSTS` to your domain
- [ ] Uncomment `IsAuthenticated` in `documents/views.py`
- [ ] Move from free Gemini tier to a paid plan under real traffic
- [ ] Add HNSW index on the `embedding` column for large datasets
- [ ] Configure a log aggregator (Sentry, Datadog) instead of console-only logging
- [ ] Never commit `.env` — use your platform's secret manager

---

## Known Limitations

- One CSV row = one chunk. Long answers aren't sub-chunked, so very long rows can dilute retrieval quality.
- No conversation memory — each query is independent.
- No re-ranking step; raw cosine distance is trusted. A cross-encoder re-ranker would improve precision.
- Free-tier Gemini quotas make this unsuitable for high traffic as-is.

---

## License

MIT — do what you like, no warranty.
