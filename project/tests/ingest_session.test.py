import json
from unittest.mock import MagicMock


def _patch_events(ingest_mod, mocker):
    """Patch the EventBridge client so handler() doesn't hit AWS. Returns the
    mock events client so tests can assert on put_events calls."""
    eb = MagicMock()
    eb.put_events.return_value = {"FailedEntryCount": 0, "Entries": [{"EventId": "1"}]}
    mocker.patch.object(ingest_mod, "_events_client", return_value=eb)
    return eb


def test_missing_session_key_returns_400(ingest_mod, mocker):
    eb = _patch_events(ingest_mod, mocker)
    result = ingest_mod.handler({"queryStringParameters": {}}, None)
    assert result["statusCode"] == 400
    assert "session_key" in result["body"]
    eb.put_events.assert_not_called()


def test_missing_params_returns_400(ingest_mod, mocker):
    _patch_events(ingest_mod, mocker)
    result = ingest_mod.handler({"queryStringParameters": None}, None)
    assert result["statusCode"] == 400


def test_returns_202_and_fires_ingest_requested(ingest_mod, mocker):
    eb = _patch_events(ingest_mod, mocker)
    result = ingest_mod.handler({"queryStringParameters": {"session_key": "9158"}}, None)

    assert result["statusCode"] == 202
    body = json.loads(result["body"])
    assert body["status"] == "accepted"
    assert body["session_key"] == "9158"

    eb.put_events.assert_called_once()
    entries = eb.put_events.call_args.kwargs["Entries"]
    assert entries[0]["Source"] == "racetrack"
    assert entries[0]["DetailType"] == "IngestRequested"
    assert json.loads(entries[0]["Detail"])["session_key"] == "9158"


def test_eventbridge_failure_returns_500(ingest_mod, mocker):
    eb = _patch_events(ingest_mod, mocker)
    eb.put_events.side_effect = RuntimeError("boom")
    result = ingest_mod.handler({"queryStringParameters": {"session_key": "9158"}}, None)
    assert result["statusCode"] == 500
