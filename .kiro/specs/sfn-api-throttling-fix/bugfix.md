# Bugfix Requirements Document

## Introduction

The Step Functions monitoring dashboard (`viz/sections/step_functions.py`) triggers AWS API rate limiting (`ThrottlingException`) when fetching execution history. The `fetch_executions()` function in `viz/sfn_data_provider.py` calls the `ListExecutions` API sequentially for every discovered state machine ARN without any rate limiting, exponential backoff, or caching. When multiple state machines match the `raw-to-base-*-eu-west-1` pattern, the rapid succession of paginated API calls exceeds the AWS Step Functions API rate limit, causing `ThrottlingException: Rate exceeded` errors. This results in missing execution data for some or all state machines in the dashboard.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN `fetch_executions()` is called with multiple state machine ARNs THEN the system fires `ListExecutions` API calls in rapid succession without any delay or backoff, causing `ThrottlingException: Rate exceeded` errors from the AWS Step Functions API.

1.2 WHEN a `ThrottlingException` occurs during `ListExecutions` pagination for a state machine THEN the system logs a warning and skips the entire state machine, losing all execution data for that state machine even though a retry after a short delay would likely succeed.

1.3 WHEN the dashboard auto-refresh is enabled (e.g., every 30 seconds) THEN the system re-fetches all execution data from the API on every refresh cycle without any caching, compounding the rate limiting problem.

1.4 WHEN `describe_execution()` is called for each FAILED or TIMED_OUT execution to retrieve error details THEN the system makes additional unbounded API calls without rate limiting, further contributing to throttling.

### Expected Behavior (Correct)

2.1 WHEN `fetch_executions()` is called with multiple state machine ARNs THEN the system SHALL use exponential backoff with jitter when making `ListExecutions` API calls, retrying on `ThrottlingException` errors before giving up.

2.2 WHEN a `ThrottlingException` occurs during `ListExecutions` pagination for a state machine THEN the system SHALL retry the request with exponential backoff (up to a configurable maximum number of retries) before skipping the state machine.

2.3 WHEN the dashboard fetches execution data THEN the system SHALL cache the results and serve cached data for subsequent requests within a configurable TTL (time-to-live) period, reducing redundant API calls.

2.4 WHEN `describe_execution()` is called for FAILED or TIMED_OUT executions THEN the system SHALL apply the same retry-with-backoff strategy to these calls to avoid contributing to throttling.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN `fetch_executions()` is called with a list of state machine ARNs and no throttling occurs THEN the system SHALL CONTINUE TO return a DataFrame containing execution data for all state machines with the same columns and schema (`state_machine_arn`, `environment`, `execution_arn`, `execution_name`, `status`, `start_time`, `stop_time`, `duration_seconds`, `error_name`, `error_cause`).

3.2 WHEN a non-throttling API error occurs during `ListExecutions` for a specific state machine THEN the system SHALL CONTINUE TO log the error and skip that state machine, returning partial results for the remaining state machines.

3.3 WHEN `describe_execution()` fails with a non-throttling error THEN the system SHALL CONTINUE TO gracefully handle the error by setting `error_name` to `"Error retrieving details"` and `error_cause` to the exception message.

3.4 WHEN `list_matching_state_machines()` is called THEN the system SHALL CONTINUE TO discover and return all state machines matching the `raw-to-base-*-eu-west-1` pattern with the same DataFrame schema.

3.5 WHEN the time window filter is applied to executions THEN the system SHALL CONTINUE TO correctly filter executions by `start_time` within the specified `start_time` and `end_time` range.

3.6 WHEN a RUNNING execution is encountered THEN the system SHALL CONTINUE TO return `NaN` for `duration_seconds` and `NaT` for `stop_time`.

---

### Bug Condition (Formal)

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type FetchExecutionsInput (state_machine_arns, start_time, end_time)
  OUTPUT: boolean

  // The bug triggers when the volume/rate of API calls exceeds the
  // AWS Step Functions rate limit. This correlates with:
  //   - Multiple state machine ARNs being queried in rapid succession
  //   - No backoff/retry on ThrottlingException
  //   - No caching to reduce redundant calls
  RETURN len(X.state_machine_arns) > 0
    AND api_call_rate(X) > AWS_SFN_RATE_LIMIT
END FUNCTION
```

```pascal
// Property: Fix Checking — Throttling Resilience
FOR ALL X WHERE isBugCondition(X) DO
  result ← fetch_executions'(X.state_machine_arns, X.start_time, X.end_time)
  ASSERT result IS DataFrame
    AND no_unhandled_ThrottlingException(result)
    AND result.columns = expected_schema
    AND len(result) >= len(fetch_executions_without_throttling(X))
END FOR
```

```pascal
// Property: Preservation Checking — Non-Throttled Behavior Unchanged
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT fetch_executions(X) = fetch_executions'(X)
END FOR
```
