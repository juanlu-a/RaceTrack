import json
from unittest.mock import MagicMock


_DRIVER_ROW = {
    "session_key": "9158", "driver_number": 1,
    "full_name": "Max Verstappen", "team_name": "Red Bull Racing", "country_code": "NLD",
}


def _db_mock(mocker, rows):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.__enter__ = lambda s: s
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_cur.fetchall.return_value = rows
    mocker.patch("psycopg2.connect", return_value=mock_conn)


def test_missing_session_key_returns_400(list_drivers_mod):
    result = list_drivers_mod.handler({"queryStringParameters": {}}, None)
    assert result["statusCode"] == 400
    assert "session_key" in result["body"].lower()


def test_empty_session_key_returns_400(list_drivers_mod):
    result = list_drivers_mod.handler({"queryStringParameters": {"session_key": ""}}, None)
    assert result["statusCode"] == 400


def test_returns_drivers(list_drivers_mod, mocker):
    _db_mock(mocker, [_DRIVER_ROW])
    result = list_drivers_mod.handler({"queryStringParameters": {"session_key": "9158"}}, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["pilotCount"] == 1
    pilot = body["pilots"][0]
    assert pilot["pilotName"] == "Max Verstappen"
    assert pilot["pilotNumber"] == 1
    assert pilot["pilotTeam"] == "Red Bull Racing"
    assert pilot["pilotCountry"] == "NLD"


def test_no_drivers_returns_404(list_drivers_mod, mocker):
    _db_mock(mocker, [])
    result = list_drivers_mod.handler({"queryStringParameters": {"session_key": "9999"}}, None)
    assert result["statusCode"] == 404
