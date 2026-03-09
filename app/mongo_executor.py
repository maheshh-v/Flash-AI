from __future__ import annotations

import json
import os
import re
import logging
from functools import lru_cache
from typing import Any

from bson import ObjectId, json_util
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database
from datetime import datetime



BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))
logger = logging.getLogger(__name__)


ALLOWED_COLLECTIONS = {
    "invoices",
    "users",
    "reviews",
    "properties",
    "spaces",
    "bookings",
    "payments",
    "coworkingspaces",
    "meetingrooms",
    "virtualoffices",
    "seatbookings",
}



ALLOWED_COLLECTIONS_ADMIN = {
    "invoices",
    "users",
    "reviews",
    "properties",
    "spaces",
    "bookings",
    "payments",
    "coworkingspaces",
    "meetingrooms",
    "virtualoffices",
    "seatbookings",
}

DEFAULT_LIMIT = int(os.getenv("MONGO_QUERY_DEFAULT_LIMIT", "50"))
MAX_LIMIT = int(os.getenv("MONGO_QUERY_MAX_LIMIT", "200"))


class MongoQueryError(ValueError):
    pass


@lru_cache(maxsize=1)
def get_mongo_db() -> Database:
    uri = (os.getenv("MONGODB_URI") or "").strip()
    if not uri:
        raise MongoQueryError("Missing MONGODB_URI")

    db_name = ("test")
    if not db_name:
        raise MongoQueryError("Missing MONGODB_DB_NAME")

    client = MongoClient(uri, serverSelectionTimeoutMS=8000)
    return client[db_name]


# def convert_objectid(data: Any) -> Any:
#     if isinstance(data, dict):
#         if set(data.keys()) == {"$oid"}:
#             return ObjectId(str(data["$oid"]))
#         return {k: convert_objectid(v) for k, v in data.items()}
#     if isinstance(data, list):
#         return [convert_objectid(item) for item in data]
#     return data


def _try_parse_iso_date(value: Any) -> Any:
    if isinstance(value, str):
        try:
            # Handles ISO format like 2026-02-01T00:00:00Z
            if "T" in value:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            pass
    return value

def convert_objectid(data: Any) -> Any:
    if isinstance(data, dict):
        # Handle ObjectId
        if set(data.keys()) == {"$oid"}:
            return ObjectId(str(data["$oid"]))

        # Handle explicit $date
        if set(data.keys()) == {"$date"}:
            return datetime.fromisoformat(
                data["$date"].replace("Z", "+00:00")
            )

        return {k: convert_objectid(_try_parse_iso_date(v)) for k, v in data.items()}

    if isinstance(data, list):
        return [convert_objectid(item) for item in data]

    return _try_parse_iso_date(data)


# def convert_objectid(data: Any) -> Any:
#     if isinstance(data, dict):
#         # Handle ObjectId
#         if set(data.keys()) == {"$oid"}:
#             return ObjectId(str(data["$oid"]))

#         # Handle Date
#         if set(data.keys()) == {"$date"}:
#             return datetime.fromisoformat(
#                 data["$date"].replace("Z", "+00:00")
#             )

#         return {k: convert_objectid(v) for k, v in data.items()}

#     if isinstance(data, list):
#         return [convert_objectid(item) for item in data]

    return data


def _allowed_collections_for_role(role: str | None) -> set[str]:
    if (role or "").lower() == "admin":
        return ALLOWED_COLLECTIONS_ADMIN
    return ALLOWED_COLLECTIONS


def validate_lookup(payload: Any, allowed_collections: set[str]) -> None:
    if isinstance(payload, dict):
        if "$lookup" in payload:
            lookup = payload.get("$lookup") or {}
            lookup_from = lookup.get("from")
            if lookup_from not in allowed_collections:
                raise MongoQueryError(f"Unauthorized lookup collection: {lookup_from}")

        for value in payload.values():
            validate_lookup(value, allowed_collections)
        return

    if isinstance(payload, list):
        for item in payload:
            validate_lookup(item, allowed_collections)


def _normalize_limit(value: Any) -> int:
    try:
        limit = int(value)
    except Exception:
        limit = DEFAULT_LIMIT
    if limit < 1:
        limit = 1
    return min(limit, MAX_LIMIT)


def _json_safe(value: Any) -> Any:
    return json.loads(json_util.dumps(value))


