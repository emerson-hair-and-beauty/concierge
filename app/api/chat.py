"""
Chat API Endpoints for Empath Diagnostic Engine
Provides REST routes for diagnostic conversations and event persistence
"""

from fastapi import APIRouter, HTTPException
from app.api.models import (
    ChatRequest, 
    ChatResponse, 
    SaveEventRequest, 
    HairEvent,
    VitalsPayload
)
from app.services.db_service import get_db
from app.services.librarian_service import get_librarian
from app.agents.empath_diagnostic import diagnose_hair_concern

router = APIRouter(tags=["chat"])

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    POST /api/chat
    
    Main diagnostic conversation endpoint. Receives user messages and returns
    AI responses with optional handoff triggers.
    
    Args:
        request: ChatRequest with user_id, message, and session_id
        
    Returns:
        ChatResponse with AI message, handoff flag, and target vital
    """
    try:
        db = get_db()
        
        # 1. Retrieve conversation history (last 10 messages)
        history = db.get_chat_history(request.session_id, limit=10)
        print(f"[DEBUG] Retrieved history: {len(history)} messages")
        
        # 2. Save the user's message to history
        db.append_chat_message(request.session_id, "user", request.message, user_id=request.user_id)
        print(f"[DEBUG] Saved user message: {request.message}")
        
        # 3. Fetch past events from Librarian for context
        librarian = get_librarian()
        past_events = librarian.get_recent_events(request.user_id, limit=5)
        past_context = librarian.format_context_for_prompt(past_events)
        print(f"[DEBUG] Retrieved {len(past_events)} past events for context")
        
        # 4. Run the diagnostic agent with past context
        print(f"[DEBUG] Running diagnostic agent with Librarian context...")
        response_message, handoff, target_vital = await diagnose_hair_concern(
            history=history,
            current_message=request.message,
            past_context=past_context
        )
        print(f"[DEBUG] Agent response: {response_message[:100]}...")
        print(f"[DEBUG] Handoff: {handoff}, Target: {target_vital}")
        
        # 4. If handoff detected, run auto-summarization
        summary = None
        keywords = []
        if handoff:
            from app.agents.summarizer import summarize_diagnostic
            print(f"[DEBUG] Handoff detected. Running summarizer...")
            # Include the current exchange in the summary context
            full_context = history + [
                {"role": "user", "message": request.message},
                {"role": "assistant", "message": response_message}
            ]
            summary, keywords = await summarize_diagnostic(full_context)
            print(f"[DEBUG] Auto-summary: {summary}")
            print(f"[DEBUG] Keywords: {keywords}")
        
        # 5. Save the assistant's response to history
        db.append_chat_message(request.session_id, "assistant", response_message, user_id=request.user_id)
        
        # 6. Return the response
        return ChatResponse(
            message=response_message,
            handoff=handoff,
            target_vital=target_vital,
            session_id=request.session_id,
            summary=summary,
            keywords=keywords
        )
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"[ERROR] Chat endpoint failed: {error_detail}")
        raise HTTPException(
            status_code=500,
            detail=f"Chat processing failed: {str(e)}"
        )


@router.post("/event", response_model=HairEvent)
async def save_event_endpoint(request: SaveEventRequest):
    """
    POST /api/event
    
    Saves a completed diagnostic event after the user provides slider input.
    
    Args:
        request: SaveEventRequest with user_id, session_id, vital value, and summary
        
    Returns:
        The saved HairEvent with generated ID
    """
    try:
        db = get_db()
        librarian = get_librarian()
        
        # Categorize the event using Librarian
        primary_label = librarian.categorize_vital(request.target_vital)
        print(f"[DEBUG] Categorized event as: {primary_label}")
        
        # Build the vitals payload based on which vital was diagnosed
        vitals = VitalsPayload()
        
        # Set the appropriate vital field
        if request.target_vital == "moisture":
            vitals.moisture = request.vital_value
        elif request.target_vital == "definition":
            vitals.definition = request.vital_value
        elif request.target_vital == "scalp":
            vitals.scalp = request.vital_value
        elif request.target_vital == "breakage":
            vitals.breakage = request.vital_value
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid target_vital: {request.target_vital}. Must be one of: moisture, definition, scalp, breakage"
            )
        
        # Create the HairEvent with category
        event = HairEvent(
            user_id=request.user_id,
            session_id=request.session_id,
            wash_day_number=request.wash_day_number,
            day_in_cycle=request.day_in_cycle,
            vitals_payload=vitals,
            conversation_summary=request.conversation_summary,
            keywords=request.keywords,
            primary_label=primary_label  # Add category label
        )
        
        # Save to database
        saved_event = db.save_hair_event(event)
        print(f"[DEBUG] Saved event with ID: {saved_event.id}, Category: {primary_label}")
        
        # Clean up chat session - it's now captured in the event summary
        db.delete_chat_session(request.session_id)
        print(f"[DEBUG] Cleaned up chat session {request.session_id}")
        
        return saved_event
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[ERROR] Chat endpoint failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Chat processing failed: {str(e)}"
        )



@router.get("/events/{user_id}")
async def get_user_events(user_id: str):
    """
    GET /api/events/{user_id}
    
    Retrieve all diagnostic events for a specific user.
    
    Args:
        user_id: The user identifier
        
    Returns:
        List of HairEvents for this user
    """
    try:
        db = get_db()
        events = db.get_events_by_user(user_id)
        return {"user_id": user_id, "events": events, "count": len(events)}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve events: {str(e)}"
        )


@router.delete("/session/{session_id}")
async def clear_session(session_id: str):
    """
    DELETE /api/session/{session_id}
    
    Clear a chat session (useful for testing/debugging).
    
    Args:
        session_id: The session to clear
        
    Returns:
        Success confirmation
    """
    try:
        db = get_db()
        db.clear_session(session_id)
        return {"message": f"Session {session_id} cleared successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear session: {str(e)}"
        )
