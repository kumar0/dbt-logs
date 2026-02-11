#!/usr/bin/env python3
"""Parse dbt run_results.json and publish metrics to CloudWatch."""

import json
import os
import sys
from datetime import datetime

import boto3


def publish_metrics():
    results_path = "/dbt/target/run_results.json"
    if not os.path.exists(results_path):
        print("No run_results.json found, skipping metrics publish")
        return

    with open(results_path) as f:
        data = json.load(f)

    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    cw = boto3.client("cloudwatch", region_name=region)

    namespace = "ETL/dbt"
    timestamp = datetime.utcnow()

    # Summary metrics
    results = data.get("results", [])
    total = len(results)
    passed = sum(1 for r in results if r.get("status") in ("success", "pass"))
    failed = sum(1 for r in results if r.get("status") in ("error", "fail"))
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    total_time = sum(r.get("execution_time", 0) for r in results)

    metrics = [
        {"MetricName": "ModelsTotal", "Value": total, "Unit": "Count"},
        {"MetricName": "ModelsPassed", "Value": passed, "Unit": "Count"},
        {"MetricName": "ModelsFailed", "Value": failed, "Unit": "Count"},
        {"MetricName": "ModelsSkipped", "Value": skipped, "Unit": "Count"},
        {"MetricName": "TotalExecutionTime", "Value": total_time, "Unit": "Seconds"},
    ]

    metric_data = []
    for m in metrics:
        metric_data.append({
            "MetricName": m["MetricName"],
            "Timestamp": timestamp,
            "Value": m["Value"],
            "Unit": m["Unit"],
            "Dimensions": [
                {"Name": "Project", "Value": "etl_pipeline"},
                {"Name": "Environment", "Value": os.environ.get("DBT_TARGET", "dev")},
            ],
        })

    # Per-model execution time
    for r in results:
        uid = r.get("unique_id", "unknown")
        exec_time = r.get("execution_time", 0)
        status = r.get("status", "unknown")
        resource_type = uid.split(".")[0] if "." in uid else "unknown"

        metric_data.append({
            "MetricName": "ModelExecutionTime",
            "Timestamp": timestamp,
            "Value": exec_time,
            "Unit": "Seconds",
            "Dimensions": [
                {"Name": "Project", "Value": "etl_pipeline"},
                {"Name": "ModelName", "Value": uid.split(".")[-1] if "." in uid else uid},
                {"Name": "ResourceType", "Value": resource_type},
            ],
        })

        metric_data.append({
            "MetricName": "ModelStatus",
            "Timestamp": timestamp,
            "Value": 1 if status in ("success", "pass") else 0,
            "Unit": "Count",
            "Dimensions": [
                {"Name": "Project", "Value": "etl_pipeline"},
                {"Name": "ModelName", "Value": uid.split(".")[-1] if "." in uid else uid},
                {"Name": "Status", "Value": status},
            ],
        })

    # CloudWatch accepts max 1000 metrics per call, batch in 25s
    for i in range(0, len(metric_data), 25):
        batch = metric_data[i : i + 25]
        cw.put_metric_data(Namespace=namespace, MetricData=batch)

    print(f"Published {len(metric_data)} metrics to CloudWatch namespace '{namespace}'")


if __name__ == "__main__":
    try:
        publish_metrics()
    except Exception as e:
        print(f"Warning: Failed to publish metrics: {e}", file=sys.stderr)
        sys.exit(0)  # Don't fail the pipeline over metrics
