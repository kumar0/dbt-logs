#!/bin/bash
# Wrapper script for dbt commands with proper AWS profile

export AWS_PROFILE=mondayskills.development
export DBT_PROFILES_DIR="$(dirname "$0")"

echo "Using AWS Profile: $AWS_PROFILE"
echo "DBT Profiles Dir: $DBT_PROFILES_DIR"
echo ""

# Run dbt command
dbt "$@"
