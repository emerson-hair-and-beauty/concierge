from fastapi import APIRouter, HTTPException, status
from typing import List, Dict, Optional
from datetime import datetime, timezone

from app.api.models import (
    Recommendation, RecommendationsResponse, RecommendationDecisionRequest,
    PushSubscriptionRequest
)
from app.services.db_service import get_db
from app.services.recommendations.recommendation_agent import generate_recommendations
from app.services.recommendations.push_service import store_subscription

router = APIRouter(tags=["recommendations"])


@router.get("/recommendations/{user_id}", status_code=status.HTTP_200_OK)
async def get_recommendations(user_id: str) -> RecommendationsResponse:
    """
    Fetch recommendations for a user.
    If no recommendations exist for today, generate new ones via LLM.
    Returns pending recommendations only (already accepted/dismissed ones are excluded).
    """
    db = get_db()

    try:
        # Check if recommendations already exist for today
        pending_recs = db.get_pending_recommendations(user_id)

        if not pending_recs:
            # Generate new recommendations
            # Fetch user context
            user_metadata = db.get_user_metadata(user_id)
            user_routine = db.get_active_routine(user_id)
            user_alerts = db.get_pending_alerts(user_id, limit=3)
            user_vitals = db.get_vitals_summary(user_id) if hasattr(db, 'get_vitals_summary') else {}

            # Call recommendation agent
            recommendations = await generate_recommendations(
                user_id=user_id,
                user_metadata=user_metadata or {},
                routine=user_routine or {},
                alerts=user_alerts,
                vitals=user_vitals
            )

            # Save recommendations to DB
            for rec in recommendations:
                db.save_recommendation(user_id, rec)

            pending_recs = recommendations

        # Convert to response format
        rec_dicts = [
            {
                "id": rec.get("id"),
                "user_id": user_id,
                "title": rec.get("title"),
                "message": rec.get("message"),
                "reasoning": rec.get("reasoning"),
                "routine_step_ref": rec.get("routine_step_ref"),
                "recommendation_type": rec.get("recommendation_type"),
                "status": "pending",
                "created_at": rec.get("created_at"),
                "decided_at": None
            }
            for rec in pending_recs
        ]

        return RecommendationsResponse(
            status="success",
            recommendations=rec_dicts,
            message=f"Found {len(pending_recs)} recommendations for you today"
        )

    except Exception as e:
        print(f"[RECOMMENDATIONS] Error fetching recommendations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch recommendations"
        )


@router.patch("/recommendations/{recommendation_id}", status_code=status.HTTP_200_OK)
async def update_recommendation(recommendation_id: str, request: RecommendationDecisionRequest):
    """
    Update a recommendation status (accept or dismiss).
    """
    db = get_db()

    try:
        success = db.update_recommendation_status(recommendation_id, request.status)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recommendation not found"
            )

        return {
            "status": "success",
            "message": f"Recommendation marked as {request.status}"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[RECOMMENDATIONS] Error updating recommendation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update recommendation"
        )


@router.post("/push/subscribe", status_code=status.HTTP_200_OK)
async def subscribe_to_push(request: PushSubscriptionRequest):
    """
    Subscribe a user to push notifications.
    Stores their push subscription details for later use.
    """
    try:
        success = await store_subscription(request.user_id, request.endpoint, request.p256dh, request.auth)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to subscribe to push notifications"
            )

        return {
            "status": "success",
            "message": "Successfully subscribed to push notifications"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[PUSH] Error subscribing: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to subscribe to push notifications"
        )


@router.delete("/push/subscribe", status_code=status.HTTP_200_OK)
async def unsubscribe_from_push(user_id: str):
    """
    Unsubscribe a user from push notifications.
    Removes their subscription from the database.
    """
    db = get_db()

    try:
        success = db.delete_push_subscription(user_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found"
            )

        return {
            "status": "success",
            "message": "Successfully unsubscribed from push notifications"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[PUSH] Error unsubscribing: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unsubscribe from push notifications"
        )
