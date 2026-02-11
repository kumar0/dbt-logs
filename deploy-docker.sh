#!/usr/bin/env bash
set -euo pipefail

#──────────────────────────────────────────────────────────
# deploy-docker.sh — Build dbt image and push to ECR
# Usage: ./deploy-docker.sh
#──────────────────────────────────────────────────────────

AWS_PROFILE="mondayskills.development"
AWS_REGION="us-east-1"
ECR_REPO_NAME="etl-dbt"

echo "▸ Resolving AWS account..."
ACCOUNT_ID=$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query Account --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}"

echo "  Account : ${ACCOUNT_ID}"
echo "  ECR URI : ${ECR_URI}"

#── 1. Docker build (linux/amd64 for Fargate) ─────────────
echo ""
echo "▸ Building Docker image for linux/amd64..."
docker build --platform linux/amd64 -t "${ECR_REPO_NAME}:latest" etl/

#── 2. ECR login & push ───────────────────────────────────
echo ""
echo "▸ Logging into ECR..."
aws ecr get-login-password --region "$AWS_REGION" --profile "$AWS_PROFILE" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "▸ Tagging and pushing image..."
docker tag "${ECR_REPO_NAME}:latest" "${ECR_URI}:latest"
docker push "${ECR_URI}:latest"

echo ""
echo "✔ Docker image pushed to ECR."
