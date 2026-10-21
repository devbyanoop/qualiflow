from fastapi.testclient import TestClient

from qualiflow_api.main import app

client = TestClient(app)


def test_healthz_unauthenticated():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_protected_without_token_is_401():
    # No Authorization header at all — short-circuits before ever reaching
    # Keycloak, so this is a true unit test, no live JWKS needed.
    response = client.get("/protected")
    assert response.status_code == 401


def test_protected_with_garbage_token_is_401():
    response = client.get("/protected", headers={"Authorization": "Bearer not.a.real.token"})
    assert response.status_code == 401
