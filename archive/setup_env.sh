#!/bin/bash

# Setup script for dbt environment variables
# This script retrieves values from CDK stack outputs

set -e

AWS_PROFILE="mondayskills.development"
STACK_NAME="EtlDatabaseStack"

echo "Fetching CDK stack outputs for profile: $AWS_PROFILE"

# Get stack outputs
ROLE_ARN=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --profile $AWS_PROFILE \
  --query "Stacks[0].Outputs[?OutputKey=='GlueJobRoleArn'].OutputValue" \
  --output text)

DATA_LAKE_LOCATION=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --profile $AWS_PROFILE \
  --query "Stacks[0].Outputs[?OutputKey=='DataLakeLocation'].OutputValue" \
  --output text)

AWS_REGION=$(aws configure get region --profile $AWS_PROFILE)

if [ -z "$AWS_REGION" ]; then
  AWS_REGION="us-east-1"
fi

# Export environment variables
export DBT_GLUE_ROLE_ARN="$ROLE_ARN"
export DBT_GLUE_LOCATION="$DATA_LAKE_LOCATION"
export AWS_REGION="$AWS_REGION"
export AWS_PROFILE="$AWS_PROFILE"

echo ""
echo "Environment variables set:"
echo "  DBT_GLUE_ROLE_ARN=$DBT_GLUE_ROLE_ARN"
echo "  DBT_GLUE_LOCATION=$DBT_GLUE_LOCATION"
echo "  AWS_REGION=$AWS_REGION"
echo "  AWS_PROFILE=$AWS_PROFILE"
echo ""
echo "To use these in your current shell, run:"
echo "  source setup_env.sh"
