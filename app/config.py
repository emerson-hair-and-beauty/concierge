from dotenv import load_dotenv
import os

# Load environment variables from .env located next to this file. Using an
# explicit path ensures the key is loaded whether the package is imported
# from the repository root or the module is executed directly.
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not found in app/.env or environment")

#print("GEMINI_API_KEY loaded:", GEMINI_API_KEY is not None)




