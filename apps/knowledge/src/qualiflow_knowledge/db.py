from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .settings import settings

engine = create_async_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def org_scoped_session(org_id: str) -> AsyncGenerator[AsyncSession, None]:
    """Same RLS-scoping mechanism as apps/api/db.py's get_org_scoped_db —
    set_config(..., is_local=true), transaction-scoped, never leaks
    across a pooled connection.

    DELIBERATE SIMPLIFICATION (flag, don't hide): unlike apps/api, this
    takes org_id as a plain argument rather than deriving it from a
    verified JWT — apps/knowledge has no Keycloak integration yet. The
    RLS mechanism itself doesn't care where org_id came from, but this
    endpoint is NOT safe to expose to untrusted callers until it does.
    Revisit when a shared auth package exists (likely alongside
    generate_tests, which will need the same verification apps/api
    already has)."""
    async with SessionLocal() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.current_org_id', :org_id, true)"),
                {"org_id": org_id},
            )
            yield session
