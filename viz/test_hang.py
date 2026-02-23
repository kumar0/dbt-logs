import os
import sys
import logging
from datetime import datetime, timedelta, timezone

# Set up logging to console
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(name)s - %(message)s')

os.environ["DBT_LOG_GROUP"] = "EtlComputeStack-DbtTaskDefinitionDbtContainerLogGroupE420E81B-W7fZGqD3w8jD"
os.environ["AWS_PROFILE"] = "mondayskills.development"

from data_provider import fetch_dbt_run_logs, fetch_glue_job_metrics

def main():
    print("Testing fetch bounds...")
    now = datetime.now(timezone.utc)
    start_iso = (now - timedelta(hours=3)).isoformat()
    end_iso = now.isoformat()

    print(f"Start: {start_iso}, End: {end_iso}")
    
    print("\n--- Calling fetch_dbt_run_logs ---")
    try:
        dbt_df = fetch_dbt_run_logs(
            start_time=start_iso,
            end_time=end_iso,
            fetch_mode="full",
            since=None,
            prefer_realtime=False
        )
        print(f"fetch_dbt_run_logs completed. Rows: {len(dbt_df)}")
    except Exception as e:
        print(f"fetch_dbt_run_logs failed: {e}")

    print("\n--- Calling fetch_glue_job_metrics ---")
    try:
        glue_df = fetch_glue_job_metrics(
            start_time=start_iso,
            end_time=end_iso,
            fetch_mode="full"
        )
        print(f"fetch_glue_job_metrics completed. Rows: {len(glue_df)}")
    except Exception as e:
        print(f"fetch_glue_job_metrics failed: {e}")

if __name__ == "__main__":
    main()
