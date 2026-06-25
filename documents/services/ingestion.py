# documents/services/ingestion.py
#
# Handles embedding text and loading CSV data into the vector store.
#
# Why we embed text:
#   Raw text can't be compared mathematically.  An embedding model converts a
#   string into a dense float vector (768 numbers here) where semantically
#   similar texts land close together in vector space.  Storing these vectors
#   in PostgreSQL via pgvector lets us run fast nearest-neighbour queries at
#   retrieval time without a separate vector database.

import os
import csv
import time
import logging
from google.genai import types

from documents.models import DocumentChunk
from .client import get_genai_client
from .config import (
    EMBED_MODEL,
    EMBED_DIM,
    EMBED_BATCH_SIZE,
    MAX_RETRIES,
    RETRY_BACKOFF_BASE,
    REQUIRED_CSV_COLUMNS,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _retry_embed(texts: list[str]) -> list[list[float]]:
    """
    Call the Gemini embedding API for a batch of texts, retrying on quota
    errors (HTTP 429 / RESOURCE_EXHAUSTED) with exponential back-off.

    Returns a list of embedding vectors in the same order as `texts`.
    Raises RuntimeError after all retries are exhausted.
    """
    client = get_genai_client()

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.embed_content(
                model=EMBED_MODEL,
                # Passing a list produces one embedding per element — this
                # is the batch path that saves round-trips during ingestion.
                contents=texts,
                config=types.EmbedContentConfig(output_dimensionality=EMBED_DIM),
            )
            return [emb.values for emb in response.embeddings]

        except Exception as exc:
            is_quota_error = "RESOURCE_EXHAUSTED" in str(exc) or "429" in str(exc)

            if is_quota_error and attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF_BASE ** attempt  # 1 s, 2 s, 4 s …
                logger.warning(
                    "Gemini quota exhausted (attempt %d/%d), retrying in %ds …",
                    attempt + 1,
                    MAX_RETRIES,
                    wait,
                )
                time.sleep(wait)
                continue

            raise RuntimeError(f"Embedding failed after {attempt + 1} attempt(s): {exc}") from exc

    raise RuntimeError("Embedding failed: all retries exhausted")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def embed_text(text: str) -> list[float]:
    """
    Embed a single text string.

    Kept as a public helper so retrieval.py can call it for query embedding
    without needing to know about batch logic.
    """
    return _retry_embed([text])[0]


def ingest_csv(file_path: str, source_name: str | None = None) -> dict:
    """
    Load a CSV file into the vector store.

    Each row becomes one DocumentChunk whose `content` is:
        "Q: <question>\\nA: <answer>"

    The text is embedded and stored alongside the raw content so that at query
    time we can embed the user's question, find the closest chunks, and feed
    them to the LLM as context.

    Args:
        file_path:   Absolute or relative path to the CSV file on disk.
        source_name: Override the source label stored on each chunk.
                     Defaults to the file's basename.  Useful when the file
                     was saved to a temp path but you want the original name.

    Returns:
        {"source": str, "ingested": int, "skipped": int}

    Raises:
        ValueError  – CSV is missing required columns or is empty.
        RuntimeError – Embedding API call failed after all retries.

    Idempotency:
        Any existing chunks for `source` are deleted before insertion, so
        re-running the command on the same file is safe and won't create
        duplicate chunks.
    """
    source = source_name or os.path.basename(file_path)

    # --- Idempotency: remove stale chunks for this source ---
    deleted_count, _ = DocumentChunk.objects.filter(source=source).delete()
    if deleted_count:
        logger.info("Deleted %d existing chunk(s) for source '%s'", deleted_count, source)

    rows_to_embed: list[tuple[str, str, str]] = []  # (content, category, name)
    skipped = 0

    # --- Parse and validate CSV ---
    with open(file_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            raise ValueError(f"CSV file '{file_path}' is empty or has no header row.")

        actual_cols = {c.strip() for c in reader.fieldnames}
        missing = REQUIRED_CSV_COLUMNS - actual_cols
        if missing:
            raise ValueError(
                f"CSV is missing required column(s): {missing}. "
                f"Found: {actual_cols}"
            )

        for row_num, row in enumerate(reader, start=2):  # row 1 is the header
            question = row.get("question", "").strip()
            answer = row.get("answer", "").strip()

            if not question or not answer:
                logger.warning("Row %d: empty question or answer — skipping.", row_num)
                skipped += 1
                continue

            content = f"Q: {question}\nA: {answer}"
            category = row.get("category", "").strip()
            name = row.get("name", "").strip()
            rows_to_embed.append((content, category, name))

    if not rows_to_embed:
        logger.warning("No valid rows found in '%s'.", file_path)
        return {"source": source, "ingested": 0, "skipped": skipped}

    # --- Embed in batches to minimise API round-trips ---
    objects: list[DocumentChunk] = []

    for batch_start in range(0, len(rows_to_embed), EMBED_BATCH_SIZE):
        batch = rows_to_embed[batch_start : batch_start + EMBED_BATCH_SIZE]
        texts = [r[0] for r in batch]

        try:
            embeddings = _retry_embed(texts)
        except RuntimeError as exc:
            # Log which rows failed and continue rather than aborting the whole import.
            logger.error(
                "Batch starting at row %d failed to embed, skipping %d rows. Error: %s",
                batch_start + 2,
                len(batch),
                exc,
            )
            skipped += len(batch)
            continue

        for (content, category, name), embedding in zip(batch, embeddings):
            objects.append(
                DocumentChunk(
                    source=source,
                    category=category,
                    content=content,
                    embedding=embedding,
                    metadata={"name": name},
                )
            )

    # --- Persist all valid chunks in a single query ---
    DocumentChunk.objects.bulk_create(objects)
    logger.info(
        "Ingested %d chunk(s) from '%s'; skipped %d.", len(objects), source, skipped
    )

    return {"source": source, "ingested": len(objects), "skipped": skipped}
