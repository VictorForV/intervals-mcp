import json
import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture
def activity_detail():
    """A synthetic API-shaped hike with 183 fields."""
    return load("activity_detail")


@pytest.fixture
def activities_list():
    return load("activities_list")


@pytest.fixture
def activity_streams():
    """Three series of 14019 points each."""
    return load("activity_streams")


@pytest.fixture
def activity_intervals():
    return load("activity_intervals")


@pytest.fixture
def wellness_days():
    """30 days of June 2022; only 10 of 46 fields ever non-null."""
    return load("wellness")


@pytest.fixture
def sport_settings():
    return load("sport_settings")


@pytest.fixture
def athlete_profile():
    return load("athlete_profile")


@pytest.fixture
def hr_curves():
    """Time-indexed curve: best heart rate held for N seconds."""
    return load("hr_curves")


@pytest.fixture
def pace_curves():
    """Distance-indexed curve: fastest time over N metres. A different shape
    from hr/power curves, which caught a real bug."""
    return load("pace_curves")
