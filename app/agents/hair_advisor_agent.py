"""
Hair Advisor Agent - Science & Technique Expert
Powered by the existing Emerson classifiers to provide personalized curl advice.
"""

from typing import List, Dict, Optional
from app.agents.llm_call.llm_call import run_llm_agent
from app.agents.input.lib.find_advice import collateAdvice
from app.services.db_service import get_db

class HairAdvisorAgent:
    """
    Agent focused on scientifically accurate curl care, powered by existing classifiers.
    """
    
    SYSTEM_PROMPT = """You are the Emerson Expert Hair Advisor.
Your mission is to provide accurate, science-based curl care advice (L.O.C. method, squish to condish, etc.).

ADVICE GUARDRAILS:
{directives}

ROUTINE FLAGS:
{routine_flags}

RULES:
1. Use the 'Directives' and 'Routine Flags' as your absolute ground truth for this user.
2. Be expert, encouraging, and highly technical yet accessible.
3. If asked about a product, hand the user back to the "Consultation" agent.
4. If the hair profile is unknown, provide general best practices but emphasize "it depends on your profile".
"""

    def __init__(self, model: str = "gemini-2.5-flash-lite"):
        self.model = model

    def _get_user_profile(self, user_id: str) -> dict:
        """
        Mock profile retrieval from Supabase.
        In production, calls db.get_user_profile(user_id).
        """
        # For simulation, we assume a "High Porosity / Dense" profile if user_id exists
        if user_id:
            return {
                "texture": "Type 3C",
                "density": "High",
                "moisture_behaviour": "High Porosity",
                "humidity_response": "Expands and fizzes",
                "hair_goals": ["Volume", "Definition"]
            }
        return {}

    async def run(self, history: List[Dict[str, str]], message: str, user_id: str = None):
        """
        Runs the Hair Advisor agent.
        """
        profile = self._get_user_profile(user_id)
        advice_data = collateAdvice(profile)
        
        directives_str = "\n".join([f"- {k}: {v}" for k, v in advice_data.get("directives", {}).items()])
        flags_str = str(advice_data.get("routine_flags", {}))
        
        system_inst = self.SYSTEM_PROMPT.format(
            directives=directives_str if directives_str else "No specific profile known yet.",
            routine_flags=flags_str
        )
        
        prompt = f"{system_inst}\n\nHISTORY:\n{history}\n\nUSER: {message}\n\nASSISTANT:"
        
        async for chunk in run_llm_agent(prompt, model=self.model):
            yield chunk

async def run_hair_advisor(history, message, user_id=None, model="gemini-2.5-flash-lite"):
    agent = HairAdvisorAgent(model=model)
    async for event in agent.run(history, message, user_id=user_id):
        yield event
