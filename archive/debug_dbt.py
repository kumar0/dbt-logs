import sys
print("Before import dbt...", flush=True)
from dbt.cli.main import cli
print("After import dbt...", flush=True)

if __name__ == '__main__':
    try:
        sys.exit(cli())
    except Exception as e:
        print(f"Exception occurred: {e}")
        raise
