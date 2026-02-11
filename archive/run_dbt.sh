#!/bin/bash

# Script to run dbt with proper AWS credentials

set -e

# Set AWS profile
export AWS_PROFILE=mondayskills.development

# Check if SSO session is valid
echo "Checking AWS credentials..."
if ! aws sts get-caller-identity --profile $AWS_PROFILE &> /dev/null; then
    echo "AWS SSO session expired. Logging in..."
    aws sso login --profile $AWS_PROFILE
fi

echo "AWS credentials valid ✓"
echo ""

# Export AWS credentials as environment variables for dbt-glue
echo "Setting up environment for dbt-glue..."
export AWS_DEFAULT_REGION=us-east-1
export AWS_REGION=us-east-1

# Run dbt command
if [ $# -eq 0 ]; then
    echo "Usage: ./run_dbt.sh <dbt-command>"
    echo "Examples:"
    echo "  ./run_dbt.sh debug"
    echo "  ./run_dbt.sh run"
    echo "  ./run_dbt.sh run --select dim_customers"
    exit 1
fi

echo "Running: dbt $@"
echo "This may take 3-5 minutes on first run (Glue session provisioning)..."
echo ""

dbt "$@"
