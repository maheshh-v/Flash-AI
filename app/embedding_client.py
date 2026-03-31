"""
embedding_client.py

Provides get_embedding(text) -> list[float] for use in the Partner Pinecone query flow.

Previously called the old OpenAI proxy (stirringminds.com).
Now uses Google Gemini text-embedding-004 (same model as app/vectorstore.py)
to guarantee vector-dimension consistency with the indexed Pinecone namespace.

Dimension: 768 (text-embedding-004 default)
"""

import logging
import os
import time

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def get_embedding(text: str, retries: int = 3) -> list:
    """Return an embedding vector for the given text.

    Uses Google Gemini text-embedding-004 via the langchain-google-genai client.
    Falls back to a zero vector of the expected dimension if all retries fail.
    """
    google_api_key = (os.getenv("GOOGLE_API_KEY") or "").strip()
    model = os.getenv("GOOGLE_EMBEDDING_MODEL", "models/text-embedding-004")

    if not google_api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Cannot generate embeddings for Partner Pinecone query."
        )

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            embedder = GoogleGenerativeAIEmbeddings(
                model=model,
                google_api_key=google_api_key,
            )
            vector = embedder.embed_query(text)
            logger.debug("[Embedding] Google Gemini model=%s dim=%d", model, len(vector))
            return vector

        except Exception as exc:
            last_exc = exc
            logger.warning("[Embedding] Attempt %d/%d failed: %s", attempt + 1, retries, exc)
            if attempt < retries - 1:
                time.sleep(1)

    raise RuntimeError(f"Embedding failed after {retries} attempts: {last_exc}") from last_exc
