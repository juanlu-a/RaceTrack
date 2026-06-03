import json
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws


_SESSION = {"session_key": "9158", "session_name": "Race", "session_type": "Race",
            "circuit_short_name": "Monza", "country_name": "Italy", "location": "Monza",
            "date_start": "2023-09-03", "date_end": "2023-09-03", "year": 2023, "meeting_key": "1234"}
_DRIVER = {"driver_number": 1, "full_name": "Max Verstappen", "team_name": "Red Bull", "country_code": "NLD"}
_LAP = {"driver_number": 1, "lap_number": 1, "lap_duration": 83.5,
        "i1_speed": 290, "i2_speed": 300, "st_speed": 310, "is_pit_out_lap": False}


def _mock_requests(mocker, sessions=None, drivers=None, laps=None):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.side_effect = [
        sessions if sessions is not None else [_SESSION],
        drivers if drivers is not None else [_DRIVER],
        laps if laps is not None else [_LAP],
    ]
    mocker.patch("requests.get", return_value=resp)
    return resp


def test_missing_session_key_returns_400(ingest_mod):
    result = ingest_mod.handler({"queryStringParameters": {}}, None)
    assert result["statusCode"] == 400
    assert "session_key" in result["body"]


def test_missing_params_returns_400(ingest_mod):
    result = ingest_mod.handler({"queryStringParameters": None}, None)
    assert result["statusCode"] == 400


@mock_aws
def test_s3_object_created(ingest_mod, mocker):
    _mock_requests(mocker)
    result = ingest_mod.handler({"queryStringParameters": {"session_key": "9158"}}, None)
    assert result["statusCode"] == 200

    s3 = boto3.client("s3", region_name="us-east-1")
    obj = s3.get_object(Bucket="racetrack-test-sessions", Key="sessions/9158/raw.json")
    body = json.loads(obj["Body"].read())
    assert body["session_key"] == "9158"
    assert body["session"] == _SESSION
    assert len(body["drivers"]) == 1
    assert len(body["laps"]) == 1


@mock_aws
def test_response_counts_drivers_and_laps(ingest_mod, mocker):
    _mock_requests(mocker, drivers=[_DRIVER, _DRIVER], laps=[_LAP, _LAP, _LAP])
    result = ingest_mod.handler({"queryStringParameters": {"session_key": "9158"}}, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["drivers_fetched"] == 2
    assert body["laps_fetched"] == 3


@mock_aws
def test_empty_sessions_returns_404(ingest_mod, mocker):
    _mock_requests(mocker, sessions=[], drivers=[], laps=[])
    result = ingest_mod.handler({"queryStringParameters": {"session_key": "9999"}}, None)
    assert result["statusCode"] == 404


@mock_aws
def test_openf1_timeout_returns_502(ingest_mod, mocker):
    import requests as req_lib
    mocker.patch("requests.get", side_effect=req_lib.exceptions.Timeout)
    result = ingest_mod.handler({"queryStringParameters": {"session_key": "9158"}}, None)
    assert result["statusCode"] == 502
    assert "timeout" in result["body"].lower()
