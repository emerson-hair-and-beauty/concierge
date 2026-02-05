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

@router.get("/routine/{user_id}")
async def get_routine_endpoint(user_id: str):
    """
    Get the most recent routine for a user.
    """
    try:
        from app.services.db_service import get_db
        db = get_db()
        routine = db.get_active_routine(user_id)
        
        if not routine:
            # Return empty object if no routine found (not 404, to simplify frontend logic)
            return {"routine": None, "message": "No routine found"}
            
        return routine
    except Exception as e:
        return {"error": "Failed to retrieve routine", "detail": str(e)}
