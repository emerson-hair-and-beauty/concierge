from fastapi import APIRouter
from app.api.models import OrchestratorInput

router = APIRouter(tags=["orchestrator"])

@router.post("/run-orchestrator")
async def run_orchestrator_endpoint(input_data: OrchestratorInput):
    try:
        from app.agents.ochestrator import orchestrator
        result = await orchestrator(input_data)
        return {"result": result}
    except Exception as e:
        return {"error": "orchestrator backend not available", "detail": str(e)}
