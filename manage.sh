#!/usr/bin/env sh
set -eu

if command -v uv >/dev/null 2>&1; then
  exec uv run intervals-mcp-admin "$@"
fi

if [ -x .venv/bin/python ]; then
  exec .venv/bin/python -m intervals_mcp.admin "$@"
fi

printf 'uv is not installed. Install it from the official Astral installer now? [Y/n] '
read -r answer
case "${answer:-Y}" in
  y|Y|yes|YES)
    if command -v curl >/dev/null 2>&1; then
      curl -LsSf https://astral.sh/uv/install.sh | sh
    else
      echo "Error: curl is required for automatic installation." >&2
      echo "See https://docs.astral.sh/uv/getting-started/installation/" >&2
      exit 1
    fi
    PATH="${HOME}/.local/bin:${PATH}"
    export PATH
    exec uv run intervals-mcp-admin "$@"
    ;;
  *)
    echo "Install uv from https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
    ;;
esac
