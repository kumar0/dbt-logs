# SFN API Throttling Fix — Bugfix Design

## Overview

The `fetch_executions()` function in `viz/sfn_data_provider.py` fires `ListExecutions` and `describe_execution()` API calls in rapid succession across all discovered state machines with no backoff, retry, or caching. When multiple state machines match the `raw-to-base-*-eu-west-1` pattern, this exceeds the AWS Step Functions API rate limit, causing `ThrottlingException: Rate exceeded` errors and missing execution data. The fix introduces exponential backoff with jitter on throttled API calls, a configurable retry limit, and a TTL-based in-memory cache to reduce redundant calls on dashboard auto-refresh.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — when the volume/rate of `ListExecutions` and `describe_execution` API calls exceeds the AWS Step Functions rate limit, causing `ThrottlingException` errors.
- **Property (P)**: The desired behavior — API calls are retried with exponential backoff on `ThrottlingException`, and results are cached to reduce call volume.
- **Preservation**: Existing behavior that must remain unchanged — DataFrame schema, non-throttling error handling, time window filtering, partial result return on per-SM failures.
- **`fetch_executions()`**: The function in `viz/sfn_data_provider.py` that iterates over state machine ARNs, calls `ListExecutions` (paginated) for each, and calls `describe_execution()` for FAILED/TIMED_OUT executions.
- **`_sfn_client()`**: Factory function in `viz/sfn_data_provider.py` that creates a boto3 Step Functions client using the resolved AWS profile.
- **ThrottlingException**: AWS `botocore.exceptions.ClientError` with error code `ThrottlingException` or `Throttling`, raised when API rate limits are exceeded.
- **TTL Cache**: Time-to-live in-memory cache that stores `fetch_executions` results and serves them for subsequent calls with the same parameters within the TTL window.

## Bug Details

### Bug Condition

The bug manifests when `fetch_executions()` is called with multiple state machine ARNs. The function iterates over each ARN sequentially, calling the paginated `ListExecutions` API and then `describe_execution()` for each FAILED/TIMED_OUT execution — all without any delay, backoff, or caching. When the cumulative API call rate exceeds the AWS Step Functions rate limit (~5-10 TPS for `ListExecutions`), `ThrottlingException` is raised. The current code catches this as a generic `Exception`, logs a warning, and skips the entire state machine — losing all its execution data even though a retry after a short delay would succeed.

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input of type FetchExecutionsCall (state_machine_arns, start_time, end_time, api_context)
  OUTPUT: boolean

  RETURN len(input.state_machine_arns) > 0
         AND cumulative_api_calls(input) > AWS_SFN_RATE_LIMIT_TPS
         AND any_call_raises(ThrottlingException)
         AND no_retry_attempted()
