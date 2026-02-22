#!/usr/bin/env python3
"""
Extract dbt run logs from CloudWatch and produce a CSV matching
the schema expected by the dbt Run Monitor dashboard.

The ECS Fargate task runs dbt with --log-format json, so each
CloudWatch log event is a JSON line emitted by dbt-core. This script
queries CloudWatch Logs Insights, parses the structured JSON events,
and writes sample_dbt_logs.csv.

Key design decision: classification happens HERE at extraction time,
not downstream in pandas. The dbt JSON event codes map directly:

    Q011 (NodeStart)    → record_type=MODEL_START
    Q012 (NodeFinished) → record_type=MODEL_END  + status=OK/error/skipped
    Z038 (RunResultTotal) → record_type=EXECUTION_STATUS
    Computed per-invocation → record_type=EXECUTION_DURATION

Usage
-----
    python extract_dbt_logs.py                          # last 24h
    python extract_dbt_logs.py --hours 72               # last 72h
    python extract_dbt_logs.py --start 2026-02-09T00:00 --end 2026-02-10T00:00
    python extract_dbt_logs.py --log-group /ecs/EtlComputeStack-DbtTaskDefinition
"""

import argparse
import csv
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

import boto3

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_PROFILE = "dev2"
DEFAULT_LOG_GROUP = "/ecs/ecs-dpinv-dbt"
DEFAULT_HOURS = 24
OUTPUT_FILE = "sample_dbt_logs.csv"

CSV_COLUMNS = [
    "invocation_id",
    "timestamp",
    "entity",
    "model_name",
    "start_time",
    "end_time",
    "duration",
    "status",          # OK, error, skipped, pass (final outcome)
    "record_type",     # MODEL_START, MODEL_END, EXECUTION_DURATION, EXECUTION_STATUS
    "message",
    "thread_info",
    "resource_type",   # model, test, seed, snapshot
    "materialized",    # table, incremental, view
    "error_message",   # actual error text on failures
]


# ---------------------------------------------------------------------------
# CloudWatch query
# ---------------------------------------------------------------------------
def run_insights_query(
    session: boto3.Session,
    log_group: str,
    start_time: datetime,
    end_time: datetime,
) -> list[dict]:
    """Run a CloudWatch Logs Insights query and return raw log events."""
    client = session.client("logs")

    query = (
        "fields @timestamp, @message, @logStream\n"
        "| filter @message like /Q011/ "
        "or @message like /Q012/ "
        "or @message like /Q007/ "
        "or @message like /Z038/ "
        "or @message like /container_start/\n"
        "| sort @timestamp asc\n"
        "| limit 10000"
    )

    print(f"Querying log group: {log_group}")
    print(f"  Time range: {start_time.isoformat()} → {end_time.isoformat()}")

    resp = client.start_query(
        logGroupName=log_group,
        startTime=int(start_time.timestamp()),
        endTime=int(end_time.timestamp()),
        queryString=query,
    )
    query_id = resp["queryId"]

    while True:
        result = client.get_query_results(queryId=query_id)
        query_status = result["status"]
        if query_status in ("Complete", "Failed", "Cancelled", "Timeout"):
            break
        print(f"  Query status: {query_status} ...")
        time.sleep(1)

    if query_status != "Complete":
        print(f"  Query ended with status: {query_status}", file=sys.stderr)
        return []

    rows = result.get("results", [])
    print(f"  Retrieved {len(rows)} raw log events")
    return rows


