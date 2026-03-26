from app.agents.llm_call.llm_call import run_llm_agent
from .save_response import parse_gemini_response
import json

def routine_prompt(advice: dict) -> dict:
    """
    Build a RoutineAgent prompt from the collated advice object.

    advice: {
        "goals": "Long-lasting definition, Frizz control",  ← primary objective
        "directives": { texture: "...", density: "...", ... },  ← guardrails
        "routine_flags": { texture: [...], density: [...], ... }
    }
    """
    goals = advice.get("goals", "General curl health")
    directives = advice.get("directives", {})
    routine_flags = advice.get("routine_flags", {})

    # Flatten flags into a readable list
    all_flags = []
    for flag_list in routine_flags.values():
        all_flags.extend(flag_list)
    flags_text = ", ".join(sorted(set(all_flags))) if all_flags else "standard_care"

    prompt = f"""
You are the RoutineAgent for Emerson Curl Concierge.
Your job is to create a personalised 5-step wash day routine.

== PRIMARY GOAL ==
The routine MUST be designed to achieve the following for this user:
  {goals}

Every step in the routine should directly serve this goal. Prioritise steps and ingredients that help achieve it.

== CONSTRAINTS ==
You must respect the following hair profile guardrails. These are facts about the user's hair that constrain HOW you achieve the goal:

{directives}

Active routine flags (these restrict or shape product and method choices):
  {flags_text}

== RULES ==
- Do NOT recommend specific product names; another agent handles that.
- Do NOT guess traits or add information not provided.
- The routine must feel like a professional curl consultation recommendation.
- GCC climate context: the routine should account for high-humidity conditions.

Output JSON (exact format):
{{
  "goal": "{goals}",
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
