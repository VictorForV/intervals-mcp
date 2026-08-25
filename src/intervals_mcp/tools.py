"""Tool logic: resolve arguments, call the API, shape the result.

Kept separate from server.py so the tools can be tested without starting an MCP
server. Every method here is read-only.
"""

import datetime
from collections.abc import Callable
from typing import Any

from . import analytics, charts, compact, dates
from .client import IntervalsClient

CURVE_ENDPOINTS = {"hr": "hr-curves", "pace": "pace-curves", "power": "power-curves"}

DEFAULT_STREAM_TYPES = "heartrate,velocity_smooth,altitude,cadence,watts"


class IntervalsTools:
    def __init__(
        self,
        client: IntervalsClient,
        today: Callable[[], datetime.date] = datetime.date.today,
    ) -> None:
        self._client = client
        self._today = today

    def _window(self, oldest, newest, default_oldest, default_newest="today"):
        return dates.window(
            oldest,
            newest,
            default_oldest=default_oldest,
            default_newest=default_newest,
            today=self._today(),
        )

    # --- athlete context -------------------------------------------------

    def get_athlete_profile(self) -> dict:
        return compact.compact_profile(self._client.athlete_get("profile"))

    def get_sport_settings(self) -> dict:
        raw = self._client.athlete_get("sport-settings")
        return {"sports": compact.compact_sport_settings(raw)}

    def get_gear(self) -> dict:
        return {"gear": self._client.athlete_get("gear")}

    def list_workouts(self) -> dict:
        return {
            "workouts": self._client.athlete_get("workouts"),
            "folders": self._client.athlete_get("folders"),
        }

    # --- completed training ----------------------------------------------

    def list_activities(
        self,
        oldest: str | None = None,
        newest: str | None = None,
        limit: int = 50,
        activity_type: str | None = None,
    ) -> dict:
        start, end = self._window(oldest, newest, default_oldest="-30d")
        raw = self._client.athlete_get(
            "activities", {"oldest": start, "newest": end}
        )

        if activity_type:
            wanted = activity_type.strip().lower()
            raw = [a for a in raw if (a.get("type") or "").lower() == wanted]

        matched = len(raw)
        # The API returns newest first; sort defensively so truncation keeps
        # the most recent sessions rather than whatever order arrived.
        raw = sorted(raw, key=lambda a: a.get("start_date_local") or "", reverse=True)
        shown = raw[:limit] if limit else raw

        result = {
            "window": {"oldest": start, "newest": end},
            "matched": matched,
            "returned": len(shown),
            "activities": compact.compact_activities(shown),
        }
        if matched > len(shown):
            result["note"] = (
                f"{matched} activities matched, showing the {len(shown)} most recent. "
                "Raise limit or narrow the date range to see the rest."
            )
        return result

    def get_activity(self, activity_id: str) -> dict:
        return compact.compact_activity(self._client.get(f"activity/{activity_id}"))

    def get_activity_intervals(self, activity_id: str) -> dict:
        return compact.compact_intervals(self._client.get(f"activity/{activity_id}/intervals"))

    def get_activity_streams(
        self,
        activity_id: str,
        types: str = DEFAULT_STREAM_TYPES,
        points: int = 200,
        full: bool = False,
    ) -> dict:
        raw = self._client.get(f"activity/{activity_id}/streams", {"types": types})
        return compact.compact_streams(raw, points=points, full=full)

    # --- form and plan ---------------------------------------------------

    def get_wellness(self, oldest: str | None = None, newest: str | None = None) -> dict:
        start, end = self._window(oldest, newest, default_oldest="-30d")
        raw = self._client.athlete_get("wellness", {"oldest": start, "newest": end})
        return {
            "window": {"oldest": start, "newest": end},
            "days": compact.compact_wellness(raw),
        }

    def get_training_readiness(self, oldest: str | None = None, newest: str | None = None) -> dict:
        # A six-week default gives the HRV comparison a real baseline (the
        # last 7 days against everything older) rather than just a day or two.
        start, end = self._window(oldest, newest, default_oldest="-42d")
        raw = self._client.athlete_get("wellness", {"oldest": start, "newest": end})
        result = analytics.assess_readiness(raw)
        result["window"] = {"oldest": start, "newest": end}
        return result

    def get_training_load_chart(self, oldest: str | None = None, newest: str | None = None) -> bytes:
        # 90 days is the usual PMC window: long enough to see a build and a
        # taper, short enough that daily wiggle is still legible.
        start, end = self._window(oldest, newest, default_oldest="-90d")
        raw = self._client.athlete_get("wellness", {"oldest": start, "newest": end})
        return charts.render_pmc_chart(raw, title=f"Training load {start} to {end}")

    def get_events(self, oldest: str | None = None, newest: str | None = None) -> dict:
        # Events are plans, so the useful default window looks forward.
        start, end = self._window(
            oldest, newest, default_oldest="today", default_newest="+28d"
        )
        raw = self._client.athlete_get("events", {"oldest": start, "newest": end})
        return {
            "window": {"oldest": start, "newest": end},
            "events": compact.compact_events(raw),
        }

    def _fetch_curve(
        self, kind: str, sport_type: str, oldest: str | None, newest: str | None
    ) -> tuple[dict, str, str]:
        endpoint = CURVE_ENDPOINTS.get(kind.strip().lower())
        if not endpoint:
            raise ValueError(
                f"Unknown kind {kind!r}. Use one of: {', '.join(sorted(CURVE_ENDPOINTS))}."
            )
        start, end = self._window(oldest, newest, default_oldest="-1y")
        raw = self._client.athlete_get(
            endpoint, {"type": sport_type, "oldest": start, "newest": end}
        )
        return raw, start, end

    def get_best_efforts(
        self,
        kind: str,
        sport_type: str = "Run",
        oldest: str | None = None,
        newest: str | None = None,
    ) -> dict:
        raw, start, end = self._fetch_curve(kind, sport_type, oldest, newest)
        result = compact.compact_curves(raw)
        result["window"] = {"oldest": start, "newest": end}
        result["sport_type"] = sport_type
        return result

    def get_best_effort_chart(
        self,
        kind: str,
        sport_type: str = "Run",
        oldest: str | None = None,
        newest: str | None = None,
    ) -> bytes:
        raw, start, end = self._fetch_curve(kind, sport_type, oldest, newest)
        curves = raw.get("list") or []
        if not curves:
            raise ValueError(f"No {kind} curve data for {sport_type} in this window.")
        title = f"{sport_type} {kind} curve ({start} to {end})"
        return charts.render_curve_chart(curves[0], kind=kind, title=title)

    # --- escape hatch ----------------------------------------------------

    def intervals_get_raw(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET any v1 path and return the body unshaped.

        ``{athlete}`` in the path expands to the configured athlete id.
        """
        path = path.replace("{athlete}", self._client.athlete_id)
        return self._client.get(path, params)
