import logging
import traceback
import json
from datetime import datetime
from typing import Optional, Any, Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("empath_chat")

def log_error(
    error: Exception, 
    context: Optional[str] = None, 
    extra_data: Optional[Dict[str, Any]] = None
):
    """
    Log a structured error message for debugging and monitoring.
    """
    error_type = type(error).__name__
    error_message = str(error)
    stack_trace = traceback.format_exc()
    
    log_payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "error_type": error_type,
        "message": error_message,
        "context": context,
        "extra_data": extra_data or {},
        "stack_trace": stack_trace.split("\n")[-5:] # Last 5 lines of stack trace
    }
    
    # Print structured info for terminal monitoring
    print(f"\n[ERROR] {error_type} in {context or 'unknown'}: {error_message}")
    
    # In a real production app, you might send this to Sentry, CloudWatch, or Datadog
    logger.error(json.dumps(log_payload))

def log_chat_event(event_type: str, session_id: str, message: str):
    """Log structured chat events for monitoring (hit/miss, etc)"""
    logger.info(f"[CHAT_EVENT] {event_type} | Session: {session_id} | {message}")
