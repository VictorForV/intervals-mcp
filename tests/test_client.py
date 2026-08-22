"""Tests for the HTTP layer, against a mocked transport.

The live API is exercised separately by scripts/smoke.py; these tests pin down
auth shape, retry behaviour, and the error text an agent will read.
"""

import base64

import httpx
import pytest
import respx

from intervals_mcp.client import IntervalsClient, IntervalsError
from intervals_mcp.config import Config

BASE = "https://intervals.icu/api/v1"


@pytest.fixture
def client():
    # backoff_base=0 keeps retry tests instant.
    return IntervalsClient(Config(api_key="testkey", athlete_id="i123"), backoff_base=0)


class TestAuth:
    @respx.mock
    def test_sends_the_key_as_the_password_under_the_literal_api_key_username(self, client):
        route = respx.get(f"{BASE}/athlete/i123/profile").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        client.get("athlete/i123/profile")

        header = route.calls.last.request.headers["authorization"]
        assert header.startswith("Basic ")
        decoded = base64.b64decode(header.removeprefix("Basic ")).decode()
        assert decoded == "API_KEY:testkey"


class TestSuccess:
    @respx.mock
    def test_returns_the_parsed_body(self, client):
        respx.get(f"{BASE}/athlete/i123/profile").mock(
            return_value=httpx.Response(200, json={"athlete": {"id": "i123"}})
        )

        assert client.get("athlete/i123/profile") == {"athlete": {"id": "i123"}}

    @respx.mock
    def test_passes_query_parameters_through(self, client):
        route = respx.get(f"{BASE}/athlete/i123/activities").mock(
            return_value=httpx.Response(200, json=[])
        )

        client.get("athlete/i123/activities", {"oldest": "2026-01-01", "limit": 5})

        assert route.calls.last.request.url.params["oldest"] == "2026-01-01"
        assert route.calls.last.request.url.params["limit"] == "5"

    @respx.mock
    def test_drops_parameters_that_are_none(self, client):
        route = respx.get(f"{BASE}/athlete/i123/activities").mock(
            return_value=httpx.Response(200, json=[])
        )

        client.get("athlete/i123/activities", {"oldest": "2026-01-01", "type": None})

        assert "type" not in route.calls.last.request.url.params

    @respx.mock
    def test_accepts_a_path_written_with_a_leading_slash(self, client):
        respx.get(f"{BASE}/athlete/i123/profile").mock(return_value=httpx.Response(200, json={}))

        assert client.get("/athlete/i123/profile") == {}


class TestErrorMapping:
    @respx.mock
    def test_401_explains_the_username_convention(self, client):
        respx.get(f"{BASE}/athlete/i123/profile").mock(
            return_value=httpx.Response(401, json={"error": "Auth failed"})
        )

        with pytest.raises(IntervalsError) as excinfo:
            client.get("athlete/i123/profile")

        message = str(excinfo.value)
        assert "API_KEY" in message
        assert "INTERVALS_API_KEY" in message

    @respx.mock
    def test_403_says_the_athlete_is_not_accessible(self, client):
        respx.get(f"{BASE}/athlete/i999/profile").mock(return_value=httpx.Response(403))

        with pytest.raises(IntervalsError) as excinfo:
            client.get("athlete/i999/profile")

        assert "access" in str(excinfo.value).lower()

    @respx.mock
    def test_404_names_the_path_that_was_not_found(self, client):
        respx.get(f"{BASE}/activity/nope").mock(return_value=httpx.Response(404))

        with pytest.raises(IntervalsError) as excinfo:
            client.get("activity/nope")

        assert "activity/nope" in str(excinfo.value)

    @respx.mock
    def test_422_surfaces_which_parameter_the_api_wants(self, client):
        respx.get(f"{BASE}/athlete/i123/activities").mock(
            return_value=httpx.Response(
                422,
                json={
                    "error": "Required request parameter 'oldest' "
                    "for method parameter type String is not present"
                },
            )
        )

        with pytest.raises(IntervalsError) as excinfo:
            client.get("athlete/i123/activities")

        assert "oldest" in str(excinfo.value)

    @respx.mock
    def test_429_is_reported_as_rate_limiting(self, client):
        respx.get(f"{BASE}/athlete/i123/profile").mock(return_value=httpx.Response(429))

        with pytest.raises(IntervalsError) as excinfo:
            client.get("athlete/i123/profile")

        assert "rate" in str(excinfo.value).lower()

    @respx.mock
    def test_does_not_leak_the_api_key_into_error_text(self, client):
        respx.get(f"{BASE}/athlete/i123/profile").mock(return_value=httpx.Response(401))

        with pytest.raises(IntervalsError) as excinfo:
            client.get("athlete/i123/profile")

        assert "testkey" not in str(excinfo.value)


