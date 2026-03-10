# Requirements Document

## Introduction

A Step Functions monitoring and visualization dashboard integrated into the existing Streamlit "Data Flow Monitor" application. The dashboard provides real-time and historical visibility into AWS Step Functions executions matching the naming pattern `raw-to-base-*-eu-west-1`, covering execution status counts, error analysis, duration metrics, and execution history across environments (dev2, dint1, uat1, prd1, etc.).

## Glossary

- **Dashboard**: The Streamlit-based "Data Flow Monitor" web application located in `/viz`.
- **Step_Functions_Section**: A new top-level navigation section within the Dashboard dedicated to Step Functions monitoring.
- **SFN_Data_Provider**: The module responsible for querying AWS Step Functions APIs via boto3 and returning structured DataFrames.
- **Execution**: A single run of a Step Functions state machine, identified by its execution ARN.
- **State_Machine**: An AWS Step Functions state machine matching the naming pattern `raw-to-base-*-eu-west-1`.
- **Environment**: The deployment environment identifier embedded in the state machine name (e.g., dev2, dint1, uat1, prd1).
- **Execution_Status**: One of RUNNING, SUCCEEDED, FAILED, TIMED_OUT, or ABORTED as reported by the Step Functions API.
- **Error_Detail**: The error name and cause information attached to a failed or timed-out Execution.

## Requirements

### Requirement 1: Discover State Machines

**User Story:** As a developer, I want the dashboard to automatically discover all Step Functions state machines matching the naming pattern, so that I do not need to manually configure each environment.

#### Acceptance Criteria

1. WHEN the Step_Functions_Section loads, THE SFN_Data_Provider SHALL list all state machines whose names match the pattern `raw-to-base-*-eu-west-1`.
2. THE SFN_Data_Provider SHALL extract the Environment identifier from each discovered State_Machine name.
3. IF no state machines matching the pattern are found, THEN THE Step_Functions_Section SHALL display an informational message indicating zero state machines were discovered.

### Requirement 2: Fetch Execution History

**User Story:** As a developer, I want to retrieve execution history for selected state machines within a configurable time window, so that I can analyze recent and historical runs.

#### Acceptance Criteria

1. THE Step_Functions_Section SHALL provide date and time range controls for selecting the query window.
2. WHEN the user clicks a fetch button, THE SFN_Data_Provider SHALL retrieve executions for all discovered State_Machines within the selected time window.
3. THE SFN_Data_Provider SHALL retrieve execution details including: execution ARN, execution name, status, start time, stop time, and error information for each Execution.
4. IF the Step Functions API returns an error, THEN THE Step_Functions_Section SHALL display the error message to the user.

### Requirement 3: Environment Filter

**User Story:** As a developer, I want to filter the dashboard view by environment, so that I can focus on a specific deployment stage.

#### Acceptance Criteria

1. THE Step_Functions_Section SHALL provide a multi-select filter populated with all discovered Environment values.
2. WHEN the user selects one or more environments, THE Step_Functions_Section SHALL display data only for the selected environments.
3. WHEN no environment filter is applied, THE Step_Functions_Section SHALL display data for all discovered environments.

### Requirement 4: Execution Status Summary KPIs

**User Story:** As a developer, I want to see at-a-glance counts of executions by status, so that I can quickly assess the health of the data pipeline.

#### Acceptance Criteria

1. THE Step_Functions_Section SHALL display KPI cards showing the count of executions in each Execution_Status: RUNNING, SUCCEEDED, FAILED, TIMED_OUT, and ABORTED.
2. THE Step_Functions_Section SHALL display the total number of executions across all statuses.
3. WHEN execution data is refreshed, THE Step_Functions_Section SHALL update all KPI cards to reflect the latest counts.

### Requirement 5: Error Analysis

**User Story:** As a developer, I want to see details about failed executions including error reasons, so that I can diagnose and resolve pipeline failures.

#### Acceptance Criteria

1. THE Step_Functions_Section SHALL display a table of failed and timed-out executions including: environment, execution name, start time, stop time, error name, and error cause.
2. WHEN there are no failed or timed-out executions, THE Step_Functions_Section SHALL display a message indicating all executions succeeded.
3. THE Step_Functions_Section SHALL group or count errors by error name to highlight recurring failure patterns.

### Requirement 6: Execution Duration Metrics

**User Story:** As a developer, I want to see how long executions take, so that I can identify performance trends and outliers.

#### Acceptance Criteria

1. THE Step_Functions_Section SHALL calculate execution duration as the difference between stop time and start time for each completed Execution.
2. THE Step_Functions_Section SHALL display a chart showing execution durations over time, grouped by Environment.
3. THE Step_Functions_Section SHALL display summary statistics for execution duration: minimum, maximum, average, and median per Environment.

### Requirement 7: Execution History Table

**User Story:** As a developer, I want to browse a detailed table of all executions, so that I can inspect individual runs.

#### Acceptance Criteria

1. THE Step_Functions_Section SHALL display a sortable table of all executions with columns: environment, execution name, status, start time, stop time, and duration.
2. THE Step_Functions_Section SHALL apply color coding to the status column: green for SUCCEEDED, red for FAILED, orange for TIMED_OUT, blue for RUNNING, and grey for ABORTED.
3. THE Step_Functions_Section SHALL sort the execution table by start time in descending order by default.

### Requirement 8: Execution Status Distribution Chart

**User Story:** As a developer, I want a visual breakdown of execution statuses, so that I can quickly understand the success rate across environments.

#### Acceptance Criteria

1. THE Step_Functions_Section SHALL display a chart showing the distribution of Execution_Status values.
2. WHEN multiple environments are selected, THE Step_Functions_Section SHALL show the status distribution per Environment.

### Requirement 9: Integration with Existing Dashboard

**User Story:** As a developer, I want the Step Functions monitoring to be a section within the existing Data Flow Monitor, so that all pipeline monitoring is in one place.

#### Acceptance Criteria

1. THE Dashboard SHALL include a "Step Functions" tab alongside the existing "Raw to Base", "Base to Prepared", and "Notification" tabs.
2. THE Step_Functions_Section SHALL follow the same visual styling (CSS classes, metric cards, layout patterns) as the existing Base_to_Prepared section.
3. THE Step_Functions_Section SHALL use the same AWS profile resolution logic (CLI --profile > env AWS_PROFILE > IAM role) as the existing SFN_Data_Provider.

### Requirement 10: Auto-Refresh Support

**User Story:** As a developer, I want the Step Functions dashboard to auto-refresh, so that I can monitor running executions without manually reloading.

#### Acceptance Criteria

1. THE Step_Functions_Section SHALL provide an auto-refresh selector with options: Off, 30s, 1m, 5m.
2. WHILE auto-refresh is enabled, THE Step_Functions_Section SHALL re-fetch execution data at the selected interval.
3. WHEN auto-refresh is enabled, THE Step_Functions_Section SHALL update the time window end boundary to the current time on each refresh cycle.
