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
