# dbt Commands Reference

## Prerequisites

Before running any dbt commands, ensure:

1. **AWS credentials are active:**

   ```bash
   aws sso login --profile mondayskills.development
   ```

2. **Environment variables are set:**

   ```bash
   export AWS_PROFILE=mondayskills.development
   export AWS_DEFAULT_REGION=us-east-1
   export AWS_REGION=us-east-1
   ```

3. **dbt packages are installed:**
   ```bash
   cd etl
   dbt deps
   ```

## Important Notes

- **First run takes 3-5 minutes** - AWS Glue needs to provision an interactive session
- **Session timeout is 10 minutes** - If command hangs longer, there's an issue
- **Sessions are reused** - Subsequent runs will be faster

---

## Core dbt Commands

### Test Connection

```bash
dbt debug
```

Validates your connection to AWS Glue and checks configuration.

---

### Run All Models

```bash
# First run - full refresh to initialize all tables
dbt run --full-refresh

# Subsequent runs - incremental updates
dbt run
```

---

### Run Specific Models

```bash
# Run a single model
dbt run --select dim_customers

# Run another single model
dbt run --select dim_products

# Run multiple specific models
dbt run --select dim_customers dim_products
```

---

### Run by Layer

```bash
# Run all staging models
dbt run --select staging

# Run all dimension models
dbt run --select marts.dimensions

# Run all fact models
dbt run --select marts.facts

# Run all models in marts folder
dbt run --select marts
```

---

### Run with Dependencies

```bash
# Run a model and all downstream dependencies
dbt run --select dim_customers+

# Run a model and all upstream dependencies
dbt run --select +fact_orders

# Run a model with both upstream and downstream
dbt run --select +dim_customers+
```

---

### Run by Pattern

```bash
# Run all staging models (pattern matching)
dbt run --select stg_*

# Run all dimension models (pattern matching)
dbt run --select dim_*

# Run all fact models (pattern matching)
dbt run --select fact_*
```

---

## Testing Commands

```bash
# Run all tests
dbt test

# Test specific model
dbt test --select dim_customers

# Test all dimension models
dbt test --select marts.dimensions
```

---

## Compilation Commands

```bash
# Compile all models without running
dbt compile

# Compile specific model
dbt compile --select dim_customers

# View compiled SQL in: target/compiled/etl_pipeline/models/
```

---

## Documentation Commands

```bash
# Generate documentation
dbt docs generate

# Serve documentation locally (opens browser)
dbt docs serve
```

---

## Utility Commands

```bash
# List all models
dbt list

# List specific selection
dbt list --select marts.dimensions

# Show model dependencies
dbt list --select +fact_orders --output json

# Clean generated files
dbt clean
```

---

## Recommended Workflow

### Initial Setup

```bash
# 1. Set environment
export AWS_PROFILE=mondayskills.development
export AWS_DEFAULT_REGION=us-east-1

# 2. Test connection
dbt debug

# 3. Install packages
dbt deps

# 4. Run full refresh
dbt run --full-refresh

# 5. Run tests
dbt test
```

### Daily Development

```bash
# 1. Run dimensions first
dbt run --select marts.dimensions

# 2. Then run facts
dbt run --select marts.facts

# 3. Test everything
dbt test
```

### Working on Specific Model

```bash
# 1. Compile to check SQL
dbt compile --select dim_customers

# 2. Run the model
dbt run --select dim_customers

# 3. Test the model
dbt test --select dim_customers
```

---

## Troubleshooting

### If dbt commands hang:

1. **Check AWS credentials:**

   ```bash
   aws sts get-caller-identity --profile mondayskills.development
   ```

2. **Check Glue sessions:**

   ```bash
   aws glue list-sessions --profile mondayskills.development
   ```

3. **Stop hanging session:**

   ```bash
   aws glue delete-session --id dbt-glue --profile mondayskills.development
   ```

4. **Verify environment variables:**
   ```bash
   echo $AWS_PROFILE
   echo $AWS_REGION
   ```

### If models fail:

1. **Check compiled SQL:**

   ```bash
   dbt compile --select <model_name>
   # Check: target/compiled/etl_pipeline/models/
   ```

2. **Run with debug:**

   ```bash
   dbt run --select <model_name> --debug
   ```

3. **Check logs:**
   ```bash
   # Logs are in: logs/dbt.log
   tail -f logs/dbt.log
   ```

---

## Model Execution Order

For proper data flow, run models in this order:

```bash
# 1. Staging (views - fast)
dbt run --select staging

# 2. Dimensions (SCD Type 2 - slower)
dbt run --select dim_customers
dbt run --select dim_products

# 3. Facts (depends on dimensions)
dbt run --select fact_orders
dbt run --select fact_order_items
```

Or run all at once (dbt handles dependencies):

```bash
dbt run
```

---

## Performance Tips

- Use `--select` to run only what you need
- Use incremental runs instead of `--full-refresh` after initial load
- Dimensions take longer due to SCD Type 2 logic
- Facts are faster as they're append-only
- First run of the day takes longer (session provisioning)
- Subsequent runs reuse the session and are faster
