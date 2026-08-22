FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.11 /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first so code edits do not invalidate the layer.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src/ ./src/
RUN uv sync --locked --no-dev

ENV PORT=8080
EXPOSE 8080

CMD ["uv", "run", "--no-dev", "intervals-mcp-http"]
