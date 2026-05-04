"""
Decomposer Agent - 4-Stage Categorisation System
Technical specification and routing diagram for engineering implementation.
Converts a raw user message into a structured decision object.
"""

import json
from typing import List, Dict, Optional, AsyncGenerator
from app.agents.llm_call.llm_call import run_llm_agent

class Decomposer:
    """
    Pass 2: Decomposer.
    Categorizes the user journey state, intent, and problem type.
    """
    
    DECOMPOSER_PROMPT = """You are the Emerson Decomposer Agent.
Your job is to classify the user's query into a structured decision object before routing to specialized agents.

STATES:
1. "DISCOVERING": Broad exploration, early learning, unclear shopping intent. Goal: Educate.
2. "DIAGNOSING": Problem described, cause unclear, needs interpretation. Goal: Explain issue.
3. "EVALUATING": Comparing options, narrowing choices, asking differences. Goal: Reduce friction.
4. "CONVERSION_READY": Asking what to buy, routine request, ready for decisive help. Goal: Recommend clearly.

INTENTS:
- education, problem_solution, routine_building, product_recommendation, product_comparison, ingredient_question, order_support

PROBLEM TYPES:
- dryness, frizz_humidity, lack_of_definition, buildup, damage_breakage, scalp_issues, low_porosity, high_porosity, protective_styling, heat_damage, unknown

ROUTING RULES (agent_plan):
- DISCOVERING -> ["faq_agent"] (optional second: "hair_advisor")
- DIAGNOSING -> ["hair_advisor"] (optional second: "product_discovery")
- EVALUATING -> ["hair_advisor"] or ["product_discovery"] (optional second: "faq_agent")
- CONVERSION_READY -> ["product_discovery"] (optional second: "hair_advisor")

RESPONSE SCHEMA:
{
  "state": "DISCOVERING | DIAGNOSING | EVALUATING | CONVERSION_READY",
  "intent": "intent_from_taxonomy",
  "problem_type": "problem_type_from_taxonomy",
  "confidence": "high | medium | low",
  "agent_plan": ["agent_name1", "agent_name2"],
  "cta_mode": "none | soft | guided | direct",
  "follow_up_question": "Only if confidence is low"
}

RULES:
- Return ONLY JSON.
- If confidence is low, populate follow_up_question with a short clarifying question.
- agent_plan names should be: "hair_advisor", "product_discovery", "faq_agent".
"""

    def __init__(self, model: str = "gemini-2.5-flash-lite"):
        self.model = model

    async def decompose(self, message: str, profile: Dict = None) -> Dict:
        """Categorizes the message and returns the decision object."""
        # Enrich the prompt with current profile context if available
        profile_context = f"CURRENT PROFILE: {json.dumps(profile)}" if profile else "CURRENT PROFILE: Unknown"
        
        prompt = f"{self.DECOMPOSER_PROMPT}\n\n{profile_context}\n\nUSER MESSAGE: {message}\n\nDECISION JSON:"
        
        json_str = ""
        async for chunk in run_llm_agent(prompt, model=self.model):
            if chunk.get("type") == "content":
                json_str += chunk.get("content", "")
        
        try:
            clean_json = json_str.replace("```json", "").replace("```", "").strip()
            decision = json.loads(clean_json)
            
            # Basic validation/defaults
            required_fields = ["state", "intent", "problem_type", "confidence", "agent_plan", "cta_mode"]
            for field in required_fields:
                if field not in decision:
                    decision[field] = "unknown" if field != "agent_plan" else ["hair_advisor"]
            
            return decision
        except Exception as e:
            print(f"[DECOMPOSER] Error parsing JSON: {e}")
            return {
                "state": "DISCOVERING",
                "intent": "education",
                "problem_type": "unknown",
                "confidence": "low",
                "agent_plan": ["hair_advisor"],
                "cta_mode": "soft",
                "follow_up_question": "I'm sorry, could you tell me a bit more about what you're looking for?"
            }
