#!/usr/bin/env bash
# Install a Desktop launcher for OpenSesame (Kali / GNOME / KDE friendly).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
# OpenSesame vanish build — sling ring cursor + .hidden illusion
VENV_PYTHON="$ROOT/.venv/bin/python"
MAIN="$ROOT/main.py"
ICON="$ROOT/appicon.png"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Virtual env missing. Run first:"
  echo "  cd \"$ROOT\" && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$DESKTOP_DIR"

DESKTOP_FILE="$DESKTOP_DIR/opensesame.desktop"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=OpenSesame
Comment=Dr. Strange magic ring toy
Exec=$VENV_PYTHON $MAIN
Icon=$ICON
Terminal=false
Categories=Utility;
StartupNotify=true
EOF

chmod +x "$DESKTOP_FILE"

# Also drop a copy on ~/Desktop when that folder exists (common on KDE/Xfce)
if [[ -d "$HOME/Desktop" ]]; then
  cp "$DESKTOP_FILE" "$HOME/Desktop/OpenSesame.desktop"
  chmod +x "$HOME/Desktop/OpenSesame.desktop"
  echo "Installed: $HOME/Desktop/OpenSesame.desktop"
fi

echo "Installed: $DESKTOP_FILE"
echo "Launch OpenSesame from your app menu or Desktop, then click the ring."
