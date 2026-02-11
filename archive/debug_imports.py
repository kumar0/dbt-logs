import sys
print("Importing boto3...", flush=True)
try:
    import boto3
    print("Imported boto3", flush=True)
except ImportError:
    print("boto3 not found", flush=True)

print("Importing dbt...", flush=True)
import dbt
print("Importing dbt.adapters...", flush=True)
import dbt.adapters
print("Importing dbt.adapters.glue...", flush=True)
try:
    import dbt.adapters.glue
    print("Imported dbt.adapters.glue", flush=True)
except ImportError:
    print("dbt.adapters.glue not found", flush=True)

print("Done", flush=True)
