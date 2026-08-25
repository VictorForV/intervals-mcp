"""Tests for response shaping.

The point of compact.py is that raw intervals.icu payloads are too large to put
in front of an agent. These tests assert the shaping is both lossy in the right
places and lossless where a coach needs detail.
"""

from intervals_mcp import compact


class TestPick:
    def test_keeps_only_whitelisted_fields(self):
        result = compact.pick({"a": 1, "b": 2, "c": 3}, ["a", "c"])

        assert result == {"a": 1, "c": 3}

    def test_drops_null_fields(self):
        result = compact.pick({"a": 1, "b": None}, ["a", "b"])

        assert result == {"a": 1}

    def test_drops_empty_lists_and_strings(self):
        result = compact.pick({"a": 1, "b": [], "c": ""}, ["a", "b", "c"])

        assert result == {"a": 1}

    def test_keeps_false_and_zero(self):
        result = compact.pick({"race": False, "load": 0}, ["race", "load"])

        assert result == {"race": False, "load": 0}

    def test_ignores_requested_fields_that_are_absent(self):
        result = compact.pick({"a": 1}, ["a", "nope"])

        assert result == {"a": 1}


class TestDownsample:
    def test_reduces_long_series_to_requested_point_count(self):
        result = compact.downsample(list(range(1000)), 100)

        assert len(result) == 100

    def test_returns_series_unchanged_when_already_short(self):
        result = compact.downsample([1, 2, 3], 100)

        assert result == [1, 2, 3]

    def test_preserves_first_and_last_sample(self):
        result = compact.downsample(list(range(1000)), 10)

        assert result[0] == 0
        assert result[-1] == 999

    def test_samples_evenly_across_the_series(self):
        result = compact.downsample(list(range(100)), 5)

        assert result == [0, 24, 49, 74, 99]


class TestSummarizeSeries:
    def test_reports_min_mean_max(self):
        result = compact.summarize_series([10, 20, 30])

        assert result["min"] == 10
        assert result["max"] == 30
        assert result["mean"] == 20

    def test_ignores_nulls_that_intervals_puts_in_streams(self):
        result = compact.summarize_series([None, 10, 20, None])

        assert result["min"] == 10
        assert result["max"] == 20
        assert result["mean"] == 15

    def test_returns_none_stats_for_an_all_null_series(self):
        result = compact.summarize_series([None, None])

        assert result["min"] is None
        assert result["mean"] is None

    def test_rounds_mean_to_two_decimals(self):
        result = compact.summarize_series([1, 2])

        assert result["mean"] == 1.5

    def test_summarizes_a_latlng_stream_as_a_bounding_box_instead_of_crashing(self):
        result = compact.summarize_series([[55.751, 37.618], [55.753, 37.620], [55.752, 37.615]])

        assert result == {
            "lat_min": 55.751,
            "lat_max": 55.753,
            "lon_min": 37.615,
            "lon_max": 37.620,
            "points": 3,
        }

    def test_ignores_nulls_in_a_latlng_stream(self):
        result = compact.summarize_series([[55.751, 37.618], None, [55.752, 37.619]])

        assert result["points"] == 2


class TestPaceFromSpeed:
    def test_converts_metres_per_second_to_pace_per_kilometre(self):
        assert compact.pace_from_speed(1000 / 300) == "5:00"

    def test_formats_seconds_with_leading_zero(self):
        assert compact.pace_from_speed(1000 / 305) == "5:05"

    def test_returns_none_for_zero_or_missing_speed(self):
        assert compact.pace_from_speed(0) is None
        assert compact.pace_from_speed(None) is None