def run_filter_log_events(
    session: boto3.Session,
    log_group: str,
    start_time: datetime,
    end_time: datetime,
) -> list[dict]:
    """Fetch recent log events using FilterLogEvents (no indexing delay).

    Returns rows in the same format as ``run_insights_query`` so the
    downstream ``parse_dbt_json_events`` works unchanged.
    """
    import re

    client = session.client("logs")
    _q_pattern = re.compile(r'"code":\s*"(Q011|Q012|Q007|Z038)"|"event":\s*"container_start"')

    print(f"FilterLogEvents on {log_group}")
    print(f"  Time range: {start_time.isoformat()} → {end_time.isoformat()}")

    rows: list[dict] = []
    kwargs: dict = dict(
        logGroupName=log_group,
        startTime=int(start_time.timestamp() * 1000),
        endTime=int(end_time.timestamp() * 1000),
        interleaved=True,
    )

    while True:
        resp = client.filter_log_events(**kwargs)
        for evt in resp.get("events", []):
            msg = evt.get("message", "")
            if _q_pattern.search(msg):
                # Reshape into the Insights result format expected by the parser
                rows.append([
                    {"field": "@timestamp", "value": datetime.fromtimestamp(
                        evt["timestamp"] / 1000, tz=timezone.utc
                    ).isoformat()},
                    {"field": "@message", "value": msg},
                    {"field": "@logStream", "value": evt.get("logStreamName", "")},
                ])
        token = resp.get("nextToken")
        if not token:
            break
        kwargs["nextToken"] = token

    rows.sort(key=lambda r: next(f["value"] for f in r if f["field"] == "@timestamp"))
    print(f"  Retrieved {len(rows)} events via FilterLogEvents")
    return rows


