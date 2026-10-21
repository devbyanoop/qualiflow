from pathlib import Path

from dotenv import load_dotenv

# Same reasoning as apps/api/src/qualiflow_api/settings.py — load here,
# in the package's own __init__ (runs before any submodule, from any
# entry point: pytest, uvicorn, a plain script), so GROQ_API_KEY etc.
# land in the process environment the same way regardless of how this
# gets run. parents[4] from this file is the repo root.
load_dotenv(Path(__file__).resolve().parents[4] / ".env")
