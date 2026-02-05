"""
Quick test to verify Supabase connection
"""

import os
from dotenv import load_dotenv

load_dotenv("app/.env")

print("=" * 60)
print("Supabase Connection Test")
print("=" * 60)

print(f"\n1. Checking environment variables...")
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

print(f"   SUPABASE_URL: {supabase_url}")
print(f"   SUPABASE_KEY: {supabase_key[:20]}..." if supabase_key else "   SUPABASE_KEY: NOT FOUND")

if not supabase_url or not supabase_key:
    print("\n❌ Missing Supabase credentials!")
    exit(1)

print(f"\n2. Attempting to connect to Supabase...")
try:
    from supabase import create_client
    client = create_client(supabase_url, supabase_key)
    print("   ✅ Supabase client created successfully")
except Exception as e:
    print(f"   ❌ Failed to create client: {str(e)}")
    exit(1)

print(f"\n3. Testing database query (chat_messages table)...")
try:
    response = client.table("chat_messages").select("*").limit(1).execute()
    print(f"   ✅ Query successful! Found {len(response.data)} rows")
except Exception as e:
    print(f"   ❌ Query failed: {str(e)}")
    print(f"\n   This might mean:")
    print(f"   - The table doesn't exist (did you run the migration?)")
    print(f"   - The API key doesn't have the right permissions")
    print(f"   - Row Level Security (RLS) is blocking the query")
    exit(1)

print(f"\n4. Testing insert operation...")
try:
    test_data = {
        "session_id": "test-connection-check",
        "role": "user",
        "content": "Connection test message"
    }
    response = client.table("chat_messages").insert(test_data).execute()
    print(f"   ✅ Insert successful!")
    
    # Clean up
    client.table("chat_messages").delete().eq("session_id", "test-connection-check").execute()
    print(f"   ✅ Cleanup successful!")
except Exception as e:
    print(f"   ❌ Insert failed: {str(e)}")
    exit(1)

print("\n" + "=" * 60)
print("✅ All tests passed! Supabase is ready to use.")
print("=" * 60)
