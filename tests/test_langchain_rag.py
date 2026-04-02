import os
from dotenv import load_dotenv
import sys

# Add current dir to path
sys.path.append(os.getcwd())

from app.vectorstore import get_pinecone_vectorstore

load_dotenv(override=True)

query = 'in jaipur'
print(f"Testing LangChain PineconeVectorStore for query: '{query}'")

try:
    vectorstore = get_pinecone_vectorstore(namespace='public')
    results = vectorstore.similarity_search_with_score(query, k=5)
    
    print(f"\nFound {len(results)} matches via LangChain:")
    for doc, score in results:
        print(f"Score: {score:.4f}, Content snippet: {doc.page_content[:100]}")
        print(f"Metadata keys: {doc.metadata.keys()}")
        print("-" * 20)
except Exception as e:
    print(f"ERROR: {e}")
