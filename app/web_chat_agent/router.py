import json
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from .models import WebChatRequest, WebChatResponse
from .orchestrator import orchestrate_web_chat
from collections import defaultdict
from typing import Dict, List

# In-memory chat history for web chat sessions (separate from diagnostic chat)
_web_chat_history_cache: Dict[str, List[Dict[str, str]]] = defaultdict(list)

def get_web_history(session_id: str, limit: int = 10) -> List[Dict[str, str]]:
    history = _web_chat_history_cache.get(session_id, [])
    return history[-limit:] if limit else history

def append_web_history(session_id: str, role: str, message: str, user_id: str = None):
    _web_chat_history_cache[session_id].append({
        "role": role,
        "message": message,
        "user_id": user_id
    })

router = APIRouter(tags=["web_chat"])

@router.post("/chat", response_model=WebChatResponse)
async def web_chat_endpoint(request: WebChatRequest):
    """Sync endpoint for Web Chat."""
    history = get_web_history(request.session_id)
    append_web_history(request.session_id, "user", request.message, user_id=request.user_id)
    
    full_message = ""
    shopify_id = None
    msg_type = "text"
    
    async for event in orchestrate_web_chat(history, request.message, session_id=request.session_id, user_id=request.user_id):
        if event["type"] == "content":
            full_message += event["content"]
        elif event["type"] == "product":
            shopify_id = event.get("shopify_id")
            msg_type = "product"

    append_web_history(request.session_id, "assistant", full_message, user_id=request.user_id)
    
    return WebChatResponse(
        message=full_message,
        session_id=request.session_id,
        type=msg_type,
        shopify_id=shopify_id
    )

@router.post("/chat/stream")
async def web_chat_stream_endpoint(request: WebChatRequest):
    """Streaming SSE endpoint for Web Chat."""
    history = get_web_history(request.session_id)
    append_web_history(request.session_id, "user", request.message, user_id=request.user_id)

    async def event_generator():
        full_message = ""
        try:
            async for event in orchestrate_web_chat(history, request.message, session_id=request.session_id, user_id=request.user_id):
                # Forward the event to the client
                yield f"data: {json.dumps(event)}\n\n"
                
                if event["type"] == "content":
                    full_message += event["content"]
            
            # Save final message to history
            append_web_history(request.session_id, "assistant", full_message, user_id=request.user_id)
            yield f"data: {json.dumps({'type': 'done', 'session_id': request.session_id})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(), 
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
