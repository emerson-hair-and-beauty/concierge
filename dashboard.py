"""
Emerson Concierge — Stakeholder Testing Dashboard
Run: streamlit run dashboard.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime

import streamlit as st

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.services.decision_state.models import (
    ProfileState, EnvironmentalContext, SessionSignal, ResponseComposerInput
)
from app.services.session_signal.signal_detector import detect_signals
from app.services.session_intent.intent_detector import detect_intent
from app.services.decision_state.decision_engine import build_strategy_payload
from app.services.decision_state.jte import resolve_delivery_plan
from app.services.session_intent.session_intent_service import process_session_intent
from app.services.decision_state.response_composer import compose_response
from app.agents.recommendation.lib.knowledge_base.query_products import query_products
from app.services.decision_state.pipeline import (
    _PRODUCT_QUERY_TEMPLATES, _POROSITY_CONTEXT, _TEXTURE_CONTEXT
)

FEEDBACK_FILE = os.path.join(os.path.dirname(__file__), "feedback_log.jsonl")

# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

PROFILES = {
    "Dense Coils (4B) — High porosity, low elasticity": ProfileState(
        texture_type="4B", texture_label="Dense Coils",
        porosity="high", density="high", elasticity="low",
        humidity_response="high sensitivity",
        hair_goals=["length retention", "definition"],
        routine_flags=["seal_moisture", "strengthen", "frizz_control"],
    ),
    "Tight Curls (3C) — Low porosity, medium density": ProfileState(
        texture_type="3C", texture_label="Tight Curls",
        porosity="low", density="medium",
        humidity_response="moderate sensitivity",
        hair_goals=["definition", "moisture"],
        routine_flags=["frizz_control", "avoid_butters", "use_heat_for_masks"],
    ),
    "Loose Coils (4A) — Medium porosity, high density": ProfileState(
        texture_type="4A", texture_label="Loose Coils",
        porosity="medium", density="high",
        humidity_response="low sensitivity",
        hair_goals=["moisture", "scalp health"],
        routine_flags=["standard_care", "seal_moisture"],
    ),
    "Defined Curls (3B) — Medium porosity, medium density": ProfileState(
        texture_type="3B", texture_label="Defined Curls",
        porosity="medium", density="medium",
        humidity_response="moderate sensitivity",
        hair_goals=["definition", "frizz control"],
        routine_flags=["frizz_control", "balanced_volume"],
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def save_feedback(entry: dict):
    with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


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


# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------

st.title("Emerson Concierge — AI Testing Dashboard")
st.caption("Type a hair concern below. The dashboard shows every decision the AI makes before responding.")

# Chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# ── Clarification MCQ (shown when signal detection was inconclusive) ──────────
if st.session_state.pending_clarification:
    clar = st.session_state.pending_clarification
    with st.chat_message("assistant"):
        st.markdown(f"**{clar['question']}**")
        option_labels = [opt["label"] for opt in clar["options"]]
        selected = st.radio("", option_labels, key="clarification_radio", label_visibility="collapsed")
        if st.button("That sounds right →", type="primary"):
            st.session_state.messages.append({"role": "user", "content": selected})
            st.session_state.pending_clarification = None
            st.rerun()
    st.stop()

# Input
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
            signals_raw = run_async(detect_signals(messages))

        signal_map = {
            "breakage_active":    "Active breakage / shedding",
            "absorption_blocked": "Moisture not absorbing",
            "buildup_present":    "Product / sebum buildup",
            "hold_loss":          "Curls losing definition",
            "coated_feel":        "Waxy or coated texture",
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
    _signal_keys = ["breakage_active", "absorption_blocked", "buildup_present", "hold_loss", "coated_feel"]
    _no_signals   = not any(signals_raw.get(k) for k in _signal_keys)
    _low_conf     = signals_raw.get("confidence_score", 0) < 0.5
    if _no_signals and _low_conf:
        from app.services.clarification.clarification_generator import generate_clarification
        with st.spinner("Generating clarifying question..."):
            _clar = run_async(generate_clarification(messages))
        st.session_state.pending_clarification = _clar.model_dump()
        st.rerun()

    # ── Step 2: Intent Detection ──────────────────────────────────────────
    with st.expander("🧠 Step 2 — How is the user engaging?", expanded=True):
        with st.spinner("Analysing conversation tone..."):
            intent_raw = run_async(detect_intent(messages))

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Journey state",    intent_raw["journey_state"])
        c2.metric("Intent clarity",   intent_raw["intent_clarity"])
        c3.metric("Confidence",       intent_raw["confidence_level"])
        c4.metric("Friction",         intent_raw["friction_score"])
        c5.metric("Emotion",          intent_raw["emotional_state"])

        if intent_raw.get("reasoning"):
            st.caption(f"**Reasoning:** {intent_raw['reasoning']}")

    # ── Step 3: Decision Engine ───────────────────────────────────────────
    with st.expander("⚙️ Step 3 — What does the hair actually need?", expanded=True):
        session_signal = SessionSignal(**{
            k: signals_raw.get(k, False)
            for k in SessionSignal.model_fields if k in signals_raw
        })
        session_intent = run_async(process_session_intent(messages))
        strategy = build_strategy_payload(profile, session_signal, env, session_intent)

        ds = strategy.decision_state or "balanced_routine_first"
        colour_map = {
            "repair_first":         "#c62828",
            "reset_first":          "#e65100",
            "hold_first":           "#1565c0",
            "simplify_friction":    "#6a1b9a",
            "balanced_routine_first": "#2e7d32",
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

    # ── Step 5: Products ──────────────────────────────────────────────────
    candidate_products = []
    with st.expander("🛍️ Step 5 — Product search", expanded=True):
        if delivery.product_exposure == "hidden":
            st.info("Products hidden — JTE says build trust first before surfacing recommendations.")
        else:
            with st.spinner("Searching Emerson catalogue..."):
                base = _PRODUCT_QUERY_TEMPLATES.get(ds, "curl care moisturiser")
                porosity_ctx = _POROSITY_CONTEXT.get(strategy.product_filters.porosity_match or "", "")
                texture_ctx = _TEXTURE_CONTEXT.get(strategy.product_filters.texture_match or "", "")
                query = f"{base} {porosity_ctx} {texture_ctx}".strip()
                result = run_async(query_products(query, top_k=3))
                candidate_products = result.get("products", [])

            if candidate_products:
                for p in candidate_products:
                    st.markdown(f"- {p.get('content', '')[:120]}")
            else:
                st.warning("No matching products found in catalogue.")

    # ── Step 6: Response ──────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("💬 Emerson's Response")

    composer_input = ResponseComposerInput(
        strategy_payload=strategy,
        jte_delivery_plan=delivery,
        profile_state=profile,
        candidate_products=candidate_products,
        recent_messages=messages[-6:],
    )

    response_placeholder = st.empty()
    full_response = ""

    async def stream_response():
        async for chunk in compose_response(composer_input):
            if chunk.get("type") == "content":
                yield chunk["content"]

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

    # ── Feedback ──────────────────────────────────────────────────────────
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
        st.rerun()