END FUNCTION
```

### Examples

- **Example 1**: `fetch_executions(["arn:...:raw-to-base-dev2-eu-west-1", "arn:...:raw-to-base-prd1-eu-west-1", "arn:...:raw-to-base-uat1-eu-west-1"], "2025-01-15T10:00:00Z", "2025-01-15T12:00:00Z")` — With 3 state machines each having 50+ executions, the rapid `ListExecutions` pagination + `describe_execution` calls for failures exceed the rate limit. The 2nd or 3rd state machine gets `ThrottlingException` and its data is lost.
- **Example 2**: Dashboard auto-refresh at 30s interval calls `fetch_executions()` repeatedly with the same parameters. Each call makes fresh API calls, compounding the throttling problem even when data hasn't changed.
- **Example 3**: A state machine with 10 FAILED executions triggers 10 sequential `describe_execution()` calls with no delay, contributing to throttling alongside the `ListExecutions` calls.
- **Edge case**: A single state machine ARN with few executions and no failures — unlikely to trigger throttling, should work identically before and after the fix.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- The returned DataFrame schema must remain identical: columns `state_machine_arn`, `environment`, `execution_arn`, `execution_name`, `status`, `start_time`, `stop_time`, `duration_seconds`, `error_name`, `error_cause`.
- Non-throttling API errors (e.g., `AccessDeniedException`) during `ListExecutions` must continue to log and skip that state machine, returning partial results.
- Non-throttling errors during `describe_execution()` must continue to set `error_name = "Error retrieving details"` and `error_cause` to the exception message.
- `list_matching_state_machines()` must continue to discover state machines matching the pattern with the same behavior.
- Time window filtering (`start_time` within `[start_dt, end_dt]`) must continue to work identically.
- RUNNING executions must continue to return `NaN` for `duration_seconds` and `NaT` for `stop_time`.

**Scope:**
All inputs that do NOT trigger `ThrottlingException` should produce exactly the same results as the unfixed code. This includes:

- Calls with a small number of state machines that stay within rate limits
- Calls where all API responses succeed on the first attempt
- Non-throttling error scenarios (AccessDenied, InvalidArn, etc.)

## Hypothesized Root Cause

Based on the bug description and code analysis, the root causes are:

1. **No Retry on ThrottlingException**: The `fetch_executions()` function catches all exceptions from `ListExecutions` pagination as generic `Exception` and immediately skips the state machine. There is no distinction between transient throttling errors (which should be retried) and permanent errors (which should be skipped). Lines 148-152 in `sfn_data_provider.py` show the broad `except Exception as list_exc` handler.

2. **No Rate Limiting Between API Calls**: The `for arn in state_machine_arns` loop (line 127) iterates without any delay between state machines. Each `paginator.paginate()` call fires immediately after the previous one completes, and `describe_execution()` calls within the inner loop add to the burst.

3. **No Caching of Results**: The dashboard's auto-refresh (30s/1m/5m intervals in `step_functions.py` line 79) calls `fetch_executions()` on every cycle. Each call makes fresh API calls even when the same parameters are used, multiplying the API call volume unnecessarily.

4. **Unbounded describe_execution Calls**: For each FAILED or TIMED_OUT execution, `describe_execution()` is called immediately (line 140) with no backoff or batching, adding to the cumulative API call rate.

## Correctness Properties

Property 1: Bug Condition — Throttled API Calls Are Retried

_For any_ `fetch_executions` call where the AWS Step Functions API raises `ThrottlingException` on `ListExecutions` or `describe_execution`, the fixed function SHALL retry the call with exponential backoff and jitter, up to a configurable maximum number of retries, before skipping the state machine or falling back to error defaults.

**Validates: Requirements 2.1, 2.2, 2.4**

Property 2: Preservation — Non-Throttled Behavior Unchanged

_For any_ `fetch_executions` call where no `ThrottlingException` occurs (all API calls succeed on the first attempt or fail with non-throttling errors), the fixed function SHALL produce exactly the same DataFrame output as the original function, preserving schema, filtering, error handling, and partial result behavior.

**Validates: Requirements 3.1, 3.2, 3.3, 3.5, 3.6**

Property 3: Caching — Repeated Calls Within TTL Serve Cached Results

_For any_ two consecutive `fetch_executions` calls with identical parameters (`state_machine_arns`, `start_time`, `end_time`) within the cache TTL window, the second call SHALL return the cached result without making any additional AWS API calls.

**Validates: Requirements 2.3**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `viz/sfn_data_provider.py`

**Function**: `fetch_executions()` and supporting helpers

**Specific Changes**:

1. **Add a retry-with-backoff helper**: Create a `_retry_on_throttle(func, *args, max_retries=5, base_delay=1.0, **kwargs)` helper that wraps an API call and retries on `ThrottlingException` with exponential backoff and jitter. Detect throttling by checking `ClientError.response['Error']['Code']` for `ThrottlingException` or `Throttling`.

2. **Wrap ListExecutions pagination with retry**: Replace the direct `paginator.paginate(stateMachineArn=arn)` iteration with a retry-aware wrapper. Since pagination yields pages, the retry should wrap each page fetch or use a non-paginator approach (`list_executions` with `nextToken`) to enable per-call retry.

3. **Wrap describe_execution with retry**: Replace the direct `client.describe_execution(executionArn=...)` call with the retry helper so that throttled `describe_execution` calls are retried before falling back to the error default.

4. **Add TTL-based caching**: Implement a simple in-memory cache (e.g., using `functools.lru_cache` with a TTL wrapper, or a custom dict-based cache) for `fetch_executions()`. Cache key should be derived from `(tuple(state_machine_arns), start_time, end_time)`. Cache TTL should be configurable, defaulting to ~60 seconds.

5. **Preserve non-throttling error handling**: Ensure the existing behavior for non-throttling errors is unchanged — `ListExecutions` failures still skip the state machine, `describe_execution` failures still set fallback error fields.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that mock the boto3 client to raise `ThrottlingException` (as a `botocore.exceptions.ClientError`) during `ListExecutions` pagination and `describe_execution` calls. Run these tests on the UNFIXED code to observe that the function skips state machines without retrying.

**Test Cases**:

1. **ListExecutions Throttle Test**: Mock `paginator.paginate()` to raise `ClientError` with code `ThrottlingException` for one ARN — verify the unfixed code skips it without retry (will fail to retry on unfixed code)
2. **describe_execution Throttle Test**: Mock `describe_execution()` to raise `ThrottlingException` — verify the unfixed code falls back to error defaults without retry (will fail to retry on unfixed code)
3. **Multiple ARN Burst Test**: Mock the client to raise `ThrottlingException` on the 2nd of 3 ARNs — verify the unfixed code loses data for that ARN (will lose data on unfixed code)
4. **Repeated Call Test**: Call `fetch_executions()` twice with the same parameters — verify the unfixed code makes full API calls both times (no caching on unfixed code)

**Expected Counterexamples**:

- `ThrottlingException` during `ListExecutions` causes the state machine to be skipped entirely with no retry
- `ThrottlingException` during `describe_execution` causes fallback error fields with no retry
- Repeated calls always hit the API, no caching

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**

```
FOR ALL input WHERE isBugCondition(input) DO
  result := fetch_executions'(input.state_machine_arns, input.start_time, input.end_time)
  ASSERT no_unhandled_ThrottlingException(result)
  ASSERT retry_was_attempted()
  ASSERT result.columns == expected_schema
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT fetch_executions(input) == fetch_executions'(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:

- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for non-throttled API calls, then write property-based tests capturing that behavior. Use `hypothesis` to generate random combinations of state machine ARNs, execution statuses, time windows, and error scenarios — verify the fixed code produces identical output when no throttling occurs.

**Test Cases**:

1. **Schema Preservation**: Generate random execution data (varying statuses, time ranges, error types) and verify the output DataFrame always has the correct schema and values
2. **Time Window Filtering Preservation**: Generate random time windows and execution start times, verify filtering logic is identical
3. **Non-Throttling Error Preservation**: Generate random non-throttling exceptions and verify they are handled identically (skip SM for ListExecutions, fallback fields for describe_execution)
4. **RUNNING Execution Preservation**: Generate RUNNING executions and verify NaN/NaT handling is unchanged

### Unit Tests

- Test retry helper with configurable max retries and verify exponential backoff delays
- Test that `ThrottlingException` on `ListExecutions` triggers retry and eventually succeeds
- Test that `ThrottlingException` on `describe_execution` triggers retry and eventually succeeds
- Test that max retries exceeded still skips the state machine gracefully
- Test cache hit returns cached data without API calls
- Test cache miss makes API calls and stores result
- Test cache expiry after TTL causes fresh API calls

### Property-Based Tests

- Generate random execution lists with varying statuses and verify schema correctness is preserved
- Generate random non-throttling error scenarios and verify identical error handling behavior
- Generate random time windows and execution timestamps to verify filtering preservation

### Integration Tests

- Test full flow: `list_matching_state_machines()` → `fetch_executions()` with mocked throttling, verify complete data returned after retries
- Test dashboard auto-refresh scenario: two rapid calls with same parameters, verify second call uses cache
- Test mixed scenario: some ARNs throttle, some succeed, verify partial results include retried ARNs
