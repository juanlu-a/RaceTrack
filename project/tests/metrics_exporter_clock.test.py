"""Unit tests for the metrics-exporter simulation clock (containers/metrics_exporter/clock.py)."""


def _buckets(*starts):
    return [{"race_time_start_seconds": s, "race_time_end_seconds": s + 10, "bucket_index": i}
            for i, s in enumerate(starts)]


def test_speed_factor(exporter_clock_mod):
    # 6000s of race compressed into 300s of wall clock -> 20x
    assert exporter_clock_mod.speed_factor(6000, 300) == 20.0


def test_speed_factor_falls_back_on_bad_input(exporter_clock_mod):
    assert exporter_clock_mod.speed_factor(6000, 0) == 1.0
    assert exporter_clock_mod.speed_factor(6000, None) == 1.0


def test_sim_race_time_maps_wallclock(exporter_clock_mod):
    # 5s elapsed at 20x -> race time 100s
    assert exporter_clock_mod.sim_race_time_seconds(5, 20.0) == 100.0
    # negative elapsed clamps to 0
    assert exporter_clock_mod.sim_race_time_seconds(-3, 20.0) == 0.0


def test_select_bucket_picks_current_window(exporter_clock_mod):
    buckets = _buckets(0, 10, 20, 30)
    # race time 25s -> bucket starting at 20
    assert exporter_clock_mod.select_bucket(buckets, 25)["bucket_index"] == 2


def test_select_bucket_before_first_returns_none(exporter_clock_mod):
    buckets = _buckets(10, 20, 30)
    assert exporter_clock_mod.select_bucket(buckets, 5) is None


def test_select_bucket_catch_up_to_latest_passed(exporter_clock_mod):
    # Clock has already run past several buckets that only just arrived: pick the
    # most recent one whose race time has passed, not the first unprocessed one.
    buckets = _buckets(0, 10, 20, 30, 40)
    assert exporter_clock_mod.select_bucket(buckets, 100)["bucket_index"] == 4


def test_select_bucket_exact_boundary_is_inclusive(exporter_clock_mod):
    buckets = _buckets(0, 10, 20)
    assert exporter_clock_mod.select_bucket(buckets, 20)["bucket_index"] == 2


def test_progress_ratio_clamps(exporter_clock_mod):
    assert exporter_clock_mod.progress_ratio(3000, 6000) == 0.5
    assert exporter_clock_mod.progress_ratio(9000, 6000) == 1.0
    assert exporter_clock_mod.progress_ratio(-5, 6000) == 0.0
    assert exporter_clock_mod.progress_ratio(100, 0) == 0.0
