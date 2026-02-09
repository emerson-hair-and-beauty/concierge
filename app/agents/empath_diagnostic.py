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
1. MAX 2 QUESTIONS: After asking 2 questions, you MUST output EXACTLY this phrase:
   "May I ask a few more details to understand your hair's experience?"
   DO NOT add empathetic preambles like "I'm so sorry to hear...". 
   DO NOT rephrase. Use EXACTLY this phrase.
   
2. QUESTION COUNTING: 
   - Question 1: Initial diagnostic question
   - Question 2: Follow-up question
   - After Question 2: MANDATORY permission request (use exact phrase above)
   - Question 3+: Only if user grants permission
   
3. STOP EARLY: If the user confirms a major symptom (e.g., "Yes, it's breaking"), DO NOT ask about other categories (like Scalp) unless they mentioned it. Focus on the confirmed issue.

4. ONE AT A TIME: Ask ONLY one question per turn.

5. POSITIVE LANGUAGE: Use "rich texture", "voluminous". BAN "unruly", "difficult".

6. ACCESSIBLE LANGUAGE: Avoid technical jargon. Use "irritation" not "inflammation", "redness" not "erythema".

7. VERIFY: Summarize "Symptom + Wash Day" and ask for confirmation before handoff.

8. HANDOFF: Output [CHECKPOINT: CATEGORY] after confirmation.
"""

    def __init__(self, model: str = "gemini-2.5-flash-lite"):
        self.model = model
    
    def _is_temporal_known(self, history: List[Dict[str, str]], current_message: str) -> bool:
        """Detects if temporal context (wash day) has already been provided."""
        temporal_markers = [r'\bday\b', r'\bwash\b', r'\blast\b', r'\byesterday\b', r'\bago\b']
        full_text = " ".join([m.get("message", "") for m in history] + [current_message]).lower()
        return any(re.search(marker, full_text) for marker in temporal_markers)

    def _count_questions(self, history: List[Dict[str, str]]) -> int:
        """Counts how many diagnostic questions the assistant has asked."""
        count = 0
        for msg in history:
            if msg["role"] == "assistant":
                # A question is any message that ends with or contains a '?' 
                # and isn't the permission request itself.
                text = msg["message"]
                if "?" in text and "May I ask a few more details" not in text:
                    count += 1
        return count

    def _build_prompt(self, history: List[Dict[str, str]], current_message: str, past_context: str = None) -> str:
        """Assembles the prompt with past context and trackers."""
        
        # 1. Check temporal context
        temporal_known = self._is_temporal_known(history, current_message)
        
        # 2. Count questions asked so far
        question_count = self._count_questions(history)
        
        # 3. Build Guard Rails
        guard_rails = []
        
        # Question counting guard rail
        guard_rails.append(f"[SYSTEM NOTE: You have already asked {question_count} diagnostic questions.]")
        if question_count >= 2:
            guard_rails.append("[CRITICAL: You MUST ask permission now. Use the exact phrase specified in Rule 1.]")
        
        # Temporal guard rail
        if temporal_known:
            guard_rails.append("[SYSTEM NOTE: Wash day is ALREADY KNOWN. Move to Verification or Handoff.]")
        else:
            guard_rails.append("[SYSTEM NOTE: Wash day is UNKNOWN. Ask for the wash day timeline soon.]")

        prompt_parts = [
            self.SYSTEM_PROMPT,
            "\n".join(guard_rails)
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