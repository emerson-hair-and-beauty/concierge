from google import genai
import os
import sys

# Prefer absolute import when package is available. When this module is
# executed directly (e.g. python app/agents/llm_call/llm_call.py) the
# `app` package may not be on sys.path, so fall back to inserting the
# repository root into sys.path and retry the import.
try:
    from app.config import GEMINI_API_KEY
except Exception:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from app.config import GEMINI_API_KEY


# Fallback model pool to handle rate limits and availability
MODEL_POOL = [
    "gemini-2.5-flash-lite", 
    "gemini-2.0-flash-lite"
]

async def run_llm_agent(prompt: str, model: str = None, max_retries: int = 5):
    """
    Run LLM agent with automatic retry and model fallback logic.
    """
    import asyncio
    from google.genai.errors import ClientError
    
    # Use provided model or default to first in pool
    current_model = model if model else MODEL_POOL[0]
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    retry_count = 0
    model_index = 0
    
    while retry_count <= max_retries:
        try:
            # Prepare config based on model
            generation_config = {}
            if current_model and "thinking" in current_model:
                generation_config["thinking_config"] = {
                    "include_thoughts": True,
                    "thinking_budget": 1024
                }
            
            async for chunk in await client.aio.models.generate_content_stream(
                model=current_model,
                contents=prompt,
                config=generation_config
            ):
                if chunk.candidates:
                    for candidate in chunk.candidates:
                        if candidate.content and candidate.content.parts:
                            for part in candidate.content.parts:
                                # Handle Thinking/Thoughts
                                thought_value = getattr(part, 'thought', None)
                                if thought_value:
                                    yield {"type": "thought", "content": str(thought_value)}
                                    continue
                                
                                # Handle final text content
                                text_value = getattr(part, 'text', '')
                                if text_value:
                                    yield {"type": "content", "content": text_value}
                                    
                if chunk.usage_metadata:
                     yield {
                        "type": "token_usage",
                        "model": current_model,
                        "usage": {
                            "prompt_tokens": chunk.usage_metadata.prompt_token_count or 0,
                            "completion_tokens": chunk.usage_metadata.candidates_token_count or 0,
                            "total_tokens": chunk.usage_metadata.total_token_count or 0
                        }
                    }
            
            # Success!
            break
            
        except ClientError as e:
            error_str = str(e).upper()
            is_rate_limit = "RESOURCE_EXHAUSTED" in error_str or "429" in error_str
            is_invalid_model = "NOT_FOUND" in error_str or "INVALID_ARGUMENT" in error_str
            
            if is_rate_limit or is_invalid_model:
                retry_count += 1
                if retry_count > max_retries:
                    raise e
                
                # Model Fallback: Switch to next model in pool
                model_index = (model_index + 1) % len(MODEL_POOL)
                old_model = current_model
                current_model = MODEL_POOL[model_index]
                
                delay = 2 ** retry_count # Exponential backoff
                print(f"[LLM] Error with {old_model}. Switching to {current_model}. Waiting {delay}s...")
                await asyncio.sleep(delay)
            else:
                raise e

