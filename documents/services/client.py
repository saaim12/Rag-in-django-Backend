# documents/services/client.py
#
# Provides a single shared Gemini client instance for all service modules.
# Using a cached singleton avoids creating a new HTTP client on every request,
# which would be wasteful and slow.

import os
import logging
from functools import lru_cache
from google import genai

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_genai_client() -> genai.Client:
    """
    Return the shared Gemini API client, constructing it on first call.

    lru_cache(maxsize=1) turns this into a lazy singleton — the Client is
    built once and reused for the lifetime of the process.  This is safe
    because google.genai.Client is thread-safe.

    Raises RuntimeError if GEMINI_API_KEY is not set in the environment.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is not set. "
            "Add it to your .env file."
        )
    logger.debug("Initialising Gemini client")
    return genai.Client(api_key=api_key)
