import boto3
import os
import time
from datetime import datetime, timedelta, timezone
from extract_dbt_logs import run_filter_log_events

os.environ["AWS_PROFILE"] = "mondayskills.development"

def test_filter():
    session = boto3.Session(profile_name="mondayskills.development")
    log_group = "EtlComputeStack-DbtTaskDefinitionDbtContainerLogGroupE420E81B-W7fZGqD3w8jD"
    now = datetime.now(timezone.utc)
    # just 1 hour
    start_time = now - timedelta(hours=1)
    
    print("Testing run_filter_log_events...")
    t0 = time.time()
    try:
        events = run_filter_log_events(session, log_group, start_time, now)
        print(f"Got {len(events)} events in {time.time() - t0:.2f}s")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_filter()
