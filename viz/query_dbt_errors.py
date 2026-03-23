#!/usr/bin/env python3
"""
Query CloudWatch dbt logs and extract error records into a pandas DataFrame.

Importable:
    from query_dbt_errors import fetch_dbt_errors
    df = fetch_dbt_errors("2026-02-25T00:00")          # 24h window from that time
    df = fetch_dbt_errors("2026-02-25T00:00", hours=6) # 6h window

Returns a DataFrame with columns:
    timestamp, invocation_id, entity_name, error_message
"""

import json
import os
from datetime import datetime, timedelta, timezone

import boto3
import pandas as pd

LOG_GROUP = os.environ.get(
    "DBT_LOG_GROUP",
    "EtlComputeStack-DbtTaskDefinitionDbtContainerLogGroupE420E81B-W7fZGqD3w8jD",
)
AWS_PROFILE = os.environ.get("AWS_PROFILE") or None  # None → boto3 uses IAM role in ECS


def fetch_dbt_errors(
    start_dt: str | datetime | None = None,
    hours: float = 24,
) -> pd.DataFrame:
    """
    Fetch dbt error log entries from CloudWatch.

    Args:
        start_dt: Start of the window. Accepts an ISO string ("2026-02-25T00:00"),
                  a datetime object, or None (defaults to `hours` ago from now).
        hours:    Width of the time window in hours (default 24).

    Returns:
        DataFrame with columns: timestamp, invocation_id, entity_name, error_message
    """
    if start_dt is None:
        start = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
    elif isinstance(start_dt, str):
        start = datetime.fromisoformat(start_dt).replace(tzinfo=timezone.utc)
    else:
        start = start_dt if start_dt.tzinfo else start_dt.replace(tzinfo=timezone.utc)

    end = start + timedelta(hours=hours)
    return _query_cloudwatch(start, end)


def _query_cloudwatch(start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
    session = boto3.Session(profile_name=AWS_PROFILE) if AWS_PROFILE else boto3.Session()
    client = session.client("logs")

    filter_pattern = '"level": "error"'

    rows = []
    kwargs = dict(
        logGroupName=LOG_GROUP,
        startTime=int(start_dt.timestamp() * 1000),
        endTime=int(end_dt.timestamp() * 1000),
        filterPattern=filter_pattern,
        interleaved=True,
    )

    print(f"Querying {LOG_GROUP}")
    print(f"  Range: {start_dt.isoformat()} → {end_dt.isoformat()}")

    while True:
        resp = client.filter_log_events(**kwargs)
        for evt in resp.get("events", []):
            row = _parse_error_event(evt)
            if row:
                rows.append(row)
        token = resp.get("nextToken")
        if not token or token == kwargs.get("nextToken"):
            break
        kwargs["nextToken"] = token

    print(f"  Found {len(rows)} error entries")

    if not rows:
        return pd.DataFrame(columns=["timestamp", "invocation_id", "entity_name", "error_message"])

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def _parse_error_event(evt: dict) -> dict | None:
    """Parse a single CloudWatch log event into an error record."""
    try:
        msg = json.loads(evt.get("message", ""))
    except (json.JSONDecodeError, TypeError):
        return None

    info = msg.get("info", {})
    if info.get("level") != "error":
        return None

    data = msg.get("data", {})
    node_info = data.get("node_info", {})

    # Entity name: prefer node_name from node_info, fall back to unique_id tail
    entity_name = node_info.get("node_name", "")
    if not entity_name:
        unique_id = node_info.get("unique_id", "")
        entity_name = unique_id.split(".")[-1] if unique_id else ""

    # Error message: prefer run_result.message, then data.exc, then info.msg
    run_result = data.get("run_result", {})
    error_message = (
        run_result.get("message")
        or data.get("exc")
        or info.get("msg", "")
    )

    return {
        "timestamp": info.get("ts", ""),
        "invocation_id": info.get("invocation_id", ""),
        "entity_name": entity_name or None,
        "error_message": error_message,
    }


def main():
    df = fetch_dbt_errors()  # last 24h by default
    print(df.to_string())


if __name__ == "__main__":
    main()
