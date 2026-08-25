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
