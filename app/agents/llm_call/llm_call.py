from app.agents.llm_call.provider import stream_text


async def run_llm_agent(prompt: str, model: str = "gemini-3.5-flash", max_retries: int = 5, temperature: float = 0.1):
    """Streaming text generation. Provider is controlled by LLM_PROVIDER in config."""
    async for chunk in stream_text(prompt, temperature=temperature):
        yield chunk
