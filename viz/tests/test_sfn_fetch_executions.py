"""Unit tests for sfn_data_provider.fetch_executions."""

import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Ensure viz/ is on the path so imports resolve.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_ARN = "arn:aws:states:eu-west-1:123456789012:stateMachine:raw-to-base-dev2-eu-west-1"
_EXEC_ARN_TPL = "arn:aws:states:eu-west-1:123456789012:execution:raw-to-base-dev2-eu-west-1:{name}"

_NOW = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_execution(name, status, start, stop=None):
    """Build a dict mimicking the shape returned by list_executions."""
    rec = {
        "executionArn": _EXEC_ARN_TPL.format(name=name),
        "name": name,
        "stateMachineArn": _BASE_ARN,
        "status": status,
        "startDate": start,
    }
    if stop is not None:
        rec["stopDate"] = stop
    return rec


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@patch("sfn_data_provider._sfn_client")
def test_basic_succeeded_execution(mock_client_fn):
    """A single SUCCEEDED execution is returned with correct columns and duration."""
    from sfn_data_provider import fetch_executions

    start = _NOW - timedelta(hours=1)
    stop = _NOW - timedelta(minutes=30)

    client = MagicMock()
    mock_client_fn.return_value = client

    paginator = MagicMock()
    client.get_paginator.return_value = paginator
    paginator.paginate.return_value = [
        {"executions": [_make_execution("run-1", "SUCCEEDED", start, stop)]}
    ]

    df = fetch_executions(
        [_BASE_ARN],
        (_NOW - timedelta(hours=2)).isoformat(),
        _NOW.isoformat(),
    )

    assert len(df) == 1
    row = df.iloc[0]
    assert row["status"] == "SUCCEEDED"
    assert row["environment"] == "dev2"
    assert row["execution_name"] == "run-1"
    assert row["duration_seconds"] == pytest.approx(1800.0)
    assert row["error_name"] == ""
    assert row["error_cause"] == ""


@patch("sfn_data_provider._sfn_client")
def test_running_execution_has_nan_duration(mock_client_fn):
    """RUNNING executions have NaT stop_time and NaN duration."""
    from sfn_data_provider import fetch_executions

    start = _NOW - timedelta(minutes=10)

    client = MagicMock()
    mock_client_fn.return_value = client

    paginator = MagicMock()
    client.get_paginator.return_value = paginator
    paginator.paginate.return_value = [
        {"executions": [_make_execution("run-running", "RUNNING", start)]}
    ]

    df = fetch_executions(
        [_BASE_ARN],
        (_NOW - timedelta(hours=1)).isoformat(),
        _NOW.isoformat(),
    )

    assert len(df) == 1
    row = df.iloc[0]
    assert row["status"] == "RUNNING"
    assert pd.isna(row["stop_time"])
    assert pd.isna(row["duration_seconds"])


@patch("sfn_data_provider._sfn_client")
def test_failed_execution_fetches_error_details(mock_client_fn):
    """FAILED executions trigger describe_execution for error details."""
    from sfn_data_provider import fetch_executions

    start = _NOW - timedelta(hours=1)
    stop = _NOW - timedelta(minutes=45)

    client = MagicMock()
    mock_client_fn.return_value = client

    paginator = MagicMock()
    client.get_paginator.return_value = paginator
    exec_arn = _EXEC_ARN_TPL.format(name="run-fail")
    paginator.paginate.return_value = [
        {"executions": [_make_execution("run-fail", "FAILED", start, stop)]}
    ]
    client.describe_execution.return_value = {
        "error": "States.TaskFailed",
        "cause": "Lambda function timed out",
    }

    df = fetch_executions(
        [_BASE_ARN],
        (_NOW - timedelta(hours=2)).isoformat(),
        _NOW.isoformat(),
    )

    client.describe_execution.assert_called_once_with(executionArn=exec_arn)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["error_name"] == "States.TaskFailed"
    assert row["error_cause"] == "Lambda function timed out"


@patch("sfn_data_provider._sfn_client")
def test_timed_out_execution_fetches_error_details(mock_client_fn):
    """TIMED_OUT executions also trigger describe_execution."""
    from sfn_data_provider import fetch_executions

    start = _NOW - timedelta(hours=1)
    stop = _NOW - timedelta(minutes=5)

    client = MagicMock()
    mock_client_fn.return_value = client

    paginator = MagicMock()
    client.get_paginator.return_value = paginator
    paginator.paginate.return_value = [
        {"executions": [_make_execution("run-timeout", "TIMED_OUT", start, stop)]}
    ]
    client.describe_execution.return_value = {
        "error": "States.Timeout",
        "cause": "Execution exceeded max duration",
    }

    df = fetch_executions(
        [_BASE_ARN],
        (_NOW - timedelta(hours=2)).isoformat(),
        _NOW.isoformat(),
    )

    assert len(df) == 1
    assert df.iloc[0]["error_name"] == "States.Timeout"


