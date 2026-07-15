"""
Emerson Concierge — Stakeholder Testing Dashboard
Run: streamlit run dashboard.py
"""

import asyncio
import json
import os
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
from app.services.decision_state.response_composer import compose_response, _TONE_INSTRUCTIONS
from app.services.decision_state.pipeline import _fetch_candidate_products
from app.services.decision_state.texture_modifiers import resolve_texture_modifiers
from app.services.resilience import get_degraded_events

FEEDBACK_FILE = os.path.join(os.path.dirname(__file__), "feedback_log.jsonl")
AB_LOG_FILE = os.path.join(os.path.dirname(__file__), "tone_ab_log.jsonl")
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
# Helpers
# ---------------------------------------------------------------------------

def save_feedback(entry: dict):
    with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def save_ab_feedback(entry: dict):
    with open(AB_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


async def _collect_response(composer_input, tone_override, temperature):
    parts = []
    async for chunk in compose_response(composer_input, tone_override=tone_override, temperature=temperature):
        if chunk.get("type") == "content":
            parts.append(chunk["content"])
    return "".join(parts)


def run_async(coro):
    return asyncio.run(coro)


def badge(label: str, value: str, color: str = "#2d2d2d") -> str:
    return (
        f'<span style="background:{color};color:white;padding:2px 10px;'
        f'border-radius:12px;font-size:13px;margin-right:6px">'
        f'<b>{label}</b> {value}</span>'
    )


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

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
    ab_mode = st.toggle("🧪 Tone A/B testing", value=False)
    if ab_mode:
        st.caption(
            "Step 6 becomes a two-column comparison — pick a tone preset and "
            "temperature per side. Preferences saved to `tone_ab_log.jsonl`."
        )


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

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
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
        # ── Step 6 (A/B): Tone comparison ───────────────────────────────────
        st.subheader("🧪 Step 6 — Tone A/B Comparison")

        turn_key = len(messages)  # identifies this turn, so a stale result from a prior turn never renders
        default_idx = TONE_PRESETS.index(delivery.tone_profile) if delivery.tone_profile in TONE_PRESETS else 0

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Variant A**")
            tone_a = st.selectbox("Tone preset", TONE_PRESETS, index=default_idx, key="tone_a")
            temp_a = st.slider("Temperature", 0.0, 1.0, 0.1, 0.05, key="temp_a")
        with col_b:
            st.markdown("**Variant B**")
            tone_b = st.selectbox("Tone preset", TONE_PRESETS, index=(default_idx + 1) % len(TONE_PRESETS), key="tone_b")
            temp_b = st.slider("Temperature", 0.0, 1.0, 0.1, 0.05, key="temp_b")

        if st.button("Generate both →", type="primary"):
            with st.spinner("Composing variant A..."):
                resp_a = run_async(_collect_response(composer_input, _TONE_INSTRUCTIONS[tone_a], temp_a))
            with st.spinner("Composing variant B..."):
                resp_b = run_async(_collect_response(composer_input, _TONE_INSTRUCTIONS[tone_b], temp_b))
            st.session_state.ab_result = {
                "turn_key": turn_key,
                "a": {"tone": tone_a, "temperature": temp_a, "response": resp_a},
                "b": {"tone": tone_b, "temperature": temp_b, "response": resp_b},
                "resolved": False,
            }

        result = st.session_state.ab_result
        if result and result.get("turn_key") == turn_key:
            col_a, col_b = st.columns(2)
            with col_a:
                st.caption(f"**{result['a']['tone'].replace('_', ' ')}** · temp {result['a']['temperature']}")
                st.markdown(f'<div class="response-box">{result["a"]["response"]}</div>', unsafe_allow_html=True)
            with col_b:
                st.caption(f"**{result['b']['tone'].replace('_', ' ')}** · temp {result['b']['temperature']}")
                st.markdown(f'<div class="response-box">{result["b"]["response"]}</div>', unsafe_allow_html=True)

            st.markdown("**Which one?**")

            def _resolve_ab(choice: str, chosen_response: str):
                save_ab_feedback({
                    "timestamp":      datetime.now().isoformat(),
                    "profile":        profile_name,
                    "user_input":     user_input,
                    "decision_state": ds,
                    "variant_a":      result["a"],
                    "variant_b":      result["b"],
                    "preferred":      choice,
                })
                st.session_state.messages.append({"role": "assistant", "content": chosen_response})
                st.session_state.ab_result["resolved"] = True

            if not result.get("resolved"):
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
            "user_input":     user_input,
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
        # New session id — otherwise signal/decision-state history from this test
        # conversation would keep bleeding into the "new" one via Supabase.
        st.session_state.session_id = f"dashboard-{uuid.uuid4()}"
        st.rerun()
