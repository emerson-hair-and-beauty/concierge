from app.agents.recommendation.lib.knowledge_base.query_products import query_products

def parseRoutineStep(step: dict) -> str:
   ingredients = step.get('ingredients', [])
   if isinstance(ingredients, list):
       ingredients_list = ", ".join(ingredients)
   else:
       ingredients_list = str(ingredients)
       
   step_info = f"""
    The user needs to: {step.get('action', 'N/A')}. Find products with the following: {ingredients_list}. Remember to {step.get('notes', 'N/A')}
    Ensure the products fit these criteria.
"""
   return step_info


def createRecommendations(routine: dict) -> list:
    
    routine_steps = routine.get("routine", [])
    updated_routine = []
    
    for step in routine_steps:
        step_instructions = parseRoutineStep(step)
        products = query_products(step_instructions)
        
        updated_step = {
            "step": step.get('step'),
            "action": step.get('action'),
            "ingredients": step.get('ingredients'), 
            "products": products,
            "notes": step.get('notes')
        }
        updated_routine.append(updated_step)
    return updated_routine

   
