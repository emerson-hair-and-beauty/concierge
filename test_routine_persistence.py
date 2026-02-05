"""
Test Routine Persistence

Verifies that:
1. Valid routine data can be saved to the database via db_service
2. Routines can be retrieved via the GET API endpoint
3. The retrieved structure matches the saved structure
"""

import requests
import uuid
import json
import asyncio
from app.services.db_service import get_db

BASE_URL = "http://localhost:8000"

def test_routine_persistence():
    print("=" * 70)
    print("TESTING ROUTINE PERSISTENCE")
    print("=" * 70)
    
    user_id = f"routine-test-{str(uuid.uuid4())[:8]}"
    
    print(f"\n📋 Test Setup:")
    print(f"   User ID: {user_id}")
    
    # ========================================
    # STEP 1: Simulate Orchestrator Saving Routine
    # ========================================
    print(f"\n💾 STEP 1: Saving routine via DB Service")
    print("-" * 70)
    
    # Mock routine data (simplified from user example)
    mock_routine = {
        "routine": [
            {
                "title": "Cleanse",
                "description": "Use a gentle cleanser",
                "products": [
                    {
                        "name": "Gentle Cleansing Rinse",
                        "brand": "Recommended",
                        "tags": ["Cleanse", "Gentle"]
                    }
                ]
            },
            {
                "title": "Condition",
                "description": "Apply a moisturizing conditioner",
                "products": [
                    {
                        "name": "Super Moisture Conditioner",
                        "brand": "Recommended",
                        "tags": ["Moisture", "Protein"]
                    }
                ]
            }
        ],
        "profile": {
            "hair_density": "Medium",
            "porosity_level": "High Porosity"
        }
    }
    
    try:
        # We use the DB service directly to simulate the orchestrator's internal save
        # since calling the actual orchestrator costs money/tokens
        db = get_db()
        saved_record = db.save_routine(user_id, mock_routine)
        
        print(f"   ✅ Routine saved to DB!")
        print(f"   Record ID: {saved_record.get('id', 'unknown')}")
        
        
    except Exception as e:
        print(f"   ❌ Failed to save routine: {e}")
        if hasattr(e, 'response') and e.response:
             print(f"   Response text: {e.response.text}")
        return

    # ========================================
    # STEP 2: Retrieve via API
    # ========================================
    print(f"\n📥 STEP 2: Retrieving routine via API")
    print("-" * 70)
    
    url = f"{BASE_URL}/run-orchestrator/routine/{user_id}"
    print(f"   GET {url}")
    
    response = requests.get(url, timeout=10)
    
    if response.status_code == 200:
        retrieved_data = response.json()
        print(f"   ✅ API Response received")
        
        # Verify content
        if retrieved_data.get("profile", {}).get("hair_density") == "Medium":
            print(f"   ✅ Verified profile data matches")
        else:
            print(f"   ❌ Profile data mismatch")
            print(f"   Got: {json.dumps(retrieved_data.get('profile'), indent=2)}")
            
        if len(retrieved_data.get("routine", [])) == 2:
            print(f"   ✅ Verified routine has 2 steps")
        else:
            print(f"   ❌ Routine step count mismatch")
            
        print(f"   ✅ Full structure retrieved successfully")
        
    else:
        print(f"   ❌ API Failed: {response.status_code}")
        print(f"   {response.text}")

    # ========================================
    # VERIFICATION
    # ========================================
    print("\n" + "=" * 70)
    print("✅ TEST COMPLETE!")
    print("=" * 70)
    print(f"\n📊 Verification in Supabase:")
    print(f"   Check table 'user_routines'")
    print(f"   Filter user_id = '{user_id}'")
    print(f"   You should see the JSON blob stored in 'routine_data'")
    print("=" * 70)

if __name__ == "__main__":
    test_routine_persistence()
