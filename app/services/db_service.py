"""
Database Service for Empath Diagnostic Engine
Provides Supabase-backed storage for chat sessions and hair events
"""

from typing import List, Dict, Optional
from app.api.models import HairEvent
from app.services.supabase_service import get_supabase

class DatabaseService:
    """
    Supabase-backed database service for persistent storage.
    Replaces in-memory storage with production-ready Supabase tables.
    """
    
    def __init__(self):
        self.supabase = get_supabase()
        print("[DB] DatabaseService initialized with Supabase backend")
    
    def get_chat_history(self, session_id: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Retrieve the last N messages from a chat session.
        
        Args:
            session_id: Unique session identifier
            limit: Maximum number of messages to return (default: 10)
            
        Returns:
            List of message dicts with 'role' and 'message' keys
        """
        try:
            # Query chat_messages table, ordered by created_at DESC, limit N
            response = self.supabase.table("chat_messages") \
                .select("role, content, created_at") \
                .eq("session_id", session_id) \
                .order("created_at", desc=False) \
                .limit(limit) \
                .execute()
            
            # Transform to expected format
            messages = []
            for row in response.data:
                messages.append({
                    "role": row["role"],
                    "message": row["content"]
                })
            
            print(f"[DB] Retrieved {len(messages)} messages for session {session_id}")
            return messages
            
        except Exception as e:
            print(f"[DB ERROR] Failed to retrieve chat history: {str(e)}")
            return []
    
    def append_chat_message(self, session_id: str, role: str, message: str, user_id: str = None) -> None:
        """
        Add a message to the chat history.
        
        Args:
            session_id: Unique session identifier
            role: Either "user" or "assistant"
            message: The message content
            user_id: Firebase user ID (optional for backward compatibility)
        """
        try:
            insert_data = {
                "session_id": session_id,
                "role": role,
                "content": message
            }
            
            # Add user_id if provided
            if user_id:
                insert_data["user_id"] = user_id
            
            self.supabase.table("chat_messages").insert(insert_data).execute()
            
            print(f"[DB] Saved {role} message to session {session_id}" + (f" for user {user_id}" if user_id else ""))
            
        except Exception as e:
            print(f"[DB ERROR] Failed to save message: {str(e)}")
            raise e
    
    def save_hair_event(self, event: HairEvent) -> HairEvent:
        """
        Persist a HairEvent to storage.
        
        Args:
            event: The HairEvent to save
            
        Returns:
            The saved event (with generated ID if not provided)
        """
        try:
            # Convert VitalsPayload to dict for JSONB storage
            vitals_dict = event.vitals_payload.model_dump()
            
            # Determine primary_label from vitals_payload
            primary_label = None
            for vital_name, vital_value in vitals_dict.items():
                if vital_value is not None:
                    primary_label = vital_name.upper()
                    break
            
            # Prepare metadata
            metadata = {
                "wash_day_number": event.wash_day_number,
                "day_in_cycle": event.day_in_cycle,
                "keywords": event.keywords,
                "session_id": event.session_id
            }
            
            # Insert into hair_events table
            response = self.supabase.table("hair_events").insert({
                "user_id": event.user_id,
                "primary_label": primary_label,
                "summary": event.conversation_summary,
                "vital_score": next((v for v in vitals_dict.values() if v is not None), None),
                "metadata": metadata
            }).execute()
            
            print(f"[DB] Saved HairEvent for user {event.user_id} with label {primary_label}")
            return event
            
        except Exception as e:
            print(f"[DB ERROR] Failed to save hair event: {str(e)}")
            raise e
    
    def delete_chat_session(self, session_id: str) -> None:
        """
        Delete all chat messages for a given session.
        Called after event is saved to clean up temporary chat history.
        
        Args:
            session_id: Session identifier to delete
        """
        try:
            response = self.supabase.table("chat_messages") \
                .delete() \
                .eq("session_id", session_id) \
                .execute()
            
            deleted_count = len(response.data) if response.data else 0
            print(f"[DB] Deleted {deleted_count} chat messages for session {session_id}")
            
        except Exception as e:
            print(f"[DB ERROR] Failed to delete chat session: {str(e)}")
            # Don't raise - this is a cleanup operation, not critical
    
    def get_events_by_user(self, user_id: str) -> List[HairEvent]:
        """
        Retrieve all events for a specific user.
        
        Args:
            user_id: The user identifier
            
        Returns:
            List of HairEvents for this user
        """
        try:
            response = self.supabase.table("hair_events") \
                .select("*") \
                .eq("user_id", user_id) \
                .order("created_at", desc=True) \
                .execute()
            
            # Convert Supabase rows back to HairEvent objects
            events = []
            for row in response.data:
                # Reconstruct VitalsPayload from vital_score and primary_label
                from app.api.models import VitalsPayload
                vitals = VitalsPayload()
                if row["primary_label"] and row["vital_score"]:
                    setattr(vitals, row["primary_label"].lower(), row["vital_score"])
                
                # Extract metadata fields
                metadata = row.get("metadata", {})
                
                event = HairEvent(
                    id=str(row["id"]),
                    user_id=row["user_id"],
                    session_id=metadata.get("session_id", ""),
                    wash_day_number=metadata.get("wash_day_number"),
                    day_in_cycle=metadata.get("day_in_cycle"),
                    vitals_payload=vitals,
                    conversation_summary=row["summary"] or "",
                    keywords=metadata.get("keywords", []),
                    created_at=row["created_at"]
                )
                events.append(event)
            
            print(f"[DB] Retrieved {len(events)} events for user {user_id}")
            return events
            
        except Exception as e:
            print(f"[DB ERROR] Failed to retrieve events: {str(e)}")
            return []
    
    def get_event_by_id(self, event_id: str) -> Optional[HairEvent]:
        """
        Retrieve a specific event by ID.
        
        Args:
            event_id: The event UUID
            
        Returns:
            The HairEvent if found, None otherwise
        """
        try:
            response = self.supabase.table("hair_events") \
                .select("*") \
                .eq("id", event_id) \
                .single() \
                .execute()
            
            if not response.data:
                return None
            
            row = response.data
            from app.api.models import VitalsPayload
            vitals = VitalsPayload()
            if row["primary_label"] and row["vital_score"]:
                setattr(vitals, row["primary_label"].lower(), row["vital_score"])
            
            metadata = row.get("metadata", {})
            
            event = HairEvent(
                id=str(row["id"]),
                user_id=row["user_id"],
                session_id=metadata.get("session_id", ""),
                wash_day_number=metadata.get("wash_day_number"),
                day_in_cycle=metadata.get("day_in_cycle"),
                vitals_payload=vitals,
                conversation_summary=row["summary"] or "",
                keywords=metadata.get("keywords", []),
                created_at=row["created_at"]
            )
            
            return event
            
        except Exception as e:
            print(f"[DB ERROR] Failed to retrieve event: {str(e)}")
            return None
    
    def clear_session(self, session_id: str) -> None:
        """
        Clear all messages from a session (useful for testing).
        
        Args:
            session_id: The session to clear
        """
        try:
            self.supabase.table("chat_messages") \
                .delete() \
                .eq("session_id", session_id) \
                .execute()
            
            print(f"[DB] Cleared session: {session_id}")
            

        except Exception as e:
            print(f"[DB ERROR] Failed to clear session: {str(e)}")

    def save_routine(self, user_id: str, routine_data: Dict) -> Dict:
        """
        Save a generated routine for a user.
        
        Args:
            user_id: The user identifier
            routine_data: Complete routine JSON object
            
        Returns:
            The saved routine record
        """
        try:
            # Note: Column is named 'routine_json' in Supabase
            response = self.supabase.table("user_routines").insert({
                "user_id": user_id,
                "routine_json": routine_data
            }).execute()
            
            print(f"[DB] Saved routine for user {user_id}")
            return response.data[0] if response.data else {}
            
        except Exception as e:
            print(f"[DB ERROR] Failed to save routine: {str(e)}")
            raise e
            
    def get_active_routine(self, user_id: str) -> Optional[Dict]:
        """
        Get the most recent routine for a user.
        
        Args:
            user_id: The user identifier
            
        Returns:
            The routine data dict or None
        """
        try:
            # Note: Column is named 'routine_json' in Supabase
            response = self.supabase.table("user_routines") \
                .select("routine_json, created_at") \
                .eq("user_id", user_id) \
                .order("created_at", desc=True) \
                .limit(1) \
                .execute()
            
            if response.data:
                # Return just the data part
                return response.data[0]["routine_json"]
            return None
            
        except Exception as e:
            print(f"[DB ERROR] Failed to retrieve routine: {str(e)}")
            return None


# Global singleton instance
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
