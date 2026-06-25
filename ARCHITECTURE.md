# Architecture

This document describes the data flow and component responsibilities for the Django RAG backend.

---

## High-level Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        INGESTION  (run once per dataset)                │
│                                                                         │
│  CSV file                                                               │
│  (name, category,  ──► ingest_csv()  ──► embed_texts_batch()           │
│   question, answer)     ingestion.py      (Gemini gemini-embedding-001) │
│                              │                                          │
│                              ▼                                          │
│                    DocumentChunk.objects.bulk_create()                  │
│                    PostgreSQL  documents_documentchunk                  │
│                    ┌──────────────────────────────────┐                 │
│                    │ source   │ category │ content     │                 │
│                    │ embedding(768-dim)  │ metadata    │                 │
│                    └──────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                        QUERY  (every API request)                       │
│                                                                         │
│  POST /api/documents/query/                                             │
│  { "query": "..." }                                                     │
│          │                                                              │
│          ▼                                                              │
│    QueryView (views.py)                                                 │
│          │                                                              │
│          ▼                                                              │
│    rag_query()  ──────────────────────────────────────────────────┐    │
│    (rag.py)                                                        │    │
│          │                                                         │    │
│          ▼  Step 1: Retrieve                                       │    │
│    retrieve_chunks()                                               │    │
│    (retrieval.py)                                                  │    │
│          │                                                         │    │
│          ├──► embed_text(query)                                    │    │
│          │    (ingestion.py → Gemini)                              │    │
│          │                                                         │    │
│          ├──► CosineDistance ORM query → pgvector                  │    │
│          │    ORDER BY distance ASC LIMIT top_k                    │    │
│          │                                                         │    │
│          └──► filter(distance <= threshold) → chunks[]             │    │
│                                                │                   │    │
│                              ┌─────────────────┘                   │    │
│                              ▼  Step 2: Augment                    │    │
│                       Build grounded prompt                        │    │
│                       "Answer using ONLY:                          │    │
│                        {chunk1}---{chunk2}---...                   │    │
│                        Question: {user_query}"                     │    │
│                              │                                     │    │
│                              ▼  Step 3: Generate                   │    │
│                       client.models.generate_content()             │    │
│                       (Gemini gemini-2.5-flash)                    │    │
│                              │                                     │    │
│                              └─────────────────────────────────────┘    │
│                                                                         │
│          ▼                                                              │
│    { "answer": "...", "context": [...], "source_count": N }            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Component Responsibilities

### `documents/services/config.py`

Single source of truth for all magic numbers: model names, `EMBED_DIM`, `TOP_K`, distance threshold, retry settings. Change values here — never scatter them through service files.

### `documents/services/client.py`

A lazy singleton (`@lru_cache`) that builds the `google.genai.Client` once on first use and reuses it for the process lifetime. Raises `RuntimeError` early if `GEMINI_API_KEY` is missing.

### `documents/services/ingestion.py`

- Validates CSV columns against `REQUIRED_CSV_COLUMNS`.
- Deletes existing chunks for the same `source` before insert (idempotency).
- Embeds rows in batches of `EMBED_BATCH_SIZE` to reduce API round-trips.
- Retries each batch on `RESOURCE_EXHAUSTED` (429) with exponential back-off.
- Returns `{"source", "ingested", "skipped"}`.

### `documents/services/retrieval.py`

- Embeds the user's query with the same model used during ingestion (critical — vectors must come from the same model to be comparable).
- Runs a `CosineDistance` annotated queryset, ordered ascending (closest first).
- Applies a threshold filter: chunks farther than `DISTANCE_THRESHOLD` are discarded. Without this, the LLM would receive irrelevant context and fabricate an answer.
- Supports an optional `category` filter.

### `documents/services/rag.py`

Orchestrates the full RAG pipeline. If retrieval returns nothing (all chunks exceeded the threshold), it short-circuits and returns `"I don't know…"` without calling the generation API at all. Retries generation on quota errors.

### `documents/views.py`

Three DRF `APIView` subclasses:

| View | Method | Responsibility |
|---|---|---|
| `QueryView` | POST | Validate input, call `rag_query()`, map exceptions to HTTP errors |
| `IngestView` | POST | Accept multipart upload, write to temp file, call `ingest_csv()`, clean up |
| `HealthView` | GET | Ping DB with `SELECT 1`, return chunk count |

All views have `IsAuthenticated` scaffolding commented with `# TODO` — flip it on before production.

### `documents/models.py` — `DocumentChunk`

One row per Q&A pair. The `embedding` column is a `vector(768)` type (pgvector native). The `source` and `category` columns have B-tree indexes for fast filtering. A vector HNSW index (not in migrations, must be added manually) is recommended for datasets > ~10,000 rows.

### `documents/tasks.py`

A fully-commented Celery task stub. Disabled by default — no import-time side effects. See the file header for a step-by-step enablement guide.

---

## Why pgvector instead of a dedicated vector DB?

Dedicated vector databases (Weaviate, Pinecone, Milvus) add operational complexity — another service to deploy, monitor, and pay for. pgvector keeps vectors in the same PostgreSQL instance as the rest of the data, which means:

- No network hop between the Django app and the vector store
- ACID guarantees on ingestion (the bulk insert and the delete-before-insert are in the same transaction context)
- Standard Django ORM for all queries
- One fewer moving part to operate

The trade-off: pgvector's approximate nearest-neighbour (HNSW) index is slower than purpose-built vector DBs at very high scale (tens of millions of vectors). For most document Q&A use cases this is not the bottleneck.

---

## Why cosine distance instead of L2 / dot product?

Embeddings encode the *direction* of meaning, not magnitude. Cosine distance (1 − cosine similarity) measures the angle between two vectors and is therefore invariant to the length of the text. A short question and a long answer can still be very close in cosine space if they discuss the same concept.

pgvector supports all three metrics; we use `CosineDistance` from `pgvector.django`.
