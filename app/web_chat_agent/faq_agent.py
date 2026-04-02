"""
FAQ Agent - Support Assistant
Specialized in handling shipping, returns, and store policy queries.
Now with extreme brevity and product linking.
"""

import json
from typing import List, Dict, Optional
from google import genai
from app.config import GEMINI_API_KEY
from app.agents.llm_call.llm_call import run_llm_agent
from app.agents.recommendation.lib.knowledge_base.query_products import query_products

class FAQAgent:
    """
    Agent focused on answering store policies and general support FAQs.
    Uses 'search_products_tool' if the user asks about ingredients or a line.
    """
    
    SYSTEM_PROMPT = """You are the Emerson Store Support Assistant.
Goal: Provide a direct, 1-3 sentence answer using the provided FAQ context.

USER PROFILE CONTEXT:
{profile_json}

RULES:
1. NO ESSAYS. Maximum 3 sentences. No conversational filler ("I understand...", "That is a great question...").
2. Only answer based on the CONTEXT SNIPPETS provided.
3. CONFLICT RESOLUTION: Use the 'USER PROFILE CONTEXT' to decide which regional policy applies.
4. PRODUCT LINKING: If you mention a specific product line or ingredient, use 'search_products_tool' to find the Shopify ID.
5. If context is missing, provide a 1-sentence handoff to a human advisor.
6. Warm, premium brand voice—professional but extremely concise.
"""

    def __init__(self, model: str = "gemini-2.0-flash-lite"):
        self.model = model
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    async def search_faqs_tool(self, query: str) -> List[str]:
        """
        Retrieves multiple relevant FAQ snippets.
        In production, this would search a Pinecone index for top_k results.
        """
        print(f"[FAQ] Searching for snippets related to: '{query}'")
        
        # Expanded mock knowledge base
        knowledge = {
            "shipping_gcc": "Emerson ships within the GCC (UAE, Saudi Arabia, Qatar, Kuwait, Oman, Bahrain) in 2-4 business days via Aramex.",
            "shipping_int": "International shipping to the UK, EU, and US takes 7-10 business days via DHL Express.",
            "returns_gcc": "We offer a 30-day 'Curl Happiness' guarantee with FREE returns within the GCC.",
            "returns_int": "International returns are accepted within 30 days, but the customer is responsible for shipping costs.",
            "ingredients": "All products are sulfate-free, paraben-free, and silicone-free, following the Curly Girl Method guidelines.",
            "recycling": "Our packaging is 100% recyclable and we use minimal plastic in our shipping materials.",
            "order_tracking": "Once your order ships, you will receive a tracking link via email and WhatsApp."
        }
        
        # Improved keyword matching for simulation
        results = []
        query_lower = query.lower()
        
        # Handle "return policy" -> "returns"
        if "policy" in query_lower or "return" in query_lower:
             query_lower += " returns"
             
        for key, text in knowledge.items():
            if any(word in query_lower for word in key.split("_")):
                results.append(text)
        
        return results if results else ["No specific policy found."]

    async def search_products_tool(self, query: str) -> str:
        """Internal tool for the LLM to search for products."""
        print(f"[FAQ] Tool called: search_products('{query}')")
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

    async def run(self, history: List[Dict[str, str]], message: str, profile: Dict = None):
        """
        Runs the FAQ agent with Synthesis and Product Linking.
        """
        snippets = await self.search_faqs_tool(message)
        context_str = "\n".join([f"- {s}" for s in snippets])
        profile_json = json.dumps(profile or {}, indent=2)
        
        system_inst = self.SYSTEM_PROMPT.format(profile_json=profile_json)

        print(f"\n[PROMPT: FAQ] Synthesis Context:\n{context_str}")

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
            
            # 3. Handle Potential Tool Calls
            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                first_part = response.candidates[0].content.parts[0]
                if hasattr(first_part, 'function_call') and first_part.function_call:
                    fc = first_part.function_call
                    if fc.name == "search_products_tool":
                        query = fc.args["query"]
                        yield {"type": "status", "content": f"Searching for products related to {query}..."}
                        
                        tool_result = await self.search_products_tool(query)
                        final_response = await chat.send_message(f"TOOL RESULT: {tool_result}\n\nPresent the product ID and keep it brief.")
                        yield {"type": "content", "content": final_response.text}
                    else:
                        yield {"type": "content", "content": response.text}
                else:
                    yield {"type": "content", "content": response.text}
            else:
                 yield {"type": "content", "content": response.text}

        except Exception as e:
            yield {"type": "error", "content": f"FAQ Error: {str(e)}"}

async def run_faq(history, message, profile=None, model="gemini-2.0-flash-lite"):
    agent = FAQAgent(model=model)
    async for event in agent.run(history, message, profile=profile):
        yield event
