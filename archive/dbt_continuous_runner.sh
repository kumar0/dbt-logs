#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# dbt Continuous Runner
# Runs dbt models in a loop with random model selection.
# Waits 30s–60s between runs (only after previous run finishes).
# ─────────────────────────────────────────────────────────────

# ── Environment variable defaults ──
export GLUE_SESSION_ID="${GLUE_SESSION_ID:-glue-session-$(date +%s)}"
export WORKER_TYPE="${WORKER_TYPE:-G.1X}"
export NUM_WORKERS="${NUM_WORKERS:-3}"
export AWS_PROFILE="${AWS_PROFILE:-mondayskills.development}"
export AWS_REGION="${AWS_REGION:-us-east-1}"
export DBT_PROFILES_DIR="${DBT_PROFILES_DIR:-$(dirname "$0")}"
export RUN_INTERVAL_MIN="${RUN_INTERVAL_MIN:-30}"
export RUN_INTERVAL_MAX="${RUN_INTERVAL_MAX:-60}"

# ── All available models ──
MODELS=(
  "stg_customers"
  "stg_orders"
  "stg_order_items"
  "stg_payments"
  "stg_products"
  "dim_customers"
  "dim_products"
  "fact_order_items"
  "fact_orders"
)

# ── on-project-start: log all env vars as JSON ──
log_env_json() {
  local ts
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  cat <<EOF
{
  "event": "project_start",
  "timestamp": "${ts}",
  "env": {
    "GLUE_SESSION_ID": "${GLUE_SESSION_ID}",
    "WORKER_TYPE": "${WORKER_TYPE}",
    "NUM_WORKERS": "${NUM_WORKERS}",
    "AWS_PROFILE": "${AWS_PROFILE}",
    "AWS_REGION": "${AWS_REGION}",
    "DBT_PROFILES_DIR": "${DBT_PROFILES_DIR}",
    "RUN_INTERVAL_MIN": "${RUN_INTERVAL_MIN}",
    "RUN_INTERVAL_MAX": "${RUN_INTERVAL_MAX}"
  }
}
EOF
}

# ── Pick a random model ──
random_model() {
  local idx=$(( RANDOM % ${#MODELS[@]} ))
  echo "${MODELS[$idx]}"
}

# ── Random sleep between min and max seconds ──
random_sleep() {
  local min=$RUN_INTERVAL_MIN
  local max=$RUN_INTERVAL_MAX
  local range=$(( max - min + 1 ))
  local secs=$(( RANDOM % range + min ))
  echo "$secs"
}

# ── Main ──
echo "============================================"
log_env_json
echo "============================================"

RUN_NUMBER=0

while true; do
  RUN_NUMBER=$(( RUN_NUMBER + 1 ))
  MODEL=$(random_model)
  START_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  START_EPOCH=$(date +%s)

  # Log run start as JSON
  cat <<EOF
{"event":"run_start","run_number":${RUN_NUMBER},"model":"${MODEL}","glue_session_id":"${GLUE_SESSION_ID}","timestamp":"${START_TS}"}
EOF

  # Run dbt with JSON logging, metrics enabled via conf, random model selection
  set +e
  dbt run \
    --log-format json \
    --select "$MODEL" \
    --profiles-dir "$DBT_PROFILES_DIR" \
    --vars "{glue_session_id: '${GLUE_SESSION_ID}', worker_type: '${WORKER_TYPE}', num_workers: ${NUM_WORKERS}}" \
    2>&1
  EXIT_CODE=$?
  set -e

  END_EPOCH=$(date +%s)
  DURATION=$(( END_EPOCH - START_EPOCH ))
  END_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  STATUS="success"
  [ "$EXIT_CODE" -ne 0 ] && STATUS="failure"

  # Log run end as JSON
  cat <<EOF
{"event":"run_end","run_number":${RUN_NUMBER},"model":"${MODEL}","status":"${STATUS}","exit_code":${EXIT_CODE},"duration_seconds":${DURATION},"timestamp":"${END_TS}"}
EOF

  # Wait random interval before next run
  SLEEP_SECS=$(random_sleep)
  cat <<EOF
{"event":"sleep","run_number":${RUN_NUMBER},"sleep_seconds":${SLEEP_SECS},"next_run":$(( RUN_NUMBER + 1 ))}
EOF
  sleep "$SLEEP_SECS"
done
