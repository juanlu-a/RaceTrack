"""
Pure simulation-clock logic for the metrics-exporter.

The exporter owns the simulation clock. It maps wall-clock elapsed time since it
first saw a simulation onto *race time*, then picks which bucket to publish.

    speed_factor  = max_race_time_seconds / simulation_duration_seconds
    sim_race_time = (now - sim_start_wallclock) * speed_factor

Given the ordered buckets of a simulation, `select_bucket` returns the latest
bucket whose race-time window the clock has already entered. This naturally
handles catch-up: if a late-arriving bucket's race time has already passed, it
is selected on the next tick rather than skipped or waited on.

All functions are pure (no I/O, no boto3) so the clock can be unit-tested.
"""
from typing import Any, Dict, List, Optional


def speed_factor(max_race_time_seconds: float, simulation_duration_seconds: float) -> float:
    """Race seconds per wall-clock second. Falls back to 1.0 on bad input."""
    try:
        if simulation_duration_seconds and simulation_duration_seconds > 0:
            return float(max_race_time_seconds) / float(simulation_duration_seconds)
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    return 1.0


def sim_race_time_seconds(elapsed_wallclock_seconds: float, factor: float) -> float:
    """Current race-time position given wall-clock elapsed and the speed factor."""
    return max(0.0, float(elapsed_wallclock_seconds)) * float(factor)


def select_bucket(
    buckets: List[Dict[str, Any]],
    sim_race_time: float,
) -> Optional[Dict[str, Any]]:
    """Pick the bucket the clock is currently in (or the latest one passed).

    `buckets` must be ordered by race_time_start_seconds ascending (the
    BUCKET#<padded> SK guarantees this from a DynamoDB Query). Returns the last
    bucket whose race_time_start_seconds <= sim_race_time, or None if the clock
    has not reached the first bucket yet.
    """
    selected = None
    for bucket in buckets:
        start = bucket.get("race_time_start_seconds")
        if start is None:
            continue
        if float(start) <= sim_race_time:
            selected = bucket
        else:
            # buckets are ordered, so nothing further can match
            break
    return selected


def progress_ratio(sim_race_time: float, max_race_time_seconds: float) -> float:
    """Fraction of the race elapsed, clamped to [0, 1]."""
    try:
        if max_race_time_seconds and max_race_time_seconds > 0:
            return max(0.0, min(1.0, float(sim_race_time) / float(max_race_time_seconds)))
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    return 0.0
