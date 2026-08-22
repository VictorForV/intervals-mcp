# intervals.icu MCP server — design

Date: 2026-08-10

## Purpose

Give agents read-only access to one athlete's intervals.icu training data, so an
agent can act as a coach: read completed workouts, training load, wellness
trends, and planned sessions, then reason about them.

## Constraints

- Read-only. Athlete accounts contain sensitive health and training data. The
  server issues GET requests and nothing else.
- Responses must be compact. Raw payloads are large enough to crowd out the
  agent's reasoning budget (measurements below).
- Single athlete per server process, configured by environment.

## Measured API facts

Verified against the live API during initial development. The tracked fixtures
are now generated, fully synthetic examples.

Authentication is HTTP Basic with the literal string `API_KEY` as the username
and the API key as the password. Passing the key as the username fails with
`401 Auth failed`.

Working endpoints:

| Endpoint | Notes |
| --- | --- |
| `GET athlete/{id}/profile` | small |
| `GET athlete/{id}/activities?oldest&newest&limit` | `oldest` is required; 422 without it |
| `GET activity/{id}` | 183 keys, 113 of them null |
| `GET activity/{id}/intervals` | laps under `icu_intervals`, 84 keys each |
| `GET activity/{id}/streams?types=` | 14 019 points per series; 363 KB for three series |
| `GET athlete/{id}/wellness?oldest&newest` | 46 keys/day, ~10 non-null |
| `GET athlete/{id}/events?oldest&newest` | planned workouts |
| `GET athlete/{id}/sport-settings` | FTP and zones per sport group |
| `GET athlete/{id}/{hr,pace,power}-curves?type&oldest&newest` | best-effort curves |
| `GET athlete/{id}/gear`, `/workouts`, `/folders` | small |

Confirmed absent (404): `athlete/{id}/fitness`, `athlete/{id}/activity-totals`,
`athlete/{id}/activity-fields`, `athlete/{id}/intervals`.

## Architecture

Four modules, each independently testable:

| Module | Responsibility | Depends on |
| --- | --- | --- |
| `config.py` | Load `INTERVALS_API_KEY` and `INTERVALS_ATHLETE_ID`; fail with an actionable message when absent | — |
| `dates.py` | Parse ISO dates, relative offsets (`-7d`, `-1y`), and `today`; apply per-tool default windows | — |
| `compact.py` | Pure shaping functions: field whitelists, null stripping, stream downsampling | — |
| `client.py` | HTTP transport: auth, timeout, retry, status-to-message mapping | `config` |
| `server.py` | Tool declarations, argument handling | all of the above |

`compact.py` and `dates.py` are pure, so they are tested directly against
synthetic API-shaped fixtures (`tests/fixtures/`). `client.py` is tested
against mocked HTTP via `respx`. `server.py` is thin glue, verified by the live
smoke script.

## Tools

Twelve read-only tools:

1. `get_athlete_profile()`
2. `get_sport_settings()` — FTP and zones
3. `list_activities(oldest, newest, limit, activity_type)`
4. `get_activity(activity_id)`
5. `get_activity_intervals(activity_id)` — laps
6. `get_activity_streams(activity_id, types, points, full)`
7. `get_wellness(oldest, newest)`
8. `get_events(oldest, newest)`
9. `get_best_efforts(kind, sport_type, oldest, newest)` — `kind` is `hr`, `pace`, or `power`
10. `get_gear()`
11. `list_workouts()` — workout library and folders
12. `intervals_get_raw(path, params)` — escape hatch for any GET path

## Date handling

Agents frequently do not know the current date, and `oldest` is mandatory on
several endpoints. The server resolves dates itself:

- Accepted forms: `2026-08-01`, `today`, `-7d`, `-6w`, `-1y`.
- Defaults: activities and wellness use the last 30 days; events use today
  through +28 days; curves use the last 12 months.
- Resolved window is echoed back in the response so the agent knows what it got.

## Response shaping

Field whitelists keep the fields a coach reasons about and drop the rest. Nulls
are stripped after filtering, so an activity without a power meter does not
carry 30 empty power fields.

Streams are downsampled to `points` samples (default 200) by uniform stride,
alongside a summary of min/mean/max and the original point count. `full=true`
returns every point and is documented as expensive.

Every list response reports how many items matched versus how many were
returned, so truncation is never silent.

## Error handling

The client retries network errors and 5xx three times with exponential backoff.
Status codes map to actionable text: 401 explains the `API_KEY` username
convention, 403 means no access to that athlete, 404 means the id does not
exist, 422 names the missing parameter. Errors are returned to the agent as
text rather than crashing the process.

## Secrets

`INTERVALS_API_KEY` and `INTERVALS_ATHLETE_ID` live in `.env`, mode 600, listed
in `.gitignore` before the first commit. `.env.example` documents the shape.

## Testing

- Unit tests for `compact.py` and `dates.py` against captured live fixtures.
- Mocked-transport tests for `client.py` covering 401/403/404/422/500 and retry.
- `scripts/smoke.py` exercises all twelve tools against the live account and
  reports payload sizes before and after shaping.
