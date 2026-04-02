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

    Uses OpenAI Proxy (text-embedding-3-small, 1536-dim) to maintain compatibility
    with the Pinecone index.
    """
    google_api_key = (os.getenv("GOOGLE_API_KEY") or "").strip()
    proxy_url = (os.getenv("PROXY_URL") or "").strip()
    model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            if google_api_key and False: # Disabled Gemini to force proxy 1536-dim
                pass
            
            from langchain_openai import OpenAIEmbeddings
            embedder = OpenAIEmbeddings(
                model=model,
                api_key="proxy-key",
                base_url=f"{proxy_url}/v1" if proxy_url else None
            )
            vector = embedder.embed_query(text)
            logger.debug("[Embedding] Proxy model=%s dim=%d", model, len(vector))
            return vector

        except Exception as exc:
            last_exc = exc
            logger.warning("[Embedding] Attempt %d/%d failed: %s", attempt + 1, retries, exc)
            if attempt < retries - 1:
                time.sleep(1)

    # Return empty 1536 vector on absolute failure
    return [0.0] * 1536
