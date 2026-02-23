"""
Summarizer Agent
Generates a dense diagnostic summary and extracts technical keywords 
from chat history for the Empath Diagnostic Engine.
"""

import json
import logging
import re
from typing import List, Dict, Tuple
from app.agents.llm_call.llm_call import run_llm_agent

# Configure logger
logger = logging.getLogger(__name__)

class EmpathSummarizer:
    """
    Utility agent to condense diagnostic conversations into structured summaries.
    """
    
    SYSTEM_PROMPT = """You are a Technical Hair Analyst. 
Goal: Summarize a conversation between a User and a Hair Empath into a dense diagnostic report.

OUTPUT FORMAT:
Return a JSON object with EXACTLY the following keys:
- "summary": A 1-2 sentence dense summary focusing on the symptoms and timeline.
- "keywords": A list of 3-5 technical hair terms mentioned or inferred.

CRITICAL RULES:
- ONLY return the JSON object. 
- DO NOT add any preambles, notes, or markdown formatting (like ```json).
- Be technical and precise.
- Focus on the primary hair concern diagnosed.
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
            
        prompt_parts.append("\nJSON REPORT:")
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
        try:
            # Clean potential markdown artifacts
            clean_text = text.strip()
            if clean_text.startswith("```"):
                clean_text = re.sub(r'^```(json)?', '', clean_text)
                clean_text = re.sub(r'```$', '', clean_text).strip()
            
            data = json.loads(clean_text)
            summary = data.get("summary", "Summary generation failed.")
            keywords = data.get("keywords", [])
            return summary, keywords
            
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"[Summarizer] Failed to parse JSON output: {str(e)}. Raw text: {text}")
            
            # Fallback to legacy parsing if it looks like it's still using the old format
            # or just return the first line as summary
            summary = ""
            keywords = []
            
            lines = text.strip().split('\n')
            for line in lines:
                if "SUMMARY:" in line.upper():
                    summary = line.split(":", 1)[1].strip()
                elif "KEYWORDS:" in line.upper():
                    kw_str = line.split(":", 1)[1].strip()
                    keywords = [k.strip() for k in kw_str.split(',') if k.strip()]
            
            if not summary:
                summary = text.split('\n')[0][:100] + "..." if len(text) > 100 else text
                
            return summary, keywords

async def summarize_diagnostic(history: List[Dict[str, str]], model: str = "gemini-2.5-flash-lite") -> Tuple[str, List[str]]:
    """Helper function to run the summarizer."""
    summarizer = EmpathSummarizer(model=model)
    return await summarizer.summarize(history)
