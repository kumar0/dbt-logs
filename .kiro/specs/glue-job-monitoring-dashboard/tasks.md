# Implementation Plan: Glue Job Monitoring Dashboard

## Overview

This plan implements the Glue job monitoring dashboard in three layers: CDK infrastructure (dummy Glue job + Step Function wiring), a Python data provider for the Glue API, and Streamlit dashboard UI with sub-tabs, KPIs, charts, and tables. Tasks are ordered so each builds on the previous, with infrastructure first, then data layer, then UI, and finally integration.

## Tasks

- [x] 1. Create dummy Glue job infrastructure in CDK
  - [x] 1.1 Create the PySpark dummy job script
    - Create `iac/scripts/dummy_job.py` — a minimal PySpark script that sleeps briefly and exits
    - _Requirements: 1.1_

  - [x] 1.2 Add Glue job and S3 script deployment to OrchestrationStack
    - In `iac/lib/orchestration-stack.ts`, extend `OrchestrationStackProps` with `dataLakeBucketName`, `glueJobRoleArn`, and `vpc`
    - Use `s3deploy.BucketDeployment` to upload `dummy_job.py` to `s3://<dataLakeBucket>/glue-scripts/`
    - Create a `glue.CfnJob` named `raw-to-base-dummy-glue-job` with worker type `G.1X`, 2 workers, Glue version `4.0`, `--enable-metrics=true`, `--enable-continuous-cloudwatch-log=true`, timeout 300s, using the existing VPC `vpc-0a2290ed34b346805`
    - Add a `CfnOutput` for the Glue job name
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 1.3 Wire Glue job step into the Step Function definition
    - In `iac/lib/orchestration-stack.ts`, create a `GlueStartJobRun` task with `.sync` integration pattern
    - Pass `entityName` and `runDate` as Glue job arguments
    - Insert the Glue step before the existing `RunDbtBuild` ECS step
    - Add a Catch block that transitions to `DbtRunFailed` with error details in `$.error`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 1.4 Update CDK app entry point to pass new props
    - In `iac/bin/app.ts`, pass `dataLakeBucketName`, `glueJobRoleArn`, and `vpc` from existing stacks to `OrchestrationStack`
    - _Requirements: 1.1, 2.1_

  - [ ]\* 1.5 Write unit tests for Glue job CDK constructs
    - Assert CDK template has Glue job with correct name, worker type `G.1X`, 2 workers, `--enable-metrics=true`
    - Assert CDK template has CfnOutput for Glue job name
    - Assert state machine definition has Glue step before ECS step with `.sync` pattern
    - Assert Glue step has Catch block pointing to failure state
    - Assert Glue step passes `entityName` and `runDate` as arguments
    - _Requirements: 1.1, 1.3, 1.4, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 2. Wire simulated Glue step into test harness
  - [x] 2.1 Add SimulateGlueJob Pass state to SfnTestHarnessStack
    - In `iac/lib/sfn-test-harness-stack.ts`, insert a `SimulateGlueJob{Suffix}` Pass state before `ConfigureParams{Suffix}`
    - Set result payload with mock `JobRunId` and `JobName`
    - Update `StartAt` to point to `SimulateGlueJob{Suffix}`
    - _Requirements: 3.1, 3.2, 3.3_

  - [ ]\* 2.2 Write unit tests for test harness Glue simulation
    - Assert test harness ASL has `SimulateGlueJob` Pass state
    - Assert `SimulateGlueJob` result contains `JobRunId` and `JobName`
    - _Requirements: 3.1, 3.2_

- [x] 3. Checkpoint — Verify infrastructure changes
  - Ensure all CDK code compiles (`npx cdk synth`), ask the user if questions arise.

- [x] 4. Implement Glue job data provider
  - [x] 4.1 Create `viz/glue_job_data_provider.py`
    - Implement `fetch_glue_job_runs(job_name, start_time, end_time) -> pd.DataFrame` returning columns: `job_run_id`, `status`, `start_time`, `completion_time`, `execution_time_sec`, `dpu_count`, `error_message`
    - Use `boto3.Session(profile_name=...)` with the same AWS profile resolution as `data_provider.py` (CLI `--profile` > env `AWS_PROFILE` > IAM role)
    - Call `glue_client.get_job_runs()` with pagination
    - Filter runs by `StartedOn` within the `[start_time, end_time]` window
    - Implement exponential backoff retry via `_retry_on_throttle` (same pattern as `sfn_data_provider.py`)
    - Add module-level TTL cache (60s) keyed by `(job_name, start_time, end_time)`
    - Return empty DataFrame with correct schema on API errors
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]\* 4.2 Write property test: Time Window Filtering (Property 1)
    - **Property 1: Time Window Filtering**
    - Generate random job runs with random start times and a random time window; verify all returned runs fall within `[start, end]`
    - Create `viz/tests/test_glue_job_data_provider.py`
    - **Validates: Requirements 5.1**

  - [ ]\* 4.3 Write property test: Schema Preservation (Property 2)
    - **Property 2: Schema Preservation**
    - Generate random API responses (empty, single, multiple runs); verify DataFrame always has the 7 expected columns
    - Add to `viz/tests/test_glue_job_data_provider.py`
    - **Validates: Requirements 5.2**

  - [ ]\* 4.4 Write unit tests for data provider error handling
    - Test that API errors return empty DataFrame with correct schema
    - Test that `EntityNotFoundException` returns empty DataFrame
    - Test that no runs found returns empty DataFrame
    - Add to `viz/tests/test_glue_job_unit.py`
    - _Requirements: 5.3, 5.4_

