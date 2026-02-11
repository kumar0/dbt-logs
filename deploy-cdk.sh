#!/usr/bin/env bash
set -euo pipefail

#──────────────────────────────────────────────────────────
# deploy-cdk.sh — Deploy all CDK stacks
# Usage: ./deploy-cdk.sh
#──────────────────────────────────────────────────────────

AWS_PROFILE="mondayskills.development"
AWS_REGION="us-east-1"

echo "▸ Resolving AWS account..."
ACCOUNT_ID=$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query Account --output text)

echo "  Account : ${ACCOUNT_ID}"

#── 1. Deploy ECR stack first (so the repo exists) ────────
echo ""
echo "▸ Deploying ECR stack..."
cd iac
npx cdk deploy EtlEcrStack --profile "$AWS_PROFILE" --require-approval never

#── 2. Tear down Orchestration stack to release cross-stack refs ──
echo ""
echo "▸ Destroying EtlOrchestrationStack (to release cross-stack refs)..."
npx cdk destroy EtlOrchestrationStack --profile "$AWS_PROFILE" --force || true

#── 3. Deploy remaining CDK stacks in dependency order ────
echo ""
echo "▸ Deploying all CDK stacks..."
npx cdk deploy --all --profile "$AWS_PROFILE" --require-approval never
cd ..

echo ""
echo "✔ CDK deploy complete."
echo ""
echo "To trigger the pipeline:"
echo "  aws stepfunctions start-execution \\"
echo "    --state-machine-arn arn:aws:states:${AWS_REGION}:${ACCOUNT_ID}:stateMachine:etl-dbt-pipeline \\"
echo "    --input '{\"dbtCommand\": \"build\", \"numWorkers\": \"3\", \"workerType\": \"G.1X\", \"glueSessionId\": \"etl-dbt-session\"}' \\"
echo "    --profile ${AWS_PROFILE}"
