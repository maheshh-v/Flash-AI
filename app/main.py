import os
import logging
import re
from typing import Optional
import hashlib


from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import redis


from app.chains import build_chain, build_partner_chain, build_admin_chain
from app.mongo_executor import run_mongo_query_from_string
from app.mongo_query_service import execute_safe_query, generate_mongo_query, query_improve
from app.session_store import ensure_session, get_session_messages,save_message
from app.auth import AuthContext, get_auth_context



from app.vectorstore import format_docs, retrieve_with_scores
from app.recommendation import (
    get_service_recommendation,
    is_proximity_query,
    get_nearest_space_hint,
    build_contextual_recommendation_reply,
    is_company_registration_recommendation_query,
)
from app.flashspace_advisor_logic import get_flashspace_fast_response, build_flashspace_runtime_hint


from app.router import router_chain
from app.embedding_client import get_embedding
from app.vectorstore import get_pinecone_index
from functools import lru_cache
from app.vectorstore import get_pinecone_index, build_schema_context
import json
from app.mongo_utils import extract_collections
from app.schema_context import build_context



from app.mongo_query_service import formatting_output
from app.prompts import ADMIN_MONGO_PROMPT
from app.prompts import PARTNER_MONGO_PROMPT, PARTNER_QUERY_NORMALIZER_PROMPT, PARTNER_QUERY_MONGO_GUARD_PROMPT

from app.mongo_query_service import generate_mongo_query, generate_pymongo_query, normalize_partner_db_query, validate_partner_query_mongo_alignment
from app.llm import get_llm
from app.safety_guard import predict_query_safety
from app.cache_service import CacheUnavailableError, get_cache_service



logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


# Redis connection for distributed rate limiting
try:
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    redis_client = redis.from_url(redis_url, decode_responses=True)
    redis_client.ping()
    logger.info("Redis connected for rate limiting")
except Exception as e:
    logger.warning(f"Redis unavailable, using in-memory rate limiting: {e}")
    redis_client = None




_GUEST_KNOWN_CITIES = {
    "bangalore", "bengaluru", "mumbai", "delhi", "new delhi", "gurgaon", "gurugram",
    "noida", "pune", "hyderabad", "chennai", "kolkata", "ahmedabad", "jaipur",
    "lucknow", "indore", "bhopal", "surat", "kochi", "coimbatore", "nagpur",
    "visakhapatnam", "vijayawada", "patna", "bhubaneswar", "chandigarh", "gujarat", "gujrat",
}

def get_user_identifier(request: Request) -> str:
    """Extract user_id from auth context for rate limiting."""
    try:
        auth = request.state.auth
        return f"user:{auth.tenant_id}:{auth.user_id}"
    except:
        return f"ip:{get_remote_address(request)}"


def get_ip_identifier(*args, **kwargs) -> str:
    """Robust IP key extractor for SlowAPI key_func call variations."""
    request = None
    if args:
        request = args[0]
    elif "request" in kwargs:
        request = kwargs.get("request")

    if request is None:
        return "ip:unknown"
    return f"ip:{get_remote_address(request)}"

limiter = Limiter(
    key_func=get_user_identifier,
    storage_uri=redis_url if redis_client else None
)




app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)



chain = build_chain()
partner_chain = build_partner_chain()  
admin_chain = build_admin_chain()
summary_chain = ChatPromptTemplate.from_messages([
    (
        "system",
        "You summarize prior chat context for a guest support assistant.\n"
        "Return a compact, deeply contextual memory summary with:\n"
        "1) user goals and constraints\n"
        "2) confirmed facts and preferences\n"
        "3) unresolved questions\n"
        "4) guidance for answering the next question consistently.\n"
        "Do not invent facts."
    ),
    (
        "human",
        "Current question:\n{query}\n\n"
        "Recent conversation (oldest to newest):\n{history}\n\n"
        "Write the contextual summary now."
    ),
]) | get_llm()



