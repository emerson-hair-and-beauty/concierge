from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

# Define request schema
class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


# Define endpoint. Import the heavy search/backend logic lazily so the
# app can start even if the optional embedding packages are not installed.
@router.post("/search")
async def search_products_endpoint(request: SearchRequest):
    try:
        # Import here to avoid startup-time import errors if optional deps
        # (like sentence_transformers) are missing in the environment.
        from app.agents.recommendation.lib.knowledge_base.query_products import query_products
    except Exception as e:
        # Return a user-friendly error rather than letting the server crash
        return {"error": "search backend not available", "detail": str(e)}

    results = query_products(request.query, top_k=request.top_k)
    return {"results": results}
