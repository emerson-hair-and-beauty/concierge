from fastapi import APIRouter, HTTPException, status
from app.api.models import WashEventRequest, LocationUpdateRequest
from app.services.db_service import get_db

router = APIRouter(tags=["user_telemetry"])

@router.post("/wash", status_code=status.HTTP_200_OK)
async def log_wash(request: WashEventRequest):
    """
    Log an explicit hair-wash event to the wash_logs table.
    Triggered when a user opens the app on their designated wash day.
    """
    db = get_db()
    success = db.log_wash_event(request.user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to log wash event"
        )
    return {"status": "success", "message": "Wash event logged"}

@router.post("/location", status_code=status.HTTP_200_OK)
async def update_location(request: LocationUpdateRequest):
    """
    Update a user's location based on their current IP or device request.
    This feeds the AI weather defense scenarios.
    """
    db = get_db()
    success = db.update_user_location(request.user_id, request.location)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user location"
        )
    return {"status": "success", "message": "Location updated"}

@router.get("/alerts", status_code=status.HTTP_200_OK)
async def get_alerts(user_id: str):
    """
    Fetch the last 3 unread AI scenario alerts for the user.
    """
    db = get_db()
    alerts = db.get_pending_alerts(user_id, limit=3)
    return {"status": "success", "alerts": alerts}

@router.post("/alerts/{alert_id}/read", status_code=status.HTTP_200_OK)
async def mark_read(alert_id: str):
    """
    Mark an alert as read so it no longer appears in the banner.
    """
    db = get_db()
    success = db.mark_alert_read(alert_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark alert as read"
        )
    return {"status": "success", "message": "Alert marked as read"}
