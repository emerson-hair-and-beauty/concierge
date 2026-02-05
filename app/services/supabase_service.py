"""
Supabase Service - Centralized database client
Provides singleton access to Supabase client for the application
"""

import os
from typing import Optional
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class SupabaseService:
    """
    Singleton service for Supabase database operations.
    Manages connection and provides client access.
    """
    
    def __init__(self):
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        
        if not supabase_url or not supabase_key:
            raise ValueError(
                "Missing Supabase credentials. "
                "Please set SUPABASE_URL and SUPABASE_KEY in .env file"
            )
        
        self.client: Client = create_client(supabase_url, supabase_key)
        print(f"[Supabase] Connected to {supabase_url}")
    
    def get_client(self) -> Client:
        """Get the Supabase client instance"""
        return self.client


# Global singleton instance
_supabase_instance: Optional[SupabaseService] = None

def get_supabase() -> Client:
    """
    Get the global Supabase client instance.
    
    Returns:
        Supabase Client for database operations
    """
    global _supabase_instance
    if _supabase_instance is None:
        _supabase_instance = SupabaseService()
    return _supabase_instance.get_client()
