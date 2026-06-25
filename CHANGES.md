# Changes

Summary of what was refactored and why, relative to the original working prototype.

---

## New files

| File | Purpose |
|---|---|
| `documents/services/config.py` | Centralises all model names and tuning constants. Previously scattered as magic strings. |
| `documents/services/client.py` | Shared `get_genai_client()` singleton. Previously each service file constructed its own `genai.Client` at module import time — wasteful and would crash on import if the env var wasn't set. |
| `documents/tasks.py` | Celery async ingestion stub with full setup guide in comments. |
| `ARCHITECTURE.md` | ASCII data-flow diagram and per-component responsibility notes. |
| `CHANGES.md` | This file. |

---

## Modified files

### `core/settings.py`

- **Removed** the four `print()` calls that leaked database credentials to stdout on every server start.
- **Fixed bug:** `GEMINI_API_KEY` was being read from `os.getenv("OPENAI_API_KEY")` — wrong variable name. Now reads from `os.getenv("GEMINI_API_KEY")`.
- Added `ALLOWED_HOSTS` driven by an env var (comma-separated) so production deployments can narrow the list without code changes.
- Added `DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"` to silence Django's system check warning.
- Added `REST_FRAMEWORK` defaults block with empty auth/permission classes (with a TODO comment to enable auth before production).
- Added `LOGGING` config that routes `documents.*` at INFO level to the console and keeps everything else at WARNING. Prevents log spam from Django internals while showing service-layer activity.
- Added commented `CELERY_*` settings block so the Celery path is one uncomment away.

### `documents/services/ingestion.py`

- **Idempotency guard:** `DocumentChunk.objects.filter(source=source).delete()` runs before insert. Re-ingesting the same file is now safe.
- **Column validation:** raises `ValueError` with a clear message if any of `name, category, question, answer` are missing from the CSV.
- **Row-level skipping:** empty `question` or `answer` fields are logged and skipped rather than crashing the whole import.
- **Batch embedding:** rows are embedded in batches of `EMBED_BATCH_SIZE` (20) in a single Gemini API call instead of one call per row — dramatically fewer round-trips.
- **Retry with back-off:** `RESOURCE_EXHAUSTED` (HTTP 429) errors trigger up to `MAX_RETRIES` retries with exponential back-off.
- **`source_name` parameter:** callers (e.g., `IngestView`) can override the source label so temp file paths don't leak into the DB.
- Return type changed from `int` → `dict` with `{source, ingested, skipped}`.

### `documents/services/retrieval.py`

- **Distance threshold:** chunks with `cosine_distance > DISTANCE_THRESHOLD` are filtered out before returning. Without this, a query with no relevant content would still receive the "least bad" chunk and the LLM would fabricate an answer.
- **Category filter:** optional `category` argument scopes the DB query.
- **Configurable `top_k` and `distance_threshold`** via function parameters with config.py defaults.
- Uses shared `embed_text()` from `ingestion.py` rather than a separate client instantiation.

### `documents/services/rag.py`

- Uses shared `get_genai_client()` instead of constructing a new client at module level.
- Retry logic on generation (same pattern as ingestion).
- Response shape extended to `{answer, context, source_count}` — the `source_count` is useful for debugging threshold tuning.
- Prompt template extracted to a named constant `_PROMPT_TEMPLATE` for readability.

### `documents/views.py`

- **`QueryView`:** accepts optional `category` field, maps `RuntimeError` → 503, maps unexpected errors → 500 with a generic message (no stack trace leak).
- **`IngestView` (new):** `POST /api/documents/ingest/` accepts a multipart CSV upload, writes to a temp file, calls `ingest_csv()`, deletes the temp file in a `finally` block.
- **`HealthView` (new):** `GET /api/documents/health/` returns `{"status": "ok", "chunk_count": N}` or 503 on DB failure.
- `IsAuthenticated` scaffolding added as commented-out code with `# TODO` on every view.

### `documents/urls.py`

Added named routes for the two new endpoints:
- `ingest/` → `IngestView`
- `health/` → `HealthView`

### `documents/models.py`

- Added `Meta.indexes` for `source` and `category` fields — speeds up the idempotency delete and the category filter query.
- Docstring explains each field and why embedding dimension is frozen.

### `documents/management/commands/ingest_csv.py`

- Checks that the file exists before calling the service (raises `CommandError` cleanly instead of a Python traceback).
- Handles `ValueError` (column validation) and `RuntimeError` (Gemini failure) and surfaces them as `CommandError` with readable messages.
- Updated output to show the full `{source, ingested, skipped}` result dict.

### `.gitignore`

Replaced single-line `venv` with a comprehensive ignore covering Python bytecode, `.env`, `Files/` uploads, IDE folders, OS junk, test artefacts, and static/media output.

### `README.md`

Complete rewrite in UTF-8. Previous file was UTF-16 LE encoded. New version covers quick start, all env vars, API reference with request/response examples, configuration tuning table, deployment guide, and production checklist.

---

## Migration added

`0006_add_chunk_indexes.py` — adds B-tree indexes on `source` and `category` to `documents_documentchunk`. No data changes; safe to apply to an existing populated table.

---

## What was NOT changed

- Embedding dimension stays at 768 — re-embedding the full dataset is expensive and the current model/dimension combination works well.
- Migration history is preserved; `0001`–`0005` are untouched.
- The `CDC-COVID-FAQ.csv` sample file is untouched.
- No LangChain dependency was added — the pipeline uses the `google-genai` SDK directly, which is simpler and has fewer moving parts for this use case.
