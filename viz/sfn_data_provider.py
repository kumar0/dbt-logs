"""
Data provider for Step Functions monitoring dashboard.

Discovers state machines matching the naming pattern ``raw-to-base-*-eu-west-1``
and fetches execution history via the AWS Step Functions API.
"""

import re
import time
import random
import logging
from fnmatch import fnmatch

import boto3
import botocore.exceptions
import pandas as pd

from data_provider import AWS_PROFILE

logger = logging.getLogger(__name__)

_ENV_RE = re.compile(r"^raw-to-base-(.+)-eu-west-1$")
_B2P_ENV_RE = re.compile(r"^base-to-prepared-(.+)-eu-west-1$")

CACHE_TTL_SECONDS: int = 60
"""Default time-to-live (in seconds) for the ``fetch_executions`` result cache."""

_fetch_cache: dict[tuple, tuple[float, pd.DataFrame]] = {}
"""Module-level cache mapping ``(arns_tuple, start_time, end_time)`` → ``(timestamp, DataFrame)``."""


def _to_utc_timestamp(value) -> pd.Timestamp:
    """Convert a datetime-like value to a UTC-aware :class:`pd.Timestamp`.

    Handles both tz-naive (assumed UTC) and tz-aware inputs without raising
    the ``Cannot pass a datetime or Timestamp with tzinfo with the tz
    parameter`` error.
    """
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")



def _sfn_client():
    """Create a Step Functions client using the resolved AWS profile."""
    session = boto3.Session(profile_name=AWS_PROFILE) if AWS_PROFILE else boto3.Session()
    return session.client("stepfunctions")



def extract_environment(name: str) -> str:
    """Extract environment identifier from a state machine name.

    Pattern: ``raw-to-base-{environment}-eu-west-1``

    Example::

        >>> extract_environment("raw-to-base-dev2-eu-west-1")
        'dev2'

    Returns an empty string when the name does not match the expected pattern.
    """
    m = _ENV_RE.match(name)
    if m:
        return m.group(1)
    m = _B2P_ENV_RE.match(name)
    return m.group(1) if m else ""


def extract_environment_b2p(name: str) -> str:
    """Extract environment from a base-to-prepared state machine name.

    Pattern: ``base-to-prepared-{environment}-eu-west-1``

    Returns an empty string when the name does not match.
    """
    m = _B2P_ENV_RE.match(name)
    return m.group(1) if m else ""