@patch("sfn_data_provider._sfn_client")
def test_time_window_filtering(mock_client_fn):
    """Only executions within the time window are returned."""
    from sfn_data_provider import fetch_executions

    inside = _NOW - timedelta(hours=1)
    outside_before = _NOW - timedelta(hours=5)
    outside_after = _NOW + timedelta(hours=1)

    client = MagicMock()
    mock_client_fn.return_value = client

    paginator = MagicMock()
    client.get_paginator.return_value = paginator
    paginator.paginate.return_value = [
        {
            "executions": [
                _make_execution("inside", "SUCCEEDED", inside, inside + timedelta(minutes=10)),
                _make_execution("before", "SUCCEEDED", outside_before, outside_before + timedelta(minutes=10)),
                _make_execution("after", "SUCCEEDED", outside_after, outside_after + timedelta(minutes=10)),
            ]
        }
    ]

    df = fetch_executions(
        [_BASE_ARN],
        (_NOW - timedelta(hours=2)).isoformat(),
        _NOW.isoformat(),
    )

    assert len(df) == 1
    assert df.iloc[0]["execution_name"] == "inside"


@patch("sfn_data_provider._sfn_client")
def test_describe_execution_error_handled_gracefully(mock_client_fn):
    """If describe_execution fails, error fields are populated with fallback."""
    from sfn_data_provider import fetch_executions

    start = _NOW - timedelta(hours=1)
    stop = _NOW - timedelta(minutes=30)

    client = MagicMock()
    mock_client_fn.return_value = client

    paginator = MagicMock()
    client.get_paginator.return_value = paginator
    paginator.paginate.return_value = [
        {"executions": [_make_execution("run-fail", "FAILED", start, stop)]}
    ]
    client.describe_execution.side_effect = Exception("Access denied")

    df = fetch_executions(
        [_BASE_ARN],
        (_NOW - timedelta(hours=2)).isoformat(),
        _NOW.isoformat(),
    )

    assert len(df) == 1
    assert df.iloc[0]["error_name"] == "Error retrieving details"
    assert "Access denied" in df.iloc[0]["error_cause"]


@patch("sfn_data_provider._sfn_client")
def test_list_executions_error_skips_state_machine(mock_client_fn):
    """If list_executions fails for one ARN, other ARNs still succeed."""
    from sfn_data_provider import fetch_executions

    arn_ok = "arn:aws:states:eu-west-1:123456789012:stateMachine:raw-to-base-prd1-eu-west-1"
    arn_bad = "arn:aws:states:eu-west-1:123456789012:stateMachine:raw-to-base-uat1-eu-west-1"

    start = _NOW - timedelta(hours=1)
    stop = _NOW - timedelta(minutes=30)

    client = MagicMock()
    mock_client_fn.return_value = client

    paginator = MagicMock()
    client.get_paginator.return_value = paginator

    def paginate_side_effect(stateMachineArn):
        if stateMachineArn == arn_bad:
            raise Exception("Throttled")
        return [
            {
                "executions": [
                    {
                        "executionArn": f"{arn_ok}:exec1",
                        "name": "exec1",
                        "stateMachineArn": arn_ok,
                        "status": "SUCCEEDED",
                        "startDate": start,
                        "stopDate": stop,
                    }
                ]
            }
        ]

    paginator.paginate.side_effect = paginate_side_effect

    df = fetch_executions(
        [arn_bad, arn_ok],
        (_NOW - timedelta(hours=2)).isoformat(),
        _NOW.isoformat(),
    )

    assert len(df) == 1
    assert df.iloc[0]["environment"] == "prd1"


@patch("sfn_data_provider._sfn_client")
def test_empty_arns_returns_empty_dataframe(mock_client_fn):
    """Passing an empty list of ARNs returns an empty DataFrame with correct columns."""
    from sfn_data_provider import fetch_executions

    client = MagicMock()
    mock_client_fn.return_value = client

    df = fetch_executions([], _NOW.isoformat(), (_NOW + timedelta(hours=1)).isoformat())

    assert len(df) == 0
    expected_cols = [
        "state_machine_arn", "environment", "execution_arn", "execution_name",
        "status", "start_time", "stop_time", "duration_seconds",
        "error_name", "error_cause",
    ]
    assert list(df.columns) == expected_cols


@patch("sfn_data_provider._sfn_client")
def test_dataframe_schema_completeness(mock_client_fn):
    """Returned DataFrame always has all required columns."""
    from sfn_data_provider import fetch_executions

    start = _NOW - timedelta(hours=1)
    stop = _NOW - timedelta(minutes=30)

    client = MagicMock()
    mock_client_fn.return_value = client

    paginator = MagicMock()
    client.get_paginator.return_value = paginator
    paginator.paginate.return_value = [
        {"executions": [_make_execution("run-1", "SUCCEEDED", start, stop)]}
    ]

    df = fetch_executions(
        [_BASE_ARN],
        (_NOW - timedelta(hours=2)).isoformat(),
        _NOW.isoformat(),
    )

    expected_cols = {
        "state_machine_arn", "environment", "execution_arn", "execution_name",
        "status", "start_time", "stop_time", "duration_seconds",
        "error_name", "error_cause",
    }
    assert set(df.columns) == expected_cols


@patch("sfn_data_provider._sfn_client")
def test_client_creation_failure_returns_empty(mock_client_fn):
    """If _sfn_client() raises, an empty DataFrame is returned."""
    from sfn_data_provider import fetch_executions

    mock_client_fn.side_effect = Exception("Bad credentials")

    df = fetch_executions(
        [_BASE_ARN],
        _NOW.isoformat(),
        (_NOW + timedelta(hours=1)).isoformat(),
    )

    assert len(df) == 0
    assert "state_machine_arn" in df.columns
