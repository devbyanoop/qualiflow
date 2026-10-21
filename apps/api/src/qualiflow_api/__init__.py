import asyncio
import sys

# psycopg's async mode can't use Windows' default ProactorEventLoop —
# only SelectorEventLoop. This lives in the package's own __init__ (run
# before ANY submodule, by every entry point — uvicorn, pytest, alembic,
# a test that creates its own engine directly) rather than in db.py,
# which not every caller necessarily imports.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
