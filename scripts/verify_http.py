"""Drive the running HTTP server with a real MCP client.

    uv run python scripts/verify_http.py [base_url]

Defaults to http://127.0.0.1:8080. Completes the MCP handshake, lists the tools,
and calls several of them against the live account, which is what a connector
such as ChatGPT does.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def run(base_url: str, token: str) -> int:
    endpoint = f"{base_url.rstrip('/')}/{token}/mcp"
    print(f"connecting to {base_url.rstrip('/')}/<token>/mcp\n")

    async with streamable_http_client(endpoint) as (read, write), ClientSession(read, write) as session:
        init = await session.initialize()
        print(f"server:   {init.server_info.name} v{init.server_info.version}")
        print(f"protocol: {init.protocol_version}")

        tools = (await session.list_tools()).tools
        print(f"tools:    {len(tools)}")
        for tool in tools:
            print(f"            - {tool.name}")

        print("\ncalling tools against live data:")
        calls = [
            ("get_athlete_profile", {}),
            ("get_sport_settings", {}),
            ("list_activities", {"oldest": "-14d", "limit": 3}),
            ("get_wellness", {"oldest": "-5d"}),
            ("get_best_efforts", {"kind": "pace", "sport_type": "Run"}),
            ("get_events", {}),
        ]
        failures = []
        for name, args in calls:
            result = await session.call_tool(name, args)
            text = result.content[0].text if result.content else ""
            if result.is_error:
                failures.append((name, text[:120]))
                print(f"  {name:22s} ERROR {text[:80]}")
            else:
                print(f"  {name:22s} ok, {len(text):,} chars  {text[:70]}...")

        if failures:
            print(f"\n{len(failures)} call(s) failed")
            return 1
        print(f"\nall {len(calls)} calls succeeded over HTTP")
        return 0


def main() -> int:
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    token = os.environ.get("INTERVALS_MCP_TOKEN")
    if not token:
        print("INTERVALS_MCP_TOKEN is not set")
        return 1
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
    return asyncio.run(run(base, token))


if __name__ == "__main__":
    sys.exit(main())
