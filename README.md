# Intervals MCP

[Русская версия](README.ru.md)

A self-hosted, read-only MCP server that gives AI assistants access to an
athlete's [Intervals.icu](https://intervals.icu/) training data.

Connect a sports watch, bike computer, trainer, Strava, or another supported
source to Intervals.icu. Intervals MCP then exposes the normalized training data
to ChatGPT, Claude, Claude Code, Cursor, VS Code, and other MCP clients. See
[Intervals.icu](https://intervals.icu/) for its current integrations; the list
changes over time.

The server only makes `GET` requests. It cannot create, edit, or delete anything
in an athlete's Intervals.icu account.

## What an assistant can read

- Athlete profile, timezone, sport settings, zones, FTP, LTHR, and max HR.
- Activities, details, laps, intervals, and downsampled streams.
- Wellness, fitness, fatigue, HRV, sleep, mood, and weight when available.
- A coach-style training readiness assessment: form (TSB) classified into a
  band, a ramp-rate read, and whether recent HRV has dropped below baseline.
- Planned events, best-effort curves, gear, and the workout library.
- Additional Intervals.icu v1 `GET` endpoints through a read-only raw tool.

Large responses are compacted before they reach the model. Empty fields are
dropped, streams are downsampled, and summaries use the full data series.

## Quick start

You need an Ubuntu or Debian VPS with a public hostname. Point the hostname's DNS
record at the server and allow inbound TCP ports 80 and 443. The installer adds
Docker, Compose, Git, and uv when they are missing:

```bash
curl -fsSL https://raw.githubusercontent.com/VictorForV/intervals-mcp/master/install.sh | sudo bash
```

Review [`install.sh`](install.sh) before running it if you prefer not to pipe a
remote script to a privileged shell. Manual installation remains available by
cloning the repository and running `./manage.sh` after installing the
prerequisites.

Choose **Initial setup**. The manager asks for the public hostname, a short
athlete name, and the Intervals.icu athlete ID and API key. The ID and key are
available under **Settings → Developer Settings** in Intervals.icu. The API key
uses hidden input.

The manager creates owner-only configuration, generates a strong random URL
token, starts the service, and prints the connector URLs. Run `./manage.sh` later
to add, list, edit, or remove athletes, rotate URLs, rebuild, restart, or inspect
the service.

## Connecting an AI client

Each athlete receives two secret URLs:

```text
https://mcp.example.com/<secret>/mcp  # Streamable HTTP, preferred
https://mcp.example.com/<secret>/sse  # legacy SSE compatibility
```

Treat the complete URL like a password. It grants read access to that athlete's
training and wellness data.

### Claude and Claude Desktop

Open **Settings → Connectors → Add custom connector** and enter the `/mcp` URL.
Availability and organization permissions depend on the Claude plan. See the
current [Anthropic instructions](https://support.anthropic.com/en/articles/11175166-about-custom-integrations-using-remote-mcp).

### Claude Code

The manager prints a ready-to-run command:

```bash
claude mcp add --transport http intervals-alex https://mcp.example.com/<secret>/mcp
```

### ChatGPT

Add the server as a custom app/connector and use the URL accepted by your current
ChatGPT workspace. Availability, UI, and administrator requirements vary by plan
and can change. See the current
[OpenAI apps documentation](https://help.openai.com/en/articles/11487775-connectors-in-chatgpt).
The manager shows both URL formats for compatibility.

### Other clients

Use `/mcp` with remote Streamable HTTP clients and `/sse` with older SSE clients.
Follow the client's current documentation and never commit a secret URL to a
shared configuration.

## Administration

The interactive panel is the recommended interface:

```bash
./manage.sh
```

For automation, the same interface has subcommands:

```bash
uv run intervals-mcp-admin add
uv run intervals-mcp-admin list
uv run intervals-mcp-admin show alex
uv run intervals-mcp-admin edit alex
uv run intervals-mcp-admin rotate alex
uv run intervals-mcp-admin remove alex
```

Avoid `--api-key` in an interactive shell because command arguments can be saved
in shell history or exposed in the process list. Omit it for hidden input.

## Local stdio mode

For one athlete and a client that launches local processes, copy `.env.example`
to `.env`, configure the Intervals.icu credentials, and run:

```bash
uv run intervals-mcp
```

## Security model

- Intervals.icu requests are read-only (`GET`).
- Each athlete gets a separate API client and independent random path token.
- `.env` and `users.toml` are gitignored and written with mode `0600`.
- API keys and path tokens are excluded from application and proxy access logs.
- The public service uses HTTPS through Caddy.
- `users.toml` is mounted read-only into the container.

The path token is bearer authentication: anyone with the URL can read that
athlete's data. Rotate it from `./manage.sh` if exposed. See
[SECURITY.md](SECURITY.md) for reporting issues.

## Development

```bash
uv sync
uv run pytest
```

Tests use fully synthetic, API-shaped fixtures and make no network requests.
Regenerate them with `uv run python scripts/generate_fixtures.py`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## License

MIT — see [LICENSE](LICENSE).
