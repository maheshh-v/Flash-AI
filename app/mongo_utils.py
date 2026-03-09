

def extract_collections(mongo_query):
    collections = set()

    # Main collection
    if "collection" in mongo_query:
        collections.add(mongo_query["collection"])

    # Aggregate pipeline
    for stage in mongo_query.get("aggregate", []):
        if "$lookup" in stage:
            collections.add(stage["$lookup"]["from"])

    return collections