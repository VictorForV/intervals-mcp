"""Shape intervals.icu payloads down to what a coaching agent can actually read.

Raw payloads are far larger than they look useful: an activity carries 183
fields of which 113 are null, a single lap carries 84, and three stream series
from one activity come to 363 KB. Every function here is pure so it can be
tested against synthetic fixtures shaped like the live API.
"""

import re
from collections.abc import Iterable, Sequence
from typing import Any

# Fields worth showing for a completed activity. Power fields stay in the list
# because the same server serves cycling; null stripping removes them for runs.
ACTIVITY_FIELDS = (
    "id",
    "type",
    "name",
    "description",
    "start_date_local",
    "distance",
    "moving_time",
    "elapsed_time",
    "average_speed",
    "max_speed",
    "pace",
    "average_heartrate",
    "max_heartrate",
    "icu_hr_zone_times",
    "average_cadence",
    "average_stride",
    "icu_weighted_avg_watts",
    "icu_ftp",
    "icu_training_load",
    "icu_intensity",
    "trimp",
    "hr_load",
    "total_elevation_gain",
    "total_elevation_loss",
    "calories",
    "icu_atl",
    "icu_ctl",
    "feel",
    "perceived_exertion",
    "icu_rpe",
    "race",
)

LAP_FIELDS = (
    "id",
    "type",
    "label",
    "zone",
    "start_time",
    "end_time",
    "distance",
    "moving_time",
    "elapsed_time",
    "average_speed",
    "max_speed",
    "average_heartrate",
    "min_heartrate",
    "max_heartrate",
    "average_watts",
    "max_watts",
    "weighted_average_watts",
    "average_cadence",
    "intensity",
    "training_load",
    "total_elevation_gain",
    "average_gradient",
    "decoupling",
)

WELLNESS_FIELDS = (
    "id",
    "ctl",
    "atl",
    "rampRate",
    "ctlLoad",
    "atlLoad",
    "weight",
    "tempWeight",
    "restingHR",
    "tempRestingHR",
    "hrv",
    "hrvSDNN",
    "sleepSecs",
    "sleepScore",
    "sleepQuality",
    "avgSleepingHR",
    "soreness",
    "fatigue",
    "stress",
    "mood",
    "motivation",
    "injury",
    "steps",
    "kcalConsumed",
    "spO2",
    "systolic",
    "diastolic",
    "respiration",
    "bodyFat",
    "vo2max",
    "comments",
)

# Rounded to one decimal: these are trend metrics, and six decimals of CTL is
# noise the agent would have to read past.
WELLNESS_ROUNDED = ("ctl", "atl", "rampRate", "ctlLoad", "atlLoad", "weight", "tempWeight")

SPORT_SETTINGS_FIELDS = (
    "types",
    "ftp",
    "indoor_ftp",
    "w_prime",
    "p_max",
    "power_zones",
    "power_zone_names",
    "hr_zones",
    "hr_zone_names",
    "lthr",
    "max_hr",
    "pace_zones",
    "pace_zone_names",
    "threshold_pace",
    "pace_units",
    "sweet_spot_min",
    "sweet_spot_max",
    "warmup_time",
    "cooldown_time",
    "gap_model",
)

PROFILE_FIELDS = ("id", "name", "city", "state", "country", "timezone", "sex", "bio", "icu_coach")

EVENT_FIELDS = (
    "id",
    "start_date_local",
    "end_date_local",
    "category",
    "name",
    "description",
    "type",
    "moving_time",
    "distance",
    "icu_training_load",
    "icu_intensity",
    "atl_days",
    "ctl_days",
    "indoor",
    "workout_doc",
    "paired_activity_id",
)

# Durations a coach actually quotes, mapped to the label used in output.
CURVE_DURATIONS = (
    (5, "5s"),
    (15, "15s"),
    (30, "30s"),
    (60, "1m"),
    (300, "5m"),
    (600, "10m"),
    (1200, "20m"),
    (1800, "30m"),
    (3600, "1h"),
    (5400, "1h30m"),
)

