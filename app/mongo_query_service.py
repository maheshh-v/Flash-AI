import requests
import os
import re
import json
import hashlib
from app.mongo_executor import get_mongo_db
from app.cache_service import CacheUnavailableError, get_cache_service


CHAT_URL = os.getenv("CHAT_URL")


def _hash_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def generate_mongo_query(user_query, schema_context, mongo_prompt=None, role: str = "partner"):
    selected_prompt = mongo_prompt 
    cache = get_cache_service()
    role_norm = (role or "partner").strip().lower()
    domain = "mongo_generate"

    # Combine everything into ONE question (proxy requirement)
    question = f"""
{selected_prompt}

Schema Context:
{schema_context}

User Request:
{user_query}

CRTICAL: WHENNEVER customers is involved than first join join role:user of users collection with booking collection's user to and filter using partner to know targetted customers.

Generate MongoDB Python query only.
DO NOT EVERY INVENT NEW FIELD WHICH IS NOT PRESENT IN SCHEMA. If user is asking for a field that is not present in the schema, return an empty result or handle it gracefully without making assumptions.
"""

    cache_payload = {
        "user_query": user_query,
        "schema_hash": _hash_text(schema_context),
        "prompt_hash": _hash_text(selected_prompt or ""),
        "model": os.getenv("OPENAI_MODEL") or os.getenv("CHAT_MODEL") or "",
        "chat_url": CHAT_URL or "",
    }
    cache_key = cache.make_key(role_norm, domain, cache_payload)
    ttl = cache.get_ttl(domain)
    try:
        cached = cache.get_json(cache_key, role=role_norm, domain=domain)
        if isinstance(cached, dict) and isinstance(cached.get("answer"), str):
            return cached["answer"]
    except CacheUnavailableError:
        raise RuntimeError("Admin-sensitive cache unavailable for mongo_generate")

    payload = {
        "question": question
    }

    headers = {
        "Content-Type": "application/json"
    }



    response = requests.post(
        CHAT_URL,
        json=payload,
        headers=headers,
        timeout=30
    )

    if response.status_code != 200:
        raise Exception(response.text)

    data = response.json()

    # Your proxy likely returns:
    # { "answer": "db.collection.find()" }
    answer = data.get("answer", "").strip()
    try:
        cache.set_json(cache_key, {"answer": answer}, ttl, role=role_norm, domain=domain)
    except CacheUnavailableError:
        raise RuntimeError("Admin-sensitive cache unavailable for mongo_generate")
    return answer




