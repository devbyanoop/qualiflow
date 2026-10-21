import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qualiflow_api.settings import settings


@pytest.mark.asyncio
async def test_rls_isolates_orgs_but_bypass_sees_everything():
    """The leak test the build plan calls for: seed two orgs' data, then
    prove the restricted role sees only its own org while the superuser
    (RLS-bypassed) confirms both rows genuinely exist. If this is ever
    green without the RLS policy in place, the test is wrong, not the
    policy -- that's the whole point of the bypass check."""
    admin_engine = create_async_engine(settings.database_url_admin)
    app_engine = create_async_engine(settings.database_url)

    org_a, org_b = f"org-a-{uuid.uuid4().hex[:8]}", f"org-b-{uuid.uuid4().hex[:8]}"

    try:
        # Seed as the superuser -- bypasses RLS entirely (including the
        # WITH CHECK side of the policy on INSERT), so no org-context
        # juggling is needed just to create test rows.
        async with admin_engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO organizations (id, name) VALUES (:a, :a), (:b, :b)"),
                {"a": org_a, "b": org_b},
            )
            await conn.execute(
                text(
                    "INSERT INTO projects (id, org_id, name) VALUES "
                    "(:p1, :a, 'Project A'), (:p2, :b, 'Project B')"
                ),
                {"p1": f"proj-{org_a}", "a": org_a, "p2": f"proj-{org_b}", "b": org_b},
            )

        # Bypass path: the superuser sees both rows. This proves the
        # isolation checked below is real enforcement, not a row that
        # simply doesn't exist.
        async with admin_engine.connect() as conn:
            result = await conn.execute(
                text("SELECT org_id FROM projects WHERE org_id IN (:a, :b)"), {"a": org_a, "b": org_b}
            )
            assert {row.org_id for row in result} == {org_a, org_b}

        # Normal path, scoped to org_a: sees org_a's project, never org_b's.
        async with app_engine.begin() as conn:
            await conn.execute(text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": org_a})
            result = await conn.execute(text("SELECT org_id FROM projects"))
            seen = {row.org_id for row in result}
            assert org_a in seen
            assert org_b not in seen

        # The reverse, in a FRESH transaction -- proving the context
        # genuinely resets per transaction, not just "happened to work
        # once" on a connection that still remembered org_a.
        async with app_engine.begin() as conn:
            await conn.execute(text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": org_b})
            result = await conn.execute(text("SELECT org_id FROM projects"))
            seen = {row.org_id for row in result}
            assert org_b in seen
            assert org_a not in seen

        # No org set at all -> the secure failure mode is "see nothing,"
        # not "see everything."
        async with app_engine.begin() as conn:
            result = await conn.execute(text("SELECT org_id FROM projects"))
            seen = {row.org_id for row in result}
            assert org_a not in seen
            assert org_b not in seen
    finally:
        async with admin_engine.begin() as conn:
            await conn.execute(text("DELETE FROM projects WHERE org_id IN (:a, :b)"), {"a": org_a, "b": org_b})
            await conn.execute(text("DELETE FROM organizations WHERE id IN (:a, :b)"), {"a": org_a, "b": org_b})
        await admin_engine.dispose()
        await app_engine.dispose()
