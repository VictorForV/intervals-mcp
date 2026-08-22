"""Resolve the date arguments the intervals.icu API insists on.

Agents routinely do not know today's date, and `oldest` is mandatory on several
endpoints, so relative forms like ``-7d`` are accepted and expanded here.
``today`` is injectable to keep this testable.
"""

import calendar
import datetime
import re

RELATIVE = re.compile(r"^([+-])(\d+)([dwmy])$")

ACCEPTED_FORMS = "2026-08-01, today, -7d, -6w, -3m, -1y, +28d"


class DateError(Exception):
    """A date argument could not be understood."""


def _shift_months(day: datetime.date, months: int) -> datetime.date:
    total = day.month - 1 + months
    year = day.year + total // 12
    month = total % 12 + 1
    # Clamp so that 31 March minus one month is the last day of February.
    return day.replace(year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1]))


def resolve(value: str | datetime.date | None, today: datetime.date | None = None) -> str:
    """Return ``value`` as an ISO date string, expanding relative forms."""
    if isinstance(value, datetime.date):
        return value.isoformat()

    today = today or datetime.date.today()
    text = (value or "").strip()

    if not text:
        raise DateError(f"Empty date. Accepted forms: {ACCEPTED_FORMS}.")

    if text.lower() == "today":
        return today.isoformat()
    if text.lower() == "yesterday":
        return (today - datetime.timedelta(days=1)).isoformat()

    match = RELATIVE.match(text)
    if match:
        sign, amount, unit = match.groups()
        count = int(amount) * (-1 if sign == "-" else 1)
        if unit == "d":
            return (today + datetime.timedelta(days=count)).isoformat()
        if unit == "w":
            return (today + datetime.timedelta(weeks=count)).isoformat()
        if unit == "m":
            return _shift_months(today, count).isoformat()
        return _shift_months(today, count * 12).isoformat()

    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise DateError(
            f"Could not read {text!r} as a date. Accepted forms: {ACCEPTED_FORMS}."
        ) from exc


def window(
    oldest: str | None,
    newest: str | None,
    default_oldest: str,
    default_newest: str = "today",
    today: datetime.date | None = None,
) -> tuple[str, str]:
    """Resolve a date range, filling in defaults and ordering the ends."""
    today = today or datetime.date.today()
    start = resolve(oldest or default_oldest, today=today)
    end = resolve(newest or default_newest, today=today)
    if start > end:
        start, end = end, start
    return start, end
