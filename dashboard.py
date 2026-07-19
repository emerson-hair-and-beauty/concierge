"""
Emerson Concierge — Stakeholder Testing Dashboard
Run: streamlit run dashboard.py
"""

import asyncio
import difflib
import json
import os
import random
import sqlite3
import sys
import uuid
from datetime import datetime

import streamlit as st

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.services.decision_state.models import (
    ProfileState, EnvironmentalContext, SessionSignal, ResponseComposerInput
)
from app.services.session_signal.signal_detector import SIGNAL_NAMES
from app.services.session_signal.session_signal_service import process_session_signals
from app.services.decision_state.decision_engine import build_strategy_payload, _STRUCTURAL_PRIORITY_STATES
from app.services.decision_state.decision_state_history import get_session_decision_states, log_decision_state
from app.services.decision_state.jte import resolve_delivery_plan
from app.services.session_intent.session_intent_service import process_session_intent
from app.services.decision_state.response_composer import (
    compose_response, _TONE_INSTRUCTIONS, _DEPTH_INSTRUCTIONS, _CTA_INSTRUCTIONS, _EXPOSURE_INSTRUCTIONS,
    _RESPONSE_STRUCTURES, FIXED_SECTION_DEFAULTS, render_response_prompt,
)
from app.services.decision_state.pipeline import _fetch_candidate_products
from app.services.decision_state.texture_modifiers import resolve_texture_modifiers
from app.services.resilience import get_degraded_events

FEEDBACK_FILE = os.path.join(os.path.dirname(__file__), "feedback_log.jsonl")
AB_LOG_FILE = os.path.join(os.path.dirname(__file__), "tone_ab_log.jsonl")
EXPERIMENT_DB_FILE = os.path.join(os.path.dirname(__file__), "experiment_versions.sqlite3")
TONE_PRESETS = list(_TONE_INSTRUCTIONS.keys())

# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

# texture_type, porosity, density, elasticity, humidity_response, hair_goals, routine_flags, description
_PROFILE_SPECS = [
    ("2A", "low",    "low",    None,  "low sensitivity",
     ["hold", "volume"], ["lightweight_products", "avoid_heavy_oils"],
     "Low porosity, low density"),
    ("2B", "medium", "low",    None,  "moderate sensitivity",
     ["definition", "frizz control"], ["light_hold", "frizz_control"],
     "Medium porosity, low density"),
    ("2C", "medium", "medium", None,  "high sensitivity",
     ["frizz control", "hold"], ["frizz_control", "medium_hold"],
     "Medium porosity, medium density"),
    ("3A", "medium", "medium", None,  "moderate sensitivity",
     ["definition", "moisture"], ["moisture_balance", "light_styler"],
     "Medium porosity, medium density"),
    ("3B", "medium", "medium", None,  "moderate sensitivity",
     ["definition", "frizz control"], ["frizz_control", "balanced_volume"],
     "Medium porosity, medium density"),
    ("3C", "low",    "medium", None,  "moderate sensitivity",
     ["definition", "moisture"], ["frizz_control", "avoid_butters", "use_heat_for_masks"],
     "Low porosity, medium density"),
    ("4A", "medium", "high",   None,  "low sensitivity",
     ["moisture", "scalp health"], ["standard_care", "seal_moisture"],
     "Medium porosity, high density"),
    ("4B", "high",   "high",   "low", "high sensitivity",
     ["length retention", "definition"], ["seal_moisture", "strengthen", "frizz_control"],
     "High porosity, low elasticity"),
    ("4C", "high",   "high",   "low", "high sensitivity",
     ["moisture retention", "breakage prevention"], ["seal_moisture", "strengthen", "protective_styling"],
     "High porosity, low elasticity"),
]

PROFILES = {}
for texture_type, porosity, density, elasticity, humidity_response, hair_goals, routine_flags, description in _PROFILE_SPECS:
    label = resolve_texture_modifiers(texture_type).label
    key = f"{label} ({texture_type}) — {description}"
    PROFILES[key] = ProfileState(
        texture_type=texture_type, texture_label=label,
        porosity=porosity, density=density, elasticity=elasticity,
        humidity_response=humidity_response,
        hair_goals=hair_goals, routine_flags=routine_flags,
    )

# ---------------------------------------------------------------------------
# Curated scenarios — stakeholder blind test walks through these one at a time
# instead of asking a non-technical reviewer to type a hair concern themselves.
# ---------------------------------------------------------------------------