class TestRetry:
    @respx.mock
    def test_retries_a_server_error_and_succeeds(self, client):
        route = respx.get(f"{BASE}/athlete/i123/profile").mock(
            side_effect=[
                httpx.Response(500),
                httpx.Response(502),
                httpx.Response(200, json={"ok": True}),
            ]
        )

        assert client.get("athlete/i123/profile") == {"ok": True}
        assert route.call_count == 3

    @respx.mock
    def test_gives_up_after_three_attempts(self, client):
        route = respx.get(f"{BASE}/athlete/i123/profile").mock(
            return_value=httpx.Response(503)
        )

        with pytest.raises(IntervalsError) as excinfo:
            client.get("athlete/i123/profile")

        assert route.call_count == 3
        assert "3 attempts" in str(excinfo.value)

    @respx.mock
    def test_retries_a_network_failure(self, client):
        route = respx.get(f"{BASE}/athlete/i123/profile").mock(
            side_effect=[
                httpx.ConnectError("connection refused"),
                httpx.Response(200, json={"ok": True}),
            ]
        )

        assert client.get("athlete/i123/profile") == {"ok": True}
        assert route.call_count == 2

    @respx.mock
    def test_retries_a_timeout(self, client):
        route = respx.get(f"{BASE}/athlete/i123/profile").mock(
            side_effect=[
                httpx.ReadTimeout("too slow"),
                httpx.Response(200, json={"ok": True}),
            ]
        )

        assert client.get("athlete/i123/profile") == {"ok": True}
        assert route.call_count == 2

    @respx.mock
    def test_does_not_retry_a_client_error(self, client):
        route = respx.get(f"{BASE}/activity/nope").mock(return_value=httpx.Response(404))

        with pytest.raises(IntervalsError):
            client.get("activity/nope")

        assert route.call_count == 1


class TestAthleteHelpers:
    @respx.mock
    def test_expands_the_configured_athlete_into_a_path(self, client):
        respx.get(f"{BASE}/athlete/i123/wellness").mock(return_value=httpx.Response(200, json=[]))

        assert client.athlete_get("wellness") == []

    @respx.mock
    def test_rejects_a_non_get_verb_in_a_raw_path(self, client):
        with pytest.raises(IntervalsError) as excinfo:
            client.get("athlete/i123/profile?x=1#frag")

        assert "path" in str(excinfo.value).lower()


class TestRawPathCannotEscapeTheApi:
    """intervals_get_raw hands the model a free-text path; it must never be able
    to redirect the request (and this client's Basic Auth credentials) off
    intervals.icu."""

    def test_rejects_an_absolute_url(self, client):
        with pytest.raises(IntervalsError) as excinfo:
            client.get("https://attacker.example/collect")

        assert "absolute" in str(excinfo.value).lower()

    def test_never_leaks_the_api_key_to_another_host(self, client):
        captured = {}

        def handler(request):
            captured["host"] = request.url.host
            captured["authorization"] = request.headers.get("authorization")
            return httpx.Response(200, json={})

        client._client._transport = httpx.MockTransport(handler)

        with pytest.raises(IntervalsError):
            client.get("https://attacker.example/collect")

        assert captured == {}
