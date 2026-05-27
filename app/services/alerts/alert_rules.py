import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.services.alerts.alert_types import (
    Alert,
    SOURCE_ENV_FACTOR,
    SOURCE_SESSION_SIGNAL,
)
from app.services.environmental_factors.sweat_service import (
    calculate_dew_point,
    get_sweat_level,
)
from app.services.environmental_factors.hard_water_service import get_water_hardness


SOURCE_CRON = "cron"

# Cooldown strategy per rule. None = once per user forever.
COOLDOWN_BUILDUP_FILTRATION = None
COOLDOWN_HARD_WATER = None
COOLDOWN_SWEAT = 7
COOLDOWN_HAIR_STATE = 14
COOLDOWN_LONG_GAP = 7              # repeat weekly while the user keeps skipping
COOLDOWN_DAY_3_PULSE = 1           # trigger is exact-day; cooldown just guards against cron double-runs
COOLDOWN_WEATHER_DEFENSE = 1       # matches legacy daily semantics
COOLDOWN_PERFORMANCE_REVIEW = None # 3rd wash happens once


def _session_signal_alerts(snapshot: Dict[str, bool]) -> List[Alert]:
    alerts: List[Alert] = []

    if snapshot.get("buildup_present"):
        alerts.append(Alert(
            alert_type="buildup_filtration_check",
            source_type=SOURCE_SESSION_SIGNAL,
            source_id="buildup_present",
            cooldown_days=COOLDOWN_BUILDUP_FILTRATION,
            scenario="Buildup Check",
            message=(
                "I'm noticing signs of buildup. Do you have a water filtration system at home? "
                "This directly affects mineral deposits on your hair."
            ),
        ))

    if snapshot.get("breakage_active"):
        alerts.append(Alert(
            alert_type="breakage_protein_check",
            source_type=SOURCE_SESSION_SIGNAL,
            source_id="breakage_active",
            cooldown_days=COOLDOWN_HAIR_STATE,
            scenario="Breakage Check",
            message=(
                "Active breakage usually points to a protein/moisture imbalance. "
                "When did you last do a strengthening treatment?"
            ),
        ))

    if snapshot.get("absorption_blocked"):
        alerts.append(Alert(
            alert_type="absorption_clarify",
            source_type=SOURCE_SESSION_SIGNAL,
            source_id="absorption_blocked",
            cooldown_days=COOLDOWN_HAIR_STATE,
            scenario="Absorption Check",
            message=(
                "If products are beading up, the cuticle may be coated. "
                "A clarifying wash before your next treatment could help."
            ),
        ))

    if snapshot.get("hold_loss"):
        alerts.append(Alert(
            alert_type="hold_loss_protein",
            source_type=SOURCE_SESSION_SIGNAL,
            source_id="hold_loss",
            cooldown_days=COOLDOWN_HAIR_STATE,
            scenario="Hold Loss",
            message=(
                "Curls dropping fast often signals weakened elasticity. "
                "A light protein step in your wash routine may restore structure."
            ),
        ))

    if snapshot.get("coated_feel"):
        alerts.append(Alert(
            alert_type="coated_clarify",
            source_type=SOURCE_SESSION_SIGNAL,
            source_id="coated_feel",
            cooldown_days=COOLDOWN_HAIR_STATE,
            scenario="Coated Feel",
            message=(
                "That waxy, filmy feel is usually silicone or oil buildup. "
                "A clarifying shampoo will reset the strand."
            ),
        ))

    return alerts


def _environmental_alerts(
    temp_c: Optional[float],
    humidity: Optional[float],
    in_ac: bool,
    country: Optional[str],
    has_filtration: bool,
) -> List[Alert]:
    alerts: List[Alert] = []

    if temp_c is not None and humidity is not None:
        sweat = get_sweat_level(temp_c, humidity, in_ac)
        if sweat == "HIGH":
            td = calculate_dew_point(temp_c, humidity)
            alerts.append(Alert(
                alert_type="sweat_high_humidity",
                source_type=SOURCE_ENV_FACTOR,
                source_id="sweat",
                cooldown_days=COOLDOWN_SWEAT,
                scenario="Weather Defense",
                message=(
                    f"High humidity today (Dew Point: {td:.1f}°C) — sweat is likely to "
                    f"sit on your scalp. Are you spending most of your day in AC?"
                ),
            ))
        elif sweat == "MEDIUM":
            alerts.append(Alert(
                alert_type="sweat_medium_heat",
                source_type=SOURCE_ENV_FACTOR,
                source_id="sweat",
                cooldown_days=COOLDOWN_SWEAT,
                scenario="Weather Defense",
                message=(
                    f"Hot day ahead ({temp_c}°C) — sweating may leave salt deposits on "
                    f"your hair. Are you spending most of your day in AC?"
                ),
            ))
        elif sweat == "DRY":
            alerts.append(Alert(
                alert_type="sweat_dry_ac_cold",
                source_type=SOURCE_ENV_FACTOR,
                source_id="sweat",
                cooldown_days=COOLDOWN_SWEAT,
                scenario="Weather Defense",
                message=(
                    "Cold weather combined with indoor AC can strip moisture from your hair. "
                    "Are you noticing more dryness or brittleness than usual?"
                ),
            ))

    if country:
        hardness = get_water_hardness(country, has_filtration)
        if hardness == "hard":
            alerts.append(Alert(
                alert_type="hard_water_cleansing",
                source_type=SOURCE_ENV_FACTOR,
                source_id="water_hardness",
                cooldown_days=COOLDOWN_HARD_WATER,
                scenario="Hard Water",
                message=(
                    "With hard water, mineral buildup is common. "
                    "A chelating or clarifying shampoo should be part of your routine."
                ),
            ))

    return alerts


