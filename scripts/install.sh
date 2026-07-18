#!/usr/bin/env bash
#
# Mist installer — fresh macOS/Linux system to working `mist` in one command:
#
#   git clone https://github.com/bajajra/mist.git && cd mist && ./scripts/install.sh
#
# Installs Bun if missing, builds the self-contained binary, links it onto
# PATH, and prints the first-run model setup. Override the link location with
# MIST_BIN_DIR (default: ~/.local/bin, or /opt/homebrew/bin if writable).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ---- 1. Bun ----------------------------------------------------------------
if ! command -v bun >/dev/null 2>&1; then
  echo "→ Bun not found — installing (https://bun.sh)"
  curl -fsSL https://bun.sh/install | bash
  export BUN_INSTALL="${BUN_INSTALL:-$HOME/.bun}"
  export PATH="$BUN_INSTALL/bin:$PATH"
fi
echo "✓ bun $(bun --version)"

# ---- 2. Build --------------------------------------------------------------
cd "$REPO_ROOT/ts"
bun install
bun run build
echo "✓ built ts/dist/mist ($(du -h dist/mist | cut -f1 | tr -d ' '))"

# ---- 3. Link onto PATH -----------------------------------------------------
if [ -n "${MIST_BIN_DIR:-}" ]; then
  BIN_DIR="$MIST_BIN_DIR"
elif [ -d /opt/homebrew/bin ] && [ -w /opt/homebrew/bin ]; then
  BIN_DIR=/opt/homebrew/bin
else
  BIN_DIR="$HOME/.local/bin"
fi
mkdir -p "$BIN_DIR"
ln -sf "$REPO_ROOT/ts/dist/mist" "$BIN_DIR/mist"
echo "✓ linked $BIN_DIR/mist"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "⚠  $BIN_DIR is not on your PATH — add to your shell profile:"
     echo "     export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac

# ---- 4. First-run guidance -------------------------------------------------
cat <<'EOF'

Next steps:
  1. Pick a model (any ONE of these works):
       • Anthropic (zero config): export ANTHROPIC_API_KEY=sk-ant-...
         — the default model is claude-opus-4-8; claude-* names need no registry
       • OpenAI:  export OPENAI_API_KEY=... ; then inside mist: /model gpt-5.2
       • Gemini:  export GEMINI_API_KEY=... ; then inside mist: /model gemini-2.0-flash
       • Custom/Anthropic-compatible endpoints (z.ai, minimax, cerebras, local):
         add an entry to ~/.mist/extra_models.json, e.g.
           { "my-model": { "type": "custom_anthropic", "name": "model-code",
             "custom_endpoint": { "url": "https://api.example.com/anthropic",
                                  "api_key": "..." },
             "context_length": 256000 } }
  2. Run it:
       mist                 # interactive session
       mist "fix the bug"   # one-shot
       mist -c              # resume the latest session here
  3. Inside mist: /help for commands, /model to switch models, /theme for looks.

Optional: MCP servers in ~/.mist/mcp_servers.json (same schema as Python Mist).
EOF
