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
        

async def generateRoutine(advice: dict) -> dict:
    prompt = routine_prompt(advice)
    model = "gemini-2.5-flash"
    response_text = run_llm_agent(prompt, model)
    #print("Raw LLM response:", response_text)
    cleaned_response = await clean_llm_response(response_text, model)
    
    return cleaned_response['text']
