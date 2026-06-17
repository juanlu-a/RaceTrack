"""Unit tests for the f1-consumer pure metric computation (containers/f1_consumer/metrics.py)."""


def _ev(event_type, driver_id, ts, payload):
    return {"event_type": event_type, "driver_id": driver_id, "timestamp": ts, "payload": payload}


def test_speed_current_is_last_and_max_is_peak(consumer_metrics_mod):
    events = [
        _ev("car_data", 1, "2023-09-03T13:00:00+00:00", {"speed": 100}),
        _ev("car_data", 1, "2023-09-03T13:00:05+00:00", {"speed": 320}),
        _ev("car_data", 1, "2023-09-03T13:00:09+00:00", {"speed": 210}),
    ]
    m = consumer_metrics_mod.compute_driver_metrics(events)
    assert m["speed_kmh"] == 210.0  # last in the bucket
    assert m["max_speed_kmh"] == 320.0  # peak


def test_last_location_used_for_xy(consumer_metrics_mod):
    events = [
        _ev("location", 1, "2023-09-03T13:00:01+00:00", {"x": 10, "y": 20, "z": 0}),
        _ev("location", 1, "2023-09-03T13:00:08+00:00", {"x": 99, "y": -5, "z": 0}),
    ]
    m = consumer_metrics_mod.compute_driver_metrics(events)
    assert m["x"] == 99.0 and m["y"] == -5.0


def test_gap_position_and_lap(consumer_metrics_mod):
    events = [
        _ev("interval", 1, "2023-09-03T13:00:02+00:00", {"gap_to_leader": 1.234}),
        _ev("position", 1, "2023-09-03T13:00:03+00:00", {"position": 3}),
        _ev("lap", 1, "2023-09-03T13:00:04+00:00", {"lap_number": 12, "lap_duration": 91.5, "is_pit_out_lap": False}),
    ]
    m = consumer_metrics_mod.compute_driver_metrics(events)
    assert m["gap_to_leader_seconds"] == 1.234
    assert m["position"] == 3 and isinstance(m["position"], int)
    assert m["lap_number"] == 12
    assert m["last_lap_duration"] == 91.5
    assert m["is_pit_out_lap"] is False


def test_missing_event_types_are_omitted(consumer_metrics_mod):
    m = consumer_metrics_mod.compute_driver_metrics([
        _ev("car_data", 1, "2023-09-03T13:00:00+00:00", {"speed": 200}),
    ])
    assert "speed_kmh" in m and "max_speed_kmh" in m
    assert "x" not in m and "position" not in m and "gap_to_leader_seconds" not in m


def test_empty_events_produce_empty_metrics(consumer_metrics_mod):
    assert consumer_metrics_mod.compute_driver_metrics([]) == {}


def test_bad_speed_values_are_ignored(consumer_metrics_mod):
    events = [
        _ev("car_data", 1, "2023-09-03T13:00:00+00:00", {"speed": None}),
        _ev("car_data", 1, "2023-09-03T13:00:01+00:00", {"speed": "fast"}),
        _ev("car_data", 1, "2023-09-03T13:00:02+00:00", {"speed": 150}),
    ]
    m = consumer_metrics_mod.compute_driver_metrics(events)
    assert m["max_speed_kmh"] == 150.0


def test_bucket_groups_by_driver_and_skips_none(consumer_metrics_mod):
    body = {"events": [
        _ev("car_data", 1, "2023-09-03T13:00:00+00:00", {"speed": 100}),
        _ev("car_data", 44, "2023-09-03T13:00:01+00:00", {"speed": 200}),
        _ev("race_control", None, "2023-09-03T13:00:02+00:00", {"flag": "GREEN"}),
    ]}
    drivers = consumer_metrics_mod.compute_bucket_metrics(body)
    assert set(drivers.keys()) == {"1", "44"}  # stringified driver ids, None dropped
    assert drivers["44"]["speed_kmh"] == 200.0


def test_bucket_with_no_events(consumer_metrics_mod):
    assert consumer_metrics_mod.compute_bucket_metrics({"events": []}) == {}
    assert consumer_metrics_mod.compute_bucket_metrics({}) == {}
