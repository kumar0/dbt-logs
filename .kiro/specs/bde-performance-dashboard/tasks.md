# Implementation Plan: BDE Performance Dashboard

## Overview

This plan implements the BDE Performance Dashboard by extending the Base to Prepared section with sub-tab navigation (mirroring Raw to Base), adding a BDE name parser, a Step Functions sub-tab with per-BDE performance analytics, and extracting the existing dbt dashboard into a dedicated sub-tab module. Tasks are ordered: utility module first, then data provider extension, then UI refactoring, then new Step Functions sub-tab, and finally wiring and integration.

## Tasks

- [x] 1. Create BDE name parser utility module
  - [x] 1.1 Create `viz/bde_parser.py` with `extract_bde_name()` function
    - Implement regex pattern `^(.+)_(\d+)_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}.*)$` to match `{bde_name}_{numeric_timestamp}_{uuid}`
    - Return group 1 (BDE name) on match, return full input string on no match
    - Handle empty strings gracefully
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ]\* 1.2 Write property test: BDE Name Round-Trip Parsing (Property 1)
    - **Property 1: BDE Name Round-Trip Parsing**
    - Generate random BDE names (underscore-separated lowercase alphanumeric segments), numeric timestamps, and valid UUIDs; compose into `{bde_name}_{timestamp}_{uuid}` and verify `extract_bde_name()` returns the original BDE name
    - Create `viz/tests/test_bde_performance.py`
    - **Validates: Requirements 2.1, 2.5**

  - [ ]\* 1.3 Write property test: Non-Matching Names Returned Unchanged (Property 2)
    - **Property 2: Non-Matching Names Returned Unchanged**
    - Generate random strings that do not match the `{bde_name}_{numeric_timestamp}_{uuid}` pattern; verify `extract_bde_name()` returns the input unchanged
    - Add to `viz/tests/test_bde_performance.py`
    - **Validates: Requirements 2.4**

  - [ ]\* 1.4 Write unit tests for concrete BDE parser examples
    - Test `com_avaloq_acp_bde_collat_val_po_3731905182_019cfaa8-fde6-7570-0000-000000000000` → `com_avaloq_acp_bde_collat_val_po`
    - Test `com_avaloq_acp_bde_doc_pay_3731604180_019cfaa4-6621-70fb-b700-000000000000` → `com_avaloq_acp_bde_doc_pay`
    - Test empty string returns empty string
    - Add to `viz/tests/test_bde_performance.py`
    - _Requirements: 2.2, 2.3, 2.4_

- [x] 2. Extend `viz/sfn_data_provider.py` with base-to-prepared environment extraction
  - [x] 2.1 Add `extract_environment_b2p()` function and update `extract_environment()` to try both patterns
    - Add `_B2P_ENV_RE = re.compile(r"^base-to-prepared-(.+)-eu-west-1$")` regex
    - Implement `extract_environment_b2p(name)` that extracts environment from base-to-prepared state machine names
    - Update `extract_environment()` to try the raw-to-base pattern first, then fall back to the base-to-prepared pattern, then return `"unknown"`
    - _Requirements: 3.1, 3.2_

  - [ ]\* 2.2 Write property test: Environment Filtering Correctness (Property 5)
    - **Property 5: Environment Filtering Correctness**
    - Generate random DataFrames of executions and random subsets of environments; verify filtering by those environments returns only rows whose environment is in the selected set and includes all such rows
    - Add to `viz/tests/test_bde_performance.py`
    - **Validates: Requirements 4.4**

- [x] 3. Checkpoint — Verify parser and data provider
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Refactor `viz/sections/base_to_prepared.py` with sub-tab navigation
  - [x] 4.1 Extract existing dbt monitor logic into `viz/sections/b2p_dbt_monitor.py`
    - Create `render_b2p_dbt_monitor(start_date, start_time, end_date, end_time, auto_refresh)` function
    - Move all dbt data fetching, processing, KPI rendering, and tab rendering from current `base_to_prepared.py` into this module
    - Preserve all existing session state keys (unprefixed) for dbt functionality
    - _Requirements: 1.3_

  - [x] 4.2 Rewrite `viz/sections/base_to_prepared.py` with shared controls and sub-tabs
    - Implement `_render_shared_controls()` returning `(start_date, start_time, end_date, end_time, auto_refresh)` using `b2p_` prefixed session state keys, following the `raw_to_base.py` pattern
    - Create two `st.tabs`: "Step Functions" and "dbt Monitor"
    - Import and call `render_b2p_step_functions()` in the Step Functions tab
    - Import and call `render_b2p_dbt_monitor()` in the dbt Monitor tab
    - _Requirements: 1.1, 1.2, 1.4, 7.1, 7.2, 7.3, 7.4_

  - [ ]\* 4.3 Write property test: Session State Key Prefix Invariant (Property 10)
    - **Property 10: Session State Key Prefix Invariant**
    - Verify all session state keys created by the shared controls and Step Functions sub-tab start with `b2p_`
    - Add to `viz/tests/test_bde_performance.py`
    - **Validates: Requirements 7.4**

