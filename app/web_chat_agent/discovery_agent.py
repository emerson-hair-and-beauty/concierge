"""
Discovery Agent - Socratic Product Consultant
Specialized in identifying user hair needs before recommending products.
Now with extreme brevity and silent onboarding.
"""

import os
import sys
import json
from typing import List, Dict, Tuple, Optional
from google import genai
from app.config import GEMINI_API_KEY
from app.agents.recommendation.lib.knowledge_base.query_products import query_products

class DiscoveryAgent:
    """
    Agent focused exclusively on Socratic discovery for product recommendations.
    Uses the 'profile' state to identify and fill knowledge gaps.
    Now with extreme brevity.
    """
    
    SYSTEM_PROMPT = """You are Emerson's Socratic Discovery Expert.
Your goal is to consult with the user to identify their hair profile and style goals.

CONTEXT:
State: {state}
CTA Mode: {cta_mode}

CURRENT PROFILE KNOWLEDGE:
{profile_json}

CONSULTATION RULES:
1. NO ESSAYS. Maximum 2-3 sentences per segment. No conversational filler.
2. SILENT ONBOARDING: Review the 'CURRENT PROFILE KNOWLEDGE'. If any core fields are null, weave a natural question into your response.
3. ADAPTIVE PACE: 
   - If State is "DISCOVERING", be very exploratory. 
   - If State is "CONVERSION_READY" or CTA Mode is "direct", move to recommendation faster.
4. Keep the tone expert, warm, and luxury concierge-style—but extremely concise.
5. When you find products, briefly explain WHY they match the user's specific profile before displaying them.
"""

    def __init__(self, model: str = "gemini-2.0-flash-lite"):
        self.model = model
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    async def search_products_tool(self, query: str) -> str:
        """Internal tool for the LLM to search for products."""
        print(f"[DISCOVERY] Tool called: search_products('{query}')")
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

    async def run(self, history: List[Dict[str, str]], message: str, profile: Dict = None, decision: Dict = None):
        """
        Runs the discovery agent with tool-calling and profile awareness.
        """
        profile_json = json.dumps(profile or {}, indent=2)
        
        # Extract decision metadata if available
        state = decision.get("state", "Unknown") if decision else "Unknown"
        cta_mode = decision.get("cta_mode", "soft") if decision else "soft"

        system_inst = self.SYSTEM_PROMPT.format(
            profile_json=profile_json,
            state=state,
            cta_mode=cta_mode
        )

        print(f"\n[PROMPT: DISCOVERY] System Instruction (Concise):\n{system_inst}")

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
            yield {"type": "error", "content": f"Discovery Error: {str(e)}"}

async def run_discovery(history, message, profile=None, model="gemini-2.0-flash-lite", decision=None):
    agent = DiscoveryAgent(model=model)
    async for event in agent.run(history, message, profile=profile, decision=decision):
        yield event