CURATED_SCENARIOS = [
    {"message": "My hair keeps breaking off at the ends and it feels so weak lately, I don't know what's going on."},
    {"message": "I deep condition every single wash day but my hair still feels dry the second it's out of the shower."},
    {"message": "My curls feel waxy and coated no matter how much I rinse, like nothing is actually getting clean."},
    {"message": "My curls look great right after I style them but by lunchtime they're just flat and stringy."},
    {"message": "My scalp has been so itchy and irritated lately, especially after I use my usual gel."},
    {"message": "The second I step outside in this humidity my hair just poofs up and frizzes no matter what I do."},
    {"message": "Honestly my routine has been working really well the last few weeks, just wanted to check if there's anything to tweak."},
    {"message": "I'm so overwhelmed, I have ten products and don't know what order to even use them in anymore, it's too much."},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def save_feedback(entry: dict):
    with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def save_ab_feedback(entry: dict):
    with open(AB_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _experiment_db():
    conn = sqlite3.connect(EXPERIMENT_DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def initialise_experiment_store():
    """A small local revision store; each generated run is immutable."""
    with _experiment_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS test_suites (
                id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS experiment_revisions (
                id TEXT PRIMARY KEY, suite_id TEXT NOT NULL, parent_id TEXT,
                created_at TEXT NOT NULL, input_snapshot TEXT NOT NULL,
                variant_a TEXT NOT NULL, variant_b TEXT NOT NULL,
                FOREIGN KEY(suite_id) REFERENCES test_suites(id)
            );
            CREATE TABLE IF NOT EXISTS experiment_feedback (
                id TEXT PRIMARY KEY, revision_id TEXT NOT NULL, created_at TEXT NOT NULL,
                choice TEXT NOT NULL, note TEXT NOT NULL,
                FOREIGN KEY(revision_id) REFERENCES experiment_revisions(id)
            );
        """)
        conn.execute("INSERT OR IGNORE INTO test_suites VALUES (?, ?, ?)", ("default", "Untitled test suite", datetime.now().isoformat()))


def list_test_suites() -> list[dict]:
    with _experiment_db() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM test_suites ORDER BY created_at DESC")]


def create_test_suite(name: str) -> str:
    suite_id = str(uuid.uuid4())
    with _experiment_db() as conn:
        conn.execute("INSERT INTO test_suites VALUES (?, ?, ?)", (suite_id, name.strip(), datetime.now().isoformat()))
    return suite_id


def save_experiment_revision(suite_id: str, input_snapshot: dict, variant_a: dict, variant_b: dict) -> str:
    revision_id = str(uuid.uuid4())
    with _experiment_db() as conn:
        previous = conn.execute(
            "SELECT id FROM experiment_revisions WHERE suite_id = ? ORDER BY created_at DESC LIMIT 1", (suite_id,)
        ).fetchone()
        conn.execute(
            "INSERT INTO experiment_revisions VALUES (?, ?, ?, ?, ?, ?, ?)",
            (revision_id, suite_id, previous["id"] if previous else None, datetime.now().isoformat(),
             json.dumps(input_snapshot), json.dumps(variant_a), json.dumps(variant_b)),
        )
    return revision_id


def save_experiment_review(revision_id: str, choice: str, note: str):
    with _experiment_db() as conn:
        conn.execute("INSERT INTO experiment_feedback VALUES (?, ?, ?, ?, ?)",
                     (str(uuid.uuid4()), revision_id, datetime.now().isoformat(), choice, note))


def load_experiment_revisions(suite_id: str, limit: int = 20) -> list[dict]:
    with _experiment_db() as conn:
        rows = conn.execute("""
            SELECT r.*, f.choice, f.note, f.created_at AS reviewed_at
            FROM experiment_revisions r
            LEFT JOIN experiment_feedback f ON f.revision_id = r.id
            WHERE r.suite_id = ? ORDER BY r.created_at DESC LIMIT ?
        """, (suite_id, limit)).fetchall()
    revisions = []
    for row in rows:
        revision = dict(row)
        for key in ("input_snapshot", "variant_a", "variant_b"):
            revision[key] = json.loads(revision[key])
        revisions.append(revision)
    return revisions


def _json_editor(label: str, value, key: str, height: int = 260):
    """Show a response-contributing value as editable JSON and validate it."""
    text = st.text_area(label, value=json.dumps(value, indent=2, default=str), key=key, height=height)
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return value, str(exc)


async def _collect_response(composer_input, overrides=None, temperature=0.1, prompt_override=None):
    parts = []
    async for chunk in compose_response(
        composer_input, overrides=overrides, temperature=temperature, prompt_override=prompt_override
    ):
        if chunk.get("type") == "content":
            parts.append(chunk["content"])
    return "".join(parts)


def _preset_text_editor(label: str, presets: dict, key: str) -> str:
    """A text area seeded from a preset dropdown, freely editable afterwards."""
    preset_names = list(presets.keys())
    preset_key = f"{key}_preset"
    text_key = f"{key}_text"

    if text_key not in st.session_state:
        st.session_state[text_key] = presets[preset_names[0]]

    def _load_preset():
        st.session_state[text_key] = presets[st.session_state[preset_key]]

    st.selectbox(f"{label} — start from preset", preset_names, key=preset_key, on_change=_load_preset)
    st.text_area(label, key=text_key, height=110)
    return st.session_state[text_key]


def _variant_knob(label: str, presets: dict, key_prefix: str):
    """Renders a 'vary this?' toggle. Off = one locked, editable value for both
    variants. On = two independently editable values, one per variant."""
    varied = st.checkbox(f"Vary {label} between A and B?", key=f"{key_prefix}_vary")
    if varied:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**{label} — Variant A**")
            text_a = _preset_text_editor(label, presets, f"{key_prefix}_a")
        with c2:
            st.markdown(f"**{label} — Variant B**")
            text_b = _preset_text_editor(label, presets, f"{key_prefix}_b")
        return text_a, text_b
    else:
        st.markdown(f"**{label} — locked (both variants)**")
        text = _preset_text_editor(label, presets, f"{key_prefix}_locked")
        return text, text


def _variant_text_knob(label: str, default_text: str, key_prefix: str):
    """Like _variant_knob, but for fixed-scaffold sections that have exactly one
    canonical form (no preset menu to pick from) — still fully editable text,
    still supports varying it independently between A and B."""
    varied = st.checkbox(f"Vary {label} between A and B?", key=f"{key_prefix}_vary")
    if varied:
        c1, c2 = st.columns(2)
        with c1:
            text_a = st.text_area(f"{label} — Variant A", value=default_text, key=f"{key_prefix}_a", height=160)
        with c2:
            text_b = st.text_area(f"{label} — Variant B", value=default_text, key=f"{key_prefix}_b", height=160)
        return text_a, text_b
    else:
        text = st.text_area(f"{label} — locked (both variants)", value=default_text, key=f"{key_prefix}_locked", height=160)
        return text, text


def _variant_temperature(key_prefix: str):
    varied = st.checkbox("Vary temperature between A and B?", value=True, key=f"{key_prefix}_vary")
    if varied:
        c1, c2 = st.columns(2)
        temp_a = c1.slider("Temperature — Variant A", 0.0, 1.0, 0.1, 0.05, key=f"{key_prefix}_a")
        temp_b = c2.slider("Temperature — Variant B", 0.0, 1.0, 0.4, 0.05, key=f"{key_prefix}_b")
        return temp_a, temp_b
    else:
        temp = st.slider("Temperature — locked (both variants)", 0.0, 1.0, 0.1, 0.05, key=f"{key_prefix}_locked")
        return temp, temp


def run_async(coro):
    return asyncio.run(coro)


def badge(label: str, value: str, color: str = "#2d2d2d") -> str:
    return (
        f'<span style="background:{color};color:white;padding:2px 10px;'
        f'border-radius:12px;font-size:13px;margin-right:6px">'
        f'<b>{label}</b> {value}</span>'
    )


def insight_card(title: str, value: str, detail: str, accent: str = "#7c4dff"):
    """Plain-language card for stakeholders; technical detail stays available below."""
    st.markdown(
        f'<div class="insight-card" style="border-top-color:{accent}">'
        f'<div class="insight-card-title">{title}</div>'
        f'<div class="insight-card-value">{value}</div>'
        f'<div class="insight-card-detail">{detail}</div></div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

initialise_experiment_store()

st.set_page_config(
    page_title="Emerson Concierge — AI Testing Dashboard",
    page_icon="💇",
    layout="wide",
)

st.markdown("""
<style>
    .block-container { padding-top: 2rem; }
    .stExpander { border: 1px solid #e0e0e0; border-radius: 8px; margin-bottom: 8px; }
    .response-box {
        background: #f9f9f9; border-left: 4px solid #7c4dff;
        padding: 16px 20px; border-radius: 8px;
        font-size: 15px; line-height: 1.7; color: #1a1a1a;
    }
    .signal-active { color: #2e7d32; font-weight: bold; }
    .signal-inactive { color: #aaa; }
    .insight-card {
        min-height: 130px; padding: 16px; background: #fff; border: 1px solid #e7e3ee;
        border-top: 4px solid #7c4dff; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.04);
    }
    .insight-card-title { font-size: 12px; color: #6b6474; text-transform: uppercase; letter-spacing: .04em; }
    .insight-card-value { margin: 9px 0 7px; font-size: 18px; font-weight: 650; color: #261f2f; }
    .insight-card-detail { font-size: 13px; line-height: 1.45; color: #5f5869; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar — Profile & Environment
# ---------------------------------------------------------------------------

with st.sidebar:
    st.image("https://via.placeholder.com/200x60?text=Emerson", use_container_width=True)
    st.title("Test Settings")

    st.subheader("Hair Profile")
    profile_name = st.selectbox("Select a profile", list(PROFILES.keys()))
    profile = PROFILES[profile_name]

    st.caption(f"**Type:** {profile.texture_label} ({profile.texture_type})  \n"
               f"**Porosity:** {profile.porosity}  \n"
               f"**Density:** {profile.density}  \n"
               f"**Elasticity:** {profile.elasticity or 'not set'}")

    st.divider()
    st.subheader("Environment")
    humidity = st.select_slider("Humidity", ["low", "medium", "high"], value="high")
    heat = st.select_slider("Heat stress", ["low", "high"], value="high")
    hard_water = st.toggle("Hard water", value=False)

    env = EnvironmentalContext(
        humidity_level=humidity,
        heat_stress=heat,
        hard_water=hard_water,
        sweat_freq="high" if heat == "high" else "low",
    )

    st.divider()
    st.caption("Feedback is saved locally to `feedback_log.jsonl`")

    st.divider()
    test_mode = st.radio(
        "Mode",
        ["🧪 Full experiment suite", "Normal", "🧑‍🤝‍🧑 Stakeholder blind test"],
        index=0,
    )
    ab_mode = test_mode == "🧪 Full experiment suite"
    stakeholder_mode = test_mode == "🧑‍🤝‍🧑 Stakeholder blind test"

    if ab_mode:
        st.caption(
            "Send a message, then edit the complete pipeline trace and both exact prompts in Step 6. "
            "Every run is saved as a versioned revision."
        )

        st.divider()
        st.subheader("Versioned test suite")
        suites = list_test_suites()
        suite_names = {suite["id"]: suite["name"] for suite in suites}
        active_suite_id = st.selectbox("Save experiments to", list(suite_names), format_func=suite_names.get)
        new_suite_name = st.text_input("New suite name", placeholder="e.g. Humidity-frizz tone tests")
        if st.button("Create test suite", use_container_width=True) and new_suite_name.strip():
            try:
                create_test_suite(new_suite_name)
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("A suite with that name already exists.")
    elif stakeholder_mode:
        st.caption(
            "A blind, one-variable-at-a-time test loop for non-technical reviewers. "
            "Configure the round below, then hand the screen to your reviewer — no "
            "tone/temperature jargon is shown to them. Preferences saved to `tone_ab_log.jsonl`."
        )

        active_suite_id = "default"
    else:
        active_suite_id = "default"


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "feedback_given" not in st.session_state:
    st.session_state.feedback_given = False
if "pending_clarification" not in st.session_state:
    st.session_state.pending_clarification = None
if "shown_product_ids" not in st.session_state:
    st.session_state.shown_product_ids = set()
if "ab_result" not in st.session_state:
    st.session_state.ab_result = None
if "stakeholder_round" not in st.session_state:
    st.session_state.stakeholder_round = None
if "stakeholder_scenario_idx" not in st.session_state:
    st.session_state.stakeholder_scenario_idx = 0
if "stakeholder_tally" not in st.session_state:
    st.session_state.stakeholder_tally = {"a": 0, "b": 0, "tie": 0}
if "stakeholder_current" not in st.session_state:
    st.session_state.stakeholder_current = None
if "session_id" not in st.session_state:
    # Real session id — process_session_signals/log_decision_state persist to Supabase
    # keyed on this, so it must be fresh per conversation to match production behaviour.
    st.session_state.session_id = f"dashboard-{uuid.uuid4()}"
if "user_id" not in st.session_state:
    st.session_state.user_id = "dashboard-test-user"


# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------

st.title("Emerson Concierge — AI Testing Dashboard")
st.caption("Type a hair concern below. The dashboard shows every decision the AI makes before responding.")

with st.expander("Experiment history", expanded=False):
    revisions = load_experiment_revisions(active_suite_id)
    if not revisions:
        st.caption("No revisions in this suite yet. Each Engineer A/B generation creates an immutable revision.")
    for run_index, revision in enumerate(revisions):
        st.markdown(f"**Revision {len(revisions) - run_index}** · {revision['created_at']} · `{revision['id']}`")
        if revision.get("choice"):
            st.success(f"Feedback: {revision['choice']}")
            if revision.get("note"):
                st.caption(revision["note"])
        if run_index + 1 < len(revisions):
            previous = revisions[run_index + 1]
            diff = list(difflib.unified_diff(
                previous["variant_a"]["prompt"].splitlines(), revision["variant_a"]["prompt"].splitlines(),
                fromfile="previous A", tofile="this A", lineterm=""
            ))
            if diff:
                st.code("\n".join(diff[:100]), language="diff")
            else:
                st.caption("No Variant A prompt change from the prior experiment.")
        with st.expander("Recorded input, prompts, and outputs"):
            st.json(revision["input_snapshot"])
            st.text_area("Variant A prompt", revision["variant_a"]["prompt"], disabled=True, key=f"history_prompt_a_{revision['id']}")
            st.text_area("Variant A output", revision["variant_a"]["response"], disabled=True, key=f"history_a_{revision['id']}")
            st.text_area("Variant B prompt", revision["variant_b"]["prompt"], disabled=True, key=f"history_prompt_b_{revision['id']}")
            st.text_area("Variant B output", revision["variant_b"]["response"], disabled=True, key=f"history_b_{revision['id']}")

if ab_mode:
    st.info(
        "Full experiment suite is active. Submit a chat message to generate its trace; "
        "Step 6 then opens the editable signal/intent outputs, resolved composer input, "
        "named prompt blocks, and complete rendered prompts."
    )

# ── Infra reliability banner ────────────────────────────────────────────────
# Session memory (signal history, decision-state progression) depends entirely
# on Supabase with no fallback store. When it's unreachable, the concierge still
# responds — but silently loses cross-turn memory. Surfaced here, not just in
# server logs, so the cost of that gap is visible during a live demo, not just
# to whoever happens to be watching the terminal.
_degraded = get_degraded_events()
if _degraded:
    with st.expander(f"⚠️ Session memory degraded {len(_degraded)}x this run — Supabase unreachable", expanded=True):
        st.error(
            "Signal and decision-state persistence has no fallback store. Every event below is a "
            "turn where the concierge silently lost memory of the conversation so far — decision "
            "states can repeat instead of progressing, and signals mentioned earlier can be forgotten."
        )
        for e in _degraded[-5:]:
            st.caption(f"**{e['source']}** — {e['detail']}")
            st.caption(f"↳ {e['error']}")

if stakeholder_mode:
    # ── Stakeholder blind test ──────────────────────────────────────────────
    st.subheader("🧑‍🤝‍🧑 Stakeholder Blind Test")
    st.caption("Pick which response sounds more like Emerson. No setup needed on your end — just read and choose.")

    with st.expander("⚙️ Round setup (engineer only)", expanded=not st.session_state.stakeholder_round):
        st.caption(
            "Configure exactly one variable to test this round — everything else stays "
            "locked so results aren't confounded by more than one change at a time."
        )
        variable_under_test = st.radio("Variable under test", ["Tone preset", "Temperature"], horizontal=True)

        round_profile_name = st.selectbox("Hair profile (locked for this round)", list(PROFILES.keys()), key="round_profile")
        rc1, rc2, rc3 = st.columns(3)
        round_humidity = rc1.select_slider("Humidity (locked)", ["low", "medium", "high"], value="high", key="round_humidity")
        round_heat = rc2.select_slider("Heat stress (locked)", ["low", "high"], value="high", key="round_heat")
        round_hard_water = rc3.toggle("Hard water (locked)", value=False, key="round_hard_water")

        if variable_under_test == "Tone preset":
            c1, c2, c3 = st.columns(3)
            val_a = c1.selectbox("Variant A tone", TONE_PRESETS, index=0, key="round_tone_a")
            val_b = c2.selectbox("Variant B tone", TONE_PRESETS, index=1, key="round_tone_b")
            locked_temp = c3.slider("Temperature (locked for both)", 0.0, 1.0, 0.1, 0.05, key="round_locked_temp")
            locked_tone = None
        else:
            c1, c2, c3 = st.columns(3)
            val_a = c1.slider("Variant A temperature", 0.0, 1.0, 0.1, 0.05, key="round_temp_a")
            val_b = c2.slider("Variant B temperature", 0.0, 1.0, 0.5, 0.05, key="round_temp_b")
            locked_tone = c3.selectbox("Tone preset (locked for both)", TONE_PRESETS, index=0, key="round_locked_tone")
            locked_temp = None

        if st.button("Start round →", type="primary"):
            st.session_state.stakeholder_round = {
                "variable": variable_under_test,
                "value_a": val_a,
                "value_b": val_b,
                "locked_temp": locked_temp,
                "locked_tone": locked_tone,
                "profile_name": round_profile_name,
                "humidity": round_humidity,
                "heat": round_heat,
                "hard_water": round_hard_water,
            }
            st.session_state.stakeholder_scenario_idx = 0
            st.session_state.stakeholder_tally = {"a": 0, "b": 0, "tie": 0}
            st.session_state.stakeholder_current = None
            st.rerun()

    round_cfg = st.session_state.stakeholder_round

    if not round_cfg:
        st.info("Configure a round above to begin.")
    else:
        idx = st.session_state.stakeholder_scenario_idx
        st.markdown("---")

        if idx >= len(CURATED_SCENARIOS):
            tally = st.session_state.stakeholder_tally
            st.success(f"Round complete — {len(CURATED_SCENARIOS)} scenarios rated.")
            label_a = round_cfg["value_a"] if round_cfg["variable"] == "Tone preset" else f"temp {round_cfg['value_a']}"
            label_b = round_cfg["value_b"] if round_cfg["variable"] == "Tone preset" else f"temp {round_cfg['value_b']}"
            m1, m2, m3 = st.columns(3)
            m1.metric(f"Preferred: {label_a}", tally["a"])
            m2.metric(f"Preferred: {label_b}", tally["b"])
            m3.metric("Tie / no preference", tally["tie"])
            if st.button("Start a new round"):
                st.session_state.stakeholder_round = None
                st.rerun()
        else:
            st.caption(f"Scenario {idx + 1} of {len(CURATED_SCENARIOS)}")
            scenario = CURATED_SCENARIOS[idx]
            with st.chat_message("user"):
                st.write(scenario["message"])

            current = st.session_state.stakeholder_current
            if current is None or current.get("idx") != idx:
                with st.spinner("Preparing comparison..."):
                    sh_profile = PROFILES[round_cfg["profile_name"]]
                    sh_env = EnvironmentalContext(
                        humidity_level=round_cfg["humidity"],
                        heat_stress=round_cfg["heat"],
                        hard_water=round_cfg["hard_water"],
                        sweat_freq="high" if round_cfg["heat"] == "high" else "low",
                    )
                    sh_messages = [{"role": "user", "content": scenario["message"]}]
                    sh_session_id = f"stakeholder-{uuid.uuid4()}"

                    sh_signals_raw = run_async(process_session_signals("stakeholder-user", sh_session_id, sh_messages))
                    sh_intent = run_async(process_session_intent(sh_messages))
                    sh_signal = SessionSignal(**{
                        k: sh_signals_raw.get(k, False)
                        for k in SessionSignal.model_fields if k in sh_signals_raw
                    })
                    sh_strategy = build_strategy_payload(sh_profile, sh_signal, sh_env, sh_intent, frozenset())
                    sh_delivery = resolve_delivery_plan(sh_strategy.jte_input, sh_strategy.decision_state)

                    sh_products = []
                    if sh_delivery.product_exposure != "hidden":
                        sh_products = run_async(_fetch_candidate_products(
                            sh_strategy, session_signal=sh_signal, shown_product_ids=set()
                        ))

                    sh_composer_input = ResponseComposerInput(
                        strategy_payload=sh_strategy,
                        jte_delivery_plan=sh_delivery,
                        profile_state=sh_profile,
                        env=sh_env,
                        candidate_products=sh_products,
                        recent_messages=sh_messages,
                    )

                    if round_cfg["variable"] == "Tone preset":
                        tone_a_text = _TONE_INSTRUCTIONS[round_cfg["value_a"]]
                        tone_b_text = _TONE_INSTRUCTIONS[round_cfg["value_b"]]
                        temp_a = temp_b = round_cfg["locked_temp"]
                    else:
                        tone_a_text = tone_b_text = _TONE_INSTRUCTIONS[round_cfg["locked_tone"]]
                        temp_a, temp_b = round_cfg["value_a"], round_cfg["value_b"]

                    resp_a = run_async(_collect_response(
                        sh_composer_input, {"tone_instruction": tone_a_text}, temp_a))
                    resp_b = run_async(_collect_response(
                        sh_composer_input, {"tone_instruction": tone_b_text}, temp_b))

                    # Randomise which side "A"/"B" lands on so position never carries signal.
                    flip = random.random() < 0.5
                    left_response, right_response = (resp_b, resp_a) if flip else (resp_a, resp_b)

                    st.session_state.stakeholder_current = {
                        "idx": idx,
                        "decision_state": sh_strategy.decision_state,
                        "left": left_response,
                        "right": right_response,
                        "left_is_a": not flip,
                    }
                current = st.session_state.stakeholder_current

            col_l, col_r = st.columns(2)
            with col_l:
                st.caption("Response A")
                st.markdown(f'<div class="response-box">{current["left"]}</div>', unsafe_allow_html=True)
            with col_r:
                st.caption("Response B")
                st.markdown(f'<div class="response-box">{current["right"]}</div>', unsafe_allow_html=True)

            st.markdown("**Which one sounds more like Emerson?**")

            def _record_stakeholder_choice(side: str):
                if side == "tie":
                    actual = "tie"
                elif side == "left":
                    actual = "a" if current["left_is_a"] else "b"
                else:
                    actual = "b" if current["left_is_a"] else "a"

                st.session_state.stakeholder_tally[actual] += 1
                save_ab_feedback({
                    "timestamp":      datetime.now().isoformat(),
                    "mode":           "stakeholder_blind",
                    "round_variable": round_cfg["variable"],
                    "value_a":        round_cfg["value_a"],
                    "value_b":        round_cfg["value_b"],
                    "scenario":       scenario["message"],
                    "decision_state": current["decision_state"],
                    "shown_left":     "a" if current["left_is_a"] else "b",
                    "preferred":      actual,
                })
                st.session_state.stakeholder_scenario_idx += 1
                st.session_state.stakeholder_current = None

            p1, p2, p3 = st.columns(3)
            if p1.button("👈 A", use_container_width=True):
                _record_stakeholder_choice("left")
                st.rerun()
            if p2.button("🤝 Can't tell", use_container_width=True):
                _record_stakeholder_choice("tie")
                st.rerun()
            if p3.button("B 👉", use_container_width=True):
                _record_stakeholder_choice("right")
                st.rerun()

else:
    # ── Normal / Engineer A/B chat flow ─────────────────────────────────────

    # Chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # ── Clarification MCQ (shown when signal detection was inconclusive) ──────────
    # When answered, this feeds `user_input` directly into the Steps 1-6 block below —
    # it must NOT just append to history and rerun, since that block only runs off
    # `user_input`, and st.chat_input() returns None on a rerun nothing was typed into.
    user_input = None

    if st.session_state.pending_clarification:
        clar = st.session_state.pending_clarification
        with st.chat_message("assistant"):
            st.markdown(f"**{clar['question']}**")
            option_labels = [opt["label"] for opt in clar["options"]]
            selected = st.radio("", option_labels, key="clarification_radio", label_visibility="collapsed")
            if st.button("That sounds right →", type="primary"):
                st.session_state.pending_clarification = None
                st.session_state.pop("clarification_radio", None)  # avoid stale option on the next clarification
                user_input = selected
    else:
        # Input — hidden while a clarification is pending so the user answers that first
        user_input = st.chat_input("Type a hair concern...")

    active_turn = user_input or (st.session_state.get("active_experiment_turn") if ab_mode else None)
    if active_turn:
        # Streamlit reruns on every button click. Keep this turn alive while a
        # stakeholder edits controls, generates variants, and gives feedback.
        if user_input:
            st.session_state.messages.append({"role": "user", "content": user_input})
            st.session_state.active_experiment_turn = user_input
            st.session_state.feedback_given = False

            with st.chat_message("user"):
                st.write(user_input)

        messages = st.session_state.messages.copy()

        # ── Step 1: Signal Detection ──────────────────────────────────────────
        with st.expander("🔬 Step 1 — What is happening to the hair?", expanded=True):
            with st.spinner("Detecting hair signals..."):
                signals_raw = run_async(process_session_signals(
                    st.session_state.user_id, st.session_state.session_id, messages
                ))

            signal_map = {
                "breakage_active":    "Active breakage / shedding",
                "absorption_blocked": "Moisture not absorbing",
                "buildup_present":    "Product / sebum buildup",
                "hold_loss":          "Curls losing definition",
                "coated_feel":        "Waxy or coated texture",
                "scalp_sensitivity":  "Scalp sensitivity / irritation",
            }

            cols = st.columns(len(signal_map))
            for col, (key, label) in zip(cols, signal_map.items()):
                active = signals_raw.get(key, False)
                col.metric(label, "✓ Yes" if active else "· No",
                           delta_color="off")

            if signals_raw.get("evidence_quote"):
                st.info(f"**Evidence:** \"{signals_raw['evidence_quote']}\"")

            c1, c2 = st.columns(2)
            c1.caption(f"Confidence: {signals_raw.get('confidence_score', 0):.0%}")
            c2.caption(f"Fallback used: {'yes' if signals_raw.get('fallback_used') else 'no'}")

            if ab_mode:
                edited_signals, signals_error = _json_editor(
                    "Signal detector output (JSON)", signals_raw, f"trace_signals_{len(messages)}", height=220
                )
                if signals_error:
                    st.error(f"Signal JSON is invalid: {signals_error}")
                elif st.checkbox("Use edited signal output downstream", key=f"use_trace_signals_{len(messages)}"):
                    signals_raw = edited_signals

        # ── Clarification gate ────────────────────────────────────────────────
        _no_signals   = not any(signals_raw.get(k) for k in SIGNAL_NAMES)
        _low_conf     = signals_raw.get("confidence_score", 0) < 0.5
        if _no_signals and _low_conf:
            from app.services.clarification.clarification_generator import generate_clarification
            with st.spinner("Generating clarifying question..."):
                _clar = run_async(generate_clarification(messages))
            st.session_state.pending_clarification = _clar.model_dump()
            st.rerun()

        # ── Step 2: Intent Detection ──────────────────────────────────────────
        # Computed once via the same service the real pipeline uses (process_session_intent),
        # instead of a separate detect_intent() call just for display — that was a second,
        # redundant LLM call producing a value never actually fed into the strategy below.
        with st.expander("🧠 Step 2 — How is the user engaging?", expanded=True):
            with st.spinner("Analysing conversation tone..."):
                session_intent = run_async(process_session_intent(messages))

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Journey state",    session_intent.journey_state)
            c2.metric("Intent clarity",   session_intent.intent_clarity)
            c3.metric("Confidence",       session_intent.confidence_level)
            c4.metric("Friction",         session_intent.friction_score)
            c5.metric("Emotion",          session_intent.emotional_state)

            if ab_mode:
                intent_dump = session_intent.model_dump(mode="json")
                edited_intent, intent_error = _json_editor(
                    "Intent detector output (JSON)", intent_dump, f"trace_intent_{len(messages)}", height=220
                )
                if intent_error:
                    st.error(f"Intent JSON is invalid: {intent_error}")
                elif st.checkbox("Use edited intent output downstream", key=f"use_trace_intent_{len(messages)}"):
                    try:
                        session_intent = type(session_intent).model_validate(edited_intent)
                    except Exception as exc:
                        st.error(f"Edited intent cannot be used: {exc}")

        # ── Step 3: Decision Engine ───────────────────────────────────────────
        with st.expander("⚙️ Step 3 — What does the hair actually need?", expanded=True):
            session_signal = SessionSignal(**{
                k: signals_raw.get(k, False)
                for k in SessionSignal.model_fields if k in signals_raw
            })
            delivered_states = get_session_decision_states(st.session_state.session_id)
            strategy = build_strategy_payload(profile, session_signal, env, session_intent, frozenset(delivered_states))
            log_decision_state(st.session_state.user_id, st.session_state.session_id, strategy.decision_state)

            ds = strategy.decision_state or "balanced_routine_first"
            colour_map = {
                "repair_first":                 "#c62828",
                "reset_first":                  "#e65100",
                "scalp_calm_first":             "#ad1457",
                "climate_control_first":        "#0277bd",
                "hold_and_definition_first":    "#1565c0",
                "reinforce_current_routine":    "#2e7d32",
                "simplify_and_reduce_friction": "#6a1b9a",
                "balanced_routine_first":       "#4caf50",
            }
            st.markdown(
                f'<div style="font-size:20px;font-weight:bold;color:{colour_map.get(ds,"#333")};'
                f'margin-bottom:12px">Decision State: {ds.replace("_", " ").upper()}</div>',
                unsafe_allow_html=True
            )

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Routine plan**")
                st.write(f"Steps: {strategy.routine_constraints.step_count_target}")
                st.write("Must include: " + ", ".join(strategy.routine_constraints.mandatory_steps))
                st.write("Must avoid: " + (", ".join(strategy.routine_constraints.forbidden_steps) or "none"))
            with c2:
                st.markdown("**Product filters**")
                st.write("Required: " + (", ".join(strategy.product_filters.required_flags) or "none"))
                st.write("Forbidden: " + (", ".join(strategy.product_filters.forbidden_flags) or "none"))
                st.write(f"Hold level: {strategy.product_filters.ideal_hold_level or 'any'}")
                st.write(f"Porosity match: {strategy.product_filters.porosity_match or 'any'}")

            mods = strategy.product_filters.texture_modifiers
            if mods:
                st.markdown("**Texture modifiers**")
                st.write(
                    f"{mods.label} ({profile.texture_type}) — "
                    f"shrinkage: {mods.shrinkage_factor}, fragility: {mods.fragility_index}, "
                    f"definition difficulty: {mods.definition_difficulty}"
                )

                styling_applies = ds not in _STRUCTURAL_PRIORITY_STATES
                effects = []
                if mods.fragility_index == "high":
                    effects.append("Fragility high → avoiding heavy manipulation, favouring protein/strengthening products")
                if mods.shrinkage_factor == "high":
                    effects.append(
                        "Shrinkage high → added an elongation/stretching step"
                        if styling_applies else
                        "Shrinkage high → elongation step skipped (a more urgent concern owns the routine this turn)"
                    )
                if mods.definition_difficulty == "high":
                    effects.append(
                        "Definition difficulty high → added a styling/cast step and raised target hold to strong"
                        if styling_applies else
                        "Definition difficulty high → styling step and hold bump skipped (a more urgent concern owns the routine this turn)"
                    )
                if effects:
                    for e in effects:
                        st.caption(f"• {e}")
                else:
                    st.caption("No high-impact traits for this texture — standard handling applies.")

        # ── Step 4: JTE ───────────────────────────────────────────────────────
        with st.expander("🎯 Step 4 — How should we deliver this?", expanded=True):
            delivery = resolve_delivery_plan(strategy.jte_input, strategy.decision_state)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Readiness",       f"{delivery.readiness_band} ({delivery.readiness_score})")
            c2.metric("Response mode",   delivery.response_mode)
            c3.metric("Depth",           delivery.response_depth)
            c4.metric("Tone",            delivery.tone_profile.replace("_", " "))

            c1, c2, c3 = st.columns(3)
            c1.metric("CTA pressure",    delivery.cta_pressure)
            c2.metric("Product exposure", delivery.product_exposure)
            c3.metric("Ask strategy",    delivery.ask_strategy.replace("_", " "))

            _structure_map = {
                "educate":      "Observation → Interpretation → Recommendation → Why",
                "troubleshoot": "What is Happening → Most Likely Cause → What to Change First → What to Monitor",
                "convert":      "Problem → Desired Outcome → Why Product Fits → How to Use",
                "reassure":     "What is Working → Evidence → Why Consistency Matters → Optional Optimisation",
                "compare":      "Observation → Options & Trade-offs → Recommendation → Why",
            }
            st.caption(f"**Response structure:** {_structure_map.get(delivery.response_mode, 'Standard')}")

        # ── Step 5: Products ──────────────────────────────────────────────────
        candidate_products = []
        with st.expander("🛍️ Step 5 — Product search", expanded=True):
            if delivery.product_exposure == "hidden":
                st.info("Products hidden — JTE says build trust first before surfacing recommendations.")
            else:
                with st.spinner("Searching Emerson catalogue..."):
                    # Calls the real pipeline function — same query building (incl. active
                    # signal terms and texture modifier terms), reranking, and freshness
                    # logic a real user would get, instead of a hand-rolled reimplementation.
                    candidate_products = run_async(_fetch_candidate_products(
                        strategy, session_signal=session_signal, shown_product_ids=st.session_state.shown_product_ids
                    ))

                    for p in candidate_products:
                        st.session_state.shown_product_ids.add(p.get("id"))

                if candidate_products:
                    for p in candidate_products:
                        st.markdown(f"- {p.get('content', '')[:120]}")
                else:
                    st.warning("No matching products found in catalogue.")

        # ── Step 6: Response ──────────────────────────────────────────────────
        st.markdown("---")

        composer_input = ResponseComposerInput(
            strategy_payload=strategy,
            jte_delivery_plan=delivery,
            profile_state=profile,
            env=env,
            candidate_products=candidate_products,
            recent_messages=messages[-6:],
        )

        if ab_mode:
            # ── Step 6 (A/B): stakeholder-facing experiment workspace ───────────
            st.subheader("🧪 Step 6 — Experiment workspace")
            st.caption(
                "Start with the four cards below. They tell the story of this turn in plain language; "
                "the editable controls and complete technical trace sit underneath."
            )

            active_signal_names = [signal_map[key] for key in signal_map if signals_raw.get(key)]
            summary_cols = st.columns(4)
            with summary_cols[0]:
                insight_card("What we heard", active_turn[:62] + ("…" if len(active_turn) > 62 else ""),
                             ", ".join(active_signal_names) if active_signal_names else "No strong hair signal was detected.", "#7c4dff")
            with summary_cols[1]:
                insight_card("What matters most", ds.replace("_", " ").title(),
                             "This is the concern the system chose to address first.", "#e06c75")
            with summary_cols[2]:
                insight_card("How it will respond", delivery.response_mode.title(),
                             f"{delivery.response_depth.title()} detail · {delivery.tone_profile.replace('_', ' ').title()} tone", "#1f8a70")
            with summary_cols[3]:
                product_summary = "No products will be shown." if delivery.product_exposure == "hidden" else f"{len(candidate_products)} relevant product options found."
                insight_card("Product role", delivery.product_exposure.replace("_", " ").title(), product_summary, "#e09f3e")

            turn_key = len(messages)  # identifies this turn, so a stale result from a prior turn never renders

            # The complete resolved input to the LLM stage, after all upstream
            # pipeline work. Editing this is local to the experiment only.
            input_snapshot = composer_input.model_dump(mode="json")
            with st.expander("Advanced: edit the complete pipeline trace", expanded=False):
                st.caption("For detailed investigation: this includes the resolved strategy, delivery plan, profile, environment, retrieved products, and conversation. The signal and intent outputs in Steps 1–2 are their provenance.")
                edited_snapshot, snapshot_error = _json_editor(
                    "Response-composer input (JSON)", input_snapshot, f"trace_input_{turn_key}", height=460
                )
                use_edited_input = st.checkbox("Use this edited input for both variants", key=f"use_trace_input_{turn_key}")
                if snapshot_error:
                    st.error(f"Input JSON is invalid: {snapshot_error}")
            experiment_input = composer_input
            if use_edited_input and not snapshot_error:
                try:
                    experiment_input = ResponseComposerInput.model_validate(edited_snapshot)
                except Exception as exc:
                    st.error(f"Edited input cannot be used: {exc}")

            st.markdown("##### What should we change?")
            st.caption("Keep a control locked when you do not want it to differ between A and B. Turn on “Vary” only for the idea you are testing.")
            with st.expander("Tone", expanded=True):
                tone_a_text, tone_b_text = _variant_knob("Tone", _TONE_INSTRUCTIONS, "ab_tone")
            with st.expander("Temperature", expanded=True):
                temp_a, temp_b = _variant_temperature("ab_temp")
            with st.expander("Response depth"):
                depth_a_text, depth_b_text = _variant_knob("Depth", _DEPTH_INSTRUCTIONS, "ab_depth")
            with st.expander("CTA pressure"):
                cta_a_text, cta_b_text = _variant_knob("CTA pressure", _CTA_INSTRUCTIONS, "ab_cta")
            with st.expander("Product exposure"):
                exposure_a_text, exposure_b_text = _variant_knob("Product exposure", _EXPOSURE_INSTRUCTIONS, "ab_exposure")
            with st.expander("Response structure"):
                structure_a_text, structure_b_text = _variant_knob("Response structure", _RESPONSE_STRUCTURES, "ab_structure")

            st.markdown("##### Fixed scaffold (previously locked as the control — now editable too)")
            with st.expander("Brand framing"):
                brand_a_text, brand_b_text = _variant_text_knob(
                    "Brand framing", FIXED_SECTION_DEFAULTS["brand_framing"], "ab_brand")
            with st.expander("Emerson Chat Voice (authority / resolution-test rule)"):
                voice_a_text, voice_b_text = _variant_text_knob(
                    "Voice block", FIXED_SECTION_DEFAULTS["voice_block"], "ab_voice")
            with st.expander("Curl philosophy"):
                philosophy_a_text, philosophy_b_text = _variant_text_knob(
                    "Philosophy block", FIXED_SECTION_DEFAULTS["philosophy_block"], "ab_philosophy")
            with st.expander("Diagnostic reasoning"):
                reasoning_a_text, reasoning_b_text = _variant_text_knob(
                    "Diagnostic reasoning block", FIXED_SECTION_DEFAULTS["diagnostic_reasoning_block"], "ab_reasoning")
            with st.expander("Task footer"):
                footer_a_text, footer_b_text = _variant_text_knob(
                    "Task footer", FIXED_SECTION_DEFAULTS["task_footer"], "ab_footer")

            preview_overrides_a = {
                "tone_instruction": tone_a_text, "depth_instruction": depth_a_text, "cta_instruction": cta_a_text,
                "exposure_instruction": exposure_a_text, "response_structure": structure_a_text,
                "brand_framing": brand_a_text, "voice_block": voice_a_text, "philosophy_block": philosophy_a_text,
                "diagnostic_reasoning_block": reasoning_a_text, "task_footer": footer_a_text,
            }
            preview_overrides_b = {
                "tone_instruction": tone_b_text, "depth_instruction": depth_b_text, "cta_instruction": cta_b_text,
                "exposure_instruction": exposure_b_text, "response_structure": structure_b_text,
                "brand_framing": brand_b_text, "voice_block": voice_b_text, "philosophy_block": philosophy_b_text,
                "diagnostic_reasoning_block": reasoning_b_text, "task_footer": footer_b_text,
            }
            with st.expander("Advanced: the exact instruction sent to the model", expanded=False):
                st.caption("This is the final assembled prompt. Edit it only when you want to test wording that does not fit one of the simpler controls above.")
                prompt_a = st.text_area("Variant A exact model prompt", value=render_response_prompt(experiment_input, preview_overrides_a), key=f"prompt_a_{turn_key}", height=560)
                prompt_b = st.text_area("Variant B exact model prompt", value=render_response_prompt(experiment_input, preview_overrides_b), key=f"prompt_b_{turn_key}", height=560)

            if st.button("Generate both →", type="primary"):
                overrides_a = {
                    "tone_instruction": tone_a_text, "depth_instruction": depth_a_text,
                    "cta_instruction": cta_a_text, "exposure_instruction": exposure_a_text,
                    "response_structure": structure_a_text, "brand_framing": brand_a_text,
                    "voice_block": voice_a_text, "philosophy_block": philosophy_a_text,
                    "diagnostic_reasoning_block": reasoning_a_text, "task_footer": footer_a_text,
                }
                overrides_b = {
                    "tone_instruction": tone_b_text, "depth_instruction": depth_b_text,
                    "cta_instruction": cta_b_text, "exposure_instruction": exposure_b_text,
                    "response_structure": structure_b_text, "brand_framing": brand_b_text,
                    "voice_block": voice_b_text, "philosophy_block": philosophy_b_text,
                    "diagnostic_reasoning_block": reasoning_b_text, "task_footer": footer_b_text,
                }
                with st.spinner("Composing variant A..."):
                    resp_a = run_async(_collect_response(experiment_input, overrides_a, temp_a, prompt_a))
                with st.spinner("Composing variant B..."):
                    resp_b = run_async(_collect_response(experiment_input, overrides_b, temp_b, prompt_b))
                st.session_state.ab_result = {
                    "turn_key": turn_key,
                    "input_snapshot": experiment_input.model_dump(mode="json"),
                    "a": {"overrides": overrides_a, "temperature": temp_a, "prompt": prompt_a, "response": resp_a},
                    "b": {"overrides": overrides_b, "temperature": temp_b, "prompt": prompt_b, "response": resp_b},
                    "resolved": False,
                }
                st.session_state.ab_result["experiment_id"] = save_experiment_revision(
                    active_suite_id, st.session_state.ab_result["input_snapshot"],
                    st.session_state.ab_result["a"], st.session_state.ab_result["b"],
                )

            result = st.session_state.ab_result
            if result and result.get("turn_key") == turn_key:
                col_a, col_b = st.columns(2)
                with col_a:
                    st.caption(f"**Variant A** · temp {result['a']['temperature']}")
                    st.markdown(f'<div class="response-box">{result["a"]["response"]}</div>', unsafe_allow_html=True)
                with col_b:
                    st.caption(f"**Variant B** · temp {result['b']['temperature']}")
                    st.markdown(f'<div class="response-box">{result["b"]["response"]}</div>', unsafe_allow_html=True)

                st.markdown("**Which one?**")

                def _resolve_ab(choice: str, chosen_response: str):
                    save_ab_feedback({
                        "timestamp":      datetime.now().isoformat(),
                        "profile":        profile_name,
                        "user_input":     active_turn,
                        "decision_state": ds,
                        "variant_a":      result["a"],
                        "variant_b":      result["b"],
                        "preferred":      choice,
                    })
                    save_experiment_review(
                        result["experiment_id"], choice, st.session_state.get("experiment_feedback_note", "")
                    )
                    st.session_state.messages.append({"role": "assistant", "content": chosen_response})
                    st.session_state.ab_result["resolved"] = True
                    st.session_state.pop("active_experiment_turn", None)

                if not result.get("resolved"):
                    st.text_area("Experiment feedback (what changed in tone, and why?)", key="experiment_feedback_note")
                    p1, p2, p3 = st.columns(3)
                    if p1.button("👈 Prefer A", use_container_width=True):
                        _resolve_ab("a", result["a"]["response"])
                        st.rerun()
                    if p2.button("🤝 Tie", use_container_width=True):
                        _resolve_ab("tie", result["a"]["response"])
                        st.rerun()
                    if p3.button("Prefer B 👉", use_container_width=True):
                        _resolve_ab("b", result["b"]["response"])
                        st.rerun()
                else:
                    st.success("Preference saved — winning response added to the conversation.")

        else:
            # ── Step 6 (normal): Single response ────────────────────────────────
            st.subheader("💬 Emerson's Response")

            def sync_stream():
                async def collect():
                    parts = []
                    async for chunk in compose_response(composer_input):
                        if chunk.get("type") == "content":
                            parts.append(chunk["content"])
                    return "".join(parts)
                return asyncio.run(collect())

            with st.spinner("Composing response..."):
                full_response = sync_stream()

            st.markdown(
                f'<div class="response-box">{full_response}</div>',
                unsafe_allow_html=True
            )

            st.session_state.messages.append({"role": "assistant", "content": full_response})
            st.session_state.last_result = {
                "timestamp":      datetime.now().isoformat(),
                "profile":        profile_name,
                "user_input":     active_turn,
                "decision_state": ds,
                "response_mode":  delivery.response_mode,
                "response":       full_response,
            }

            # ── Feedback ─────────────────────────────────────────────────────
            st.markdown("---")
            st.subheader("📝 Was this response good?")

            col1, col2, col3 = st.columns([1, 1, 4])

            if col1.button("👍  Yes", use_container_width=True):
                entry = {**st.session_state.last_result, "rating": "positive", "note": ""}
                save_feedback(entry)
                st.session_state.feedback_given = True
                st.success("Thanks — feedback saved.")

            if col2.button("👎  No", use_container_width=True):
                st.session_state.feedback_given = "negative"

            if st.session_state.feedback_given == "negative":
                note = st.text_area("What was wrong with the response?", key="feedback_note")
                if st.button("Submit feedback"):
                    entry = {**st.session_state.last_result, "rating": "negative", "note": note}
                    save_feedback(entry)
                    st.session_state.feedback_given = True
                    st.success("Thanks — feedback saved.")

    # ── Reset conversation ─────────────────────────────────────────────────────
    if st.session_state.messages:
        if st.button("🔄 Start new conversation"):
            st.session_state.messages = []
            st.session_state.last_result = None
            st.session_state.feedback_given = False
            st.session_state.shown_product_ids = set()
            st.session_state.ab_result = None
            st.session_state.pop("active_experiment_turn", None)
            # New session id — otherwise signal/decision-state history from this test
            # conversation would keep bleeding into the "new" one via Supabase.
            st.session_state.session_id = f"dashboard-{uuid.uuid4()}"
            st.rerun()
