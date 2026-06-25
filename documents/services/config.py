# documents/services/config.py
#
# Single source of truth for all Gemini model names and RAG tuning constants.
# Change values here rather than hunting through service files.

# --- Gemini model identifiers ---
# gemini-embedding-001 produces 768-dim vectors and is the best available
# embedding model for semantic search as of mid-2025.
EMBED_MODEL = "gemini-embedding-001"

# gemini-2.5-flash balances speed and quality for answer generation.
GENERATION_MODEL = "gemini-2.5-flash"

# --- Embedding dimension ---
# Must match the VectorField(dimensions=768) in DocumentChunk.
# Changing this requires a new migration AND re-embedding the full dataset —
# do not change without a migration plan.
EMBED_DIM = 768

# --- Retrieval settings ---
# Number of chunks to fetch from the vector store per query.
TOP_K = 5

# Cosine distance threshold for relevance filtering.
# Cosine distance ranges from 0 (vectors are identical) to 2 (vectors are
# opposite). A distance > DISTANCE_THRESHOLD means the retrieved chunk is
# probably not relevant to the query, so we discard it rather than force a
# weak answer.  0.7 is a reasonable default; tune downward to be stricter.
DISTANCE_THRESHOLD = 0.7

# --- Ingestion settings ---
# How many rows to embed in a single Gemini batch call.
# Batching reduces round-trips during CSV ingestion significantly.
EMBED_BATCH_SIZE = 20

# Columns that must be present in an ingested CSV.
REQUIRED_CSV_COLUMNS = {"category", "question", "answer"}

# --- Retry / back-off settings ---
# How many times to retry a Gemini call when the API returns 429
# RESOURCE_EXHAUSTED (quota limit hit).
MAX_RETRIES = 3

# Base seconds for exponential back-off: wait = RETRY_BACKOFF_BASE ** attempt
# attempt 0 → 1 s, attempt 1 → 2 s, attempt 2 → 4 s
RETRY_BACKOFF_BASE = 2
