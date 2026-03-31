import os
import logging
from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def get_llm():
    """Return chat model.

    Priority:
    1) Cloudflare Workers AI via AI Gateway  (CF_API_TOKEN + CF_GATEWAY_URL)
    2) Google Gemini                         (GOOGLE_API_KEY)
    3) Offline stub
    """

    cf_token = (os.getenv("CF_API_TOKEN") or "").strip()
    cf_gateway_url = (os.getenv("CF_GATEWAY_URL") or "").strip()
    cf_model = (os.getenv("CF_MODEL") or "@cf/meta/llama-3.3-70b-instruct-fp8-fast").strip()
    google_api_key = (os.getenv("GOOGLE_API_KEY") or "").strip()
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))

    # ---- 1) Cloudflare Workers AI (primary) ----
    # CF AI Gateway exposes an OpenAI-compatible endpoint at:
    #   {gateway_url}/v1/chat/completions
    # ChatOpenAI (langchain-openai) appends /chat/completions to base_url,
    # so base_url must be {gateway_url}/v1.
    if cf_token and cf_gateway_url:
        try:
            from langchain_openai import ChatOpenAI

            # OpenAI-compatible base: gateway + /v1
            base_url = cf_gateway_url.rstrip("/") + "/v1"

            logger.info("[LLM Provider] Cloudflare Workers AI — model=%s base=%s", cf_model, base_url)
            return ChatOpenAI(
                model=cf_model,
                api_key=cf_token,
                base_url=base_url,
                temperature=temperature,
            )
        except Exception as exc:
            logger.error("Failed to initialise Cloudflare LLM: %s — falling back to Gemini", exc)

    # ---- 2) Google Gemini (fallback) ----
    if google_api_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
            logger.info("[LLM Provider] Google Gemini — model=%s", gemini_model)
            return ChatGoogleGenerativeAI(
                model=gemini_model,
                google_api_key=google_api_key,
                temperature=temperature,
            )
        except Exception as exc:
            logger.error("Failed to initialise Gemini: %s", exc)

    # ---- 3) Offline stub ----
    logger.warning("[LLM Provider] OFFLINE MODE — no CF or Gemini credentials found")

    def _offline_response(prompt_value):
        try:
            messages = prompt_value.to_messages()
            last_user = next(
                (m.content for m in reversed(messages)
                 if getattr(m, "type", "") in ("human", "user")),
                "",
            )
        except Exception:
            last_user = ""

        content = (
            "[OFFLINE MODE] No Cloudflare or Gemini credentials configured. "
            f"You asked: {last_user}"
        )
        return AIMessage(content=content)

    return RunnableLambda(_offline_response)