def _days_since(ts_iso: str, current_date: datetime) -> Optional[int]:
    try:
        ts = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    except Exception:
        return None
    return (current_date.date() - ts.date()).days


def _cron_alerts(
    wash_logs: List[Dict],
    routine: Optional[Dict],
    user_meta: Optional[Dict],
    humidity: Optional[float],
    current_date: datetime,
) -> List[Alert]:
    """Rules that need historical state — only fire from the cron path."""
    alerts: List[Alert] = []
    user_meta = user_meta or {}

    # --- Scenario 1: Long Gap (>= 28 days since last wash) ----------------
    if wash_logs:
        delta = _days_since(wash_logs[0].get("created_at", ""), current_date)
        if delta is not None and delta >= 28:
            alerts.append(Alert(
                alert_type="long_gap_clarify",
                source_type=SOURCE_CRON,
                source_id="wash_logs",
                cooldown_days=COOLDOWN_LONG_GAP,
                scenario="Long Gap",
                message=(
                    "It's been 4 weeks. To prevent scalp inflammation and help your hair "
                    "actually absorb moisture again, you need a Clarifying Wash to reset "
                    "your foundation."
                ),
            ))

    # --- Scenario 2: Day-3 Pulse (exactly 3 days post-wash) ---------------
    if wash_logs:
        delta = _days_since(wash_logs[0].get("created_at", ""), current_date)
        primary_goal = (user_meta.get("primary_goal") or "").lower()
        if delta == 3 and primary_goal == "strength":
            alerts.append(Alert(
                alert_type="day_3_pulse_strength",
                source_type=SOURCE_CRON,
                source_id="wash_logs",
                cooldown_days=COOLDOWN_DAY_3_PULSE,
                scenario="Day 3 Pulse",
                message="[AGENT INSTRUCTION: Ask if curls feel they have more structure or if there is less hair fall.]",
            ))
        elif delta == 3 and primary_goal == "moisture":
            alerts.append(Alert(
                alert_type="day_3_pulse_moisture",
                source_type=SOURCE_CRON,
                source_id="wash_logs",
                cooldown_days=COOLDOWN_DAY_3_PULSE,
                scenario="Day 3 Pulse",
                message="[AGENT INSTRUCTION: Check for Dry Strands or Severe Frizz. If present, flag a 'Sealant Imbalance'.]",
            ))

    # --- Scenario 3: Weather Defense (humectants + high humidity) ---------
    if routine and humidity is not None and humidity >= 70:
        routine_text = json.dumps(routine).lower()
        has_humectant = "polyquaternium-69" in routine_text or "pvp" in routine_text
        if has_humectant:
            alerts.append(Alert(
                alert_type="weather_defense_humectants",
                source_type=SOURCE_CRON,
                source_id="routine_humectants",
                cooldown_days=COOLDOWN_WEATHER_DEFENSE,
                scenario="Weather Defense",
                message=(
                    f"Humidity is at {int(humidity)}%. Your current products might have too many "
                    f"humectants. Layer in a strong-hold gel or a sealant to block the moisture "
                    f"out and keep your definition."
                ),
            ))

    # --- Scenario 4: Performance Review (exactly 3 wash events) -----------
    if len(wash_logs) == 3:
        alerts.append(Alert(
            alert_type="performance_review_3_washes",
            source_type=SOURCE_CRON,
            source_id="wash_logs",
            cooldown_days=COOLDOWN_PERFORMANCE_REVIEW,
            scenario="Performance Review",
            message="[AGENT INSTRUCTION: Trigger a 'Performance Review' chat to update vital_scores. If user felt stripped/dry after clarify, intervene and remind about moisturizing follow-up.]",
        ))

    return alerts


def evaluate(
    snapshot: Dict[str, bool],
    *,
    temp_c: Optional[float] = None,
    humidity: Optional[float] = None,
    in_ac: bool = False,
    country: Optional[str] = None,
    has_filtration: bool = False,
    wash_logs: Optional[List[Dict]] = None,
    routine: Optional[Dict] = None,
    user_meta: Optional[Dict] = None,
    current_date: Optional[datetime] = None,
) -> List[Alert]:
    alerts = (
        _session_signal_alerts(snapshot)
        + _environmental_alerts(temp_c, humidity, in_ac, country, has_filtration)
    )
    if wash_logs is not None or routine is not None or user_meta is not None:
        alerts += _cron_alerts(
            wash_logs=wash_logs or [],
            routine=routine,
            user_meta=user_meta,
            humidity=humidity,
            current_date=current_date or datetime.now(timezone.utc),
        )
    return alerts
