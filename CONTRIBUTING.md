# Contributing

Contributions are welcome through GitHub issues and pull requests.

## Development setup

```bash
git clone https://github.com/VictorForV/intervals-mcp.git
cd intervals-mcp
uv sync
uv run pytest
```

Keep changes focused and add tests for new behavior. The unit suite must remain
offline and deterministic.

## Fixture privacy

Never commit a raw Intervals.icu response. Responses can contain names,
locations, account identifiers, free text, device details, and training data.
The tracked fixtures are fully synthetic and are generated with
`scripts/generate_fixtures.py`. Extend that generator when a new API shape is
needed.

Do not weaken `.gitignore` rules for `.env` or `users.toml`. Use obvious example
values in documentation and tests.
