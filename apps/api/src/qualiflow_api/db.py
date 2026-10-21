from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .auth import verify_token
from .settings import settings

# The APP's engine — connects as qualiflow_app, never the superuser.
engine = create_async_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_org_scoped_db(claims: dict = Depends(verify_token)) -> AsyncGenerator[AsyncSession, None]:
    """Simplification for the Walking Skeleton: one Keycloak client IS
    one org (the `azp` claim), until a real Organization/membership
    model exists. Revisit once users can belong to more than one org.

    set_config(..., is_local=true) is the parameterized equivalent of
    `SET LOCAL app.current_org_id = '...'` — it only lasts for the
    current transaction, so a pooled connection handed to a DIFFERENT
    request right after this one commits starts with no org set at all
    (every row hidden by default), never the previous request's org."""
    org_id = claims["azp"]

    async with SessionLocal() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.current_org_id', :org_id, true)"),
                {"org_id": org_id},
            )
            yield session
