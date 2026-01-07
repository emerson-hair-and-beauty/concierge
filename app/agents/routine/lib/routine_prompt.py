from app.agents.llm_call.llm_call import run_llm_agent
from .save_response import parse_gemini_response
import json

def routine_prompt(advice: dict) -> dict:
    """
    Build a RoutineAgent prompt from directives and routine_flags,
    send it to the LLM, and return structured JSON.
    
    advice: {
        "directives": { porosity: "...", scalp: "...", ... },
        "routine_flags": { porosity: [...], scalp: [...], ... }
    }
    """
    prompt = f"""
You are the RoutineAgent.
Create a personalized 5-step hair care routine using ONLY the info provided.
Do NOT guess traits or add extra information.
Do NOT recommend specific products; another agent handles that.

Directives:
{advice['directives']}

Routine Flags:
{advice['routine_flags']}

Output JSON (exact format):
{{
  "routine": [
    {{
      "step": "Cleanse",
      "action": "...",
      "ingredients": ["...", "..."],
      "notes": "..."
    }},
    {{
      "step": "Condition",
      "action": "...",
      "ingredients": ["...", "..."],
      "notes": "..."
    }},
    {{
      "step": "Treat",
      "action": "...",  
      "ingredients": ["...", "..."],
      "notes": "..."
    }},
    {{
      "step": "Moisturize / Prep",
      "action": "...",
      "ingredients": ["...", "..."],
      "notes": "..."
    }},
    {{
      "step": "Style & Protect",
      "action": "...",
      "ingredients": ["...", "..."],
      "notes": "..."
    }}
  ]
}}

Return ONLY valid JSON.
"""
    print(prompt)
    return prompt

async def clean_llm_response(response_text: str, model):
      cleaned_response = parse_gemini_response(response_text)
      return cleaned_response
        

async def generateRoutine(advice: dict):
    prompt = routine_prompt(advice)
    model = "gemini-2.5-flash-lite"
    
    full_text = ""
    async for chunk in run_llm_agent(prompt, model):
        yield chunk
        if chunk["type"] == "content":
            full_text += chunk["content"]
    
    # We don't return here anymore, we yield chunks. 
    # The caller (orchestrator) will need the final full_text to parse JSON and proceed.
    # We can yield a special chunk at the end or the caller can accumulate.
    # To keep it simple, after the loop finishes, the caller has the full text if they accumulated it.
