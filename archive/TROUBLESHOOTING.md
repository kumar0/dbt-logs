# dbt-glue Troubleshooting Guide

## Issue: dbt commands hanging

### Root Cause

dbt-glue uses AWS Glue Interactive Sessions which:

1. Take time to provision (2-5 minutes on first run)
2. Require proper IAM permissions
3. May timeout if AWS credentials expire (SSO sessions)

### Solutions

#### Option 1: Wait for Session Provisioning (Recommended for First Run)

The first `dbt debug` or `dbt run` can take 3-5 minutes as it provisions a Glue session.

```bash
# Set AWS profile
export AWS_PROFILE=mondayskills.development

# Ensure SSO session is active
aws sso login --profile mondayskills.development

# Run dbt with increased timeout
dbt debug --profiles-dir .
```

#### Option 2: Use Existing Glue Session

If you have an existing Glue session, specify it:

```bash
# List existing sessions
aws glue list-sessions --profile mondayskills.development

# Use specific session by setting session ID in profiles.yml
# Add to dev output:
#   session_id: 'your-session-id'
```

#### Option 3: Alternative - Use dbt-athena Instead

dbt-athena is simpler and doesn't require Glue sessions:

```bash
# Install dbt-athena
pip install dbt-athena-community

# Update profiles.yml to use athena adapter
```

**profiles.yml for Athena:**

```yaml
etl_pipeline:
  target: dev
  outputs:
    dev:
      type: athena
      s3_staging_dir: s3://etl-athena-results-777334699019-us-east-1/
      region_name: us-east-1
      database: etl_dest_db
      schema: etl_dest_db
      work_group: etl-workgroup
      num_retries: 3
```

## Common Issues

### 1. SSO Session Expired

**Symptom:** Commands hang or fail with authentication errors

**Solution:**

```bash
aws sso login --profile mondayskills.development
```

### 2. Glue Session Timeout

**Symptom:** Session provisioning takes too long

**Solution:** Increase timeout in profiles.yml:

```yaml
session_provisioning_timeout_in_seconds: 600  # 10 minutes
```

### 3. IAM Permission Issues

**Symptom:** Access denied errors

**Solution:** Verify role has permissions:

```bash
aws iam get-role-policy \
  --role-name etl-glue-job-role-us-east-1 \
  --policy-name GlueJobPolicy \
  --profile mondayskills.development
```

### 4. Check Active Sessions

```bash
# List all sessions
aws glue list-sessions --profile mondayskills.development

# Get session details
aws glue get-session \
  --id dbt-glue \
  --profile mondayskills.development

# Stop a hanging session
aws glue delete-session \
  --id dbt-glue \
  --profile mondayskills.development
```

## Recommended Workflow

### For Development (Fast Iteration)

Use **dbt-athena** for faster development:

1. Install: `pip install dbt-athena-community`
2. Use Athena profile configuration
3. Run models: `dbt run`

### For Production (Glue Jobs)

Use **dbt-glue** for production deployments:

1. Package dbt project
2. Deploy as Glue Job via CDK/CloudFormation
3. Schedule with EventBridge or Step Functions

## Debug Commands

```bash
# Check dbt version
dbt --version

# Validate profiles
dbt debug --profiles-dir .

# Compile without running
dbt compile --select dim_customers

# Check AWS credentials
aws sts get-caller-identity --profile mondayskills.development

# Test S3 access
aws s3 ls s3://etl-datalake-777334699019-us-east-1/ \
  --profile mondayskills.development
```

## Performance Tips

1. **Use smaller worker types for dev:** G.1X (1 DPU)
2. **Increase workers for prod:** 4-10 workers
3. **Set idle timeout:** Automatically stop sessions after inactivity
4. **Use incremental models:** Faster than full refresh

## Alternative: Run dbt via Glue Job (No Interactive Session)

Create a Glue Job that runs dbt:

```python
# glue_job_script.py
import sys
from awsglue.utils import getResolvedOptions
import subprocess

args = getResolvedOptions(sys.argv, ['dbt_command'])

# Run dbt command
result = subprocess.run(
    ['dbt', args['dbt_command']],
    capture_output=True,
    text=True
)

print(result.stdout)
if result.returncode != 0:
    raise Exception(f"dbt failed: {result.stderr}")
```

This avoids interactive session issues entirely.
