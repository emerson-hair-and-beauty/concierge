import asyncio
from input.lib.find_advice import collateAdvice
from recommendation.lib.create_recommendations import createRecommendations
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

async def processProductRecommendations(routine):
    products = createRecommendations(routine)
    return products

    
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
    final_output = await processProductRecommendations(routine)
    #print("Product recommendations complete:", final_output)
    return final_output


if __name__ == "__main__":
    final_output = asyncio.run(orchestrator())
    print("Final Output:", final_output)
