"""
LLM Provider abstraction.
Change LLM_PROVIDER in app/.env (or environment) to switch everything:
  LLM_PROVIDER=openai   (default)
  LLM_PROVIDER=gemini
"""
import json
import asyncio
from typing import AsyncGenerator, Dict, List

from app.config import LLM_PROVIDER, OPENAI_API_KEY, GEMINI_API_KEY

# ---------------------------------------------------------------------------
# Model config — override via env if needed
# ---------------------------------------------------------------------------
import os

OPENAI_CHAT_MODEL     = os.getenv("OPENAI_CHAT_MODEL",     "gpt-4o-mini")
OPENAI_COMPOSER_MODEL = os.getenv("OPENAI_COMPOSER_MODEL", "gpt-4o")
OPENAI_EMBED_MODEL    = os.getenv("OPENAI_EMBED_MODEL",    "text-embedding-3-small")
EMBED_DIMENSIONS      = int(os.getenv("EMBED_DIMENSIONS",  "384"))

GEMINI_CHAT_MODEL  = os.getenv("GEMINI_CHAT_MODEL",  "gemini-2.5-flash-lite")
GEMINI_EMBED_MODEL = "models/gemini-embedding-001"


# ---------------------------------------------------------------------------
# generate_json — structured single-shot call, returns a dict
# Used by: signal_detector, intent_detector, clarification_generator
# ---------------------------------------------------------------------------

async def generate_json(prompt: str) -> Dict:
    if LLM_PROVIDER == "openai":
        return await _openai_json(prompt)
    return await _gemini_json(prompt)


async def _openai_json(prompt: str) -> Dict:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    response = await client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        messages=[
            {"role": "system", "content": "Respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(response.choices[0].message.content)


async def _gemini_json(prompt: str, schema: Dict | None = None) -> Dict:
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)
    cfg = {"response_mime_type": "application/json"}
    if schema:
        cfg["response_schema"] = schema
    response = await client.aio.models.generate_content(
        model=GEMINI_CHAT_MODEL,
        contents=prompt,
        config=cfg,
    )
    return json.loads(response.text)


# ---------------------------------------------------------------------------
# stream_text — streaming call, yields {"type": "content"|"token_usage", ...}
# Used by: response_composer (via run_llm_agent)
# ---------------------------------------------------------------------------

async def stream_text(prompt: str) -> AsyncGenerator:
    if LLM_PROVIDER == "openai":
        async for chunk in _openai_stream(prompt):
            yield chunk
    else:
        async for chunk in _gemini_stream(prompt):
            yield chunk


async def _openai_stream(prompt: str) -> AsyncGenerator:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    stream = await client.chat.completions.create(
        model=OPENAI_COMPOSER_MODEL,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        temperature=0.1,
    )
    prompt_tokens = 0
    completion_tokens = 0
    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield {"type": "content", "content": delta.content}
        if chunk.usage:
            prompt_tokens     = chunk.usage.prompt_tokens or 0
            completion_tokens = chunk.usage.completion_tokens or 0

    if prompt_tokens or completion_tokens:
        yield {
            "type": "token_usage",
            "model": OPENAI_COMPOSER_MODEL,
            "usage": {
                "prompt_tokens":     prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens":      prompt_tokens + completion_tokens,
            },
        }


async def _gemini_stream(prompt: str) -> AsyncGenerator:
    from google import genai
    from google.genai.errors import ClientError
    client = genai.Client(api_key=GEMINI_API_KEY)
    model_pool = [GEMINI_CHAT_MODEL, "gemini-2.0-flash-lite"]
    model_index = 0
    retries = 0

    while retries <= 5:
        try:
            async for chunk in await client.aio.models.generate_content_stream(
                model=model_pool[model_index], contents=prompt,
                config={"temperature": 0.1},
            ):
                if chunk.candidates:
                    for candidate in chunk.candidates:
                        if candidate.content and candidate.content.parts:
                            for part in candidate.content.parts:
                                if getattr(part, "thought", None):
                                    yield {"type": "thought", "content": str(part.thought)}
                                elif getattr(part, "text", ""):
                                    yield {"type": "content", "content": part.text}
                if chunk.usage_metadata:
                    yield {
                        "type": "token_usage",
                        "model": model_pool[model_index],
                        "usage": {
                            "prompt_tokens":     chunk.usage_metadata.prompt_token_count or 0,
                            "completion_tokens": chunk.usage_metadata.candidates_token_count or 0,
                            "total_tokens":      chunk.usage_metadata.total_token_count or 0,
                        },
                    }
            break
        except ClientError as e:
            err = str(e).upper()
            if "RESOURCE_EXHAUSTED" in err or "429" in err or "NOT_FOUND" in err:
                retries += 1
                model_index = (model_index + 1) % len(model_pool)
                await asyncio.sleep(2 ** retries)
            else:
                raise


# ---------------------------------------------------------------------------
# embed — returns a float vector
# Used by: query_products, index_product_matrix
# ---------------------------------------------------------------------------

async def embed(text: str) -> List[float]:
    if LLM_PROVIDER == "openai":
        return await _openai_embed(text)
    return await _gemini_embed(text)


async def _openai_embed(text: str) -> List[float]:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    response = await client.embeddings.create(
        model=OPENAI_EMBED_MODEL,
        input=text,
        dimensions=EMBED_DIMENSIONS,
    )
    return response.data[0].embedding


async def _gemini_embed(text: str) -> List[float]:
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = await client.aio.models.embed_content(
        model=GEMINI_EMBED_MODEL,
        contents=text,
        config={"output_dimensionality": EMBED_DIMENSIONS},
    )
    return response.embeddings[0].values
