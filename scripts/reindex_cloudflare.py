import os
import json
import logging
import sys
import time

# Ensure app module can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(override=True)

from pinecone import Pinecone, ServerlessSpec
from app.vectorstore import get_embeddings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def enhance_guest_text(metadata, original_text):
    address = metadata.get("address", "")
    city = metadata.get("city", "")
    state = metadata.get("state", "")
    
    if not city or not state:
        parts = [p.strip() for p in address.split(',')]
        if len(parts) >= 3:
            if not city: city = parts[-3]
            if not state: 
                state_zip = parts[-2]
                state = ''.join([c for c in state_zip if not c.isdigit()]).strip()

    amenities = metadata.get("amenities", [])
    if isinstance(amenities, list):
        amenities_str = ", ".join(amenities)
    else:
        amenities_str = str(amenities)

    enhanced_text = f"WORKSPACE LOCATION INFO:\n"
    if city: enhanced_text += f"- City: {city}\n"
    if state: enhanced_text += f"- State: {state}\n"
    if address: enhanced_text += f"- Full Address: {address}\n"
    if amenities_str: enhanced_text += f"- Amenities Available: {amenities_str}\n"
    
    enhanced_text += f"\nDescription: {original_text}"
    return enhanced_text

def run_migration():
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        logger.error("PINECONE_API_KEY is missing")
        return

    new_index_name = "ai-agent-backend-cf-indexes"
    pc = Pinecone(api_key=api_key)
    
    existing_indexes = [index_info["name"] for index_info in pc.list_indexes()]
    if new_index_name not in existing_indexes:
        logger.info(f"Index {new_index_name} does not exist. Attempting to create it...")
        try:
            pc.create_index(
                name=new_index_name,
                dimension=768, 
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
            # Wait for index to be ready
            while not pc.describe_index(new_index_name).status['ready']:
                time.sleep(1)
        except Exception as e:
            logger.error(f"Could not create index automatically via API. Error: {e}")
            logger.error("PLEASE CREATE THE INDEX MANUALLY IN YOUR PINECONE DASHBOARD:")
            logger.error(f"  Name: {new_index_name}")
            logger.error("  Dimensions: 768")
            logger.error("  Metric: cosine")
            logger.error("Then re-run this script.")
            return

    logger.info(f"Index {new_index_name} is ready. Appending strictly guest data.")

    index = pc.Index(new_index_name)
    embedder = get_embeddings()

    backup_path = "pinecone_backup.json"
    if not os.path.exists(backup_path):
        logger.error(f"Backup file {backup_path} not found.")
        return

    with open(backup_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    guest_namespaces = ["public", "public_v1", "guest", "guest_amenity"]
    
    for namespace in guest_namespaces:
        items = data.get(namespace, [])
        if not items:
            continue
            
        logger.info(f"Processing GUEST namespace: {namespace} ({len(items)} items)")
        
        batch_size = 5
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            
            ids = []
            texts = []
            metadatas = []
            
            for item in batch:
                # Ensure unique IDs across namespaces to prevent overwrites
                item_id = f"{namespace}:{item.get('id')}"
                metadata = item.get("metadata", {})
                raw_text = metadata.get("text") or metadata.get("content") or metadata.get("chunk") or ""
                enhanced_text = enhance_guest_text(metadata, raw_text)
                
                if enhanced_text and item.get("id"):
                    ids.append(item_id)
                    texts.append(enhanced_text)
                    metadata["text"] = enhanced_text
                    metadatas.append(metadata)
            
            if texts:
                logger.info(f"  Embedding batch of {len(texts)} spaces...")
                vectors = embedder.embed_documents(texts)
                upsert_data = [(v_id, v_vec, v_meta) for v_id, v_vec, v_meta in zip(ids, vectors, metadatas)]
                logger.info("  Upserting vectors securely to Pinecone...")
                index.upsert(vectors=upsert_data, namespace="public")
            
    logger.info("Guest workspace migration completed successfully!")

if __name__ == "__main__":
    run_migration()
