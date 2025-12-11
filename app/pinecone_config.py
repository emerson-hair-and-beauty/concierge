# config.py
import os
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

load_dotenv() 

# -----------------------------
# Environment variables
# -----------------------------
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = os.getenv("PINECONE_INDEX", "concierge-knowledge-base")
DIMENSION = 384  # must match your embedding model (all-MiniLM-L6-v2)

# -----------------------------
# Initialize Pinecone client
# -----------------------------
pc = Pinecone(api_key=PINECONE_API_KEY)

# -----------------------------
# Check if index exists
# -----------------------------
existing_indexes = [idx.name for idx in pc.list_indexes()]

if INDEX_NAME in existing_indexes:
    # Fetch index info to check dimension
    info = pc.describe_index(INDEX_NAME)
    current_dim = info.dimension
    if current_dim != DIMENSION:
        print(f"⚠️  Index '{INDEX_NAME}' exists with dimension {current_dim}, but embeddings are {DIMENSION}-d.")
        print("Deleting and recreating index...")
        pc.delete_index(INDEX_NAME)
        pc.create_index(
            name=INDEX_NAME,
            dimension=DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )
        print(f"✅ Index '{INDEX_NAME}' recreated with dimension {DIMENSION}.")
else:
    # Create new index
    pc.create_index(
        name=INDEX_NAME,
        dimension=DIMENSION,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1")
    )
    print(f"✅ Index '{INDEX_NAME}' created with dimension {DIMENSION}.")

# -----------------------------
# Get index handle
# -----------------------------
index = pc.Index(INDEX_NAME)

