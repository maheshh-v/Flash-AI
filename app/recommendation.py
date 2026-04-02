import logging
import re
import json
from typing import Optional, Dict, Any, List
from app.vectorstore import get_pinecone_vectorstore
from app.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

_KNOWN_CITIES = {
    "bangalore", "bengaluru", "mumbai", "delhi", "new delhi", "gurgaon", "gurugram",
    "noida", "pune", "hyderabad", "chennai", "kolkata", "ahmedabad", "jaipur",
    "lucknow", "indore", "bhopal", "surat", "kochi", "coimbatore", "nagpur",
    "visakhapatnam", "vijayawada", "patna", "bhubaneswar", "chandigarh",
}

_KNOWN_REGIONS = {
    "gujarat", "gujrat", "maharashtra", "karnataka", "tamil nadu", "telangana",
    "uttar pradesh", "west bengal", "rajasthan", "madhya pradesh", "haryana",
    "punjab", "odisha", "kerala", "bihar", "jharkhand", "chhattisgarh", "assam",
    "andhra pradesh", "new delhi", "delhi ncr", "ncr",
}


def _has_city_mention(user_input: str) -> bool:
    text = (user_input or "").strip().lower()
    if not text:
        return False

    for city in _KNOWN_CITIES:
        if re.search(rf"\b{re.escape(city)}\b", text):
            return True

    for region in _KNOWN_REGIONS:
        if re.search(rf"\b{re.escape(region)}\b", text):
            return True

# Internal helper for main.py integration
def _extract_city_from_text_logic(text: str) -> str:
    t = (text or "").lower()
    for city in _KNOWN_CITIES:
        if re.search(rf"\b{re.escape(city)}\b", t):
            return city
    return ""


def _has_service_mention(text: str) -> bool:
    input_lower = (text or "").lower()
    service_keywords = [
        "coworking", "virtual office", "virtual offices", "meeting room",
        "meeting rooms", "cabin", "desk", "workspace", "office space",
        "space", "spaces", "office", "offices", "nearest space", "nearby space"
    ]
    return any(keyword in input_lower for keyword in service_keywords)


def is_proximity_query(text: str) -> bool:
    input_lower = (text or "").lower()
    proximity_keywords = [
        "nearest",
        "closest",
        "nearby",
        "near ",
        "near to",
    ]
    return any(keyword in input_lower for keyword in proximity_keywords)