- [x] 5. Implement Step Functions sub-tab with BDE performance analytics
  - [x] 5.1 Create `viz/sections/b2p_step_functions.py` with core Step Functions monitoring
    - Implement `render_b2p_step_functions(start_date, start_time, end_date, end_time, auto_refresh)`
    - Define `B2P_SFN_PATTERN = "base-to-prepared-*-eu-west-1"`
    - Call `sfn_data_provider.list_matching_state_machines()` with the pattern
    - Display `st.info()` if no state machines found
    - Add environment multi-select filter
    - Enrich execution DataFrame with `bde_name` column using `bde_parser.extract_bde_name()`
    - Display KPI cards: total, running, succeeded, failed, timed out, aborted
    - Display execution history table with environment, execution name, status, start time, stop time, duration
    - Display error analysis section for FAILED/TIMED_OUT executions
    - _Requirements: 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 4.4_

  - [ ]\* 5.2 Write property test: Status Count Correctness (Property 3)
    - **Property 3: Status Count Correctness**
    - Generate random DataFrames with statuses from {SUCCEEDED, FAILED, TIMED_OUT, RUNNING, ABORTED}; verify computed counts match actual row counts per status and total equals DataFrame length
    - Add to `viz/tests/test_bde_performance.py`
    - **Validates: Requirements 4.1**

  - [ ]\* 5.3 Write property test: Error Filtering Correctness (Property 4)
    - **Property 4: Error Filtering Correctness**
    - Generate random DataFrames; verify filtering for errors returns only FAILED/TIMED_OUT rows and result is a subset of the original
    - Add to `viz/tests/test_bde_performance.py`
    - **Validates: Requirements 4.3**

  - [x] 5.4 Add BDE performance analytics section
    - Implement `_render_bde_performance(filtered_df)` within `b2p_step_functions.py`
    - Compute BDE summary table: execution count, avg/min/max/median duration, success rate per BDE
    - Display horizontal bar chart of average duration per BDE sorted descending
    - Display scatter chart of execution duration over time colored by BDE name
    - Implement BDE drill-down: selectbox to pick a BDE, show individual executions for that BDE
    - Handle empty/all-running DataFrames gracefully with `st.info()` messages
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]\* 5.5 Write property test: BDE Summary Aggregation with Success Rate (Property 6)
    - **Property 6: BDE Summary Aggregation with Success Rate**
    - Generate random DataFrames with BDE names and durations; verify summary has one row per unique BDE, correct execution_count, avg/min/max/median duration, and success_rate = (SUCCEEDED count / total) \* 100
    - Add to `viz/tests/test_bde_performance.py`
    - **Validates: Requirements 5.1, 5.4**

  - [ ]\* 5.6 Write property test: BDE Summary Sorted by Average Duration Descending (Property 7)
    - **Property 7: BDE Summary Sorted by Average Duration Descending**
    - Generate random BDE summary tables; verify when sorted for the bar chart, average durations are in descending order
    - Add to `viz/tests/test_bde_performance.py`
    - **Validates: Requirements 5.2**

  - [ ]\* 5.7 Write property test: BDE Drill-Down Filtering (Property 8)
    - **Property 8: BDE Drill-Down Filtering**
    - Generate random DataFrames and pick a BDE name present in the data; verify filtering returns only rows for that BDE and includes all such rows
    - Add to `viz/tests/test_bde_performance.py`
    - **Validates: Requirements 5.3**

  - [x] 5.8 Add live execution monitoring for running executions grouped by BDE
    - Filter for RUNNING status executions
    - Group by BDE name and display execution name, BDE name, start time, elapsed duration
    - Only render when auto-refresh is enabled and running executions exist
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]\* 5.9 Write property test: Running Executions Grouped by BDE (Property 9)
    - **Property 9: Running Executions Grouped by BDE**
    - Generate random DataFrames; verify filtering for RUNNING returns only RUNNING rows, and grouping by bde_name produces groups where every execution has the same BDE name
    - Add to `viz/tests/test_bde_performance.py`
    - **Validates: Requirements 6.1**

- [x] 6. Checkpoint — Verify sub-tab rendering and BDE analytics
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Wire everything together and update entry point
  - [x] 7.1 Verify `dbt_run_dashboard.py` integration
    - Confirm the Base to Prepared tab in `dbt_run_dashboard.py` calls `base_to_prepared.render()` (should already be wired)
    - Verify Step Functions is the first sub-tab (default active)
    - Verify dbt Monitor sub-tab preserves all existing functionality
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 8. Update CHANGES.md
  - Add a new entry at the top of `CHANGES.md` summarizing the BDE Performance Dashboard feature and listing all changed/created files:
    - `viz/bde_parser.py` (new)
    - `viz/sections/base_to_prepared.py` (refactored)
    - `viz/sections/b2p_step_functions.py` (new)
    - `viz/sections/b2p_dbt_monitor.py` (new)
    - `viz/sfn_data_provider.py` (extended)
    - `viz/tests/test_bde_performance.py` (new)

- [x] 9. Final checkpoint — Verify everything works
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The implementation uses Python throughout (Streamlit viz layer)
- The pattern closely follows the existing Raw to Base sub-tab structure (`raw_to_base.py` + `step_functions.py` + `glue_job.py`)
- Session state keys use `b2p_` prefix to avoid conflicts with Raw to Base (`r2b_`) and existing dbt dashboard (unprefixed)
