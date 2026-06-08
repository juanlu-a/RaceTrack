import json
from unittest.mock import MagicMock


_SESSION_ROW = {
    "session_key": "9158", "session_name": "Race", "session_type": "Race",
    "circuit_short_name": "Monza", "country_name": "Italy", "location": "Monza",
    "date_start": "2023-09-03", "date_end": "2023-09-03", "year": 2023, "meeting_key": "1234",
}


def _db_mock(mocker, rows):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.__enter__ = lambda s: s
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_cur.fetchall.return_value = rows
    mocker.patch("psycopg2.connect", return_value=mock_conn)
    return mock_conn


def test_non_numeric_year_returns_400(list_session_mod):
    result = list_session_mod.handler({"queryStringParameters": {"year": "abc"}}, None)
    assert result["statusCode"] == 400
    assert "year" in result["body"].lower()


def test_returns_all_sessions(list_session_mod, mocker):
    _db_mock(mocker, [_SESSION_ROW])
    result = list_session_mod.handler({"queryStringParameters": {}}, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["count"] == 1
    assert body["sessions"][0]["session_key"] == "9158"


def test_filters_by_year(list_session_mod, mocker):
    _db_mock(mocker, [_SESSION_ROW])
    result = list_session_mod.handler({"queryStringParameters": {"year": "2023"}}, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["year"] == 2023


def test_empty_result_with_year_returns_404(list_session_mod, mocker):
    _db_mock(mocker, [])
    result = list_session_mod.handler({"queryStringParameters": {"year": "1990"}}, None)
    assert result["statusCode"] == 404


def test_empty_result_without_year_returns_200_empty(list_session_mod, mocker):
    _db_mock(mocker, [])
    result = list_session_mod.handler({"queryStringParameters": {}}, None)
    assert result["statusCode"] == 200
    assert json.loads(result["body"])["count"] == 0
