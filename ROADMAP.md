# Concierge Roadmap

## Environmental Factors — ✅ Built

### hard_water_service.py
- GCC countries (UAE, Saudi Arabia, Oman, Qatar, Kuwait, Bahrain) should default to **hard** water — desalinated water carries high mineral content
- Add `has_filtration: bool` parameter — if True, always return **soft** regardless of country

### sweat_service.py
- AC variable now covers **winter** scenario: if `in_ac=True` and `temp_c < 18°C`, return `"DRY"` instead of `"LOW"` (cold + AC = dry air exposure)
- Sweat trigger on **humidity OR heat** (either alone is sufficient): `humidity > 70%` OR `temp > 28°C` for HIGH, not only dew point

### sweat_alert_service.py
- Accept `buildup_present: bool` (from session signal) — if True, prompt user about water filtration ("Do you have a water filtration system at home?")
  - If user confirms filtration → water treated as **soft**
  - If no filtration → default to **hard** for GCC
- Accept `water_hardness: str` — if **hard**, include cleansing recommendation (chelating / clarifying shampoo)
- Add `"DRY"` sweat level handling: generate dry air prompt when AC + cold weather detected

## Alerts Pipeline — ✅ Built

Unified pipeline replacing the parallel `pending_alerts` + `scenarios.py` system. One table (`alert_log`), one engine (`process_alerts`), two entry points (per chat turn, daily cron).

### Phase 1 — Schema + read API (✅)
- `sql/create_alert_log.sql` — unified table: `id, user_id, source_type, source_id, alert_type, scenario, prompt, is_read, sent_at`
- `sql/migrate_alert_log_v2.sql` — drops legacy UNIQUE constraint, adds new columns, imports `pending_alerts` rows tagged `source_type='legacy_scenario'`
- `db.get_pending_alerts` / `db.mark_alert_read` now read/write `alert_log`
- `db.save_pending_alert` (called by `scenarios.py` cron) shimmed to write into `alert_log`

### Phase 3 — Cooldowns + chat-side wiring (✅)
- `Alert.cooldown_days` per rule (mixed strategy):
  - `buildup_filtration_check`, `hard_water_cleansing` → `None` (forever — structural facts)
  - `sweat_*` → 7 days (weather changes)
  - hair-state rules (breakage, absorption, hold_loss, coated) → 14 days
- `filter_unsent` honours per-rule cooldown via `sent_at` comparison
- `app/web_chat_agent/orchestrator.py` runs `process_session_signals` + `process_alerts` between Observer and Triage passes
- Env context: user `location` from `user_metadata` → weather service → `temp_c`/`humidity`/`country` passed to rules. Best-effort; failures don't block the reply
- Alerts emitted as `{"type": "alert", ...}` SSE events
- Fixed: `session_id` now passed through `app/web_chat_agent/router.py` (was always defaulting to `"default"`)

### Phase 2 — Cron scenarios ported into rules (✅)
- 4 rules in `alert_rules.py::_cron_alerts`:
  - `long_gap_clarify` (≥28 days since last wash, cooldown 7d)
  - `day_3_pulse_strength` / `day_3_pulse_moisture` (exact day 3 + primary_goal, cooldown 1d)
  - `weather_defense_humectants` (humidity ≥70% + Polyquaternium-69/PVP in routine, cooldown 1d)
  - `performance_review_3_washes` (exactly 3 wash events, no cooldown)
- `evaluate()` / `process_alerts()` extended with `wash_logs`, `routine`, `user_meta`, `current_date` kwargs
- `app/api/scenarios.py` rewritten: `POST /scenarios/run` iterates users → builds context → delegates to `process_alerts`. ~180 lines collapsed to ~70

### Phase 4 — Legacy cleanup (✅)
- `db.save_pending_alert` and `db.update_last_weather_alert_sent` removed
- `sweat_alert_service.py` and `tests/test_sweat_alerts.py` deleted (functionality lives in `alert_rules.py` + env alerts)
- `sql/drop_pending_alerts.sql` — drops `pending_alerts` table and `user_metadata.last_weather_alert_sent` column

### Deployment notes
- Run `sql/migrate_alert_log_v2.sql` against Supabase before deploying. Safe to run on a database that has either the v1 `alert_log`, the legacy `pending_alerts`, or both.
- After verifying migrated rows in `alert_log`, run `sql/drop_pending_alerts.sql` to retire the legacy table and column.

### Verification
- `tests/test_alerts_e2e.py` covers all 5 turns: session-signal alerts, env alerts (with live weather), cooldown, new-signal-while-others-on-cooldown, cron scenarios (Long Gap + Performance Review + Day-3 Pulse + Weather Defense). 13/13 pass.
