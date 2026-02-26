"""
Data provider for dbt Run Monitor dashboard.

dbt logs  → CloudWatch Logs Insights (live).
Glue metrics → CloudWatch GetMetricData (live).

Fetch modes
-----------
- "full"  : Complete data pull for the requested date range.
            Used on first load, date change, or manual refresh.
- "delta" : Incremental pull for records newer than *since* timestamp.
            Used when auto-refresh is active.
"""

import os
import sys
import logging
import argparse

import pandas as pd
from typing import Optional, Literal

FetchMode = Literal["full", "delta"]

logger = logging.getLogger(__name__)


def _parse_profile_from_cli() -> Optional[str]:
    """Parse --profile from command-line args (after Streamlit's '--' separator)."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--profile", type=str, default=None)
    args, _ = parser.parse_known_args()
    return args.profile


# ---------------------------------------------------------------------------
# Config — override via: CLI --profile > env AWS_PROFILE > default (None = use IAM role in ECS)
# ---------------------------------------------------------------------------
_cli_profile = _parse_profile_from_cli()
AWS_PROFILE = _cli_profile or os.environ.get("AWS_PROFILE") or None  # None → boto3 uses IAM role
logger.info("[Config] AWS_PROFILE resolved to '%s' (cli=%s, env=%s)",
            AWS_PROFILE, _cli_profile, os.environ.get("AWS_PROFILE"))
DBT_LOG_GROUP = os.environ.get("DBT_LOG_GROUP", "EtlComputeStack-DbtTaskDefinitionDbtContainerLogGroupE420E81B-W7fZGqD3w8jD")

# --- Glue metrics config ---
# PRODUCTION: Change this prefix to match your production Glue session naming convention.
GLUE_SESSION_ID_PREFIX = os.environ.get("GLUE_SESSION_ID_PREFIX", "hk_dbt")

# Tracks what happened on the last fetch — read by the dashboard for display
last_dbt_fetch_info: dict = {"source": "none", "detail": "", "log_group": ""}
last_glue_fetch_info: dict = {"source": "none", "detail": ""}

# Run config extracted from container_start log event
last_run_config: dict = {}


# ---------------------------------------------------------------------------
# dbt run logs — CloudWatch live
# ---------------------------------------------------------------------------

def fetch_dbt_run_logs(
    log_group_name: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    filter_pattern: Optional[str] = None,
    limit: int = 10_000,
    fetch_mode: FetchMode = "full",
    since: Optional[str] = None,
    prefer_realtime: bool = False,
) -> pd.DataFrame:
    """
    Return dbt run log records as a DataFrame from CloudWatch.

    Parameters
    ----------
    log_group_name : str, optional
        CloudWatch log group. Auto-discovered if not provided.
    start_time / end_time : str, optional
        ISO-8601 bounds for the query window.
    fetch_mode : "full" | "delta"
        "full"  – complete date range.  "delta" – only newer than *since*.
    since : str, optional
        ISO-8601 cutoff for delta mode.
    prefer_realtime : bool
        When True, use FilterLogEvents (zero lag) even for full fetches.

    Returns
    -------
    pd.DataFrame
    """
    df = _fetch_from_cloudwatch(
        log_group_name=log_group_name,
        start_time=start_time,
        end_time=end_time,
        fetch_mode=fetch_mode,
        since=since,
        prefer_realtime=prefer_realtime,
    )
    if not df.empty:
        last_dbt_fetch_info["source"] = "cloudwatch"
        last_dbt_fetch_info["detail"] = f"{len(df)} records"
    else:
        last_dbt_fetch_info["source"] = "cloudwatch"
        last_dbt_fetch_info["detail"] = "0 records returned"
    return df


def _fetch_from_cloudwatch(
    log_group_name: Optional[str],
    start_time: Optional[str],
    end_time: Optional[str],
    fetch_mode: FetchMode,
    since: Optional[str],
    prefer_realtime: bool = False,
) -> pd.DataFrame:
    """Query CloudWatch for dbt JSON events.

    - **delta** mode uses ``FilterLogEvents`` (zero indexing delay) so the
      dashboard can show live progress during a running execution.
    - **full** mode uses Logs Insights which is faster for large time ranges
      but has a multi-minute indexing lag.
    """
    from datetime import datetime, timedelta, timezone
    from extract_dbt_logs import (
        run_insights_query,
        run_filter_log_events,
        parse_dbt_json_events,
        discover_log_group,
        CSV_COLUMNS,
    )
    import boto3

    session = boto3.Session(profile_name=AWS_PROFILE) if AWS_PROFILE else boto3.Session()

    # Resolve log group
    log_group = log_group_name or DBT_LOG_GROUP
    if not log_group:
        log_group = discover_log_group(session)
    if not log_group:
        raise RuntimeError("Could not discover CloudWatch log group. "
                           "Set DBT_LOG_GROUP env var or pass --log-group.")
    last_dbt_fetch_info["log_group"] = log_group

    # Resolve time window
    if fetch_mode == "delta" and since:
        _since_dt = datetime.fromisoformat(since)
        query_start = _since_dt.astimezone(timezone.utc) if _since_dt.tzinfo else _since_dt.replace(tzinfo=timezone.utc)
        query_end = datetime.now(timezone.utc)
    elif start_time and end_time:
        _st = datetime.fromisoformat(start_time)
        _et = datetime.fromisoformat(end_time)
        query_start = _st.astimezone(timezone.utc) if _st.tzinfo else _st.replace(tzinfo=timezone.utc)
        query_end = _et.astimezone(timezone.utc) if _et.tzinfo else _et.replace(tzinfo=timezone.utc)
    else:
        query_end = datetime.now(timezone.utc)
        query_start = query_end - timedelta(hours=1)

    if fetch_mode == "delta" or prefer_realtime:
        raw_rows = run_filter_log_events(session, log_group, query_start, query_end)
    else:
        raw_rows = run_insights_query(session, log_group, query_start, query_end)
        # If Insights returned nothing (indexing lag), try FilterLogEvents
        if not raw_rows:
            raw_rows = run_filter_log_events(session, log_group, query_start, query_end)

    if not raw_rows:
        return pd.DataFrame(columns=CSV_COLUMNS)

    records = parse_dbt_json_events(raw_rows)
    if not records:
        return pd.DataFrame(columns=CSV_COLUMNS)

    # Extract run config (worker_type etc.) from RUN_CONFIG records
    import json as _json
    for rec in records:
        if rec.get("record_type") == "RUN_CONFIG":
            try:
                last_run_config.update(_json.loads(rec.get("message", "{}")))
            except (_json.JSONDecodeError, TypeError):
                pass

    df = pd.DataFrame(records)
    return _coerce_types(df)


def _coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure datetime and numeric columns have correct types."""
    for col in ["timestamp", "start_time", "end_time"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
    if "duration" in df.columns:
        df["duration"] = pd.to_numeric(df["duration"], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Glue job metrics  (CloudWatch GetMetricData)
# ---------------------------------------------------------------------------

# Metric definitions grouped by category — shared with the dashboard for
# display labels, units, and descriptions.
GLUE_METRIC_CATEGORIES = {
    "Resource Utilization": {
        "glue.ALL.jvm.heap.usage": ("Heap Usage (ALL)", "ratio", "Average JVM heap utilization across all executors (0-1). >0.8 = memory pressure."),
        "glue.ALL.jvm.heap.used": ("Heap Used (ALL)", "bytes", "Total JVM heap bytes used across all executors."),
        "glue.ALL.system.cpuSystemLoad": ("CPU Load (ALL)", "ratio", "Average system CPU load across all executors (0-1)."),
        "glue.driver.jvm.heap.usage": ("Driver Heap Usage", "ratio", "Driver JVM heap utilization. High = driver bottleneck."),
        "glue.driver.jvm.heap.used": ("Driver Heap Used", "bytes", "Driver JVM heap bytes used."),
        "glue.driver.system.cpuSystemLoad": ("Driver CPU Load", "ratio", "Driver CPU system load."),
        "glue.driver.BlockManager.disk.diskSpaceUsed_MB": ("Disk Spill (MB)", "MB", "Disk spill on driver. >0 means memory insufficient, spilling to disk."),
    },
    "I/O & Data Volume": {
        "glue.ALL.s3.filesystem.read_bytes": ("S3 Read (ALL)", "bytes", "Total bytes read from S3 across all executors."),
        "glue.ALL.s3.filesystem.write_bytes": ("S3 Write (ALL)", "bytes", "Total bytes written to S3 across all executors."),
        "glue.driver.s3.filesystem.read_bytes": ("S3 Read (Driver)", "bytes", "Bytes read from S3 by driver."),
        "glue.driver.s3.filesystem.write_bytes": ("S3 Write (Driver)", "bytes", "Bytes written to S3 by driver."),
        "glue.driver.aggregate.bytesRead": ("Total Bytes Read", "bytes", "Total bytes read across all Spark tasks."),
        "glue.driver.aggregate.recordsRead": ("Records Read", "count", "Total records read. Useful for row-count validation."),
    },
    "Shuffle & Task Performance": {
        "glue.driver.aggregate.shuffleBytesWritten": ("Shuffle Written", "bytes", "Shuffle data written. High = expensive joins/aggregations (SCD2 merges)."),
        "glue.driver.aggregate.shuffleLocalBytesRead": ("Shuffle Local Read", "bytes", "Shuffle data read locally. Compare with total shuffle for data locality."),
        "glue.driver.aggregate.numCompletedStages": ("Completed Stages", "count", "Spark stages completed."),
        "glue.driver.aggregate.numCompletedTasks": ("Completed Tasks", "count", "Spark tasks completed. Throughput indicator."),
        "glue.driver.aggregate.numFailedTasks": ("Failed Tasks", "count", "Failed Spark tasks. Non-zero = data issues or resource problems."),
        "glue.driver.aggregate.numKilledTasks": ("Killed Tasks", "count", "Killed tasks (speculative exec or OOM). Should be near zero."),
        "glue.driver.aggregate.jvmGCTime": ("GC Time", "ms", "Total JVM garbage collection time. High = memory pressure."),
        "glue.driver.aggregate.elapsedTime": ("Elapsed Time", "ms", "Total elapsed time across all Spark tasks."),
    },
    "Executor Scaling": {
        "glue.driver.ExecutorAllocationManager.executors.numberAllExecutors": ("Active Executors", "count", "Current executor count. Key for DPU-hour calculation."),
        "glue.driver.ExecutorAllocationManager.executors.numberMaxNeededExecutors": ("Max Needed Executors", "count", "Max executors Spark thinks it needs. Compare with actual for scaling gaps."),
    },
}

# Flat lookup built once at import time
ALL_METRICS_FLAT = {}
for _cat, _metrics in GLUE_METRIC_CATEGORIES.items():
    for _metric_name, (_label, _unit, _desc) in _metrics.items():
        ALL_METRICS_FLAT[_metric_name] = {"label": _label, "unit": _unit, "desc": _desc, "category": _cat}


def fetch_glue_job_metrics(
    namespace: str = "Glue",
    job_name: Optional[str] = None,
    job_run_id: Optional[str] = None,
    metric_names: Optional[list[str]] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    period: int = 300,
    statistics: Optional[list[str]] = None,
    fetch_mode: FetchMode = "full",
    since: Optional[str] = None,
    entity: Optional[str] = None,
) -> pd.DataFrame:
    """
    Return Glue job CloudWatch metrics as a DataFrame.

    Discovers sessions whose JobRunId starts with GLUE_SESSION_ID_PREFIX.
    Pass *entity* to restrict results to a single entity (e.g. "customers").

    Returns
    -------
    pd.DataFrame
        Columns: job_name, job_run_id, entity, metric_name, metric_type,
                 timestamp, value, average, maximum, minimum, sum,
                 sample_count, label, unit, category, description,
                 run_id_type
    """
    logger.debug("[GlueMetrics] fetch_glue_job_metrics called — mode=%s, prefix=%s, entity=%s, start=%s, end=%s",
                 fetch_mode, GLUE_SESSION_ID_PREFIX, entity, start_time, end_time)
    logger.debug("[GlueMetrics] Using AWS_PROFILE=%s", AWS_PROFILE)

    # Build entity-specific prefix when a single entity is requested.
    # JobName convention: {prefix}_{entity}  e.g. hk_dbt_asset
    session_prefix = f"{GLUE_SESSION_ID_PREFIX}_{entity}" if entity else GLUE_SESSION_ID_PREFIX

    df = _fetch_glue_from_cloudwatch(
        namespace=namespace,
        job_name=job_name,
        job_run_id=job_run_id,
        metric_names=metric_names,
        start_time=start_time,
        end_time=end_time,
        period=period,
        statistics=statistics,
        fetch_mode=fetch_mode,
        since=since,
        session_prefix=session_prefix,
    )
    logger.debug("[GlueMetrics] _fetch_glue_from_cloudwatch returned %d rows", len(df))
    if not df.empty:
        last_glue_fetch_info["source"] = "cloudwatch"
        last_glue_fetch_info["detail"] = f"{len(df)} records, {df['job_run_id'].nunique()} sessions"
        return _enrich_glue_df(df)
    last_glue_fetch_info["source"] = "cloudwatch"
    last_glue_fetch_info["detail"] = "0 records returned"
    return pd.DataFrame()


def _fetch_glue_from_cloudwatch(
    namespace: str,
    job_name: Optional[str],
    job_run_id: Optional[str],
    metric_names: Optional[list[str]],
    start_time: Optional[str],
    end_time: Optional[str],
    period: int,
    statistics: Optional[list[str]],
    fetch_mode: FetchMode,
    since: Optional[str],
    session_prefix: Optional[str] = None,
) -> pd.DataFrame:
    """Pull Glue metrics from CloudWatch via list_metrics + get_metric_data."""
    from datetime import datetime, timedelta, timezone
    import boto3
    import time as _time

    effective_prefix = session_prefix or GLUE_SESSION_ID_PREFIX
    logger.debug("[GlueMetrics] _fetch_glue_from_cloudwatch START — namespace=%s, mode=%s, prefix=%s",
                 namespace, fetch_mode, effective_prefix)

    session = boto3.Session(profile_name=AWS_PROFILE) if AWS_PROFILE else boto3.Session()
    cw = session.client("cloudwatch")

    # --- Resolve time window ---
    if fetch_mode == "delta" and since:
        query_start = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
        query_end = datetime.now(timezone.utc)
    elif start_time and end_time:
        query_start = datetime.fromisoformat(start_time).replace(tzinfo=timezone.utc)
        query_end = datetime.fromisoformat(end_time).replace(tzinfo=timezone.utc)
    else:
        query_end = datetime.now(timezone.utc)
        query_start = query_end - timedelta(hours=1)

    # Guard: CloudWatch requires EndTime > StartTime
    if query_end <= query_start:
        logger.warning("[GlueMetrics] EndTime (%s) <= StartTime (%s); adjusting EndTime to StartTime + 1h",
                       query_end, query_start)
        query_end = query_start + timedelta(hours=1)

    logger.debug("[GlueMetrics] Time window: %s → %s", query_start, query_end)

    # --- Step 1: Discover sessions via list_metrics ---
    _t0 = _time.monotonic()
    sessions, discovered_metrics, job_name_to_entity = _discover_glue_sessions(cw, namespace, effective_prefix)
    logger.debug("[GlueMetrics] _discover_glue_sessions took %.2fs — %d sessions, %d metrics discovered",
                 _time.monotonic() - _t0, len(sessions), len(discovered_metrics))
    if not sessions:
        logger.info("No Glue sessions found matching prefix '%s'", effective_prefix)
        return pd.DataFrame()

    logger.info("Discovered %d Glue sessions matching prefix '%s'", len(sessions), effective_prefix)

    # --- Step 2: Build metric queries for each session ---
    # Merge predefined metrics with dynamically discovered ones (includes per-executor)
    predefined = list(ALL_METRICS_FLAT.keys()) if not metric_names else metric_names
    target_metrics = sorted(set(predefined) | discovered_metrics)
    stat_list = statistics or ["Average", "Maximum", "Minimum", "Sum", "SampleCount"]

    logger.debug("[GlueMetrics] Target metrics count: %d (predefined=%d, discovered=%d)",
                 len(target_metrics), len(predefined), len(discovered_metrics))

    all_metric_queries = []
    query_id_map = {}

    query_idx = 0
    for sess_job_name, sess_run_id in sessions:
        for metric_name in target_metrics:
            safe_id = f"q_{query_idx}"
            all_metric_queries.append({
                "Id": safe_id,
                "MetricStat": {
                    "Metric": {
                        "Namespace": namespace,
                        "MetricName": metric_name,
                        "Dimensions": [
                            {"Name": "JobName", "Value": sess_job_name},
                            {"Name": "JobRunId", "Value": sess_run_id},
                            {"Name": "Type", "Value": "gauge"},
                        ],
                    },
                    "Period": period,
                    "Stat": "Average",
                },
                "ReturnData": True,
            })
            query_id_map[safe_id] = (metric_name, sess_job_name, sess_run_id)
            query_idx += 1

    total_batches = (len(all_metric_queries) + 499) // 500
    all_records = []
    for batch_start in range(0, len(all_metric_queries), 500):
        batch_num = batch_start // 500 + 1
        batch = all_metric_queries[batch_start:batch_start + 500]
        logger.debug("[GlueMetrics]   Batch %d/%d (%d queries) for all sessions",
                     batch_num, total_batches, len(batch))
        _tb = _time.monotonic()
        records = _run_get_metric_data(
            cw, batch, query_id_map, query_start, query_end, period, stat_list,
            job_name_to_entity=job_name_to_entity,
        )
        logger.debug("[GlueMetrics]   Batch %d/%d returned %d records in %.2fs",
                     batch_num, total_batches, len(records), _time.monotonic() - _tb)
        all_records.extend(records)

    logger.debug("[GlueMetrics] Total records collected: %d", len(all_records))

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def _discover_glue_sessions(cw, namespace: str, prefix: str) -> tuple[list[tuple[str, str]], set[str], dict[str, str]]:
    """Use list_metrics to find (JobName, JobRunId) pairs matching the prefix.

    Glue interactive sessions publish metrics where:
      - JobRunId = the session ID (e.g. hk_dbt_dim_customers_18022026)
      - JobName  = an internal UUID assigned by Glue

    So we match on JobRunId.startswith(prefix), not JobName.

    Two-pass discovery:
    1. Probe a known metric to find (JobName, JobRunId) pairs where
       JobRunId starts with *prefix*.
    2. Per-JobName scan to collect all metric names (including per-executor
       metrics like ``glue.1.jvm.heap.usage``).

    Returns
    -------
    tuple[list[tuple[str, str]], set[str], dict[str, str]]
        Sorted list of (JobName, JobRunId) pairs, a set of all discovered
        metric names (including per-executor metrics), and a mapping of
        JobName (UUID) → entity name derived from the real JobRunId.
    """
    sessions: set[tuple[str, str]] = set()
    job_names: set[str] = set()
    # Maps internal JobName UUID → entity name (derived from real JobRunId)
    job_name_to_entity: dict[str, str] = {}
    paginator = cw.get_paginator("list_metrics")

    import time as _time

    # --- Pass 1: Find (JobName, JobRunId) pairs where JobRunId matches prefix ---
    logger.debug("[GlueMetrics] _discover_glue_sessions Pass 1: scanning JobRunId for prefix='%s'", prefix)
    _t0 = _time.monotonic()
    page_count = 0
    # Also match legacy session IDs like etl-dbt-session__<role>__<uuid>
    _EXTRA_PREFIXES = ["etl-dbt-session__"]

    probe_iter = paginator.paginate(
        Namespace=namespace,
        MetricName="glue.ALL.jvm.heap.usage",
    )
    for page in probe_iter:
        page_count += 1
        for metric in page.get("Metrics", []):
            dims = {d["Name"]: d["Value"] for d in metric.get("Dimensions", [])}
            job_name = dims.get("JobName", "")
            job_run_id = dims.get("JobRunId", "")
            # Match on JobRunId (the session ID), not JobName (which is a UUID)
            matched = job_run_id and (
                job_run_id.startswith(prefix)
                or any(job_run_id.startswith(p) for p in _EXTRA_PREFIXES)
            )
            if matched:
                sessions.add((job_name, job_run_id))
                job_names.add(job_name)
                # Build entity mapping from the real JobRunId (not the UUID JobName)
                if job_name not in job_name_to_entity:
                    job_name_to_entity[job_name] = _extract_entity_from_job_name(job_name, job_run_id)
    logger.debug("[GlueMetrics] Pass 1 done: %d pages, %d sessions, %d job_names in %.2fs",
                 page_count, len(sessions), len(job_names), _time.monotonic() - _t0)

    if not job_names:
        logger.debug("[GlueMetrics] No sessions found with JobRunId prefix '%s' — returning empty", prefix)
        return [], set()

    logger.info("Discovered %d session(s) with JobRunId prefix '%s': %s",
                len(sessions), prefix, sorted(r for _, r in sessions))

    # --- Pass 2: Skip discovery of all metrics (incl. per-executor) for performance ---
    discovered_metrics: set[str] = set()

    logger.debug("[GlueMetrics] _discover_glue_sessions DONE — %d total sessions, %d unique metrics",
                 len(sessions), len(discovered_metrics))
    return sorted(sessions), discovered_metrics, job_name_to_entity


def _run_get_metric_data(
    cw,
    queries: list[dict],
    query_id_map: dict,
    start_time,
    end_time,
    period: int,
    stat_list: list[str],
    job_name_to_entity: dict[str, str] | None = None,
) -> list[dict]:
    """Execute get_metric_data and return flat records."""
    import time as _time
    records = []
    next_token = None
    page_num = 0

    logger.debug("[GlueMetrics] _run_get_metric_data START — %d queries", len(queries))
    _t0 = _time.monotonic()

    while True:
        page_num += 1
        kwargs = {
            "MetricDataQueries": queries,
            "StartTime": start_time,
            "EndTime": end_time,
        }
        if next_token:
            kwargs["NextToken"] = next_token

        logger.debug("[GlueMetrics]   get_metric_data page %d (token=%s)...",
                     page_num, "yes" if next_token else "no")
        _tp = _time.monotonic()
        resp = cw.get_metric_data(**kwargs)
        logger.debug("[GlueMetrics]   page %d returned in %.2fs — %d results",
                     page_num, _time.monotonic() - _tp, len(resp.get("MetricDataResults", [])))

        for result in resp.get("MetricDataResults", []):
            query_id = result["Id"]
            if query_id not in query_id_map:
                continue

            metric_name, job_name, job_run_id = query_id_map[query_id]
            timestamps = result.get("Timestamps", [])
            values = result.get("Values", [])

            entity = _extract_entity_from_job_name(job_name, job_run_id)
            # For synthetic ALL rows, job_run_id is "ALL" so _extract_entity_from_job_name
            # falls back to job_name (a UUID). Use the pre-built map instead.
            if job_run_id == "ALL" and job_name_to_entity and job_name in job_name_to_entity:
                entity = job_name_to_entity[job_name]

            for ts, val in zip(timestamps, values):
                records.append({
                    "job_name": job_name,
                    "job_run_id": job_run_id,
                    "entity": entity,
                    "metric_name": metric_name,
                    "metric_type": "gauge",
                    "timestamp": ts,
                    "value": val,
                    "average": val,
                    "maximum": val,
                    "minimum": val,
                    "sum": val,
                    "sample_count": 1.0,
                })

        next_token = resp.get("NextToken")
        if not next_token:
            break

    logger.debug("[GlueMetrics] _run_get_metric_data Average pass done: %d records in %.2fs",
                 len(records), _time.monotonic() - _t0)

    return records





def _extract_entity_from_job_name(job_name: str, job_run_id: str = "") -> str:
    """Extract entity name from the Glue JobRunId (session ID).

    JobRunId convention: hk_dbt_{entity}_{ddmmyyyy}
    e.g. hk_dbt_dim_customers_18022026 → dim_customers
         hk_dbt_stg_payments_20022026  → stg_payments

    Legacy convention: etl-dbt-session__{role}__{uuid} → etl-dbt-session

    Falls back to job_name if job_run_id doesn't match any known prefix.
    """
    prefix = GLUE_SESSION_ID_PREFIX + "_"
    source = job_run_id if job_run_id.startswith(prefix) else job_name
    if source.startswith(prefix):
        remainder = source[len(prefix):]
        # Strip trailing _ddmmyyyy (8 digits) if present
        import re
        remainder = re.sub(r"_\d{8}$", "", remainder)
        return remainder or source
    # Legacy: etl-dbt-session__<role>__<uuid>
    if job_run_id.startswith("etl-dbt-session__"):
        return "etl-dbt-session"
    return source


def _enrich_glue_df(df: pd.DataFrame) -> pd.DataFrame:
    """Add display metadata columns from GLUE_METRIC_CATEGORIES."""
    df["label"] = df["metric_name"].map(lambda m: ALL_METRICS_FLAT[m]["label"] if m in ALL_METRICS_FLAT else m)
    df["unit"] = df["metric_name"].map(lambda m: ALL_METRICS_FLAT[m]["unit"] if m in ALL_METRICS_FLAT else "")
    df["category"] = df["metric_name"].map(lambda m: ALL_METRICS_FLAT[m]["category"] if m in ALL_METRICS_FLAT else "Other")
    df["description"] = df["metric_name"].map(lambda m: ALL_METRICS_FLAT[m]["desc"] if m in ALL_METRICS_FLAT else "")
    df["run_id_type"] = df["job_run_id"].apply(lambda x: "ALL" if x == "ALL" else "session")
    return df
