"""Bug condition exploration test — ThrottlingException causes data loss without retry.

**Validates: Requirements 1.1, 1.2, 1.4, 2.1, 2.2, 2.4**

This test encodes the EXPECTED (fixed) behavior: when a ThrottlingException
occurs on ListExecutions or describe_execution, the function should retry
with backoff and eventually return the data.

On UNFIXED code this test MUST FAIL — the unfixed code skips the state
machine entirely (ListExecutions) or falls back to "Error retrieving details"
(describe_execution) instead of retrying.  Failure confirms the bug exists.
"""

import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_throttle_error():
    """Create a botocore ClientError that mimics ThrottlingException."""
    error_response = {
        "Error": {
            "Code": "ThrottlingException",
            "Message": "Rate exceeded",
        }
    }
    return botocore.exceptions.ClientError(error_response, "ListExecutions")


def _make_arn(env: str) -> str:
    return f"arn:aws:states:eu-west-1:123456789012:stateMachine:raw-to-base-{env}-eu-west-1"


def _make_exec_arn(env: str, name: str) -> str:
    return f"arn:aws:states:eu-west-1:123456789012:execution:raw-to-base-{env}-eu-west-1:{name}"


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


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

env_strategy = st.sampled_from(["dev2", "prd1", "uat1", "stg1", "dev1"])

arn_list_strategy = st.lists(
    env_strategy,
    min_size=1,
    max_size=5,
    unique=True,
).map(lambda envs: [_make_arn(e) for e in envs])

hours_offset_strategy = st.integers(min_value=1, max_value=48)


# ---------------------------------------------------------------------------
# Tests — ListExecutions throttling
# ---------------------------------------------------------------------------


@given(
    envs=st.lists(env_strategy, min_size=1, max_size=5, unique=True),
    hours_back=hours_offset_strategy,
)
@settings(max_examples=20, deadline=None)
@patch("sfn_data_provider._sfn_client")
def test_list_executions_throttle_retried_and_data_returned(
    mock_client_fn, envs, hours_back,
):
    """ListExecutions ThrottlingException on first call should be retried.

    On UNFIXED code this FAILS because the function skips the throttled SM
    instead of retrying.

    **Validates: Requirements 1.1, 1.2, 2.1, 2.2**
    """
    import sfn_data_provider
    sfn_data_provider._fetch_cache.clear()
    from sfn_data_provider import fetch_executions

    arns = [_make_arn(e) for e in envs]
    throttled_env = envs[0]
    throttled_arn = arns[0]

    start_dt = _NOW - timedelta(hours=hours_back)
    end_dt = _NOW

    client = MagicMock()
    mock_client_fn.return_value = client

    paginator = MagicMock()
    client.get_paginator.return_value = paginator

    # Track call count per ARN to simulate throttle-then-succeed
    call_counts = {}

    def paginate_side_effect(stateMachineArn):
        call_counts.setdefault(stateMachineArn, 0)
        call_counts[stateMachineArn] += 1

        if stateMachineArn == throttled_arn and call_counts[stateMachineArn] == 1:
            raise _make_throttle_error()

        # On retry (or for non-throttled ARNs), return execution data
        env = stateMachineArn.rsplit(":", 1)[-1].replace("raw-to-base-", "").replace("-eu-west-1", "")
        exec_start = start_dt + timedelta(minutes=10)
        exec_stop = exec_start + timedelta(minutes=5)
        return [
            {
                "executions": [
                    _make_execution(env, f"run-{env}", "SUCCEEDED", exec_start, exec_stop)
                ]
            }
        ]

    paginator.paginate.side_effect = paginate_side_effect

    df = fetch_executions(arns, start_dt.isoformat(), end_dt.isoformat())

    # The throttled state machine MUST appear in results (retry succeeded)
    throttled_rows = df[df["state_machine_arn"] == throttled_arn]
    assert len(throttled_rows) > 0, (
        f"Throttled SM {throttled_arn} missing from results — "
        f"no retry was attempted (bug condition confirmed)"
    )

    # DataFrame schema must match expected columns
    assert list(df.columns) == EXPECTED_COLUMNS

    # No ThrottlingException should propagate unhandled — we got a DataFrame
    assert isinstance(df, pd.DataFrame)


# ---------------------------------------------------------------------------
# Tests — describe_execution throttling
# ---------------------------------------------------------------------------


@given(
    env=env_strategy,
    hours_back=hours_offset_strategy,
)
@settings(max_examples=20, deadline=None)
@patch("sfn_data_provider._sfn_client")
def test_describe_execution_throttle_retried_and_error_details_populated(
    mock_client_fn, env, hours_back,
):
    """describe_execution ThrottlingException should be retried, not fall back.

    On UNFIXED code this FAILS because the function catches the exception and
    sets error_name="Error retrieving details" instead of retrying.

    **Validates: Requirements 1.4, 2.4**
    """
    import sfn_data_provider
    sfn_data_provider._fetch_cache.clear()
    from sfn_data_provider import fetch_executions

    arn = _make_arn(env)
    exec_arn = _make_exec_arn(env, "run-fail")

    start_dt = _NOW - timedelta(hours=hours_back)
    end_dt = _NOW
    exec_start = start_dt + timedelta(minutes=10)
    exec_stop = exec_start + timedelta(minutes=5)

    client = MagicMock()
    mock_client_fn.return_value = client

    paginator = MagicMock()
    client.get_paginator.return_value = paginator
    paginator.paginate.return_value = [
        {
            "executions": [
                _make_execution(env, "run-fail", "FAILED", exec_start, exec_stop)
            ]
        }
    ]

    # describe_execution: throttle on first call, succeed on retry
    describe_call_count = {"n": 0}

    def describe_side_effect(executionArn):
        describe_call_count["n"] += 1
        if describe_call_count["n"] == 1:
            raise _make_throttle_error()
        return {
            "error": "States.TaskFailed",
            "cause": "Lambda function timed out",
        }

    client.describe_execution.side_effect = describe_side_effect

    df = fetch_executions([arn], start_dt.isoformat(), end_dt.isoformat())

    assert len(df) == 1
    row = df.iloc[0]

    # The error details should come from the successful retry, NOT the fallback
    assert row["error_name"] != "Error retrieving details", (
        "describe_execution was not retried — fell back to error default "
        "(bug condition confirmed)"
    )
    assert row["error_name"] == "States.TaskFailed"
    assert row["error_cause"] == "Lambda function timed out"

    # Schema check
    assert list(df.columns) == EXPECTED_COLUMNS
