#!/bin/sh
# Code GPT CLI installer for macOS and Linux.  Usage:  curl -fsSL https://codegpt.it.com/install.sh | sh
set -e
APP_URL="https://chat.codegpt.it.com"
DIR="$HOME/.codegpt"
BIN="$HOME/.local/bin"
echo "Installing the Code GPT CLI..."
PY=""
for p in python3 python; do
  if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then PY="$p"; break; fi
done
if [ -z "$PY" ]; then
  echo "The Code GPT CLI needs Python 3.8 or newer."
  echo "  macOS:  brew install python      (or download it from https://www.python.org/downloads/)"
  echo "  Ubuntu: sudo apt install python3"
  exit 1
fi
mkdir -p "$DIR" "$BIN"
if command -v curl >/dev/null 2>&1; then curl -fsSL "$APP_URL/static/downloads/codegpt-cli/codegpt.py" -o "$DIR/codegpt.py"
else wget -qO "$DIR/codegpt.py" "$APP_URL/static/downloads/codegpt-cli/codegpt.py"; fi
cat > "$BIN/codegpt" <<EOF
#!/bin/sh
exec "$(command -v $PY)" "$DIR/codegpt.py" "\$@"
EOF
chmod +x "$BIN/codegpt"
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
       [ -f "$rc" ] && ! grep -q '.local/bin' "$rc" && printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$rc"
     done
     echo "Added $BIN to your PATH. Open a new terminal (or run: export PATH=\"$BIN:\$PATH\")." ;;
esac
echo ""
echo "Done. Start with:   codegpt login"
