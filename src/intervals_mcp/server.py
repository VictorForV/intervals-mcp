"""MCP server exposing one athlete's intervals.icu data, read-only.

Two transports are served from one app so the same URL works whether the client
speaks legacy SSE or streamable HTTP: ChatGPT's connector dialog suggests
``/sse``, while newer clients use ``/mcp``.

Both live under a secret path token. ChatGPT's connector dialog offers no way to
send an API key, so the token in the URL is what keeps the data private — treat
the URL itself as a password.
"""

import contextlib
import functools
import os
import secrets
from collections.abc import Sequence
from typing import Any

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import config
from .client import IntervalsClient, IntervalsError
from .config import Config, UserConfig
from .tools import IntervalsTools

INSTRUCTIONS = """\
Read-only access to one athlete's intervals.icu training data: completed
activities, laps, second-by-second streams, training load and wellness history,
planned calendar entries, best-effort curves, and zone settings.

Use it to reason like a coach. Start with get_athlete_profile and
get_sport_settings for zones and FTP, get_wellness for fitness (CTL), fatigue
(ATL) and ramp rate, and list_activities for what was actually done.

Date arguments are optional everywhere. They accept ISO dates (2026-08-01) and
relative forms (today, -7d, -6w, -3m, -1y, +28d). Omit them to get sensible
defaults; every response echoes the window it used, so there is no need to guess
today's date.

Responses are trimmed to meaningful fields and empty ones are dropped, so a run
carries no power fields. Streams are downsampled by default; ask for full=true
only when you truly need every sample.

Nothing here can modify the account.
"""


def generate_token() -> str:
    """A URL-safe secret long enough to be unguessable in a public path."""
    return secrets.token_urlsafe(32)


def build_server(tools: IntervalsTools | None = None) -> MCPServer:
    """Assemble the MCP server. ``tools`` is injectable for tests."""
    if tools is None:
        tools = IntervalsTools(IntervalsClient(config.load_config()))

    mcp = MCPServer(
        name="intervals-icu",
        title="intervals.icu training data",
        instructions=INSTRUCTIONS,
        version="0.1.0",
        website_url="https://intervals.icu",
    )

    def guard(fn):
        """Turn API failures into readable text instead of a transport error.

        functools.wraps is essential rather than cosmetic here: the tool schema
        is derived from the wrapper's signature, so without __wrapped__ every
        tool would advertise ``args``/``kwargs`` instead of its real parameters.
        """

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except (IntervalsError, ValueError, config.ConfigError) as exc:
                return {"error": str(exc)}

        return wrapper

    @mcp.tool()
    @guard
    def get_athlete_profile() -> dict:
        """The athlete's profile: name, location, timezone, sex.

        Read this first when you need to interpret local times or address the
        athlete by name.
        """
        return tools.get_athlete_profile()

    @mcp.tool()
    @guard
    def get_sport_settings() -> dict:
        """Training zones and thresholds per sport: FTP, LTHR, max HR, power,
        heart-rate and pace zones, sweet spot range.

        Read this before judging whether a session was easy or hard; zone
        boundaries differ per sport.
        """
        return tools.get_sport_settings()

    @mcp.tool()
    @guard
    def list_activities(
        oldest: str | None = None,
        newest: str | None = None,
        limit: int = 50,
        activity_type: str | None = None,
    ) -> dict:
        """Completed activities in a date range, newest first.

        Defaults to the last 30 days. Filter by activity_type such as Run,
        TrailRun, Ride, Swim, Hike, Workout, WeightTraining, Yoga. Each entry
        carries distance, duration, pace, heart rate, elevation, training load
        and the CTL/ATL standing at the time. The response reports how many
        activities matched versus how many were returned.
        """
        return tools.list_activities(
            oldest=oldest, newest=newest, limit=limit, activity_type=activity_type
        )

    @mcp.tool()
    @guard
    def get_activity(activity_id: str) -> dict:
        """Full detail for one activity, by id from list_activities.

        Adds fields the list view omits, including heart-rate time in zone,
        calories, TRIMP and perceived effort where the athlete recorded it.
        """
        return tools.get_activity(activity_id)

    @mcp.tool()
    @guard
    def get_activity_intervals(activity_id: str) -> dict:
        """Laps and detected intervals inside one activity.

        Use it to see how a session was structured: per-lap distance, duration,
        pace, heart rate, power and zone. This is where interval execution shows
        up, such as whether reps faded.
        """
        return tools.get_activity_intervals(activity_id)

    @mcp.tool()
    @guard
    def get_activity_streams(
        activity_id: str,
        types: str = "heartrate,velocity_smooth,altitude,cadence,watts",
        points: int = 200,
        full: bool = False,
    ) -> dict:
        """Time series inside one activity, downsampled.

        types is a comma-separated list, for example heartrate, velocity_smooth,
        altitude, cadence, watts, temp, latlng. Returns `points` evenly spaced
        samples per series plus min/mean/max over the whole series. The raw data
        can exceed ten thousand samples per series, so pass full=true only when
        the shape of every second genuinely matters.
        """
        return tools.get_activity_streams(
            activity_id, types=types, points=points, full=full
        )

    @mcp.tool()
    @guard
    def get_wellness(oldest: str | None = None, newest: str | None = None) -> dict:
        """Daily wellness and training-load history.

        Defaults to the last 30 days. Per day: CTL (fitness), ATL (fatigue),
        ramp rate, plus whatever the athlete logs — weight, resting HR, HRV,
        sleep, soreness, fatigue, stress, mood, motivation. This is the record
        to read before judging whether load is sustainable.
        """
        return tools.get_wellness(oldest=oldest, newest=newest)

    @mcp.tool()
    @guard
    def get_events(oldest: str | None = None, newest: str | None = None) -> dict:
        """Planned calendar entries: future workouts, races and goals.

        Defaults to today through 28 days ahead. Pass an earlier oldest to see
        what was planned in the past. An empty list means nothing is scheduled.
        """
        return tools.get_events(oldest=oldest, newest=newest)

    @mcp.tool()
    @guard
    def get_best_efforts(
        kind: str,
        sport_type: str = "Run",
        oldest: str | None = None,
        newest: str | None = None,
    ) -> dict:
        """Best-effort curve for a sport: the athlete's peak sustained values.

        kind is hr, pace or power. Returns the best value held for 5s, 15s, 30s,
        1m, 5m, 10m, 20m, 30m, 1h and 1h30m over the window, which defaults to
        the last 12 months. Use it to compare current form against past peaks.
        """
        return tools.get_best_efforts(
            kind=kind, sport_type=sport_type, oldest=oldest, newest=newest
        )

    @mcp.tool()
    @guard
    def get_gear() -> dict:
        """Registered gear such as shoes and bikes, with accumulated distance.

        Useful for mileage on a given pair of shoes. An empty list means the
        athlete tracks no gear.
        """
        return tools.get_gear()

    @mcp.tool()
    @guard
    def list_workouts() -> dict:
        """The athlete's saved workout library and its folders.

        These are workout templates, not completed sessions; use list_activities
        for what was actually done.
        """
        return tools.list_workouts()

    @mcp.tool()
    @guard
    def intervals_get_raw(path: str, params: dict[str, Any] | None = None) -> Any:
        """Escape hatch: GET any intervals.icu v1 path and return it unshaped.

        Use only when a dedicated tool cannot answer the question, since raw
        payloads are large. path is relative to https://intervals.icu/api/v1,
        for example "athlete/{athlete}/activities"; "{athlete}" expands to the
        configured athlete id. Pass query arguments in params, not in the path.
        This is still read-only.
        """
        return tools.intervals_get_raw(path, params)

    return mcp


