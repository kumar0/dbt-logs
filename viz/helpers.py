"""Shared helper functions for the dbt Run Monitor dashboard."""

import pandas as pd


def get_model_records(df, include_tests: bool = False):
    """Extract meaningful model-level records using record_type instead of overloaded status.

    Parameters
    ----------
    include_tests : bool
        If False (default), exclude dbt test nodes so only real models
        (model, seed, snapshot) appear in the dashboard counts.
    """
    if "record_type" in df.columns:
        mask = df["record_type"].isin(["MODEL_START", "MODEL_END", "STATUS"])
    else:
        # Backward compat with old CSV format (no record_type column)
        mask = df["status"].isin(["MODEL_START", "MODEL_END", "OK", "error", "skipped", "pass"])

    result = df[mask & df["model_name"].notna() & (df["model_name"] != "")].copy()

    # Filter out test nodes unless explicitly requested
    if not include_tests and "resource_type" in result.columns:
        result = result[result["resource_type"] != "test"].copy()

    return result


def get_execution_summary(df):
    """Get per-invocation execution summary."""
    if "record_type" in df.columns:
        exec_rows = df[df["record_type"] == "EXECUTION_DURATION"].copy()
        status_rows = df[df["record_type"] == "EXECUTION_STATUS"].copy()
    else:
        exec_rows = df[df["status"] == "EXECUTION_DURATION"].copy()
        status_rows = df[df["status"] == "EXECUTION_STATUS"].copy()
    summaries = []
    for _, row in exec_rows.iterrows():
        inv = row["invocation_id"]
        status_msg = status_rows[status_rows["invocation_id"] == inv]["message"].values
        summaries.append({
            "invocation_id": inv[:12] + "...",
            "invocation_id_full": inv,
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "total_duration_s": row["duration"],
            "status_message": status_msg[0] if len(status_msg) > 0 else "N/A",
        })
    return pd.DataFrame(summaries)


def classify_model_status(model_df, completed_invocations: set | None = None):
    """For each model in an invocation, determine final status.

    Parameters
    ----------
    completed_invocations : set, optional
        Invocation IDs that have an EXECUTION_DURATION / EXECUTION_STATUS
        record, meaning the dbt run finished.  Models that appear to be
        "running" inside a completed invocation are reclassified as
        "unknown" (their end-event was likely lost / truncated).
    """
    if completed_invocations is None:
        completed_invocations = set()

    results = []
    for (inv, entity, model), grp in model_df.groupby(["invocation_id", "entity", "model_name"]):
        if "record_type" in grp.columns:
            has_start = (grp["record_type"] == "MODEL_START").any()
            has_end = (grp["record_type"] == "MODEL_END").any()
            final_rows = grp[grp["record_type"] == "STATUS"]
        else:
            has_start = (grp["status"] == "MODEL_START").any()
            has_end = (grp["status"] == "MODEL_END").any()
            final_rows = grp[grp["status"].isin(["OK", "error", "skipped", "pass"])]

        if not final_rows.empty:
            final_status = final_rows.iloc[-1]["status"]
        elif has_start and not has_end:
            # If the invocation already finished, this model can't still be
            # running — its end event was missed (log truncation, etc.).
            if inv in completed_invocations:
                final_status = "unknown"
            else:
                # If start_time is older than 30 minutes, assume stale
                start_ts = grp["start_time"].min()
                if pd.notna(start_ts):
                    # Ensure timezone-aware comparison
                    if start_ts.tzinfo is None:
                        start_ts = start_ts.tz_localize("UTC")
                    age_minutes = (pd.Timestamp.now(tz="UTC") - start_ts).total_seconds() / 60
                    final_status = "unknown" if age_minutes > 30 else "running"
                else:
                    final_status = "running"
        elif has_end:
            final_status = "OK"
        else:
            final_status = "unknown"

        start = grp["start_time"].min()
        end = grp["end_time"].max() if has_end else pd.NaT
        dur = grp["duration"].max() if has_end else None
        thread = grp["thread_info"].iloc[0] if "thread_info" in grp.columns else ""

        results.append({
            "invocation_id": inv,
            "entity": entity,
            "model_name": model,
            "final_status": final_status,
            "start_time": start,
            "end_time": end,
            "duration_s": dur,
            "thread": thread,
        })
    return pd.DataFrame(results)


def status_icon(status):
    icons = {"OK": "✅", "pass": "✅", "error": "❌", "skipped": "⏭️", "running": "🔄", "unknown": "❓"}
    return icons.get(status, "❓")

def build_invocation_labels(classified: pd.DataFrame) -> dict[str, str]:
    """Build a mapping of invocation_id → friendly display label.

    Label format: ``entity | YYYY-MM-DD HH:MM | inv_id_short``
    When multiple entities share an invocation, they are comma-joined.
    """
    if classified.empty or "invocation_id" not in classified.columns:
        return {}

    labels: dict[str, str] = {}
    for inv_id, grp in classified.groupby("invocation_id"):
        entities = sorted(grp["entity"].dropna().unique())
        entity_str = ", ".join(entities) if entities else "unknown"
        earliest = grp["start_time"].min()
        ts_str = earliest.strftime("%Y-%m-%d %H:%M") if pd.notna(earliest) else "—"
        labels[inv_id] = f"{entity_str} | {ts_str} | {inv_id[:10]}"
    return labels




def get_glue_entities(glue_df: pd.DataFrame) -> list:
    """Get sorted list of entities from Glue metrics."""
    return sorted(glue_df["entity"].unique().tolist())


def format_bytes(val):
    """Format bytes to human-readable."""
    if pd.isna(val) or val == 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(val) < 1024:
            return f"{val:.1f} {unit}"
        val /= 1024
    return f"{val:.1f} PB"


def get_metric_summary_for_session(metrics_df: pd.DataFrame) -> pd.DataFrame:
    """Summarize metrics into a single-row-per-metric table using ALL aggregation."""
    if metrics_df.empty:
        return pd.DataFrame()

    all_df = metrics_df[metrics_df["run_id_type"] == "ALL"]
    if all_df.empty:
        all_df = metrics_df

    summary = all_df.groupby(["metric_name", "label", "unit", "category", "description"]).agg(
        avg=("average", "mean"),
        peak=("maximum", "max"),
        total=("sum", "sum"),
        samples=("sample_count", "sum"),
    ).reset_index()

    return summary.sort_values(["category", "label"])
