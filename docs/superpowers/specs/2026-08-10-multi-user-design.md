# Multi-user support — design

Date: 2026-08-10

## Purpose

Serve several athletes from one deployment. Each person gets their own URL for
their own ChatGPT, and sees only their own training data.

## Constraints

- intervals.icu keys are per-athlete. This account is not a coach account
  (`icu_coach: false`, no shared folders), so there is no way to read another
  athlete with one key. Every person supplies their own key.
- A handful of users, added by the operator. No self-registration.
- The existing single-athlete deployment must keep working, including its
  current connector URL.
- ChatGPT connectors cannot send an API key, so the per-user secret stays in the
  URL path.

## Approach

One MCP server instance per user, mounted under that user's secret token.

Isolation is structural rather than procedural: the route `/{token}/mcp` is built
already bound to one athlete's HTTP client, so serving the wrong person's data
would require mounting the wrong route, not merely mishandling a request.

Rejected: a single server resolving credentials per request from the path token.
It allows adding users without a restart, but tools would have to reach into the
current request's context, and MCP sessions over SSE are long-lived. A mistake
there hands one person another person's data — the one failure this design must
exclude.

Rejected: one container per user. Stronger isolation, but each user then needs a
port, a compose service and a Caddy route. Disproportionate for a handful.

## Storage

`users.toml` at the project root, mode 600, gitignored, alongside `.env`:

```toml
[[users]]
name = "alex"
athlete_id = "i123456"
api_key = "..."
token = "..."
```

TOML because it is readable by hand and parsed by the standard library's
`tomllib`, adding no dependency.

When `users.toml` is absent, the server falls back to the single athlete in
`.env`, so an existing deployment is unaffected until the file is created.

## Components

| Module | Change |
| --- | --- |
| `config.py` | Add `UserConfig` and `load_users()`; keep `load_config()` for the single-user and stdio paths |
| `server.py` | `build_app` takes a sequence of users and mounts one route set each |
| `adduser.py` | New: CLI that generates a token, appends a user, prints the URL |
| `tools.py`, `client.py`, `compact.py`, `dates.py` | Unchanged — already parameterised by client |

Lifespans of all mounted sub-apps are entered through an `AsyncExitStack`, since
each user contributes both an SSE and a streamable app.

## Validation at startup

Fail loudly rather than serve half a configuration: empty user list, duplicate
tokens, tokens shorter than 20 characters, duplicate names, missing or blank
fields. Athlete ids are normalised to the `i`-prefixed form.

## Adding a user

```
uv run intervals-mcp-adduser --name bob --athlete-id i123 --api-key <key>
```

Generates the token, appends to `users.toml` with mode 600, refuses a duplicate
name or athlete, and prints the connector URL. Hand-editing remains possible but
the CLI avoids typos and duplicate tokens. The server picks up the new user on
`docker compose up -d`.

## Privacy

`/healthz` stays reachable without a token and reveals neither names nor the
number of users. Tokens are not logged: Caddy already strips the request URI, and
the application logs no paths of its own. API keys are excluded from `UserConfig`
reprs so a traceback cannot print them.

## Testing

- `load_users`: valid file, missing file, empty list, duplicate token, duplicate
  name, short token, missing field, blank value, athlete id normalisation, key
  absent from repr.
- App assembly: two users produce two route sets; each token's routes exist.
- **Isolation:** a call authenticated by user A's token issues requests only to
  A's athlete id, and B's token gives no route to A's data. This is the test that
  justifies the whole approach.
- Existing single-token tests move to the new signature with a one-user list.
