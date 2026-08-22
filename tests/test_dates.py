"""Tests for date resolution.

An agent often does not know today's date, and several endpoints reject requests
without an `oldest` parameter. The server resolves both, so `today` is injected
here to keep the tests deterministic.
"""

import datetime

import pytest

from intervals_mcp import dates

TODAY = datetime.date(2026, 8, 10)


class TestResolveDate:
    def test_passes_an_iso_date_through(self):
        assert dates.resolve("2026-03-04", today=TODAY) == "2026-03-04"

    def test_understands_today(self):
        assert dates.resolve("today", today=TODAY) == "2026-08-10"

    def test_understands_days_back(self):
        assert dates.resolve("-7d", today=TODAY) == "2026-08-03"

    def test_understands_weeks_back(self):
        assert dates.resolve("-2w", today=TODAY) == "2026-07-27"

    def test_understands_months_back(self):
        assert dates.resolve("-3m", today=TODAY) == "2026-05-10"

    def test_understands_years_back(self):
        assert dates.resolve("-1y", today=TODAY) == "2025-08-10"

    def test_understands_days_forward(self):
        assert dates.resolve("+28d", today=TODAY) == "2026-09-07"

    def test_clamps_to_the_end_of_a_shorter_month(self):
        assert dates.resolve("-1m", today=datetime.date(2026, 3, 31)) == "2026-02-28"

    def test_crosses_a_year_boundary_going_back(self):
        assert dates.resolve("-2m", today=datetime.date(2026, 1, 15)) == "2025-11-15"

    def test_ignores_surrounding_whitespace(self):
        assert dates.resolve("  -7d  ", today=TODAY) == "2026-08-03"

    def test_accepts_a_date_object(self):
        assert dates.resolve(datetime.date(2020, 1, 2), today=TODAY) == "2020-01-02"

    def test_rejects_nonsense_with_an_actionable_message(self):
        with pytest.raises(dates.DateError) as excinfo:
            dates.resolve("last tuesday", today=TODAY)

        message = str(excinfo.value)
        assert "last tuesday" in message
        assert "-7d" in message, "the message should show an accepted form"

    def test_rejects_an_impossible_calendar_date(self):
        with pytest.raises(dates.DateError):
            dates.resolve("2026-02-30", today=TODAY)


class TestWindow:
    def test_applies_both_defaults_when_nothing_is_given(self):
        oldest, newest = dates.window(None, None, default_oldest="-30d", today=TODAY)

        assert oldest == "2026-07-11"
        assert newest == "2026-08-10"

    def test_respects_an_explicit_oldest(self):
        oldest, newest = dates.window("2019-01-01", None, default_oldest="-30d", today=TODAY)

        assert oldest == "2019-01-01"
        assert newest == "2026-08-10"

    def test_supports_a_forward_looking_default_for_planned_events(self):
        oldest, newest = dates.window(
            None, None, default_oldest="today", default_newest="+28d", today=TODAY
        )

        assert oldest == "2026-08-10"
        assert newest == "2026-09-07"

    def test_swaps_a_reversed_range_rather_than_returning_nothing(self):
        oldest, newest = dates.window("2026-08-01", "2026-07-01", default_oldest="-30d", today=TODAY)

        assert (oldest, newest) == ("2026-07-01", "2026-08-01")