def query_improve(schema_context, mongo_query, role: str = "partner"):
    cache = get_cache_service()
    role_norm = (role or "partner").strip().lower()
    domain = "mongo_improve"

    question = f"""
Role: Act as a Senior MongoDB Database Engineer and Query Optimizer.

DO NOT EVERY INVENT NEW FIELD WHICH IS NOT PRESENT IN SCHEMA. If user is asking for a field that is not present in the schema, return an empty result or handle it gracefully without making assumptions.
For any MongoDB ObjectId field (e.g., _id, partner, partnerId, user, spaceId), always use ObjectId("...") and never use {{"$oid":"..."}} or plain string IDs.

Objective:
Correct the provided MongoDB query using the Schema and Business Logic.
Do not Auto Generate any Field if they are not in Schema & Relationships.

Intent Canonicalization Rule (CRITICAL):
Before improving the Mongo query, normalize ambiguous place-phrases in the user intent.
If user asks customer-related questions "under/in/from space(s), meeting room(s), virtual office(s) <name>",
reinterpret as property-scoped intent by property name when schema links those spaces to properties.

Generalized rewrite pattern:
- "show customers name under space or meeting rooms <X>"
  -> "show customers name under property of name <X>"

Example:
- Input intent: show customers name under space or metting rooms Tremblay - Borer Hub
- Canonical intent: show customers name under proprty of name Tremblay - Borer Hub

Input:
Bad Query: {mongo_query}
Schema & Relationships: {schema_context}

Reasoning Instructions (Internal Only):
Think step-by-step internally before answering. Perform the following checks:
1. Syntax Audit – remove illegal MongoDB patterns.
2. Path Validation – ensure relationships and field paths are correct.
3. Data Type Alignment – wrap all 24-character IDs using "$oid".
4. Performance Optimization:
   - Place $match as early as possible.
   - Avoid unnecessary $lookup.
   - Use index-friendly filters.
5. Financial Integrity:
   - If financial data is involved, include important Fields
   - If the user asks for a time-based metric (year/month/date range), enforce filtering by createdAt using $gte/$lt boundaries.
   - Use collection-specific status mapping:
     bookings -> "active"/"not active"
     invoices -> "paid"/"not paid"
     Do not mix status values across collections.
      

IMPORTANT:
Do NOT show your reasoning.
Do NOT output analysis, notes, or explanations.
Use the reasoning internally only.
Never use $toObjectId inside $match.
Always use '$oid' format for IDs.
Always convert '$oid' to ObjectId(), use schema-valid fields (prefer totalAmount for payments), and place $match first.
CRITICAL NAME FIELD RULE:
- For partner/customer user-name outputs, use "fullName" only.
- Never project or reference user/customer name as "name" or "full_name".

Output Format (STRICT):
Return ONLY valid JSON.
Do NOT include markdown, text, or explanations.

$lookup Optimization Rules (CRITICAL):

1. Use $lookup ONLY when necessary.
   - If the required filter field exists in the base collection, DO NOT use $lookup.

2. Filter Early.
   - Always place $match before $lookup for fields that exist in the base collection.
   - This reduces the dataset before the join.

3. Filter Inside $lookup (Preferred).
   - When filtering on joined collection fields (e.g., partner, property, user),
     use pipeline-based $lookup with $match inside it.
   - Avoid joining full documents and filtering later.

4. Avoid Array Matching Errors.
   - If using simple $lookup (localField/foreignField) and filtering after it,
     you MUST add:
        '$unwind': '$joinedField'
   - Never match directly on an array field.

5. Short-Circuit Joins.
   - If the required ID is already available in the base collection,
     do not join to another collection.
   - Example:
       payments.property exists → filter directly.
       Do NOT join properties unless filtering by properties.partner.

6. Time Filter Rule (CRITICAL).
   - For time-scoped requests (e.g., "in 2026", "this month", "between dates"), use createdAt for date filtering.
   - Preserve createdAt filters if already present; do not replace with unrelated date fields.

Allowed JSON structures:

Find query:

  'collection': '<name>',
  'filter': ,
  "projection": ,
  "limit": <int>


Aggregation:

  "collection": "<name>",
  "pipeline": []

CRITICAL LIMIT RULE:
- If intent is a single-record/self-detail request (e.g., my profile, my email, my details, latest single item), enforce limit = 1.
- Do not expand such single-record requests to limit 50.
- Use larger limits only when user explicitly asks for lists/multiple records.


FINAL RULE:
If the response contains anything other than valid JSON, the answer is incorrect.
"""

    cache_payload = {
        "schema_hash": _hash_text(schema_context),
        "mongo_query_hash": _hash_text(str(mongo_query)),
        "prompt_hash": _hash_text(question),
        "model": os.getenv("OPENAI_MODEL") or os.getenv("CHAT_MODEL") or "",
        "chat_url": CHAT_URL or "",
    }
    cache_key = cache.make_key(role_norm, domain, cache_payload)
    ttl = cache.get_ttl(domain)
    try:
        cached = cache.get_json(cache_key, role=role_norm, domain=domain)
        if isinstance(cached, dict) and isinstance(cached.get("answer"), str):
            return cached["answer"]
    except CacheUnavailableError:
        raise RuntimeError("Admin-sensitive cache unavailable for mongo_improve")

    payload = {
        "question": question
    }

    headers = {
        "Content-Type": "application/json"
    }



    response = requests.post(
        CHAT_URL,
        json=payload,
        headers=headers,
        timeout=30
    )

    if response.status_code != 200:
        raise Exception(response.text)

    data = response.json()

    # Your proxy likely returns:
    # { "answer": "db.collection.find()" }
    answer = data.get("answer", "").strip()
    try:
        cache.set_json(cache_key, {"answer": answer}, ttl, role=role_norm, domain=domain)
    except CacheUnavailableError:
        raise RuntimeError("Admin-sensitive cache unavailable for mongo_improve")
    return answer



def formatting_output(query_text, schema_context, mongo_code, result, role_label="Partner"):
    cache = get_cache_service()
    role_norm = (role_label or "partner").strip().lower()
    domain = "formatting_output"
    question = f"""
  Humanize the output.

  Partner asked: {query_text}

  Context:

  - relevant schema: {schema_context}
  - llm generated json mongo query : {mongo_code}
  - Result: {result}

You are talking to a Role {role_label}.

  Instruction:
  Respond naturally. Assume the value is {result}.
  Use correct pluralization.
  Use indian Rupees style
  """

    cache_payload = {
        "query_text": query_text,
        "schema_hash": _hash_text(str(schema_context)),
        "mongo_code_hash": _hash_text(str(mongo_code)),
        "result_hash": _hash_text(json.dumps(result, sort_keys=True, default=str)),
        "model": os.getenv("OPENAI_MODEL") or os.getenv("CHAT_MODEL") or "",
    }
    cache_key = cache.make_key(role_norm, domain, cache_payload)
    ttl = cache.get_ttl(domain)
    try:
        cached = cache.get_json(cache_key, role=role_norm, domain=domain)
        if isinstance(cached, dict):
            return cached
    except CacheUnavailableError:
        raise RuntimeError("Admin-sensitive cache unavailable for formatting_output")

    payload = {
        "question": question.strip()
    }

    headers = {
        "Content-Type": "application/json"
        # "Authorization": "Bearer YOUR_API_KEY"  # if required
    }

    response = requests.post(CHAT_URL, json=payload, headers=headers)
    out = response.json()
    try:
        cache.set_json(cache_key, out, ttl, role=role_norm, domain=domain)
    except CacheUnavailableError:
        raise RuntimeError("Admin-sensitive cache unavailable for formatting_output")
    return out


