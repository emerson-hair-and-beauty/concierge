from dataclasses import dataclass
from typing import Optional


SOURCE_SESSION_SIGNAL = "session_signal"
SOURCE_ENV_FACTOR = "environmental_factor"


@dataclass(frozen=True)
class Alert:
    alert_type: str
    source_type: str
    source_id: str
    message: str
    cooldown_days: Optional[int] = None  # None = never re-fire after first send
    scenario: Optional[str] = None       # banner-UI label; defaults to alert_type when None