def build_servers(users: Sequence[UserConfig]) -> dict[str, MCPServer]:
    """One MCP server per user, keyed by that user's token.

    Each server is built already bound to one athlete's client, so a token can
    only ever reach that athlete's data. Nothing is resolved per request, which
    is what makes cross-user leakage a structural impossibility rather than a
    matter of getting request handling right.
    """
    servers: dict[str, MCPServer] = {}
    for user in users:
        client = IntervalsClient(Config(api_key=user.api_key, athlete_id=user.athlete_id))
        servers[user.token] = build_server(IntervalsTools(client))
    return servers


def build_app(
    users: Sequence[UserConfig],
    allowed_hosts: list[str] | None = None,
) -> Starlette:
    """Serve every user's MCP transports beneath their own secret path token.

    An unguessable URL is the access control, which is what ChatGPT's "no
    authentication" mode leaves us.
    """
    if not users:
        raise ValueError("Cannot build the app with no users configured.")

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(allowed_hosts),
        allowed_hosts=allowed_hosts or [],
        allowed_origins=[f"https://{h}" for h in (allowed_hosts or [])],
    )

    servers = build_servers(users)
    sub_apps: list[Starlette] = []
    routes: list[Route] = []

    for token, mcp in servers.items():
        # Both transports accept a full path, so their routes are merged into one
        # app. Mounting them as sibling sub-apps does not work: a Mount on ""
        # claims every path and the first one wins.
        sse = mcp.sse_app(
            sse_path=f"/{token}/sse",
            message_path=f"/{token}/messages/",
            transport_security=security,
        )
        http = mcp.streamable_http_app(
            streamable_http_path=f"/{token}/mcp", transport_security=security
        )
        sub_apps += [sse, http]
        routes += [*sse.routes, *http.routes]

    async def health(request):
        return JSONResponse({"status": "ok", "server": "intervals-icu-mcp"})

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        # Each streamable transport needs its session manager running, and child
        # lifespans are not started for us, so every sub-app is entered here.
        async with contextlib.AsyncExitStack() as stack:
            for sub in sub_apps:
                await stack.enter_async_context(sub.router.lifespan_context(sub))
            yield

    return Starlette(
        routes=[Route("/healthz", health, methods=["GET"]), *routes],
        lifespan=lifespan,
    )


def main() -> None:
    """Run over stdio, for a local client that launches this as a subprocess."""
    build_server().run(transport="stdio")


def main_http() -> None:
    """Run the HTTP server that ChatGPT connects to."""
    import uvicorn

    users = config.resolve_users()
    hosts = [h.strip() for h in (os.environ.get("INTERVALS_MCP_HOSTS") or "").split(",") if h.strip()]
    port = int(os.environ.get("PORT") or 8080)

    # Names only: a token in the log would defeat the point of the secret URL.
    print(f"serving {len(users)} athlete(s): {', '.join(u.name for u in users)}", flush=True)

    uvicorn.run(
        build_app(users=users, allowed_hosts=hosts or None),
        host="0.0.0.0",
        port=port,
        log_level="info",
        # The access log would record request paths, and every path contains a
        # user's secret token. Container logs are not the place for it.
        access_log=False,
    )
