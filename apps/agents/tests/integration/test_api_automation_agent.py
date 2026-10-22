import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qualiflow_agents.api_automation_agent import (
    dry_run,
    generate_pytest_script,
    generate_resolver_script,
    run_resolver,
)
from qualiflow_agents.settings import settings
from qualiflow_agents.targets import get_target

REPO_ROOT = Path(__file__).resolve().parents[4]
REQUIREMENT_TEXT = (REPO_ROOT / "fixtures" / "novapay" / "brd-transfer-rule.md").read_text(encoding="utf-8")
OPENAPI_SPEC = (REPO_ROOT / "fixtures" / "novapay" / "openapi.yaml").read_text(encoding="utf-8")
# NovaPay here is just the first registered target app, exercised through
# the same generic mechanism any other app would use -- nothing in
# api_automation_agent.py itself knows this is NovaPay.
BASE_URL = "http://localhost:4000"
AUTH = {"username": "demo", "password": "Demo@123"}
CASE = {
    "title": "Successful fund transfer between own accounts",
    "preconditions": "Customer logged in, has two own accounts",
    "steps": ["Transfer $100 from source to destination"],
    "test_data": "amount=100",
    "expected_result": "Balances update correctly, refNo returned",
    "priority": "high",
}


async def _seed_target(org_id: str, feature_id: str, environment: str = "dev") -> None:
    engine = create_async_engine(settings.database_url_admin)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO target_apps (id, org_id, feature_id, base_url, openapi_spec, environment) "
                "VALUES (:id, :org_id, :feature_id, :base_url, :openapi_spec, :environment)"
            ),
            {
                "id": str(uuid.uuid4()),
                "org_id": org_id,
                "feature_id": feature_id,
                "base_url": BASE_URL,
                "openapi_spec": OPENAPI_SPEC,
                "environment": environment,
            },
        )
    await engine.dispose()


async def _cleanup_target(org_id: str) -> None:
    engine = create_async_engine(settings.database_url_admin)
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM target_apps WHERE org_id = :org_id"), {"org_id": org_id})
    await engine.dispose()


# --- Positive ---------------------------------------------------------------


@pytest.mark.requires_novapay
def test_positive_resolver_discovers_real_values_against_the_real_api():
    """Real LLM call writes a resolver script; real subprocess execution
    against the real running NovaPay. This is also the regression guard
    for the exact bug M0.9 hit: an invented account ID ("12345678") that
    doesn't exist, 404ing immediately -- now solved generically (any
    target app, any OpenAPI spec) instead of by one hand-written
    NovaPay-specific function."""
    resolver_code = generate_resolver_script(OPENAPI_SPEC, CASE, BASE_URL, AUTH)
    resolved = run_resolver(resolver_code)
    assert resolved, "resolver must find at least one real value for this case"


@pytest.mark.requires_novapay
@pytest.mark.asyncio
async def test_positive_generated_script_passes_against_the_real_api():
    """Real LLM calls (no mocking) + real subprocess execution against
    the real running NovaPay, routed entirely through the generic
    target-app mechanism (POST /targets' underlying table) -- no
    NovaPay-specific code path in api_automation_agent.py itself."""
    org_id = f"test-org-{uuid.uuid4().hex[:8]}"
    await _seed_target(org_id, "transfers")
    try:
        target = await get_target(org_id, "transfers")
        script = generate_pytest_script(CASE, REQUIREMENT_TEXT, target, AUTH)
        result = dry_run(script)
        assert result["passed"], result["output"]
    finally:
        await _cleanup_target(org_id)


# --- Negative -----------------------------------------------------------


@pytest.mark.requires_novapay
def test_negative_bad_credentials_fail_real_resolution():
    """Wrong credentials against the real login endpoint -- the resolver
    script can't authenticate, so it either errors out (non-zero exit,
    surfaced as RuntimeError) or genuinely finds nothing. Either way
    this must not silently succeed with invented-looking values."""
    bad_auth = {"username": "not-a-real-user", "password": "wrong"}
    try:
        resolved = run_resolver(generate_resolver_script(OPENAPI_SPEC, CASE, BASE_URL, bad_auth))
        assert resolved == {}, "must not resolve real-looking values from a failed login"
    except RuntimeError:
        pass  # also an acceptable, honest failure mode


# --- Edge ------------------------------------------------------------------


def test_edge_dry_run_captures_a_syntax_error_without_crashing_our_own_code():
    """A real failure mode: the LLM could return code with a syntax
    error. dry_run must report that as a failed run, not raise an
    unhandled exception in our own process."""
    result = dry_run("def test_generated(:\n    pass")  # deliberately invalid syntax
    assert result["passed"] is False
    assert "SyntaxError" in result["output"] or "error" in result["output"].lower()


def test_edge_run_resolver_raises_on_a_crashing_script():
    """Mirrors dry_run's syntax-error edge case, but for the resolver
    pipeline: a script that raises must surface as RuntimeError here,
    not an unhandled crash in our own process."""
    with pytest.raises(RuntimeError):
        run_resolver("raise ValueError('deliberately broken resolver')")


def test_edge_run_resolver_raises_when_no_json_is_printed():
    """A resolver script that runs fine but forgets to print JSON (a
    real mistake an LLM could make) must be caught explicitly, not
    silently treated as an empty-but-valid result."""
    with pytest.raises(RuntimeError):
        run_resolver("print('not json')")


# --- Regression --------------------------------------------------------------
#
# This milestone's whole point: api_automation_agent.py used to hardcode
# NovaPay's URL, OpenAPI spec path, demo credentials, and a bank-account-
# specific resolver function. Target identity must always flow through
# target_apps / function parameters, never a constant in source.


def test_regression_no_app_name_is_hardcoded_in_source():
    source = Path(__file__).resolve().parents[2] / "src" / "qualiflow_agents" / "api_automation_agent.py"
    content = source.read_text(encoding="utf-8").lower()
    assert "novapay" not in content


@pytest.mark.requires_novapay
def test_regression_prompt_always_includes_real_target_and_auth():
    import litellm

    captured_prompts = []
    original_completion = litellm.completion

    def spy_completion(*args, **kwargs):
        captured_prompts.append(kwargs.get("messages")[0]["content"])
        return original_completion(*args, **kwargs)

    litellm.completion = spy_completion
    try:
        generate_pytest_script(CASE, REQUIREMENT_TEXT, {"base_url": BASE_URL, "openapi_spec": OPENAPI_SPEC}, AUTH)
    finally:
        litellm.completion = original_completion

    final_prompt = captured_prompts[-1]  # the script-generation call, after the resolver call
    assert "Demo@123" in final_prompt, "real auth must be in the prompt, not left for the LLM to guess"
    assert BASE_URL in final_prompt, "the real target base URL must be in the prompt"
    assert "openapi" in final_prompt.lower() or "paths:" in final_prompt, "the real OpenAPI spec must be in the prompt"
