#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi
MIN_AUC="${MIN_AUC:-0.85}"

"$PYTHON_BIN" "$ROOT_DIR/scripts/train_model.py" --min-auc "$MIN_AUC" "$@"
