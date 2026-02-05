import asyncio
import json
import re
from app.agents.input.lib.find_advice import collateAdvice
from app.agents.routine.lib.routine_prompt import generateRoutine
from app.api.models import OrchestratorInput
from app.utils.cost_calculator import calculate_gemini_cost, calculate_embedding_cost

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
    try:
        # Initialize token tracking
        total_routine_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        total_embedding_usage = {"prompt_tokens": 0, "total_tokens": 0, "calls": 0}

        yield json.dumps({"type": "status", "content": "Processing your input..."}) + "\n"
        answers_dict = await receive_input(answers)
        advice = await processInput(answers_dict)
        
        yield json.dumps({"type": "status", "content": "Generating routine..."}) + "\n"
        
        full_routine_text = ""
        # generateRoutine is now an async generator
        async for chunk in generateRoutine(advice):
            if chunk.get("type") == "token_usage":
                u = chunk["usage"]
                total_routine_usage["prompt_tokens"] += u.get("prompt_tokens", 0)
                total_routine_usage["completion_tokens"] += u.get("completion_tokens", 0)
                total_routine_usage["total_tokens"] += u.get("total_tokens", 0)
                continue

            yield json.dumps(chunk) + "\n"
            if chunk["type"] == "content":
                full_routine_text += chunk["content"]
                
        # Clean and parse the routine for product recommendations
        cleaned_text = re.sub(r"```json|```", "", full_routine_text).strip()
        try:
            routine_json = json.loads(cleaned_text)
        except Exception as e:
            yield json.dumps({"type": "error", "content": f"Failed to parse routine: {str(e)}", "raw": cleaned_text}) + "\n"
            return

        
        # Accumulate the final routine structure with products
        final_routine_for_db = routine_json.copy()
        final_routine_for_db["routine"] = [] # Reset steps to populate with full product info
        
        yield json.dumps({"type": "status", "content": "Creating product recommendations..."}) + "\n"
        
        async for recommendation_chunk in processProductRecommendations(routine_json):
            # Handle embedding usage
            if recommendation_chunk.get("type") == "embedding_usage":
                u = recommendation_chunk["content"].get("usage", {})
                total_embedding_usage["prompt_tokens"] += u.get("prompt_tokens", 0)
                total_embedding_usage["total_tokens"] += u.get("total_tokens", 0)
                total_embedding_usage["calls"] += 1
                continue
            
            # Handle actual product steps
            if recommendation_chunk.get("type") == "step":
                step_content = recommendation_chunk["content"]
                # Add to DB object
                final_routine_for_db["routine"].append(step_content)
                # Stream to client
                yield json.dumps({"type": "product_recommendation", "content": step_content}) + "\n"
        
        # Save complete routine to Supabase if user_id is present
        if answers.user_id:
            try:
                from app.services.db_service import get_db
                db = get_db()
                db.save_routine(answers.user_id, final_routine_for_db)
                yield json.dumps({"type": "status", "content": "Routine saved to your profile!"}) + "\n"
            except Exception as e:
                print(f"Failed to save routine: {e}")
                yield json.dumps({"type": "error", "content": "Failed to save routine to profile"}) + "\n"
        
        yield json.dumps({"type": "status", "content": "All recommendations complete!"}) + "\n"

        # Calculate and yield token summary
        # Thinking tokens are billed as output, so derived output_tokens = total - prompt
        derived_output_tokens = total_routine_usage["total_tokens"] - total_routine_usage["prompt_tokens"]
        cost_routine = calculate_gemini_cost("gemini-2.5-flash-lite", total_routine_usage["prompt_tokens"], derived_output_tokens)
        cost_embedding = calculate_embedding_cost("text-embedding-004", total_embedding_usage["total_tokens"])
        total_cost = cost_routine + cost_embedding
        
        grand_total_tokens = total_routine_usage["total_tokens"] + total_embedding_usage["total_tokens"]
        
        summary = {
            "type": "token_summary",
            "content": {
                "routine_generation": {
                    "model": "gemini-2.5-flash-lite",
                    **total_routine_usage
                },
                "embeddings": {
                    "model": "text-embedding-004",
                    **total_embedding_usage
                },
                "grand_total_tokens": grand_total_tokens,
                "estimated_cost_usd": total_cost
            }
        }
        yield json.dumps(summary) + "\n"
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        yield json.dumps({"type": "error", "content": f"Orchestrator internal error: {str(e)}", "details": error_details}) + "\n"


if __name__ == "__main__":
    final_output = asyncio.run(orchestrator())
    print("Final Output:", final_output)
