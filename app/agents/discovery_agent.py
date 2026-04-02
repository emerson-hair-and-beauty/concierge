"""
Discovery Agent - Socratic Product Consultant
Specialized in identifying user hair needs before recommending products.
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
    """
    
    SYSTEM_PROMPT = """You are Emerson's Socratic Discovery Expert.
Your goal is to consult with the user to identify their hair profile and style goals.

CONSULTATION RULES:
1. DO NOT recommend products immediately. 
2. Ask 1-2 discovery questions to understand:
   - Hair Pattern (Waves, Curls, Coils)
   - Primary Goal (Volume, Definition, Moisture, Scalp Health)
   - Environmental Context (GCC humidity, hard water)
3. Once you have a clear picture (Confidence > 80%), use the 'search_products' tool.
4. Keep the tone expert, warm, and luxury concierge-style.
5. If the user is vague, ask for specific details about how their hair behaves on "Day 2".

MANDATORY HANDOFF:
When you find products, explain WHY they match the user's specific profile before displaying them.
"""

    def __init__(self, model: str = "gemini-2.0-flash-lite"):
        self.model = model
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    async def search_products_tool(self, query: str) -> str:
        """Internal tool for the LLM to search for products."""
        print(f"[DISCOVERY] Tool called: search_products('{query}')")
        result = await query_products(query, top_k=3)
        products = result.get("products", [])
        
        if not products:
            return "No matching products found."
        
        # Format for the LLM to see
        formatted_results = []
        for p in products:
            formatted_results.append(f"ID: {p['id']} | Info: {p['content'][:200]}...")
        
        return "\n".join(formatted_results)

    def _build_history(self, history: List[Dict[str, str]]) -> List[Dict]:
        """Convert standard history to GenAI SDK format."""
        formatted = []
        for msg in history:
            role = "user" if msg["role"] == "user" else "model"
            formatted.append({"role": role, "parts": [{"text": msg["message"]}]})
        return formatted

    async def run(self, history: List[Dict[str, str]], message: str):
        """
        Runs the discovery agent with tool-calling capabilities.
        Yields events for streaming.
        """
        
        # 1. Setup Tools
        def search_products(query: str):
            """Search the Emerson product catalog for hair care solutions."""
            # This is a placeholder for the SDK to recognize the signature
            pass

        # 2. Call LLM with Tool Calling enabled
        chat = self.client.aio.chats.create(
            model=self.model,
            config={
                "system_instruction": self.SYSTEM_PROMPT,
                "tools": [self.search_products_tool]
            },
            history=self._build_history(history)
        )

        try:
            response = await chat.send_message(message)
            
            # 3. Handle Potential Tool Calls
            # Note: For simplicity in this first version, we handle one tool call loop.
            # If the LLM wants to call a tool, we execute it and send the result back.
            
            if response.candidates[0].content.parts[0].function_call:
                fc = response.candidates[0].content.parts[0].function_call
                if fc.name == "search_products_tool":
                    query = fc.args["query"]
                    yield {"type": "status", "content": f"Searching for {query}..."}
                    
                    tool_result = await self.search_products_tool(query)
                    
                    # Send tool result back to model for final interpretation
                    final_response = await chat.send_message(
                        f"TOOL RESULT: {tool_result}\n\nInterpret these results and present the Shopify Product IDs to the user."
                    )
                    
                    text = final_response.text
                    yield {"type": "content", "content": text}
                else:
                    yield {"type": "content", "content": response.text}
            else:
                yield {"type": "content", "content": response.text}

        except Exception as e:
            yield {"type": "error", "content": f"Discovery Error: {str(e)}"}

async def run_discovery(history, message, model="gemini-2.0-flash-lite"):
    agent = DiscoveryAgent(model=model)
    async for event in agent.run(history, message):
        yield event
