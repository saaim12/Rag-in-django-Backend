# documents/services/rag.py
#
# The top-level RAG (Retrieval-Augmented Generation) pipeline.
#
# RAG in three steps:
#   1. Retrieve – embed the user's question and pull the closest stored chunks.
#   2. Augment  – build a prompt that includes those chunks as context.
#   3. Generate – send the prompt to the LLM and return its answer.
#
# Grounding the prompt with retrieved context is what separates RAG from plain
# chat: the model can only draw on the supplied documents, so it can't
# hallucinate facts it doesn't have.

import time
import logging

from .client import get_genai_client
from .retrieval import retrieve_chunks
from .config import GENERATION_MODEL, MAX_RETRIES, RETRY_BACKOFF_BASE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------
# The instruction "using ONLY the context below" is the grounding constraint.
# Without it the model would blend retrieved facts with its own training data,
# making answers harder to audit.
_PROMPT_TEMPLATE = """\
You are a helpful assistant. Answer the question using ONLY the context below.
If the answer is not in the context, say "I don't know based on the provided documents."

Context:
{context}

Question: {question}

Answer:"""


def rag_query(
    user_query: str,
    category: str | None = None,
) -> dict:
    """
    Run the full RAG pipeline for a user question.

    Args:
        user_query: The question from the API request.
        category:   Optional category to scope retrieval (passed through to
                    retrieve_chunks).

    Returns:
        {
            "answer":       str,   # LLM-generated answer
            "context":      list,  # raw chunk texts used as context
            "source_count": int,   # how many chunks were retrieved
        }

    Raises:
        RuntimeError – if the Gemini generation call fails after all retries.
    """
    # Step 1 – Retrieve relevant chunks from the vector store.
    chunks = retrieve_chunks(user_query, category=category)

    if not chunks:
        # No chunk passed the relevance threshold — return a safe "I don't
        # know" instead of asking the LLM to work with nothing.
        return {
            "answer": "I don't know based on the provided documents.",
            "context": [],
            "source_count": 0,
        }

    # Step 2 – Assemble the grounded prompt.
    # Chunks are separated by a visible divider so the model can distinguish
    # where one passage ends and the next begins.
    context_block = "\n\n---\n\n".join(chunks)
    prompt = _PROMPT_TEMPLATE.format(context=context_block, question=user_query)

    # Step 3 – Generate the answer with retry on quota errors.
    client = get_genai_client()

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=GENERATION_MODEL,
                contents=prompt,
            )
            return {
                "answer": response.text,
                "context": chunks,
                "source_count": len(chunks),
            }

        except Exception as exc:
            is_quota_error = "RESOURCE_EXHAUSTED" in str(exc) or "429" in str(exc)

            if is_quota_error and attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF_BASE ** attempt
                logger.warning(
                    "Gemini generation quota exhausted (attempt %d/%d), retrying in %ds …",
                    attempt + 1,
                    MAX_RETRIES,
                    wait,
                )
                time.sleep(wait)
                continue

            raise RuntimeError(
                f"LLM generation failed after {attempt + 1} attempt(s): {exc}"
            ) from exc

    raise RuntimeError("LLM generation failed: all retries exhausted")
