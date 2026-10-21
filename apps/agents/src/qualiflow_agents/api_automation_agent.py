import subprocess
import sys
import uuid
from pathlib import Path

import httpx
import litellm
from pydantic import BaseModel, ConfigDict

from .logging_utils import log_llm_call
from .tiers import resolve_tier

# Generated scripts are real, inspectable files, not throwaway tempfiles
# -- "AI authors and maintains; deterministic engines execute" (plan §3
# principle 1) means these files ARE the artifact, not an implementation
# detail. Gitignored (they're generated, not source), but written to a
# stable, visible location.
GENERATED_DIR = Path(__file__).resolve().parents[4] / "apps" / "agents" / "generated"
GENERATED_DIR.mkdir(exist_ok=True)

NOVAPAY_URL = "http://localhost:4000"
OPENAPI_SPEC_PATH = Path(__file__).resolve().parents[4] / "fixtures" / "novapay" / "openapi.yaml"


class GeneratedScript(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str


def resolve_two_own_accounts(username: str = "demo", password: str = "Demo@123") -> tuple[int, int]:
    """Real httpx calls against the live app to find two accounts that
    genuinely belong to the same user — plan §7.1: "the agent maps
    steps to the live app... to resolve real locators and endpoints."
    This is NOT the LLM's job to guess; an invented plausible-looking
    account ID (e.g. "12345678") doesn't exist and 404s immediately —
    exactly what happened before this function existed."""
    login = httpx.post(f"{NOVAPAY_URL}/api/auth/login", json={"username": username, "password": password})
    login.raise_for_status()
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    found: dict[int, list[int]] = {}
    for account_id in range(1, 21):
        resp = httpx.get(f"{NOVAPAY_URL}/api/accounts/{account_id}", headers=headers)
        if resp.status_code != 200:
            continue
        user_id = resp.json()["user_id"]
        found.setdefault(user_id, []).append(account_id)
        for ids in found.values():
            if len(ids) >= 2:
                return ids[0], ids[1]

    raise RuntimeError("Could not find two accounts belonging to the same user in the first 20 account IDs.")


def generate_pytest_script(case: dict, retrieved_chunk: str) -> str:
    tier = "qf-strong"  # code generation — the plan's own guidance for this tier
    model = resolve_tier(tier)

    from_id, to_id = resolve_two_own_accounts()
    openapi_spec = OPENAPI_SPEC_PATH.read_text(encoding="utf-8")

    prompt = (
        "Write ONE pytest test function (name it test_generated) that automates "
        "this manual QA test case against NovaPay's real running API. Use the "
        "httpx library for all HTTP calls (already imported in the file this runs "
        "in — do not import it yourself). Use plain assert statements. Output "
        "ONLY the function body as Python source — no markdown fences, no "
        "explanation, no other imports.\n\n"
        "Use this EXACT OpenAPI spec for endpoint paths, request field names, and "
        "response field names — do not invent or guess field names, use exactly "
        f"what this spec says:\n{openapi_spec}\n\n"
        "Use these REAL, verified values from the running system — do not invent "
        "different ones for any of them:\n"
        '- Login credentials: {"username": "demo", "password": "Demo@123"}\n'
        f"- fromAccountId={from_id}, toAccountId={to_id} (confirmed to exist and "
        "belong to the same customer)\n\n"
        f"Business requirement:\n{retrieved_chunk}\n\n"
        f"Manual test case to automate:\n{case}"
    )

    with log_llm_call(tier, model) as finish:
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "generated_script", "schema": GeneratedScript.model_json_schema(), "strict": True},
            },
        )
        finish(response)

    parsed = GeneratedScript.model_validate_json(response.choices[0].message.content)
    return parsed.code


def dry_run(code: str) -> dict:
    """Subprocess, not sandboxed container — that's a later-phase
    hardening step (build plan M0.9 is explicit this isn't required
    yet). This is still real execution of real generated code against
    a real running app, not a simulation."""
    script_path = GENERATED_DIR / f"test_{uuid.uuid4().hex[:8]}.py"
    script_path.write_text("import httpx\n\n\n" + code + "\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(script_path), "-v"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return {
        "script_path": str(script_path),
        "code": code,
        "passed": result.returncode == 0,
        "output": result.stdout + result.stderr,
    }
