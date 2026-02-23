import asyncio
from fastapi import APIRouter, HTTPException, status
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
from app.api.errors import (
    ChatValidationError,
    ChatRateLimitError,
    ChatDatabaseError,
    ChatTimeoutError,
    ChatInternalError
)
from app.utils.error_logger import log_error, log_chat_event
from collections import defaultdict
from typing import Dict, List

# In-memory chat history storage (session_id -> list of message dicts)
# Each message: {"role": str, "message": str, "user_id": Optional[str]}
_chat_history_cache: Dict[str, List[Dict[str, str]]] = defaultdict(list)

# In-memory context cache (session_id -> formatted context string)
_session_context_cache: Dict[str, str] = {}

def get_history_from_cache(session_id: str, limit: int = 10) -> List[Dict[str, str]]:
    """Retrieve chat history from in-memory cache"""
    history = _chat_history_cache.get(session_id, [])
    return history[-limit:] if limit else history

def append_to_history_cache(session_id: str, role: str, message: str, user_id: str = None):
    """Append a message to the in-memory chat history cache"""
    _chat_history_cache[session_id].append({
        "role": role,
        "message": message,
        "user_id": user_id
    })

def clear_history_cache(session_id: str):
    """Remove a session's history from the cache"""
    if session_id in _chat_history_cache:
        del _chat_history_cache[session_id]

def clear_session_caches(session_id: str):
    """Clear both history and context caches for a session"""
    clear_history_cache(session_id)
    if session_id in _session_context_cache:
        del _session_context_cache[session_id]

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
        # Request Validation
        if not request.message or not request.session_id:
            raise ChatValidationError("Missing message or session_id")
        
        db = get_db()
        
        # 1. Retrieve conversation history from CACHE (Fast)
        try:
            history = get_history_from_cache(request.session_id, limit=10)
        except Exception as e:
            log_error(e, context="get_history_from_cache", extra_data={"session_id": request.session_id})
            # Fallback to DB if cache fails (though unlikely)
            history = db.get_chat_history(request.session_id, limit=10)
            
        # 2. Save the user's message to CACHE
        try:
            append_to_history_cache(request.session_id, "user", request.message, user_id=request.user_id)
        except Exception as e:
            log_error(e, context="append_to_history_cache_user")
            # Fallback to DB
            db.append_chat_message(request.session_id, "user", request.message, user_id=request.user_id)
            
        # 3. Fetch past events from Librarian for context (with CACHE)
        if request.session_id in _session_context_cache:
            past_context = _session_context_cache[request.session_id]
            log_chat_event("cache_hit_context", request.session_id, "Using cached Librarian context")
        else:
            librarian = get_librarian()
            try:
                past_events = librarian.get_recent_events(request.user_id, limit=5)
                past_context = librarian.format_context_for_prompt(past_events)
                # Store in cache
                _session_context_cache[request.session_id] = past_context
                log_chat_event("cache_miss_context", request.session_id, "Fetched and cached Librarian context")
            except Exception as e:
                log_error(e, context="librarian_fetch", extra_data={"user_id": request.user_id})
                # Graceful degradation: continue with empty context if Librarian fails
                past_context = ""
        
        # 4. Run the diagnostic agent with past context (with timeout)
        try:
            # Set a 30 second timeout for LLM processing
            response_message, handoff, target_vital = await asyncio.wait_for(
                diagnose_hair_concern(
                    history=history,
                    current_message=request.message,
                    past_context=past_context
                ),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            raise ChatTimeoutError("The diagnostic engine took too long to respond. Please try again.")
        except Exception as e:
            # Check if it looks like a rate limit
            if "429" in str(e) or "quota" in str(e).lower():
                raise ChatRateLimitError()
            log_error(e, context="diagnose_hair_concern", extra_data={"session_id": request.session_id})
            raise ChatInternalError(f"Diagnostic engine failure: {str(e)}")
        
        # 5. If handoff detected, run auto-summarization (graceful failure)
        summary = None
        keywords = []
        if handoff:
            try:
                from app.agents.summarizer import summarize_diagnostic
                full_context = history + [
                    {"role": "user", "message": request.message},
                    {"role": "assistant", "message": response_message}
                ]
                # Summarization failure shouldn't crash the whole chat
                summary, keywords = await asyncio.wait_for(
                    summarize_diagnostic(full_context),
                    timeout=15.0
                )
            except Exception as e:
                log_error(e, context="summarization_failure")
                # Non-critical failure, continue with empty summary
                summary = "Summary generation failed."
                keywords = []
        
        # 6. Save the assistant's response to CACHE
        try:
            append_to_history_cache(request.session_id, "assistant", response_message, user_id=request.user_id)
        except Exception as e:
            log_error(e, context="append_to_history_cache_assistant")
            db.append_chat_message(request.session_id, "assistant", response_message, user_id=request.user_id)
        
        log_chat_event("success_cache_history", request.session_id, "Response generated with in-memory history")
        
        return ChatResponse(
            message=response_message,
            handoff=handoff,
            target_vital=target_vital,
            session_id=request.session_id,
            summary=summary,
            keywords=keywords
        )
        
    except (ChatValidationError, ChatRateLimitError, ChatDatabaseError, ChatTimeoutError, ChatInternalError) as ce:
        # Re-raise known chat errors (FastAPI handles status_code)
        raise HTTPException(status_code=ce.status_code, detail=ce.message)
    except Exception as e:
        log_error(e, context="chat_endpoint_top_level")
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}"
        )


