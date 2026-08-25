"""Tests for the tool layer: date defaults, shaping, and truncation reporting.

These run a real IntervalsClient over a mocked transport, so they cover the whole
chain from tool argument to shaped result.
"""

import datetime
import json
import pathlib

import httpx
import pytest
import respx

from intervals_mcp.client import IntervalsClient
from intervals_mcp.config import Config
from intervals_mcp.tools import IntervalsTools

BASE = "https://intervals.icu/api/v1"
ATHLETE = "i123"
TODAY = datetime.date(2026, 8, 10)
FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def fixture(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture
def tools():
    client = IntervalsClient(Config(api_key="testkey", athlete_id=ATHLETE), backoff_base=0)
    return IntervalsTools(client, today=lambda: TODAY)


class TestListActivities:
    @respx.mock
    def test_defaults_to_the_last_thirty_days(self, tools):
        route = respx.get(f"{BASE}/athlete/{ATHLETE}/activities").mock(
            return_value=httpx.Response(200, json=[])
        )

        result = tools.list_activities()

        params = route.calls.last.request.url.params
        assert params["oldest"] == "2026-07-11"
        assert params["newest"] == "2026-08-10"
        assert result["window"] == {"oldest": "2026-07-11", "newest": "2026-08-10"}

    @respx.mock
    def test_accepts_a_relative_range(self, tools):
        route = respx.get(f"{BASE}/athlete/{ATHLETE}/activities").mock(
            return_value=httpx.Response(200, json=[])
        )

        tools.list_activities(oldest="-1y", newest="today")

        assert route.calls.last.request.url.params["oldest"] == "2025-08-10"

    @respx.mock
    def test_shapes_each_activity(self, tools):
        respx.get(f"{BASE}/athlete/{ATHLETE}/activities").mock(
            return_value=httpx.Response(200, json=fixture("activities_list"))
        )

        result = tools.list_activities()

        assert len(result["activities"]) == 5
        assert "skyline_chart_bytes" not in result["activities"][0]

    @respx.mock
    def test_filters_by_activity_type(self, tools):
        respx.get(f"{BASE}/athlete/{ATHLETE}/activities").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"id": "a", "type": "Run"},
                    {"id": "b", "type": "Hike"},
                    {"id": "c", "type": "Run"},
                ],
            )
        )

        result = tools.list_activities(activity_type="Run")

        assert [a["id"] for a in result["activities"]] == ["a", "c"]

    @respx.mock
    def test_matches_activity_type_case_insensitively(self, tools):
        respx.get(f"{BASE}/athlete/{ATHLETE}/activities").mock(
            return_value=httpx.Response(200, json=[{"id": "a", "type": "Run"}])
        )

        assert len(tools.list_activities(activity_type="run")["activities"]) == 1

    @respx.mock
    def test_reports_truncation_instead_of_hiding_it(self, tools):
        respx.get(f"{BASE}/athlete/{ATHLETE}/activities").mock(
            return_value=httpx.Response(200, json=[{"id": str(i), "type": "Run"} for i in range(50)])
        )

        result = tools.list_activities(limit=10)

        assert result["matched"] == 50
        assert result["returned"] == 10
        assert len(result["activities"]) == 10
        assert "50" in result["note"]

    @respx.mock
    def test_says_nothing_about_truncation_when_nothing_was_cut(self, tools):
        respx.get(f"{BASE}/athlete/{ATHLETE}/activities").mock(
            return_value=httpx.Response(200, json=[{"id": "a", "type": "Run"}])
        )

        assert "note" not in tools.list_activities(limit=10)

    @respx.mock
    def test_returns_the_most_recent_activities_when_truncating(self, tools):
        respx.get(f"{BASE}/athlete/{ATHLETE}/activities").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"id": "newest", "type": "Run", "start_date_local": "2026-08-09T10:00:00"},
                    {"id": "middle", "type": "Run", "start_date_local": "2026-08-05T10:00:00"},
                    {"id": "oldest", "type": "Run", "start_date_local": "2026-08-01T10:00:00"},
                ],
            )
        )

        result = tools.list_activities(limit=1)

        assert result["activities"][0]["id"] == "newest"


