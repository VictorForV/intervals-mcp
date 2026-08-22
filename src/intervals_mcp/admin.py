"""Interactive administration panel and scriptable user commands."""

from __future__ import annotations

import argparse
import getpass
import os
import pathlib
import subprocess
import sys
import shutil

from dotenv import dotenv_values, load_dotenv

from . import config, users


def _prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def _secret(label: str, allow_blank: bool = False) -> str:
    while True:
        value = getpass.getpass(f"{label}: ").strip()
        if value or allow_blank:
            return value
        print(f"{label} cannot be blank.")


def _host(value: str | None) -> str:
    file_value = dotenv_values(config.DEFAULT_ENV_FILE).get("MCP_DOMAIN")
    return (value or os.environ.get("MCP_DOMAIN") or file_value or "").strip()


def _print_links(user: config.UserConfig, host: str) -> None:
    links = users.endpoint_urls(host, user.token)
    print(f"\nConnector URLs for {user.name} (treat both as passwords):")
    print(f"  Streamable HTTP (recommended): {links['http']}")
    print(f"  Legacy SSE (compatibility):    {links['sse']}")
    print("\nClaude Code:")
    print(f"  claude mcp add --transport http intervals-{user.name} {links['http']}")


def _restart_hint() -> None:
    print("\nApply the change with: docker compose restart mcp")


def _load(path: pathlib.Path) -> list[config.UserConfig]:
    return config.load_users(path) if path.exists() else []


def add(path: pathlib.Path, host: str, *, name: str = "", athlete_id: str = "", api_key: str = "") -> None:
    name = name or _prompt("Athlete name (a short local label)")
    athlete_id = athlete_id or _prompt("Intervals.icu athlete ID (for example i123456)")
    api_key = api_key or _secret("Intervals.icu API key (input hidden)")
    user = users.add_user(path, name, athlete_id, api_key)
    print(f"\nAdded {user.name} ({user.athlete_id}).")
    if host:
        _print_links(user, host)
    else:
        print("Set MCP_DOMAIN in .env to generate complete connector URLs.")
    _restart_hint()


def list_users(path: pathlib.Path) -> None:
    entries = _load(path)
    if not entries:
        print("No athletes are configured.")
        return
    print("\nConfigured athletes (secrets are hidden):")
    for index, user in enumerate(entries, 1):
        print(f"  {index}. {user.name} ({user.athlete_id})")


def show(path: pathlib.Path, host: str, name: str = "") -> None:
    name = name or _choose_user(path).name
    _print_links(users.find_user(path, name), host)


def _choose_user(path: pathlib.Path) -> config.UserConfig:
    entries = _load(path)
    if not entries:
        raise users.UserError("No athletes are configured yet.")
    list_users(path)
    choice = _prompt("Select athlete number")
    try:
        return entries[int(choice) - 1]
    except (ValueError, IndexError) as exc:
        raise users.UserError("Invalid athlete selection.") from exc


def edit(path: pathlib.Path, current_name: str = "") -> None:
    current = users.find_user(path, current_name) if current_name else _choose_user(path)
    print("Leave a value blank to keep it unchanged.")
    name = _prompt("Name", current.name)
    athlete_id = _prompt("Athlete ID", current.athlete_id)
    api_key = _secret("New API key (blank keeps the current key)", allow_blank=True)
    updated = users.update_user(
        path,
        current.name,
        name=name,
        athlete_id=athlete_id,
        api_key=api_key or None,
    )
    print(f"Updated {updated.name} ({updated.athlete_id}).")
    _restart_hint()


def rotate(path: pathlib.Path, host: str, name: str = "") -> None:
    current = users.find_user(path, name) if name else _choose_user(path)
    updated = users.update_user(path, current.name, rotate_token=True)
    print(f"Rotated the access token for {updated.name}. Old URLs no longer work after restart.")
    if host:
        _print_links(updated, host)
    _restart_hint()


def remove(path: pathlib.Path, name: str = "", yes: bool = False) -> None:
    current = users.find_user(path, name) if name else _choose_user(path)
    if not yes and _prompt(f"Type {current.name!r} to confirm removal") != current.name:
        print("Removal cancelled.")
        return
    users.remove_user(path, current.name)
    print(f"Removed {current.name}. Their connector URLs no longer work after restart.")
    _restart_hint()


