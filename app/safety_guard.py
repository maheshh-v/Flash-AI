import logging
import os
import re
from typing import Any
import hashlib

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from app.cache_service import CacheUnavailableError, get_cache_service
from app.llm import get_llm

logger = logging.getLogger(__name__)


class SafetyDecision(BaseModel):
    allowed: bool
    category: str
    reason: str = ""


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _escape_template_braces_keep_query(text: str) -> str:
    """Escape literal braces for ChatPromptTemplate while preserving {query}."""
    raw = text or ""
    escaped = raw.replace("{", "{{").replace("}", "}}")
    return escaped.replace("{{query}}", "{query}")


def _load_prompt_text(filename: str, fallback: str) -> str:
    path = os.path.join(BASE_DIR, "prompts", filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read().strip()
            if text:
                return text
    except Exception:
        logger.exception("Failed loading safety prompt file: %s", path)
    return fallback


_PARTNER_SAFETY_PROMPT_TEXT = _load_prompt_text(
    "partner_safety_prompt.txt",
    """
You are a strict safety intent classifier for partner chat input.
Classify into: safe, abuse, threat, links, db_operation, sql_injection, prompt_injection, malware, data_exfiltration, other_harm.
Output JSON with allowed/category/reason only.
User query:
{query}
""".strip(),
)

_ADMIN_SAFETY_PROMPT_TEXT = _load_prompt_text(
    "admin_safety_prompt.txt",
    """
You are a strict safety intent classifier for admin chat input.
Classify into: safe, abuse, threat, links, db_operation, sql_injection, prompt_injection, malware, data_exfiltration, other_harm.
Admins can ask advanced analytics; block only harmful/unsafe intent.
Output JSON with allowed/category/reason only.
User query:
{query}
""".strip(),
)


_PARTNER_SAFETY_PROMPT = ChatPromptTemplate.from_template(
    _escape_template_braces_keep_query(_PARTNER_SAFETY_PROMPT_TEXT)
)
_ADMIN_SAFETY_PROMPT = ChatPromptTemplate.from_template(
    _escape_template_braces_keep_query(_ADMIN_SAFETY_PROMPT_TEXT)
)


try:
    llm = get_llm()
    _safety_chains = {
        "partner": _PARTNER_SAFETY_PROMPT | llm.with_structured_output(
            SafetyDecision,
            method="json_mode",
        ),
        "admin": _ADMIN_SAFETY_PROMPT | llm.with_structured_output(
            SafetyDecision,
            method="json_mode",
        ),
    }
except Exception:
    logger.exception("Failed to initialize LLM safety chains")
    _safety_chains = {}


_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "links": [
        re.compile(r"https?://", re.IGNORECASE),
        re.compile(r"\bwww\.", re.IGNORECASE),
        re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", re.IGNORECASE),
    ],
    "sql_injection": [
        re.compile(r"(?i)\b(select|insert|update|delete|drop|truncate|alter|create)\b.+\b(from|into|table)\b"),
        re.compile(r"(?i)\bselect\s*\*"),
        re.compile(r"(?i)\bwhere\b.+(=|like|in)\b"),
        re.compile(r"(?i)\b(order\s+by|group\s+by|having|limit)\b"),
        re.compile(r"(?i)(--|/\*|\*/|#)\s*$"),
        re.compile(r"(?i)\b(xp_cmdshell|sleep\s*\(|benchmark\s*\()"),
        re.compile(r"(?i)\bunion\s+select\b"),
        re.compile(r"(?i)\bor\s+1\s*=\s*1\b"),
        re.compile(r"(?i)'\s*(or|and)\s*'?\d+'?\s*=\s*'?\d+'?\s*(--|#|/\*)?"),
        re.compile(r"(?i)'\s*and\s+1\s*=\s*1\s*(--|#|/\*)?"),
        re.compile(r"(?i)\bdrop\s+table\b"),
        re.compile(r"(?i)\binformation_schema\b"),
        re.compile(r"(?i)\bselect\s+\*\s+from\s+\w+\s+where\s+.+\b(username|email)\b\s*=\s*['\"<].+['\">]\s+and\s+\bpassword\b\s*=\s*['\"<].+['\">]"),
        re.compile(r"(?i)\bselect\b.+\bfrom\b.+\bwhere\b.+\b(username|email)\b.+\band\b.+\bpassword\b"),
        re.compile(r"(?i)\$\bwhere\b"),
        re.compile(r"(?i)\$ne\b.*\bnull\b"),
    ],
    "prompt_injection": [
        re.compile(r"(?i)\b(ignore|bypass|override)\b.{0,40}\b(instructions|system)\b"),
        re.compile(r"(?i)\breveal\b.{0,40}\b(system prompt|hidden prompt)\b"),
    ],
    "other_harm": [
        re.compile(r"(?im)^\s*import\s+[a-zA-Z0-9_\.]+"),
        re.compile(r"(?im)^\s*from\s+[a-zA-Z0-9_\.]+\s+import\s+[a-zA-Z0-9_*,\s]+"),
        re.compile(r"(?i)\b(function|def|class)\s+[a-zA-Z_][a-zA-Z0-9_]*\s*[\(\{]"),
        re.compile(r"(?i)\b(console\.log|print\s*\(|return\s+|if\s*\(|for\s*\(|while\s*\()"),
        re.compile(r"(?i)\b(curl|wget|powershell|bash|sh)\b"),
        re.compile(r"(?i)<script\b"),
        re.compile(r"(?i)</script>"),
        re.compile(r"(?i)<\?php"),
        re.compile(r"(?i)\bjavascript:"),
        re.compile(r"(?i)`[^`]+`"),
        re.compile(r"(?i)\beval\s*\("),
        re.compile(r"(?i)\bexec\s*\("),
        re.compile(r"(?i)__import__\s*\("),
        re.compile(r"(?i)\bos\.environ\b"),
        re.compile(r"(?i)\bsubprocess\.(popen|run|call)\s*\("),
        re.compile(r"(?i)\bos\.(system|popen)\s*\("),
    ],
    "threat": [
        re.compile(r"(?i)\b(kill|murder|bomb|attack|shoot)\b"),
        re.compile(r"(?i)\b(i will|i'm going to)\b.{0,20}\b(hurt|harm|kill)\b"),
    ],
    "abuse": [
        re.compile(r"(?i)\b(fuck|bitch|bastard|idiot|stupid)\b"),
    ],
    "malware": [
        re.compile(r"(?i)\b(keylogger|ransomware|malware|virus|trojan)\b"),
        re.compile(r"(?i)\b(exploit|payload|reverse shell)\b"),
        re.compile(r"(?i)\b(cmd\.exe|powershell\s+-enc|mshta|regsvr32|rundll32)\b"),
        re.compile(r"(?i)\b(base64\s+-d|certutil|nc\s+-e|netcat\s+-e)\b"),
    ],
    "data_exfiltration": [
        re.compile(r"(?i)\b(leak|dump)\b.{0,30}\b(database|credentials|passwords?)\b"),
        re.compile(r"(?i)\b(steal|exfiltrate)\b"),
    ],
}


