#!/bin/bash

# Quick test script for dbt-glue

export AWS_PROFILE=mondayskills.development
export AWS_DEFAULT_REGION=us-east-1
export AWS_REGION=us-east-1

echo "Testing dbt connection..."
echo "This will take 3-5 minutes on first run (provisioning Glue session)"
echo ""
echo "Press Ctrl+C to cancel if it hangs"
echo ""

# Run with timeout
timeout 600 dbt debug

if [ $? -eq 124 ]; then
    echo ""
    echo "Command timed out after 10 minutes"
    echo "This usually means:"
    echo "1. Glue session is taking too long to provision"
    echo "2. Network/firewall issues"
    echo "3. IAM permission issues"
fi
