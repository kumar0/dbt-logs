# ETL Pipeline - dbt Project

This dbt project implements an ETL pipeline that loads data from source tables (`etl_source_db`) to destination tables (`etl_dest_db`) with dimensional modeling and SCD Type 2 for dimensions.

## Project Structure

```
etl/
├── models/
│   ├── staging/          # Staging views from source tables
│   │   ├── stg_customers.sql
│   │   ├── stg_products.sql
│   │   ├── stg_orders.sql
│   │   ├── stg_order_items.sql
│   │   ├── stg_payments.sql
│   │   └── sources.yml
│   └── marts/
│       ├── dimensions/   # SCD Type 2 dimension tables
│       │   ├── dim_customers.sql
│       │   └── dim_products.sql
│       └── facts/        # Fact tables
│           ├── fact_orders.sql
│           └── fact_order_items.sql
├── dbt_project.yml
├── profiles.yml
├── packages.yml
└── requirements.txt
```

## Setup

### 1. Deploy CDK Infrastructure

First, deploy the CDK stack to create the necessary AWS resources:

```bash
cd iac
npm install
cdk deploy --profile mondayskills.development
```

This will create:

- S3 bucket for data lake: `etl-datalake-{account}-{region}`
- Glue databases: `etl_source_db` and `etl_dest_db`
- IAM role for Glue jobs: `etl-glue-job-role-{region}`
- Athena workgroup for queries

### 2. Install dbt Dependencies

```bash
cd etl
pip install -r requirements.txt
```

### 3. Configure Environment Variables

**Option A: Use the setup script (recommended)**

```bash
source setup_env.sh
```

This automatically retrieves values from the deployed CDK stack.

**Option B: Manual configuration**

Copy the example file and fill in values from CDK outputs:

```bash
cp .env.example .env
# Edit .env with values from: cdk deploy output or AWS Console
```

Required environment variables:

- `DBT_GLUE_ROLE_ARN`: IAM role ARN (from CDK output: GlueJobRoleArn)
- `DBT_GLUE_LOCATION`: S3 path (from CDK output: DataLakeLocation)
- `AWS_REGION`: AWS region (e.g., us-east-1)
- `AWS_PROFILE`: mondayskills.development

### 4. Install dbt Packages

```bash
dbt deps
```

### 5. Populate Source Data (Optional)

Load sample data into source tables:

```bash
cd ../iac/scripts
pip install -r requirements.txt
python populate_source_data.py
```

## Running the Pipeline

### Full Refresh (Initial Load)

```bash
dbt run --full-refresh
```

### Incremental Load

```bash
dbt run
```

### Run Specific Models

```bash
# Run only dimensions
dbt run --select marts.dimensions

# Run only facts
dbt run --select marts.facts

# Run specific model
dbt run --select dim_customers
```

### Run Tests

```bash
dbt test
```

## Data Flow

1. **Staging Layer**: Views that read directly from source tables in `etl_source_db`
2. **Dimension Layer**: SCD Type 2 implementation for slowly changing dimensions
   - `dim_customers`: Customer dimension with history
   - `dim_products`: Product dimension with history
3. **Fact Layer**: Fact tables with surrogate key joins
   - `fact_orders`: Order-level facts
   - `fact_order_items`: Order item-level facts

## SCD Type 2 Logic

The dimension models implement SCD Type 2 with:

- **Surrogate Keys**: Generated using hash of natural key + timestamp
- **Effective Date**: When the record became active
- **End Date**: When the record was superseded (NULL for current)
- **is_current**: Flag ('Y' or 'N') for current records
- **Partitioning**: By `is_current` for query optimization

### How It Works

On incremental runs:

1. Detect changed records by comparing source with current dimension records
2. Expire old records by setting `end_date` and `is_current = 'N'`
3. Insert new records with `effective_date = current_date` and `is_current = 'Y'`
4. Insert completely new records (not previously in dimension)

## Querying the Data

### Get Current Customer Record

```sql
SELECT * FROM etl_dest_db.dim_customers
WHERE customer_id = 'CUST-12345' AND is_current = 'Y'
```

### Get Customer History

```sql
SELECT * FROM etl_dest_db.dim_customers
WHERE customer_id = 'CUST-12345'
ORDER BY effective_date DESC
```

### Order Analysis with Dimensions

```sql
SELECT
    c.first_name,
    c.last_name,
    o.order_date,
    o.total_amount,
    o.total_items
FROM etl_dest_db.fact_orders o
JOIN etl_dest_db.dim_customers c ON o.customer_sk = c.customer_sk
WHERE c.is_current = 'Y'
```

## Troubleshooting

### Check Model Status

```bash
dbt run --select <model_name> --debug
```

### Compile SQL Without Running

```bash
dbt compile
```

### View Compiled SQL

Check `target/compiled/etl_pipeline/models/` for compiled SQL files.
