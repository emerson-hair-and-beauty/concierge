from typing import AsyncGenerator, Dict

from app.agents.llm_call.llm_call import run_llm_agent
from app.agents.recommendation.lib.knowledge_base.query_products import query_products

_REPAIR_PROMPT = """\
You are a professional curl and hair health specialist. The user's hair is currently experiencing active breakage — strands are snapping, shedding excessively, or structurally weakened.

Your job is to give them a clear, compassionate repair-first response. Do not recommend a full routine or products yet. Focus on:
- What is likely causing the breakage
- Immediate steps to stop further damage
- What to avoid right now

Keep the tone warm and expert. Be specific and actionable.

User context:
{user_context}"""

_RESET_PROMPT = """\
You are a professional curl and hair health specialist. The user's hair is showing signs of buildup or blocked absorption — products are sitting on the surface, the hair feels heavy or unresponsive, or moisture won't penetrate.

Your job is to give them a clear, focused reset-first response. Do not recommend a full routine or products yet. Focus on:
- Why a reset is needed before anything else will work
- How to do a proper clarifying or reset wash
- What to expect after the reset

Keep the tone warm and expert. Be specific and actionable.

User context:
{user_context}"""

_PRODUCT_QUERIES = {
    "repair_first": "protein treatment bond repair strengthening breakage curl recovery",
    "reset_first": "clarifying shampoo chelating treatment scalp buildup removal deep cleanse",
}


def _build_hair_type_string(user_context: Dict) -> str:
    parts = [
        user_context.get("texture"),
        user_context.get("density"),
        user_context.get("moisture_behaviour"),
    ]
    return " ".join(p for p in parts if p)


async def _stream_targeted_products(decision_state: str, user_context: Dict) -> AsyncGenerator:
    base_query = _PRODUCT_QUERIES[decision_state]
    hair_type = _build_hair_type_string(user_context)
    query = f"{base_query} {hair_type}".strip()
    products_data = await query_products(query, top_k=5)

    usage = products_data.get("embedding_usage")
    if usage:
        yield {"type": "embedding_usage", "content": usage}

    for product in products_data.get("products", []):
        yield {"type": "targeted_product", "content": product}


async def repair_first_handler(user_context: Dict) -> AsyncGenerator:
    prompt = _REPAIR_PROMPT.format(user_context=user_context)
    async for chunk in run_llm_agent(prompt):
        yield chunk

    async for chunk in _stream_targeted_products("repair_first", user_context):
        yield chunk


async def reset_first_handler(user_context: Dict) -> AsyncGenerator:
    prompt = _RESET_PROMPT.format(user_context=user_context)
    async for chunk in run_llm_agent(prompt):
        yield chunk

    async for chunk in _stream_targeted_products("reset_first", user_context):
        yield chunk