def _sanitize_llm_query_text(query_text: str) -> str:
    """Normalize LLM output into strict JSON text expected by this executor."""
    text = (query_text or "").strip()

    # Remove markdown code fences if present.
    if "```" in text:
        text = re.sub(r"^\s*```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)

    # Drop JS-style line comments that can leak from LLM output.
    text = re.sub(r"(?m)^\s*//.*$", "", text)

    # Trim to outermost JSON object if extra text leaked in.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    # Accept ObjectId("...") and convert to extended JSON for downstream conversion.
    text = re.sub(
        r'ObjectId\(\s*"([a-fA-F0-9]{24})"\s*\)',
        r'{"$oid":"\1"}',
        text,
    )
    text = re.sub(
        r"ObjectId\(\s*'([a-fA-F0-9]{24})'\s*\)",
        r'{"$oid":"\1"}',
        text,
    )

    # Accept ISODate("...") / new Date("...") and convert to extended JSON date.
    text = re.sub(
        r'ISODate\(\s*"([^"]+)"\s*\)',
        r'{"$date":"\1"}',
        text,
    )
    text = re.sub(
        r"ISODate\(\s*'([^']+)'\s*\)",
        r'{"$date":"\1"}',
        text,
    )
    text = re.sub(
        r'new\s+Date\(\s*"([^"]+)"\s*\)',
        r'{"$date":"\1"}',
        text,
    )
    text = re.sub(
        r"new\s+Date\(\s*'([^']+)'\s*\)",
        r'{"$date":"\1"}',
        text,
    )

    # Normalize numeric Mongo wrappers to plain JSON numbers.
    text = re.sub(r"NumberInt\(\s*\"?(-?\d+)\"?\s*\)", r"\1", text)
    text = re.sub(r"NumberLong\(\s*\"?(-?\d+)\"?\s*\)", r"\1", text)
    text = re.sub(r'Decimal128\(\s*"(-?\d+(?:\.\d+)?)"\s*\)', r"\1", text)
    text = re.sub(r"Decimal128\(\s*'(-?\d+(?:\.\d+)?)'\s*\)", r"\1", text)

    # Convert common single-quoted JSON drift into valid double-quoted JSON.
    text = re.sub(r"([{\[,]\s*)'([^']+)'\s*:", r'\1"\2":', text)
    text = re.sub(r":\s*'([^']*)'(\s*[,}\]])", r': "\1"\2', text)

    # Remove trailing commas before object/array close to tolerate common LLM JSON mistakes.
    # Example: {"a": 1,} or [1,2,]
    while True:
        cleaned = re.sub(r",\s*([}\]])", r"\1", text)
        if cleaned == text:
            break
        text = cleaned

    return text.strip()


def _canonical_field_name(field: str, root_collection: str | None) -> str:
    """Fix common LLM-invented key names to schema-valid keys."""
    if not isinstance(field, str) or field.startswith("$"):
        return field

    key_lower = field.strip().lower()
    root = (root_collection or "").strip().lower()

    if key_lower in {"partnerid", "parterid"}:
        if root == "users":
            return "_id"
        return "partner"

    return field.strip()


def _canonical_field_path_value(
    value: Any,
    parent_key: str | None = None,
    root_collection: str | None = None,
) -> Any:
    """Fix common LLM path mistakes for user/customer name fields in expressions."""
    if not isinstance(value, str):
        return value

    v = value.strip()
    if not v.startswith("$"):
        return value

    path = v[1:]
    lower = path.lower()
    key_lower = (parent_key or "").strip().lower()
    root = (root_collection or "").strip().lower()

    if lower == "name":
        # In user/customer name projections, bare "$name" should map to "$fullName".
        if key_lower in {"customer_name", "customername", "user_name", "username", "partner_name"}:
            return "$fullName"
        if root == "users":
            return "$fullName"

    # Normalize snake_case variant first.
    if lower.endswith(".full_name"):
        return f"${path[:-10]}.fullName"

    # Common joined aliases where users.fullName is expected.
    if lower.endswith(".name"):
        prefixes = (
            "customerdetails.",
            "customerdetails.",
            "customer_info.",
            "customerinfo.",
            "userdetails.",
            "user_info.",
            "userinfo.",
            "customer.",
            "user.",
        )
        if lower.startswith(prefixes):
            return f"${path[:-5]}.fullName"

    return value


def _rewrite_query_fields(payload: Any, root_collection: str | None) -> Any:
    """Recursively rewrite invalid field aliases inside query payload."""
    if isinstance(payload, dict):
        rewritten: dict[str, Any] = {}
        for key, value in payload.items():
            fixed_key = _canonical_field_name(key, root_collection)
            rewritten[fixed_key] = _rewrite_query_fields(value, root_collection)
            if not isinstance(rewritten[fixed_key], (dict, list)):
                rewritten[fixed_key] = _canonical_field_path_value(
                    rewritten[fixed_key],
                    parent_key=fixed_key,
                    root_collection=root_collection,
                )
        return rewritten
    if isinstance(payload, list):
        return [_rewrite_query_fields(item, root_collection) for item in payload]
    return _canonical_field_path_value(payload, root_collection=root_collection)




def run_mongo_query_from_string(
    query_str: str | dict[str, Any],
    role: str | None = None
) -> list[dict[str, Any]]:
    """Execute a vetted Mongo query from JSON text or dict."""

    if isinstance(query_str, str):
        try:
            sanitized = _sanitize_llm_query_text(query_str)
            query = json.loads(sanitized)
        except Exception as exc:
            logger.exception("Failed to parse Mongo JSON after sanitize: %s", sanitized[:1200] if 'sanitized' in locals() else "")
            raise MongoQueryError("Invalid JSON format") from exc
    elif isinstance(query_str, dict):
        query = query_str
    else:
        raise MongoQueryError("Query must be a JSON string or dict")

    if not isinstance(query, dict):
        raise MongoQueryError("Query root must be an object")

    role_norm = (role or "").lower()
    allowed_collections = _allowed_collections_for_role(role)
    db = get_mongo_db()

    # Admin-only pseudo operation: count available collections.
    operation = str(query.get("operation") or "").strip().lower()
    if operation == "count_collections":
        if role_norm != "admin":
            raise MongoQueryError("Operation 'count_collections' is admin-only")
        collection_names = sorted(
            name for name in db.list_collection_names() if name in allowed_collections
        )
        return [{"totalCollections": len(collection_names), "collections": collection_names}]

    collection_name = str(query.get("collection") or "").strip()
    if not collection_name:
        raise MongoQueryError("Missing collection name")

    # Admin LLM fallback shape: {"collection":"collections","pipeline":[...{"$count":...}]}
    if role_norm == "admin" and collection_name == "collections":
        pipeline = query.get("pipeline")
        if isinstance(pipeline, list) and any(isinstance(s, dict) and "$count" in s for s in pipeline):
            collection_names = sorted(
                name for name in db.list_collection_names() if name in allowed_collections
            )
            return [{"totalCollections": len(collection_names), "collections": collection_names}]

    if collection_name not in allowed_collections:
        raise MongoQueryError(f"Collection '{collection_name}' not allowed")

    query = _rewrite_query_fields(query, collection_name)
    collection = db[collection_name]
    query = convert_objectid(query)

        # Handle count operation
    operation = query.get("operation")

    # Case 1: operation = "count"
    is_count_op = operation == "count"

    # Case 2: count key present (LLM style)
    is_count_key = "count" in query

    if is_count_op or is_count_key:
        filter_ = query.get("filter", {})
        if not isinstance(filter_, dict):
            raise MongoQueryError("'filter' must be an object for count")

        count = collection.count_documents(filter_)
        return [{"count": count}]


    if "pipeline" in query:
        pipeline = query.get("pipeline")
        if not isinstance(pipeline, list):
            raise MongoQueryError("'pipeline' must be a list")
        validate_lookup(pipeline, allowed_collections)
        return _json_safe(list(collection.aggregate(pipeline)))

    if "filter" in query:
        filter_ = query.get("filter")
        projection = query.get("projection")
        if filter_ is None:
            filter_ = {}
        if not isinstance(filter_, dict):
            raise MongoQueryError("'filter' must be an object")
        if projection is not None and not isinstance(projection, dict):
            raise MongoQueryError("'projection' must be an object when provided")
        limit = _normalize_limit(query.get("limit", DEFAULT_LIMIT))
        return _json_safe(list(collection.find(filter_, projection).limit(limit)))

    raise MongoQueryError("Unsupported query format; expected 'pipeline' or 'filter'")
