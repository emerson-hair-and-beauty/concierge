"""
Database Service for Empath Diagnostic Engine
Provides in-memory storage for chat sessions and hair events (vertical slice implementation)
"""

from typing import List, Dict, Optional
from app.api.models import HairEvent

class DatabaseService:
    """
    Lightweight in-memory database for the vertical slice.
    In production, this would be replaced with Firebase/PostgreSQL/etc.
    """
    
    def __init__(self):
        # session_id -> List[{"role": "user"|"assistant", "message": str}]
        self._chat_sessions: Dict[str, List[Dict[str, str]]] = {}
        
        # List of all saved HairEvents
        self._hair_events: List[HairEvent] = []
    
    def get_chat_history(self, session_id: str, limit: int = 5) -> List[Dict[str, str]]:
        """
        Retrieve the last N messages from a chat session.
        
        Args:
            session_id: Unique session identifier
            limit: Maximum number of messages to return (default: 5)
            
        Returns:
            List of message dicts with 'role' and 'message' keys
        """
        if session_id not in self._chat_sessions:
            return []
        
        # Return the last 'limit' messages
        return self._chat_sessions[session_id][-limit:]
    
    def append_chat_message(self, session_id: str, role: str, message: str) -> None:
        """
        Add a message to the chat history.
        
        Args:
            session_id: Unique session identifier
            role: Either "user" or "assistant"
            message: The message content
        """
        if session_id not in self._chat_sessions:
            self._chat_sessions[session_id] = []
        
        self._chat_sessions[session_id].append({
            "role": role,
            "message": message
        })
    
    def save_hair_event(self, event: HairEvent) -> HairEvent:
        """
        Persist a HairEvent to storage.
        
        Args:
            event: The HairEvent to save
            
        Returns:
            The saved event (with generated ID if not provided)
        """
        self._hair_events.append(event)
        print(f"[DB] Saved HairEvent: {event.id} for user {event.user_id}")
        return event
    
    def get_events_by_user(self, user_id: str) -> List[HairEvent]:
        """
        Retrieve all events for a specific user.
        
        Args:
            user_id: The user identifier
            
        Returns:
            List of HairEvents for this user
        """
        return [event for event in self._hair_events if event.user_id == user_id]
    
    def get_event_by_id(self, event_id: str) -> Optional[HairEvent]:
        """
        Retrieve a specific event by ID.
        
        Args:
            event_id: The event UUID
            
        Returns:
            The HairEvent if found, None otherwise
        """
        for event in self._hair_events:
            if event.id == event_id:
                return event
        return None
    
    def clear_session(self, session_id: str) -> None:
        """
        Clear all messages from a session (useful for testing).
        
        Args:
            session_id: The session to clear
        """
        if session_id in self._chat_sessions:
            del self._chat_sessions[session_id]
            print(f"[DB] Cleared session: {session_id}")


# Global singleton instance for the vertical slice
# In production, this would use dependency injection
_db_instance: Optional[DatabaseService] = None

def get_db() -> DatabaseService:
    """
    Get the global database service instance.
    
    Returns:
        The DatabaseService singleton
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseService()
    return _db_instance
