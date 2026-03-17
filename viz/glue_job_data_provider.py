"""
Data provider for AWS Glue job monitoring dashboard.

Fetches Glue job run history via the AWS Glue ``GetJobRuns`` API,
mirroring the patterns established by ``sfn_data_provider.py``.
"""

import time
import random
import logging

import boto3
import botocore.exceptions
import pandas as pd

from data_provider import AWS_PROFILE

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS: int = 60
"""Default time-to-live (in seconds) for the ``fetch_glue_job_runs`` result cache."""

_fetch_cache: dict[tuple, tuple[float, pd.DataFrame]] = {}
"""Module-level cache mapping ``(job_name, start_time, end_time)`` → ``(timestamp, DataFrame)``."""

EXPECTED_COLUMNS = [
    "job_run_id",
    "status",
    "start_time",
    "completion_time",
    "execution_time_sec",
    "dpu_count",
    "error_message",
]
"""Schema columns always present in the returned DataFrame."""


def _empty_dataframe() -> pd.DataFrame:
    """Return an empty DataFrame with the correct Glue job run schema."""
    return pd.DataFrame(columns=EXPECTED_COLUMNS)


def _glue_client():
    """Create a Glue client using the resolved AWS profile."""
    session = boto3.Session(profile_name=AWS_PROFILE) if AWS_PROFILE else boto3.Session()
    return session.client("glue")


def _to_utc_timestamp(value) -> pd.Timestamp:
    """Convert a datetime-like value to a UTC-aware :class:`pd.Timestamp`.

    Handles both tz-naive (assumed UTC) and tz-aware inputs.
    """
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _retry_on_throttle(func, *args, max_retries=5, base_delay=1.0, **kwargs):
    """Call *func* and retry with exponential backoff on throttling errors.

    Parameters
    ----------
    func:
        Callable to invoke (e.g., ``client.get_job_runs``).
    *args:
        Positional arguments forwarded to *func*.
    max_retries:
        Maximum number of retry attempts before re-raising.
    base_delay:
        Base delay in seconds for exponential backoff.
    **kwargs:
        Keyword arguments forwarded to *func*.

    Returns
    -------
    The return value of *func*.

    Raises
    ------
    botocore.exceptions.ClientError
        Re-raised after *max_retries* exhausted for throttling errors,
        or immediately for non-throttling errors.
    Exception
        Any non-ClientError exception is re-raised immediately.
    """
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except botocore.exceptions.ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            if error_code not in ("ThrottlingException", "Throttling"):
                raise
            if attempt >= max_retries:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            logger.info(
                "Throttled (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1,
                max_retries,
                delay,
                exc,
            )
            time.sleep(delay)


def fetch_glue_job_runs(
    job_name: str,
    start_time: str,
    end_time: str,
) -> pd.DataFrame:
    """Fetch Glue job runs within a time window.

    Parameters
    ----------
    job_name:
        Name of the Glue job to query.
    start_time:
        ISO-8601 start of the query window (inclusive).
    end_time:
        ISO-8601 end of the query window (inclusive).

    Returns
    -------
    pd.DataFrame
        DataFrame with columns: ``job_run_id``, ``status``, ``start_time``,
        ``completion_time``, ``execution_time_sec``, ``dpu_count``,
        ``error_message``.

    Errors are logged and an empty DataFrame with the correct schema is
    returned so that callers always receive a valid DataFrame.
    """
    empty = _empty_dataframe()

    start_dt = _to_utc_timestamp(start_time)
    end_dt = _to_utc_timestamp(end_time)

    # --- TTL cache lookup ---
    cache_key = (job_name, start_time, end_time)
    cached = _fetch_cache.get(cache_key)
    if cached is not None:
        cached_ts, cached_df = cached
        if time.time() - cached_ts < CACHE_TTL_SECONDS:
            return cached_df

    try:
        client = _glue_client()
    except Exception as exc:
        logger.error("Failed to create Glue client: %s", exc)
        return empty

    rows: list[dict] = []
    next_token: str | None = None

    try:
        while True:
            kwargs: dict = {"JobName": job_name, "MaxResults": 200}
            if next_token:
                kwargs["NextToken"] = next_token

            response = _retry_on_throttle(client.get_job_runs, **kwargs)

            for run in response.get("JobRuns", []):
                try:
                    run_start = _to_utc_timestamp(run["StartedOn"])
                except Exception:
                    logger.warning("Skipping run with invalid StartedOn: %s", run.get("Id"))
                    continue

                # Filter by time window
                if run_start < start_dt or run_start > end_dt:
                    continue

                completed_on = run.get("CompletedOn")
                completion_ts = _to_utc_timestamp(completed_on) if completed_on else pd.NaT

                execution_time = float(run.get("ExecutionTime", 0))

                # DPU count: prefer MaxCapacity, fall back to NumberOfWorkers
                dpu_count = float(run.get("MaxCapacity", run.get("NumberOfWorkers", 0)))

                rows.append(
                    {
                        "job_run_id": run.get("Id", ""),
                        "status": run.get("JobRunState", ""),
                        "start_time": run_start,
                        "completion_time": completion_ts,
                        "execution_time_sec": execution_time,
                        "dpu_count": dpu_count,
                        "error_message": run.get("ErrorMessage", ""),
                    }
                )

            next_token = response.get("NextToken")
            if not next_token:
                break

    except botocore.exceptions.ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code == "EntityNotFoundException":
            logger.warning("Glue job '%s' not found: %s", job_name, exc)
        else:
            logger.error("Error fetching job runs for '%s': %s", job_name, exc)
        _fetch_cache[cache_key] = (time.time(), empty)
        return empty
    except Exception as exc:
        logger.error("Unexpected error fetching job runs for '%s': %s", job_name, exc)
        _fetch_cache[cache_key] = (time.time(), empty)
        return empty

    if not rows:
        _fetch_cache[cache_key] = (time.time(), empty)
        return empty

    result = pd.DataFrame(rows, columns=EXPECTED_COLUMNS)
    _fetch_cache[cache_key] = (time.time(), result)
    return result
