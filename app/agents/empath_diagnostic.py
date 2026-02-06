"""
Empath Diagnostic Agent
Implements Socratic questioning to diagnose hair health issues with token-efficiency
and anti-looping logic.
"""

import re
from typing import List, Dict, Tuple, Optional
from app.agents.llm_call.llm_call import run_llm_agent

class EmpathDiagnosticAgent:
    """
    The "Empath Brain" - Optimized for high-confidence diagnosis and low token usage.
    """
    
    SYSTEM_PROMPT = """You are a Luxury Hair Concierge Empath with Long-Term Memory.
Goal: Reach 90% confidence in ONE category. STOP immediately once a primary issue is identified.

DIAGNOSTIC CRITERIA:
1. MOISTURE: Hair feels rough, dry, or "straw-like."
2. DEFINITION: Pattern is messy or lacks structure, but hair feels soft/healthy.
3. SCALP: Itching, redness, oil, or irritation.
4. BREAKAGE: Hair is snapping, shedding, or feels limp/weak.

CRITICAL RULES:
1. MAX 2 QUESTIONS: You MUST ask permission ("May I ask a few more details to make sure I fully understand your hair's experience?") if you need a 3rd question. NO EXCEPTIONS.
2. CHECK HISTORY: Count how many questions you have already asked. If > 2, trigger permission.
3. STOP EARLY: If the user confirms a major symptom (e.g., "Yes, it's breaking"), DO NOT ask about other categories (like Scalp) unless they mentioned it. Focus on the confirmed issue.
4. ONE AT A TIME: Ask ONLY one question per turn.
5. POSITIVE LANGUAGE: Use "rich texture", "voluminous". BAN "unruly", "difficult".
6. VERIFY: Summarize "Symptom + Wash Day" and ask for confirmation before handoff.
7. HANDOFF: Output [CHECKPOINT: CATEGORY] after confirmation.
"""

    def __init__(self, model: str = "gemini-2.5-flash-lite"):
        self.model = model
    
    def _is_temporal_known(self, history: List[Dict[str, str]], current_message: str) -> bool:
        """Detects if temporal context (wash day) has already been provided."""
        temporal_markers = [r'\bday\b', r'\bwash\b', r'\blast\b', r'\byesterday\b', r'\bago\b']
        full_text = " ".join([m.get("message", "") for m in history] + [current_message]).lower()
        return any(re.search(marker, full_text) for marker in temporal_markers)

    def _build_prompt(self, history: List[Dict[str, str]], current_message: str, past_context: str = None) -> str:
        """Assembles the prompt with past context and 'Instruction Guard' to prevent loops."""
        
        # Check if we already know the wash day to prevent the LLM from asking again
        temporal_known = self._is_temporal_known(history, current_message)
        guard_rail = ""
        if temporal_known:
            guard_rail = "\n[SYSTEM NOTE: Wash day is ALREADY KNOWN. Move to Verification or Handoff.]"
        else:
            guard_rail = "\n[SYSTEM NOTE: Wash day is UNKNOWN. You must ask for the wash day timeline soon.]"

        prompt_parts = [
            self.SYSTEM_PROMPT,
            guard_rail
        ]
        
        # Inject past context from Librarian if available
        if past_context:
            prompt_parts.append(f"\n{past_context}\n")
        
        prompt_parts.append("\nCONVERSATION HISTORY:")
        
        if not history:
            prompt_parts.append("(New Conversation)")
        else:
            for msg in history:
                role = "User" if msg["role"] == "user" else "Assistant"
                prompt_parts.append(f"{role}: {msg['message']}")
        
        prompt_parts.append(f"User: {current_message}")
        prompt_parts.append("Assistant:")
        
        return "\n".join(prompt_parts)

    async def run_diagnostic(
        self, 
        history: List[Dict[str, str]], 
        current_message: str,
        past_context: str = None
    ) -> str:
        """Calls the LLM and streams the response with past context."""
        conversation = self._build_prompt(history, current_message, past_context)
        
        full_response = ""
        async for chunk in run_llm_agent(conversation, self.model):
            if chunk.get("type") == "content":
                full_response += chunk.get("content", "")
        
        return full_response.strip()

    def parse_response(self, response_text: str) -> Tuple[str, bool, Optional[str]]:
        """Extracts the handoff trigger and cleans the message for the UI."""
        checkpoint_pattern = r'\[CHECKPOINT:\s*(MOISTURE|DEFINITION|SCALP|BREAKAGE)\s*\]'
        match = re.search(checkpoint_pattern, response_text, re.IGNORECASE)
        
        if match:
            category = match.group(1).upper()
            clean_message = re.sub(checkpoint_pattern, '', response_text, flags=re.IGNORECASE).strip()
            
            vital_mapping = {
                "MOISTURE": "moisture",
                "DEFINITION": "definition",
                "SCALP": "scalp",
                "BREAKAGE": "breakage"
            }
            
            return (clean_message, True, vital_mapping[category])
        
        return (response_text, False, None)

# Main entry point
async def diagnose_hair_concern(
    history: List[Dict[str, str]], 
    current_message: str,
    past_context: str = None,
    model: str = "gemini-2.5-flash-lite"
) -> Tuple[str, bool, Optional[str]]:
    """Convenience function to run the diagnostic loop with optional past context."""
    agent = EmpathDiagnosticAgent(model=model)
    response = await agent.run_diagnostic(history, current_message, past_context)
    return agent.parse_response(response)