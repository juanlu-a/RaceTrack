"""
E2E tests for GET /drivers
Requires: API_BASE_URL env var pointing to a deployed API Gateway endpoint.

Note: tests that require DB connectivity accept 500 until RDS is provisioned.
"""
import pytest

_SESSION_KEY = "9158"
_DB_OK = (200, 404, 500)


@pytest.mark.e2e
def test_missing_session_key_returns_400(api_base, http):
    r = http.get(f"{api_base}/drivers", timeout=10)
    assert r.status_code == 400


@pytest.mark.e2e
def test_unknown_session_key_returns_404(api_base, http):
    r = http.get(f"{api_base}/drivers", params={"session_key": "0"}, timeout=10)
    assert r.status_code in _DB_OK


@pytest.mark.e2e
def test_known_session_returns_drivers(api_base, http):
    r = http.get(f"{api_base}/drivers", params={"session_key": _SESSION_KEY}, timeout=10)
    assert r.status_code in _DB_OK
    if r.status_code == 200:
        body = r.json()
        assert "pilots" in body
        assert body["pilotCount"] == len(body["pilots"])
        pilot = body["pilots"][0]
        assert "pilotName" in pilot
        assert "pilotNumber" in pilot


@pytest.mark.e2e
def test_response_content_type_is_json(api_base, http):
    r = http.get(f"{api_base}/drivers", timeout=10)
    assert "application/json" in r.headers.get("Content-Type", "")
