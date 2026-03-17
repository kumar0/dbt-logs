# Requirements Document

## Introduction

The existing "Raw to Base" section in the Data Flow Monitor dashboard currently renders only a Step Functions monitoring view. This feature extends the Raw to Base section to also monitor AWS Glue job performance. A dummy Glue job is created in the CDK infrastructure and wired into the existing `raw-to-base-*` Step Function as a step. The Raw to Base section gains sub-tabs: one for Step Function performance and one for Glue job performance, giving developers a unified view of the full raw-to-base pipeline.

## Glossary

- **Dashboard**: The Streamlit-based "Data Flow Monitor" web application located in `/viz`.
- **Raw_to_Base_Section**: The top-level navigation section in the Dashboard dedicated to the raw-to-base pipeline, rendered by `viz/sections/raw_to_base.py`.
- **Step_Functions_Tab**: A sub-tab within the Raw_to_Base_Section that displays the existing Step Functions monitoring content.
- **Glue_Job_Tab**: A sub-tab within the Raw_to_Base_Section that displays Glue job execution metrics and performance data.
- **Dummy_Glue_Job**: A minimal AWS Glue job created via CDK that performs a trivial operation (e.g., a short PySpark sleep/pass script) for testing and dashboard development purposes.
- **Glue_Data_Provider**: The module responsible for querying AWS Glue and CloudWatch APIs to retrieve Glue job run history and metrics.
- **Orchestration_State_Machine**: The Step Functions state machine (`raw-to-base-*-eu-west-1`) that orchestrates the raw-to-base pipeline.
- **Glue_Job_Run**: A single execution of a Glue job, identified by its job run ID.
- **Glue_Job_Run_Status**: One of STARTING, RUNNING, STOPPING, STOPPED, SUCCEEDED, FAILED, TIMEOUT, or ERROR as reported by the Glue API.

## Requirements

### Requirement 1: Create Dummy Glue Job Infrastructure

**User Story:** As a developer, I want a dummy Glue job defined in CDK, so that I can test the Glue monitoring dashboard without needing a real data transformation workload.

#### Acceptance Criteria

1. THE CDK infrastructure SHALL define a Glue job named `raw-to-base-dummy-glue-job` with a minimal PySpark script that completes within 60 seconds.
2. THE Dummy_Glue_Job SHALL use the existing VPC `vpc-0a2290ed34b346805` for network configuration.
3. THE Dummy_Glue_Job SHALL use worker type `G.1X` with 2 workers as the default configuration.
4. THE Dummy_Glue_Job SHALL have CloudWatch metrics enabled (`--enable-metrics=true`).
5. THE CDK infrastructure SHALL create an S3 location for the Glue job script within the existing data lake bucket.
6. THE CDK infrastructure SHALL output the Glue job name as a CloudFormation output.

### Requirement 2: Wire Glue Job into Step Function

**User Story:** As a developer, I want the dummy Glue job integrated into the raw-to-base Step Function, so that the Glue job executes as part of the pipeline and appears in execution history.

#### Acceptance Criteria

1. THE Orchestration_State_Machine SHALL include a Glue job step that invokes the Dummy_Glue_Job before the existing ECS RunTask step.
2. WHEN the Glue job step succeeds, THE Orchestration_State_Machine SHALL proceed to the ECS RunTask step.
3. IF the Glue job step fails, THEN THE Orchestration_State_Machine SHALL transition to the failure state with the Glue error details captured in the error output.
4. THE Glue job step SHALL pass the `entityName` and `runDate` input parameters as Glue job arguments.
5. THE Orchestration_State_Machine SHALL use the `.sync` integration pattern for the Glue job step to wait for completion.

### Requirement 3: Wire Glue Job into Test Harness Step Function

**User Story:** As a developer, I want the test harness Step Functions to also include a simulated Glue job step, so that the dashboard can be tested without deploying the full orchestration stack.

#### Acceptance Criteria

1. THE SfnTestHarnessStack SHALL include a Pass state simulating a Glue job step before the existing Wait state in each test state machine.
2. THE simulated Glue job step SHALL set a result payload containing a mock `JobRunId` and `JobName` in the state machine execution data.
3. WHEN the test harness state machine executes, THE simulated Glue job step SHALL appear in the execution history as a distinct step.

### Requirement 4: Raw to Base Sub-Tab Navigation

**User Story:** As a developer, I want the Raw to Base section to have sub-tabs for Step Functions and Glue job monitoring, so that I can switch between the two views within the same section.

#### Acceptance Criteria

