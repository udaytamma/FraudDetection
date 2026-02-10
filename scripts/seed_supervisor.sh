#!/usr/bin/env bash
set -u -o pipefail

ROOT="/Users/omega/Projects/FraudDetection"
LOG_DIR="$ROOT/storage"
UVICORN_LOG="$LOG_DIR/uvicorn.log"
SEED_LOG="$LOG_DIR/seed_supervisor.log"
STATUS_LOG="$LOG_DIR/seed_status.log"
UVICORN_PID_FILE="$LOG_DIR/uvicorn.pid"
SEED_PID_FILE="$LOG_DIR/seed.pid"

TARGET_COUNT="${TARGET_COUNT:-250000}"
CONCURRENCY="${CONCURRENCY:-300}"
PER_RUN="${PER_RUN:-50000}"
RUNS="${RUNS:-1}"

mkdir -p "$LOG_DIR"
: > "$STATUS_LOG"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  source "$ROOT/.env"
  set +a
fi

POSTGRES_URL="${POSTGRES_URL:-postgresql://${POSTGRES_USER:-fraud_user}:${POSTGRES_PASSWORD:-fraud_dev_password}@${POSTGRES_HOST:-localhost}:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-fraud_detection}}"

is_running() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid=$(cat "$pid_file" 2>/dev/null || true)
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

start_uvicorn() {
  if is_running "$UVICORN_PID_FILE"; then
    return 0
  fi
  nohup "$ROOT/venv/bin/uvicorn" src.api.main:app \
    --host 0.0.0.0 --port 8000 --workers 1 --log-level warning \
    > "$UVICORN_LOG" 2>&1 &
  echo $! > "$UVICORN_PID_FILE"
}

start_seeder() {
  if is_running "$SEED_PID_FILE"; then
    return 0
  fi
  nohup env PYTHONUNBUFFERED=1 "$ROOT/venv/bin/python" \
    "$ROOT/scripts/seed_synthetic.py" \
    --runs "$RUNS" --per-run "$PER_RUN" \
    --mature-ratio 0.8 --maturity-days 120 --backdate-captured-at \
    --concurrency "$CONCURRENCY" \
    --postgres-url "$POSTGRES_URL" \
    --log-every 10000 \
    >> "$SEED_LOG" 2>&1 &
  echo $! > "$SEED_PID_FILE"
}

current_count() {
  "$ROOT/venv/bin/python" - <<PY
import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect("$POSTGRES_URL")
    try:
        tx = await conn.fetchval('SELECT COUNT(*) FROM transaction_evidence')
        cb = await conn.fetchval('SELECT COUNT(*) FROM chargebacks')
        print(f"{tx} {cb}")
    finally:
        await conn.close()

asyncio.run(main())
PY
}

while true; do
  counts=$(current_count 2>/dev/null || echo "0 0")
  tx=$(echo "$counts" | awk '{print $1}')
  cb=$(echo "$counts" | awk '{print $2}')
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo "$ts transaction_evidence=$tx chargebacks=$cb" >> "$STATUS_LOG"

  if [[ "${tx:-0}" -ge "$TARGET_COUNT" ]]; then
    if is_running "$SEED_PID_FILE"; then
      kill "$(cat "$SEED_PID_FILE")" 2>/dev/null || true
      rm -f "$SEED_PID_FILE"
    fi
    if is_running "$UVICORN_PID_FILE"; then
      kill "$(cat "$UVICORN_PID_FILE")" 2>/dev/null || true
      rm -f "$UVICORN_PID_FILE"
    fi
    echo "$ts target reached: $tx" >> "$STATUS_LOG"
    exit 0
  fi

  start_uvicorn
  start_seeder

  sleep 300

done
