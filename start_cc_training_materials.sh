#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_DATASET="$SCRIPT_DIR/cc_training_materials_dataset"

exec python3 "$SCRIPT_DIR/cc_training_materials.py" \
  --dataset "$DEFAULT_DATASET" \
  --host 0.0.0.0 \
  "$@"
