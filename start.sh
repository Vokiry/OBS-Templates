#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "=================================================="
echo "    SYSTEM — OBS Broadcast Templates Launcher     "
echo "=================================================="

# 1. Check Python
if ! command -v python3 &>/dev/null; then
  echo "[!] Python 3 not found. Please install Python 3.10+"
  exit 1
fi

# 2. Check virtualenv
if [ ! -d "bridge/.venv" ]; then
  echo "[*] Initializing virtual environment in bridge/.venv..."
  python3 -m venv bridge/.venv
  ./bridge/.venv/bin/pip install --upgrade pip
  ./bridge/.venv/bin/pip install -r bridge/requirements.txt
fi

# 3. Check config.toml
if [ ! -f "bridge/config.toml" ]; then
  echo "[*] Creating bridge/config.toml from template..."
  cp bridge/config.example.toml bridge/config.toml
fi

# 4. Generate & link OBS Scene Collection if OBS config folder exists
if [ -d "$HOME/.config/obs-studio/basic/scenes" ]; then
  echo "[*] Updating SYSTEM Scene Collection in OBS Studio..."
  python3 obs/generate_collection.py >/dev/null 2>&1 || true
  cp obs/SYSTEM_Scene_Collection.json "$HOME/.config/obs-studio/basic/scenes/SYSTEM.json" 2>/dev/null || true
fi

echo ""
echo "  [✓] Unified Server:   http://localhost:8787/"
echo "  [✓] Control Dock:     http://localhost:8787/dock"
echo "  [✓] Event WebSocket:  ws://localhost:8787/events"
echo ""
echo "  [!] In OBS Studio:"
echo "      1. Scene Collection -> select 'SYSTEM Broadcast Templates'"
echo "         (or Scene Collection -> Import -> obs/SYSTEM_Scene_Collection.json)"
echo "      2. Docks -> Custom Browser Docks:"
echo "         Name: SYSTEM Dock, URL: http://localhost:8787/dock"
echo "=================================================="
echo "[*] Starting SYSTEM server... (Press Ctrl+C to stop)"
echo ""

exec ./bridge/.venv/bin/python bridge/alerts_bridge.py
