# documents/models.py
#
# Database model for the RAG vector store.
#
# Why one table instead of separate Documents + Chunks tables?
#   For this dataset (Q&A pairs) each row is already an atomic unit of
#   information — there is no multi-paragraph document to split.  Keeping
#   everything in a single table simplifies queries and migrations.

from django.db import models
from pgvector.django import VectorField


class DocumentChunk(models.Model):
    """
    A single unit of retrievable knowledge.

    Fields:
        source    – Filename the chunk came from (e.g. "CDC-COVID-FAQ.csv").
                    Used by the idempotency guard in ingest_csv to delete stale
                    chunks before re-ingestion.
        category  – Topic label from the CSV (e.g. "Transmission").
                    Exposed as an optional filter on the /query/ endpoint.
        content   – The raw text that was embedded, in the form:
                        "Q: <question>\\nA: <answer>"
                    Returned verbatim as retrieval context to the LLM.
        embedding – 768-dimensional float vector produced by
                    gemini-embedding-001.  pgvector stores this as a native
                    PostgreSQL `vector(768)` column and indexes it for fast
                    approximate nearest-neighbour search.
        metadata  – Arbitrary key/value store for extra fields from the CSV
                    (currently {"name": "..."}).
        created_at – UTC timestamp of ingestion; useful for debugging stale data.
    """

    source = models.CharField(max_length=255)
    category = models.CharField(max_length=255, blank=True)
    content = models.TextField()
    # dimensions must stay 768 — changing it requires a new migration AND
    # re-embedding every row (the stored vectors would be incompatible).
    embedding = VectorField(dimensions=768)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["source"]),
            models.Index(fields=["category"]),
        ]

    def __str__(self) -> str:
        return f"[{self.category}] {self.content[:80]}"
