import os
import uuid
import logging
from typing import Optional, List
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

from pymongo import MongoClient
from pymongo.collection import Collection
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, Session

from app.models import Base, ChatSession

logger = logging.getLogger(__name__)


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./chat.db"
)
MONGODB_URI = (os.getenv("MONGODB_URI") or "").strip()
MONGODB_DB_NAME = (os.getenv("MONGODB_DB_NAME") or "test").strip() or "test"
CHAT_MESSAGES_COLLECTION = (os.getenv("CHAT_MESSAGES_COLLECTION") or "chat_messages").strip() or "chat_messages"

_engine_kwargs = {"pool_pre_ping": True}
if (DATABASE_URL or "").startswith("sqlite"):
    # Required for FastAPI/uvicorn where sync endpoints run in a threadpool.
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **_engine_kwargs)

try:
    url = make_url(DATABASE_URL)
    if url.drivername.startswith("sqlite") and url.database:
        db_path = url.database
        if not os.path.isabs(db_path):
            db_path = os.path.abspath(db_path)
        logger.info("SQLite DB path: %s", db_path)
except Exception:
    logger.exception("Failed to parse DATABASE_URL")

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base.metadata.create_all(bind=engine)


def _get_db() -> Session:
    return SessionLocal()


@dataclass
class ChatMessageRecord:
    id: str
    session_id: str
    conversation_id: Optional[str]
    actual_role: Optional[str]
    role: str
    content: str
    created_at: datetime


@lru_cache(maxsize=1)
def _get_chat_messages_collection() -> Collection:
    if not MONGODB_URI:
        raise RuntimeError("Missing MONGODB_URI for chat_messages migration")

    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=8000)
    collection = client[MONGODB_DB_NAME][CHAT_MESSAGES_COLLECTION]
    try:
        collection.create_index([("session_id", 1), ("created_at", 1)])
    except Exception:
        logger.exception("Failed to create chat_messages index")
    return collection


def _resolve_message_meta(
    session_id: str,
    conversation_id: Optional[str],
    actual_role: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    conv_id = conversation_id
    ar = actual_role

    db: Optional[Session] = None
    try:
        db = _get_db()
        sess = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if sess is not None:
            if not conv_id:
                conv_id = getattr(sess, "conversation_id", None)
            if not ar:
                ar = getattr(sess, "role", None)
    except Exception:
        logger.exception("Failed to lookup conversation metadata for session %s", session_id)
    finally:
        if db:
            db.close()

    if isinstance(ar, str) and ar.lower() in {"guest", "guest_amenity"}:
        ar = "public"

    return conv_id, ar


# --------------------------------------------------
# Create Session Per User
# --------------------------------------------------
def create_session(user_id: str, tenant_id: str, conversation_id: Optional[str] = None, role: Optional[str] = None) -> str:

    db: Optional[Session] = None

    try:
        db = _get_db()

        session = ChatSession(
            user_id=user_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            role=role,
        )

        db.add(session)
        db.commit()
        db.refresh(session)

        return session.id

    except Exception:
        logger.exception("DB create_session failed")
        return str(uuid.uuid4())

    finally:
        if db:
            db.close()


def ensure_session(session_id: str, user_id: str, tenant_id: str, conversation_id: Optional[str] = None, role: Optional[str] = None) -> None:
    """Ensure a chat session row exists for the given session_id.

    This is useful when session IDs are derived deterministically (e.g. from
    tenant/user/conversation_id) and we don't want to create a new UUID session
    on every request.
    """

    if not (session_id or "").strip():
        return

    db: Optional[Session] = None
    try:
        db = _get_db()

        existing = (
            db.query(ChatSession)
            .filter(ChatSession.id == session_id)
            .first()
        )
        if existing is not None:
            # If we have a conversation_id or role now but the existing row doesn't, update it.
            updated = False
            if conversation_id and not getattr(existing, "conversation_id", None):
                existing.conversation_id = conversation_id
                updated = True
            if role and not getattr(existing, "role", None):
                existing.role = role
                updated = True
            if updated:
                db.add(existing)
                db.commit()
            return

        session = ChatSession(
            id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            role=role,
        )
        db.add(session)
        db.commit()

    except Exception:
        logger.exception("DB ensure_session failed")

    finally:
        if db:
            db.close()


# --------------------------------------------------
# Save Chat Message
# --------------------------------------------------
def save_message(session_id: str, role: str, content: str, conversation_id: Optional[str] = None, actual_role: Optional[str] = None):
    conv_id, ar = _resolve_message_meta(session_id, conversation_id, actual_role)
    try:
        collection = _get_chat_messages_collection()
        collection.insert_one(
            {
                "id": str(uuid.uuid4()),
                "session_id": session_id,
                "conversation_id": conv_id,
                "actual_role": ar,
                "role": role,
                "content": content,
                "created_at": datetime.now(timezone.utc),
            }
        )
    except Exception:
        logger.exception("Mongo save_message failed")


# --------------------------------------------------
# Get Session Messages (History)
# --------------------------------------------------
def get_session_messages(session_id: str) -> List[ChatMessageRecord]:
    try:
        collection = _get_chat_messages_collection()
        docs = list(collection.find({"session_id": session_id}).sort("created_at", 1))
        rows: list[ChatMessageRecord] = []
        for d in docs:
            created = d.get("created_at")
            if not isinstance(created, datetime):
                created = datetime.now(timezone.utc)
            rows.append(
                ChatMessageRecord(
                    id=str(d.get("id") or d.get("_id") or ""),
                    session_id=str(d.get("session_id") or ""),
                    conversation_id=d.get("conversation_id"),
                    actual_role=d.get("actual_role"),
                    role=str(d.get("role") or ""),
                    content=str(d.get("content") or ""),
                    created_at=created,
                )
            )
        return rows
    except Exception:
        logger.exception("Mongo get_session_messages failed")
        return []


def clear_session_messages(session_id: str) -> None:
    """Delete all messages for a session."""
    try:
        collection = _get_chat_messages_collection()
        collection.delete_many({"session_id": session_id})
    except Exception:
        logger.exception("Mongo clear_session_messages failed")
