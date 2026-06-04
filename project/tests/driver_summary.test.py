import json
from unittest.mock import MagicMock


_DRIVER = {"full_name": "Max Verstappen", "team_name": "Red Bull Racing", "country_code": "NLD"}
_STATS = {
    "total_laps": 50, "best_lap_duration": 83.5,
    "avg_lap_duration": 85.2, "top_speed": 330, "avg_speed": 310.5,
}


def _db_mock(mocker, driver_row, stats_row):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.__enter__ = lambda s: s
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_cur.fetchone.side_effect = [driver_row, stats_row]
    mocker.patch("psycopg2.connect", return_value=mock_conn)


def test_missing_session_key_returns_400(driver_summary_mod):
    result = driver_summary_mod.handler({"queryStringParameters": {}}, None)
    assert result["statusCode"] == 400
    assert "session_key" in result["body"].lower()


def test_missing_driver_number_returns_400(driver_summary_mod):
    result = driver_summary_mod.handler({"queryStringParameters": {"session_key": "9158"}}, None)
    assert result["statusCode"] == 400
    assert "driver_number" in result["body"].lower()


def test_non_numeric_driver_number_returns_400(driver_summary_mod):
    result = driver_summary_mod.handler(
        {"queryStringParameters": {"session_key": "9158", "driver_number": "abc"}}, None
    )
    assert result["statusCode"] == 400


def test_returns_stats(driver_summary_mod, mocker):
    _db_mock(mocker, _DRIVER, _STATS)
    result = driver_summary_mod.handler(
        {"queryStringParameters": {"session_key": "9158", "driver_number": "1"}}, None
    )
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["driverName"] == "Max Verstappen"
    assert body["driverNumber"] == 1
    stats = body["stats"]
    assert stats["totalLaps"] == 50
    assert stats["bestLapDuration"] == round(83.5, 3)
    assert stats["topSpeed"] == 330


def test_driver_not_found_returns_404(driver_summary_mod, mocker):
    _db_mock(mocker, None, _STATS)
    result = driver_summary_mod.handler(
        {"queryStringParameters": {"session_key": "9999", "driver_number": "99"}}, None
    )
    assert result["statusCode"] == 404
