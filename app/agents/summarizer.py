"""
Summarizer Agent
Generates a dense diagnostic summary and extracts technical keywords 
from chat history for the Empath Diagnostic Engine.
"""

from typing import List, Dict, Tuple
from app.agents.llm_call.llm_call import run_llm_agent

class EmpathSummarizer:
    """
    Utility agent to condense diagnostic conversations into structured summaries.
    """
    
    SYSTEM_PROMPT = """You are a Technical Hair Analyst. 
Goal: Summarize a conversation between a User and a Hair Empath into a dense diagnostic report.

OUTPUT FORMAT:
1. SUMMARY: A 1-2 sentence dense summary focusing on the symptoms and timeline (e.g., "User reporting high breakage on Day 5, specifically when brushing dry hair.").
2. KEYWORDS: A comma-separated list of 3-5 technical hair terms mentioned or inferred (e.g., "mechanical damage, cuticle fatigue, low elasticity").

CONSTRAINTS:
- Be technical and precise.
- Focus on the primary hair concern diagnosed.
- If Wash Day or Day in Cycle was mentioned, include it.
"""

    def __init__(self, model: str = "gemini-2.5-flash-lite"):
        self.model = model

    def _build_prompt(self, history: List[Dict[str, str]]) -> str:
        prompt_parts = [
            self.SYSTEM_PROMPT,
            "\nCONVERSATION HISTORY:"
        ]
        
        for msg in history:
            role = "User" if msg["role"] == "user" else "Assistant"
            prompt_parts.append(f"{role}: {msg['message']}")
            
        prompt_parts.append("\nTECHNICAL REPORT:")
        return "\n".join(prompt_parts)

    async def summarize(self, history: List[Dict[str, str]]) -> Tuple[str, List[str]]:
        """
        Summarizes the history and returns (summary, keywords).
        """
        prompt = self._build_prompt(history)
        
        full_response = ""
        async for chunk in run_llm_agent(prompt, self.model):
            if chunk.get("type") == "content":
                full_response += chunk.get("content", "")
        
        return self._parse_summary_output(full_response)

    def _parse_summary_output(self, text: str) -> Tuple[str, List[str]]:
        """Parses the LLM output into summary and keywords."""
        summary = ""
        keywords = []
        
        lines = text.strip().split('\n')
        for line in lines:
            if line.upper().startswith("SUMMARY:"):
                summary = line[8:].strip()
            elif line.upper().startswith("KEYWORDS:"):
                kw_str = line[9:].strip()
                keywords = [k.strip() for k in kw_str.split(',') if k.strip()]
                
        # Fallback if parsing fails
        if not summary:
            summary = text.split('\n')[0]
        
        return summary, keywords

async def summarize_diagnostic(history: List[Dict[str, str]], model: str = "gemini-2.5-flash-lite") -> Tuple[str, List[str]]:
    """Helper function to run the summarizer."""
    summarizer = EmpathSummarizer(model=model)
    return await summarizer.summarize(history)
