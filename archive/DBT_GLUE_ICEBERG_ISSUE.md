# DBT Glue + Iceberg Compatibility Issue

## Problem Summary

The `dbt run` command fails with the error:

```
Column 'customer_id' does not exist. Did you mean one of the following? []
HiveTableRelation [`etl_source_db`.`customers`, org.apache.iceberg.mr.hive.HiveIcebergSerDe, Data Cols: [], Partition Cols: []]
```

## Root Cause

AWS Glue Interactive Sessions with `--datalake-formats=iceberg` flag is not properly loading Iceberg table schemas. The tables are being read as Hive tables with empty column lists (`Data Cols: []`), even though:

1. The Glue Catalog shows the correct schema
2. Athena can query the tables successfully
3. The Iceberg metadata files exist in S3

The issue is that Spark in Glue Interactive Sessions falls back to `HiveTableRelation` instead of using the Iceberg reader, resulting in an empty schema.

## Attempted Fixes

1. ✗ Removed `database` field from profiles.yml
2. ✗ Added Iceberg Spark catalog configuration
3. ✗ Used `glue_catalog` prefix in table references
4. ✗ Simplified to just `--datalake-formats=iceberg`

All attempts result in either:

- `ClassNotFoundException: org.apache.iceberg.spark.SparkCatalog` (when using catalog config)
- Empty schema with `HiveTableRelation` (when using default config)

## Recommended Solutions

### Option 1: Use dbt-athena Instead (Recommended)

Switch from `dbt-glue` to `dbt-athena` adapter, which has better Iceberg support:

```yaml
# profiles.yml
etl_pipeline:
  target: dev
  outputs:
    dev:
      type: athena
      s3_staging_dir: s3://etl-datalake-777334699019-us-east-1/athena-results/
      region_name: us-east-1
      database: etl_dest_db
      schema: etl_dest_db
      work_group: primary
      aws_profile_name: mondayskills.development
```

### Option 2: Use Table Refresh Pre-Hook

Add a pre-hook to refresh Iceberg table metadata before querying:

```sql
-- models/staging/stg_customers.sql
{{ config(
    materialized='view',
    pre_hook="REFRESH TABLE {{ source('etl_source', 'customers') }}"
) }}

select * from {{ source('etl_source', 'customers') }}
```

### Option 3: Use Glue ETL Jobs Instead of Interactive Sessions

Run dbt through Glue ETL Jobs which have better Iceberg support, but this requires custom deployment setup.

## Current Status

- **profiles.yml**: Configured with minimal `--datalake-formats=iceberg`
- **Issue**: Unresolved - Glue Interactive Sessions cannot read Iceberg table schemas
- **Workaround Needed**: Switch to dbt-athena or add refresh pre-hooks

## References

- [dbt-glue Iceberg Support](https://github.com/aws-samples/dbt-glue)
- [AWS Glue Iceberg Documentation](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-etl-format-iceberg.html)
- [dbt-athena Adapter](https://github.com/dbt-athena/dbt-athena)
