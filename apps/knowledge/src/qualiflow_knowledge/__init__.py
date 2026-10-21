import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

# Same pattern as apps/api and apps/agents — see their __init__.py for why.
load_dotenv(Path(__file__).resolve().parents[4] / ".env")

# Same psycopg/Windows ProactorEventLoop fix as apps/api/db.py — forgot
# it here on first write even though this service also opens an async
# Postgres connection; caught by actually running it, not by remembering.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
