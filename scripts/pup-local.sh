#!/usr/bin/env bash
#==========================================================================
# pup-local.sh
#==========================================================================
# DESCRIPTION:
#   Manage a GLOBAL, editable install of code-puppy via `uv tool`.
#   This exposes `code-puppy` and `pup` on your PATH (~/.local/bin) so you
#   can run them from any repo, while still tracking your local clone live.
#
#   NOTE: this is NOT the same as `code-puppy-dev`. That script reinstalls
#   into the project's local .venv and uses `uv run`. This one manages the
#   machine-wide tool install instead.
#
# USAGE:
#   pup-local.sh --install     # or -i : (re)install editable global tool
#   pup-local.sh --uninstall   # or -u : remove the global tool
#   pup-local.sh --help        # or -h : show this help
#
# CONFIG:
#   Defaults to the current directory; override with PUP_REPO_DIR if needed:
#     PUP_REPO_DIR=/path/to/code-puppy pup-local.sh -i
#==========================================================================

set -euo pipefail

# Default to the current directory; override with PUP_REPO_DIR if needed.
REPO_DIR="${PUP_REPO_DIR:-$(pwd)}"

# --- pretty output helpers -------------------------------------------------
c_info()  { printf '\033[1;36m[*] %s\033[0m\n' "$*"; }
c_ok()    { printf '\033[1;32m[ok] %s\033[0m\n' "$*"; }
c_warn()  { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }
c_err()   { printf '\033[1;31m[x] %s\033[0m\n' "$*" >&2; }

usage() {
  # Print the leading comment header (everything from line 2 up to the
  # first non-'#' line), stripping the leading '# '.
  awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"
}

require_uv() {
  command -v uv >/dev/null 2>&1 || {
    c_err "uv not found on PATH. Install it first: https://docs.astral.sh/uv/"
    exit 1
  }
}

do_install() {
  require_uv
  [ -f "$REPO_DIR/pyproject.toml" ] || {
    c_err "No pyproject.toml at: $REPO_DIR"
    c_err "Set PUP_REPO_DIR to your clone path and retry."
    exit 1
  }
  c_info "Installing editable global code-puppy from: $REPO_DIR"
  uv tool install --editable "$REPO_DIR" --force
  c_ok "Done. 'code-puppy' and 'pup' now track your clone live."
  c_info "Tip: re-run --install after dependency changes in pyproject.toml."
}

do_uninstall() {
  require_uv
  c_info "Uninstalling global code-puppy tool..."
  uv tool uninstall code-puppy
  c_ok "Gone. (Your clone at $REPO_DIR is untouched.)"
}

# --- arg parsing -----------------------------------------------------------
[ $# -eq 0 ] && { usage; exit 1; }

case "$1" in
  -i|--install)   do_install   ;;
  -u|--uninstall) do_uninstall ;;
  -h|--help)      usage        ;;
  *)
    c_err "Unknown argument: $1"
    usage
    exit 1
    ;;
esac