def normalize_partner_db_query(user_query: str, partner_id: str, normalizer_prompt: str) -> str:
    """Normalize partner DB intent before Mongo query generation."""
    cache = get_cache_service()
    role_norm = "partner"
    domain = "partner_normalize"
    question = f"""
{normalizer_prompt}

Partner Context:
- partner_id: {partner_id}
- role: partner

Original User Query:
{user_query}

Return only rewritten normalized query text.
"""

    cache_payload = {
        "user_query": user_query,
        "partner_id": partner_id,
        "prompt_hash": _hash_text(normalizer_prompt),
        "model": os.getenv("OPENAI_MODEL") or os.getenv("CHAT_MODEL") or "",
        "chat_url": CHAT_URL or "",
    }
    cache_key = cache.make_key(role_norm, domain, cache_payload)
    ttl = cache.get_ttl(domain)
    cached = cache.get_json(cache_key, role=role_norm, domain=domain)
    if isinstance(cached, dict) and isinstance(cached.get("answer"), str):
        return cached["answer"] or user_query

    payload = {
        "question": question.strip()
    }

    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(
        CHAT_URL,
        json=payload,
        headers=headers,
        timeout=30
    )

    if response.status_code != 200:
        raise Exception(response.text)

    data = response.json()
    normalized = (data.get("answer", "") or "").strip()
    answer = normalized or user_query
    cache.set_json(cache_key, {"answer": answer}, ttl, role=role_norm, domain=domain)
    return answer


def validate_partner_query_mongo_alignment(user_query: str, mongo_code, guard_prompt: str) -> dict:
    """Validate generated Mongo query against partner user intent and safety constraints."""
    cache = get_cache_service()
    role_norm = "partner"
    domain = "mongo_guard"
    mongo_text = mongo_code if isinstance(mongo_code, str) else json.dumps(mongo_code)
    question = f"""
{guard_prompt}

Partner Request:
{user_query}

Generated Mongo Query:
{mongo_text}

Return only JSON with keys: allowed, message.
"""

    cache_payload = {
        "user_query": user_query,
        "mongo_hash": _hash_text(mongo_text),
        "guard_prompt_hash": _hash_text(guard_prompt),
        "model": os.getenv("OPENAI_MODEL") or os.getenv("CHAT_MODEL") or "",
    }
    cache_key = cache.make_key(role_norm, domain, cache_payload)
    ttl = cache.get_ttl(domain)
    cached = cache.get_json(cache_key, role=role_norm, domain=domain)
    if isinstance(cached, dict) and "allowed" in cached:
        return {
            "allowed": bool(cached.get("allowed", True)),
            "message": str(cached.get("message", "")),
        }

    payload = {"question": question.strip()}
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(
            CHAT_URL,
            json=payload,
            headers=headers,
            timeout=30
        )
        if response.status_code != 200:
            return {"allowed": True, "message": "Validation skipped due to validator error"}

        data = response.json()
        answer = (data.get("answer", "") or "").strip()

        # Try direct JSON first
        try:
            parsed = json.loads(answer)
        except Exception:
            # Fallback: trim to outer JSON object
            start = answer.find("{")
            end = answer.rfind("}")
            if start != -1 and end != -1 and end > start:
                parsed = json.loads(answer[start:end + 1])
            else:
                return {"allowed": True, "message": "Validation skipped due to parse error"}

        allowed = bool(parsed.get("allowed", True))
        message = str(parsed.get("message", "")).strip() or ("Allowed" if allowed else "Blocked by validator")
        out = {"allowed": allowed, "message": message}
        cache.set_json(cache_key, out, ttl, role=role_norm, domain=domain)
        return out
    except Exception:
        return {"allowed": True, "message": "Validation skipped due to validator exception"}



import requests
import json
import time

try:
    from pinecone import Pinecone
except ImportError:
    print("Please install pinecone: pip install pinecone")
    exit(1)

PINECONE_API_KEY = "pcsk_6KZmMj_DEaYE3Kef64KRPETaE31npL2bdnA6Ncn6RyBxvi1FFqw31cxRhqTgFYNXjHHP29"
PINECONE_INDEX_NAME = "ai-agent-backend-indexes"
EMBEDDING_URL = "https://api.stirringminds.com/embedding"
CHAT_URL = "https://api.stirringminds.com/chat"
NAMESPACE_KB = "admin_v5"
NAMESPACE_SCHEMA = "admin_schema_v2"

