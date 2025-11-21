Developer notes — running and testing locally

Quick steps to get the project running locally for development and testing:

1) Create a Python virtual environment (recommended)

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2) Install dependencies

```bash
python3 -m pip install -r requirements.txt
```

3) Ensure the Gemini API key is available

- The project expects a `.env` file next to `app/config.py` (the file `app/.env` is used by default).
- The key should be named `GEMINI_API_KEY`.

4) Run a quick import test (from repository root)

```bash
python3 -m pip install -r requirements.txt
python3 -c "from app.agents.llm_call import llm_call; print('Imported OK', hasattr(llm_call, 'run_llm_agent'))"
```

5) Running modules

- Prefer running modules as packages so absolute imports work reliably:

```bash
python -m app.agents.llm_call.llm_call
```

- If you need to run a module as a script directly, the code includes a small sys.path fallback that adds the repository root to `sys.path` so imports like `from app.config import ...` still work.

Notes

- `app/__init__.py` was added so that `app` is recognized as a package by Python.
- `app/config.py` now loads `app/.env` explicitly which avoids missing-key errors when importing from the repository root.
- If you prefer to store sensitive credentials in your shell environment instead of `.env`, set `GEMINI_API_KEY` in your environment before running.