def _extract_reference_location(query: str) -> str:
    text = (query or "").strip()
    if not text:
        return ""

    patterns = [
        r"(?:nearest|closest)\s+(?:to\s+)?([a-zA-Z][a-zA-Z\s,.-]{1,80})\??$",
        r"near(?:by)?\s+(?:to\s+)?([a-zA-Z][a-zA-Z\s,.-]{1,80})\??$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" ?.,")

    return ""


def _extract_location_from_content(content: str) -> str:
    text = (content or "").strip()
    if not text:
        return ""
    match = re.search(r"^\s*Location:\s*(.+)$", text, flags=re.IGNORECASE | re.MULTILINE)
    if match:
        return match.group(1).strip()
    return ""


def _build_space_candidates(docs: list) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for idx, doc in enumerate(docs or []):
        metadata = getattr(doc, "metadata", {}) or {}
        page_content = getattr(doc, "page_content", "") or ""

        address = (metadata.get("address") or "").strip()
        if not address:
            address = _extract_location_from_content(page_content)
        
        # Fallback: Use chunk of text if no explicit address but mentions a known city
        if not address:
            for city in _KNOWN_CITIES:
                if city in page_content.lower():
                    address = f"{city.title()} workspace"
                    break

        if not address:
            continue

        candidates.append(
            {
                "index": idx,
                "address": address,
                "city": (metadata.get("city") or "").strip() or _extract_city_from_text_logic(address),
                "state": (metadata.get("state") or "").strip(),
                "gst_price": metadata.get("gst_price"),
                "br_price": metadata.get("br_price"),
                "mail_price": metadata.get("mail_price"),
                "amenities": metadata.get("amenities"),
            }
        )
    return candidates


def _fallback_best_candidate(reference_location: str, candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not candidates:
        return None
    if not reference_location:
        return candidates[0]

    ref_tokens = {t for t in re.findall(r"[a-z0-9]+", reference_location.lower()) if len(t) > 2}
    if not ref_tokens:
        return candidates[0]

    scored = []
    for candidate in candidates:
        address = (candidate.get("address") or "").lower()
        addr_tokens = {t for t in re.findall(r"[a-z0-9]+", address) if len(t) > 2}
        overlap = len(ref_tokens.intersection(addr_tokens))
        scored.append((overlap, candidate))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored else candidates[0]


def get_nearest_space_hint(user_input: str, docs: list) -> str:
    """
    Build a high-priority hint for nearest-space queries by asking the LLM to
    evaluate all retrieved space candidates against the user-provided location.
    """
    if not is_proximity_query(user_input):
        return ""

    reference_location = _extract_reference_location(user_input)
    candidates = _build_space_candidates(docs)

    if not candidates:
        return ""

    if len(candidates) == 1:
        return (
            "Authoritative nearest result:\n"
            f"Reference location: {reference_location or 'unspecified'}\n"
            f"Nearest space: {candidates[0].get('address', '')}"
        )

    prompt_messages = [
        SystemMessage(
            content=(
                "You are a strict geo-ranking function for Delhi/India localities. "
                "Pick the single nearest candidate address to the reference location. "
                "Use real-world locality knowledge. Return JSON only with keys "
                "best_index (int from provided index) and reason (short)."
            )
        ),
        HumanMessage(
            content=(
                "Reference location:\n"
                f"{reference_location or user_input}\n\n"
                "Candidates:\n"
                f"{json.dumps(candidates, ensure_ascii=True)}\n\n"
                "Return only JSON."
            )
        ),
    ]

    best_candidate: Optional[Dict[str, Any]] = None
    llm_reason = ""

    try:
        llm = get_llm()
        llm_response = llm.invoke(prompt_messages)
        raw = (getattr(llm_response, "content", "") or "").strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            fence_match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
            parsed = json.loads(fence_match.group(0)) if fence_match else {}
        best_index = parsed.get("best_index")
        llm_reason = str(parsed.get("reason", "")).strip()

        if isinstance(best_index, int):
            by_index = {item["index"]: item for item in candidates}
            best_candidate = by_index.get(best_index)
    except Exception:
        logger.exception("Nearest-space LLM ranking failed; using fallback matcher")

    if not best_candidate:
        best_candidate = _fallback_best_candidate(reference_location, candidates)

    if not best_candidate:
        return ""

    reason_text = llm_reason or "Based on locality-level proximity matching."
    return (
        "Authoritative nearest result:\n"
        f"Reference location: {reference_location or 'unspecified'}\n"
        f"Nearest space: {best_candidate.get('address', '')}\n"
        f"Reason: {reason_text}"
    )

def find_my_fit(user_need: str, group_size: str, city_choice: str) -> Optional[Dict[str, Any]]:
    """
    Translates user requirements into a Pinecone query to find the best workspace match.
    
    Args:
        user_need: The category of need (e.g., 'Solo Work', 'Team Meeting').
        group_size: Number of people (e.g., '5 people').
        city_choice: The city namespace in Pinecone.
    """
    # Map the 'Need' to keywords that exist in your vector store context
    need_mapping = {
        "Solo Work": "coworking space, hot desk, private office, quiet focus",
        "Team Meeting": "meeting room, conference room, projector, whiteboard",
        "Business Address": "virtual office, mail handling, business registration"
    }
    
    # Construct a natural language query
    mapped_need = need_mapping.get(user_need, user_need)
    search_query = f"I am looking for {mapped_need} for {group_size}."
    
    try:
        # Use the existing vectorstore abstraction which handles embeddings automatically
        vectorstore = get_pinecone_vectorstore(namespace=city_choice)
        
        # Get the best single match
        results = vectorstore.similarity_search(search_query, k=1)
        
        if results:
            return results[0].metadata
            
    except Exception:
        logger.exception("find_my_fit search failed")
        
    return None

def get_service_recommendation(user_input: str, conversation_hint: str = "") -> str:
    """
    Simple branching logic to recommend service pages based on user intent.
    """
    input_lower = user_input.lower()
    combined_text = f"{user_input}\n{conversation_hint}".strip()
    city_provided = _has_city_mention(combined_text)
    service_provided = _has_service_mention(combined_text)
    find_my_fit_triggers = [
        "help me find my fit",
        "recommend",
        "not sure",
        "suggest",
       
        
    ]
    # If service + location are already known, answer directly from available listings.
    # Do not ask extra preference questions unless user explicitly asks to refine.
    if city_provided and service_provided:
        return (
            "User has already provided enough information (service + location). STOP. "
            "Give the available spaces directly from context. "
            "Do NOT ask for amenities, budget, size, or confirmation unless user explicitly asks for filtering."
        )
    
    # Trigger guided discovery when user asks for recommendation but city is not known yet.
    if "find my fit" in input_lower or any(trigger in input_lower for trigger in find_my_fit_triggers):
        if not city_provided:
            return "Recommendation flow active. STOP. Ask EXACTLY one question next: 'Which city are you looking for?' Do not show locations before city is confirmed."
        return "City is confirmed. Show 3 options max with one-line notes and labels: Most affordable / Balanced / Premium."

    # Guardrail: Generic space intent should ask service type first.
    if len(user_input.split()) <= 6 and any(x in input_lower for x in ["space", "office", "workspace", "desk"]) and not any(x in input_lower for x in ["coworking", "virtual"]):
        return "The user wants a space but has not selected a type yet. STOP. Your NEXT STEP is to ask EXACTLY: 'What type of space are you looking for: Virtual Office or Coworking Space?'"

    # Guardrail: If user provides a clear service type or requirement (like duration), ask city next.
    # This prevents the AI from assuming a city from the retrieved context (Rule 10).
    service_keywords = ["coworking", "virtual", "meeting", "room", "cabin"]
    if any(x in input_lower for x in service_keywords) or any(x in input_lower for x in ["month", "day", "hour", "week"]):
        if city_provided:
            return ""
        return "User has provided service details or requirements. STOP. Do NOT assume a city from context. If the user has not specified a city yet, your NEXT STEP is to ask: 'Which city are you looking for?'"

    # Guardrail: If user provides a budget (number), force the AI to ask for city without assumptions.
    # We check for digits, currency keywords, or phrases like "anything will do".
    if user_input.replace(',', '').replace('.', '').strip().isdigit() or any(x in input_lower for x in ["rs", "rupees", "budget", "will do", "no restriction"]):
        if city_provided and service_provided:
            return "Budget provided. Recommend ONLY spaces within the stated budget and do not show options above budget."
        if city_provided:
            return "User already provided city. STOP. Your NEXT STEP is to ask EXACTLY: 'What type of space are you looking for: Virtual Office or Coworking Space?'"
        return "User has provided the Budget. STOP. Do NOT assume any city from previous context. Your NEXT STEP is to ask EXACTLY: 'Which city are you looking for?'"

    return ""


def _extract_budget_from_text(text: str) -> Optional[int]:
    content = (text or "").lower()
    if not content:
        return None
    match = re.search(r"(?:₹|rs\.?|inr|rupees?)\s*([0-9][0-9,]*)", content, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except Exception:
        return None


def _pick_registration_price(candidate: Dict[str, Any]) -> Optional[int]:
    for key in ("gst_price", "br_price", "mail_price"):
        value = candidate.get(key)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            digits = re.sub(r"[^0-9]", "", value)
            if digits:
                return int(digits)
    return None


def _extract_short_area(address: str) -> str:
    if not address:
        return ""
    parts = [p.strip() for p in address.split(",") if p.strip()]
    return parts[0] if parts else address


def build_contextual_recommendation_reply(
    query: str,
    docs: list,
    conversation_hint: str = "",
    remembered_city: str = "",
) -> str:
    """
    Deterministic recommendation formatter for follow-up intent like:
    "I want to register my company. What should I choose?"
    Uses existing retrieved docs + conversation context (city/budget).
    """
    q = (query or "").lower()
    followup_intent = any(
        phrase in q
        for phrase in (
            "what should i choose",
            "what shall i choose",
            "what should i go with",
            "what shall i go with",
            "which should i choose",
            "which one is best",
            "recommend",
            "best option",
        )
    )
    registration_intent = any(
        phrase in q
        for phrase in (
            "register my company",
            "company registration",
            "register company",
            "gst registration",
            "business registration",
        )
    )
    if not (followup_intent and registration_intent):
        return ""

    candidates = _build_space_candidates(docs)
    if not candidates:
        return ""

    city_hint = (remembered_city or "").strip().lower()
    if city_hint:
        city_filtered = [
            c for c in candidates
            if city_hint in ((c.get("city") or "").lower()) or city_hint in ((c.get("address") or "").lower())
        ]
        if city_filtered:
            candidates = city_filtered

    priced: List[Dict[str, Any]] = []
    for c in candidates:
        price = _pick_registration_price(c)
        if price is None:
            continue
        c_copy = dict(c)
        c_copy["picked_price"] = price
        priced.append(c_copy)

    if not priced:
        return ""

    budget = _extract_budget_from_text(f"{query}\n{conversation_hint}")
    if budget is not None:
        within_budget = [p for p in priced if int(p["picked_price"]) <= budget]
        if within_budget:
            priced = within_budget

    priced.sort(key=lambda x: int(x["picked_price"]))
    top = priced[:3]
    if not top:
        return ""

    lines: List[str] = []
    city_label = (remembered_city or "").strip().title()
    if city_label:
        lines.append(f"For company registration in {city_label}, these virtual office options fit best:")
    else:
        lines.append("For company registration, these virtual office options fit best:")
    lines.append("")

    tags = ["Most affordable", "Balanced option", "Premium option"]
    reasons = [
        "Best for startup budget and GST registration",
        "Good balance of price and location credibility",
        "Higher cost option for premium location preference",
    ]
    for idx, item in enumerate(top):
        area = _extract_short_area(item.get("address", ""))
        price = int(item["picked_price"])
        tag = tags[idx] if idx < len(tags) else "Option"
        reason = reasons[idx] if idx < len(reasons) else "Suitable based on available pricing."
        lines.append(f"{area} - Rs {price:,} ({tag})")
        lines.append(reason)

    if budget is not None:
        lines.append("")
        lines.append(f"Budget insight: filtered to options within Rs {budget:,}.")

    lines.append("Which one interests you?")
    return "\n".join(lines)


def is_company_registration_recommendation_query(query: str) -> bool:
    q = (query or "").lower()
    followup_intent = any(
        phrase in q
        for phrase in (
            "what should i choose",
            "what shall i choose",
            "what should i go with",
            "what shall i go with",
            "which should i choose",
            "which one is best",
            "recommend",
            "best option",
        )
    )
    registration_intent = any(
        phrase in q
        for phrase in (
            "register my company",
            "company registration",
            "register company",
            "gst registration",
            "business registration",
        )
    )
    return followup_intent and registration_intent