class TestActivityDetail:
    @respx.mock
    def test_shapes_the_activity(self, tools):
        respx.get(f"{BASE}/activity/i100000001").mock(
            return_value=httpx.Response(200, json=fixture("activity_detail"))
        )

        result = tools.get_activity("i100000001")

        assert result["type"] == "Hike"
        assert result["pace_per_km"] == "22:38"

    @respx.mock
    def test_returns_laps(self, tools):
        respx.get(f"{BASE}/activity/i100000001/intervals").mock(
            return_value=httpx.Response(200, json=fixture("activity_intervals"))
        )

        result = tools.get_activity_intervals("i100000001")

        assert len(result["laps"]) == 1


class TestStreams:
    @respx.mock
    def test_downsamples_by_default(self, tools):
        respx.get(f"{BASE}/activity/i100000001/streams").mock(
            return_value=httpx.Response(200, json=fixture("activity_streams"))
        )

        result = tools.get_activity_streams("i100000001")

        assert result["original_points"] == 14019
        assert result["returned_points"] == 200

    @respx.mock
    def test_requests_the_types_that_were_asked_for(self, tools):
        route = respx.get(f"{BASE}/activity/i1/streams").mock(
            return_value=httpx.Response(200, json=[])
        )

        tools.get_activity_streams("i1", types="heartrate,altitude")

        assert route.calls.last.request.url.params["types"] == "heartrate,altitude"

    @respx.mock
    def test_full_mode_keeps_every_point(self, tools):
        respx.get(f"{BASE}/activity/i100000001/streams").mock(
            return_value=httpx.Response(200, json=fixture("activity_streams"))
        )

        result = tools.get_activity_streams("i100000001", full=True)

        assert result["returned_points"] == 14019


class TestWellness:
    @respx.mock
    def test_defaults_to_the_last_thirty_days(self, tools):
        route = respx.get(f"{BASE}/athlete/{ATHLETE}/wellness").mock(
            return_value=httpx.Response(200, json=[])
        )

        tools.get_wellness()

        assert route.calls.last.request.url.params["oldest"] == "2026-07-11"

    @respx.mock
    def test_shapes_each_day(self, tools):
        respx.get(f"{BASE}/athlete/{ATHLETE}/wellness").mock(
            return_value=httpx.Response(200, json=fixture("wellness"))
        )

        result = tools.get_wellness()

        assert len(result["days"]) == 30
        assert "sleepScore" not in result["days"][0]


class TestTrainingReadiness:
    @respx.mock
    def test_defaults_to_a_six_week_window(self, tools):
        route = respx.get(f"{BASE}/athlete/{ATHLETE}/wellness").mock(
            return_value=httpx.Response(200, json=[])
        )

        result = tools.get_training_readiness()

        assert route.calls.last.request.url.params["oldest"] == "2026-06-29"
        assert result["window"] == {"oldest": "2026-06-29", "newest": "2026-08-10"}

    @respx.mock
    def test_assesses_form_from_the_latest_day(self, tools):
        respx.get(f"{BASE}/athlete/{ATHLETE}/wellness").mock(
            return_value=httpx.Response(200, json=fixture("wellness"))
        )

        result = tools.get_training_readiness()

        assert result["as_of"] == "2024-01-30"
        assert result["tsb"] == 4.2
        assert result["form"] == "neutral"
        assert result["ramp"] == "maintaining"

    @respx.mock
    def test_reports_no_hrv_deviation_when_it_has_not_moved(self, tools):
        respx.get(f"{BASE}/athlete/{ATHLETE}/wellness").mock(
            return_value=httpx.Response(200, json=fixture("wellness"))
        )

        result = tools.get_training_readiness()

        assert result["hrv"]["pct_change"] == 0.0
        assert result["hrv"]["below_baseline"] is False

    @respx.mock
    def test_errors_when_the_window_has_no_usable_data(self, tools):
        respx.get(f"{BASE}/athlete/{ATHLETE}/wellness").mock(
            return_value=httpx.Response(200, json=[])
        )

        result = tools.get_training_readiness()

        assert "error" in result


class TestEvents:
    @respx.mock
    def test_looks_forward_by_default_because_events_are_plans(self, tools):
        route = respx.get(f"{BASE}/athlete/{ATHLETE}/events").mock(
            return_value=httpx.Response(200, json=[])
        )

        result = tools.get_events()

        params = route.calls.last.request.url.params
        assert params["oldest"] == "2026-08-10"
        assert params["newest"] == "2026-09-07"
        assert result["events"] == []


