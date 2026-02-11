#!/usr/bin/env bash
set -euo pipefail

# Default dbt command if none provided
DBT_COMMAND="${DBT_COMMAND:-build}"

echo "Running: dbt ${DBT_COMMAND} --log-format json --profiles-dir /dbt"
exec dbt ${DBT_COMMAND} --log-format json --profiles-dir /dbt
