#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

LAUNCH_OBS=false
RESET_SCENES=false

for arg in "$@"; do
  case "$arg" in
    --obs)
      LAUNCH_OBS=true
      ;;
    --reset-scenes)
      RESET_SCENES=true
      ;;
    -h|--help)
      echo "SYSTEM Broadcast Templates — Launcher"
      echo ""
      echo "Usage: ./start.sh [options]"
      echo ""
      echo "Options:"
      echo "  --obs           Start OBS Studio (with QT_QPA_PLATFORM=xcb) once bridge is ready"
      echo "  --reset-scenes  Force restore OBS scenes from template (backs up existing SYSTEM.json)"
      echo "  -h, --help      Show this help message"
      exit 0
      ;;
  esac
done

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

# 4. Safe scene collection handling (never overwrite user sources without confirmation)
OBS_SCENES_DIR="$HOME/.config/obs-studio/basic/scenes"
if [ -d "$OBS_SCENES_DIR" ]; then
  DEST_FILE="$OBS_SCENES_DIR/SYSTEM.json"
  if [ ! -f "$DEST_FILE" ]; then
    echo "[*] First run: importing SYSTEM scene collection to OBS..."
    ./bridge/.venv/bin/python obs/generate_collection.py >/dev/null 2>&1 || true
    cp obs/SYSTEM_Scene_Collection.json "$DEST_FILE" 2>/dev/null || true
    echo "    [✓] Created: $DEST_FILE"
  elif [ "$RESET_SCENES" = true ]; then
    BACKUP="$DEST_FILE.bak.$(date +%Y%m%d_%H%M%S)"
    cp "$DEST_FILE" "$BACKUP"
    echo "[!] Existing scenes backed up to: $(basename "$BACKUP")"
    ./bridge/.venv/bin/python obs/generate_collection.py >/dev/null 2>&1 || true
    cp obs/SYSTEM_Scene_Collection.json "$DEST_FILE"
    echo "    [✓] Reset $DEST_FILE to template defaults."
  else
    echo "[i] Existing OBS scene collection kept intact (custom sources preserved)."
    echo "    (To reset scenes to template defaults: ./start.sh --reset-scenes)"
  fi
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

if [ "$LAUNCH_OBS" = true ]; then
  echo "[*] Starting SYSTEM server in background..."
  ./bridge/.venv/bin/python bridge/alerts_bridge.py &
  SERVER_PID=$!

  cleanup() {
    echo ""
    echo "[*] Stopping SYSTEM server (PID $SERVER_PID)..."
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
    exit 0
  }
  trap cleanup SIGINT SIGTERM EXIT

  echo "[*] Waiting for server on http://localhost:8787/health..."
  READY=false
  for i in {1..20}; do
    if curl -s http://127.0.0.1:8787/health | grep -q '"status":"running"'; then
      READY=true
      break
    fi
    sleep 0.5
  done

  if [ "$READY" = true ]; then
    echo "    [✓] Server is ready."
  else
    echo "    [!] Server check timed out, continuing..."
  fi

  echo "[*] Launching OBS Studio with QT_QPA_PLATFORM=xcb..."
  QT_QPA_PLATFORM=xcb obs &
  echo "    [✓] OBS Studio launched."
  echo ""
  echo "[*] SYSTEM bridge running. Press Ctrl+C to stop."

  wait "$SERVER_PID"
else
  echo "[*] Starting SYSTEM server... (Press Ctrl+C to stop, or pass --obs to launch OBS)"
  echo ""
  exec ./bridge/.venv/bin/python bridge/alerts_bridge.py
fi