1. THE Raw_to_Base_Section SHALL display two sub-tabs labeled "Step Functions" and "Glue Job".
2. WHEN the Raw_to_Base_Section loads, THE Dashboard SHALL display the "Step Functions" sub-tab as the default active sub-tab.
3. WHEN the user selects the "Step Functions" sub-tab, THE Dashboard SHALL display the existing Step Functions monitoring content.
4. WHEN the user selects the "Glue Job" sub-tab, THE Dashboard SHALL display the Glue job monitoring content.

### Requirement 5: Glue Job Run Discovery and Fetching

**User Story:** As a developer, I want the dashboard to fetch Glue job run history, so that I can see execution details for the raw-to-base Glue job.

#### Acceptance Criteria

1. THE Glue_Data_Provider SHALL retrieve job runs for the `raw-to-base-dummy-glue-job` Glue job within the user-selected time window.
2. THE Glue_Data_Provider SHALL retrieve run details including: job run ID, status, start time, completion time, execution time in seconds, error message, and allocated DPU count.
3. IF the Glue API returns an error, THEN THE Glue_Job_Tab SHALL display the error message to the user.
4. IF no job runs are found within the selected time window, THEN THE Glue_Job_Tab SHALL display an informational message indicating zero runs were found.
5. THE Glue_Data_Provider SHALL use the same AWS profile resolution logic (CLI `--profile` > env `AWS_PROFILE` > IAM role) as the existing SFN_Data_Provider.

### Requirement 6: Glue Job Execution Status KPIs

**User Story:** As a developer, I want to see at-a-glance counts of Glue job runs by status, so that I can quickly assess the health of the Glue job.

#### Acceptance Criteria

1. THE Glue_Job_Tab SHALL display KPI cards showing the count of job runs in each Glue_Job_Run_Status: SUCCEEDED, FAILED, TIMEOUT, RUNNING, and STOPPED.
2. THE Glue_Job_Tab SHALL display the total number of job runs across all statuses.
3. WHEN job run data is refreshed, THE Glue_Job_Tab SHALL update all KPI cards to reflect the latest counts.

### Requirement 7: Glue Job Duration Metrics

**User Story:** As a developer, I want to see how long Glue job runs take, so that I can identify performance trends and outliers.

#### Acceptance Criteria

1. THE Glue_Job_Tab SHALL calculate job run duration from the execution time reported by the Glue API for each completed Glue_Job_Run.
2. THE Glue_Job_Tab SHALL display a chart showing job run durations over time.
3. THE Glue_Job_Tab SHALL display summary statistics for job run duration: minimum, maximum, average, and median.

### Requirement 8: Glue Job Error Analysis

**User Story:** As a developer, I want to see details about failed Glue job runs, so that I can diagnose and resolve failures.

#### Acceptance Criteria

1. THE Glue_Job_Tab SHALL display a table of failed and timed-out job runs including: job run ID, start time, completion time, execution time, and error message.
2. WHEN there are no failed or timed-out job runs, THE Glue_Job_Tab SHALL display a message indicating all runs succeeded.

### Requirement 9: Glue Job Run History Table

**User Story:** As a developer, I want to browse a detailed table of all Glue job runs, so that I can inspect individual executions.

#### Acceptance Criteria

1. THE Glue_Job_Tab SHALL display a sortable table of all job runs with columns: job run ID, status, start time, completion time, execution time, and DPU allocation.
2. THE Glue_Job_Tab SHALL apply color coding to the status column: green for SUCCEEDED, red for FAILED, orange for TIMEOUT, blue for RUNNING, and grey for STOPPED.
3. THE Glue_Job_Tab SHALL sort the job run table by start time in descending order by default.

### Requirement 10: Glue Job Cost Estimation

**User Story:** As a developer, I want to see estimated costs for Glue job runs, so that I can monitor spending and right-size the job configuration.

#### Acceptance Criteria

1. THE Glue_Job_Tab SHALL calculate estimated cost per job run using the formula: DPU count multiplied by execution time in hours multiplied by the Glue DPU-hour rate of $0.44.
2. THE Glue_Job_Tab SHALL display total estimated cost across all job runs in the selected time window.
3. THE Glue_Job_Tab SHALL display average cost per job run.

### Requirement 11: Shared Controls and Styling

**User Story:** As a developer, I want the Glue job tab to share the same date/time controls and visual styling as the Step Functions tab, so that the dashboard feels cohesive.

#### Acceptance Criteria

1. THE Raw_to_Base_Section SHALL provide shared date and time range controls above the sub-tabs that apply to both the Step_Functions_Tab and the Glue_Job_Tab.
2. THE Glue_Job_Tab SHALL follow the same visual styling (CSS classes, metric cards, layout patterns) as the Step_Functions_Tab.
3. THE Glue_Job_Tab SHALL provide an auto-refresh selector with options: Off, 30s, 1m, 5m, consistent with the Step_Functions_Tab.