class TestCompactActivity:
    def test_cuts_the_payload_down_sharply(self, activity_detail):
        result = compact.compact_activity(activity_detail)

        assert len(activity_detail) == 183, "fixture changed; revisit the whitelist"
        assert len(result) < 30

    def test_keeps_the_fields_a_coach_reasons_about(self, activity_detail):
        result = compact.compact_activity(activity_detail)

        assert result["id"] == "i100000001"
        assert result["type"] == "Hike"
        assert result["name"].startswith("Example ")
        assert result["start_date_local"] == "2024-01-01T10:00:00"
        assert result["distance"] == 10323.1
        assert result["moving_time"] == 9860
        assert result["average_heartrate"] == 112
        assert result["max_heartrate"] == 142
        assert result["icu_training_load"] == 69
        assert result["total_elevation_gain"] == 718.2007

    def test_drops_the_null_power_fields(self, activity_detail):
        result = compact.compact_activity(activity_detail)

        assert "icu_pm_ftp" not in result
        assert "icu_weighted_avg_watts" not in result

    def test_drops_internal_bookkeeping_fields(self, activity_detail):
        result = compact.compact_activity(activity_detail)

        assert "skyline_chart_bytes" not in result
        assert "icu_sync_date" not in result
        assert "external_id" not in result

    def test_adds_derived_pace_so_the_agent_need_not_divide(self, activity_detail):
        result = compact.compact_activity(activity_detail)

        # 0.736 m/s over a hike is about 22:39 per km.
        assert result["pace_per_km"] == "22:38"

    def test_shapes_every_activity_in_a_list(self, activities_list):
        result = compact.compact_activities(activities_list)

        assert len(result) == len(activities_list)
        assert all("id" in a for a in result)


class TestCompactStreams:
    def test_downsamples_each_series(self, activity_streams):
        result = compact.compact_streams(activity_streams, points=200)

        for series in result["series"]:
            assert len(series["data"]) == 200

    def test_reports_the_original_resolution(self, activity_streams):
        result = compact.compact_streams(activity_streams, points=200)

        assert result["original_points"] == 14019
        assert result["returned_points"] == 200

    def test_summarizes_each_series(self, activity_streams):
        result = compact.compact_streams(activity_streams, points=200)

        hr = next(s for s in result["series"] if s["type"] == "heartrate")
        assert hr["summary"]["max"] == 142
        assert hr["summary"]["min"] is not None

    def test_full_mode_keeps_every_point(self, activity_streams):
        result = compact.compact_streams(activity_streams, full=True)

        assert result["returned_points"] == 14019
        for series in result["series"]:
            assert len(series["data"]) == 14019

    def test_shrinks_the_payload_by_orders_of_magnitude(self, activity_streams):
        import json

        raw = len(json.dumps(activity_streams))
        shaped = len(json.dumps(compact.compact_streams(activity_streams, points=200)))

        assert raw > 200_000, "fixture changed; revisit this assertion"
        assert shaped < raw / 20

    def test_handles_a_latlng_stream_without_crashing(self, activity_streams):
        streams = [
            *activity_streams,
            {
                "type": "latlng",
                "data": [[55.751, 37.618], [55.752, 37.619], [55.753, 37.620]],
            },
        ]

        result = compact.compact_streams(streams, points=200)

        latlng = next(s for s in result["series"] if s["type"] == "latlng")
        assert latlng["data"] == [[55.751, 37.618], [55.752, 37.619], [55.753, 37.620]]
        assert latlng["summary"]["lat_min"] == 55.751
        assert latlng["summary"]["lon_max"] == 37.620

    def test_downsamples_a_latlng_stream_as_whole_pairs(self):
        pairs = [[55.7 + i * 0.001, 37.6 + i * 0.001] for i in range(1000)]
        streams = [{"type": "latlng", "data": pairs}]

        result = compact.compact_streams(streams, points=10)

        latlng = result["series"][0]
        assert len(latlng["data"]) == 10
        assert all(len(point) == 2 for point in latlng["data"])
        assert latlng["data"][0] == pairs[0]
        assert latlng["data"][-1] == pairs[-1]


class TestCompactWellness:
    def test_drops_fields_that_are_null_for_every_day(self, wellness_days):
        result = compact.compact_wellness(wellness_days)

        assert len(result) == 30
        assert not any("sleepScore" in day for day in result)

    def test_keeps_training_load_metrics(self, wellness_days):
        result = compact.compact_wellness(wellness_days)

        assert result[0]["id"] == "2024-01-01"
        assert "ctl" in result[0]
        assert "atl" in result[0]

    def test_rounds_fitness_metrics_to_one_decimal(self, wellness_days):
        result = compact.compact_wellness(wellness_days)

        assert result[0]["ctl"] == round(wellness_days[0]["ctl"], 1)


