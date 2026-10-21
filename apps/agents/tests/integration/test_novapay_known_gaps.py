"""Documents a real gap in NovaPay (see fixtures/novapay/openapi.yaml
and docs/project/roadmap.md's M0.5 entry), found while writing that
OpenAPI spec and cashed in here as M0.9's own deferred promise: a
test that genuinely fails against the real API, not a happy-path
confirmation. NovaPay isn't QualiFlow's to patch -- this test exists
to prove generation finds real gaps, and to notice immediately if
NovaPay is ever fixed (this test would then unexpectedly pass,
which is itself worth noticing)."""

import httpx
import pytest


@pytest.mark.requires_novapay
@pytest.mark.xfail(
    strict=True,
    reason="Known NovaPay gap: /api/transfers never checks fromAccountId ownership. "
    "strict=True so this test FAILS (not silently passes as xfail) the moment "
    "NovaPay's behavior changes -- that's a real signal worth noticing, not "
    "something to let go green quietly.",
)
def test_cannot_transfer_from_an_account_you_dont_own():
    login = httpx.post("http://localhost:4000/api/auth/login", json={"username": "demo", "password": "Demo@123"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['token']}"}

    # Account 3 belongs to Jane M. Smith (user_id=2), not "demo"
    # (user_id=4). Per brd-transfer-rule.md, this must be rejected.
    resp = httpx.post(
        "http://localhost:4000/api/transfers",
        json={"fromAccountId": 3, "toAccountId": 5, "amount": 10},
        headers=headers,
    )
    assert resp.status_code in (400, 401, 403), (
        f"KNOWN GAP in NovaPay (not QualiFlow's to fix): expected the transfer to be "
        f"rejected since fromAccountId doesn't belong to the caller, but got "
        f"{resp.status_code}: {resp.text}. If this assertion starts passing, "
        f"NovaPay's ownership check was fixed -- update the roadmap entry."
    )
