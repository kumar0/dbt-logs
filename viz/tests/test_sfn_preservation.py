"""Preservation property tests — Non-Throttled Behavior Unchanged.

**Validates: Requirements 3.1, 3.2, 3.3, 3.5, 3.6**

These tests verify that for all inputs where no ThrottlingException occurs,
``fetch_executions`` produces the expected DataFrame output — preserving
schema, filtering, error handling, and partial-result behavior.

These tests should PASS on both unfixed and fixed code.
"""

import sys
import os
import math
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
import botocore.exceptions

# Ensure viz/ is on the path so imports resolve.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPECTED_COLUMNS = [
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

_NOW = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

ALL_STATUSES = ["SUCCEEDED", "FAILED", "TIMED_OUT", "RUNNING", "ABORTED"]

NON_THROTTLING_ERRORS = [
    "AccessDeniedException",
    "InvalidArn",
    "StateMachineDoesNotExist",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_arn(env: str) -> str:
    return (
        f"arn:aws:states:eu-west-1:123456789012:"
        f"stateMachine:raw-to-base-{env}-eu-west-1"
    )


def _make_exec_arn(env: str, name: str) -> str:
    return (
        f"arn:aws:states:eu-west-1:123456789012:"
        f"execution:raw-to-base-{env}-eu-west-1:{name}"
    )


def _make_execution(env, name, status, start, stop=None):
    """Build a dict mimicking the shape returned by list_executions."""
    rec = {
        "executionArn": _make_exec_arn(env, name),
        "name": name,
        "stateMachineArn": _make_arn(env),
        "status": status,
        "startDate": start,
    }
    if stop is not None:
        rec["stopDate"] = stop
    return rec


def _make_non_throttle_error(code: str):
    """Create a botocore ClientError with a non-throttling error code."""
    error_response = {
        "Error": {
            "Code": code,
            "Message": f"Simulated {code}",
        }
    }
    return botocore.exceptions.ClientError(error_response, "TestOperation")


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

env_strategy = st.sampled_from(["dev2", "prd1", "uat1", "stg1", "dev1"])

status_strategy = st.sampled_from(ALL_STATUSES)

non_throttle_error_strategy = st.sampled_from(NON_THROTTLING_ERRORS)

hours_offset_strategy = st.integers(min_value=1, max_value=48)


# ---------------------------------------------------------------------------
# Property 1: Schema preservation for all non-throttling inputs
# ---------------------------------------------------------------------------


@given(
    env=env_strategy,
    status=status_strategy,
    hours_back=hours_offset_strategy,
)
@settings(max_examples=30, deadline=None)
@patch("sfn_data_provider._sfn_client")
def test_schema_always_has_expected_columns(mock_client_fn, env, status, hours_back):
    """For all non-throttling inputs, DataFrame schema is always the expected 10 columns.

    **Validates: Requirements 3.1**
    """
    import sfn_data_provider
    sfn_data_provider._fetch_cache.clear()
    from sfn_data_provider import fetch_executions

    arn = _make_arn(env)
    start_dt = _NOW - timedelta(hours=hours_back)
    end_dt = _NOW
    exec_start = start_dt + timedelta(minutes=10)

    client = MagicMock()
    mock_client_fn.return_value = client

    paginator = MagicMock()
    client.get_paginator.return_value = paginator

    # Build execution — RUNNING has no stopDate
    if status == "RUNNING":
        exec_data = _make_execution(env, f"run-{env}", status, exec_start)
    else:
        exec_stop = exec_start + timedelta(minutes=5)
        exec_data = _make_execution(env, f"run-{env}", status, exec_start, exec_stop)

    paginator.paginate.return_value = [{"executions": [exec_data]}]

    # For FAILED/TIMED_OUT, mock describe_execution to succeed
    if status in ("FAILED", "TIMED_OUT"):
        client.describe_execution.return_value = {
            "error": "States.TaskFailed",
            "cause": "Something went wrong",
        }

    df = fetch_executions([arn], start_dt.isoformat(), end_dt.isoformat())

    assert list(df.columns) == EXPECTED_COLUMNS
    assert len(df) == 1
    assert isinstance(df, pd.DataFrame)


# ---------------------------------------------------------------------------
# Property 2: RUNNING executions have NaN duration and NaT stop_time
# ---------------------------------------------------------------------------


@given(
    env=env_strategy,
    hours_back=hours_offset_strategy,
)
@settings(max_examples=30, deadline=None)
@patch("sfn_data_provider._sfn_client")
def test_running_executions_have_nan_duration_and_nat_stop(
    mock_client_fn, env, hours_back,
):
    """For all RUNNING executions, duration_seconds is NaN and stop_time is NaT.

    **Validates: Requirements 3.6**
    """
    import sfn_data_provider
    sfn_data_provider._fetch_cache.clear()
    from sfn_data_provider import fetch_executions

    arn = _make_arn(env)
    start_dt = _NOW - timedelta(hours=hours_back)
    end_dt = _NOW
    exec_start = start_dt + timedelta(minutes=10)

    client = MagicMock()
    mock_client_fn.return_value = client

    paginator = MagicMock()
    client.get_paginator.return_value = paginator

    # RUNNING execution — no stopDate
    exec_data = _make_execution(env, f"run-{env}", "RUNNING", exec_start)
    paginator.paginate.return_value = [{"executions": [exec_data]}]

    df = fetch_executions([arn], start_dt.isoformat(), end_dt.isoformat())

    assert len(df) == 1
    row = df.iloc[0]
    assert row["status"] == "RUNNING"
    assert pd.isna(row["stop_time"])
    assert math.isnan(row["duration_seconds"])


# ---------------------------------------------------------------------------
# Property 3: Non-throttling ListExecutions errors skip SM, others succeed
# ---------------------------------------------------------------------------


@given(
    error_code=non_throttle_error_strategy,
    hours_back=hours_offset_strategy,
)
@settings(max_examples=30, deadline=None)
@patch("sfn_data_provider._sfn_client")
def test_non_throttling_list_error_skips_sm_others_still_return(
    mock_client_fn, error_code, hours_back,
):
    """For all non-throttling ListExecutions errors, the SM is skipped and
    remaining SMs still return data.

    **Validates: Requirements 3.2**
    """
    import sfn_data_provider
    sfn_data_provider._fetch_cache.clear()
    from sfn_data_provider import fetch_executions

    arn_bad = _make_arn("uat1")
    arn_ok = _make_arn("prd1")

    start_dt = _NOW - timedelta(hours=hours_back)
    end_dt = _NOW
    exec_start = start_dt + timedelta(minutes=10)
    exec_stop = exec_start + timedelta(minutes=5)

    client = MagicMock()
    mock_client_fn.return_value = client

    paginator = MagicMock()
    client.get_paginator.return_value = paginator

    def paginate_side_effect(stateMachineArn):
        if stateMachineArn == arn_bad:
            raise _make_non_throttle_error(error_code)
        return [
            {
                "executions": [
                    _make_execution("prd1", "run-prd1", "SUCCEEDED", exec_start, exec_stop)
                ]
            }
        ]

    paginator.paginate.side_effect = paginate_side_effect

    df = fetch_executions(
        [arn_bad, arn_ok], start_dt.isoformat(), end_dt.isoformat()
    )

    # The bad SM is skipped, the good SM still returns data
    assert len(df) == 1
    assert df.iloc[0]["state_machine_arn"] == arn_ok
    assert df.iloc[0]["environment"] == "prd1"
    assert list(df.columns) == EXPECTED_COLUMNS


# ---------------------------------------------------------------------------
# Property 4: Non-throttling describe_execution errors use fallback fields
# ---------------------------------------------------------------------------


@given(
    env=env_strategy,
    error_code=non_throttle_error_strategy,
    hours_back=hours_offset_strategy,
)
@settings(max_examples=30, deadline=None)
@patch("sfn_data_provider._sfn_client")
def test_non_throttling_describe_error_sets_fallback_fields(
    mock_client_fn, env, error_code, hours_back,
):
    """For all non-throttling describe_execution errors, error_name is
    "Error retrieving details" and error_cause contains the exception message.

    **Validates: Requirements 3.3**
    """
    import sfn_data_provider
    sfn_data_provider._fetch_cache.clear()
    from sfn_data_provider import fetch_executions

    arn = _make_arn(env)
    start_dt = _NOW - timedelta(hours=hours_back)
    end_dt = _NOW
    exec_start = start_dt + timedelta(minutes=10)
    exec_stop = exec_start + timedelta(minutes=5)

    client = MagicMock()
    mock_client_fn.return_value = client

    paginator = MagicMock()
    client.get_paginator.return_value = paginator

    exec_data = _make_execution(env, f"run-{env}", "FAILED", exec_start, exec_stop)
    paginator.paginate.return_value = [{"executions": [exec_data]}]

    error = _make_non_throttle_error(error_code)
    client.describe_execution.side_effect = error

    df = fetch_executions([arn], start_dt.isoformat(), end_dt.isoformat())

    assert len(df) == 1
    row = df.iloc[0]
    assert row["error_name"] == "Error retrieving details"
    assert f"Simulated {error_code}" in row["error_cause"]
    assert list(df.columns) == EXPECTED_COLUMNS


# ---------------------------------------------------------------------------
# Property 5: Time window filtering excludes out-of-range executions
# ---------------------------------------------------------------------------


@given(
    env=env_strategy,
    window_hours=st.integers(min_value=1, max_value=24),
    offset_before=st.integers(min_value=1, max_value=48),
    offset_after=st.integers(min_value=1, max_value=48),
)
@settings(max_examples=30, deadline=None)
@patch("sfn_data_provider._sfn_client")
def test_time_window_filtering_excludes_outside_executions(
    mock_client_fn, env, window_hours, offset_before, offset_after,
):
    """Executions with start_time outside [start_dt, end_dt] are excluded.

    **Validates: Requirements 3.5**
    """
    import sfn_data_provider
    sfn_data_provider._fetch_cache.clear()
    from sfn_data_provider import fetch_executions

    arn = _make_arn(env)
    end_dt = _NOW
    start_dt = _NOW - timedelta(hours=window_hours)

    # One execution inside the window
    inside_start = start_dt + timedelta(minutes=10)
    assume(inside_start < end_dt)  # ensure it's actually inside
    inside_stop = inside_start + timedelta(minutes=5)

    # One execution before the window
    before_start = start_dt - timedelta(hours=offset_before)
    before_stop = before_start + timedelta(minutes=5)

    # One execution after the window
    after_start = end_dt + timedelta(hours=offset_after)
    after_stop = after_start + timedelta(minutes=5)

    client = MagicMock()
    mock_client_fn.return_value = client

    paginator = MagicMock()
    client.get_paginator.return_value = paginator

    paginator.paginate.return_value = [
        {
            "executions": [
                _make_execution(env, "inside", "SUCCEEDED", inside_start, inside_stop),
                _make_execution(env, "before", "SUCCEEDED", before_start, before_stop),
                _make_execution(env, "after", "SUCCEEDED", after_start, after_stop),
            ]
        }
    ]

    df = fetch_executions([arn], start_dt.isoformat(), end_dt.isoformat())

    # Only the "inside" execution should be returned
    assert len(df) == 1
    assert df.iloc[0]["execution_name"] == "inside"
    assert list(df.columns) == EXPECTED_COLUMNS