# ---------------------------------------------------------------------------
# Parse dbt JSON log lines
# ---------------------------------------------------------------------------
def parse_dbt_json_events(raw_rows: list[dict]) -> list[dict]:
    """
    Parse CloudWatch Logs Insights results into classified records.

    Classification happens here — no downstream mask logic needed.
    """
    records = []
    model_starts: dict[tuple[str, str], dict] = {}   # (invocation_id, unique_id) → start info
    invocation_meta: dict[str, dict] = {}             # invocation_id → tracking

    for raw_row in raw_rows:
        fields = {item["field"]: item["value"] for item in raw_row}
        message_str = fields.get("@message", "")

        try:
            msg = json.loads(message_str)
        except (json.JSONDecodeError, TypeError):
            continue

        # ── container_start: plain JSON from docker-entrypoint ──
        if msg.get("event") == "container_start":
            records.append(_make_record(
                timestamp=fields.get("@timestamp", ""),
                record_type="RUN_CONFIG",
                status="RUN_CONFIG",
                message=json.dumps(msg),
                thread_info="MainThread",
            ))
            continue

        info = msg.get("info", {})
        data = msg.get("data", {})
        invocation_id = info.get("invocation_id", "")
        ts = info.get("ts", fields.get("@timestamp", ""))
        thread_name = info.get("thread_name", "")
        code = info.get("code", "")
        node_info = data.get("node_info", {})
        unique_id = node_info.get("unique_id", "")

        if not invocation_id:
            continue

        # Track invocation bounds
        if invocation_id not in invocation_meta:
            invocation_meta[invocation_id] = {
                "first_ts": ts, "last_ts": ts,
                "pass": 0, "fail": 0, "skip": 0,
            }
        invocation_meta[invocation_id]["last_ts"] = ts

        # ── Q011: NodeStart → MODEL_START ──
        if code == "Q011" and unique_id:
            entity = _extract_entity(unique_id)
            model_name = _extract_model_name(unique_id)
            resource_type = node_info.get("resource_type", "model")
            materialized = node_info.get("materialized", "")
            key = (invocation_id, unique_id)
            model_starts[key] = {"start_ts": ts, "entity": entity, "model_name": model_name}

            records.append(_make_record(
                invocation_id=invocation_id,
                timestamp=ts,
                entity=entity,
                model_name=model_name,
                start_time=ts,
                status="",
                record_type="MODEL_START",
                message=f"Starting {model_name}",
                thread_info=thread_name,
                resource_type=resource_type,
                materialized=materialized,
            ))

        # ── Q012: NodeFinished → MODEL_END + status row ──
        elif code == "Q012" and unique_id:
            entity = _extract_entity(unique_id)
            model_name = _extract_model_name(unique_id)
            resource_type = node_info.get("resource_type", "model")
            materialized = node_info.get("materialized", "")
            key = (invocation_id, unique_id)
            start_ts = model_starts.get(key, {}).get("start_ts", ts)
            duration = _calc_duration(start_ts, ts)

            node_status = node_info.get("node_status", "")
            mapped_status = _map_node_status(node_status)

            # Extract actual error message from run_result if present
            error_msg = ""
            run_result = data.get("run_result", {})
            if mapped_status == "error":
                error_msg = (
                    run_result.get("message", "")
                    or data.get("description", "")
                    or info.get("msg", "")
                )

            # MODEL_END record (marks completion, carries duration)
            records.append(_make_record(
                invocation_id=invocation_id,
                timestamp=ts,
                entity=entity,
                model_name=model_name,
                start_time=start_ts,
                end_time=ts,
                duration=duration,
                status=mapped_status,
                record_type="MODEL_END",
                message=f"Completed {model_name}",
                thread_info=thread_name,
                resource_type=resource_type,
                materialized=materialized,
                error_message=error_msg,
            ))

            # Status row (OK / error / skipped — what the dashboard filters on)
            records.append(_make_record(
                invocation_id=invocation_id,
                timestamp=ts,
                entity=entity,
                model_name=model_name,
                start_time=start_ts,
                end_time=ts,
                duration=duration,
                status=mapped_status,
                record_type="STATUS",
                message=f"{mapped_status.upper()} - {model_name}",
                thread_info=thread_name,
                resource_type=resource_type,
                materialized=materialized,
                error_message=error_msg,
            ))

            # Update invocation counters
            stats = invocation_meta[invocation_id]
            if mapped_status in ("OK", "pass"):
                stats["pass"] += 1
            elif mapped_status == "error":
                stats["fail"] += 1
            elif mapped_status == "skipped":
                stats["skip"] += 1

        # ── Q007: LogTestResult → MODEL_END + status row (tests only) ──
        elif code == "Q007" and unique_id:
            entity = _extract_entity(unique_id)
            model_name = _extract_model_name(unique_id)
            resource_type = node_info.get("resource_type", "test")
            materialized = node_info.get("materialized", "")
            key = (invocation_id, unique_id)
            start_ts = model_starts.get(key, {}).get("start_ts", ts)
            duration = _calc_duration(start_ts, ts)

            node_status = node_info.get("node_status", "")
            mapped_status = _map_node_status(node_status)

            error_msg = ""
            if mapped_status == "error":
                error_msg = data.get("description", "") or info.get("msg", "")

            records.append(_make_record(
                invocation_id=invocation_id,
                timestamp=ts,
                entity=entity,
                model_name=model_name,
                start_time=start_ts,
                end_time=ts,
                duration=duration,
                status=mapped_status,
                record_type="MODEL_END",
                message=f"Completed {model_name}",
                thread_info=thread_name,
                resource_type=resource_type,
                materialized=materialized,
                error_message=error_msg,
            ))

            records.append(_make_record(
                invocation_id=invocation_id,
                timestamp=ts,
                entity=entity,
                model_name=model_name,
                start_time=start_ts,
                end_time=ts,
                duration=duration,
                status=mapped_status,
                record_type="STATUS",
                message=f"{mapped_status.upper()} - {model_name}",
                thread_info=thread_name,
                resource_type=resource_type,
                materialized=materialized,
                error_message=error_msg,
            ))

            stats = invocation_meta[invocation_id]
            if mapped_status in ("OK", "pass"):
                stats["pass"] += 1
            elif mapped_status == "error":
                stats["fail"] += 1
            elif mapped_status == "skipped":
                stats["skip"] += 1

        # ── Z038: RunResultTotal → EXECUTION_STATUS ──
        elif code == "Z038":
            stat_line = data.get("stat_line", info.get("msg", ""))
            records.append(_make_record(
                invocation_id=invocation_id,
                timestamp=ts,
                record_type="EXECUTION_STATUS",
                status="EXECUTION_STATUS",
                message=stat_line,
                thread_info="MainThread",
            ))

    # ── Computed: EXECUTION_DURATION per invocation ──
    # Only emit completion records for invocations that received a Z038
    # (RunResultTotal) event, meaning dbt actually finished.  Without this
    # guard, in-progress invocations get an EXECUTION_DURATION record which
    # causes classify_model_status to mark running models as "unknown".
    invocations_with_z038 = {
        r["invocation_id"]
        for r in records
        if r["record_type"] == "EXECUTION_STATUS"
    }

    for inv_id, meta in invocation_meta.items():
        if inv_id not in invocations_with_z038:
            continue  # invocation still running — skip

        total_dur = _calc_duration(meta["first_ts"], meta["last_ts"])
        records.append(_make_record(
            invocation_id=inv_id,
            timestamp=meta["first_ts"],
            start_time=meta["first_ts"],
            end_time=meta["last_ts"],
            duration=total_dur,
            status="EXECUTION_DURATION",
            record_type="EXECUTION_DURATION",
            message=f"Total execution time: {total_dur}s",
            thread_info="MainThread",
        ))

    return records


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _extract_entity(unique_id: str) -> str:
    """
    Extract entity from dbt node_path like 'model.etl_pipeline.avqdf.payments_transform.stg_payments'.
    Returns the folder name under avqdf with '_transform' stripped (e.g. 'payments').
    Falls back to the model name if the path structure is unexpected.
    """
    parts = unique_id.split(".")
    # node_path has at least 5 parts: type.project.avqdf.<folder>.<model>
    if len(parts) >= 5:
        folder = parts[-2]
        if folder.endswith("_transform"):
            return folder[: -len("_transform")]
        return folder
    # fallback: strip layer prefix from model name
    if len(parts) >= 3:
        name = parts[-1]
        for prefix in ("stg_", "int_", "dim_", "fact_"):
            if name.startswith(prefix):
                return name[len(prefix):]
        return name
    return ""


