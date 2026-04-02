import os
import logging
from functools import lru_cache
from typing import Any, Optional

from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings


logger = logging.getLogger(__name__)

# Load env regardless of where uvicorn is started from.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))




@lru_cache(maxsize=1)
def get_embeddings() -> Embeddings:
    """Return embeddings implementation.

    Priority:
    1) Cloudflare Workers AI via AI Gateway (OpenAI compatible)
    2) Google Gemini embeddings if GOOGLE_API_KEY is set
    """
    
    cf_token = (os.getenv("CF_API_TOKEN") or "").strip()
    cf_gateway_url = (os.getenv("CF_GATEWAY_URL") or "").strip()
    google_api_key = (os.getenv("GOOGLE_API_KEY") or "").strip()

    try:
        # ---- 1) Cloudflare Workers AI Embeddings ----
        if cf_token and cf_gateway_url:
            from langchain_cloudflare import CloudflareWorkersAIEmbeddings
            
            # Extract account_id from gateway URL
            parts = cf_gateway_url.split('/')
            account_id = parts[4] if len(parts) > 4 else ""
            
            cf_model = os.getenv("CF_EMBEDDING_MODEL", "@cf/baai/bge-base-en-v1.5")
            
            logger.info("Using native Cloudflare Embeddings with model: %s", cf_model)
            return CloudflareWorkersAIEmbeddings(
                account_id=account_id,
                api_token=cf_token,
                model_name=cf_model,
            )

        # ---- 2) Google Gemini fallback ----
        if google_api_key:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            model = os.getenv("GOOGLE_EMBEDDING_MODEL", "models/text-embedding-004")
            return GoogleGenerativeAIEmbeddings(
                model=model,
                google_api_key=google_api_key,
            )

        raise RuntimeError(
            "No embedding config found. Set CF_API_TOKEN + CF_GATEWAY_URL or GOOGLE_API_KEY."
        )

    except Exception:
        logger.exception("Embedding provider init failed")
        raise RuntimeError("Embedding provider unavailable")


def _env(name: str) -> Optional[str]:
    value = os.getenv(name)
    return value if value else None


def _require_env(name: str) -> str:
    value = _env(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value

def get_pinecone_index():
    from pinecone import Pinecone
    api_key = _require_env("PINECONE_API_KEY")
    index_name = _require_env("PINECONE_INDEX_NAME")
    pc = Pinecone(api_key=api_key)
    return pc.Index(index_name)



def get_pinecone_vectorstore(namespace: Optional[str] = None):
    """Create a Pinecone-backed vector store.

    Namespace is intentionally a runtime argument so you can isolate embeddings per role
    (e.g. 'user', 'admin', 'partner', 'affiliate', 'sales').
    """

    # Use runtime imports to avoid forcing unnecessary dependencies on all flows.
    # However, these ARE required for guest/public RAG.
    from pinecone import Pinecone
    from langchain_pinecone import PineconeVectorStore

    api_key = _require_env("PINECONE_API_KEY")
    index_name = _require_env("PINECONE_INDEX_NAME")
    text_key = os.getenv("PINECONE_TEXT_KEY", "text")

    pc = Pinecone(api_key=api_key)
    index = pc.Index(index_name)

    return PineconeVectorStore(
        index=index,
        embedding=get_embeddings(),
        text_key=text_key,
        namespace=namespace,
    )


def get_retriever(*, namespace: Optional[str], k: int = 4):
    vectorstore = get_pinecone_vectorstore(namespace=namespace)
    return vectorstore.as_retriever(search_kwargs={"k": k})


def retrieve_with_scores(*, namespace: Optional[str], query: str, k: int = 4):
    """Retrieve documents with similarity scores (best-effort).

    Returns: (docs, scores)
    - docs: list[Document]
    - scores: list[float] aligned with docs when available
    """

    vectorstore = get_pinecone_vectorstore(namespace=namespace)

    # PineconeVectorStore supports similarity_search_with_score.
    results = vectorstore.similarity_search_with_score(query, k=k)
    docs = [doc for (doc, _score) in results]
    scores = [float(_score) for (_doc, _score) in results]
    return docs, scores


def format_docs(docs) -> str:
    return "\n\n".join(getattr(d, "page_content", str(d)) for d in (docs or []))


def upsert_texts(
    *,
    namespace: Optional[str],
    texts: list[str],
    metadatas: Optional[list[dict[str, Any]]] = None,
    ids: Optional[list[str]] = None,
):
    try :
        vectorstore = get_pinecone_vectorstore(namespace=namespace)

        if not vectorstore:
            logger.warning("Upsert skipped (no vectorstore)")
            return []


        return vectorstore.add_texts(texts=texts, metadatas=metadatas, ids=ids)

    except Exception:
        logger.exception("Upsert failed")
        return []
    
    
def build_schema_context(results, text_key="text", max_chars=4000):
    """
    Extracts context safely from Pinecone results.
    Works for any namespace and avoids crashes.
    """

    if not results:
        return ""
    matches = results.get("matches", [])
    if not matches:
        return ""
    context_parts = []

    for match in matches:
        metadata = match.get("metadata", {})
        text = metadata.get(text_key)

        # fallback if different key names used
        if not text:
            text = metadata.get("content") or metadata.get("chunk") or ""
        if text:
            context_parts.append(text.strip())
    context = "\n\n".join(context_parts)
    # Prevent sending too much to LLM
    return context[:max_chars]