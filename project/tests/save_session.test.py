import json
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws


_PAYLOAD = {
    "session_key": "9158",
    "session": {
        "session_key": "9158", "session_name": "Race", "session_type": "Race",
        "circuit_short_name": "Monza", "country_name": "Italy", "location": "Monza",
        "date_start": "2023-09-03", "date_end": "2023-09-03", "year": 2023, "meeting_key": "1234",
    },
    "drivers": [
        {"driver_number": 1, "full_name": "Max Verstappen", "team_name": "Red Bull", "country_code": "NLD"},
    ],
    "laps": [
        {"driver_number": 1, "lap_number": 1, "lap_duration": 83.5,
         "i1_speed": 290, "i2_speed": 300, "st_speed": 310, "is_pit_out_lap": False},
    ],
}


def _db_mock(mocker):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.__enter__ = lambda s: s
    mock_cur.__exit__ = MagicMock(return_value=False)
    mocker.patch("psycopg2.connect", return_value=mock_conn)
    return mock_conn, mock_cur


def test_missing_detail_fields_returns_400(save_mod):
    result = save_mod.handler({"detail": {}}, None)
    assert result["statusCode"] == 400


def test_no_detail_returns_400(save_mod):
    result = save_mod.handler({}, None)
    assert result["statusCode"] == 400


@mock_aws
def test_reads_s3_and_saves_to_db(save_mod, mocker):
    bucket, key = "racetrack-test-sessions", "sessions/9158/raw.json"
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=bucket)
    s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(_PAYLOAD).encode())

    _db_mock(mocker)
    event = {"detail": {"bucket": bucket, "key": key, "session_key": "9158"}}
    result = save_mod.handler(event, None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["session_key"] == "9158"
    assert body["drivers_saved"] == 1
    assert body["laps_saved"] == 1


@mock_aws
def test_db_tables_created(save_mod, mocker):
    bucket, key = "racetrack-test-sessions", "sessions/9158/raw.json"
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=bucket)
    s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(_PAYLOAD).encode())

    _, mock_cur = _db_mock(mocker)
    save_mod.handler({"detail": {"bucket": bucket, "key": key, "session_key": "9158"}}, None)

    calls = [str(c) for c in mock_cur.execute.call_args_list]
    assert len([c for c in calls if "CREATE TABLE" in c]) == 3  # sessions, drivers, laps
