"""Add an athlete to users.toml and print the URL to paste into a connector.

    uv run intervals-mcp-adduser --name bob --athlete-id i222 --api-key <key>

Editing users.toml by hand works too; this exists so a typo cannot produce a
duplicate or guessable token.
"""

import argparse
import os
import pathlib
import sys

from . import config, users


AddUserError = users.UserError


def add_user(path: pathlib.Path, name: str, athlete_id: str, api_key: str) -> str:
    """Append one athlete to ``path`` and return the token generated for them."""
    return users.add_user(path, name, athlete_id, api_key).token


def connector_url(host: str, token: str) -> str:
    """The SSE URL to paste into ChatGPT's connector dialog."""
    return users.endpoint_urls(host, token)["sse"]


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="intervals-mcp-adduser",
        description="Add an athlete to users.toml and print their connector URL.",
    )
    parser.add_argument("--name", required=True, help="short label, e.g. bob")
    parser.add_argument("--athlete-id", required=True, help="e.g. i123456")
    parser.add_argument("--api-key", required=True, help="that athlete's intervals.icu API key")
    parser.add_argument(
        "--users-file",
        type=pathlib.Path,
        default=config.DEFAULT_USERS_FILE,
        help="defaults to users.toml at the project root",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MCP_DOMAIN", ""),
        help="public hostname; defaults to MCP_DOMAIN from the environment",
    )
    args = parser.parse_args()

    try:
        token = add_user(
            args.users_file,
            name=args.name,
            athlete_id=args.athlete_id,
            api_key=args.api_key,
        )
    except (AddUserError, config.ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"added {args.name} ({config.normalise_athlete_id(args.athlete_id)}) to {args.users_file}")
    if args.host:
        print("\nConnector URL (treat it as a password):")
        print(f"  {connector_url(args.host, token)}")
    else:
        print(f"\ntoken: {token}")
        print("Pass --host, or set MCP_DOMAIN, to get the full URL.")
    # `up -d` is a no-op here: users.toml is a bind mount, so compose sees no
    # change to the service and leaves the old user list loaded in memory.
    print("\nServe them with: docker compose restart mcp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