@lru_cache(maxsize=1)
def get_index():
    return get_pinecone_index()


class Query(BaseModel):
    query: str
    conversation_id: str = Field(default="default", min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    session_id: Optional[str] = Field(
        default=None,
        description="Optional session ID"
    )



def normalize_result(result):
    from pymongo.cursor import Cursor
    from pymongo.command_cursor import CommandCursor

    if isinstance(result, (Cursor, CommandCursor)):
        return list(result)

    return result


def _normalize_query_for_cache(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _retrieve_with_scores_cached(*, namespace: str, query: str, k: int, role: str) -> tuple[list[Document], list[float]]:
    cache = get_cache_service()
    domain = "rag_retrieval"
    role_norm = (role or "guest").strip().lower()
    payload = {
        "namespace": namespace,
        "query": _normalize_query_for_cache(query),
        "k": k,
        "index": os.getenv("PINECONE_INDEX_NAME", ""),
    }
    key = cache.make_key(role_norm, domain, payload)
    ttl = cache.get_ttl(domain)

    try:
        cached = cache.get_json(key, role=role_norm, domain=domain)
        if isinstance(cached, dict):
            docs_raw = cached.get("docs") or []
            scores_raw = cached.get("scores") or []
            docs = [
                Document(
                    page_content=str(item.get("page_content", "")),
                    metadata=item.get("metadata") or {},
                )
                for item in docs_raw
                if isinstance(item, dict)
            ]
            scores = [float(s) for s in scores_raw]
            if docs:
                return docs, scores
    except CacheUnavailableError:
        pass

    docs, scores = retrieve_with_scores(namespace=namespace, query=query, k=k)
    to_store = {
        "docs": [
            {"page_content": getattr(d, "page_content", ""), "metadata": getattr(d, "metadata", {})}
            for d in docs
        ],
        "scores": [float(s) for s in scores],
    }
    cache.set_json(key, to_store, ttl, role=role_norm, domain=domain)
    return docs, scores


def _get_guest_context_summary(session_id: str, query: str, max_turns: int = 15) -> str:
    """Summarize recent guest/AI history to improve contextual continuity."""
    try:
        rows = get_session_messages(session_id)
        if not rows:
            return ""

        convo_lines = []
        for row in rows:
            role = (getattr(row, "role", "") or "").lower()
            content = (getattr(row, "content", "") or "").strip()
            if not content:
                continue
            if role in {"user", "human"}:
                convo_lines.append(f"Guest: {content}")
            elif role in {"ai", "assistant"}:
                convo_lines.append(f"AI: {content}")

        if not convo_lines:
            return ""

        history_text = "\n".join(convo_lines[-(max_turns * 2):])
        cache = get_cache_service()
        domain = "guest_summary"
        payload = {
            "session_id": session_id,
            "query": _normalize_query_for_cache(query),
            "history_hash": _hash_text(history_text),
            "model": os.getenv("OPENAI_MODEL") or os.getenv("CHAT_MODEL") or "",
        }
        key = cache.make_key("guest", domain, payload)
        ttl = cache.get_ttl(domain)
        cached = cache.get_json(key, role="guest", domain=domain)
        if isinstance(cached, dict) and isinstance(cached.get("summary"), str):
            return cached.get("summary", "")

        summary_resp = summary_chain.invoke({"query": query, "history": history_text})
        summary_text = (getattr(summary_resp, "content", "") or "").strip()
        if summary_text:
            cache.set_json(key, {"summary": summary_text}, ttl, role="guest", domain=domain)
            return summary_text
    except Exception:
        logger.exception("Failed to summarize guest history")

    return ""

def _get_guest_recent_user_text(session_id: str, max_turns: int = 20) -> str:
    """Return recent raw guest utterances to preserve exact entities like city names."""
    try:
        rows = get_session_messages(session_id)
        if not rows:
            return ""

        user_lines = []
        for row in rows:
            role = (getattr(row, "role", "") or "").lower()
            content = (getattr(row, "content", "") or "").strip()
            if role in {"user", "human"} and content:
                user_lines.append(content)

        if not user_lines:
            return ""

        return "\n".join(user_lines[-max_turns:])
    except Exception:
        logger.exception("Failed to load recent guest user text")
        return ""


def _extract_city_from_text(text: str) -> str:
    query = (text or "").strip().lower()
    if not query:
        return ""
    for city in _GUEST_KNOWN_CITIES:
        if re.search(rf"\b{re.escape(city)}\b", query):
            return city
    return ""


def _handle_admin_chat(query: str, session_id: str, actor_id: str, conversation_id: str):
    index = get_index()
    decision = router_chain.invoke({"input": query})
    route_answer = str(decision.route)
    print("===================ROUTER DECISION====================")
    print(decision.route)

    if route_answer == "db":
       
        query = f"{query}. context-> admin id : {actor_id} , role : admin"
        cache = get_cache_service()
        domain = "admin_mongo_generate"
        payload = {
            "query": _normalize_query_for_cache(query),
            "actor_id": actor_id,
            "model": os.getenv("OPENAI_MODEL") or os.getenv("CHAT_MODEL") or "",
        }
        key = cache.make_key("admin", domain, payload)
        ttl = cache.get_ttl(domain)
        try:
            cached = cache.get_json(key, role="admin", domain=domain)
        except CacheUnavailableError:
            return {"error": "Cache unavailable for admin query generation"}
        if isinstance(cached, dict) and isinstance(cached.get("context"), str) and isinstance(cached.get("mongo_code"), str):
            context = cached["context"]
            mongo_code = cached["mongo_code"]
        else:
            context, mongo_code = generate_pymongo_query(query)
            try:
                cache.set_json(
                    key,
                    {"context": context or "", "mongo_code": mongo_code or ""},
                    ttl,
                    role="admin",
                    domain=domain,
                )
            except CacheUnavailableError:
                return {"error": "Cache unavailable for admin query generation"}

        print("================== context ====================")
        print(context)


        result = execute_safe_query(mongo_code)

        result = normalize_result(result)

        print("================== RESULT ========================")
        print(result)
       

        admin_reply = formatting_output(query , context, mongo_code, result)


        save_message(
            session_id=session_id,
            role="user",
            content=query,
            conversation_id=conversation_id,
            actual_role="admin"
        )
        save_message(
            session_id=session_id,
            role="ai",
            content= admin_reply['answer'],
            conversation_id=conversation_id,
            actual_role="admin"
        )
        return {"reply": admin_reply['answer'], "session_id": session_id}

    response = admin_chain.invoke(
        {"question": query, "context": ""},
        config={"configurable": {"session_id": session_id, "namespace": "admin"}}
    )
    return {"reply": response.content, "session_id": session_id}

def get_rate_limits_for_role(role: str) -> tuple:
    """Return (per_minute, burst) limits based on role."""
    limits = {
        "public": ("10/minute", "3/5seconds"),
        "guest": ("10/minute", "3/5seconds"),
        "guest_amenity": ("10/minute", "3/5seconds"),
        "partner": ("30/minute", "7/5seconds"),
        "admin": ("100/minute", "20/5seconds"),
    }
    return limits.get(role, ("20/minute", "5/5seconds"))



@app.post("/chat")
@limiter.limit("1000/minute")  # Global limit
@limiter.limit("100/minute", key_func=get_ip_identifier)  # IP limit
def chat(
    request: Request,
    data: Query,
    auth: AuthContext = Depends(get_auth_context),
):
    try:

        request.state.auth = auth


        # Apply role-based rate limits
        per_min, burst = get_rate_limits_for_role(auth.role)
        user_key = f"user:{auth.tenant_id}:{auth.user_id}"

        # Check role-specific limits manually
        if redis_client:
            # Check per-minute limit
            min_key = f"ratelimit:{user_key}:minute"
            min_count = redis_client.incr(min_key)
            if min_count == 1:
                redis_client.expire(min_key, 60)
            if min_count > int(per_min.split("/")[0]):
                raise RateLimitExceeded(f"Rate limit exceeded: {per_min}")

            # Check burst limit
            burst_key = f"ratelimit:{user_key}:burst"
            burst_count = redis_client.incr(burst_key)
            if burst_count == 1:
                redis_client.expire(burst_key, 5)
            if burst_count > int(burst.split("/")[0]):
                raise RateLimitExceeded(f"Burst limit exceeded: {burst}")



        query_text = (data.query or "").strip()
        if not query_text:
            return {"reply": "Query cannot be empty.", "session_id": (data.session_id or "").strip()}





    
        session_id = (data.session_id or "").strip()
        if not session_id:
            
            session_id = f"{auth.tenant_id}:{auth.user_id}:{data.conversation_id}"

        # for backward compatibility, ensure session exists even if session_id is not provided (using conversation_id as part of session_id)
        ensure_session(
            session_id=session_id,
            user_id=auth.user_id,
            tenant_id=auth.tenant_id,
            conversation_id=data.conversation_id,
            role=auth.role,
        )



        role = auth.role
        # namespace = auth.namespace
        # # session_id = f"{auth.tenant_id}:{auth.user_id}:{data.conversation_id}"
        # session_id = auth.session_id

        recent_user_text_for_fast = ""
        remembered_city_for_fast = ""
        if role in {"public"}:
            recent_user_text_for_fast = _get_guest_recent_user_text(session_id=session_id, max_turns=20)
            remembered_city_for_fast = _extract_city_from_text(recent_user_text_for_fast)

        logger.info("/chat namespace=%s session_id=%s query=%r", role, session_id, data.query)

        if role in {"public"}:
            fast_reply = get_flashspace_fast_response(
                query_text,
                conversation_hint=recent_user_text_for_fast,
                remembered_city=remembered_city_for_fast,
            )
            if fast_reply:
                return {
                    "reply": fast_reply,
                    "session_id": session_id,
                }

        safety = predict_query_safety(query_text, role)
        logger.info("[Safety Check] role=%s query=%r allowed=%s category=%s reason=%s", 
                    role, query_text[:50], safety.get("allowed"), safety.get("category"), safety.get("reason"))
        
        if not safety.get("allowed", True):
            logger.warning(
                "Blocked unsafe query | role=%s session_id=%s category=%s reason=%s",
                role,
                session_id,
                safety.get("category", "unknown"),
                safety.get("reason", ""),
            )
            return {"reply": "This is not allowed.", "session_id": session_id}


        if role in {"public"}:     # guest aliases
            history_summary = ""
            try:

                docs = []
                context = ""
                role=auth.role
                query=data.query
                session_id=session_id
                # actor_id=auth.actor_id,

                recent_user_text = recent_user_text_for_fast
                remembered_city = remembered_city_for_fast


                history_summary = _get_guest_context_summary(
                    session_id=session_id,
                    query=query,
                    max_turns=15
                )

        
                # Guest role: ONLY use Pinecone RAG, NO MongoDB access
                retrieval_k = 20 if is_proximity_query(query) else 4
                docs, _score = _retrieve_with_scores_cached(namespace=role, query=query, k=retrieval_k, role=role)
                print("Retrieved docs:", list(zip(docs, _score)))
                context = format_docs(docs)

                # Extract explicit valid cities from the retrieved documents
                from app.recommendation import _build_space_candidates
                doc_candidates = _build_space_candidates(docs)
                valid_cities = list(set([c.get("city", "").strip().title() for c in doc_candidates if c.get("city")]))
                if valid_cities:
                    context = f"WARNING! THE ONLY VALID CITIES IN THIS RETRIEVED CONTEXT ARE: {', '.join(valid_cities)}. IF THE USER ASKS FOR A CITY NOT IN THIS LIST, YOU MUST REJECT IT.\n\n" + context
                else:
                    context = "WARNING! NO CITIES FOUND IN RETRIEVED CONTEXT. YOU MUST REJECT SPECIFIC CITY REQUESTS.\n\n" + context

                recommendation_reply = build_contextual_recommendation_reply(
                    query=query,
                    docs=docs,
                    conversation_hint=recent_user_text or history_summary,
                    remembered_city=remembered_city,
                )
                if (not recommendation_reply) and is_company_registration_recommendation_query(query):
                    target_city = _extract_city_from_text(f"{query}\n{recent_user_text}") or remembered_city
                    pricing_query = (
                        f"virtual office GST price company registration {target_city}".strip()
                        if target_city
                        else "virtual office GST price company registration"
                    )
                    pricing_docs, _ = _retrieve_with_scores_cached(
                        namespace=role,
                        query=pricing_query,
                        k=12,
                        role=role,
                    )
                    recommendation_reply = build_contextual_recommendation_reply(
                        query=query,
                        docs=pricing_docs,
                        conversation_hint=recent_user_text or history_summary,
                        remembered_city=target_city or remembered_city,
                    )
                if recommendation_reply:
                    return {"reply": recommendation_reply, "session_id": session_id}

                nearest_hint = get_nearest_space_hint(query, docs)
                if nearest_hint:
                    context += f"\n\nSystem Nearest Match (High Priority):\n{nearest_hint}"


                if history_summary:
                    context += f"\n\nConversation Summary:\n{history_summary}"

                if remembered_city:
                                context += (
                                    f"\n\nConversation Memory:\n"
                                    f"User already specified city as '{remembered_city}'. "
                                    f"Do not ask for city again unless user changes it."
                                )
                else:
                                context += (
                                    "\n\nConversation Memory:\n"
                                    "No user-confirmed city has been provided yet. "
                                    "Do NOT claim the user previously mentioned any city/location."
                                )




                rec_hint = get_service_recommendation(query,conversation_hint=recent_user_text or history_summary,)
                if rec_hint:
                    context += f"\n\nSystem Recommendation: {rec_hint}"

                policy_hint = build_flashspace_runtime_hint(
                    query=query,
                    conversation_hint=recent_user_text or history_summary,
                    remembered_city=remembered_city,
                )
                if policy_hint:
                    context += f"\n\nSystem Policy:\n{policy_hint}"
                
            except Exception:
                logger.exception("Retrieval failed; continuing with empty context")
                context = f"Conversation Summary:\n{history_summary}" if history_summary else ""

            response = chain.invoke(
                {"question": query, "context": context},
                config={"configurable": {"session_id": session_id, "namespace": role}}
            )

            reply = response.content
            payload = {"reply": reply, "session_id": session_id}
            return payload
           


        elif role == "admin" :
            print(f"===========ADMIN CHAT DETECTED {auth.user_id}=================")
            try:
                return _handle_admin_chat(
                    query=data.query,
                    session_id=session_id,
                    actor_id=auth.user_id,
                    conversation_id=data.conversation_id,
                )
            except Exception as e:
                logger.exception("Failed to handle admin chat")
                return {"error": str(e)}
        

        elif role == "partner":

            index = get_index()


            role=auth.role
            query=data.query
            session_id=session_id
            actor_id=auth.user_id

            print(f"Received query from partner: role={role}, query={query}, session_id={session_id}, actor_id={actor_id}")


            decision = router_chain.invoke({"input": query})
            route_answer = decision.route
            route_answer = str(route_answer)
            print(decision.route)

            

            if route_answer == "db" :
                    
                    
                    query_vector = get_embedding(query)

                    results = index.query(
                    vector=query_vector,
                    top_k=10,
                    namespace= os.getenv("PARTNER_PINECONE_NAMESPACE"),
                    include_metadata=True
                )
                    kb1 = index.query(
                    vector=query_vector,
                    top_k=1,
                    namespace= "partner_kb6",
                    include_metadata=True
                )
                    SCORE_THRESHOLD = 0.0   # tune between 0.7–0.85

                    print("Knowledge base retrieval result:", kb1)

                    if kb1["matches"] and kb1["matches"][0]["score"] >= SCORE_THRESHOLD:
                      
                        kb1 = build_schema_context(kb1)
                        print("Using business knowledge")
                    else:
                        # No relevant knowledge → move to schema retrieval
                        kb1 = ""
                        print("No business knowledge, try next source")


                    original_query = query
                    try:
                        query = normalize_partner_db_query(
                            user_query=query,
                            partner_id=actor_id,
                            normalizer_prompt=PARTNER_QUERY_NORMALIZER_PROMPT
                        )
                        print(f"Normalized partner DB query: {query}")
                    except Exception:
                        logger.exception("Partner query normalization failed; using original query")
                        query = original_query

                    query = f"{query}. context-> partner : {actor_id} , role : partner"

                    schema_context = build_schema_context(results)
                    
                    print("===========================================")
                    print(kb1)
                    print(type(kb1))
                    print("===========================================")
         
                    print(f"------- QUERY >>> {query}")
                    mongo_code = generate_mongo_query(
                    query,
                    kb1 + schema_context,
                    mongo_prompt=PARTNER_MONGO_PROMPT
                )
                    print("--------->>>>> > > >>Generated MongoDB code:", mongo_code)
                    if isinstance(mongo_code, str):
                        mongo_code = json.loads(mongo_code)

                    

                    collectionx = extract_collections(mongo_code)

                    print("==========================================")
                    print(collectionx)

                    print("==================COLLECTION CONTEXT========================")

                    contextt = build_context(collectionx)
                    print(contextt)
                    print("==========================================")

                    mongo_code = generate_mongo_query(
                        query,
                        contextt
                    )

                    mongo_code = query_improve(kb1+contextt+query, mongo_code)

                    print(f"FINAL MONGO CODE : {mongo_code}")

                    print("=========================================================")

                    guard = validate_partner_query_mongo_alignment(
                        user_query=query,
                        mongo_code=mongo_code,
                        guard_prompt=PARTNER_QUERY_MONGO_GUARD_PROMPT,
                    )
                    if not guard.get("allowed", True):
                        blocked_message = guard.get("message") or "Generated query is unsafe or does not match your request."
                        logger.warning("Partner Mongo guard blocked query | session_id=%s reason=%s", session_id, blocked_message)
                        return {"allowed": False, "reply": blocked_message, "session_id": session_id}
                
                    result = run_mongo_query_from_string(mongo_code, role="partner")
                    
                    print("=========================================================")
                    print(result)

                    output = formatting_output(query , contextt, mongo_code, result)

                    if isinstance(output, dict):
                        partner_reply =(
                            output.get("answer")
                            or output.get("reply")
                            or output.get("response")
                            or json.dumps(output)
                        )
                    else :
                        partner_reply = str(output)

                    try :
                        save_message(
                            session_id=session_id,
                            role="user",
                            content=query,
                            conversation_id=data.conversation_id,
                            actual_role=role
                        )

                        save_message(
                            session_id=session_id,
                            role="ai",
                            content=partner_reply,
                            conversation_id=data.conversation_id,
                            actual_role=role
                        )
                        return {"reply": output['answer'], "session_id": session_id}
            
                    except Exception as e:
                        logger.exception("Failed to save messages for partner")
                        return {"error": str(e)}

            else :
                response = partner_chain.invoke(
                    {"question": query, "context": ""},
                        config={"configurable": {"session_id": session_id, "namespace": role}}
                )

                reply = response.content
                payload = {"reply": reply, "session_id": session_id}
                return payload

    

    
    except Exception as e:
        logger.exception("Chat failed")
        return {"error": str(e)}
    

@app.get("/health")
def health():
    return {"status": "ok"}
