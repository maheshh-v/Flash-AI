import os
from datetime import timezone

from pymongo import MongoClient, UpdateOne
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import ChatMessage


def main() -> None:
    database_url = os.getenv("DATABASE_URL", "sqlite:///./chat.db")
    mongo_uri = (os.getenv("MONGODB_URI") or "").strip()
    mongo_db_name = (os.getenv("MONGODB_DB_NAME") or "test").strip() or "test"
    collection_name = (os.getenv("CHAT_MESSAGES_COLLECTION") or "chat_messages").strip() or "chat_messages"

    if not mongo_uri:
        raise RuntimeError("Missing MONGODB_URI")

    engine_kwargs = {}
    if database_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}

    engine = create_engine(database_url, **engine_kwargs)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=8000)
    collection = client[mongo_db_name][collection_name]
    collection.create_index("id", unique=True)
    collection.create_index([("session_id", 1), ("created_at", 1)])

    db = SessionLocal()
    try:
        rows = db.query(ChatMessage).all()
        ops = []
        for row in rows:
            created_at = row.created_at
            if created_at is not None and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            ops.append(
                UpdateOne(
                    {"id": row.id},
                    {
                        "$set": {
                            "id": row.id,
                            "session_id": row.session_id,
                            "conversation_id": row.conversation_id,
                            "actual_role": row.actual_role,
                            "role": row.role,
                            "content": row.content,
                            "created_at": created_at,
                        }
                    },
                    upsert=True,
                )
            )

        if ops:
            result = collection.bulk_write(ops, ordered=False)
            print(
                f"Migration complete. matched={result.matched_count}, "
                f"modified={result.modified_count}, upserted={len(result.upserted_ids)}"
            )
        else:
            print("No chat_messages rows found in SQLite.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
