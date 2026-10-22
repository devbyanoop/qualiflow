from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .settings import settings

engine = create_async_engine(settings.database_url)


class TargetNotFoundError(ValueError):
    """Raised when no target app is registered for this org/feature —
    a real, expected failure mode (same pattern as generate_tests.py's
    ChunkNotFoundError), not a bug."""


class ProductionBlockedError(RuntimeError):
    """§8.5's guardrail: production is blocked for agents and test runs
    by default. Raised when a target is classified "production" and
    the caller hasn't explicitly opted in via allow_production. Lifting
    the block is an acknowledgment, not a safety guarantee that nothing
    destructive runs -- see docs/adr/0007-environment-classification.md
    for what's deliberately not enforced yet."""


def check_production_guardrail(target: dict, allow_production: bool) -> None:
    if target["environment"] == "production" and not allow_production:
        raise ProductionBlockedError(
            "Target is classified as production. Automation is blocked by default "
            "(see docs/adr/0007-environment-classification.md). Set "
            '"allow_production": true to proceed.'
        )


async def get_target(org_id: str, feature_id: str) -> dict:
    async with engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": org_id}
        )
        result = await conn.execute(
            text(
                "SELECT base_url, openapi_spec, environment FROM target_apps "
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
    return {"base_url": row.base_url, "openapi_spec": row.openapi_spec, "environment": row.environment}
