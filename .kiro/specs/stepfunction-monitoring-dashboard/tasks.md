# Implementation Plan: Step Functions Monitoring Dashboard

## Overview

Add a "Step Functions" section to the existing Streamlit Data Flow Monitor app. This involves creating a new data provider module (`viz/sfn_data_provider.py`) for AWS Step Functions API interaction, a section renderer (`viz/sections/step_functions.py`) for the UI, wiring it into the dashboard as a fourth tab, and adding property-based and unit tests. All code is Python, following existing patterns from `base_to_prepared` and `data_provider.py`.

## Tasks

- [x] 1. Create the SFN Data Provider module
  - [x] 1.1 Create `viz/sfn_data_provider.py` with `extract_environment` and `list_matching_state_machines`
    - Import `AWS_PROFILE` from `data_provider.py` for consistent profile resolution
    - Implement `extract_environment(name: str) -> str` using regex `raw-to-base-(.+)-eu-west-1`
    - Implement `list_matching_state_machines(pattern: str) -> pd.DataFrame` that paginates `list_state_machines()`, filters by `fnmatch`, extracts environment, and returns DataFrame with columns: `state_machine_arn`, `name`, `environment`, `creation_date`
    - Handle `botocore.exceptions.ClientError` and return empty DataFrame on failure
    - _Requirements: 1.1, 1.2, 1.3_

  - [ ]\* 1.2 Write property tests for environment extraction and state machine filtering
    - **Property 2: Environment extraction round-trip** — For any valid environment string, `extract_environment(f"raw-to-base-{env}-eu-west-1")` returns the original env
    - **Validates: Requirements 1.2**
    - **Property 1: State machine name pattern filtering** — For any list of names (matching and non-matching), filtering returns exactly those matching the glob pattern
    - **Validates: Requirements 1.1**
    - Create `viz/tests/__init__.py` and `viz/tests/test_sfn_properties.py`
    - Use Hypothesis with `max_examples=100`

  - [x] 1.3 Implement `fetch_executions(state_machine_arns, start_time, end_time) -> pd.DataFrame`
    - Paginate `list_executions()` per state machine, filter by time window
    - Call `describe_execution()` only for FAILED and TIMED_OUT executions to get error details
    - Return DataFrame with columns: `state_machine_arn`, `environment`, `execution_arn`, `execution_name`, `status`, `start_time`, `stop_time`, `duration_seconds`, `error_name`, `error_cause`
    - Calculate `duration_seconds` as `(stop_time - start_time).total_seconds()`, NaN for RUNNING
    - Handle per-state-machine and per-execution API errors gracefully (log warning, continue)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ]\* 1.4 Write property tests for execution fetching logic
    - **Property 3: Time window filtering** — For any set of executions with random start times and any window [start, end], only executions within the window are returned
    - **Validates: Requirements 2.2**
    - **Property 4: Execution DataFrame schema completeness** — For any non-empty result, all required columns are present
    - **Validates: Requirements 2.3**
    - **Property 8: Duration calculation invariant** — For completed executions, `duration_seconds == (stop_time - start_time).total_seconds()`; for RUNNING, duration is NaN
    - **Validates: Requirements 6.1**

