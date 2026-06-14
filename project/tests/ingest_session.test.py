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


def _mock_requests(mocker, sessions=None, drivers=None, laps=None,
                   starting_grid=None, pit=None, position=None,
                   intervals=None, race_control=None, car_data=None,
                   location=None):
    """URL-aware mock for OpenF1. The handler now fetches several datasets
    (some optional, laps/position/car_data/location per driver), so we map each
    path to a fixed response instead of relying on a fixed call order."""
    data_by_path = {
        "sessions": sessions if sessions is not None else [_SESSION],
        "drivers": drivers if drivers is not None else [_DRIVER],
        "laps": laps if laps is not None else [_LAP],
        "starting_grid": starting_grid if starting_grid is not None else [],
        "pit": pit if pit is not None else [],
        "position": position if position is not None else [],
        "intervals": intervals if intervals is not None else [],
        "race_control": race_control if race_control is not None else [],
        "car_data": car_data if car_data is not None else [],
        "location": location if location is not None else [],
    }

    def _get(url, params=None, timeout=None):
        path = url.rstrip("/").rsplit("/", 1)[-1]
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = data_by_path.get(path, [])
        return resp

    mocker.patch("requests.get", side_effect=_get)
    return data_by_path


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
    # laps are now fetched per driver, so total laps = laps_per_driver * drivers
    _mock_requests(mocker, drivers=[_DRIVER, _DRIVER], laps=[_LAP])
    result = ingest_mod.handler({"queryStringParameters": {"session_key": "9158"}}, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["drivers_fetched"] == 2
    assert body["laps_fetched"] == 2


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


@mock_aws
def test_car_data_decimated_to_1hz(ingest_mod, mocker):
    # ~3 Hz input over ~1.3s -> with the default 1 Hz decimation we keep the
    # first point of each second (no averaging): t=0s and t=1s.
    car_data = [
        {"date": "2023-09-03T13:00:00+00:00", "driver_number": 1, "speed": 100},
        {"date": "2023-09-03T13:00:00.300000+00:00", "driver_number": 1, "speed": 110},
        {"date": "2023-09-03T13:00:00.600000+00:00", "driver_number": 1, "speed": 120},
        {"date": "2023-09-03T13:00:01+00:00", "driver_number": 1, "speed": 130},
        {"date": "2023-09-03T13:00:01.300000+00:00", "driver_number": 1, "speed": 140},
    ]
    _mock_requests(mocker, car_data=car_data)
    result = ingest_mod.handler({"queryStringParameters": {"session_key": "9158"}}, None)
    assert result["statusCode"] == 200
    assert json.loads(result["body"])["car_data_points"] == 2

    s3 = boto3.client("s3", region_name="us-east-1")
    obj = s3.get_object(Bucket="racetrack-test-sessions", Key="sessions/9158/raw.json")
    body = json.loads(obj["Body"].read())
    speeds = [p["speed"] for p in body["car_data"]]
    assert speeds == [100, 130]
    # Only the projected fields are kept.
    assert set(body["car_data"][0].keys()) == {"date", "driver_number", "speed"}


@mock_aws
def test_telemetry_clipped_to_race_window(ingest_mod, mocker):
    session = dict(_SESSION,
                   date_start="2023-09-03T13:00:00+00:00",
                   date_end="2023-09-03T13:00:05+00:00")
    location = [
        {"date": "2023-09-03T12:59:59+00:00", "driver_number": 1, "x": 1, "y": 1, "z": 0},  # before
        {"date": "2023-09-03T13:00:02+00:00", "driver_number": 1, "x": 2, "y": 2, "z": 0},  # inside
        {"date": "2023-09-03T13:00:10+00:00", "driver_number": 1, "x": 3, "y": 3, "z": 0},  # after
    ]
    _mock_requests(mocker, sessions=[session], location=location)
    result = ingest_mod.handler({"queryStringParameters": {"session_key": "9158"}}, None)
    assert result["statusCode"] == 200
    assert json.loads(result["body"])["location_points"] == 1

    s3 = boto3.client("s3", region_name="us-east-1")
    obj = s3.get_object(Bucket="racetrack-test-sessions", Key="sessions/9158/raw.json")
    body = json.loads(obj["Body"].read())
    assert [p["x"] for p in body["location"]] == [2]
