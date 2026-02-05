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


async def run_llm_agent(prompt: str, model: str, max_retries: int = 3):
    """
    Run LLM agent with automatic retry logic for rate limiting.
    
    Args:
        prompt: The prompt to send to the LLM
        model: The model name (e.g., 'gemini-2.5-flash-lite')
        max_retries: Maximum number of retry attempts (default: 3)
    """
    import asyncio
    from google.genai.errors import ClientError
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # Prepare config based on model
    generation_config = {}
    if "thinking" in model:
        generation_config["thinking_config"] = {
            "include_thoughts": True,
            "thinking_budget": 1024
        }
    
    retry_count = 0
    while retry_count <= max_retries:
        try:
            async for chunk in await client.aio.models.generate_content_stream(
                model=model,
                contents=prompt,
                config=generation_config
            ):
                # A chunk can have multiple candidates, each with multiple parts
                if chunk.candidates:
                    for candidate in chunk.candidates:
                        if candidate.content and candidate.content.parts:
                            for part in candidate.content.parts:
                                # 1. Handle Thinking/Thoughts
                                thought_value = getattr(part, 'thought', None)
                                if thought_value:
                                    if isinstance(thought_value, str):
                                        yield {"type": "thought", "content": thought_value}
                                    elif thought_value is True:
                                        reasoning = getattr(part, 'text', '')
                                        if reasoning:
                                            yield {"type": "thought", "content": reasoning}
                                    continue # Successfully handled as thought, skip to next part
                                
                                # 2. Handle final text content
                                text_value = getattr(part, 'text', '')
                                if text_value:
                                    yield {"type": "content", "content": text_value}
                                    
                # 3. Handle Token Usage
                if chunk.usage_metadata:
                     yield {
                        "type": "token_usage",
                        "source": "routine_generation",
                        "model": model,
                        "usage": {
                            "prompt_tokens": chunk.usage_metadata.prompt_token_count or 0,
                            "completion_tokens": chunk.usage_metadata.candidates_token_count or 0,
                            "total_tokens": chunk.usage_metadata.total_token_count or 0
                        }
                    }
            
            # If we successfully completed, break out of retry loop
            break
            
        except ClientError as e:
            # Check if it's a rate limit error
            error_str = str(e)
            if "retryDelay" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                retry_count += 1
                if retry_count > max_retries:
                    print(f"[LLM ERROR] Max retries ({max_retries}) exceeded. Rate limit still active.")
                    raise e
                
                # Extract retry delay from error (default to exponential backoff)
                import re
                delay_match = re.search(r"'retryDelay':\s*'(\d+)s'", error_str)
                if delay_match:
                    delay = int(delay_match.group(1))
                else:
                    # Exponential backoff: 2^retry_count seconds
                    delay = 2 ** retry_count
                
                print(f"[LLM] Rate limited. Waiting {delay}s before retry {retry_count}/{max_retries}...")
                await asyncio.sleep(delay)
            else:
                # Not a rate limit error, re-raise
                raise e

