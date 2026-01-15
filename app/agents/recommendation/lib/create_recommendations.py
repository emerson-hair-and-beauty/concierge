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


async def createRecommendations(routine: dict):
    
    routine_steps = routine.get("routine", [])
    
    for step in routine_steps:
        step_instructions = parseRoutineStep(step)
        products_data = await query_products(step_instructions)
        products = products_data.get("products", [])
        usage = products_data.get("embedding_usage")
        
        if usage:
            yield {"type": "embedding_usage", "content": usage}

        updated_step = {
            "step": step.get('step'),
            "action": step.get('action'),
            "ingredients": step.get('ingredients'), 
            "products": products,
            "notes": step.get('notes')
        }
        yield {"type": "step", "content": updated_step}

   
