"""One-time setup for LangGraph's Postgres checkpointer tables
(checkpoints, checkpoint_blobs, checkpoint_writes, checkpoint_migrations).

Run once per fresh database as the superuser (these are CREATE TABLE
statements; qualiflow_app has no schema-level privileges):

    uv run --project apps/agents python apps/agents/scripts/setup_checkpointer.py

Then grant the restricted role access (qualiflow_app only has
row-level grants on tables it's explicitly given, never schema-wide):

    docker exec qualiflow-postgres-1 psql -U qualiflow -d qualiflow -c \
      "GRANT SELECT, INSERT, UPDATE, DELETE ON checkpoint_migrations, \
       checkpoints, checkpoint_blobs, checkpoint_writes TO qualiflow_app;"

Known gap, noted not hidden: these tables are LangGraph's own schema,
with no org_id column -- RLS (ADR-004) doesn't apply here the way it
does to our own tables. Thread IDs are namespaced with org_id/feature_id
as an application-level mitigation (see generate_tests.py), not a
database-enforced guarantee like the rest of this system has. Revisit
if/when this matters for real multi-tenant isolation.
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # noqa: E402

from qualiflow_agents.settings import settings  # noqa: E402


async def main() -> None:
    # Plain libpq URI (no +psycopg) -- the checkpointer isn't going
    # through SQLAlchemy, so it doesn't want that prefix.
    admin_uri = settings.database_url_admin.replace("postgresql+psycopg://", "postgresql://")
    async with AsyncPostgresSaver.from_conn_string(admin_uri) as saver:
        await saver.setup()
    print("Checkpointer tables created. Now run the GRANT statement in this file's docstring.")


if __name__ == "__main__":
    asyncio.run(main())
