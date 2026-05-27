"""
Hair Advisor Agent - Science & Technique Expert
Powered by the existing Emerson classifiers to provide personalized curl advice.
Now with extreme brevity and product linking.
"""

import json
from typing import List, Dict, Optional
from google import genai
from app.config import GEMINI_API_KEY
from app.agents.llm_call.llm_call import run_llm_agent
from app.agents.input.lib.find_advice import collateAdvice
from app.agents.recommendation.lib.knowledge_base.query_products import query_products

class HairAdvisorAgent:
    """
    Agent focused on scientifically accurate curl care, powered by existing classifiers.
    Now with extreme brevity and product linking.
    """
    
    SYSTEM_PROMPT = """You are the Emerson Expert Hair Advisor.
Your mission is to provide accurate, 1-3 sentence curl care advice.

CONTEXT:
State: {state}
Problem Type: {problem_type}
CTA Mode: {cta_mode}

ADVICE GUARDRAILS (Based on current profile):
{directives}

ROUTINE FLAGS:
{routine_flags}

RULES:
1. NO ESSAYS. Maximum 3 sentences. No conversational filler.
2. PRODUCT LINKING: If you recommend a technique that requires a product, you MUST use 'search_products_tool'.
3. Only use the 'Directives' and 'Routine Flags' as your absolute ground truth.
4. If the State is "DIAGNOSING", focus on explaining the cause of the {problem_type}.
5. If the State is "EVALUATING", focus on comparing options or narrowing choices.
6. Warm, premium brand voice—professional but extremely concise.
"""

    def __init__(self, model: str = "gemini-2.0-flash-lite"):
        self.model = model
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    def _get_user_profile(self, user_id: str) -> dict:
        """Mock profile retrieval from Supabase."""
        if user_id:
            return {
                "texture": "Medium",
                "density": "High",
                "moisture_behaviour": "High Porosity",
                "humidity_response": "Expands and fizzes",
                "hair_goals": ["Volume", "Definition"]
            }
        return {}

    async def search_products_tool(self, query: str) -> str:
        """Internal tool for the LLM to search for products."""
        print(f"[ADVISOR] Tool called: search_products('{query}')")
        result = await query_products(query, top_k=2)
        products = result.get("products", [])
        if not products: return "No matching products found."
        return "\n".join([f"ID: {p['id']} | Info: {p['content'][:100]}" for p in products])

    def _build_history(self, history: List[Dict[str, str]]) -> List[Dict]:
        """Convert standard history to GenAI SDK format."""
        formatted = []
        for msg in history:
            role = "user" if msg["role"] == "user" else "model"
            formatted.append({"role": role, "parts": [{"text": msg.get("message", "") or msg.get("content", "")}]})
        return formatted

    async def run(self, history: List[Dict[str, str]], message: str, profile: Dict = None, user_id: str = None, decision: Dict = None):
        """
        Runs the Hair Advisor agent with dynamic context and product linking.
        """
        # Prioritize the transient session profile (from Pass 1) over the DB profile for session consistency
        active_profile = profile if profile and any(v is not None for v in profile.values() if v != []) else self._get_user_profile(user_id)
        
        advice_data = collateAdvice(active_profile)
        
        directives_str = "\n".join([f"- {k}: {v}" for k, v in advice_data.get("directives", {}).items() if v])
        flags_str = str(advice_data.get("routine_flags", {}))
        
        # Extract decision metadata if available
        state = decision.get("state", "Unknown") if decision else "Unknown"
        problem_type = decision.get("problem_type", "Unknown") if decision else "Unknown"
        cta_mode = decision.get("cta_mode", "soft") if decision else "soft"

        system_inst = self.SYSTEM_PROMPT.format(
            state=state,
            problem_type=problem_type,
            cta_mode=cta_mode,
            directives=directives_str if directives_str else "No specific profile known yet. Providing general guidance.",
            routine_flags=flags_str
        )
        
        print(f"\n[PROMPT: ADVISOR] Grounded Directives:\n{directives_str}")

        chat = self.client.aio.chats.create(
            model=self.model,
            config={
                "system_instruction": system_inst,
                "tools": [self.search_products_tool]
            },
            history=self._build_history(history)
        )

        try:
            response = await chat.send_message(message)
            
            # Handle Potential Tool Calls
            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                first_part = response.candidates[0].content.parts[0]
                if hasattr(first_part, 'function_call') and first_part.function_call:
                    fc = first_part.function_call
                    if fc.name == "search_products_tool":
                        query = fc.args["query"]
                        yield {"type": "status", "content": f"Searching for products related to {query}..."}
                        
                        tool_result = await self.search_products_tool(query)
                        final_response = await chat.send_message(f"TOOL RESULT: {tool_result}\n\nPresent the product and ID clearly and keep it extremely brief.")
                        yield {"type": "content", "content": final_response.text}
                    else:
                        yield {"type": "content", "content": response.text}
                else:
                    yield {"type": "content", "content": response.text}
            else:
                 yield {"type": "content", "content": response.text}

        except Exception as e:
            yield {"type": "error", "content": f"Advisor Error: {str(e)}"}

async def run_hair_advisor(history, message, profile=None, user_id=None, model="gemini-2.0-flash-lite", decision=None):
    agent = HairAdvisorAgent(model=model)
    async for event in agent.run(history, message, profile=profile, user_id=user_id, decision=decision):
        yield event
