#!/usr/bin/env bash
set -euo pipefail

INSTALL_BIN="$HOME/.local/bin"
INSTALL_SHARE="$HOME/.local/share/wrun"

echo "Installing wrun..."

# Create directories
mkdir -p "$INSTALL_BIN" "$INSTALL_SHARE"

# Copy files
cp wrun "$INSTALL_BIN/wrun"
chmod +x "$INSTALL_BIN/wrun"
cp integration.zsh "$INSTALL_SHARE/integration.zsh"

# Check PATH
if ! echo "$PATH" | tr ':' '\n' | grep -q "$INSTALL_BIN"; then
    echo "WARNING: $INSTALL_BIN is not in PATH. Add it:"
    echo "  export PATH=\"$INSTALL_BIN:\$PATH\""
fi

echo ""
echo "Installed:"
echo "  $INSTALL_BIN/wrun"
echo "  $INSTALL_SHARE/integration.zsh"
echo ""
echo "Setup (add to ~/.zshenv for auto-activation in AI sessions):"
echo ""
echo '  if [[ ! -o interactive ]]; then'
echo '      export WRUN_AUTO=1'
echo '      [[ -f ~/.local/share/wrun/integration.zsh ]] && source ~/.local/share/wrun/integration.zsh'
echo '  fi'
echo ""
echo "Or for interactive shells (add to ~/.zshrc):"
echo '  [[ -f ~/.local/share/wrun/integration.zsh ]] && source ~/.local/share/wrun/integration.zsh'
echo '  export WRUN_AUTO=1  # optional: enable auto-wrap in terminal too'
echo ""
echo "Done."