_PARTNER_DB_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\bselect\s+.+\s+from\b"),
    re.compile(r"(?i)\b(insert|update|delete|drop|truncate|alter|create)\b"),
    re.compile(r"(?i)\bdb\.[a-zA-Z0-9_]+\.(find|insert|update|delete|remove|aggregate)\b"),
]


_ADMIN_BLOCKED_DB_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\b(insert|update|delete|drop|truncate|alter|create|remove)\b"),
    re.compile(r"(?i)\bdb\.[a-zA-Z0-9_]+\.(insert|update|delete|remove|drop)\b"),
]


_ALLOWLIST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\b(show|tell|give|view|get)\b.{0,40}\bmy\b.{0,40}\b(details?|profile|informations?|information|bookings?|customers?|revenue|invoices?|payments?)\b"),
    re.compile(r"(?i)\bmy\b.{0,50}\b(details?|profile|informations?|information|bookings?|customers?|revenue|invoices?|payments?)\b"),
    re.compile(r"(?i)\b(show|tell|give|view|get|list)\b.{0,50}\bcustomer(s)?\b.{0,25}\b(name|names)\b.{0,40}\b(under me|my|my bookings|my spaces)\b"),
    re.compile(r"(?i)\bcustomer(s)?\b.{0,25}\b(name|names)\b.{0,40}\b(under me|my|my bookings|my spaces)\b"),
]

_PARTNER_SELF_IDENTITY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\b(show|tell|give|view|get|what(?:'s| is))\b.{0,40}\bmy\b.{0,20}\bemail\b"),
    re.compile(r"(?i)\bmy\b.{0,20}\bemail\b"),
]

_PUBLIC_WORKSPACE_ALLOWLIST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\b(show|give|list|share|tell)\b.{0,30}\b(complete|full)\b.{0,30}\b(address|addresses|location|locations)\b"),
    re.compile(r"(?i)\b(complete|full)\b.{0,20}\b(address|addresses)\b"),
    re.compile(r"(?i)\b(address|addresses)\b.{0,30}\b(space|spaces|virtual office|coworking|meeting room|location|locations)\b"),
]

_NON_ADMIN_SCOPE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\b(all|entire|whole|complete)\s+(users|partners|customers|bookings|payments|invoices)\b"),
    re.compile(r"(?i)\b(platform[-\s]?wide|across\s+all\s+partners|global\s+data|all\s+tenants)\b"),
    re.compile(r"(?i)\b(admin\s+data|internal\s+admin|all\s+partner\s+data)\b"),
]


def _looks_like_script_payload(text: str) -> bool:
    indicators = [
        r"(?i)```",
        r"(?i)<script\b",
        r"(?i)\b(function|def|class)\b",
        r"(?i)\{.*\}",
        r"(?i)\bSELECT\b.*\bFROM\b",
    ]
    hits = 0
    for pattern in indicators:
        if re.search(pattern, text):
            hits += 1
    return hits >= 2


