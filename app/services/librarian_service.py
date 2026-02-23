"""
Librarian Service - Long-Term Memory Manager

Manages the "filing cabinet" of past hair events, enabling context-aware diagnostics.
The Librarian retrieves relevant historical events and formats them for LLM injection.
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta
from app.services.supabase_service import get_supabase

class LibrarianService:
    """
    The Librarian manages Long-Term Memory (LTM) for the diagnostic system.
    It stores and retrieves past hair events to provide historical context.
    """
    
    # Core vital categories (can be extended in the future)
    CORE_CATEGORIES = ["MOISTURE", "SCALP", "DEFINITION", "BREAKAGE"]
    
    def __init__(self):
        self.supabase = get_supabase()
        print("[LIBRARIAN] LibrarianService initialized")
    
    def get_recent_events(self, user_id: str, limit: int = 5) -> List[Dict]:
        """
        Get the most recent events for a user across all categories.
        
        Args:
            user_id: Firebase user ID
            limit: Maximum number of events to retrieve
            
        Returns:
            List of event dictionaries with summary, category, score, and timestamp
        """
        try:
            response = self.supabase.table("hair_events") \
                .select("id, primary_label, summary, vital_score, metadata, created_at") \
                .eq("user_id", user_id) \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            
            events = response.data if response.data else []
            print(f"[LIBRARIAN] Retrieved {len(events)} recent events for user {user_id}")
            return events
            
        except Exception as e:
            print(f"[LIBRARIAN ERROR] Failed to retrieve recent events: {str(e)}")
            return []
    
    def get_events_by_category(self, user_id: str, category: str, limit: int = 3) -> List[Dict]:
        """
        Get recent events for a specific category.
        
        Args:
            user_id: Firebase user ID
            category: Event category (e.g., "MOISTURE", "SCALP")
            limit: Maximum number of events to retrieve
            
        Returns:
            List of event dictionaries for the specified category
        """
        try:
            response = self.supabase.table("hair_events") \
                .select("id, primary_label, summary, vital_score, metadata, created_at") \
                .eq("user_id", user_id) \
                .eq("primary_label", category.upper()) \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            
            events = response.data if response.data else []
            print(f"[LIBRARIAN] Retrieved {len(events)} events for category {category}")
            return events
            
        except Exception as e:
            print(f"[LIBRARIAN ERROR] Failed to retrieve events by category: {str(e)}")
            return []
    
    def format_context_for_prompt(self, events: List[Dict]) -> str:
        """
        Format past events into a readable context string for LLM injection.
        
        Args:
            events: List of event dictionaries
            
        Returns:
            Formatted string for prompt injection
        """
        if not events:
            return "No past events recorded."
        
        context_lines = ["PAST CONTEXT (from Librarian):"]
        
        for event in events:
            # Calculate time ago
            created_at = datetime.fromisoformat(event['created_at'].replace('Z', '+00:00'))
            time_ago = self._format_time_ago(created_at)
            
            # Extract metadata
            metadata = event.get('metadata', {})
            wash_day = metadata.get('wash_day_number', 'unknown')
            keywords = metadata.get('keywords', [])
            keywords_str = ', '.join(keywords[:3]) if keywords else 'none'
            
            # Format event line
            category = event.get('primary_label', 'UNKNOWN')
            summary = event.get('summary', 'No summary available')
            score = event.get('vital_score', 'N/A')
            
            context_lines.append(
                f"- {time_ago}: {summary} "
                f"[Category: {category}, Severity: {score}/10, Wash Day: {wash_day}, Keywords: {keywords_str}]"
            )
        
        return "\n".join(context_lines)
    
    def _format_time_ago(self, timestamp: datetime) -> str:
        """Format timestamp as human-readable 'time ago' string."""
        now = datetime.now(timestamp.tzinfo)
        delta = now - timestamp
        
        if delta.days >= 365:
            years = delta.days // 365
            return f"{years} year{'s' if years > 1 else ''} ago"
        elif delta.days >= 30:
            months = delta.days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        elif delta.days >= 7:
            weeks = delta.days // 7
            return f"{weeks} week{'s' if weeks > 1 else ''} ago"
        elif delta.days > 0:
            return f"{delta.days} day{'s' if delta.days > 1 else ''} ago"
        elif delta.seconds >= 3600:
            hours = delta.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif delta.seconds >= 60:
            minutes = delta.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "just now"
    
    def categorize_vital(self, target_vital: str) -> str:
        """
        Map target_vital to a core category.
        
        Args:
            target_vital: The vital detected by the diagnostic agent
            
        Returns:
            Category label (e.g., "MOISTURE", "SCALP")
        """
        category_map = {
            "moisture": "MOISTURE",
            "scalp": "SCALP",
            "definition": "DEFINITION",
            "breakage": "BREAKAGE",
            "porosity": "MOISTURE",  # Porosity issues often relate to moisture
            "elasticity": "BREAKAGE",  # Elasticity issues often relate to breakage
        }
        
        category = category_map.get(target_vital.lower(), "OTHER")
        print(f"[LIBRARIAN] Categorized '{target_vital}' as '{category}'")
        return category

    def get_vitals_summary(self, user_id: str) -> Dict[str, Dict]:
        """
        Retrieve a summary of latest, average, and historical trends for all core vitals.
        
        Args:
            user_id: Firebase user ID
            
        Returns:
            Dict mapping each category (lowercase) to its latest, average, and history data.
        """
        try:
            # Get all events for user to calculate averages and history
            response = self.supabase.table("hair_events") \
                .select("primary_label, vital_score, created_at") \
                .eq("user_id", user_id) \
                .order("created_at", desc=True) \
                .execute()
            
            data = response.data if response.data else []
            
            summary = {}
            for category in self.CORE_CATEGORIES:
                # Filter events for this category
                cat_events = [e for e in data if e.get('primary_label') == category]
                
                if not cat_events:
                    summary[category.lower()] = {
                        "latest": None,
                        "average": None,
                        "history": []
                    }
                    continue
                
                # Extract scores (filtering out any potential Nones)
                scores = [e['vital_score'] for e in cat_events if e.get('vital_score') is not None]
                
                summary[category.lower()] = {
                    "latest": scores[0] if scores else None,
                    "average": round(sum(scores) / len(scores), 1) if scores else None,
                    "history": scores[:5] # Last 5 scores for trend visualization (already DESC)
                }
            
            print(f"[LIBRARIAN] Generated vitals summary for user {user_id}")
            return summary
            
        except Exception as e:
            print(f"[LIBRARIAN ERROR] Failed to calculate vitals summary: {str(e)}")
            return {cat.lower(): {"latest": None, "average": None, "history": []} for cat in self.CORE_CATEGORIES}


# Singleton instance
_librarian_instance = None

def get_librarian() -> LibrarianService:
    """Get or create the singleton LibrarianService instance."""
    global _librarian_instance
    if _librarian_instance is None:
        _librarian_instance = LibrarianService()
    return _librarian_instance