# Pace curves are indexed by distance in metres instead of by seconds, so they
# are reported at race distances. Tolerance covers the API's imperial entries
# (a mile arrives as 1609.344).
CURVE_DISTANCES = (
    (400, "400m"),
    (1000, "1k"),
    (1609.344, "1mi"),
    (5000, "5k"),
    (10000, "10k"),
    (21097.5, "HM"),
    (42195, "M"),
)
DISTANCE_TOLERANCE = 0.005


def pick(data: dict, fields: Sequence[str]) -> dict:
    """Keep whitelisted keys whose value carries information.

    Nulls and empty containers are dropped; ``False`` and ``0`` are kept,
    because "did not race" and "zero training load" are both real answers.
    """
    result = {}
    for field in fields:
        if field not in data:
            continue
        value = data[field]
        if value is None:
            continue
        if isinstance(value, (str, list, dict, tuple)) and len(value) == 0:
            continue
        result[field] = value
    return result


def downsample(data: Sequence, points: int) -> list:
    """Take ``points`` evenly spaced samples, always including first and last.

    points <= 0 and n <= points are different situations and must not share a
    fallback: the former genuinely means "give me (almost) nothing", the
    latter means "there isn't enough data to trim". Treating points < 2 as
    "return everything" (the previous behaviour) turned a request for the
    smallest possible reply into the largest one -- a payload-bomb footgun
    for whatever asked for points=0 expecting exactly that.
    """
    n = len(data)
    if points <= 0:
        return []
    if n <= points:
        return list(data)
    if points == 1:
        return [data[0]]
    return [data[int(i * (n - 1) / (points - 1))] for i in range(points)]


def _is_coordinate_pair(value: object) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(isinstance(v, (int, float)) for v in value)
    )


def summarize_series(data: Iterable) -> dict:
    """Min/mean/max over a scalar stream, ignoring the nulls intervals.icu emits.

    latlng is not a scalar stream: each sample is a [lat, lon] pair, for which
    min/mean/max are meaningless (and summing pairs outright crashes). A
    bounding box is the useful summary there instead.
    """
    values = [v for v in data if v is not None]
    if not values:
        return {"min": None, "mean": None, "max": None, "points": 0}
    if _is_coordinate_pair(values[0]):
        lats = [v[0] for v in values]
        lons = [v[1] for v in values]
        return {
            "lat_min": min(lats),
            "lat_max": max(lats),
            "lon_min": min(lons),
            "lon_max": max(lons),
            "points": len(values),
        }
    return {
        "min": min(values),
        "mean": round(sum(values) / len(values), 2),
        "max": max(values),
        "points": len(values),
    }


def pace_from_speed(speed_mps: float | None) -> str | None:
    """Format m/s as mm:ss per kilometre, the unit a runner thinks in."""
    if not speed_mps:
        return None
    seconds_per_km = 1000 / speed_mps
    return f"{int(seconds_per_km // 60)}:{int(seconds_per_km % 60):02d}"


def compact_activity(activity: dict) -> dict:
    result = pick(activity, ACTIVITY_FIELDS)
    pace = pace_from_speed(activity.get("average_speed"))
    if pace:
        result["pace_per_km"] = pace
    return result


def compact_activities(activities: Iterable[dict]) -> list[dict]:
    return [compact_activity(a) for a in activities]


def compact_intervals(payload: dict) -> dict:
    laps = payload.get("icu_intervals") or []
    return {
        "activity_id": payload.get("id"),
        "laps": [pick(lap, LAP_FIELDS) for lap in laps],
    }


def compact_streams(streams: Iterable[dict], points: int = 200, full: bool = False) -> dict:
    streams = list(streams)
    original = max((len(s.get("data") or []) for s in streams), default=0)
    series = []
    for stream in streams:
        data = stream.get("data") or []
        entry = {
            "type": stream.get("type"),
            "summary": summarize_series(data),
            "data": list(data) if full else downsample(data, points),
        }
        # Despite its name, intervals.icu's latlng stream sometimes carries only
        # latitude as a flat number per sample rather than [lat, lon] pairs --
        # observed behaviour of the upstream API, not something this tool can
        # fix. Flag it so the agent does not mistake a bare number for a full
        # coordinate or invent a longitude.
        if stream.get("type") == "latlng" and data and not _is_coordinate_pair(data[0]):
            entry["note"] = (
                "intervals.icu's own API response for this stream already carries "
                "latitude only, not [lat, lon] pairs; longitude is missing before "
                "this tool ever sees the data. Verify directly with "
                "intervals_get_raw(path='activity/{activity_id}/streams', "
                "params={'types': 'latlng'}) -- no athlete segment in that path."
            )
        series.append(entry)
    returned = max((len(s["data"]) for s in series), default=0)
    result = {
        "original_points": original,
        "returned_points": returned,
        "series": series,
    }
    if not full and returned < original:
        result["note"] = (
            f"Downsampled from {original} to {returned} points. "
            "Summaries are computed over the full series. "
            "Pass full=true for every point (expensive)."
        )
    return result


