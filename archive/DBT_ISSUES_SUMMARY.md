# DBT Issues Summary

## Issues Found and Fixed

### 1. ✅ Glue Session Configuration Error (FIXED)

**Problem:** The `--conf` parameter in `profiles.yml` had duplicate `--enable-glue-datacatalog` flag causing session creation to fail.

**Error Message:**

```
LAUNCH ERROR | Invalid input to --confPlease refer logs for details.
```

**Solution:** Removed the duplicate flag from the `conf` parameter in `etl/profiles.yml`:

```yaml
# Before:
conf: '--enable-glue-datacatalog=true --datalake-formats=iceberg'

# After:
conf: '--datalake-formats=iceberg'
```

### 2. ✅ AWS Credentials Not Found (FIXED)

**Problem:** dbt-glue wasn't picking up the AWS profile from `profiles.yml`.

**Solution:** Set the `AWS_PROFILE` environment variable when running dbt commands:

```bash
AWS_PROFILE=mondayskills.development dbt run --profiles-dir . --log-format json
```

### 3. ⚠️ Iceberg Table Schema Not Readable by Glue Sessions (CURRENT ISSUE)

**Problem:** Glue Interactive Sessions cannot read column schemas from Iceberg tables created via AWS Glue API.

**Error Message:**

```
AnalysisException: Column 'customer_id' does not exist. Did you mean one of the following? [];
HiveTableRelation [`etl_source_db`.`customers`, org.apache.iceberg.mr.hive.HiveIcebergSerDe, Data Cols: [], Partition Cols: []]
```

**Root Cause:**

- The Iceberg tables in `etl_source_db` were created using AWS Glue API
- The table metadata is stored in Iceberg metadata files (S3)
- Glue Catalog has the table registered but with empty column list in StorageDescriptor
- Glue Interactive Sessions with Spark expect columns to be explicitly listed in the Glue Catalog
- Athena can read these tables fine because it reads directly from Iceberg metadata files

**Verification:**

- ✅ Tables exist in Glue Catalog
- ✅ Data exists in S3 (Parquet files)
- ✅ Athena can query the tables successfully
- ❌ Glue Interactive Sessions see "Data Cols: []"

## Current Status

### Working:

- ✅ Glue session creation and connection
- ✅ dbt project configuration
- ✅ AWS authentication
- ✅ Destination database schemas created (`etl_dest_db_staging`, `etl_dest_db_dest`)

### Not Working:

- ❌ Reading from source Iceberg tables (`etl_source_db.*`)
- ❌ Creating staging views
- ❌ Running dimension and fact models (skipped due to staging failures)

## Possible Solutions

### Option 1: Recreate Tables with Proper Schema Registration

Recreate the Iceberg tables ensuring the Glue Catalog has the full column schema:

- Drop and recreate tables using Spark/Glue sessions
- Or update the Glue Catalog to include column definitions

### Option 2: Use Athena Instead of Glue Sessions

Switch dbt adapter from `dbt-glue` to `dbt-athena`:

- Athena reads Iceberg metadata correctly
- No Glue Interactive Session costs
- Simpler configuration

### Option 3: Fix Glue Catalog Metadata

Manually sync the Iceberg metadata to Glue Catalog:

- Read schema from Iceberg metadata files
- Update Glue Catalog StorageDescriptor with column definitions
- This is complex and error-prone

## Recommended Next Steps

1. **Short-term:** Use Athena for querying (already verified working)
2. **Long-term:** Consider switching to `dbt-athena` adapter or recreating tables properly

## Files Modified

1. `etl/profiles.yml` - Fixed conf parameter
2. `etl/fix_source_tables.py` - Script to add InputFormat/OutputFormat (partial fix)
3. `.kiro/steering/cdk-project.md` - Added dbt logging requirement

## Commands to Run

```bash
# Run dbt with proper AWS profile
cd etl
AWS_PROFILE=mondayskills.development dbt run --profiles-dir . --log-format json

# Verify tables in Athena (working)
aws athena start-query-execution \
  --query-string "SELECT * FROM etl_source_db.customers LIMIT 5" \
  --result-configuration "OutputLocation=s3://etl-datalake-777334699019-us-east-1/athena-results/" \
  --profile mondayskills.development \
  --region us-east-1
```
