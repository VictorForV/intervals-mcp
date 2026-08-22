#!/usr/bin/env bash
set -Eeuo pipefail

readonly REPOSITORY_URL="https://github.com/VictorForV/intervals-mcp.git"
readonly INSTALL_DIR="${INTERVALS_MCP_DIR:-/opt/intervals-mcp}"

info() {
  printf '\n\033[1;34m==>\033[0m %s\n' "$*"
}

fail() {
  printf '\n\033[1;31mError:\033[0m %s\n' "$*" >&2
  exit 1
}

if [[ "$(uname -s)" != "Linux" ]]; then
  fail "This installer supports Linux only."
fi

if [[ "${EUID}" -ne 0 ]]; then
  fail "Run this installer as root, for example: curl ... | sudo bash"
fi

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  source /etc/os-release
else
  fail "Cannot identify the operating system (/etc/os-release is missing)."
fi

case "${ID:-}" in
  ubuntu|debian) ;;
  *) fail "Automatic installation currently supports Ubuntu and Debian only." ;;
esac

APP_USER="${SUDO_USER:-}"
if [[ -z "${APP_USER}" || "${APP_USER}" == "root" ]]; then
  APP_USER="${INTERVALS_MCP_USER:-root}"
fi
id "${APP_USER}" >/dev/null 2>&1 || fail "User ${APP_USER@Q} does not exist."
APP_HOME="$(getent passwd "${APP_USER}" | cut -d: -f6)"
[[ -n "${APP_HOME}" ]] || fail "Cannot determine the home directory for ${APP_USER}."

export DEBIAN_FRONTEND=noninteractive

info "Installing base packages"
apt-get update
apt-get install -y ca-certificates curl git

install_docker() {
  info "Installing Docker Engine and the Compose plugin"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" \
    -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc

  local architecture codename
  architecture="$(dpkg --print-architecture)"
  codename="${VERSION_CODENAME:-}"
  [[ -n "${codename}" ]] || fail "Cannot determine the distribution codename."
  printf '%s\n' \
    "deb [arch=${architecture} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${codename} stable" \
    > /etc/apt/sources.list.d/docker.list

  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
}

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  install_docker
else
  info "Docker Engine and Compose are already installed"
fi

if [[ "${APP_USER}" != "root" ]]; then
  usermod -aG docker "${APP_USER}"
fi

run_as_app_user() {
  if [[ "${APP_USER}" == "root" ]]; then
    HOME="${APP_HOME}" PATH="${APP_HOME}/.local/bin:${PATH}" "$@"
  else
    runuser -u "${APP_USER}" -- env \
      HOME="${APP_HOME}" PATH="${APP_HOME}/.local/bin:${PATH}" "$@"
  fi
}

if ! run_as_app_user bash -lc 'command -v uv >/dev/null 2>&1'; then
  info "Installing uv for ${APP_USER}"
  uv_installer="$(mktemp)"
  trap 'rm -f "${uv_installer:-}"' EXIT
  curl -LsSf https://astral.sh/uv/install.sh -o "${uv_installer}"
  chmod 0755 "${uv_installer}"
  run_as_app_user sh "${uv_installer}"
fi

# uv was just installed into ${APP_HOME}/.local/bin by a subprocess above,
# which does not change this script's own PATH. Without this, manage.sh
# (execed below) would not find uv and wrongly offer to install it again.
export PATH="${APP_HOME}/.local/bin:${PATH}"

info "Installing Intervals MCP in ${INSTALL_DIR}"
if [[ -d "${INSTALL_DIR}/.git" ]]; then
  current_origin="$(run_as_app_user git -C "${INSTALL_DIR}" remote get-url origin 2>/dev/null || true)"
  [[ "${current_origin}" == "${REPOSITORY_URL}" || "${current_origin}" == "git@github.com:VictorForV/intervals-mcp.git" ]] \
    || fail "${INSTALL_DIR} is a Git repository with a different origin."
  run_as_app_user git -C "${INSTALL_DIR}" pull --ff-only
elif [[ -e "${INSTALL_DIR}" ]]; then
  fail "${INSTALL_DIR} already exists and is not an Intervals MCP Git checkout."
else
  git clone "${REPOSITORY_URL}" "${INSTALL_DIR}"
fi

chown -R "${APP_USER}:${APP_USER}" "${INSTALL_DIR}"

info "Opening Intervals MCP Manager"
printf 'Installation directory: %s\n' "${INSTALL_DIR}"
printf 'Run the manager later with: cd %s && ./manage.sh\n\n' "${INSTALL_DIR}"

if [[ ! -r /dev/tty ]]; then
  fail "No interactive terminal is available. Run ${INSTALL_DIR}/manage.sh after installation."
fi

if [[ "${APP_USER}" == "root" ]]; then
  cd "${INSTALL_DIR}"
  exec ./manage.sh </dev/tty >/dev/tty 2>&1
else
  exec runuser -u "${APP_USER}" -- env HOME="${APP_HOME}" \
    PATH="${APP_HOME}/.local/bin:${PATH}" \
    bash -c "cd '${INSTALL_DIR}' && exec ./manage.sh" </dev/tty >/dev/tty 2>&1
fi
