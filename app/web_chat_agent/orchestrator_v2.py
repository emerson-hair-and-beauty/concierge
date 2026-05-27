"""
Web Chat Orchestrator V2 - Stateful Decomposer
Implements the "Decomposer Agent" spec in parallel with the V1 system.
"""

import json
from typing import List, Dict, Optional, AsyncGenerator
from app.agents.llm_call.llm_call import run_llm_agent
from .discovery_agent import run_discovery
from .faq_agent import run_faq
from .hair_advisor_agent import run_hair_advisor
from .orchestrator import ProfileObserver
from .decomposer import Decomposer

class WebChatOrchestratorV2:
    """
    New Orchestrator using the Decomposer (4-Stage State Model).
    """

    def __init__(self, model: str = "gemini-2.5-flash-lite"):
        self.model = model
        self.observer = ProfileObserver(model=model)
        self.decomposer = Decomposer(model=model)

    async def stream_orchestrate(
        self, 
        history: List[Dict[str, str]], 
        message: str, 
        session_id: str,
        user_id: str = None
    ) -> AsyncGenerator[Dict, None]:
        """
        Dual-pass logic with Decomposer:
        1. Update state (Observer)
        2. Decompose journey (Decomposer)
        3. Dispatch based on agent_plan
        """
        # Pass 1: Observer (State Update)
        current_profile = await self.observer.update_state(session_id, message)
        
        # Pass 2: Decomposer (Journey Mapping)
        print(f"\n--- [PASS 2: DECOMPOSER] Analyzing message: \"{message}\" ---")
        decision = await self.decomposer.decompose(message, profile=current_profile)
        print(f"[DECOMPOSER] Decision: {json.dumps(decision, indent=2)}")
        
        # Handle Low Confidence
        if decision.get("confidence") == "low" and decision.get("follow_up_question"):
            print("[DECOMPOSER] Low confidence - asking follow-up.")
            yield {"type": "content", "content": decision["follow_up_question"]}
            return

        # Execute Agent Plan
        agent_plan = decision.get("agent_plan", ["hair_advisor"])
        for agent_name in agent_plan:
            print(f"\n--- [AGENT START] Agent: {agent_name} ---")
            
            if agent_name == "product_discovery" or agent_name == "discovery_agent":
                async for event in run_discovery(history, message, profile=current_profile, decision=decision):
                    yield event
            elif agent_name == "faq_agent":
                async for event in run_faq(history, message, profile=current_profile, decision=decision):
                    yield event
            else: # hair_advisor
                async for event in run_hair_advisor(history, message, profile=current_profile, user_id=user_id, decision=decision):
                    yield event
            
            # Optional separator between agents
            if len(agent_plan) > 1 and agent_name != agent_plan[-1]:
                yield {"type": "content", "content": "\n\n"}

async def orchestrate_web_chat_v2(history, message, session_id="default", user_id=None, model="gemini-2.5-flash-lite"):
    orchestrator = WebChatOrchestratorV2(model=model)
    async for event in orchestrator.stream_orchestrate(history, message, session_id, user_id=user_id):
        yield event
