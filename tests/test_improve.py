import os
from dotenv import load_dotenv
load_dotenv()
from app.mongo_query_service import query_improve, generate_mongo_query
from app.mongo_executor import _sanitize_llm_query_text

# fake context and query
schema_context = "{'collection': 'bookings', 'fields': {'_id': 'ObjectId', 'partner': 'ObjectId', 'user': 'ObjectId', 'status': 'str'}, 'relationships': []}"
query = "show my bookings"

print("1. GENERATING...")
code = generate_mongo_query(query, schema_context)
print("CODE:\n", code)

print("2. IMPROVING...")
improved = query_improve(schema_context, code)
print("IMPROVED:\n", improved)

print("3. SANITIZING...")
san = _sanitize_llm_query_text(improved)
print("SANITIZED:\n", san)

import json
try:
    j = json.loads(san)
    print("PARSED JSON SUCCESSFULLY:")
    print(j)
except Exception as e:
    print("FAILED TO PARSE JSON:", e)

