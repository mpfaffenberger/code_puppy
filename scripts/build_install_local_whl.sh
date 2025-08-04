#!/usr/bin/env bash
# shellcheck disable=SC2034
# shellcheck disable=SC2002
set -e

SELF=$(basename "$0")
HEADER=$(cat<<'EOH'
#=====================================================================
# build_install_local_whl.sh
#=====================================================================
# DESCRIPTION
#     This is useful if you want to test how current code-puppy changes would
#     behave on a user's machine after installing from the puppy-frontend setup script
#     - builds a new code_puppy wheel file from the current local code-puppy repo
#     - uninstalls the global code-puppy installation
#     - re-installs from the newly created wheel file
# PRE-REQUISITES:
#     - uv installed and in the PATH
#     - pip or pip3 installed and in the PATH
#     - you need to be on VPN or Eagle
#
#- OPTIONS
#-    -h, --help                Print detailed help and usage
#-
#- EXAMPLES:
#-
#- $0                  - builds and re-installs code-puppy globally
#- $0 -h               - displays help
#- $0 --help           - displays help
#
#
#=====================================================================
EOH
:)

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="$PROJECT_DIR/scripts"
VENV_DIR="$HOME/.code-puppy-venv"
UV_INDEX_URL="https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple"

# shellcheck source=/dev/null
source "$SCRIPTS_DIR/common.sh"

#----------------------------------------------------------------
# Collect arguments
#----------------------------------------------------------------
(( $# != 0 && $# != 1 )) && \
  bail_with_usage "garbled command options"
while [ $# -gt 0 ]; do
  case $1 in
  (-h|--help)    show_help;;
  (-*)  bail_with_usage "$1 unknown option"; break;;
  (*) break;;
  esac
done

step=">>> 🔧 Checking the environment..."
echo "$step"
if ! command -v uv >/dev/null; then
  error_handler 101 "'uv' not found. Please install it and retry"
fi

step=">>> 🗑 Removing existing venv if present..."
echo "$step"
rm -rf "$VENV_DIR"
error_handler $? "step: $step failed"

step=">>> 🔧 Creating a fresh venv with uv..."
echo "$step"
uv venv --default-index "$UV_INDEX_URL" "$VENV_DIR"
error_handler $? "step: $step failed"

step=">>> 🔧 Activating the new venv..."
echo "$step"
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"
error_handler $? "step: $step failed"

step=">>> 📦 Building wheel file..."
echo "$step"
cd "$PROJECT_DIR" || exit # Navigate to the root directory of code-puppy repo
uv build
error_handler $? "step: $step failed"

# shellcheck disable=SC2012
WHEEL_FILE=$(ls -t dist/*.whl | head -1) # Get the latest wheel file
echo ">>> 🛞 New wheel file: $WHEEL_FILE"

step=">>> 🔧 Installing from new wheel file: $WHEEL_FILE"
echo "$step"
cd "$HOME" || exit
uv pip install --native-tls --index-url "$UV_INDEX_URL" "$PROJECT_DIR/$WHEEL_FILE" --force-reinstall
error_handler $? "step: $step failed"

step="🔧  Installing textual cli into venv…"
echo "$step"
uv pip install --native-tls --index-url "$UV_INDEX_URL" textual-dev
error_handler $? "step: $step failed"

step=">>> 🧹 Deactivating venv"
echo "$step"
deactivate
error_handler $? "step: $step failed"

echo ">>> 🎉  Code Puppy installed successfully!"

echo ">>> 🐶 $VENV_DIR/bin/code-puppy -v"
cd "$HOME" || exit
"$VENV_DIR"/bin/code-puppy -v

echo "Use the following command to run this new version:"
echo
echo "NO_VERSION_UPDATE=1 $VENV_DIR/bin/code-puppy"