def _retry_on_throttle(func, *args, max_retries=5, base_delay=1.0, **kwargs):
    """Call *func* and retry with exponential backoff on throttling errors.

    Parameters
    ----------
    func:
        Callable to invoke (e.g., ``client.describe_execution``).
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



def list_matching_state_machines(
    pattern: str = "raw-to-base-*-eu-west-1",
) -> pd.DataFrame:
    """Discover state machines whose names match *pattern*.

    Paginates the ``list_state_machines`` API, filters by *pattern* using
    :func:`fnmatch.fnmatch`, extracts the environment from each name, and
    returns a :class:`~pandas.DataFrame` with columns:

    - ``state_machine_arn`` (str)
    - ``name`` (str)
    - ``environment`` (str)
    - ``creation_date`` (datetime)

    Returns an empty DataFrame (with the correct columns) on API failure.
    """
    columns = ["state_machine_arn", "name", "environment", "creation_date"]
    empty = pd.DataFrame(columns=columns)

    try:
        client = _sfn_client()
    except botocore.exceptions.ClientError as exc:
        logger.error("Failed to create SFN client: %s", exc)
        return empty

    rows: list[dict] = []
    try:
        paginator = client.get_paginator("list_state_machines")
        for page in paginator.paginate():
            for sm in page.get("stateMachines", []):
                name = sm["name"]
                if fnmatch(name, pattern):
                    rows.append(
                        {
                            "state_machine_arn": sm["stateMachineArn"],
                            "name": name,
                            "environment": extract_environment(name),
                            "creation_date": sm["creationDate"],
                        }
                    )
    except botocore.exceptions.ClientError as exc:
        logger.error("Error listing state machines: %s", exc)
        return empty

    if not rows:
        return empty

    df = pd.DataFrame(rows, columns=columns)
    df["creation_date"] = pd.to_datetime(df["creation_date"], utc=True)
    return df


def fetch_executions(
    state_machine_arns: list[str],
    start_time: str,
    end_time: str,
) -> pd.DataFrame:
    """Fetch execution history for given state machines within a time window.

    Parameters
    ----------
    state_machine_arns:
        List of state machine ARNs to query.
    start_time:
        ISO-8601 start of the query window (inclusive).
    end_time:
        ISO-8601 end of the query window (inclusive).

    Returns
    -------
    pd.DataFrame
        DataFrame with columns: ``state_machine_arn``, ``environment``,
        ``execution_arn``, ``execution_name``, ``status``, ``start_time``,
        ``stop_time``, ``duration_seconds``, ``error_name``, ``error_cause``.

    Errors for individual state machines or executions are logged and skipped
    so that partial results are still returned.
    """
    columns = [
        "state_machine_arn",
        "environment",
        "execution_arn",
        "execution_name",
        "status",
        "start_time",
        "stop_time",
        "duration_seconds",
        "error_name",
        "error_cause",
    ]
    empty = pd.DataFrame(columns=columns)

    start_dt = _to_utc_timestamp(start_time)
    end_dt = _to_utc_timestamp(end_time)

    # --- TTL cache lookup ---
    cache_key = (tuple(state_machine_arns), start_time, end_time)
    cached = _fetch_cache.get(cache_key)
    if cached is not None:
        cached_ts, cached_df = cached
        if time.time() - cached_ts < CACHE_TTL_SECONDS:
            return cached_df

    try:
        client = _sfn_client()
    except Exception as exc:
        logger.error("Failed to create SFN client: %s", exc)
        return empty

    rows: list[dict] = []

    for arn in state_machine_arns:
        # Derive the state machine name from the ARN (last segment after ':')
        sm_name = arn.rsplit(":", 1)[-1]
        env = extract_environment(sm_name)

        try:
            paginator = client.get_paginator("list_executions")
            pages = _retry_on_throttle(
                paginator.paginate, stateMachineArn=arn
            )
            for page in pages:
                for exc_info in page.get("executions", []):
                    exc_start = _to_utc_timestamp(exc_info["startDate"])

                    # Filter by time window
                    if exc_start < start_dt or exc_start > end_dt:
                        continue

                    status = exc_info["status"]
                    stop_date = exc_info.get("stopDate")
                    stop_ts = _to_utc_timestamp(stop_date) if stop_date else pd.NaT

                    # Calculate duration
                    if pd.notna(stop_ts):
                        duration = (stop_ts - exc_start).total_seconds()
                    else:
                        duration = float("nan")

                    error_name = ""
                    error_cause = ""

                    # Fetch error details for FAILED and TIMED_OUT executions
                    if status in ("FAILED", "TIMED_OUT"):
                        try:
                            detail = _retry_on_throttle(
                                client.describe_execution,
                                executionArn=exc_info["executionArn"],
                            )
                            error_name = detail.get("error", "")
                            error_cause = detail.get("cause", "")
                        except Exception as desc_exc:
                            logger.warning(
                                "Error describing execution %s: %s",
                                exc_info["executionArn"],
                                desc_exc,
                            )
                            error_name = "Error retrieving details"
                            error_cause = str(desc_exc)

                    rows.append(
                        {
                            "state_machine_arn": arn,
                            "environment": env,
                            "execution_arn": exc_info["executionArn"],
                            "execution_name": exc_info["name"],
                            "status": status,
                            "start_time": exc_start,
                            "stop_time": stop_ts,
                            "duration_seconds": duration,
                            "error_name": error_name,
                            "error_cause": error_cause,
                        }
                    )
        except Exception as list_exc:
            logger.warning(
                "Error listing executions for %s: %s", arn, list_exc
            )
            continue

    if not rows:
        _fetch_cache[cache_key] = (time.time(), empty)
        return empty

    result = pd.DataFrame(rows, columns=columns)
    _fetch_cache[cache_key] = (time.time(), result)
    return result

