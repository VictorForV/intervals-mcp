"""Configuration for one athlete (.env) or several (users.toml)."""

import os
import pathlib
import tomllib
from dataclasses import dataclass, field

from dotenv import load_dotenv

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

# A token is the only thing guarding a user's data, since ChatGPT connectors
# cannot send an API key. Anything short enough to guess is a misconfiguration.
MIN_TOKEN_LENGTH = 20

USER_FIELDS = ("name", "athlete_id", "api_key", "token")


class ConfigError(Exception):
    """Configuration is missing or unusable, with instructions in the message."""


@dataclass
class Config:
    api_key: str = field(repr=False)
    athlete_id: str

    def __repr__(self) -> str:
        return f"Config(athlete_id={self.athlete_id!r}, api_key=<redacted>)"


DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"

_UNSET = object()


def load_config(env_file: pathlib.Path | None = _UNSET) -> Config:  # type: ignore[assignment]
    """Read configuration from ``env_file``, falling back to the process environment.

    ``env_file`` is resolved at call time rather than bound as a default, so tests
    can isolate themselves from the real .env — which would otherwise refill
    variables they deliberately unset. Pass ``None`` to skip file loading.
    """
    if env_file is _UNSET:
        env_file = DEFAULT_ENV_FILE
    if env_file is not None:
        load_dotenv(env_file)

    api_key = (os.environ.get("INTERVALS_API_KEY") or "").strip()
    athlete_id = (os.environ.get("INTERVALS_ATHLETE_ID") or "").strip()

    if not api_key:
        raise ConfigError(
            "INTERVALS_API_KEY is not set. Put it in .env at the project root "
            "(copy .env.example), or export it in the MCP server's environment. "
            "Generate a key at https://intervals.icu/settings under Developer Settings."
        )
    if not athlete_id:
        raise ConfigError(
            "INTERVALS_ATHLETE_ID is not set. Put it in .env at the project root "
            "(copy .env.example). It looks like i123456 and appears in your "
            "intervals.icu profile URL."
        )

    return Config(api_key=api_key, athlete_id=normalise_athlete_id(athlete_id))


def normalise_athlete_id(athlete_id: str) -> str:
    """API paths use the i-prefixed form; accept a bare number too."""
    return athlete_id if athlete_id.startswith("i") else f"i{athlete_id}"


DEFAULT_USERS_FILE = PROJECT_ROOT / "users.toml"


@dataclass
class UserConfig:
    """One athlete reachable under their own secret token."""

    name: str
    athlete_id: str
    api_key: str = field(repr=False)
    token: str = field(repr=False)

    def __repr__(self) -> str:
        return f"UserConfig(name={self.name!r}, athlete_id={self.athlete_id!r}, api_key=<redacted>)"


def load_users(path: pathlib.Path = DEFAULT_USERS_FILE) -> list[UserConfig]:
    """Read and validate users.toml.

    Every problem raises instead of being skipped: serving a partial
    configuration would silently leave someone without access, or worse, mount
    two people on one route.
    """
    path = pathlib.Path(path)
    if not path.exists():
        raise ConfigError(
            f"No users file at {path}. Create it (see users.toml.example), or "
            "configure a single athlete through .env instead."
        )

    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Could not parse users.toml at {path}: {exc}") from exc

    entries = data.get("users") or []
    if not entries:
        raise ConfigError(
            f"Found no users in {path}. Each athlete needs a [[users]] block "
            "with name, athlete_id, api_key and token."
        )

    users: list[UserConfig] = []
    seen_tokens: set[str] = set()
    seen_names: set[str] = set()

    for index, entry in enumerate(entries, start=1):
        label = entry.get("name") or f"entry {index}"

        for key in USER_FIELDS:
            value = entry.get(key)
            if value is None:
                raise ConfigError(f"User {label!r} in {path} is missing {key!r}.")
            if not str(value).strip():
                raise ConfigError(f"User {label!r} in {path} has a blank {key!r}.")

        name = str(entry["name"]).strip()
        token = str(entry["token"]).strip()

        if len(token) < MIN_TOKEN_LENGTH:
            # The token itself is never echoed, only the user it belongs to.
            raise ConfigError(
                f"The token for user {name!r} is too short to be secret: it must be "
                f"at least {MIN_TOKEN_LENGTH} characters. Generate one with "
                "intervals-mcp-adduser."
            )
        if token in seen_tokens:
            raise ConfigError(
                f"Two users share a token (second one is {name!r}). Tokens must be "
                "unique, since each one is a separate URL."
            )
        if name in seen_names:
            raise ConfigError(f"Two users share the name {name!r} in {path}.")

        seen_tokens.add(token)
        seen_names.add(name)
        users.append(
            UserConfig(
                name=name,
                athlete_id=normalise_athlete_id(str(entry["athlete_id"]).strip()),
                api_key=str(entry["api_key"]).strip(),
                token=token,
            )
        )

    return users


def resolve_users(
    users_file: pathlib.Path = DEFAULT_USERS_FILE,
    env_file: pathlib.Path | None = _UNSET,  # type: ignore[assignment]
) -> list[UserConfig]:
    """Load users from users.toml, falling back to the single athlete in .env.

    The fallback keeps an existing single-athlete deployment working unchanged
    until a users file is created.
    """
    users_file = pathlib.Path(users_file)
    if users_file.exists():
        return load_users(users_file)

    if env_file is _UNSET:
        env_file = DEFAULT_ENV_FILE
    if env_file is not None:
        load_dotenv(env_file)

    token = (os.environ.get("INTERVALS_MCP_TOKEN") or "").strip()
    if not token or not (os.environ.get("INTERVALS_API_KEY") or "").strip():
        raise ConfigError(
            f"No users configured. Either create {users_file} with a [[users]] "
            "block per athlete, or set INTERVALS_API_KEY, INTERVALS_ATHLETE_ID "
            "and INTERVALS_MCP_TOKEN in .env for a single athlete."
        )

    single = load_config(env_file=env_file)
    return [
        UserConfig(
            name=single.athlete_id,
            athlete_id=single.athlete_id,
            api_key=single.api_key,
            token=token,
        )
    ]
