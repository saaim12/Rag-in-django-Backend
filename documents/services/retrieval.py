# documents/services/retrieval.py
#
# Vector similarity search against the DocumentChunk table.
#
# Why cosine distance?
#   We store embedding vectors that encode the *direction* of meaning rather
#   than magnitude.  Cosine distance (1 - cosine similarity) measures the
#   angle between two vectors:
#     0   → vectors point in exactly the same direction (identical meaning)
#     1   → vectors are orthogonal (unrelated)
#     2   → vectors point in opposite directions (antonyms / opposites)
#
#   Filtering by a distance threshold stops us from returning chunks that are
#   technically "the closest" but still semantically unrelated — which would
#   cause the LLM to hallucinate an answer from irrelevant text.

import logging

from pgvector.django import CosineDistance

from documents.models import DocumentChunk
from .ingestion import embed_text
from .config import TOP_K, DISTANCE_THRESHOLD

logger = logging.getLogger(__name__)


def retrieve_chunks(
    query: str,
    top_k: int = TOP_K,
    distance_threshold: float = DISTANCE_THRESHOLD,
    category: str | None = None,
) -> list[str]:
    """
    Embed `query` then return the `top_k` most similar chunk contents.

    Only chunks with cosine distance ≤ `distance_threshold` are returned.
    If no chunk passes the threshold the list is empty, and the caller
    (rag_query) should reply "I don't know" rather than fabricate an answer.

    Args:
        query:              The user's natural-language question.
        top_k:              Maximum number of chunks to return.
        distance_threshold: Discard chunks with cosine distance above this
                            value.  Lower = stricter relevance filter.
        category:           Optional category filter.  When supplied only
                            chunks whose `category` field matches are searched.
                            Useful for scoping queries to a topic area.

    Returns:
        List of `content` strings ordered by ascending distance (most
        relevant first).
    """
    # Embed the query into the same vector space as the stored chunks.
    # This is what makes semantic similarity possible — the same model that
    # embedded the documents is used here, so distances are meaningful.
    query_embedding = embed_text(query)

    qs = DocumentChunk.objects.annotate(
        distance=CosineDistance("embedding", query_embedding)
    )

    if category:
        qs = qs.filter(category__iexact=category)

    # Fetch top_k candidates ordered by ascending distance (closest first).
    candidates = qs.order_by("distance")[:top_k]

    # Apply threshold filter: discard chunks that are too far away.
    relevant = [r for r in candidates if r.distance <= distance_threshold]

    if not relevant:
        logger.info(
            "No chunks within threshold %.2f for query: %.60s…",
            distance_threshold,
            query,
        )

    return [r.content for r in relevant]