@router.post("/chat/warmup")
async def chat_warmup(request: ChatRequest):
    """
    POST /api/chat/warmup
    
    Proactively load and cache Librarian context for a session.
    Reduces latency for the first message.
    """
    try:
        if not request.user_id or not request.session_id:
            raise ChatValidationError("Missing user_id or session_id")
            
        # Only cache if not already present
        if request.session_id not in _session_context_cache:
            librarian = get_librarian()
            past_events = librarian.get_recent_events(request.user_id, limit=5)
            past_context = librarian.format_context_for_prompt(past_events)
            _session_context_cache[request.session_id] = past_context
            log_chat_event("warmup_success", request.session_id, "Context pre-cached")
        else:
            log_chat_event("warmup_skipped", request.session_id, "Context already cached")
            
        return {"status": "ready", "session_id": request.session_id}
        
    except ChatValidationError as ce:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ce.message)
    except Exception as e:
        log_error(e, context="chat_warmup_failure")
        # Warmup failure shouldn't be a hard error for the client
        return {"status": "failed", "detail": str(e)}


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
        if not request.target_vital or request.vital_value is None:
            raise ChatValidationError("Missing target_vital or vital_value")
            
        db = get_db()
        librarian = get_librarian()
        
        # Categorize the event using Librarian
        try:
            primary_label = librarian.categorize_vital(request.target_vital)
        except Exception as e:
            log_error(e, context="categorize_vital")
            primary_label = request.target_vital.upper() # Fallback
        
        # Build the vitals payload based on which vital was diagnosed
        vitals = VitalsPayload()
        v_attr = request.target_vital.lower()
        if hasattr(vitals, v_attr):
            setattr(vitals, v_attr, request.vital_value)
        else:
            raise ChatValidationError(f"Invalid target_vital: {request.target_vital}")
        
        # Create the HairEvent with category
        event = HairEvent(
            user_id=request.user_id,
            session_id=request.session_id,
            wash_day_number=request.wash_day_number,
            day_in_cycle=request.day_in_cycle,
            vitals_payload=vitals,
            conversation_summary=request.conversation_summary,
            keywords=request.keywords,
            primary_label=primary_label
        )
        
        # Save to database
        try:
            saved_event = db.save_hair_event(event)
        except Exception as e:
            log_error(e, context="save_hair_event")
            raise ChatDatabaseError(f"Failed to save event: {str(e)}")
        
        # Clean up chat session cache (graceful cleanup)
        try:
            clear_session_caches(request.session_id)
            # Still call DB cleanup for any legacy data or safety
            db.delete_chat_session(request.session_id)
        except Exception as e:
            log_error(e, context="delete_chat_session")
        
        return saved_event
        
    except ChatValidationError as ce:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ce.message)
    except ChatDatabaseError as ce:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=ce.message)
    except Exception as e:
        log_error(e, context="save_event_endpoint")
        raise HTTPException(status_code=500, detail=f"Failed to save event: {str(e)}")



@router.get("/vitals/{user_id}")
async def get_vitals_summary_endpoint(user_id: str):
    """
    GET /api/vitals/{user_id}
    
    Retrieve a summary of latest, average, and historical trends for all core vitals.
    
    Args:
        user_id: The user identifier
        
    Returns:
        Dict mapping each category to its latest, average, and history data.
    """
    try:
        librarian = get_librarian()
        summary = librarian.get_vitals_summary(user_id)
        return summary
    except Exception as e:
        log_error(e, context="get_vitals_summary_endpoint")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve vitals summary: {str(e)}"
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
    
    Clear a chat session and its caches (useful for testing/debugging).
    """
    try:
        db = get_db()
        # Clear in-memory caches
        clear_session_caches(session_id)
        # Clear database history
        db.clear_session(session_id)
        return {"message": f"Session {session_id} cleared successfully"}
    except Exception as e:
        log_error(e, context="clear_session_endpoint")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear session: {str(e)}"
        )