def _rule_based_detect(query: str, role: str | None = None) -> tuple[bool, str, str]:
    text = (query or "").strip()
    role_norm = (role or "").strip().lower()

    if not text:
        return True, "safe", ""

    for category, patterns in _PATTERNS.items():
        for pattern in patterns:
            if pattern.search(text):
                return False, category, "Matched safety rule"

    if _looks_like_script_payload(text):
        return False, "other_harm", "Blocked script/code-like payload"

    if role_norm in {"partner", "public", "guest", "user"}:
        for pattern in _NON_ADMIN_SCOPE_PATTERNS:
            if pattern.search(text):
                return False, "other_harm", "Blocked out-of-scope role request"

    if role_norm == "admin":
        for pattern in _ADMIN_BLOCKED_DB_PATTERNS:
            if pattern.search(text):
                return False, "db_operation", "Blocked destructive DB intent for admin"
    else:
        for pattern in _PARTNER_DB_PATTERNS:
            if pattern.search(text):
                return False, "db_operation", "Blocked command-style DB operation"

    if role_norm == "partner":
        for pattern in _ALLOWLIST_PATTERNS:
            if pattern.search(text):
                return True, "safe", "Allowlisted self-service query"

    return True, "safe", ""


def predict_query_safety(query: str, role: str | None = None) -> dict[str, Any]:
    """Return {'allowed': bool, 'category': str, 'reason': str}."""
    role_norm = (role or "").strip().lower()
    logger.info("[Safety Guard] Incoming query: %r | Role: %r | Norm Role: %r", query[:50], role, role_norm)
    chain_key = "admin" if role_norm == "admin" else "partner"
    cache_role = role_norm or "guest"
    cache = get_cache_service()

    prompt_text = _ADMIN_SAFETY_PROMPT_TEXT if chain_key == "admin" else _PARTNER_SAFETY_PROMPT_TEXT
    payload = {
        "query": (query or "").strip(),
        "role": cache_role,
        "chain_key": chain_key,
        "prompt_hash": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
        "model": os.getenv("OPENAI_MODEL") or os.getenv("CHAT_MODEL") or "",
    }
    cache_key = cache.make_key(cache_role, "safety", payload)
    ttl = cache.get_ttl("safety")

    def _safe_cache_set(value: dict[str, Any]) -> None:
        try:
            cache.set_json(cache_key, value, ttl, role=cache_role, domain="safety")
        except CacheUnavailableError:
            logger.warning("Admin safety cache write unavailable")

    try:
        cached = cache.get_json(cache_key, role=cache_role, domain="safety")
        if isinstance(cached, dict):
            return {
                "allowed": bool(cached.get("allowed", True)),
                "category": str(cached.get("category", "safe")),
                "reason": str(cached.get("reason", "")),
            }
    except CacheUnavailableError:
        logger.warning("Safety cache unavailable; proceeding with live checks")
        pass # Proceed to live checks

    if role_norm == "partner":
        for pattern in _ALLOWLIST_PATTERNS:
            if pattern.search(query or ""):
                result = {
                    "allowed": True,
                    "category": "safe",
                    "reason": "Allowlisted partner self-service query",
                }
                _safe_cache_set(result)
                return result
        for pattern in _PARTNER_SELF_IDENTITY_PATTERNS:
            if pattern.search(query or ""):
                result = {
                    "allowed": True,
                    "category": "safe",
                    "reason": "Allowlisted partner self-identity query",
                }
                _safe_cache_set(result)
                return result

    if role_norm in {"public", "guest", "user"}:
        for pattern in _PUBLIC_WORKSPACE_ALLOWLIST_PATTERNS:
            if pattern.search(query or ""):
                result = {
                    "allowed": True,
                    "category": "safe",
                    "reason": "Allowlisted public workspace address query",
                }
                _safe_cache_set(result)
                return result

    rule_allowed, rule_category, rule_reason = _rule_based_detect(query, role_norm)
    if not rule_allowed:
        result = {
            "allowed": False,
            "category": rule_category,
            "reason": rule_reason,
        }
        _safe_cache_set(result)
        return result

    chain = _safety_chains.get(chain_key)
    if chain is not None:
        try:
            decision = chain.invoke({"query": query})
            if isinstance(decision, SafetyDecision):
                result = decision.model_dump()
                _safe_cache_set(result)
                return result
            if isinstance(decision, dict):
                result = {
                    "allowed": bool(decision.get("allowed", True)),
                    "category": str(decision.get("category", "safe")),
                    "reason": str(decision.get("reason", "")),
                }
                _safe_cache_set(result)
                return result
        except Exception:
            logger.exception("LLM safety check failed; falling back to rule-based result")

    result = {
        "allowed": True,
        "category": "safe",
        "reason": "",
    }
    _safe_cache_set(result)
    return result
