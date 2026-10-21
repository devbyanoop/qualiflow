from pathlib import Path

import httpx
import pytest

from qualiflow_agents.api_automation_agent import dry_run, generate_pytest_script, resolve_two_own_accounts

REPO_ROOT = Path(__file__).resolve().parents[4]
REQUIREMENT_TEXT = (REPO_ROOT / "fixtures" / "novapay" / "brd-transfer-rule.md").read_text(encoding="utf-8")
CASE = {
    "title": "Successful fund transfer between own accounts",
    "preconditions": "Customer logged in, has two own accounts",
    "steps": ["Transfer $100 from source to destination"],
    "test_data": "amount=100",
    "expected_result": "Balances update correctly, refNo returned",
    "priority": "high",
}


# --- Positive ---------------------------------------------------------------


@pytest.mark.requires_novapay
def test_positive_resolve_two_own_accounts_finds_real_existing_accounts():
    """No LLM involved -- pure real HTTP calls against NovaPay. This is
    also the regression guard for the exact bug M0.9 hit: an invented
    account ID ("12345678") that doesn't exist, 404ing immediately.
    This function exists specifically so nothing downstream has to
    guess."""
    from_id, to_id = resolve_two_own_accounts()
    assert from_id != to_id

    login = httpx.post("http://localhost:4000/api/auth/login", json={"username": "demo", "password": "Demo@123"})
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp_from = httpx.get(f"http://localhost:4000/api/accounts/{from_id}", headers=headers)
    resp_to = httpx.get(f"http://localhost:4000/api/accounts/{to_id}", headers=headers)
    assert resp_from.status_code == 200
    assert resp_to.status_code == 200
    assert resp_from.json()["user_id"] == resp_to.json()["user_id"], "must be the SAME customer's own accounts"


@pytest.mark.requires_novapay
@pytest.mark.asyncio
async def test_positive_generated_script_passes_against_the_real_api():
    """Real LLM call (no mocking) + real subprocess execution against
    the real running NovaPay. This is M0.9's actual "done when":
    the generated file runs and passes for real."""
    script = generate_pytest_script(CASE, REQUIREMENT_TEXT)
    result = dry_run(script)
    assert result["passed"], result["output"]


# --- Negative -----------------------------------------------------------


@pytest.mark.requires_novapay
def test_negative_resolve_accounts_raises_on_bad_credentials():
    with pytest.raises(httpx.HTTPStatusError):
        resolve_two_own_accounts(username="not-a-real-user", password="wrong")


# --- Edge ------------------------------------------------------------------


def test_edge_dry_run_captures_a_syntax_error_without_crashing_our_own_code():
    """A real failure mode: the LLM could return code with a syntax
    error. dry_run must report that as a failed run, not raise an
    unhandled exception in our own process."""
    result = dry_run("def test_generated(:\n    pass")  # deliberately invalid syntax
    assert result["passed"] is False
    assert "SyntaxError" in result["output"] or "error" in result["output"].lower()


# --- Regression --------------------------------------------------------------
#
# The exact bug M0.9 hit twice: first an invented account ID (404),
# then invented login credentials (401) -- both because the LLM wasn't
# given real values and had to guess plausible-looking ones. Guards
# against ever dropping the explicit "use these REAL values" context
# from the prompt again.


@pytest.mark.requires_novapay
@pytest.mark.asyncio
async def test_regression_prompt_always_includes_real_credentials_and_account_ids():
    import litellm

    captured_prompt = {}
    original_completion = litellm.completion

    def spy_completion(*args, **kwargs):
        captured_prompt["messages"] = kwargs.get("messages")
        return original_completion(*args, **kwargs)

    litellm.completion = spy_completion
    try:
        generate_pytest_script(CASE, REQUIREMENT_TEXT)
    finally:
        litellm.completion = original_completion

    prompt_text = captured_prompt["messages"][0]["content"]
    assert "Demo@123" in prompt_text, "real login credentials must be in the prompt, not left for the LLM to guess"
    assert "fromAccountId=" in prompt_text, "real resolved account IDs must be in the prompt"
    assert "openapi" in prompt_text.lower() or "paths:" in prompt_text, "the real OpenAPI spec must be in the prompt"
