"""
Web Chat Orchestrator - Triage & State Dispatcher
Implements the "Observer-Agent" dual-pass flow:
1. Pass 1: Observer extracts hair traits into a transient session profile.
2. Pass 2: Triage decomposes message and dispatches specialized agents with the profile context.
"""

import json
from typing import List, Dict, Optional, AsyncGenerator
from app.agents.llm_call.llm_call import run_llm_agent
from .discovery_agent import run_discovery
from .faq_agent import run_faq
from .hair_advisor_agent import run_hair_advisor
from app.services.session_signal.session_signal_service import process_session_signals
from app.services.alerts.alert_service import process_alerts
from app.services.environmental_factors.weather_service import get_city_environmental_data
from app.services.db_service import get_db

# In-memory session state for V1
_session_profile_cache: Dict[str, Dict] = {}

class ProfileObserver:
    """
    Pass 1: Passive Observer.
    Scans every message for hair traits and updates the Transient Session Profile.
    """
    OBSERVER_PROMPT = """You are the Emerson Profile Observer.
Analyze the user message and extract any mentioned hair traits.

TRAITS TO EXTRACT:
- texture: Fine, Medium, Coarse
- density: Thin, Medium, Thick
- moisture_behaviour: Low Porosity, High Porosity
- humidity_response: Frizz, Limp
- hair_goals: List of strings

RESPONSE FORMAT:
Output ONLY matching traits in JSON. For any trait not mentioned, set to null.
Example: {"texture": "Fine", "density": null, "moisture_behaviour": null, "humidity_response": null, "hair_goals": ["Volume"]}
"""

    def __init__(self, model: str = "gemini-2.5-flash-lite"):
        self.model = model

    async def extract_traits(self, message: str) -> Dict:
        """Extracts JSON traits from raw text."""
        prompt = f"{self.OBSERVER_PROMPT}\n\nUSER MESSAGE: {message}\n\nJSON TRAITS:"
        
        json_str = ""
        async for chunk in run_llm_agent(prompt, model=self.model):
            if chunk.get("type") == "content":
                json_str += chunk.get("content", "")
        
        try:
            # Strip potential markdown code blocks
            clean_json = json_str.replace("```json", "").replace("```", "").strip()
            traits = json.loads(clean_json)
            return traits if isinstance(traits, dict) else {}
        except Exception:
            return {}

    async def update_state(self, session_id: str, message: str) -> Dict:
        """Updates the transient profile in the session cache."""
        print(f"\n--- [PASS 1: OBSERVER] Analyzing: \"{message}\" ---")
        new_traits = await self.extract_traits(message)
        
        if session_id not in _session_profile_cache:
            _session_profile_cache[session_id] = {
                "texture": None,
                "density": None,
                "moisture_behaviour": None,
                "humidity_response": None,
                "hair_goals": []
            }
        
        current = _session_profile_cache[session_id]
        # Merge new traits (simple overwrite for now)
        for key, val in new_traits.items():
            if val is not None:
                if key == "hair_goals" and isinstance(val, list):
                    current[key] = list(set(current[key] + val))
                else:
                    current[key] = val
        
        print(f"[OBSERVER] Updated Session State: {current}")
        return current

