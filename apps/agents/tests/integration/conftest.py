import httpx
import pytest


def _novapay_reachable() -> bool:
    try:
        httpx.get("http://localhost:4000/", timeout=2)
        return True
    except httpx.HTTPError:
        return False


# NovaPay (D:\AutomationTool\novapay) is a separate, unvendored repo
# (M0.5's deliberate decision) -- CI has no access to its source, so
# it can't be started there. Tests marked @pytest.mark.requires_novapay
# skip cleanly instead of failing with a connection error, both locally
# (if you forget to start it) and in CI (where it's never available).
#
# Implemented as a collection hook, not a decorator imported across
# files -- pytest test directories aren't regular importable packages
# (no __init__.py), so `from .conftest import ...` fails with
# "attempted relative import with no known parent package". Markers
# are the idiomatic cross-file mechanism; no import needed at all.
def pytest_collection_modifyitems(config, items):
    if _novapay_reachable():
        return
    skip_marker = pytest.mark.skip(
        reason="NovaPay isn't reachable at localhost:4000 -- expected in CI (separate "
        "repo, not vendored); start it locally (node server.js in "
        "D:\\AutomationTool\\novapay) to run these tests."
    )
    for item in items:
        if "requires_novapay" in item.keywords:
            item.add_marker(skip_marker)
