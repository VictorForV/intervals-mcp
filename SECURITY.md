# Security policy

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository. Do not
include API keys, connector URLs, athlete data, or other secrets in a public
issue.

If private reporting is unavailable, open a public issue containing only a
non-sensitive summary and ask the maintainer for a private contact channel.

## Operational security

- Never commit `.env`, `users.toml`, API keys, or complete connector URLs.
- Treat every URL containing an athlete token as a password.
- Rotate a user's token immediately after accidental disclosure.
- Keep the host, Docker images, and dependencies updated.
- Expose the service through HTTPS only.

Intervals MCP is intentionally read-only, but the data it exposes may include
health, location, and training information. Server operators are responsible for
obtaining athlete consent and protecting their deployment.
