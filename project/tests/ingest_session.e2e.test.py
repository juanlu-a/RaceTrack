"""
E2E tests for GET /ingest
Requires: API_BASE_URL env var pointing to a deployed API Gateway endpoint.
"""
import json
import pytest


@pytest.mark.e2e
def test_missing_session_key_returns_400(api_base, http):
    r = http.get(f"{api_base}/ingest", timeout=10)
    assert r.status_code == 400
    body = r.json()
    assert "session_key" in str(body).lower()


@pytest.mark.e2e
def test_invalid_session_key_returns_404(api_base, http):
    r = http.get(f"{api_base}/ingest", params={"session_key": "0"}, timeout=30)
    # Either 404 (no session found) or 502 (OpenF1 error) — not a server crash
    assert r.status_code in (404, 502)


@pytest.mark.e2e
def test_valid_session_key_returns_200(api_base, http):
    """Uses a known F1 session key from the 2023 season."""
    r = http.get(f"{api_base}/ingest", params={"session_key": "9158"}, timeout=60)
    assert r.status_code == 200
    body = r.json()
    assert body["session_key"] == "9158"
    assert "drivers_fetched" in body
    assert "laps_fetched" in body
    assert body["drivers_fetched"] > 0
    assert body["laps_fetched"] > 0


@pytest.mark.e2e
def test_response_content_type_is_json(api_base, http):
    r = http.get(f"{api_base}/ingest", timeout=10)
    assert "application/json" in r.headers.get("Content-Type", "")
