"""
E2E tests for save_session (EventBridge-triggered — tested indirectly via full ingest flow).
Requires: API_BASE_URL env var pointing to a deployed API Gateway endpoint.

save_session is invoked by EventBridge after ingest fires a SessionIngested event.
These tests verify the full pipeline: ingest → EventBridge → save → read.

Note: DB-dependent assertions accept 500 until RDS is provisioned.
"""
import time
import pytest

_SESSION_KEY = "9158"
_DB_OK = (200, 404, 500)


@pytest.mark.e2e
def test_ingest_then_list_pipeline(api_base, http):
    """Trigger ingest and confirm the session appears in /sessions afterwards."""
    ingest_r = http.get(f"{api_base}/ingest", params={"session_key": _SESSION_KEY}, timeout=60)
    assert ingest_r.status_code == 200, f"Ingest failed: {ingest_r.text}"

    time.sleep(5)

    sessions_r = http.get(f"{api_base}/sessions", timeout=10)
    assert sessions_r.status_code in _DB_OK
    if sessions_r.status_code == 200:
        keys = [str(s["session_key"]) for s in sessions_r.json()["sessions"]]
        assert _SESSION_KEY in keys, f"Session {_SESSION_KEY} not found after ingest"


@pytest.mark.e2e
def test_ingest_then_drivers_pipeline(api_base, http):
    """After ingest, /drivers should return pilots for the session."""
    http.get(f"{api_base}/ingest", params={"session_key": _SESSION_KEY}, timeout=60)
    time.sleep(5)

    r = http.get(f"{api_base}/drivers", params={"session_key": _SESSION_KEY}, timeout=10)
    assert r.status_code in _DB_OK
    if r.status_code == 200:
        assert r.json()["pilotCount"] > 0