class TestCompactIntervals:
    def test_returns_one_entry_per_lap(self, activity_intervals):
        result = compact.compact_intervals(activity_intervals)

        assert len(result["laps"]) == len(activity_intervals["icu_intervals"])

    def test_trims_each_lap_to_the_useful_fields(self, activity_intervals):
        result = compact.compact_intervals(activity_intervals)

        assert len(activity_intervals["icu_intervals"][0]) == 84
        assert len(result["laps"][0]) < 20

    def test_keeps_lap_distance_and_duration(self, activity_intervals):
        result = compact.compact_intervals(activity_intervals)

        lap = result["laps"][0]
        assert "distance" in lap
        assert "moving_time" in lap


class TestCompactCurves:
    def test_returns_one_entry_per_curve(self, hr_curves):
        result = compact.compact_curves(hr_curves)

        assert len(result["curves"]) == len(hr_curves["list"])

    def test_reduces_156_durations_to_the_ones_a_coach_quotes(self, hr_curves):
        raw = hr_curves["list"][0]
        result = compact.compact_curves(hr_curves)

        assert len(raw["secs"]) == 156, "fixture changed; revisit this assertion"
        assert len(result["curves"][0]["best"]) <= 10

    def test_keeps_the_value_recorded_at_each_duration(self, hr_curves):
        raw = hr_curves["list"][0]
        result = compact.compact_curves(hr_curves)

        expected = raw["values"][raw["secs"].index(60)]
        assert result["curves"][0]["best"]["1m"] == expected

    def test_labels_the_window_the_curve_covers(self, hr_curves):
        result = compact.compact_curves(hr_curves)

        assert result["curves"][0]["label"] == "1 year"


class TestFormatDuration:
    def test_formats_under_an_hour_as_minutes_and_seconds(self):
        assert compact.format_duration(1221) == "20:21"

    def test_formats_over_an_hour_with_hours(self):
        assert compact.format_duration(6570) == "1:49:30"

    def test_pads_seconds(self):
        assert compact.format_duration(59) == "0:59"

    def test_returns_none_for_missing_input(self):
        assert compact.format_duration(None) is None


class TestCompactPaceCurves:
    """Pace curves are indexed by distance, not by seconds: `values` holds the
    fastest time in seconds to cover `distance` metres. Reading them like an hr
    curve produced an empty result."""

    def test_reports_best_times_at_standard_race_distances(self, pace_curves):
        result = compact.compact_curves(pace_curves)

        best = result["curves"][0]["best"]
        assert best["400m"]["time"] == "0:59"
        assert best["1k"]["time"] == "3:57"
        assert best["5k"]["time"] == "20:21"
        assert best["10k"]["time"] == "50:00"

    def test_derives_pace_per_kilometre_for_each_distance(self, pace_curves):
        result = compact.compact_curves(pace_curves)

        best = result["curves"][0]["best"]
        # 5 km in 1221 s is 4:04 per km.
        assert best["5k"]["pace_per_km"] == "4:04"
        assert best["10k"]["pace_per_km"] == "5:00"

    def test_omits_distances_the_athlete_has_never_covered(self, pace_curves):
        result = compact.compact_curves(pace_curves)

        # The curve tops out at 18 km, so a marathon must not be invented.
        assert "M" not in result["curves"][0]["best"]

    def test_marks_the_curve_as_distance_indexed(self, pace_curves):
        result = compact.compact_curves(pace_curves)

        assert result["curves"][0]["indexed_by"] == "distance"

    def test_marks_a_time_indexed_curve_as_such(self, hr_curves):
        result = compact.compact_curves(hr_curves)

        assert result["curves"][0]["indexed_by"] == "duration"

    def test_shrinks_the_payload(self, pace_curves):
        import json

        raw = len(json.dumps(pace_curves))
        shaped = len(json.dumps(compact.compact_curves(pace_curves)))

        assert shaped < raw / 5


class TestCompactSportSettings:
    def test_keeps_one_entry_per_sport_group(self, sport_settings):
        result = compact.compact_sport_settings(sport_settings)

        assert len(result) == len(sport_settings)

    def test_keeps_ftp_and_zones(self, sport_settings):
        result = compact.compact_sport_settings(sport_settings)

        ride = next(s for s in result if "Ride" in s["types"])
        assert ride["ftp"] == 250
        assert ride["power_zones"] == [55, 75, 90, 105, 120, 150, 999]

    def test_shrinks_the_payload(self, sport_settings):
        import json

        raw = len(json.dumps(sport_settings))
        shaped = len(json.dumps(compact.compact_sport_settings(sport_settings)))

        assert shaped < raw / 2
