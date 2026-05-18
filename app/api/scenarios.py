from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks

from app.services.alerts.alert_service import process_alerts
from app.services.db_service import get_db
from app.services.environmental_factors.weather_service import get_city_environmental_data

router = APIRouter(tags=["scenarios"])


@router.post("/run")
async def run_scenarios(background_tasks: BackgroundTasks):
    """
    Daily cron entry point. Iterates every user, builds their context, and
    hands off to process_alerts — the same engine the chat orchestrator uses.
    Dedup + cooldown are owned by the alerts pipeline now; this endpoint just
    sources the inputs.
    """
    db = get_db()
    users = db.get_all_users()
    current_date = datetime.now(timezone.utc)

    results = []

    for user in users:
        user_id = user.get("user_id")
        if not user_id:
            continue

        wash_logs = db.get_latest_wash_events(user_id, limit=5)
        routine = db.get_active_routine(user_id) or {}

        env_kwargs = {}
        location = user.get("location")
        if location:
            env_kwargs["country"] = location
            try:
                weather = await get_city_environmental_data(location, attribute="all")
                if weather:
                    env_kwargs["temp_c"] = weather.get("peak_heat")
                    env_kwargs["humidity"] = weather.get("peak_humidity")
            except Exception as e:
                print(f"[Scenarios] weather lookup failed for {user_id}: {e}")

        try:
            alerts = process_alerts(
                user_id,
                snapshot={},
                wash_logs=wash_logs,
                routine=routine,
                user_meta=user,
                current_date=current_date,
                **env_kwargs,
            )
        except Exception as e:
            print(f"[Scenarios] process_alerts failed for {user_id}: {e}")
            continue

        if alerts:
            results.append({
                "user_id": user_id,
                "alerts": [
                    {"alert_type": a.alert_type, "scenario": a.scenario, "prompt": a.message}
                    for a in alerts
                ],
            })

    return {
        "status": "success",
        "processed_users": len(users),
        "actions_generated": len(results),
        "details": results,
    }
