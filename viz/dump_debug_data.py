#!/usr/bin/env python3
"""
Dump raw and transformed dbt log data (and Glue metrics) to viz/data/
for manual review.

Usage:
    python dump_debug_data.py                  # last 1 hour
    python dump_debug_data.py --hours 4        # last 4 hours
    python dump_debug_data.py --skip-glue      # skip Glue metrics
"""
import sys, os, json, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import boto3
import pandas as pd
from datetime import datetime, timezone, timedelta
from extract_dbt_logs import run_insights_query, parse_dbt_json_events
from helpers import get_model_records, classify_model_status
from data_provider import fetch_glue_job_metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=1)
    parser.add_argument("--profile", default=None, help="AWS profile (omit for ECS IAM role)")
    parser.add_argument("--skip-glue", action="store_true", help="Skip Glue metrics fetch")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile) if args.profile else boto3.Session()
    log_group = os.environ.get(
        "DBT_LOG_GROUP",
        "/ecs/ecs-dpinv-dbt",
    )

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=args.hours)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    os.makedirs("data", exist_ok=True)

    # ── dbt logs ──────────────────────────────────────────
    print(f"Querying last {args.hours}h of dbt logs...")
    raw_rows = run_insights_query(session, log_group, start_time, end_time)
    print(f"  Raw events: {len(raw_rows)}")

    raw_path = f"data/raw_insights_events_{ts}.json"
    with open(raw_path, "w") as f:
        for row in raw_rows:
            f.write(json.dumps({item["field"]: item["value"] for item in row}) + "\n")
    print(f"  -> {raw_path}")

    if raw_rows:
        records = parse_dbt_json_events(raw_rows)
        df_all = pd.DataFrame(records)
        all_path = f"data/parsed_all_records_{ts}.csv"
        df_all.to_csv(all_path, index=False)
        print(f"  Parsed records: {len(df_all)} -> {all_path}")

        model_df = get_model_records(df_all, include_tests=False)
        m_path = f"data/model_records_{ts}.csv"
        model_df.to_csv(m_path, index=False)
        print(f"  Model records: {len(model_df)} -> {m_path}")

        test_df = get_model_records(df_all, include_tests=True)
        if "resource_type" in test_df.columns:
            test_df = test_df[test_df["resource_type"] == "test"]
        t_path = f"data/test_records_{ts}.csv"
        test_df.to_csv(t_path, index=False)
        print(f"  Test records: {len(test_df)} -> {t_path}")

        done_mask = df_all["record_type"].isin(["EXECUTION_DURATION", "EXECUTION_STATUS"])
        completed_inv = set(df_all.loc[done_mask, "invocation_id"].unique())

        cm = classify_model_status(get_model_records(df_all, include_tests=False), completed_inv)
        cm_path = f"data/classified_models_{ts}.csv"
        cm.to_csv(cm_path, index=False)
        print(f"  Classified models: {len(cm)} -> {cm_path}")
        print(f"    {dict(cm['final_status'].value_counts())}")

        if not test_df.empty:
            ct = classify_model_status(test_df, completed_inv)
            ct_path = f"data/classified_tests_{ts}.csv"
            ct.to_csv(ct_path, index=False)
            print(f"  Classified tests: {len(ct)} -> {ct_path}")
            print(f"    {dict(ct['final_status'].value_counts())}")
    else:
        print("No dbt events found. Try increasing --hours.")

    # ── Glue metrics ──────────────────────────────────────
    if not args.skip_glue:
        print(f"\nFetching Glue metrics for last {args.hours}h...")
        try:
            glue_df = fetch_glue_job_metrics(
                start_time=start_time.isoformat(),
                end_time=end_time.isoformat(),
            )
            if not glue_df.empty:
                glue_path = f"data/glue_metrics_{ts}.csv"
                glue_df.to_csv(glue_path, index=False)
                sessions = glue_df["job_run_id"].nunique()
                print(f"  Glue metrics: {len(glue_df)} rows, {sessions} sessions -> {glue_path}")
            else:
                print("  No Glue metrics found.")
        except Exception as e:
            print(f"  Failed to fetch Glue metrics: {e}")

    print(f"\nDone. All files in viz/data/ with timestamp {ts}")


if __name__ == "__main__":
    main()