- [x] 2. Checkpoint - Ensure data provider tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Create the Step Functions Section renderer
  - [x] 3.1 Create `viz/sections/step_functions.py` with controls and environment filter
    - Implement `render()` function following `base_to_prepared.py` pattern
    - Add header with title and caption
    - Add controls row: date range input, time inputs, auto-refresh selector (Off, 30s, 1m, 5m), fetch button
    - Use `streamlit_autorefresh` for auto-refresh, same pattern as `base_to_prepared.py`
    - Call `list_matching_state_machines()` on load, cache in `st.session_state.sfn_state_machines`
    - Display `st.info()` if no state machines found and return early
    - Add multi-select environment filter populated from discovered state machines
    - Store fetched executions in `st.session_state.sfn_executions`
    - Handle invalid time range (start >= end) with `st.warning()`
    - Handle API errors with `st.error()`
    - Update time window end boundary to current time on auto-refresh cycles
    - _Requirements: 1.1, 1.3, 2.1, 2.2, 2.4, 3.1, 3.2, 3.3, 10.1, 10.2, 10.3_

  - [ ]\* 3.2 Write property test for environment filter correctness
    - **Property 5: Environment filter correctness** — For any execution DataFrame and any subset of environments, filtering returns exactly matching rows; full subset equals original DataFrame
    - **Validates: Requirements 3.2, 3.3**

  - [x] 3.3 Implement KPI cards for execution status summary
    - Display metric cards using existing CSS classes (`metric-card`, `status-ok`, `status-error`, etc.)
    - Show counts for: Total, RUNNING, SUCCEEDED, FAILED, TIMED_OUT, ABORTED
    - Apply environment filter before computing counts
    - Update on data refresh
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ]\* 3.4 Write property test for status count invariant
    - **Property 6: Status count invariant** — Sum of per-status counts equals total row count
    - **Validates: Requirements 4.1, 4.2**

  - [x] 3.5 Implement error analysis section
    - Display table of FAILED and TIMED_OUT executions with columns: environment, execution name, start time, stop time, error name, error cause
    - Display `st.info()` message when no failed/timed-out executions exist
    - Show error frequency summary grouped by `error_name`
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ]\* 3.6 Write property test for error table correctness
    - **Property 7: Error table correctness** — Error table contains exactly FAILED/TIMED_OUT rows; error count by name sums to total error rows
    - **Validates: Requirements 5.1, 5.3**

  - [x] 3.7 Implement execution duration chart and statistics
    - Calculate duration as `stop_time - start_time` for completed executions
    - Display scatter/line chart of durations over time, grouped by environment (using Plotly)
    - Display summary statistics table: min, max, average, median per environment
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]\* 3.8 Write property test for duration statistics correctness
    - **Property 9: Duration statistics correctness** — Computed min/max/avg/median match applying those functions to `duration_seconds` per environment group
    - **Validates: Requirements 6.3**

  - [x] 3.9 Implement execution history table with color-coded status
    - Display sortable table with columns: environment, execution name, status, start time, stop time, duration
    - Apply color coding: green=SUCCEEDED, red=FAILED, orange=TIMED_OUT, blue=RUNNING, grey=ABORTED
    - Default sort by start time descending
    - _Requirements: 7.1, 7.2, 7.3_

  - [ ]\* 3.10 Write property tests for status color mapping and default sort
    - **Property 10: Status color mapping completeness** — Every valid status maps to its designated color, never a default/unknown
    - **Validates: Requirements 7.2**
    - **Property 11: Default sort order** — Default-sorted table has rows in non-increasing start_time order
    - **Validates: Requirements 7.3**

  - [x] 3.11 Implement execution status distribution chart
    - Display pie or stacked bar chart of status distribution using Plotly
    - When multiple environments selected, show distribution per environment
    - _Requirements: 8.1, 8.2_

- [x] 4. Checkpoint - Ensure section renderer and all property tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Wire into the existing dashboard
  - [x] 5.1 Register the new section in `viz/sections/__init__.py`
    - Add `from sections.step_functions import render as render_step_functions`
    - _Requirements: 9.1_

  - [x] 5.2 Add the "Step Functions" tab in `viz/dbt_run_dashboard.py`
    - Import `render_step_functions` from `sections`
    - Add `"Step Functions"` to the `SECTIONS` list
    - Add a fourth tab and call `render_step_functions()` inside it
    - Initialize `sfn_state_machines`, `sfn_executions`, `sfn_last_fetch_ts`, `sfn_fetch_requested` in session state
    - _Requirements: 9.1, 9.2, 9.3_

  - [x] 5.3 Update `viz/requirements.txt` to add `hypothesis` for testing
    - Add `hypothesis>=6.0.0` to requirements.txt
    - _Requirements: Testing infrastructure_

- [x] 6. Final checkpoint - Ensure all tests pass and dashboard loads
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests use Hypothesis with `max_examples=100` and are located in `viz/tests/test_sfn_properties.py`
- All boto3 interactions in tests are mocked — no external AWS calls
- The section follows the same CSS classes and layout patterns as `base_to_prepared.py`
- AWS profile resolution reuses `AWS_PROFILE` from `data_provider.py`
