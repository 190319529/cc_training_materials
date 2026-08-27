#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$BASE_DIR/app"
DATASET_DIR="$BASE_DIR/dataset"
PYTHON="$BASE_DIR/venv/bin/python"
PID_FILE="$BASE_DIR/cc_training_materials.pid"
LOG_FILE="$BASE_DIR/cc_training_materials.log"

export HOME="$BASE_DIR/home"
export XDG_CONFIG_HOME="$BASE_DIR/home/.config"
export MPLCONFIGDIR="$BASE_DIR/home/.cache/matplotlib"
export YOLO_CONFIG_DIR="$BASE_DIR/home/.config/Ultralytics"
export TMPDIR="$BASE_DIR/tmp"
mkdir -p "$HOME" "$XDG_CONFIG_HOME" "$MPLCONFIGDIR" "$YOLO_CONFIG_DIR" "$TMPDIR"

if [[ ! -x "$PYTHON" ]]; then
  echo "Python environment is missing: $PYTHON" >&2
  exit 1
fi

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "cc_training_materials is already running (PID $(cat "$PID_FILE"))"
  exit 0
fi

cd "$APP_DIR"
nohup "$PYTHON" "$APP_DIR/cc_training_materials.py" \
  --dataset "$DATASET_DIR" \
  --host 0.0.0.0 \
  --port 8765 \
  --no-browser \
  >> "$LOG_FILE" 2>&1 < /dev/null &

echo $! > "$PID_FILE"
sleep 1
if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Service failed to start. See $LOG_FILE" >&2
  exit 1
fi
echo "cc_training_materials started: http://172.10.10.150:8765/"
