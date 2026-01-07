# config.py
import os
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

# -----------------------------
# Environment variables
# -----------------------------
# -----------------------------
# Lazy Index Fetcher
# -----------------------------
_index = None

def get_pinecone_index():
    global _index
    if _index is not None:
        return _index

    PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
    INDEX_NAME = os.getenv("PINECONE_INDEX", "concierge-knowledge-base")
    DIMENSION = 384

    pc = Pinecone(api_key=PINECONE_API_KEY)
    
    # Check if index exists - this is slow, so we only do it once
    existing_indexes = [idx.name for idx in pc.list_indexes()]

    if INDEX_NAME in existing_indexes:
        info = pc.describe_index(INDEX_NAME)
        if info.dimension != DIMENSION:
            pc.delete_index(INDEX_NAME)
            pc.create_index(
                name=INDEX_NAME,
                dimension=DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1")
            )
    else:
        pc.create_index(
            name=INDEX_NAME,
            dimension=DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )
    
    _index = pc.Index(INDEX_NAME)
    return _index

