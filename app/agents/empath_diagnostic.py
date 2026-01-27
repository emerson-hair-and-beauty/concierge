"""
Empath Diagnostic Agent
Implements Socratic questioning to diagnose hair health issues and reach 90% confidence
"""

import re
from typing import List, Dict, Tuple, Optional
from app.agents.llm_call.llm_call import run_llm_agent

class EmpathDiagnosticAgent:
    """
    The "Empath Brain" - uses Socratic questioning to narrow down hair health issues.
    Goal: Reach 90% confidence in one of 4 categories within 4-5 messages.
    """
    
    SYSTEM_PROMPT = """You are a Luxury Hair Concierge Empath specializing in textured hair care.

Your mission: Through empathetic Socratic questioning, diagnose the user's primary hair concern with 90% confidence in ONE of these categories:
1. MOISTURE (dryness, hydration issues)
2. DEFINITION (curl pattern, frizz, shape)
3. SCALP (irritation, buildup, health)
4. BREAKAGE (weakness, damage, snapping)

WORKFLOW (Follow strictly and sequentially):
1. ANCHOR: Acknowledge their concern with empathy.
2. NARROW: Ask ONE clarifying question to distinguish between categories.
   - Example: "Is it dry or just messy?" (Moisture vs Definition)
   - Example: "Is it snapping or just feeling rough?" (Breakage vs Moisture)
   - AIM to diagnose within 4-5 questions, but if confidence is low, continue asking clarifying questions. Do not force a guess.
3. TEMPORAL: Connect to their wash day cycle. YOU MUST ASK THIS if you haven't yet.
   - "What day are you on in your wash cycle?"
   - "When did you last wash your hair?"
4. VERIFY: Once you are 90% confident, summarize the situation and ask "Does this sound right?"
   - "So if I understand correctly, your hair is [X] and you're on day [Y]? Does that sound right?"
   - DO NOT trigger a checkpoint here. Wait for confirmation.
5. HANDOFF: Trigger the checkpoint ONLY after the user confirms (e.g., "Yes", "Exactly").

CHECKPOINT TRIGGER RULES:
- DO NOT use [CHECKPOINT: ...] until the user explicitly attempts to confirm your summary.
- DO NOT use [CHECKPOINT: ...] if you are still asking a clarifying question.
- NEVER trigger a checkpoint in the same message as a question.
- ONLY use [CHECKPOINT: ...] in the final helpful response after confirmation.

AMBIGUITY HANDLING:
- If the user mentions multiple issues, ask them to pick the *single most urgent* concern.
- If the user is unclear, list the likely options and ask them to choose.

Where CATEGORY_NAME is one of: MOISTURE, DEFINITION, SCALP, BREAKAGE

RULES:
- Ask ONLY ONE question per response.
- Be warm, empathetic, and conversational.
- Use natural language, not clinical jargon.
- Keep responses under 3 sentences.
- NEVER combine the Temporal question with the Narrowing question. Ask them one by one.

Example conversation:
User: "My hair feels like straw"
You: "I hear you - that sounds frustrating. Is it snapping when you touch it, or just feeling rough and dry?"

User: "Snapping when I brush it"
You: "Got it. That sounds like breakage. How many days are you into your current wash cycle?"

User: "Day 5"
You: "So your hair is experiencing breakage, especially when brushing, and you're on day 5. Does that sound right?"

User: "Yes exactly"
You: "Understood. Let me help you track this. [CHECKPOINT: BREAKAGE]"
"""

    def __init__(self, model: str = "gemini-2.5-flash-lite"):
        """
        Initialize the Empath agent.
        
        Args:
            model: The LLM model to use for diagnostics
        """
        self.model = model
    
    async def run_diagnostic(
        self, 
        history: List[Dict[str, str]], 
        current_message: str
    ) -> str:
        """
        Run the diagnostic conversation with the LLM.
        
        Args:
            history: List of previous messages [{"role": "user"|"assistant", "message": "..."}]
            current_message: The user's latest message
            
        Returns:
            The assistant's response (may contain [CHECKPOINT: ...])
        """
        # Build the conversation prompt
        conversation = self._build_prompt(history, current_message)
        
        # Call the LLM
        full_response = ""
        async for chunk in run_llm_agent(conversation, self.model):
            if chunk.get("type") == "content":
                full_response += chunk.get("content", "")
        
        return full_response.strip()
    
    def parse_response(self, response_text: str) -> Tuple[str, bool, Optional[str]]:
        """
        Parse the LLM response to detect checkpoint triggers.
        
        Args:
            response_text: The raw LLM response
            
        Returns:
            Tuple of (clean_message, handoff_flag, target_vital)
            - clean_message: Response without checkpoint marker
            - handoff_flag: True if checkpoint detected
            - target_vital: "moisture"|"definition"|"scalp"|"breakage" or None
        """
        # Check for checkpoint pattern: [CHECKPOINT: CATEGORY]
        checkpoint_pattern = r'\[CHECKPOINT:\s*(MOISTURE|DEFINITION|SCALP|BREAKAGE)\s*\]'
        match = re.search(checkpoint_pattern, response_text, re.IGNORECASE)
        
        if match:
            category = match.group(1).upper()
            # Remove the checkpoint marker from the message
            clean_message = re.sub(checkpoint_pattern, '', response_text, flags=re.IGNORECASE).strip()
            
            # Map category to vital name
            vital_mapping = {
                "MOISTURE": "moisture",
                "DEFINITION": "definition",
                "SCALP": "scalp",
                "BREAKAGE": "breakage"
            }
            
            return (clean_message, True, vital_mapping[category])
        
        # No checkpoint detected
        return (response_text, False, None)
    
    def _build_prompt(self, history: List[Dict[str, str]], current_message: str) -> str:
        """
        Build the full conversation prompt for the LLM.
        
        Args:
            history: Previous conversation messages
            current_message: Current user message
            
        Returns:
            Formatted prompt string
        """
        prompt_parts = [self.SYSTEM_PROMPT, "\n\nCONVERSATION HISTORY:"]
        
        # Add history
        if not history:
            prompt_parts.append("(No previous messages)")
        else:
            for msg in history:
                role = "User" if msg["role"] == "user" else "Assistant"
                prompt_parts.append(f"{role}: {msg['message']}")
        
        # Add current message
        prompt_parts.append(f"\nUser: {current_message}")
        prompt_parts.append("\nAssistant:")
        
        return "\n".join(prompt_parts)


# Convenience function for easy import
async def diagnose_hair_concern(
    history: List[Dict[str, str]], 
    current_message: str,
    model: str = "gemini-2.5-flash-lite"
) -> Tuple[str, bool, Optional[str]]:
    """
    Convenience function to run a diagnostic conversation.
    
    Args:
        history: Previous conversation messages
        current_message: Current user message
        model: LLM model to use
        
    Returns:
        Tuple of (response_message, handoff_flag, target_vital)
    """
    agent = EmpathDiagnosticAgent(model=model)
    response = await agent.run_diagnostic(history, current_message)
    return agent.parse_response(response)
