"""
E2E tests for save_session (EventBridge-triggered — tested indirectly via full ingest flow).
Requires: API_BASE_URL env var pointing to a deployed API Gateway endpoint.

save_session is not directly HTTP-accessible; it is invoked by EventBridge after
ingest_session fires a SessionIngested event. These tests verify the full data
pipeline by calling /ingest and then checking /sessions for the persisted data.
"""
import time
import pytest

_SESSION_KEY = "9158"


@pytest.mark.e2e
def test_ingest_then_list_pipeline(api_base, http):
    """Trigger ingest and confirm the session appears in /sessions afterwards."""
    ingest_r = http.get(f"{api_base}/ingest", params={"session_key": _SESSION_KEY}, timeout=60)
    assert ingest_r.status_code == 200, f"Ingest failed: {ingest_r.text}"

    # EventBridge → save_session is async; give it a moment to complete.
    time.sleep(5)

    sessions_r = http.get(f"{api_base}/sessions", timeout=10)
    assert sessions_r.status_code == 200
    sessions = sessions_r.json()["sessions"]
    keys = [str(s["session_key"]) for s in sessions]
    assert _SESSION_KEY in keys, f"Session {_SESSION_KEY} not found in /sessions after ingest"


@pytest.mark.e2e
def test_ingest_then_drivers_pipeline(api_base, http):
    """After ingest, /drivers should return pilots for the session."""
    http.get(f"{api_base}/ingest", params={"session_key": _SESSION_KEY}, timeout=60)
    time.sleep(5)

    r = http.get(f"{api_base}/drivers", params={"session_key": _SESSION_KEY}, timeout=10)
    assert r.status_code == 200
    assert r.json()["pilotCount"] > 0