def compact_wellness(days: Iterable[dict]) -> list[dict]:
    result = []
    for day in days:
        entry = pick(day, WELLNESS_FIELDS)
        for field in WELLNESS_ROUNDED:
            if field in entry:
                entry[field] = round(entry[field], 1)
        result.append(entry)
    return result


def compact_sport_settings(settings: Iterable[dict]) -> list[dict]:
    return [pick(group, SPORT_SETTINGS_FIELDS) for group in settings]


def compact_profile(payload: dict) -> dict:
    athlete = payload.get("athlete") or payload
    return pick(athlete, PROFILE_FIELDS)


def compact_events(events: Iterable[dict]) -> list[dict]:
    return [pick(event, EVENT_FIELDS) for event in events]


def format_duration(seconds: float | None) -> str | None:
    """Format seconds as m:ss, or h:mm:ss once it passes an hour."""
    if seconds is None:
        return None
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _best_by_duration(secs: list, values: list) -> dict:
    """Heart-rate and power curves: the best value held for each duration."""
    best = {}
    for duration, label in CURVE_DURATIONS:
        if duration in secs:
            index = secs.index(duration)
            if index < len(values) and values[index] is not None:
                best[label] = values[index]
    return best


def _best_by_distance(distances: list, values: list) -> dict:
    """Pace curves: the fastest time recorded over each race distance.

    ``values`` holds seconds, so the time is also expressed as pace per km,
    which is the form a runner reads.
    """
    best = {}
    for target, label in CURVE_DISTANCES:
        for index, distance in enumerate(distances):
            if abs(distance - target) > target * DISTANCE_TOLERANCE:
                continue
            if index >= len(values) or values[index] is None:
                continue
            seconds = values[index]
            best[label] = {
                "time": format_duration(seconds),
                "seconds": seconds,
                "pace_per_km": pace_from_speed(distance / seconds) if seconds else None,
            }
            break
    return best


def compact_curves(payload: dict) -> dict:
    curves = []
    for curve in payload.get("list") or []:
        values = curve.get("values") or []
        secs = curve.get("secs") or []
        distances = curve.get("distance") or []

        # hr and power curves come indexed by duration, pace curves by distance.
        if secs:
            indexed_by, best = "duration", _best_by_duration(secs, values)
        elif distances:
            indexed_by, best = "distance", _best_by_distance(distances, values)
        else:
            indexed_by, best = "unknown", {}

        curves.append(
            {
                "label": curve.get("label"),
                "start_date_local": curve.get("start_date_local"),
                "end_date_local": curve.get("end_date_local"),
                "indexed_by": indexed_by,
                "best": best,
            }
        )
    return {"curves": curves}


# intervals_get_raw hands back whatever an arbitrary v1 GET path returns,
# unshaped -- including account internals a coaching agent has no business
# reading or repeating back: email, API keys, invitation links. Field
# *names* survive redaction (so the response shape is still legible); only
# values that look like credentials or PII are replaced.
_SENSITIVE_KEY_MARKERS = (
    "email",
    "token",
    "apikey",
    "api_key",
    "password",
    "secret",
    "credential",
    "invite",
    "auth",
)
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS)


def redact_secrets(value: Any) -> Any:
    """Recursively replace credential- and PII-shaped values with a placeholder."""
    if isinstance(value, dict):
        return {
            k: "[redacted]" if _is_sensitive_key(k) and v not in (None, "", []) else redact_secrets(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(v) for v in value]
    if isinstance(value, str) and _EMAIL_RE.match(value.strip()):
        return "[redacted]"
    return value
