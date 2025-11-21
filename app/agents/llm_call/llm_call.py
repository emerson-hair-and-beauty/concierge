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


def run_llm_agent(prompt: str, model: str) -> str:
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
    )
    return response
