import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

# Same reasoning as apps/api/src/qualiflow_api/settings.py — load here,
# in the package's own __init__ (runs before any submodule, from any
# entry point: pytest, uvicorn, a plain script), so GROQ_API_KEY etc.
# land in the process environment the same way regardless of how this
# gets run. parents[4] from this file is the repo root.
load_dotenv(Path(__file__).resolve().parents[4] / ".env")

# Same psycopg/Windows ProactorEventLoop fix as apps/api and
# apps/knowledge — not needed until generate_tests.py added real DB
# access via retrieve_context. For entry points that create their loop
# AFTER this import (pytest; the __main__ launcher in main.py builds
# its own loop explicitly either way) this is sufficient; uvicorn's own
# CLI invocation would still need the explicit-loop pattern in main.py.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
