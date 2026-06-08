import json
from unittest.mock import MagicMock


_LAP_ROW = {
    "lap_number": 1, "lap_duration": 83.5,
    "i1_speed": 290, "i2_speed": 300, "st_speed": 310, "is_pit_out_lap": False,
}


def _db_mock(mocker, rows):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.__enter__ = lambda s: s
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_cur.fetchall.return_value = rows
    mocker.patch("psycopg2.connect", return_value=mock_conn)


def test_missing_session_key_returns_400(driver_laps_mod):
    result = driver_laps_mod.handler({"queryStringParameters": {}}, None)
    assert result["statusCode"] == 400
    assert "session_key" in result["body"].lower()


def test_missing_driver_number_returns_400(driver_laps_mod):
    result = driver_laps_mod.handler({"queryStringParameters": {"session_key": "9158"}}, None)
    assert result["statusCode"] == 400
    assert "driver_number" in result["body"].lower()


def test_non_numeric_driver_number_returns_400(driver_laps_mod):
    result = driver_laps_mod.handler(
        {"queryStringParameters": {"session_key": "9158", "driver_number": "VER"}}, None
    )
    assert result["statusCode"] == 400


def test_returns_laps(driver_laps_mod, mocker):
    rows = [_LAP_ROW, {**_LAP_ROW, "lap_number": 2, "lap_duration": 84.1}]
    _db_mock(mocker, rows)
    result = driver_laps_mod.handler(
        {"queryStringParameters": {"session_key": "9158", "driver_number": "1"}}, None
    )
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["lapCount"] == 2
    assert body["driverNumber"] == 1
    lap = body["laps"][0]
    assert lap["lapNumber"] == 1
    assert lap["lapDuration"] == 83.5
    assert lap["stSpeed"] == 310
    assert lap["isPitOutLap"] is False


def test_no_laps_returns_404(driver_laps_mod, mocker):
    _db_mock(mocker, [])
    result = driver_laps_mod.handler(
        {"queryStringParameters": {"session_key": "9999", "driver_number": "1"}}, None
    )
    assert result["statusCode"] == 404
