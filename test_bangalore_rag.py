import os
from pinecone import Pinecone
from dotenv import load_dotenv
import sys

# Add current dir to path
sys.path.append(os.getcwd())

from app.vectorstore import get_embeddings

load_dotenv(override=True)

pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
index = pc.Index('ai-agent-backend-cf-indexes')
embedder = get_embeddings()

query = 'in bangalore'
print(f"Embedding query: '{query}'")
vec = embedder.embed_query(query)

results = index.query(vector=vec, namespace='public', top_k=10, include_metadata=True)

print(f'\nResults for "{query}":')
if not results['matches']:
    print("NO MATCHES FOUND IN 'public' namespace.")
for res in results['matches']:
    print(f"Score: {res['score']:.4f}, City: {res['metadata'].get('city')}, ID: {res['id']}")
