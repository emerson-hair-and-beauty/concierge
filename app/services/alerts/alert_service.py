from datetime import datetime
from typing import Dict, List, Optional

from app.services.alerts.alert_rules import evaluate
from app.services.alerts.alert_state import filter_unsent, log_sent
from app.services.alerts.alert_types import Alert


def process_alerts(
    user_id: str,
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
    persist: bool = True,
) -> List[Alert]:
    candidates = evaluate(
        snapshot,
        temp_c=temp_c,
        humidity=humidity,
        in_ac=in_ac,
        country=country,
        has_filtration=has_filtration,
        wash_logs=wash_logs,
        routine=routine,
        user_meta=user_meta,
        current_date=current_date,
    )
    new_alerts = filter_unsent(user_id, candidates)

    if persist:
        for alert in new_alerts:
            log_sent(user_id, alert)

    return new_alerts
