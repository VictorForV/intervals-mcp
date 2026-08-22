"""Exercise every tool against the live intervals.icu account.

    uv run python scripts/smoke.py

Read-only. Prints the payload size of each result so regressions in shaping show
up as a size jump.
"""

import json
import sys
import traceback

from intervals_mcp.client import IntervalsClient
from intervals_mcp.config import load_config
from intervals_mcp.tools import IntervalsTools


def size(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str))


def main() -> int:
    tools = IntervalsTools(IntervalsClient(load_config()))

    # Discover a real activity id from the athlete's most active stretch so the
    # per-activity tools run against something with laps and streams.
    recent = tools.list_activities(oldest="-45d", limit=1)
    if recent["activities"]:
        activity_id = recent["activities"][0]["id"]
    else:
        activity_id = tools.list_activities(oldest="2022-01-01", newest="2022-12-31", limit=1)[
            "activities"
        ][0]["id"]

    checks = [
        ("get_athlete_profile", lambda: tools.get_athlete_profile()),
        ("get_sport_settings", lambda: tools.get_sport_settings()),
        ("list_activities (30d default)", lambda: tools.list_activities()),
        ("list_activities (2022, Run)", lambda: tools.list_activities(
            oldest="2022-01-01", newest="2022-12-31", activity_type="Run", limit=5)),
        ("list_activities (all 7 years)", lambda: tools.list_activities(
            oldest="2019-01-01", newest="today", limit=3)),
        ("get_activity", lambda: tools.get_activity(activity_id)),
        ("get_activity_intervals", lambda: tools.get_activity_intervals(activity_id)),
        ("get_activity_streams", lambda: tools.get_activity_streams(activity_id)),
        ("get_activity_streams (50pts)", lambda: tools.get_activity_streams(
            activity_id, types="heartrate", points=50)),
        ("get_wellness", lambda: tools.get_wellness()),
        ("get_wellness (2022 June)", lambda: tools.get_wellness(
            oldest="2022-06-01", newest="2022-06-30")),
        ("get_events", lambda: tools.get_events()),
        ("get_best_efforts (hr, Run)", lambda: tools.get_best_efforts(kind="hr", sport_type="Run")),
        ("get_best_efforts (pace, Run)", lambda: tools.get_best_efforts(
            kind="pace", sport_type="Run")),
        ("get_gear", lambda: tools.get_gear()),
        ("list_workouts", lambda: tools.list_workouts()),
        ("intervals_get_raw", lambda: tools.intervals_get_raw("athlete/{athlete}/profile")),
    ]

    failures = []
    print(f"activity under test: {activity_id}\n")
    print(f"{'tool':32s} {'bytes':>8s}  result")
    print("-" * 78)

    for label, call in checks:
        try:
            result = call()
        except Exception as exc:
            failures.append((label, f"{type(exc).__name__}: {exc}"))
            print(f"{label:32s} {'--':>8s}  FAILED {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=2)
            continue

        if isinstance(result, dict) and "error" in result and len(result) == 1:
            failures.append((label, result["error"]))
            print(f"{label:32s} {size(result):8,d}  ERROR {result['error'][:60]}")
            continue

        print(f"{label:32s} {size(result):8,d}  {summarize(result)}")

    print("-" * 78)
    if failures:
        print(f"\n{len(failures)} of {len(checks)} checks FAILED:")
        for label, reason in failures:
            print(f"  {label}: {reason}")
        return 1
    print(f"\nall {len(checks)} checks passed")
    return 0


def summarize(result) -> str:
    if isinstance(result, list):
        return f"list of {len(result)}"
    if not isinstance(result, dict):
        return str(result)[:60]
    for key in ("activities", "days", "events", "laps", "curves", "sports", "gear", "series"):
        if key in result:
            extra = ""
            if key == "activities":
                extra = f", matched {result.get('matched')}"
            elif key == "series":
                extra = f", {result.get('original_points')}->{result.get('returned_points')} pts"
            return f"{len(result[key])} {key}{extra}"
    return ", ".join(list(result)[:5])[:60]


if __name__ == "__main__":
    sys.exit(main())
