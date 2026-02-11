#!/usr/bin/env bash
set -euo pipefail

DBT_COMMAND="${DBT_COMMAND:-build}"
# Strip leading "dbt " if caller passed the full command (e.g. "dbt build")
DBT_COMMAND="${DBT_COMMAND#dbt }"

echo "{\"event\":\"container_start\",\"dbt_command\":\"${DBT_COMMAND}\",\"region\":\"${AWS_DEFAULT_REGION:-us-east-1}\",\"workers\":${NUM_WORKERS:-3},\"worker_type\":\"${WORKER_TYPE:-G.1X}\",\"glue_session_id\":\"${GLUE_SESSION_ID:-}\"}"

exec_result=0
dbt ${DBT_COMMAND} --log-format json --profiles-dir /dbt || exec_result=$?

echo "Publishing CloudWatch metrics..."
python /dbt/publish_metrics.py

exit $exec_result
