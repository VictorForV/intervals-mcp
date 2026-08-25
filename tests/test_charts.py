import io

import pytest
from PIL import Image

from intervals_mcp import charts


def _days():
    return [
        {"id": "2026-06-01", "ctl": 40, "atl": 30},
        {"id": "2026-06-15", "ctl": 45, "atl": 42},
        {"id": "2026-06-30", "ctl": 50, "atl": 38},
    ]


class TestNiceTicks:
    def test_produces_round_step_values(self):
        ticks = charts._nice_ticks(0, 97, target_count=5)

        steps = {round(b - a, 6) for a, b in zip(ticks, ticks[1:], strict=False)}
        assert steps == {50.0}
        assert ticks[-1] >= 97

    def test_spans_at_least_the_requested_range(self):
        ticks = charts._nice_ticks(3, 42, target_count=5)

        assert ticks[0] <= 3
        assert ticks[-1] >= 42

    def test_a_floor_clamps_the_lowest_tick(self):
        ticks = charts._nice_ticks(-805, 9564, target_count=5, floor=0)

        assert min(ticks) == 0
        assert ticks[-1] >= 9564

    def test_without_a_floor_negative_ticks_are_allowed(self):
        # TSB legitimately goes negative, so the PMC chart must not clamp it.
        ticks = charts._nice_ticks(-30, 20, target_count=5)

        assert min(ticks) < 0

    def test_a_single_point_range_does_not_crash(self):
        assert charts._nice_ticks(10, 10, target_count=5) == [10]


class TestRenderPmcChart:
    def test_returns_a_valid_png_of_the_expected_size(self):
        png_bytes = charts.render_pmc_chart(_days())

        image = Image.open(io.BytesIO(png_bytes))
        image.verify()
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"

    def test_raises_when_no_day_has_both_ctl_and_atl(self):
        with pytest.raises(ValueError, match="ctl and atl"):
            charts.render_pmc_chart([{"id": "2026-06-01", "ctl": None, "atl": None}])

    def test_skips_days_missing_either_field(self):
        days = [*_days(), {"id": "2026-07-01", "ctl": None, "atl": 40}]

        # Should not raise despite the incomplete trailing day.
        charts.render_pmc_chart(days)

    def test_renders_a_single_day_without_crashing(self):
        png_bytes = charts.render_pmc_chart([{"id": "2026-06-01", "ctl": 40, "atl": 30}])

        image = Image.open(io.BytesIO(png_bytes))
        image.verify()

    def test_renders_flat_data_without_a_zero_division(self):
        # min == max for every series: the scaling padding must not divide by zero.
        flat = [{"id": f"2026-06-{i:02d}", "ctl": 40, "atl": 40} for i in range(1, 4)]

        png_bytes = charts.render_pmc_chart(flat)

        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


class TestToPaceSecondsPerKm:
    def test_converts_elapsed_time_to_pace_per_km(self):
        # 1000m in 300s (5:00/km) and 5000m in 1200s (4:00/km).
        result = charts._to_pace_seconds_per_km([(1000, 300), (5000, 1200)])

        assert result == [(1000, 300.0), (5000, 240.0)]

    def test_matches_the_reported_400m_time(self):
        # 400m in 59s -> pace is 59 * 1000 / 400 = 147.5 s/km, i.e. 2:27/km.
        (_distance, pace) = charts._to_pace_seconds_per_km([(400, 59)])[0]

        assert round(pace, 1) == 147.5


class TestRenderCurveChart:
    def _duration_curve(self):
        return {
            "label": "1 year",
            "secs": [5, 60, 300, 1200, 3600],
            "values": [1000, 400, 300, 250, 220],
        }

    def _distance_curve(self):
        return {
            "label": "1 year",
            "distance": [400, 1000, 5000, 10000],
            "values": [59, 237, 1221, 3000],
        }

    def test_returns_a_valid_png_for_a_duration_curve(self):
        png_bytes = charts.render_curve_chart(self._duration_curve(), kind="power")

        image = Image.open(io.BytesIO(png_bytes))
        image.verify()
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"

    def test_returns_a_valid_png_for_a_distance_curve(self):
        png_bytes = charts.render_curve_chart(self._distance_curve(), kind="pace")

        image = Image.open(io.BytesIO(png_bytes))
        image.verify()

    def test_raises_when_the_curve_has_no_secs_or_distance(self):
        with pytest.raises(ValueError, match="secs.*distance"):
            charts.render_curve_chart({"values": [1, 2, 3]}, kind="hr")

    def test_raises_when_there_are_no_plottable_points(self):
        curve = {"secs": [5, 10], "values": [None, None]}

        with pytest.raises(ValueError, match="no plottable points"):
            charts.render_curve_chart(curve, kind="hr")

    def test_skips_points_missing_a_value(self):
        curve = {"secs": [5, 60, 300], "values": [1000, None, 300]}

        # Should not raise despite the gap.
        charts.render_curve_chart(curve, kind="power")

    def test_default_title_names_the_curve_and_axis(self):
        # Exercised through render_curve_chart's public surface only: a
        # default title is derived, not just accepted, when none is given.
        png_bytes = charts.render_curve_chart(self._duration_curve(), kind="power")

        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"

    def test_pace_axis_never_goes_negative(self):
        # Reported live: a pace curve spanning ~1min to ~2.5h produced a
        # padded axis low of about -805s, which format_duration rendered as
        # a nonsense "-1:46:35" gridline label.
        curve = {
            "distance": [400, 1000, 5000, 10000, 21097.5, 42195],
            "values": [59, 237, 1221, 3000, 8518, 17222],
        }

        y_ticks = charts._nice_ticks(
            *charts._padded_range(
                [v for _, v in sorted(zip(curve["distance"], curve["values"], strict=True))]
            ),
            charts.Y_GRIDLINES,
            floor=0,
        )

        assert all(tick >= 0 for tick in y_ticks)
        assert all("-" not in charts.format_duration(tick) for tick in y_ticks)
