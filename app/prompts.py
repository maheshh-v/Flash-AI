from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import os
import logging

logger = logging.getLogger(__name__)

def load_prompt(file_path: str) -> str:

    encodings = ("utf-8", "utf-8-sig", "cp1252", "latin-1")
    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                return f.read().strip()
        except UnicodeDecodeError:
            continue
        except Exception:
            logger.exception(f"Failed loading prompt: {file_path}")
            raise RuntimeError(f"Prompt unavailable: {os.path.basename(file_path)}")

    logger.exception(f"Failed loading prompt: {file_path}")
    raise RuntimeError(f"Prompt unavailable: {os.path.basename(file_path)}")



BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


system_prompt = load_prompt(os.path.join(BASE_DIR, "prompts", "system.txt"))
user_prompt = load_prompt(os.path.join(BASE_DIR, "prompts", "user.txt"))
PARTNER_SYSTEM_PROMPT =  load_prompt(os.path.join(BASE_DIR, "prompts", "partner_system_prompt.txt"))
PARTNER_MONGO_PROMPT = load_prompt(os.path.join(BASE_DIR, "prompts", "partner_mongo_query_prompt.txt"))
PARTNER_QUERY_NORMALIZER_PROMPT = load_prompt(os.path.join(BASE_DIR, "prompts", "partner_query_normalizer_prompt.txt"))
PARTNER_QUERY_MONGO_GUARD_PROMPT = load_prompt(os.path.join(BASE_DIR, "prompts", "partner_query_mongo_guard_prompt.txt"))
ADMIN_SYSTEM_PROMPT = load_prompt(os.path.join(BASE_DIR, "prompts", "admin_system_prompt.txt"))
ADMIN_MONGO_PROMPT = load_prompt(os.path.join(BASE_DIR, "prompts", "admin_mongo_query_prompt.txt"))


chat_prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    MessagesPlaceholder("history"),
    ("human", user_prompt)
])



partner_chat_prompt = ChatPromptTemplate.from_messages([
    ("system", PARTNER_SYSTEM_PROMPT),
    MessagesPlaceholder("history"),
    ("human", user_prompt)
])

admin_chat_prompt = ChatPromptTemplate.from_messages([
    ("system", ADMIN_SYSTEM_PROMPT),
    MessagesPlaceholder("history"),
    ("human", user_prompt)
])



# # Backwards-compatible: if a prompt file still references {profile},
# # provide an empty default so the API doesn't fail.
# try:
#     if "profile" in set(getattr(chat_prompt, "input_variables", []) or []):
#         chat_prompt = chat_prompt.partial(profile="")
# except Exception:
#     logger.exception("Failed applying prompt partial defaults")

# try:
#     logger.info("Prompt variables: %s", getattr(chat_prompt, "input_variables", None))
# except Exception:
#     pass
