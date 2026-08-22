"""Generate deterministic, fully synthetic Intervals.icu-shaped test fixtures."""

from __future__ import annotations

import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "fixtures"


def save(name: str, data) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(data, indent=1) + "\n")


def activity(index: int = 1) -> dict:
    item = {
        "id": f"i10000000{index}",
        "type": "Hike" if index == 1 else "Run",
        "name": f"Example activity {index}",
        "description": None,
        "start_date_local": f"2024-01-{index:02d}T10:00:00",
        "distance": 10323.1,
        "moving_time": 9860,
        "elapsed_time": 10000,
        "average_speed": 0.736,
        "max_speed": 2.4,
        "average_heartrate": 112,
        "max_heartrate": 142,
        "icu_training_load": 69,
        "total_elevation_gain": 718.2007,
        "icu_weighted_avg_watts": None,
        "icu_pm_ftp": None,
        "external_id": None,
        "skyline_chart_bytes": None,
        "icu_sync_date": None,
    }
    for number in range(1, 165):
        item[f"synthetic_unused_{number:03d}"] = None
    assert len(item) == 183
    return item


def lap() -> dict:
    item = {
        "id": 1,
        "type": "WORK",
        "label": "Example lap",
        "distance": 1000.0,
        "moving_time": 360,
        "elapsed_time": 365,
        "average_speed": 2.78,
        "average_heartrate": 130,
        "max_heartrate": 142,
    }
    for number in range(1, 76):
        item[f"synthetic_unused_{number:03d}"] = None
    assert len(item) == 84
    return item


def stream(kind: str, base: float, amplitude: float) -> dict:
    data = [round(base + amplitude * math.sin(index / 100), 3) for index in range(14019)]
    if kind == "heartrate":
        data[7000] = 142
    return {"type": kind, "data": data}


def main() -> int:
    save("activity_detail", activity())
    save("activities_list", [activity(index) for index in range(1, 6)])
    save("activity_intervals", {"id": "i100000001", "icu_intervals": [lap()]})
    save(
        "activity_streams",
        [
            stream("heartrate", 120, 12),
            stream("velocity_smooth", 3.2, 0.8),
            stream("altitude", 150, 30),
        ],
    )
    save(
        "athlete_profile",
        {
            "athlete": {
                "id": "i000001",
                "name": "Example Athlete",
                "city": "Example City",
                "state": "Example State",
                "country": "XX",
                "timezone": "UTC",
                "sex": "M",
                "bio": None,
                "icu_coach": False,
            }
        },
    )
    save(
        "wellness",
        [
            {
                "id": f"2024-01-{day:02d}",
                "ctl": 40 + day / 10,
                "atl": 35 + day / 8,
                "rampRate": 1.2,
                "weight": 70.0,
                "restingHR": 50,
                "hrv": 60,
                "sleepScore": None,
                "comments": None,
            }
            for day in range(1, 31)
        ],
    )
    secs = list(range(1, 151)) + [300, 600, 1200, 1800, 3600, 5400]
    save(
        "hr_curves",
        {
            "list": [
                {
                    "id": "1y",
                    "label": "1 year",
                    "start_date_local": "2024-01-01T00:00:00",
                    "end_date_local": "2024-12-31T23:59:59",
                    "secs": secs,
                    "values": [max(100, 190 - index // 3) for index in range(len(secs))],
                }
            ]
        },
    )
    save(
        "pace_curves",
        {
            "list": [
                {
                    "id": "1y",
                    "label": "1 year",
                    "start_date_local": "2024-01-01T00:00:00",
                    "end_date_local": "2024-12-31T23:59:59",
                    "distance": [400, 1000, 1609.344, 5000, 10000, 18000],
                    "values": [59, 237, 420, 1221, 3000, 6570],
                    "synthetic_padding": [0] * 2000,
                }
            ]
        },
    )
    sports = []
    for number, types in enumerate((["Ride"], ["Run"], ["Swim"], ["Other"]), 1):
        sports.append(
            {
                "id": number,
                "athlete_id": "i000001",
                "types": types,
                "ftp": 250 if "Ride" in types else None,
                "power_zones": [55, 75, 90, 105, 120, 150, 999],
                "hr_zones": [60, 70, 80, 90, 100],
                **{f"synthetic_unused_{item:02d}": None for item in range(40)},
            }
        )
    save("sport_settings", sports)
    save("folders", [{"athlete_id": "i000001", "id": 1, "type": "FOLDER", "name": "Example"}])
    save("events", [])
    save("gear", [])
    save("workouts", [])
    save("history_per_year", {"2024": 5})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
