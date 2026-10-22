import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qualiflow_agents.settings import settings
from qualiflow_agents.targets import ProductionBlockedError, check_production_guardrail, get_target

ORG_ID = "env-classification-tests"


async def _seed_target(feature_id: str, environment: str) -> None:
    engine = create_async_engine(settings.database_url_admin)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO target_apps (id, org_id, feature_id, base_url, openapi_spec, environment) "
                "VALUES (:id, :org_id, :feature_id, 'http://localhost:4000', 'openapi: 3.0.3', :environment)"
            ),
            {"id": str(uuid.uuid4()), "org_id": ORG_ID, "feature_id": feature_id, "environment": environment},
        )
    await engine.dispose()


async def _cleanup(feature_id: str) -> None:
    engine = create_async_engine(settings.database_url_admin)
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM target_apps WHERE org_id = :org_id AND feature_id = :feature_id"),
            {"org_id": ORG_ID, "feature_id": feature_id},
        )
    await engine.dispose()


# --- Positive ---------------------------------------------------------------


@pytest.mark.parametrize("environment", ["dev", "qa", "uat", "pre-production"])
def test_positive_non_production_environments_are_never_blocked(environment):
    target = {"environment": environment}
    check_production_guardrail(target, allow_production=False)  # must not raise


@pytest.mark.asyncio
async def test_positive_registered_target_is_fetched_with_its_real_environment():
    feature_id = f"feature-{uuid.uuid4().hex[:8]}"
    await _seed_target(feature_id, "qa")
    try:
        target = await get_target(ORG_ID, feature_id)
        assert target["environment"] == "qa"
    finally:
        await _cleanup(feature_id)


# --- Negative -----------------------------------------------------------


def test_negative_production_is_blocked_by_default():
    target = {"environment": "production"}
    with pytest.raises(ProductionBlockedError):
        check_production_guardrail(target, allow_production=False)


@pytest.mark.asyncio
async def test_negative_registering_an_invalid_environment_is_rejected_by_the_database():
    """Defense in depth: even a caller that bypasses the API's Pydantic
    Literal and writes raw SQL hits the DB's own CHECK constraint."""
    from sqlalchemy.exc import IntegrityError

    engine = create_async_engine(settings.database_url_admin)
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO target_apps (id, org_id, feature_id, base_url, openapi_spec, environment) "
                    "VALUES (:id, :org_id, 'bad-env-feature', 'http://x', 'openapi: 3.0.3', 'staging')"
                ),
                {"id": str(uuid.uuid4()), "org_id": ORG_ID},
            )
    await engine.dispose()


# --- Edge ------------------------------------------------------------------


def test_edge_allow_production_lifts_the_block():
    """The explicit opt-in works -- but note what it does NOT do: this
    does not verify the automation is actually read-only. That's a
    separate, unbuilt guardrail (§8.5's "Action policies" row)."""
    target = {"environment": "production"}
    check_production_guardrail(target, allow_production=True)  # must not raise


def test_edge_allow_production_is_ignored_for_non_production_targets():
    """allow_production=True on a non-production target is a no-op, not
    an error -- it simply never needed to matter."""
    target = {"environment": "dev"}
    check_production_guardrail(target, allow_production=True)  # must not raise


# --- Regression --------------------------------------------------------------
#
# Guards against the exact failure mode this guardrail exists to
# prevent: a target silently defaulting into an environment it was
# never actually classified as.


@pytest.mark.asyncio
async def test_regression_environment_has_no_default_and_must_be_explicit():
    """Registration without an explicit environment must fail at the
    database layer (NOT NULL, no default) -- confirms the migration's
    backfill-only server_default was dropped and never silently
    reapplied by a later migration or manual schema edit."""
    from sqlalchemy.exc import IntegrityError

    engine = create_async_engine(settings.database_url_admin)
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO target_apps (id, org_id, feature_id, base_url, openapi_spec) "
                    "VALUES (:id, :org_id, 'no-env-feature', 'http://x', 'openapi: 3.0.3')"
                ),
                {"id": str(uuid.uuid4()), "org_id": ORG_ID},
            )
    await engine.dispose()