class TestBestEfforts:
    @respx.mock
    def test_maps_the_kind_onto_the_right_endpoint(self, tools):
        route = respx.get(f"{BASE}/athlete/{ATHLETE}/hr-curves").mock(
            return_value=httpx.Response(200, json=fixture("hr_curves"))
        )

        result = tools.get_best_efforts(kind="hr", sport_type="Run")

        assert route.called
        assert route.calls.last.request.url.params["type"] == "Run"
        assert result["curves"][0]["best"]["1m"] is not None

    @respx.mock
    def test_supports_pace_and_power(self, tools):
        pace = respx.get(f"{BASE}/athlete/{ATHLETE}/pace-curves").mock(
            return_value=httpx.Response(200, json={"list": []})
        )
        power = respx.get(f"{BASE}/athlete/{ATHLETE}/power-curves").mock(
            return_value=httpx.Response(200, json={"list": []})
        )

        tools.get_best_efforts(kind="pace", sport_type="Run")
        tools.get_best_efforts(kind="power", sport_type="Ride")

        assert pace.called and power.called

    def test_rejects_an_unknown_kind_before_making_a_request(self, tools):
        with pytest.raises(ValueError) as excinfo:
            tools.get_best_efforts(kind="cadence", sport_type="Run")

        assert "hr" in str(excinfo.value)

    @respx.mock
    def test_defaults_to_the_last_twelve_months(self, tools):
        route = respx.get(f"{BASE}/athlete/{ATHLETE}/hr-curves").mock(
            return_value=httpx.Response(200, json={"list": []})
        )

        tools.get_best_efforts(kind="hr", sport_type="Run")

        assert route.calls.last.request.url.params["oldest"] == "2025-08-10"


class TestSmallReads:
    @respx.mock
    def test_profile_is_flattened(self, tools):
        respx.get(f"{BASE}/athlete/{ATHLETE}/profile").mock(
            return_value=httpx.Response(200, json=fixture("athlete_profile"))
        )

        result = tools.get_athlete_profile()

        assert result["id"] == "i000001"
        assert result["timezone"] == "UTC"

    @respx.mock
    def test_sport_settings_keep_ftp_and_zones(self, tools):
        respx.get(f"{BASE}/athlete/{ATHLETE}/sport-settings").mock(
            return_value=httpx.Response(200, json=fixture("sport_settings"))
        )

        result = tools.get_sport_settings()

        ride = next(s for s in result["sports"] if "Ride" in s["types"])
        assert ride["ftp"] == 250

    @respx.mock
    def test_workouts_returns_library_and_folders(self, tools):
        respx.get(f"{BASE}/athlete/{ATHLETE}/workouts").mock(
            return_value=httpx.Response(200, json=[])
        )
        respx.get(f"{BASE}/athlete/{ATHLETE}/folders").mock(
            return_value=httpx.Response(200, json=fixture("folders"))
        )

        result = tools.list_workouts()

        assert result["workouts"] == []
        assert len(result["folders"]) == 1

    @respx.mock
    def test_gear_passes_through(self, tools):
        respx.get(f"{BASE}/athlete/{ATHLETE}/gear").mock(
            return_value=httpx.Response(200, json=[{"id": "b1", "name": "Shoes"}])
        )

        assert tools.get_gear()["gear"][0]["name"] == "Shoes"


class TestRawEscapeHatch:
    @respx.mock
    def test_returns_the_body_unshaped(self, tools):
        respx.get(f"{BASE}/athlete/{ATHLETE}/profile").mock(
            return_value=httpx.Response(200, json={"athlete": {"id": "i123", "extra": "kept"}})
        )

        result = tools.intervals_get_raw("athlete/i123/profile")

        assert result == {"athlete": {"id": "i123", "extra": "kept"}}

    @respx.mock
    def test_substitutes_the_configured_athlete_id(self, tools):
        route = respx.get(f"{BASE}/athlete/{ATHLETE}/wellness").mock(
            return_value=httpx.Response(200, json=[])
        )

        tools.intervals_get_raw("athlete/{athlete}/wellness")

        assert route.called