def _extract_model_name(unique_id: str) -> str:
    return unique_id.split(".")[-1] if "." in unique_id else unique_id


def _map_node_status(node_status: str) -> str:
    s = node_status.lower()
    if s in ("success", "pass"):
        return "OK"
    elif s in ("error", "fail"):
        return "error"
    elif s == "skipped":
        return "skipped"
    return node_status or "OK"


def _calc_duration(start: str, end: str) -> str:
    try:
        t1 = datetime.fromisoformat(start.replace("Z", "+00:00"))
        t2 = datetime.fromisoformat(end.replace("Z", "+00:00"))
        return str(round((t2 - t1).total_seconds(), 2))
    except (ValueError, TypeError, AttributeError):
        return ""


def _make_record(**kwargs) -> dict:
    return {col: kwargs.get(col, "") for col in CSV_COLUMNS}


# ---------------------------------------------------------------------------
# Auto-discover log group
# ---------------------------------------------------------------------------
def discover_log_group(session: boto3.Session) -> str | None:
    client = session.client("logs")
    candidates = ["EtlComputeStack-DbtTaskDefinitionDbtContainerLogGroup", "EtlComputeStack-DbtTaskDefinition", "/ecs/etl-dbt-task", "/ecs/EtlComputeStack", "/ecs/etl-dbt", "etl-dbt"]
    try:
        paginator = client.get_paginator("describe_log_groups")
        for page in paginator.paginate():
            for lg in page["logGroups"]:
                name = lg["logGroupName"]
                for c in candidates:
                    if c in name:
                        return name
    except Exception as e:
        logger.warning("Log group discovery failed: %s", e)
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Extract dbt run logs from CloudWatch → CSV")
    parser.add_argument("--log-group", default=None, help=f"CloudWatch log group (default: auto-discover)")
    parser.add_argument("--hours", type=int, default=DEFAULT_HOURS, help="Look-back hours (default 24)")
    parser.add_argument("--start", default=None, help="Start time ISO-8601")
    parser.add_argument("--end", default=None, help="End time ISO-8601")
    parser.add_argument("--output", default=OUTPUT_FILE, help=f"Output CSV (default {OUTPUT_FILE})")
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help=f"AWS profile (default {DEFAULT_PROFILE})")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile)

    log_group = args.log_group
    if not log_group:
        print("Auto-discovering log group...")
        log_group = discover_log_group(session)
        if log_group:
            print(f"  Found: {log_group}")
        else:
            log_group = DEFAULT_LOG_GROUP
            print(f"  Not found, using default: {log_group}")

    if args.start and args.end:
        start_time = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
        end_time = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
    else:
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=args.hours)

    raw_rows = run_insights_query(session, log_group, start_time, end_time)
    if not raw_rows:
        print("No log events found. Check the log group name and time range.")
        sys.exit(1)

    records = parse_dbt_json_events(raw_rows)
    print(f"Parsed {len(records)} structured records from {len(raw_rows)} raw events")

    if not records:
        print("No dbt model events found in the logs.")
        sys.exit(1)

    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(records)

    print(f"Wrote {len(records)} rows → {args.output}")


if __name__ == "__main__":
    main()
