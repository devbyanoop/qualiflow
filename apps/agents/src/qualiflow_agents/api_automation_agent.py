import json
import subprocess
import sys
import uuid
from pathlib import Path

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


class GeneratedScript(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str


def generate_resolver_script(openapi_spec: str, case: dict, base_url: str, auth: dict) -> str:
    """Generalizes what used to be one hand-written function per app,
    hardcoded to one specific target's domain model (see M0.10's
    roadmap entry for that history). The LLM writes a small script
    that makes REAL HTTP calls against the real target to discover
    whatever concrete values this specific case needs -- not the LLM's
    job to guess at prompt time (plan §7.1: "the agent maps steps to
    the live app... to resolve real locators and endpoints"), and not
    something hand-coded per domain here either. The script must print
    exactly one JSON object to stdout; its keys become the "real
    values" fed into the generated test."""
    tier = "qf-strong"
    model = resolve_tier(tier)

    prompt = (
        "You are writing a small Python script that discovers REAL values "
        "a test case needs, by making real HTTP calls (httpx is already "
        "imported, as is json) against a live system. Do not invent IDs "
        "or data -- query the real API and use only what actually exists "
        "and satisfies the case's preconditions.\n\n"
        f"Target base URL: {base_url}\n"
        f"Authentication to use for login/requests: {json.dumps(auth)}\n\n"
        "Use this EXACT OpenAPI spec for endpoint paths and field names -- "
        f"do not guess:\n{openapi_spec}\n\n"
        f"Manual test case that needs these values:\n{json.dumps(case)}\n\n"
        "Output ONLY the body of a Python script (no markdown fences, no "
        "imports besides what's already available: httpx, json, sys). "
        "The script MUST end by printing exactly one JSON object to "
        "stdout (via print(json.dumps(...))) containing whatever named "
        "values the test case needs (e.g. real IDs confirmed to exist and "
        "satisfy the case's preconditions). If no such values can be "
        "found or none are needed, print an empty JSON object: {}"
    )

    with log_llm_call(tier, model) as finish:
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "resolver_script",
                    "schema": GeneratedScript.model_json_schema(),
                    "strict": True,
                },
            },
        )
        finish(response)

    return GeneratedScript.model_validate_json(response.choices[0].message.content).code


def run_resolver(code: str) -> dict:
    """Executes the resolver script for real against the real target --
    same no-mocking principle as dry_run below. Returns whatever JSON
    object it printed. Raises on a non-zero exit or missing/invalid
    JSON output -- a real, informative failure (e.g. the target has no
    data satisfying the case) rather than silently continuing with
    nothing resolved."""
    script_path = GENERATED_DIR / f"resolver_{uuid.uuid4().hex[:8]}.py"
    script_path.write_text("import httpx\nimport json\nimport sys\n\n\n" + code + "\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(script_path)], capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"Resolver script failed:\n{result.stdout}\n{result.stderr}")

    stdout = result.stdout.strip()
    last_line = stdout.splitlines()[-1] if stdout else ""
    try:
        return json.loads(last_line)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Resolver script did not print a JSON object. stdout:\n{result.stdout}") from exc


def generate_pytest_script(case: dict, retrieved_chunk: str, target: dict, auth: dict) -> str:
    """target: {"base_url": ..., "openapi_spec": ...} -- looked up per
    org/feature via targets.get_target, registered through POST
    /targets. auth: whatever credentials the resolver and generated
    test need (e.g. {"username": ..., "password": ...}), supplied by
    the caller per-request -- never persisted to the database."""
    tier = "qf-strong"  # code generation — the plan's own guidance for this tier
    model = resolve_tier(tier)

    resolver_code = generate_resolver_script(target["openapi_spec"], case, target["base_url"], auth)
    resolved_values = run_resolver(resolver_code)

    prompt = (
        "Write ONE pytest test function (name it test_generated) that automates "
        "this manual QA test case against the real running API described below. "
        "Use the httpx library for all HTTP calls (already imported in the file "
        "this runs in — do not import it yourself). Use plain assert statements. "
        "Output ONLY the function body as Python source — no markdown fences, no "
        "explanation, no other imports.\n\n"
        f"Target base URL: {target['base_url']}\n\n"
        "Use this EXACT OpenAPI spec for endpoint paths, request field names, and "
        "response field names — do not invent or guess field names, use exactly "
        f"what this spec says:\n{target['openapi_spec']}\n\n"
        "Use these REAL, verified values — do not invent different ones for any "
        f"of them:\n- Authentication: {json.dumps(auth)}\n"
        f"- Resolved values (confirmed to exist on the real system): {json.dumps(resolved_values)}\n\n"
        f"Business requirement:\n{retrieved_chunk}\n\n"
        f"Manual test case to automate:\n{case}"
    )

    with log_llm_call(tier, model) as finish:
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "generated_script",
                    "schema": GeneratedScript.model_json_schema(),
                    "strict": True,
                },
            },
        )
        finish(response)

    return GeneratedScript.model_validate_json(response.choices[0].message.content).code


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