class WebChatOrchestrator:
    """
    Main entry point for the Web Chat. It reads the user message and routes to the correct agent.
    """
    
    TRIAGE_PROMPT = """You are the Emerson Triage System.
Analyze the user message and decompose it into a sequence of actionable task intents.

INTENT OPTIONS:
1. "DISCOVERY": User seeking product recommendations or help finding a routine.
2. "FAQ": User seeking store info, shipping, returns, or order status.
3. "ADVISOR": User seeking technical hair advice, ingredient info, or science-based answers.

RESPONSE FORMAT: 
Output ONLY a JSON list of objects: [{"intent": "LABEL", "query": "sub-query for this intent"}].
No preamble or explanation.
"""

    def __init__(self, model: str = "gemini-2.5-flash-lite"):
        self.model = model
        self.observer = ProfileObserver(model=model)

    async def _stream_alerts(
        self,
        user_id: str,
        session_id: str,
        history: List[Dict[str, str]],
        message: str,
    ) -> AsyncGenerator[Dict, None]:
        """
        Run the session signal detector against recent chat, fetch env context
        for the user, then emit any new alerts as SSE events. Failures here are
        non-fatal — alerts are best-effort and must not block the reply.
        """
        try:
            full_history = history + [{"role": "user", "message": message}]
            snapshot = await process_session_signals(user_id, session_id, full_history)
        except Exception as e:
            print(f"[orchestrator] session signal detection failed: {e}")
            return

        env_kwargs: Dict = {}
        try:
            metadata = get_db().get_user_metadata(user_id) or {}
            location = metadata.get("location")
            if location:
                env_kwargs["country"] = location
                weather = await get_city_environmental_data(location, attribute="all")
                if weather:
                    env_kwargs["temp_c"] = weather.get("peak_heat")
                    env_kwargs["humidity"] = weather.get("peak_humidity")
        except Exception as e:
            print(f"[orchestrator] env context fetch failed: {e}")

        try:
            alerts = process_alerts(user_id, snapshot, **env_kwargs)
        except Exception as e:
            print(f"[orchestrator] alert processing failed: {e}")
            return

        for alert in alerts:
            yield {
                "type": "alert",
                "alert_type": alert.alert_type,
                "scenario": alert.scenario or alert.alert_type,
                "source_type": alert.source_type,
                "message": alert.message,
            }

    async def decompose_intents(self, message: str) -> List[Dict]:
        """Decomposes a potentially compound message into specific intent tasks."""
        prompt = f"{self.TRIAGE_PROMPT}\n\nUSER MESSAGE: {message}\n\nJSON TASK LIST:"
        
        json_str = ""
        async for chunk in run_llm_agent(prompt, model=self.model):
            if chunk.get("type") == "content":
                json_str += chunk.get("content", "")
        
        try:
            clean_json = json_str.replace("```json", "").replace("```", "").strip()
            tasks = json.loads(clean_json)
            return tasks if isinstance(tasks, list) else []
        except Exception:
            return [{"intent": "ADVISOR", "query": message}]

    async def stream_orchestrate(
        self,
        history: List[Dict[str, str]],
        message: str,
        session_id: str,
        user_id: str = None
    ) -> AsyncGenerator[Dict, None]:
        """
        Dual-pass logic: Update state first (Pass 1), run signals + alerts
        (Pass 1.5), then dispatch (Pass 2).
        """
        # Pass 1: Observer (State Update)
        current_profile = await self.observer.update_state(session_id, message)

        # Pass 1.5: Session signals + alerts
        if user_id:
            async for event in self._stream_alerts(user_id, session_id, history, message):
                yield event

        # Pass 2: Decompose & Dispatch
        print(f"\n--- [PASS 2: TRIAGE] Decomposing message: \"{message}\" ---")
        tasks = await self.decompose_intents(message)
        print(f"[TRIAGE] Assigned Tasks: {[t['intent'] for t in tasks]}")
        
        for task in tasks:
            intent = task.get("intent")
            sub_query = task.get("query", message)
            
            print(f"\n--- [AGENT START] Intent: {intent} ---")
            print(f"[AGENT] Sub-query: \"{sub_query}\"")
            
            if intent == "DISCOVERY":
                async for event in run_discovery(history, sub_query, profile=current_profile):
                    yield event
            elif intent == "FAQ":
                async for event in run_faq(history, sub_query, profile=current_profile):
                    yield event
            else: # ADVISOR
                async for event in run_hair_advisor(history, sub_query, profile=current_profile, user_id=user_id):
                    yield event
            
            # Optional separator for multi-task responses
            if len(tasks) > 1:
                yield {"type": "content", "content": "\n\n---\n\n"}

async def orchestrate_web_chat(history, message, session_id="default", user_id=None, model="gemini-2.5-flash-lite"):
    orchestrator = WebChatOrchestrator(model=model)
    async for event in orchestrator.stream_orchestrate(history, message, session_id, user_id=user_id):
        yield event
