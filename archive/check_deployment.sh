#!/bin/bash

# Script to verify CDK deployment and dbt configuration

set -e

AWS_PROFILE="mondayskills.development"
STACK_NAME="EtlDatabaseStack"

echo "=== Checking CDK Stack Deployment ==="
echo ""

# Check if stack exists
STACK_STATUS=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --profile $AWS_PROFILE \
  --query "Stacks[0].StackStatus" \
  --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$STACK_STATUS" = "NOT_FOUND" ]; then
  echo "❌ Stack '$STACK_NAME' not found"
  echo "   Deploy it with: cd iac && cdk deploy --profile $AWS_PROFILE"
  exit 1
elif [ "$STACK_STATUS" = "CREATE_COMPLETE" ] || [ "$STACK_STATUS" = "UPDATE_COMPLETE" ]; then
  echo "✅ Stack Status: $STACK_STATUS"
else
  echo "⚠️  Stack Status: $STACK_STATUS"
fi

echo ""
echo "=== Stack Outputs ==="
echo ""

# Get all outputs
aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --profile $AWS_PROFILE \
  --query "Stacks[0].Outputs[*].[OutputKey,OutputValue]" \
  --output table

echo ""
echo "=== Checking Glue Databases ==="
echo ""

# Check source database
SOURCE_DB=$(aws glue get-database \
  --name etl_source_db \
  --profile $AWS_PROFILE \
  --query "Database.Name" \
  --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$SOURCE_DB" = "etl_source_db" ]; then
  echo "✅ Source Database: etl_source_db"
  
  # Count tables
  SOURCE_TABLES=$(aws glue get-tables \
    --database-name etl_source_db \
    --profile $AWS_PROFILE \
    --query "length(TableList)" \
    --output text)
  echo "   Tables: $SOURCE_TABLES"
else
  echo "❌ Source Database: NOT FOUND"
fi

# Check destination database
DEST_DB=$(aws glue get-database \
  --name etl_dest_db \
  --profile $AWS_PROFILE \
  --query "Database.Name" \
  --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$DEST_DB" = "etl_dest_db" ]; then
  echo "✅ Destination Database: etl_dest_db"
  
  # Count tables
  DEST_TABLES=$(aws glue get-tables \
    --database-name etl_dest_db \
    --profile $AWS_PROFILE \
    --query "length(TableList)" \
    --output text)
  echo "   Tables: $DEST_TABLES"
else
  echo "❌ Destination Database: NOT FOUND"
fi

echo ""
echo "=== Checking S3 Buckets ==="
echo ""

# Get bucket name from stack
BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --profile $AWS_PROFILE \
  --query "Stacks[0].Outputs[?OutputKey=='DataLakeBucketName'].OutputValue" \
  --output text)

if [ -n "$BUCKET_NAME" ]; then
  BUCKET_EXISTS=$(aws s3 ls s3://$BUCKET_NAME --profile $AWS_PROFILE 2>/dev/null && echo "YES" || echo "NO")
  
  if [ "$BUCKET_EXISTS" = "YES" ]; then
    echo "✅ Data Lake Bucket: $BUCKET_NAME"
  else
    echo "❌ Data Lake Bucket: $BUCKET_NAME (not accessible)"
  fi
else
  echo "❌ Data Lake Bucket: NOT FOUND in stack outputs"
fi

echo ""
echo "=== Environment Variables ==="
echo ""

if [ -n "$DBT_GLUE_ROLE_ARN" ]; then
  echo "✅ DBT_GLUE_ROLE_ARN: $DBT_GLUE_ROLE_ARN"
else
  echo "❌ DBT_GLUE_ROLE_ARN: NOT SET"
  echo "   Run: source setup_env.sh"
fi

if [ -n "$DBT_GLUE_LOCATION" ]; then
  echo "✅ DBT_GLUE_LOCATION: $DBT_GLUE_LOCATION"
else
  echo "❌ DBT_GLUE_LOCATION: NOT SET"
  echo "   Run: source setup_env.sh"
fi

if [ -n "$AWS_REGION" ]; then
  echo "✅ AWS_REGION: $AWS_REGION"
else
  echo "❌ AWS_REGION: NOT SET"
fi

echo ""
echo "=== dbt Installation ==="
echo ""

if command -v dbt &> /dev/null; then
  DBT_VERSION=$(dbt --version 2>&1 | head -n 1)
  echo "✅ dbt installed: $DBT_VERSION"
else
  echo "❌ dbt not installed"
  echo "   Run: pip install -r requirements.txt"
fi

echo ""
echo "=== Summary ==="
echo ""
echo "Next steps:"
echo "1. If stack not deployed: cd iac && cdk deploy --profile $AWS_PROFILE"
echo "2. Set environment variables: source setup_env.sh"
echo "3. Install dbt packages: dbt deps"
echo "4. Load sample data: cd ../iac/scripts && python populate_source_data.py"
echo "5. Run dbt pipeline: dbt run --full-refresh"
