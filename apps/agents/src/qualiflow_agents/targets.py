from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .settings import settings

engine = create_async_engine(settings.database_url)


class TargetNotFoundError(ValueError):
    """Raised when no target app is registered for this org/feature —
    a real, expected failure mode (same pattern as generate_tests.py's
    ChunkNotFoundError), not a bug."""


async def get_target(org_id: str, feature_id: str) -> dict:
    async with engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": org_id}
        )
        result = await conn.execute(
            text(
                "SELECT base_url, openapi_spec FROM target_apps "
                "WHERE org_id = :org_id AND feature_id = :feature_id "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"org_id": org_id, "feature_id": feature_id},
        )
        row = result.first()

    if row is None:
        raise TargetNotFoundError(
            f"No target app registered for org_id={org_id!r} feature_id={feature_id!r}. "
            "Register one via POST /targets first."
        )
    return {"base_url": row.base_url, "openapi_spec": row.openapi_spec}
