"""Tests for MCP server assembly and the HTTP app that ChatGPT connects to.

The secret path token is the only thing standing between the public internet and
seven years of training data, so its behaviour is pinned down here.
"""

import asyncio

import httpx
import pytest
import respx
from starlette.testclient import TestClient

from intervals_mcp import server
from intervals_mcp.config import UserConfig

TOKEN = "0123456789abcdef0123456789abcdef"

EXPECTED_TOOLS = {
    "get_athlete_profile",
    "get_sport_settings",
    "list_activities",
    "get_activity",
    "get_activity_intervals",
    "get_activity_streams",
    "get_wellness",
    "get_training_readiness",
    "get_training_load_chart",
    "get_events",
    "get_best_efforts",
    "get_best_effort_chart",
    "get_gear",
    "list_workouts",
    "intervals_get_raw",
}


@pytest.fixture
def mcp_server(monkeypatch):
    monkeypatch.setenv("INTERVALS_API_KEY", "testkey")
    monkeypatch.setenv("INTERVALS_ATHLETE_ID", "i123")
    monkeypatch.setattr(server.config, "DEFAULT_ENV_FILE", None)
    return server.build_server()


def list_tools(mcp_server):
    return asyncio.run(mcp_server.list_tools())


class TestToolRegistration:
    def test_registers_every_planned_tool(self, mcp_server):
        names = {t.name for t in list_tools(mcp_server)}

        assert names == EXPECTED_TOOLS

    def test_every_tool_describes_itself(self, mcp_server):
        # ChatGPT chooses tools from these descriptions, so an empty one is a bug.
        for tool in list_tools(mcp_server):
            assert tool.description, f"{tool.name} has no description"
            assert len(tool.description) > 40, f"{tool.name} description is too thin"

    def test_date_arguments_are_optional_so_the_model_can_omit_them(self, mcp_server):
        activities = next(t for t in list_tools(mcp_server) if t.name == "list_activities")

        assert "oldest" in activities.input_schema["properties"]
        assert "oldest" not in activities.input_schema.get("required", [])

    def test_activity_id_is_required(self, mcp_server):
        activity = next(t for t in list_tools(mcp_server) if t.name == "get_activity")

        assert activity.input_schema["required"] == ["activity_id"]


class TestToolExecution:
    @respx.mock
    def test_the_chart_tool_returns_an_image_content_block(self, mcp_server):
        respx.get("https://intervals.icu/api/v1/athlete/i123/wellness").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"id": "2026-06-01", "ctl": 40, "atl": 30},
                    {"id": "2026-06-15", "ctl": 45, "atl": 42},
                ],
            )
        )

        result = asyncio.run(mcp_server.call_tool("get_training_load_chart", {}))

        assert len(result.content) == 1
        block = result.content[0]
        assert block.type == "image"
        assert block.mime_type == "image/png"
        assert block.data


ONE_USER = [
    UserConfig(name="solo", athlete_id="i123", api_key="testkey", token=TOKEN)
]


@pytest.fixture
def client():
    app = server.build_app(users=ONE_USER, allowed_hosts=["testserver"])
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    def test_health_needs_no_token(self, client):
        response = client.get("/healthz")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_health_does_not_leak_the_token(self, client):
        assert TOKEN not in client.get("/healthz").text


class TestSecretPath:
    def test_the_wrong_token_is_not_found(self, client):
        assert client.get("/wrongtoken/sse").status_code == 404

    def test_the_bare_transport_path_without_a_token_is_not_found(self, client):
        assert client.get("/sse").status_code == 404

    def test_the_root_reveals_nothing(self, client):
        response = client.get("/")

        assert response.status_code == 404
        assert TOKEN not in response.text

    def test_the_streamable_endpoint_exists_under_the_token(self, client):
        # Without MCP session headers the transport refuses the call, but a
        # reachable route must not answer 404.
        response = client.post(f"/{TOKEN}/mcp", json={"jsonrpc": "2.0", "method": "ping", "id": 1})

        assert response.status_code != 404

    def test_the_sse_endpoint_is_routed_under_the_token(self):
        # Requesting the stream would block until it closes, so the route table
        # is inspected instead.
        paths = {r.path for r in server.build_app(users=ONE_USER).routes}

        assert f"/{TOKEN}/sse" in paths
        assert f"/{TOKEN}/mcp" in paths
        assert f"/{TOKEN}/messages" in paths


class TestTokenGeneration:
    def test_generates_a_long_url_safe_token(self):
        token = server.generate_token()

        assert len(token) >= 32
        assert token.isalnum() or "-" in token or "_" in token

    def test_generates_a_different_token_each_time(self):
        assert server.generate_token() != server.generate_token()