- [x] 5. Refactor Raw to Base section with sub-tab navigation
  - [x] 5.1 Lift shared controls into `viz/sections/raw_to_base.py`
    - Extract date/time range controls and auto-refresh selector from `viz/sections/step_functions.py` into `raw_to_base.py`
    - Render shared controls above the sub-tabs
    - Create two `st.tabs`: "Step Functions" and "Glue Job"
    - _Requirements: 4.1, 4.2, 11.1, 11.3_

  - [x] 5.2 Refactor `viz/sections/step_functions.py` to accept shared parameters
    - Change `render()` to accept `start_date`, `start_time`, `end_date`, `end_time`, `auto_refresh` parameters
    - Remove the local date/time controls rendering
    - _Requirements: 4.3, 11.1_

- [x] 6. Implement Glue Job tab dashboard
  - [x] 6.1 Create `viz/sections/glue_job.py` with KPI cards
    - Implement `render_glue_job(start_date, start_time, end_date, end_time, auto_refresh)` function
    - Call `fetch_glue_job_runs` from the data provider
    - Display KPI metric cards for Total, SUCCEEDED, FAILED, TIMEOUT, RUNNING, STOPPED counts
    - Display `st.info()` when no runs found, `st.error()` on API errors
    - Follow the same CSS classes and metric card layout as the Step Functions tab
    - _Requirements: 5.3, 5.4, 6.1, 6.2, 6.3, 11.2_

  - [x] 6.2 Add duration metrics section
    - Calculate duration from `execution_time_sec` for completed runs
    - Display scatter chart of run durations over time
    - Display summary statistics: min, max, average, median
    - Show `st.info()` when no completed runs exist
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 6.3 Add error analysis section
    - Display table of FAILED and TIMEOUT runs with: job run ID, start time, completion time, execution time, error message
    - Show `st.info("All runs succeeded — no errors found")` when no failed/timed-out runs
    - _Requirements: 8.1, 8.2_

  - [x] 6.4 Add run history table
    - Display sortable table of all runs with columns: job run ID, status, start time, completion time, execution time, DPU allocation
    - Apply color coding to status column: green=SUCCEEDED, red=FAILED, orange=TIMEOUT, blue=RUNNING, grey=STOPPED
    - Sort by start time descending by default
    - _Requirements: 9.1, 9.2, 9.3_

  - [x] 6.5 Add cost estimation section
    - Calculate per-run cost: `dpu_count × (execution_time_sec / 3600) × 0.44`
    - Display total estimated cost and average cost per run
    - Guard against division by zero when run count is 0
    - _Requirements: 10.1, 10.2, 10.3_

  - [ ]\* 6.6 Write property test: Status Count Correctness (Property 3)
    - **Property 3: Status Count Correctness**
    - Generate random DataFrames with arbitrary status distributions; verify computed counts match actual row counts per status and total equals DataFrame length
    - Create `viz/tests/test_glue_job_dashboard.py`
    - **Validates: Requirements 6.1, 6.2**

  - [ ]\* 6.7 Write property test: Duration Statistics Correctness (Property 4)
    - **Property 4: Duration Statistics Correctness**
    - Generate random lists of positive floats as execution times; verify min/max/avg/median match numpy/pandas computations
    - Add to `viz/tests/test_glue_job_dashboard.py`
    - **Validates: Requirements 7.1, 7.3**

  - [ ]\* 6.8 Write property test: Error Run Filtering (Property 5)
    - **Property 5: Error Run Filtering**
    - Generate random DataFrames with mixed statuses; verify filtered result contains only FAILED/TIMEOUT rows
    - Add to `viz/tests/test_glue_job_dashboard.py`
    - **Validates: Requirements 8.1**

  - [ ]\* 6.9 Write property test: Status Color Mapping Completeness (Property 6)
    - **Property 6: Status Color Mapping Completeness**
    - For all statuses in {SUCCEEDED, FAILED, TIMEOUT, RUNNING, STOPPED}, verify the mapping returns the expected color
    - Add to `viz/tests/test_glue_job_dashboard.py`
    - **Validates: Requirements 9.2**

  - [ ]\* 6.10 Write property test: Default Sort Order (Property 7)
    - **Property 7: Default Sort Order**
    - Generate random DataFrames with random timestamps; verify after sorting, each row's `start_time >= next row's start_time`
    - Add to `viz/tests/test_glue_job_dashboard.py`
    - **Validates: Requirements 9.3**

  - [ ]\* 6.11 Write property test: Cost Calculation Correctness (Property 8)
    - **Property 8: Cost Calculation Correctness**
    - Generate random DPU counts and execution times; verify cost = `dpu × (time/3600) × 0.44`, total = sum, average = total/count
    - Add to `viz/tests/test_glue_job_dashboard.py`
    - **Validates: Requirements 10.1, 10.2, 10.3**

  - [ ]\* 6.12 Write unit tests for dashboard edge cases
    - Test empty error DataFrame shows success message
    - Test cost calculation handles zero execution time
    - Test cost calculation handles zero DPU count
    - Add to `viz/tests/test_glue_job_unit.py`
    - _Requirements: 8.2, 10.1_

- [x] 7. Wire Glue Job tab into Raw to Base section
  - [x] 7.1 Connect `glue_job.py` render function in `raw_to_base.py`
    - Import `render_glue_job` from `sections.glue_job`
    - Call it inside the "Glue Job" tab with shared time range parameters
    - Ensure "Step Functions" is the default active tab
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 8. Update CHANGES.md
  - Add a new entry at the top of `CHANGES.md` summarizing the Glue job monitoring dashboard feature and listing all changed files

- [x] 9. Final checkpoint — Verify everything works
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation uses Python for the data provider and dashboard (viz/), and TypeScript for CDK infrastructure (iac/)
