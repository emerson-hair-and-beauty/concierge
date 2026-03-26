import asyncio
import json
from app.api.models import OrchestratorInput
from app.agents.input.lib.find_advice import collateAdvice
from app.agents.routine.lib.routine_prompt import routine_prompt

async def simulate_flow():
    print("==================================================")
    print("1. THE INCOMING QUERY (CLIENT PAYLOAD)")
    print("==================================================")
    
    payload = {
        "user_id": "simulation-user",
        "first_name": "Maya",
        "email": "maya@example.com",
        "location": "Dubai, UAE",
        "gender": "Female",
        "hair_length": "Shoulder Length",
        "texture": "Spring curls",
        "density": "Fine",
        "moisture_behaviour": "Low Porosity",
        "humidity_response": "Lose definition",
        "hair_goals": ["Volume", "Frizz control", "Lightweight hold"]
    }
    print(json.dumps(payload, indent=2))
    
    print("\n\n==================================================")
    print("2. THE CLASSIFIERS & ADVICE COLLATION")
    print("==================================================")
    
    advice = collateAdvice(payload)
    print("--- Goals ---")
    print(advice["goals"])
    print("\n--- Directives (Classifier Output) ---")
    for trait, text in advice["directives"].items():
         print(f"{trait.title()}: {text}")
    print("\n--- Routine Flags ---")
    print(json.dumps(advice["routine_flags"], indent=2))
    
    print("\n\n==================================================")
    print("3. THE GENERATED PROMPT")
    print("==================================================")
    
    prompt = routine_prompt(advice)
    
    print("--- PROMPT TEMPLATE ---")
    print(prompt)
    
    print("\n\n==================================================")
    print("4. THE LLM RESPONSE (STREAMING)")
    print("==================================================")
    
    # We will invoke generateRoutine directly to see the response
    from app.agents.routine.lib.routine_prompt import generateRoutine
    
    full_response = ""
    async for chunk in generateRoutine(advice):
        if chunk["type"] == "content":
            text = chunk["content"]
            full_response += text
            print(text, end="", flush=True)
            
    print("\n\n==================================================")
    print("FLOW COMPLETE")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(simulate_flow())
