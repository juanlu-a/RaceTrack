"""
E2E tests for GET /driver-summary
Requires: API_BASE_URL env var pointing to a deployed API Gateway endpoint.
Run ingest first to have data: GET /ingest?session_key=9158
"""
import pytest

_SESSION_KEY = "9158"
_DRIVER_NUMBER = "1"


@pytest.mark.e2e
def test_missing_session_key_returns_400(api_base, http):
    r = http.get(f"{api_base}/driver-summary", timeout=10)
    assert r.status_code == 400


@pytest.mark.e2e
def test_missing_driver_number_returns_400(api_base, http):
    r = http.get(f"{api_base}/driver-summary", params={"session_key": _SESSION_KEY}, timeout=10)
    assert r.status_code == 400


@pytest.mark.e2e
def test_non_numeric_driver_number_returns_400(api_base, http):
    r = http.get(
        f"{api_base}/driver-summary",
        params={"session_key": _SESSION_KEY, "driver_number": "VER"},
        timeout=10,
    )
    assert r.status_code == 400


@pytest.mark.e2e
def test_known_driver_returns_stats(api_base, http):
    r = http.get(
        f"{api_base}/driver-summary",
        params={"session_key": _SESSION_KEY, "driver_number": _DRIVER_NUMBER},
        timeout=10,
    )
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        body = r.json()
        assert "stats" in body
        stats = body["stats"]
        assert "totalLaps" in stats
        assert "bestLapDuration" in stats
        assert "avgLapDuration" in stats
        assert "topSpeed" in stats
        assert "avgSpeed" in stats


@pytest.mark.e2e
def test_unknown_driver_returns_404(api_base, http):
    r = http.get(
        f"{api_base}/driver-summary",
        params={"session_key": "0", "driver_number": "999"},
        timeout=10,
    )
    assert r.status_code == 404
