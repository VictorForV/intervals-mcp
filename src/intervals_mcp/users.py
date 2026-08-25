"""Safe CRUD operations for the multi-athlete users file."""

from __future__ import annotations

import contextlib
import os
import pathlib
import tempfile
from dataclasses import replace

from . import config
from .server import generate_token


class UserError(Exception):
    """A requested user operation could not be completed."""


def _required(label: str, value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise UserError(f"{label} is required and cannot be blank.")
    return value


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _validate_unique(users: list[config.UserConfig]) -> None:
    names: set[str] = set()
    athletes: set[str] = set()
    tokens: set[str] = set()
    for user in users:
        if user.name in names:
            raise UserError(f"A user named {user.name!r} already exists.")
        if user.athlete_id in athletes:
            raise UserError(f"Athlete {user.athlete_id!r} already exists.")
        if user.token in tokens:
            raise UserError("Two users cannot share an access token.")
        names.add(user.name)
        athletes.add(user.athlete_id)
        tokens.add(user.token)


def save_users(path: pathlib.Path, users: list[config.UserConfig]) -> None:
    """Atomically replace ``path`` and keep its secrets owner-readable only."""
    path = pathlib.Path(path)
    if not users:
        raise UserError("Refusing to write an empty users file.")
    _validate_unique(users)
    path.parent.mkdir(parents=True, exist_ok=True)

    text = "# Athletes served by this deployment. Keep this file secret.\n"
    for user in users:
        text += (
            "\n[[users]]\n"
            f"name = {_quote(user.name)}\n"
            f"athlete_id = {_quote(user.athlete_id)}\n"
            f"api_key = {_quote(user.api_key)}\n"
            f"token = {_quote(user.token)}\n"
        )

    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


def add_user(path: pathlib.Path, name: str, athlete_id: str, api_key: str) -> config.UserConfig:
    name = _required("name", name)
    athlete_id = config.normalise_athlete_id(_required("athlete_id", athlete_id))
    api_key = _required("api_key", api_key)
    existing = config.load_users(path) if pathlib.Path(path).exists() else []
    user = config.UserConfig(
        name=name,
        athlete_id=athlete_id,
        api_key=api_key,
        token=generate_token(),
    )
    save_users(path, [*existing, user])
    return user


def find_user(path: pathlib.Path, name: str) -> config.UserConfig:
    for user in config.load_users(path):
        if user.name == name:
            return user
    raise UserError(f"No user named {name!r} exists in {path}.")


def update_user(
    path: pathlib.Path,
    current_name: str,
    *,
    name: str | None = None,
    athlete_id: str | None = None,
    api_key: str | None = None,
    rotate_token: bool = False,
) -> config.UserConfig:
    users = config.load_users(path)
    updated: config.UserConfig | None = None
    result: list[config.UserConfig] = []
    for user in users:
        if user.name != current_name:
            result.append(user)
            continue
        updated = replace(
            user,
            name=_required("name", name) if name is not None else user.name,
            athlete_id=(
                config.normalise_athlete_id(_required("athlete_id", athlete_id))
                if athlete_id is not None
                else user.athlete_id
            ),
            api_key=_required("api_key", api_key) if api_key is not None else user.api_key,
            token=generate_token() if rotate_token else user.token,
        )
        result.append(updated)
    if updated is None:
        raise UserError(f"No user named {current_name!r} exists in {path}.")
    save_users(path, result)
    return updated


def remove_user(path: pathlib.Path, name: str) -> config.UserConfig:
    users = config.load_users(path)
    removed = next((user for user in users if user.name == name), None)
    if removed is None:
        raise UserError(f"No user named {name!r} exists in {path}.")
    remaining = [user for user in users if user.name != name]
    if remaining:
        save_users(path, remaining)
    else:
        pathlib.Path(path).unlink()
    return removed


def endpoint_urls(host: str, token: str) -> dict[str, str]:
    host = host.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
    if not host:
        raise UserError("A public hostname is required to build connector URLs.")
    base = f"https://{host}/{token}"
    return {"http": f"{base}/mcp", "sse": f"{base}/sse"}
