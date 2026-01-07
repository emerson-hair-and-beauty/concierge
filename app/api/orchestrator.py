from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.api.models import OrchestratorInput

router = APIRouter(tags=["orchestrator"])

@router.post("/run-orchestrator")
async def run_orchestrator_endpoint(input_data: OrchestratorInput):
    try:
        from app.agents.orchestrator import orchestrator
        # Return a StreamingResponse to handle the generator from orchestrator
        return StreamingResponse(
            orchestrator(input_data), 
            media_type="text/plain" # Or text/event-stream for more formal SSE
        )
    except Exception as e:
        return {"error": "orchestrator backend failed to start", "detail": str(e)}
