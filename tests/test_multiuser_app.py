"""Tests for serving several athletes from one app.

The isolation test is the reason this design was chosen over resolving
credentials per request, so it is the one to keep honest.
"""

import asyncio

import httpx
import pytest
import respx
from starlette.testclient import TestClient

from intervals_mcp import server
from intervals_mcp.config import UserConfig

BASE = "https://intervals.icu/api/v1"

ALEX = UserConfig(name="alex", athlete_id="i111", api_key="key-alex", token="a" * 32)
BOB = UserConfig(name="bob", athlete_id="i222", api_key="key-bob", token="b" * 32)


def tool_text(result) -> str:
    return result.content[0].text if result.content else ""


def assert_succeeded(result) -> None:
    """Tool errors come back as an ``error`` key rather than a failed call, so
    checking the transport-level flag alone would miss them."""
    assert not result.is_error, f"call failed: {tool_text(result)}"
    assert '"error"' not in tool_text(result), f"tool reported: {tool_text(result)}"


@pytest.fixture
def client():
    app = server.build_app(users=[ALEX, BOB])
    with TestClient(app) as c:
        yield c


class TestRouting:
    def test_each_user_gets_their_own_route_set(self):
        paths = {r.path for r in server.build_app(users=[ALEX, BOB]).routes}

        for user in (ALEX, BOB):
            assert f"/{user.token}/sse" in paths
            assert f"/{user.token}/mcp" in paths
            assert f"/{user.token}/messages" in paths

    def test_health_is_still_reachable_without_a_token(self, client):
        assert client.get("/healthz").status_code == 200

    def test_health_reveals_neither_names_nor_user_count(self, client):
        body = client.get("/healthz").text

        assert "alex" not in body
        assert "bob" not in body
        assert "2" not in body

    def test_an_unknown_token_is_not_found(self, client):
        assert client.post("/" + "c" * 32 + "/mcp").status_code == 404

    def test_tokens_are_not_echoed_on_a_miss(self, client):
        response = client.post("/" + "c" * 32 + "/mcp")

        assert ALEX.token not in response.text
        assert BOB.token not in response.text


class TestIsolation:
    """Each token must reach exactly one athlete."""

    def test_a_token_only_ever_queries_its_own_athlete(self):
        # Build both users' servers, then call the same tool on each and observe
        # which upstream athlete path was requested. Routes are registered inside
        # the mock context: created outside, they leak into later tests and
        # answer their requests with an empty body.
        with respx.mock:
            alex_route = respx.get(f"{BASE}/athlete/{ALEX.athlete_id}/profile").mock(
                return_value=httpx.Response(200, json={"athlete": {"id": "i111"}})
            )
            bob_route = respx.get(f"{BASE}/athlete/{BOB.athlete_id}/profile").mock(
                return_value=httpx.Response(200, json={"athlete": {"id": "i222"}})
            )

            servers = server.build_servers([ALEX, BOB])

            alex_result = asyncio.run(servers[ALEX.token].call_tool("get_athlete_profile", {}))
            assert alex_route.call_count == 1
            assert bob_route.call_count == 0

            bob_result = asyncio.run(servers[BOB.token].call_tool("get_athlete_profile", {}))
            assert bob_route.call_count == 1
            assert alex_route.call_count == 1, "Bob's call must not touch Alex's athlete"

        assert "i111" in str(alex_result)
        assert "i222" in str(bob_result)

    def test_each_user_sends_their_own_api_key(self):
        import base64

        def credentials_of_last_call():
            header = respx.calls.last.request.headers["authorization"]
            return base64.b64decode(header.removeprefix("Basic ")).decode()

        with respx.mock:
            for user in (ALEX, BOB):
                respx.get(f"{BASE}/athlete/{user.athlete_id}/profile").mock(
                    return_value=httpx.Response(200, json={"athlete": {"id": user.athlete_id}})
                )
            servers = server.build_servers([ALEX, BOB])

            result = asyncio.run(servers[ALEX.token].call_tool("get_athlete_profile", {}))
            assert_succeeded(result)
            assert credentials_of_last_call() == "API_KEY:key-alex"

            result = asyncio.run(servers[BOB.token].call_tool("get_athlete_profile", {}))
            assert_succeeded(result)
            assert credentials_of_last_call() == "API_KEY:key-bob"

    def test_servers_are_distinct_objects_per_user(self):
        servers = server.build_servers([ALEX, BOB])

        assert servers[ALEX.token] is not servers[BOB.token]


class TestValidation:
    def test_refuses_to_build_an_app_with_no_users(self):
        with pytest.raises(ValueError) as excinfo:
            server.build_app(users=[])

        assert "no users" in str(excinfo.value).lower()
