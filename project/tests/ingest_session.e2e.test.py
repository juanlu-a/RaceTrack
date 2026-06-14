"""
E2E tests for GET /ingest
Requires: API_BASE_URL env var pointing to a deployed API Gateway endpoint.

/ingest is now an async entrypoint: it validates the request, fires an
EventBridge `IngestRequested` event and returns 202 immediately. The heavy
fetch + persistence happens asynchronously in ingest_worker, so these tests
assert the 202 acceptance contract, not the ingested data.
"""
import pytest


@pytest.mark.e2e
def test_missing_session_key_returns_400(api_base, http):
    r = http.get(f"{api_base}/ingest", timeout=10)
    assert r.status_code == 400
    body = r.json()
    assert "session_key" in str(body).lower()


@pytest.mark.e2e
def test_valid_session_key_returns_202(api_base, http):
    """Uses a known F1 session key from the 2023 season. The request is only
    accepted here; existence is validated later by the async worker."""
    r = http.get(f"{api_base}/ingest", params={"session_key": "9158"}, timeout=30)
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "accepted"
    assert body["session_key"] == "9158"


@pytest.mark.e2e
def test_response_content_type_is_json(api_base, http):
    r = http.get(f"{api_base}/ingest", timeout=10)
    assert "application/json" in r.headers.get("Content-Type", "")
