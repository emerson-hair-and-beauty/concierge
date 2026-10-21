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


PRODUCTS_PER_STEP = 5


def _unique_by_name(products: list) -> list:
    """The catalogue has some products under several SKUs (e.g. sizes), so the
    same product can match twice. Keep the first, best-ranked one. Names are
    compared on letters and digits only: entries differ in spacing/punctuation."""
    seen, unique = set(), []
    for p in products:
        name = (p.get("metadata") or {}).get("name") or p.get("content", "")
        key = "".join(ch for ch in name.lower() if ch.isalnum())
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


async def createRecommendations(routine: dict):

    routine_steps = routine.get("routine", [])

    for step in routine_steps:
        step_instructions = parseRoutineStep(step)
        # Over-fetch so dropping duplicates still leaves a full set.
        products_data = await query_products(step_instructions, top_k=PRODUCTS_PER_STEP + 3)
        products = _unique_by_name(products_data.get("products", []))[:PRODUCTS_PER_STEP]
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

   
