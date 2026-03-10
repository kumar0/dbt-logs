#!/bin/bash
set -euo pipefail

# ============================================================================
# Trigger Test Executions for SFN Test Harness
#
# Usage:
#   ./iac/scripts/trigger-test-executions.sh [--count N] [--state-machine-name NAME]
#
# Defaults:
#   --count 10
#   --state-machine-name raw-to-base-test-eu-west-1
#
# Starts N Step Functions executions with randomized parameters:
#   - sleepSeconds: random 1-120
#   - shouldFail: ~30% chance of true
#   - errorType: random from 5 types
#   - entityName: random from 6 entities
#   - runDate: random recent date (ddmmyyyy)
# ============================================================================

# --- Defaults ---
COUNT=10
STATE_MACHINE_NAME="raw-to-base-test-eu-west-1"
PROFILE="mondayskills.development"

# --- Argument Parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --count)
      COUNT="$2"
      shift 2
      ;;
    --state-machine-name)
      STATE_MACHINE_NAME="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1"
      echo "Usage: $0 [--count N] [--state-machine-name NAME]"
      exit 1
      ;;
  esac
done

# --- AWS CLI Availability Check ---
if ! command -v aws &> /dev/null; then
  echo "Error: AWS CLI is not installed or not in PATH."
  echo "Install it from https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
  exit 1
fi

# --- Resolve AWS Region and Account ---
REGION=$(aws configure get region --profile="${PROFILE}" 2>/dev/null || echo "us-east-1")
ACCOUNT_ID=$(aws sts get-caller-identity --profile="${PROFILE}" --query 'Account' --output text 2>&1)
if [[ $? -ne 0 || -z "$ACCOUNT_ID" ]]; then
  echo "Error: Failed to resolve AWS account ID. Check your profile '${PROFILE}'."
  echo "$ACCOUNT_ID"
  exit 1
fi
STATE_MACHINE_ARN="arn:aws:states:${REGION}:${ACCOUNT_ID}:stateMachine:${STATE_MACHINE_NAME}"

# --- Constants ---
ERROR_TYPES=("TaskError" "TimeoutError" "ValidationError" "DataError" "ConnectionError")
ENTITY_NAMES=("customers" "orders" "products" "invoices" "payments" "shipments")

# --- Helper: Generate error message matching the error type ---
generate_error_message() {
  local error_type="$1"
  local entity="$2"
  local sleep_secs="$3"

  case "$error_type" in
    TaskError)
      echo "dbt ECS task failed for entity ${entity}"
      ;;
    TimeoutError)
      echo "Task timed out after ${sleep_secs}s"
      ;;
    ValidationError)
      echo "Schema validation failed for ${entity}"
      ;;
    DataError)
      echo "Missing required column in source data for ${entity}"
      ;;
    ConnectionError)
      echo "Failed to connect to Glue session for ${entity}"
      ;;
    *)
      echo "Unknown error occurred"
      ;;
  esac
}

# --- Helper: Generate a random recent date in ddmmyyyy format ---
generate_run_date() {
  local days_ago=$(( RANDOM % 14 ))
  if date --version &> /dev/null 2>&1; then
    # GNU date (Linux)
    date -d "-${days_ago} days" +"%d%m%Y"
  else
    # BSD date (macOS)
    date -v "-${days_ago}d" +"%d%m%Y"
  fi
}

# --- Helper: Generate a unique execution name ---
generate_execution_name() {
  local index="$1"
  local uuid
  if command -v uuidgen &> /dev/null; then
    uuid=$(uuidgen | tr '[:upper:]' '[:lower:]')
  elif [[ -f /proc/sys/kernel/random/uuid ]]; then
    uuid=$(cat /proc/sys/kernel/random/uuid)
  else
    uuid=$(date +%s%N)-${RANDOM}-${index}
  fi
  echo "test-exec-${uuid}"
}

# --- Main Execution Loop ---
echo "Starting ${COUNT} test executions against state machine: ${STATE_MACHINE_NAME}"
echo "Using AWS profile: ${PROFILE} (region: ${REGION})"
echo "State machine ARN: ${STATE_MACHINE_ARN}"
echo "---"

FAILED_COUNT=0
STARTED_COUNT=0
CONFIGURED_TO_FAIL=0
MIN_SLEEP=120
MAX_SLEEP=1

for (( i=1; i<=COUNT; i++ )); do
  # Random sleepSeconds (1-120)
  sleep_secs=$(( (RANDOM % 120) + 1 ))

  # Track sleep range
  if (( sleep_secs < MIN_SLEEP )); then MIN_SLEEP=$sleep_secs; fi
  if (( sleep_secs > MAX_SLEEP )); then MAX_SLEEP=$sleep_secs; fi

  # ~30% chance of shouldFail=true
  fail_roll=$(( RANDOM % 100 ))
  if (( fail_roll < 30 )); then
    should_fail=true
    CONFIGURED_TO_FAIL=$(( CONFIGURED_TO_FAIL + 1 ))
  else
    should_fail=false
  fi

  # Random errorType and entityName
  error_type="${ERROR_TYPES[$(( RANDOM % ${#ERROR_TYPES[@]} ))]}"
  entity_name="${ENTITY_NAMES[$(( RANDOM % ${#ENTITY_NAMES[@]} ))]}"

  # Generate error message
  error_message=$(generate_error_message "$error_type" "$entity_name" "$sleep_secs")

  # Generate run date
  run_date=$(generate_run_date)

  # Generate unique execution name
  exec_name=$(generate_execution_name "$i")

  # Build JSON input
  input_json=$(cat <<EOF
{"sleepSeconds":${sleep_secs},"shouldFail":${should_fail},"errorType":"${error_type}","errorMessage":"${error_message}","entityName":"${entity_name}","runDate":"${run_date}"}
EOF
)

  # Start execution
  echo "[${i}/${COUNT}] Starting execution: ${exec_name} (sleep=${sleep_secs}s, fail=${should_fail}, entity=${entity_name})"

  if aws stepfunctions start-execution \
    --profile="${PROFILE}" \
    --state-machine-arn "${STATE_MACHINE_ARN}" \
    --name "${exec_name}" \
    --input "${input_json}" > /dev/null 2>&1; then
    STARTED_COUNT=$(( STARTED_COUNT + 1 ))
  else
    echo "  ERROR: Failed to start execution ${exec_name}"
    FAILED_COUNT=$(( FAILED_COUNT + 1 ))
  fi
done

# --- Summary ---
echo ""
echo "=== Execution Summary ==="
echo "Total started:        ${STARTED_COUNT}/${COUNT}"
echo "Configured to fail:   ${CONFIGURED_TO_FAIL}"
echo "Sleep range:          ${MIN_SLEEP}s - ${MAX_SLEEP}s"

if (( FAILED_COUNT > 0 )); then
  echo "Failed to start:      ${FAILED_COUNT}"
  exit 1
fi

echo "All executions started successfully."
