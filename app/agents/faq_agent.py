"""
FAQ Agent - Support Assistant
Specialized in handling shipping, returns, and store policy queries.
"""

from typing import List, Dict, Optional
from app.agents.llm_call.llm_call import run_llm_agent

class FAQAgent:
    """
    Agent focused on answering store policies and general support FAQs.
    """
    
    SYSTEM_PROMPT = """You are the Emerson Store Support Assistant.
Goal: Provide clear, expert answers about shipping, returns, and order management.

GUIDELINES:
1. Use the 'search_faqs' tool to look up policy details.
2. If the user asks about their specific order, ask for their order number.
3. Be helpful, professional, and reassuring.
4. If the question is about hair care, hand the user back to the "Concierge" for advice.
"""

    def __init__(self, model: str = "gemini-2.5-flash-lite"):
        self.model = model

    async def search_faqs_tool(self, query: str) -> str:
        """
        Placeholder for the FAQ vector search.
        In production, this would query a Pinecone index for 'FAQ' namespace.
        """
        print(f"[FAQ] Tool called: search_faqs('{query}')")
        
        # Hardcoded mock knowledge for testing
        knowledge = {
            "shipping": "Emerson ships within the GCC in 2-4 business days. International shipping takes 7-10 days.",
            "returns": "We offer a 30-day money-back guarantee if you're not happy with your curls.",
            "ingredients": "Our products are sulfate-free, paraben-free, and specifically formulated for wavy/curly hair.",
            "order": "You can track your order in your Emerson account dashboard."
        }
        
        for k, v in knowledge.items():
            if k in query.lower():
                return v
        
        return "Please contact support@emersoncurl.com for specific policy details."

    async def run(self, history: List[Dict[str, str]], message: str):
        """
        Runs the FAQ agent.
        """
        prompt = f"{self.SYSTEM_PROMPT}\n\nCONTEXT:\n{await self.search_faqs_tool(message)}\n\nHISTORY:\n{history}\n\nUSER: {message}\n\nASSISTANT:"
        
        async for chunk in run_llm_agent(prompt, model=self.model):
            yield chunk

async def run_faq(history, message, model="gemini-2.5-flash-lite"):
    agent = FAQAgent(model=model)
    async for event in agent.run(history, message):
        yield event
