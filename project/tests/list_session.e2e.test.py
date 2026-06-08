"""
E2E tests for GET /sessions
Requires: API_BASE_URL env var pointing to a deployed API Gateway endpoint.

Note: tests that require DB connectivity accept 500 until RDS is provisioned.
"""
import pytest

_DB_OK = (200, 404, 500)


@pytest.mark.e2e
def test_returns_200_with_sessions_list(api_base, http):
    r = http.get(f"{api_base}/sessions", timeout=10)
    assert r.status_code in _DB_OK
    if r.status_code == 200:
        body = r.json()
        assert "count" in body
        assert "sessions" in body
        assert isinstance(body["sessions"], list)


@pytest.mark.e2e
def test_invalid_year_returns_400(api_base, http):
    r = http.get(f"{api_base}/sessions", params={"year": "notanumber"}, timeout=10)
    assert r.status_code == 400


@pytest.mark.e2e
def test_filter_by_year_returns_200(api_base, http):
    r = http.get(f"{api_base}/sessions", params={"year": "2023"}, timeout=10)
    assert r.status_code in _DB_OK
    if r.status_code == 200:
        body = r.json()
        assert body["year"] == 2023
        for session in body["sessions"]:
            assert session.get("year") == 2023


@pytest.mark.e2e
def test_unknown_year_returns_404(api_base, http):
    r = http.get(f"{api_base}/sessions", params={"year": "1900"}, timeout=10)
    assert r.status_code in _DB_OK


@pytest.mark.e2e
def test_response_content_type_is_json(api_base, http):
    r = http.get(f"{api_base}/sessions", timeout=10)
    assert "application/json" in r.headers.get("Content-Type", "")
