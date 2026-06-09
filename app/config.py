from dotenv import load_dotenv
import os

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

# Active provider — change this one value to switch everything
# Options: "openai" | "gemini"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")

OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_KEY", "")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")

WEATHER_API_KEY       = os.getenv("WEATHER_API_KEY", "")
OPEN_WEATHER_API_KEY  = os.getenv("OPEN_WEATHER_API_KEY", "")

if LLM_PROVIDER == "openai" and not OPENAI_API_KEY:
    raise RuntimeError("LLM_PROVIDER=openai but OPENAI_API_KEY not found in app/.env or environment")

if LLM_PROVIDER == "gemini" and not GEMINI_API_KEY:
    raise RuntimeError("LLM_PROVIDER=gemini but GEMINI_API_KEY not found in app/.env or environment")