def get_embedding(text, retries=3):
    payload = {"input": text}
    headers = {"Content-Type": "application/json"}
    for attempt in range(retries):
        try:
            response = requests.post(EMBEDDING_URL, json=payload, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if "vectors" in data:
                    return data["vectors"][0]
        except Exception as e:
            time.sleep(1)
    raise Exception("Embedding request failed")

def get_context(query_text):
    print("Fetching context from Pinecone...")
    query_vector = get_embedding(query_text)
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(PINECONE_INDEX_NAME)
    
    # 1. Fetch Business Logic (admin_v4)
    kb_results = index.query(
        namespace=NAMESPACE_KB,
        vector=query_vector,
        top_k=3,
        include_metadata=True
    )
    
    # 2. Fetch Schema Constraints (admin_schema_v2)
    schema_results = index.query(
        namespace=NAMESPACE_SCHEMA,
        vector=query_vector,
        top_k=2,
        include_metadata=True
    )
    
    context_str = "--- BUSINESS LOGIC & RULES ---\n"
    print("\n[INFO] Retrieved Business Knowledge Metadata:")
    for match in kb_results['matches']:
        parent = match['metadata'].get('parent_content', '')
        print(f"  -> Collection: {match['metadata'].get('collection')} | Score: {match['score']:.4f}")
        if parent:
            context_str += parent + "\n\n"
            
    context_str += "--- DATABASE SCHEMA & EXAMPLES ---\n"
    print("\n[INFO] Retrieved Database Schema Metadata:")
    for match in schema_results['matches']:
        text = match['metadata'].get('text', '')
        print(f"  -> Collection: {match['metadata'].get('collection')} | Score: {match['score']:.4f}")
        if text:
            context_str += text + "\n\n"
            
    # Output the raw context that is passing into the prompt for debugging
    print("\n--- EXACT CONTEXT FED TO LLM ---")
    print(context_str[:500] + "...\n[Context truncated for console output]\n")
    print("--------------------------------")
            
    return context_str

def generate_pymongo_query(user_question):
    print(f"\n==================================================")
    print(f"QUESTION: {user_question}")
    print(f"==================================================\n")
    
    context2 = get_context(user_question)
    context = """
{'collection': 'spaces', 'description': 'Auto-generated schema for spaces', 'fields': {}, 'indexes': [['_id']], 'relationships': []}
{'collection': 'seatbookings', 'description': 'Auto-generated schema for seatbookings', 'fields': {'_id': {'type': 'ObjectId'}, 'space': {'type': 'ObjectId'}, 'user': {'type': 'ObjectId'}, 'startTime': {'type': 'datetime'}, 'endTime': {'type': 'datetime'}, 'seatIds': {'type': 'list', 'items': {'type': 'ObjectId'}}, 'totalAmount': {'type': 'int'}, 'status': {'type': 'str'}, 'paymentId': {'type': 'str'}, '__v': {'type': 'int'}, 'createdAt': {'type': 'datetime'}, 'updatedAt': {'type': 'datetime'}}, 'indexes': [['_id'], ['seatIds'], ['space', 'startTime', 'endTime', 'status']], 'relationships': ['seatbookings.space -> spaces._id', 'seatbookings.user -> users._id']}
{'collection': 'partnerinvoices', 'description': 'Auto-generated schema for partnerinvoices', 'fields': {}, 'indexes': [['_id'], ['invoiceId'], ['partnerId', 'createdAt']], 'relationships': []}
{'collection': 'spaces', 'description': 'Auto-generated schema for spaces', 'fields': {}, 'indexes': [['_id']], 'relationships': []}
{'collection': 'meetings', 'description': 'Auto-generated schema for meetings', 'fields': {}, 'indexes': [['_id'], ['expiresAt'], ['status'], ['startTime'], ['bookingUserEmail']], 'relationships': []}
{'collection': 'spacedetails', 'description': 'Auto-generated schema for spacedetails', 'fields': {}, 'indexes': [['_id']], 'relationships': []}
{'collection': 'contactforms', 'description': 'Auto-generated schema for contactforms', 'fields': {}, 'indexes': [['_id'], ['serviceInterest'], ['createdAt'], ['isDeleted', 'isActive'], ['email']], 'relationships': []}
{'collection': 'users', 'description': 'Auto-generated schema for users', 'fields': {'_id': {'type': 'ObjectId'}, 'email': {'type': 'str'}, 'fullName': {'type': 'str'}, 'password': {'type': 'str'}, 'authProvider': {'type': 'str'}, 'role': {'type': 'str'}, 'isEmailVerified': {'type': 'bool'}, 'kycVerified': {'type': 'bool'}, 'emailVerificationOTPAttempts': {'type': 'int'}, 'otpRequestCount': {'type': 'int'}, 'isActive': {'type': 'bool'}, 'credits': {'type': 'int'}, 'isDeleted': {'type': 'bool'}, 'refreshTokens': {'type': 'list', 'items': 'unknown'}, 'isTwoFactorEnabled': {'type': 'bool'}, '__v': {'type': 'int'}, 'createdAt': {'type': 'datetime'}, 'updatedAt': {'type': 'datetime'}}, 'indexes': [['_id'], ['lastLogin'], ['authProvider'], ['role'], ['isDeleted', 'isActive'], ['googleId'], ['email']], 'relationships': []}
{'collection': 'partnerinquiries', 'description': 'Auto-generated schema for partnerinquiries', 'fields': {'_id': {'type': 'ObjectId'}, 'name': {'type': 'str'}, 'email': {'type': 'str'}, 'phone': {'type': 'str'}, 'company': {'type': 'str'}, 'partnershipType': {'type': 'str'}, 'message': {'type': 'str'}, 'status': {'type': 'str'}, 'isDeleted': {'type': 'bool'}, 'createdAt': {'type': 'datetime'}, 'updatedAt': {'type': 'datetime'}, '__v': {'type': 'int'}}, 'indexes': [['_id'], ['createdAt'], ['partnershipType'], ['email']], 'relationships': []}
{'collection': 'mails', 'description': 'Auto-generated schema for mails', 'fields': {}, 'indexes': [['_id'], ['mailId']], 'relationships': []}
{'collection': 'supporttickets', 'description': 'Auto-generated schema for supporttickets', 'fields': {}, 'indexes': [['_id'], ['ticketNumber']], 'relationships': []}
{'collection': 'notifications', 'description': 'Auto-generated schema for notifications', 'fields': {}, 'indexes': [['_id'], ['recipient']], 'relationships': []}
{'collection': 'businessinfos', 'description': 'Auto-generated schema for businessinfos', 'fields': {}, 'indexes': [['_id']], 'relationships': []}
{'collection': 'eventspaces', 'description': 'Auto-generated schema for eventspaces', 'fields': {}, 'indexes': [['_id'], ['city'], ['area'], ['location'], ['popular'], ['pricePerHour'], ['type'], ['city', 'area']], 'relationships': []}
{'collection': 'coupons', 'description': 'Auto-generated schema for coupons', 'fields': {}, 'indexes': [['_id'], ['code'], ['status'], ['assignedClientId']], 'relationships': []}
{'collection': 'affiliatebookings', 'description': 'Auto-generated schema for affiliatebookings', 'fields': {}, 'indexes': [['_id'], ['status'], ['affiliateId']], 'relationships': []}
{'collection': 'affiliate_leads', 'description': 'Auto-generated schema for affiliate_leads', 'fields': {}, 'indexes': [['_id'], ['affiliateId']], 'relationships': []}
{'collection': 'virtualoffices', 'description': 'Auto-generated schema for virtualoffices', 'fields': {'_id': {'type': 'ObjectId'}, 'property': {'type': 'ObjectId'}, 'approvalStatus': {'type': 'str'}, 'partnerGstPricePerYear': {'type': 'int'}, 'adminMarkupGstPerYear': {'type': 'int'}, 'finalGstPricePerYear': {'type': 'int'}, 'partnerMailingPricePerYear': {'type': 'int'}, 'adminMarkupMailingPerYear': {'type': 'int'}, 'finalMailingPricePerYear': {'type': 'int'}, 'partnerBrPricePerYear': {'type': 'int'}, 'adminMarkupBrPerYear': {'type': 'int'}, 'finalBrPricePerYear': {'type': 'int'}, 'avgRating': {'type': 'int'}, 'totalReviews': {'type': 'int'}, 'amenities': {'type': 'list', 'items': 'unknown'}, 'popular': {'type': 'bool'}, 'sponsored': {'type': 'bool'}, 'isDeleted': {'type': 'bool'}, 'isActive': {'type': 'bool'}, 'partner': {'type': 'ObjectId'}, '__v': {'type': 'int'}, 'createdAt': {'type': 'datetime'}, 'updatedAt': {'type': 'datetime'}, 'name': {'type': 'str'}, 'address': {'type': 'str'}, 'city': {'type': 'str'}, 'area': {'type': 'str'}, 'gstPlanPricePerYear': {'type': 'int'}, 'mailingPlanPricePerYear': {'type': 'int'}, 'brPlanPricePerYear': {'type': 'int'}, 'features': {'type': 'list', 'items': {'type': 'str'}}, 'availability': {'type': 'str'}, 'location': {'type': {'type': 'str'}, 'coordinates': {'type': 'list', 'items': {'type': 'float'}}}, 'images': {'type': 'list', 'items': {'type': 'str'}}}, 'indexes': [['_id'], ['location'], ['popular', 'avgRating'], ['isDeleted', 'isActive'], ['city', 'area']], 'relationships': []}
{'collection': 'bookings', 'description': 'Auto-generated schema for bookings', 'fields': {'_id': {'type': 'ObjectId'}, 'bookingNumber': {'type': 'str'}, 'user': {'type': 'ObjectId'}, 'partner': {'type': 'ObjectId'}, 'type': {'type': 'str'}, 'spaceId': {'type': 'ObjectId'}, 'spaceSnapshot': {'name': {'type': 'str'}}, 'plan': {'name': {'type': 'str'}, 'price': {'type': 'int'}, 'discount': {'type': 'int'}, 'tenure': {'type': 'int'}, 'tenureUnit': {'type': 'str'}, '_id': {'type': 'ObjectId'}}, 'status': {'type': 'str'}, 'kycStatus': {'type': 'str'}, 'startDate': {'type': 'datetime'}, 'endDate': {'type': 'datetime'}, 'autoRenew': {'type': 'bool'}, 'features': {'type': 'list', 'items': 'unknown'}, 'isDeleted': {'type': 'bool'}, 'timeline': {'type': 'list', 'items': 'unknown'}, 'documents': {'type': 'list', 'items': 'unknown'}, 'createdAt': {'type': 'datetime'}, 'updatedAt': {'type': 'datetime'}, '__v': {'type': 'int'}}, 'indexes': [['_id'], ['bookingNumber']], 'relationships': ['bookings.user -> users._id', 'bookings.spaceId -> spaces._id']}
{'collection': 'affiliate_quotations', 'description': 'Auto-generated schema for affiliate_quotations', 'fields': {}, 'indexes': [['_id'], ['quotationId'], ['createdAt'], ['status'], ['affiliateId']], 'relationships': []}
{'collection': 'visits', 'description': 'Auto-generated schema for visits', 'fields': {}, 'indexes': [['_id']], 'relationships': []}
{'collection': 'partnerpayments', 'description': 'Auto-generated schema for partnerpayments', 'fields': {}, 'indexes': [['_id'], ['paymentId'], ['partnerId', 'createdAt']], 'relationships': []}
{'collection': 'coworkingspaces', 'description': 'Auto-generated schema for coworkingspaces', 'fields': {'_id': {'type': 'ObjectId'}, 'property': {'type': 'ObjectId'}, 'capacity': {'type': 'int'}, 'sponsored': {'type': 'bool'}, 'popular': {'type': 'bool'}, 'approvalStatus': {'type': 'str'}, 'partnerPricePerMonth': {'type': 'int'}, 'adminMarkupPerMonth': {'type': 'int'}, 'finalPricePerMonth': {'type': 'int'}, 'floors': {'type': 'list', 'items': {'floorNumber': {'type': 'int'}, 'name': {'type': 'str'}, 'tables': {'type': 'list', 'items': {'tableNumber': {'type': 'str'}, 'seats': {'type': 'list', 'items': {'seatNumber': {'type': 'str'}, 'isActive': {'type': 'bool'}, '_id': {'type': 'ObjectId'}}}, '_id': {'type': 'ObjectId'}}}, '_id': {'type': 'ObjectId'}}}, 'operatingHours': {'openTime': {'type': 'str'}, 'closeTime': {'type': 'str'}, 'daysOpen': {'type': 'list', 'items': {'type': 'str'}}}, 'avgRating': {'type': 'int'}, 'totalReviews': {'type': 'int'}, 'amenities': {'type': 'list', 'items': {'type': 'str'}}, 'isActive': {'type': 'bool'}, 'isDeleted': {'type': 'bool'}, 'partner': {'type': 'ObjectId'}, '__v': {'type': 'int'}, 'createdAt': {'type': 'datetime'}, 'updatedAt': {'type': 'datetime'}, 'name': {'type': 'str'}, 'address': {'type': 'str'}, 'city': {'type': 'str'}, 'area': {'type': 'str'}, 'location': {'type': {'type': 'str'}, 'coordinates': {'type': 'list', 'items': {'type': 'float'}}}, 'inventory': {'type': 'list', 'items': {'type': {'type': 'str'}, 'totalUnits': {'type': 'int'}, 'pricePerMonth': {'type': 'int'}, 'pricePerYear': {'type': 'int'}}}, 'images': {'type': 'list', 'items': {'type': 'str'}}}, 'indexes': [['_id'], ['avgRating'], ['popular'], ['location'], ['city', 'area'], ['city'], ['area'], ['inventory.type']], 'relationships': []}
{'collection': 'reviews', 'description': 'Auto-generated schema for reviews', 'fields': {'_id': {'type': 'ObjectId'}, 'user': {'type': 'ObjectId'}, 'space': {'type': 'ObjectId'}, 'spaceModel': {'type': 'str'}, 'rating': {'type': 'int'}, 'comment': {'type': 'str'}, 'reviewImages': {'type': 'list', 'items': 'unknown'}, '__v': {'type': 'int'}, 'createdAt': {'type': 'datetime'}, 'updatedAt': {'type': 'datetime'}}, 'indexes': [['_id'], ['user', 'space'], ['space', 'createdAt']], 'relationships': ['reviews.user -> users._id', 'reviews.space -> spaces._id']}
{'collection': 'partnerkycs', 'description': 'Auto-generated schema for partnerkycs', 'fields': {}, 'indexes': [['_id']], 'relationships': []}
{'collection': 'tickets', 'description': 'Auto-generated schema for tickets', 'fields': {}, 'indexes': [['_id'], ['ticketNumber'], ['bookingId'], ['expiresAt'], ['updatedAt'], ['assignee'], ['category'], ['status', 'priority'], ['user', 'createdAt']], 'relationships': []}
{'collection': 'invoices', 'description': 'Auto-generated schema for invoices', 'fields': {'_id': {'type': 'ObjectId'}, 'invoiceNumber': {'type': 'str'}, 'user': {'type': 'ObjectId'}, 'partner': {'type': 'ObjectId'}, 'description': {'type': 'str'}, 'subtotal': {'type': 'int'}, 'taxRate': {'type': 'int'}, 'taxAmount': {'type': 'int'}, 'total': {'type': 'int'}, 'status': {'type': 'str'}, 'isDeleted': {'type': 'bool'}, 'lineItems': {'type': 'list', 'items': 'unknown'}, 'createdAt': {'type': 'datetime'}, 'updatedAt': {'type': 'datetime'}, '__v': {'type': 'int'}}, 'indexes': [['_id'], ['invoiceNumber']], 'relationships': ['invoices.user -> users._id']}
{'collection': 'spacemedias', 'description': 'Auto-generated schema for spacemedias', 'fields': {}, 'indexes': [['_id']], 'relationships': []}
{'collection': 'affiliate_support_tickets', 'description': 'Auto-generated schema for affiliate_support_tickets', 'fields': {}, 'indexes': [['_id'], ['ticketId'], ['status'], ['affiliateId']], 'relationships': []}
{'collection': 'kycdocuments', 'description': 'Auto-generated schema for kycdocuments', 'fields': {}, 'indexes': [['_id']], 'relationships': []}
{'collection': 'credit_ledger', 'description': 'Auto-generated schema for credit_ledger', 'fields': {'_id': {'type': 'ObjectId'}, 'user': {'type': 'ObjectId'}, 'amount': {'type': 'int'}, 'type': {'type': 'str'}, 'description': {'type': 'str'}, 'balanceAfter': {'type': 'int'}, 'remainingAmount': {'type': 'int'}, 'isExpired': {'type': 'bool'}, '__v': {'type': 'int'}, 'createdAt': {'type': 'datetime'}, 'updatedAt': {'type': 'datetime'}}, 'indexes': [['_id'], ['isExpired', 'remainingAmount', 'expiryDate'], ['user', 'createdAt']], 'relationships': ['credit_ledger.user -> users._id']}
{'collection': 'affiliatepayouts', 'description': 'Auto-generated schema for affiliatepayouts', 'fields': {}, 'indexes': [['_id'], ['status'], ['affiliateId']], 'relationships': []}
{'collection': 'feedbacks', 'description': 'Auto-generated schema for feedbacks', 'fields': {}, 'indexes': [['_id']], 'relationships': []}
{'collection': 'properties', 'description': 'Auto-generated schema for properties', 'fields': {'_id': {'type': 'ObjectId'}, 'name': {'type': 'str'}, 'address': {'type': 'str'}, 'city': {'type': 'str'}, 'area': {'type': 'str'}, 'features': {'type': 'list', 'items': 'unknown'}, 'location': {'type': {'type': 'str'}, 'coordinates': {'type': 'list', 'items': {'type': 'float'}}}, 'images': {'type': 'list', 'items': {'type': 'str'}}, 'kycStatus': {'type': 'str'}, 'status': {'type': 'str'}, 'isActive': {'type': 'bool'}, 'isDeleted': {'type': 'bool'}, 'partner': {'type': 'ObjectId'}, '__v': {'type': 'int'}, 'createdAt': {'type': 'datetime'}, 'updatedAt': {'type': 'datetime'}}, 'indexes': [['_id'], ['isActive', 'isDeleted'], ['location'], ['city', 'area']], 'relationships': []}
{'collection': 'space_user_kyc', 'description': 'Auto-generated schema for space_user_kyc', 'fields': {}, 'indexes': [['_id']], 'relationships': []}
{'collection': 'meetingrooms', 'description': 'Auto-generated schema for meetingrooms', 'fields': {'_id': {'type': 'ObjectId'}, 'property': {'type': 'ObjectId'}, 'approvalStatus': {'type': 'str'}, 'partnerPricePerHour': {'type': 'int'}, 'adminMarkupPerHour': {'type': 'int'}, 'finalPricePerHour': {'type': 'int'}, 'partnerPricePerDay': {'type': 'int'}, 'adminMarkupPerDay': {'type': 'int'}, 'finalPricePerDay': {'type': 'int'}, 'operatingHours': {'openTime': {'type': 'str'}, 'closeTime': {'type': 'str'}, 'daysOpen': {'type': 'list', 'items': {'type': 'str'}}}, 'minBookingHours': {'type': 'int'}, 'capacity': {'type': 'int'}, 'type': {'type': 'str'}, 'avgRating': {'type': 'int'}, 'totalReviews': {'type': 'int'}, 'sponsored': {'type': 'bool'}, 'popular': {'type': 'bool'}, 'amenities': {'type': 'list', 'items': {'type': 'str'}}, 'isActive': {'type': 'bool'}, 'isDeleted': {'type': 'bool'}, 'partner': {'type': 'ObjectId'}, '__v': {'type': 'int'}, 'createdAt': {'type': 'datetime'}, 'updatedAt': {'type': 'datetime'}, 'name': {'type': 'str'}, 'address': {'type': 'str'}, 'city': {'type': 'str'}, 'area': {'type': 'str'}, 'pricePerHour': {'type': 'int'}, 'pricePerDay': {'type': 'int'}, 'location': {'type': {'type': 'str'}, 'coordinates': {'type': 'list', 'items': {'type': 'float'}}}, 'images': {'type': 'list', 'items': {'type': 'str'}}}, 'indexes': [['_id'], ['popular'], ['avgRating'], ['type'], ['location'], ['city', 'area'], ['city'], ['area']], 'relationships': []}
{'collection': 'payments', 'description': 'Auto-generated schema for payments', 'fields': {'_id': {'type': 'ObjectId'}, 'user': {'type': 'ObjectId'}, 'userEmail': {'type': 'str'}, 'userName': {'type': 'str'}, 'razorpayOrderId': {'type': 'str'}, 'razorpayPaymentId': {'type': 'str'}, 'razorpaySignature': {'type': 'str'}, 'amount': {'type': 'int'}, 'currency': {'type': 'str'}, 'status': {'type': 'str'}, 'paymentType': {'type': 'str'}, 'spaceModel': {'type': 'str'}, 'space': {'type': 'ObjectId'}, 'spaceName': {'type': 'str'}, 'planName': {'type': 'str'}, 'planKey': {'type': 'str'}, 'tenure': {'type': 'int'}, 'yearlyPrice': {'type': 'int'}, 'totalAmount': {'type': 'int'}, 'discountPercent': {'type': 'int'}, 'discountAmount': {'type': 'int'}, 'creditsUsed': {'type': 'int'}, 'isDeleted': {'type': 'bool'}, '__v': {'type': 'int'}, 'createdAt': {'type': 'datetime'}, 'updatedAt': {'type': 'datetime'}}, 'indexes': [['_id'], ['razorpayOrderId'], ['createdAt'], ['status'], ['userId'], ['razorpayPaymentId']], 'relationships': ['payments.user -> users._id', 'payments.space -> spaces._id']}

"""
    
    system_prompt = f"""You are an expert MongoDB administrator. Your job is to convert the admin's natural language question into an exact, executable PyMongo query.
    
Based on the provided Context (Business Rules and Database Schema), generate ONLY the Python code containing the PyMongo query.
Do NOT use `db.collection_name.find()`. Use the PyMongo format: `db['collection_name'].find({{}})`
Assume the database object is stored in a variable named `db`.
If the user asks a general database question like "list all collections", return `db.list_collection_names()`.
If the user asks "what are the fields", return the code to fetch a single document and get its keys: `list(db['collection_name'].find_one().keys())`.
CRITICAL: When searching for names or emails, ALWAYS use case-insensitive regular expressions. For example: `{{"$regex": "search_term", "$options": "i"}}`.
Do not assign the result to a variable.

CRTICAL: WHENNEVER revenue is involved with name first find its ID -> check invoice related to that ID -> then sum totalAmount from payments collection. Do NOT directly match on user name in payments collection.

CRITICAL: NEVER nest "$lookup" inside "$match". "$lookup" must be a separate, top-level stage in the aggregation pipeline. If you need to filter by a joined field, use "$lookup" first, then "$match".
Rule : for id releated keys, use ObjectId("id_value") format. Do NOT use $toObjectId in $match stage.
CRITICAL: Do NOT use the ID provided in the context (e.g. admin id) as the target ID for the query unless the user specifically asks about "me" or "my". If the user asks about a named entity (e.g. "Erick Carter"), you MUST resolve that name to an ID using a lookup or regex on the appropriate collection (e.g. users).
CRITICAL: The output must be a SINGLE Python expression. Do NOT write multiple lines of code or use intermediate variables. If you need to join data, use `db['collection'].aggregate([...])`.
OUTPUT EXACTLY THE PYTHON CODE, AND NOTHING ELSE. Do not use markdown backticks (```python).
"""

    question_payload = f"""
{system_prompt}

Schema context:
{context2}

Schema :
{context}

User Request:
{user_question}

Generate MongoDB Python query only.
"""

    payload = {
        "question": question_payload
    }
    
    headers = {"Content-Type": "application/json"}
    
    print("Generating PyMongo Query via LLM...")
    response = requests.post(CHAT_URL, json=payload, headers=headers, timeout=60)
    
    if response.status_code == 200:
        data = response.json()
        query_code = None
        
        # Pull answer directly based on proxy structure
        query_code = data.get("answer", "").strip()
            
        if query_code:
            # Clean up potential markdown formatting from LLM
            if "```python" in query_code:
                query_code = query_code.split("```python")[1].split("```")[0].strip()
            elif "```" in query_code:
                query_code = query_code.split("```")[1].strip()
            
            # Remove variable assignment if present (e.g. "result = ...")
            query_code = re.sub(r"^\s*[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*", "", query_code)
                
            print("\n--- GENERATED PYMONGO CODE ---")
            print(query_code)
            print("------------------------------\n")
            return context, query_code
            
    print("Failed to generate query:", response.text)
    return None



import re
import json
from bson import ObjectId
from pymongo.cursor import Cursor




BLOCKED_KEYWORDS = [
    "delete",
    "drop",
    "remove",
    "update",
    "insert",
    "replace",
    "create",
    "mapreduce",
    "command",
]

ALLOWED_COMMANDS = [
    "find(",
    "find_one(",
    "count_documents(",
    "aggregate(",
    "distinct(",
    "list_collection_names("
]


def normalize_query(query: str):
    query = query.replace(": false", ": False")
    query = query.replace(": true", ": True")
    query = query.replace(": null", ": None")

        # convert $oid to ObjectId
    query = re.sub(
        r'\{\s*"\$oid"\s*:\s*"([a-fA-F0-9]{24})"\s*\}',
        r'ObjectId("\1")',
        query
    )

    return query


def is_safe_query(query: str) -> bool:
    q = query.lower()

    # block dangerous keywords
    for word in BLOCKED_KEYWORDS:
        if re.search(rf"\b{word}\b", q):
            return False

    # allow only read commands
    for cmd in ALLOWED_COMMANDS:
        if cmd in q:
            return True

    return False


def serialize_mongo(obj):
    """Convert Mongo/BSON types to JSON-safe values."""
    if isinstance(obj, ObjectId):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def execute_safe_query(query: str):

    query = normalize_query(query)

    if not is_safe_query(query):
        raise PermissionError("Unsafe query detected. Only read operations are allowed.")

    db = get_mongo_db()

    # restricted eval environment
    safe_globals = {
        "__builtins__": {},
        "db": db,
        "ObjectId": ObjectId,
        "list": list,
        "dict": dict,
        "len": len,
        "str": str,
        "int": int,
        "float": float
    }


    result = eval(query, safe_globals)

    # Convert Mongo Cursor → list
    if isinstance(result, Cursor):
        result = list(result)

    # Normalize BSON → JSON safe
    try:
        result = json.loads(json.dumps(result, default=serialize_mongo))
    except Exception:
        pass

    return result
