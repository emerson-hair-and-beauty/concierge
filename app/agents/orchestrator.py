import asyncio
import json
import re
from app.agents.input.lib.find_advice import collateAdvice
from app.agents.routine.lib.routine_prompt import generateRoutine
from app.api.models import OrchestratorInput

# --------------------
# Agent Functions
# --------------------

async def receive_input(answers: OrchestratorInput):
    return answers.model_dump()
    

async def processInput(answers):
    return collateAdvice(answers)
     

async def processRoutine(directives, routine_flags):
    step_description = "Generating routine based on advice, and flags"
    print(step_description)
    advice = {"directives": directives, "routine_flags": routine_flags}
    routine = await generateRoutine(advice)
    #print("Routine generation complete:", routine)
    return routine

async def processProductRecommendations(routine):
    from app.agents.recommendation.lib.create_recommendations import createRecommendations
    async for step_with_products in createRecommendations(routine):
        yield step_with_products

    
async def finalizeOutput(routine, products):
    print("Finalizing output...")
    return {
        "routine": routine,
        "products": products
    }

# --------------------
# Orchestrator function
# --------------------

async def orchestrator(answers: OrchestratorInput):
    yield json.dumps({"type": "status", "content": "Processing your input..."}) + "\n"
    answers_dict = await receive_input(answers)
    advice = await processInput(answers_dict)
    
    yield json.dumps({"type": "status", "content": "Generating routine..."}) + "\n"
    
    full_routine_text = ""
    # generateRoutine is now an async generator
    async for chunk in generateRoutine(advice):
        yield json.dumps(chunk) + "\n"
        if chunk["type"] == "content":
            full_routine_text += chunk["content"]
            
    # Clean and parse the routine for product recommendations
    cleaned_text = re.sub(r"```json|```", "", full_routine_text).strip()
    try:
        routine_json = json.loads(cleaned_text)
    except Exception as e:
        yield json.dumps({"type": "error", "content": f"Failed to parse routine: {str(e)}"}) + "\n"
        return

    yield json.dumps({"type": "status", "content": "Creating product recommendations..."}) + "\n"
    async for recommendation_chunk in processProductRecommendations(routine_json):
        yield json.dumps({"type": "product_recommendation", "content": recommendation_chunk}) + "\n"
    
    yield json.dumps({"type": "status", "content": "All recommendations complete!"}) + "\n"


if __name__ == "__main__":
    final_output = asyncio.run(orchestrator())
    print("Final Output:", final_output)
