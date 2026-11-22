#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/Rutytoi220/chess-tui.git"
BIN_DIR="${HOME}/.local/bin"
VENV_DIR="${HOME}/.local/share/chess-tui/venv"

echo "Installing chess-tui..."

if command -v uv >/dev/null 2>&1; then
  uv tool install --force "git+${REPO_URL}"
elif command -v pipx >/dev/null 2>&1; then
  pipx install --force "git+${REPO_URL}"
elif command -v python3 >/dev/null 2>&1; then
  if ! python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"; then
    echo "Error: Python 3.11+ is required (found $(python3 --version))." >&2
    exit 1
  fi
  mkdir -p "${BIN_DIR}" "$(dirname "${VENV_DIR}")"
  python3 -m venv "${VENV_DIR}"
  "${VENV_DIR}/bin/pip" install --upgrade pip >/dev/null
  "${VENV_DIR}/bin/pip" install --upgrade "git+${REPO_URL}"
  ln -sf "${VENV_DIR}/bin/chess-tui" "${BIN_DIR}/chess-tui"
  ln -sf "${VENV_DIR}/bin/chesscom-tui" "${BIN_DIR}/chesscom-tui"
else
  echo "Error: Please install uv, pipx, or Python 3.11+." >&2
  exit 1
fi

echo ""
echo "Installed! Run: chess-tui"
case ":${PATH}:" in
  *":${BIN_DIR}:"*) ;;
  *)
    echo "Note: Add ${BIN_DIR} to your PATH if 'chess-tui' is not found:"
    echo "  export PATH=\"\${HOME}/.local/bin:\${PATH}\""
    ;;
esac
