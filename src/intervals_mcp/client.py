"""HTTP transport for the intervals.icu v1 API.

Authentication is HTTP Basic with the literal string ``API_KEY`` as the username
and the athlete's key as the password. Passing the key as the username, which
looks natural, fails with 401 — hence the explicit message on that path.
"""

import time
from typing import Any

import httpx

from .config import Config

BASE_URL = "https://intervals.icu/api/v1"
ATTEMPTS = 3
TIMEOUT = 30.0


class IntervalsError(Exception):
    """A request failed. The message is written to be read by an agent."""


def _api_message(response: httpx.Response) -> str:
    """Pull the API's own error text out of the body, if it sent any."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200].strip()
    if isinstance(body, dict):
        return str(body.get("error") or body.get("message") or "").strip()
    return ""


class IntervalsClient:
    def __init__(
        self,
        config: Config,
        timeout: float = TIMEOUT,
        attempts: int = ATTEMPTS,
        backoff_base: float = 0.5,
    ) -> None:
        self._config = config
        self._attempts = attempts
        self._backoff_base = backoff_base
        self._client = httpx.Client(
            base_url=BASE_URL,
            auth=("API_KEY", config.api_key),
            timeout=timeout,
            headers={"Accept": "application/json"},
        )

    @property
    def athlete_id(self) -> str:
        return self._config.athlete_id

    def athlete_get(self, suffix: str, params: dict[str, Any] | None = None) -> Any:
        """GET a path under the configured athlete, e.g. ``wellness``."""
        return self.get(f"athlete/{self.athlete_id}/{suffix.lstrip('/')}", params)

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        path = path.lstrip("/")
        if "?" in path or "#" in path:
            raise IntervalsError(
                f"Invalid path {path!r}: pass query arguments in params, not in the path."
            )

        clean = {k: v for k, v in (params or {}).items() if v is not None}
        last_reason = ""

        for attempt in range(1, self._attempts + 1):
            try:
                response = self._client.get(path, params=clean)
            except httpx.HTTPError as exc:
                last_reason = f"{type(exc).__name__}: {exc}"
            else:
                if response.status_code < 400:
                    return response.json()
                if response.status_code < 500:
                    raise self._client_error(response, path)
                last_reason = f"HTTP {response.status_code}"

            if attempt < self._attempts:
                time.sleep(self._backoff_base * 2 ** (attempt - 1))

        raise IntervalsError(
            f"intervals.icu did not answer for {path!r} after "
            f"{self._attempts} attempts ({last_reason})."
        )

    def _client_error(self, response: httpx.Response, path: str) -> IntervalsError:
        detail = _api_message(response)
        code = response.status_code

        if code == 401:
            return IntervalsError(
                "intervals.icu rejected the credentials (401). Check INTERVALS_API_KEY. "
                "Note the key is sent as the HTTP Basic password with the literal "
                "username 'API_KEY'; using the key as the username fails this way."
            )
        if code == 403:
            return IntervalsError(
                f"No access to {path!r} (403). The key belongs to a different athlete, "
                "or this data is not shared with you."
            )
        if code == 404:
            return IntervalsError(
                f"Not found: {path!r} (404). Check the id, or the endpoint does not exist."
            )
        if code == 422:
            return IntervalsError(
                f"intervals.icu rejected the parameters for {path!r} (422): "
                f"{detail or 'a required parameter is missing'}."
            )
        if code == 429:
            return IntervalsError(
                "Hit the intervals.icu rate limit (429). Wait a moment and ask for a "
                "narrower date range."
            )
        return IntervalsError(f"Request to {path!r} failed with HTTP {code}. {detail}".strip())

    def close(self) -> None:
        self._client.close()
