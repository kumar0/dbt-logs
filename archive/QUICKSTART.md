# dbt ETL Pipeline - Quick Start Guide

## Prerequisites

- AWS CLI configured with profile `mondayskills.development`
- Python 3.8+
- Node.js and npm (for CDK)

## Step-by-Step Deployment

### 1. Deploy Infrastructure

```bash
cd iac
npm install
cdk deploy --profile mondayskills.development
```

**Note the outputs:**

- GlueJobRoleArn
- DataLakeLocation
- DataLakeBucketName

### 2. Setup dbt Environment

```bash
cd ../etl

# Install Python dependencies
pip install -r requirements.txt

# Set environment variables from CDK outputs
source setup_env.sh

# Install dbt packages
dbt deps
```

### 3. Load Sample Data (Optional)

```bash
cd ../iac/scripts
pip install -r requirements.txt
python populate_source_data.py
```

### 4. Run dbt Pipeline

```bash
cd ../../etl

# Full refresh (first run)
dbt run --full-refresh

# Incremental runs (subsequent runs)
dbt run

# Run tests
dbt test
```

## Verify Results

### Check Glue Catalog

```bash
aws glue get-tables \
  --database-name etl_dest_db \
  --profile mondayskills.development
```

### Query with Athena

```sql
-- Check current customers
SELECT * FROM etl_dest_db.dim_customers
WHERE is_current = 'Y'
LIMIT 10;

-- Check orders with customer info
SELECT
    c.first_name,
    c.last_name,
    o.order_date,
    o.total_amount
FROM etl_dest_db.fact_orders o
JOIN etl_dest_db.dim_customers c ON o.customer_sk = c.customer_sk
WHERE c.is_current = 'Y'
LIMIT 10;
```

## Common Commands

```bash
# Run specific model
dbt run --select dim_customers

# Run dimensions only
dbt run --select marts.dimensions

# Run facts only
dbt run --select marts.facts

# Compile without running
dbt compile

# Generate documentation
dbt docs generate
dbt docs serve

# Debug connection
dbt debug
```

## Troubleshooting

### Issue: Role ARN not found

**Solution:** Ensure CDK stack is deployed and environment variables are set:

```bash
source setup_env.sh
echo $DBT_GLUE_ROLE_ARN
```

### Issue: S3 access denied

**Solution:** Verify the Glue role has permissions to the data lake bucket:

```bash
aws iam get-role \
  --role-name etl-glue-job-role-us-east-1 \
  --profile mondayskills.development
```

### Issue: Table not found

**Solution:** Check if source tables exist in Glue catalog:

```bash
aws glue get-table \
  --database-name etl_source_db \
  --name customers \
  --profile mondayskills.development
```

## Architecture

```
Source System → etl_source_db (Glue) → dbt Models → etl_dest_db (Glue)
                      ↓                                    ↓
                S3 Data Lake                         S3 Data Lake
                (Iceberg/Parquet)                    (Iceberg/Parquet)
```

## Data Flow

1. **Staging Layer**: Views reading from `etl_source_db` tables
2. **Dimension Layer**: SCD Type 2 dimensions in `etl_dest_db`
   - dim_customers
   - dim_products
3. **Fact Layer**: Fact tables in `etl_dest_db`
   - fact_orders
   - fact_order_items

## Next Steps

- Schedule dbt runs using AWS Glue Jobs or Step Functions
- Add data quality tests in `tests/` directory
- Create custom macros for common transformations
- Set up CI/CD pipeline for dbt deployments