def _compose(*args: str) -> None:
    if shutil.which("docker") is None:
        raise users.UserError(
            "Docker is required for remote deployment. Install Docker Engine "
            "with the Compose plugin from https://docs.docker.com/engine/install/."
        )
    check = subprocess.run(
        ["docker", "compose", "version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if check.returncode:
        raise users.UserError(
            "Docker Compose is unavailable. Install the Compose plugin from "
            "https://docs.docker.com/compose/install/linux/."
        )
    subprocess.run(["docker", "compose", *args], check=True)


def initial_setup(path: pathlib.Path, host: str = "") -> None:
    if path.exists():
        raise users.UserError(
            f"{path} already exists. Use Add athlete, or remove the existing configuration first."
        )
    host = host or _prompt("Public hostname (for example mcp.example.com)")
    host = host.removeprefix("https://").removeprefix("http://").rstrip("/")
    if not host or "/" in host:
        raise users.UserError("Enter a hostname without a path, for example mcp.example.com.")
    env_path = config.DEFAULT_ENV_FILE
    if not env_path.exists():
        env_path.write_text(f"MCP_DOMAIN={host}\nMCP_ALLOWED_HOSTS={host}\n")
        env_path.chmod(0o600)
        print(f"Created {env_path} with owner-only permissions.")
    add(path, host)
    if _prompt("Build and start the service now? (Y/n)", "Y").lower() in {"y", "yes"}:
        _compose("up", "-d", "--build")


def menu(path: pathlib.Path, host: str) -> int:
    actions = {
        "1": ("Initial setup", lambda: initial_setup(path, host)),
        "2": ("Add athlete", lambda: add(path, _host(host))),
        "3": ("List athletes", lambda: list_users(path)),
        "4": ("Show connector URLs", lambda: show(path, _host(host))),
        "5": ("Edit athlete", lambda: edit(path)),
        "6": ("Rotate secret connector URLs", lambda: rotate(path, _host(host))),
        "7": ("Remove athlete", lambda: remove(path)),
        "8": ("Start / rebuild service", lambda: _compose("up", "-d", "--build")),
        "9": ("Restart service", lambda: _compose("restart", "mcp")),
        "10": ("Service status", lambda: _compose("ps")),
        "11": ("Recent logs", lambda: _compose("logs", "--tail", "100", "mcp")),
    }
    while True:
        print("\nIntervals MCP Manager\n")
        for key, (label, _) in actions.items():
            print(f" {key:>2}. {label}")
        print("  0. Exit")
        choice = _prompt("Choose an option")
        if choice == "0":
            return 0
        action = actions.get(choice)
        if not action:
            print("Invalid option.")
            continue
        try:
            action[1]()
        except (users.UserError, config.ConfigError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
        except subprocess.CalledProcessError:
            # docker compose already printed its own diagnostic to stderr;
            # repeating its argv and exit code here would only add noise.
            print("Error: docker compose failed (see the message above).", file=sys.stderr)


def main() -> int:
    load_dotenv(config.DEFAULT_ENV_FILE)
    parser = argparse.ArgumentParser(description="Manage Intervals MCP athletes and deployment.")
    parser.add_argument("--users-file", type=pathlib.Path, default=config.DEFAULT_USERS_FILE)
    parser.add_argument("--host", help="public hostname; defaults to MCP_DOMAIN")
    sub = parser.add_subparsers(dest="command")
    add_parser = sub.add_parser("add", help="add an athlete (prompts for omitted values)")
    add_parser.add_argument("--name")
    add_parser.add_argument("--athlete-id")
    add_parser.add_argument("--api-key", help="prefer the hidden interactive prompt")
    sub.add_parser("list", help="list athletes without secrets")
    show_parser = sub.add_parser("show", help="show connector URLs for an athlete")
    show_parser.add_argument("name", nargs="?")
    edit_parser = sub.add_parser("edit", help="interactively edit an athlete")
    edit_parser.add_argument("name", nargs="?")
    rotate_parser = sub.add_parser("rotate", help="replace an athlete's secret URL token")
    rotate_parser.add_argument("name", nargs="?")
    remove_parser = sub.add_parser("remove", help="remove an athlete")
    remove_parser.add_argument("name", nargs="?")
    remove_parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    host = _host(args.host)
    try:
        if args.command is None:
            return menu(args.users_file, host)
        if args.command == "add":
            add(args.users_file, host, name=args.name or "", athlete_id=args.athlete_id or "", api_key=args.api_key or "")
        elif args.command == "list":
            list_users(args.users_file)
        elif args.command == "show":
            show(args.users_file, host, args.name or "")
        elif args.command == "edit":
            edit(args.users_file, args.name or "")
        elif args.command == "rotate":
            rotate(args.users_file, host, args.name or "")
        elif args.command == "remove":
            remove(args.users_file, args.name or "", args.yes)
    except (users.UserError, config.ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
