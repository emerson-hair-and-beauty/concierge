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


async def run_llm_agent(prompt: str, model: str):
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    async for chunk in await client.aio.models.generate_content_stream(
        model=model,
        contents=prompt,
        config={
            "thinking_config": {
                "include_thoughts": True,
                "thinking_budget": 1024
            }
        }
    ):
        # Extract thinking if available in the parts
        has_thought_in_chunk = False
        if chunk.candidates and chunk.candidates[0].content.parts:
            for part in chunk.candidates[0].content.parts:
                thought_value = getattr(part, 'thought', None)
                if thought_value:
                    # If thought_value is a string, it's the reasoning
                    if isinstance(thought_value, str):
                        yield {"type": "thought", "content": thought_value}
                        has_thought_in_chunk = True
                    # If thought_value is True, reasoning is in the part's text
                    elif thought_value is True:
                        reasoning = getattr(part, 'text', '')
                        if reasoning:
                            yield {"type": "thought", "content": reasoning}
                            has_thought_in_chunk = True
        
        # Extract regular text content
        # We only yield as "content" if it wasn't already identified as "thought"
        if chunk.text and not has_thought_in_chunk:
            yield {"type": "content", "content": chunk.text}
