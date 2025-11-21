import asyncio
from input.lib.find_advice import collateAdvice

from routine.lib.routine_prompt import generateRoutine

# --------------------
# Agent Functions
# --------------------

async def receive_input():
    return {
        "porosity": "Medium Porosity",
        "scalp": "Oily",
        "damage": "Yes",
        "density": "Medium",
        "texture": "Curly"
    }
    

async def processInput(answers):
    step_description = "Classifying input answers to generate advice..."
    print(step_description)
    return collateAdvice(answers)
     

async def processRoutine(directives, routine_flags):
    step_description = "Generating routine based on advice, and flags"
    print(step_description)
    advice = {"directives": directives, "routine_flags": routine_flags}
    routine = await generateRoutine(advice)
    print("Routine generation complete:", routine)
    return routine

async def processProductRecommendations(routine, advice):
    print("Processing product recommendations...")
    return {"products": ["product1", "product2"]}

    
async def finalizeOutput(routine, products):
    print("Finalizing output...")
    return {
        "routine": routine,
        "products": products
    }

# --------------------
# Orchestrator function
# --------------------

async def orchestrator():
    answers = await receive_input()
    advice = await processInput(answers)
    routine = await processRoutine(advice["directives"],advice["routine_flags"])
    product_recommendations = await processProductRecommendations(routine, advice)
    final = await finalizeOutput(routine, product_recommendations)
    return final


if __name__ == "__main__":
    final_output = asyncio.run(orchestrator())
    print("Final Output:", final_output)
