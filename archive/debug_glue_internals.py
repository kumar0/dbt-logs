print("Credentials...", flush=True)
try:
    from dbt.adapters.glue.credentials import GlueCredentials
    print("Imported Credentials", flush=True)
except Exception as e:
    print(f"Error importing Credentials: {e}", flush=True)

print("Connections...", flush=True)
try:
    from dbt.adapters.glue.connections import GlueConnectionManager
    print("Imported Connections", flush=True)
except Exception as e:
    print(f"Error importing Connections: {e}", flush=True)

print("Impl...", flush=True)
try:
    from dbt.adapters.glue.impl import GlueAdapter
    print("Imported Impl", flush=True)
except Exception as e:
    print(f"Error importing Impl: {e}", flush=True)
