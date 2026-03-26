import asyncio
import os
import json
import httpx
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks

from app.services.db_service import get_db
from app.config import WEATHER_API_KEY

router = APIRouter(tags=["scenarios"])

async def fetch_weather_humidity(location_query: str) -> int:
    """
    Fetch weather humidity from an external API using the location query.
    If WEATHER_API_KEY is not set or the request fails, return a safe default.
    """
    if not WEATHER_API_KEY:
        print("[Scenarios] WEATHER_API_KEY not configured, skipping external API.")
        return 0
        
    # Example using OpenWeatherMap (could be replaced with actual provider)
    # Using https://api.openweathermap.org/data/2.5/weather?q={location_query}&appid={WEATHER_API_KEY}
    url = f"https://api.openweathermap.org/data/2.5/weather?q={location_query}&appid={WEATHER_API_KEY}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                return data.get("main", {}).get("humidity", 0)
    except Exception as e:
        print(f"[Scenarios] Weather API error: {e}")
        
    return 0
    

def _check_scenario_1_long_gap(user: Dict, wash_logs: List[Dict], current_date: datetime) -> Optional[str]:
    """
    Scenario 1: The "Long Gap" (Reset Logic)
    Trigger: current_date - last_wash_date >= 28 days.
    """
    if not wash_logs:
        return None
        
    last_wash = wash_logs[0] # assuming ordered by created_at desc
    last_wash_date = datetime.fromisoformat(last_wash["created_at"].replace("Z", "+00:00"))
    
    delta_days = (current_date.date() - last_wash_date.date()).days
    if delta_days >= 28:
        return "It's been 4 weeks. To prevent scalp inflammation and help your hair actually absorb moisture again, you need a Clarifying Wash to reset your foundation"
    return None

def _check_scenario_2_day_3_pulse(user: Dict, wash_logs: List[Dict], current_date: datetime) -> Optional[str]:
    """
    Scenario 2: The "Day 3" Pulse (Validation Logic)
    Trigger: current_date - last_wash_date == 3 days.
    """
    if not wash_logs:
        return None
        
    last_wash = wash_logs[0]
    last_wash_date = datetime.fromisoformat(last_wash["created_at"].replace("Z", "+00:00"))
    
    delta_days = (current_date.date() - last_wash_date.date()).days
    if delta_days == 3:
        primary_goal = user.get("primary_goal", "").lower()
        if primary_goal == "strength":
            return "[AGENT INSTRUCTION: Ask if curls feel they have more structure or if there is less hair fall.]"
        elif primary_goal == "moisture":
            return "[AGENT INSTRUCTION: Check for Dry Strands or Severe Frizz. If present, flag a 'Sealant Imbalance'.]"
    return None

async def _check_scenario_3_weather_defense(user: Dict, routine: Dict) -> Optional[str]:
    """
    Scenario 3: The "Raincoat" (Weather Defense)
    Trigger: humidity >= 70% and routine contains Polyquaternium-69 or PVP.
    """
    location = user.get("location")
    if not location:
        return None
        
    # Check if they already got an alert today
    last_alert_str = user.get("last_weather_alert_sent")
    if last_alert_str:
        last_alert_date = datetime.fromisoformat(last_alert_str.replace("Z", "+00:00")).date()
        if last_alert_date == datetime.utcnow().date():
            return None # Already alerted today
    
    # Check ingredients in routine
    routine_text = json.dumps(routine).lower()
    has_humectant = "polyquaternium-69" in routine_text or "pvp" in routine_text
    
    if not has_humectant:
        return None
        
    humidity = await fetch_weather_humidity(location)
    if humidity >= 70:
        # Mark that we sent the alert
        get_db().update_last_weather_alert_sent(user.get("user_id"), datetime.utcnow().isoformat())
        return f"Humidity is at {humidity}%. Your current products might have too many humectants. Layer in a strong-hold gel or a sealant to block the moisture out and keep your definition"
        
    return None

def _check_scenario_4_performance_review(wash_logs: List[Dict]) -> Optional[str]:
    """
    Scenario 4: The "Performance Review" (Evaluation)
    Trigger: count(wash_events) == 3 since adding a new product.
    Note: For this MVP, we just count if they have exactly 3 wash events.
    """
    if len(wash_logs) == 3:
        # We assume adding a new product corresponds to starting a routine / having 3 washes
        return "[AGENT INSTRUCTION: Trigger a 'Performance Review' chat to update vital_scores. If user felt stripped/dry after clarify, intervene and remind about moisturizing follow-up.]"
    return None


@router.post("/run")
async def run_scenarios(background_tasks: BackgroundTasks):
    """
    Cron endpoint triggered daily (e.g. via Supabase Edge Functions).
    Iterates through users, evaluating the 4 scenarios.
    Returns a summary of actions taken or prompts generated.
    """
    db = get_db()
    users = db.get_all_users()
    
    results = []
    current_date = datetime.utcnow()
    
    from typing import Optional
    
    for user in users:
        user_id = user.get("user_id")
        if not user_id:
            continue
            
        events = db.get_events_by_user(user_id)
        wash_logs = db.get_latest_wash_events(user_id, limit=5)
        routine = db.get_active_routine(user_id) or {}
        
        user_actions = []
        
        # Scenario 1
        s1 = _check_scenario_1_long_gap(user, wash_logs, current_date)
        if s1: user_actions.append({"scenario": "Long Gap", "prompt": s1})
        
        # Scenario 2
        s2 = _check_scenario_2_day_3_pulse(user, wash_logs, current_date)
        if s2: user_actions.append({"scenario": "Day 3 Pulse", "prompt": s2})
        
        # Scenario 3
        s3 = await _check_scenario_3_weather_defense(user, routine)
        if s3: user_actions.append({"scenario": "Weather Defense", "prompt": s3})
        
        # Scenario 4
        s4 = _check_scenario_4_performance_review(wash_logs)
        if s4: user_actions.append({"scenario": "Performance Review", "prompt": s4})
        
        if user_actions:
            # Persist every generated action as a pending alert
            for action in user_actions:
                db.save_pending_alert(
                    user_id=user_id,
                    scenario=action["scenario"],
                    prompt=action["prompt"]
                )
            
            results.append({
                "user_id": user_id,
                "actions": user_actions
            })
            
    return {
        "status": "success",
        "processed_users": len(users),
        "actions_generated": len(results),
        "details": results
    }
