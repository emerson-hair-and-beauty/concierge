from recommendation.lib.knowledge_base.query_products import query_products

def parseRoutineStep(step: dict) -> dict:
   
   ingredients_list = ", ".join(step['ingredients'])
   step_info = f"""
    The user needs to: {step['action']}. Find products with the following: {ingredients_list}. Remember to {step['notes']}
    Ensure the products fit these criteria.

"""
   return step_info


def createRecommendations(routine: dict) -> dict:
    
    routine_steps = routine.get("routine", [])
    updated_routine = []
    
    for step in routine_steps:
        step_instructions = parseRoutineStep(step)
        products= query_products(step_instructions)
        
        updated_step = {
            "step": step['step'],
            "action": step['action'],
            "ingredients": step['ingredients'], 
            "products": products,
            "notes": step['notes']
        }
        updated_routine.append(updated_step)
    return updated_routine
        

   
