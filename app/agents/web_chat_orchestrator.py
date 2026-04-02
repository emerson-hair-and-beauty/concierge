"""
Web Chat Orchestrator - Triage Dispatcher
Routes user requests to the specialized sub-agent (Discovery, FAQ, or Hair Advisor).
"""

from typing import List, Dict, Optional, AsyncGenerator
from app.agents.llm_call.llm_call import run_llm_agent
from app.agents.discovery_agent import run_discovery
from app.agents.faq_agent import run_faq
from app.agents.hair_advisor_agent import run_hair_advisor

class WebChatOrchestrator:
    """
    Main entry point for the Web Chat. It reads the user message and routes to the correct agent.
    """
    
    TRIAGE_PROMPT = """You are the Emerson Triage System.
Based on the message below, choose the most appropriate sub-agent to handle the request.

SUB-AGENTS:
1. "DISCOVERY": User seeking product recommendations or help finding a routine.
2. "FAQ": User seeking store info, shipping, returns, or order status.
3. "ADVISOR": User seeking technical hair advice, ingredient info, or science-based answers.

RESPONSE FORMAT: 
ONLY output the sub-agent label (DISCOVERY, FAQ, or ADVISOR). Do not add preamble.
"""

    def __init__(self, model: str = "gemini-2.5-flash-lite"):
        self.model = model

    async def detect_intent(self, message: str) -> str:
        """Determines which sub-agent is best suited for the message."""
        prompt = f"{self.TRIAGE_PROMPT}\n\nUSER MESSAGE: {message}\n\nSUB-AGENT:"
        
        intent = ""
        async for chunk in run_llm_agent(prompt, model=self.model):
            if chunk.get("type") == "content":
                intent += chunk.get("content", "")
        
        intent = intent.strip().upper()
        print(f"[TRIAGE] Detected Intent: {intent}")
        return intent if intent in ["DISCOVERY", "FAQ", "ADVISOR"] else "ADVISOR"

    async def stream_orchestrate(
        self, 
        history: List[Dict[str, str]], 
        message: str, 
        user_id: str = None
    ) -> AsyncGenerator[Dict, None]:
        """
        Routes the message to the appropriate agent and manages the stream.
        """
        intent = await self.detect_intent(message)
        
        if intent == "DISCOVERY":
            async for event in run_discovery(history, message):
                yield event
        elif intent == "FAQ":
            async for event in run_faq(history, message):
                yield event
        else: # ADVISOR
            async for event in run_hair_advisor(history, message, user_id=user_id):
                yield event

async def orchestrate_web_chat(history, message, user_id=None, model="gemini-2.5-flash-lite"):
    orchestrator = WebChatOrchestrator(model=model)
    async for event in orchestrator.stream_orchestrate(history, message, user_id=user_id):
        yield event
