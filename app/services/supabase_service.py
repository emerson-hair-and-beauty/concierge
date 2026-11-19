"""
Supabase Service - Centralized database client
Provides singleton access to Supabase client for the application
"""

import os
import threading
from typing import Optional
from supabase import create_client, Client
from dotenv import load_dotenv

from pathlib import Path

# Load environment variables from app/.env
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

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


# One client per thread. The chat path runs Supabase calls in worker threads
# (asyncio.to_thread). Threads that share one client break its HTTP/2
# connection under load ("non-blocking socket operation" errors).
_local = threading.local()

def get_supabase() -> Client:
    """
    Get the Supabase client for the current thread.
    
    Returns:
        Supabase Client for database operations
    """
    instance: Optional[SupabaseService] = getattr(_local, "instance", None)
    if instance is None:
        instance = SupabaseService()
        _local.instance = instance
    return instance.get_client()
