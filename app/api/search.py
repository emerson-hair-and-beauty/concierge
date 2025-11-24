from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["search"])

# Define request schema
class SearchRequest(BaseModel):
    query: str
    top_k: int = 5



@router.post("/products")
async def search_products_endpoint(request: SearchRequest):
    try:
        from app.agents.recommendation.lib.knowledge_base.query_products import query_products
    except Exception as e:
        return {"error": "search backend not available", "detail": str(e)}

    results = query_products(request.query, top_k=request.top_k)
    return {"results": results}
