"""
E2E tests for GET /drivers
Requires: API_BASE_URL env var pointing to a deployed API Gateway endpoint.
Run ingest first to have data: GET /ingest?session_key=9158
"""
import pytest

_SESSION_KEY = "9158"


@pytest.mark.e2e
def test_missing_session_key_returns_400(api_base, http):
    r = http.get(f"{api_base}/drivers", timeout=10)
    assert r.status_code == 400


@pytest.mark.e2e
def test_unknown_session_key_returns_404(api_base, http):
    r = http.get(f"{api_base}/drivers", params={"session_key": "0"}, timeout=10)
    assert r.status_code == 404


@pytest.mark.e2e
def test_known_session_returns_drivers(api_base, http):
    r = http.get(f"{api_base}/drivers", params={"session_key": _SESSION_KEY}, timeout=10)
    assert r.status_code in (200, 404)  # 404 if not yet ingested
    if r.status_code == 200:
        body = r.json()
        assert "pilots" in body
        assert "pilotCount" in body
        assert body["pilotCount"] == len(body["pilots"])
        pilot = body["pilots"][0]
        assert "pilotName" in pilot
        assert "pilotNumber" in pilot
        assert "pilotTeam" in pilot
        assert "pilotCountry" in pilot


@pytest.mark.e2e
def test_response_content_type_is_json(api_base, http):
    r = http.get(f"{api_base}/drivers", timeout=10)
    assert "application/json" in r.headers.get("Content-Type", "")
