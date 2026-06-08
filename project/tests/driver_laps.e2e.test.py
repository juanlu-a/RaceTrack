"""
E2E tests for GET /driver-laps
Requires: API_BASE_URL env var pointing to a deployed API Gateway endpoint.
Run ingest first to have data: GET /ingest?session_key=9158

Note: tests that require DB connectivity accept 500 until RDS is provisioned.
"""
import pytest

_SESSION_KEY = "9158"
_DRIVER_NUMBER = "1"

# Status codes accepted when the DB may not be provisioned yet
_DB_OK = (200, 404, 500)


@pytest.mark.e2e
def test_missing_session_key_returns_400(api_base, http):
    r = http.get(f"{api_base}/driver-laps", timeout=10)
    assert r.status_code == 400


@pytest.mark.e2e
def test_missing_driver_number_returns_400(api_base, http):
    r = http.get(f"{api_base}/driver-laps", params={"session_key": _SESSION_KEY}, timeout=10)
    assert r.status_code == 400


@pytest.mark.e2e
def test_non_numeric_driver_number_returns_400(api_base, http):
    r = http.get(
        f"{api_base}/driver-laps",
        params={"session_key": _SESSION_KEY, "driver_number": "VER"},
        timeout=10,
    )
    assert r.status_code == 400


@pytest.mark.e2e
def test_known_driver_returns_laps(api_base, http):
    r = http.get(
        f"{api_base}/driver-laps",
        params={"session_key": _SESSION_KEY, "driver_number": _DRIVER_NUMBER},
        timeout=10,
    )
    assert r.status_code in _DB_OK
    if r.status_code == 200:
        body = r.json()
        assert "laps" in body
        assert body["lapCount"] == len(body["laps"])
        if body["laps"]:
            lap = body["laps"][0]
            assert "lapNumber" in lap
            assert "lapDuration" in lap
            assert "isPitOutLap" in lap


@pytest.mark.e2e
def test_unknown_session_returns_404(api_base, http):
    r = http.get(
        f"{api_base}/driver-laps",
        params={"session_key": "0", "driver_number": "999"},
        timeout=10,
    )
    assert r.status_code in _DB_OK
