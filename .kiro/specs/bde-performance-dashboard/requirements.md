# Requirements Document

## Introduction

The BDE Performance Dashboard extends the existing "Base to Prepared" section of the Data Flow Monitor to include Step Functions monitoring with per-BDE performance analytics. Currently, "Base to Prepared" only shows a dbt monitoring dashboard. This feature adds sub-tabs (mirroring the "Raw to Base" pattern) and introduces BDE-level grouping of Step Function executions, where the BDE name is extracted from execution names by stripping the trailing numeric timestamp and UUID suffix.

## Glossary

- **Dashboard**: The Streamlit-based Data Flow Monitor application (`viz/dbt_run_dashboard.py`).
- **Base_to_Prepared_Section**: The top-level navigation tab for the Base to Prepared data pipeline stage.
- **BDE**: Business Data Entity — a logical grouping derived from Step Function execution names (e.g., `com_avaloq_acp_bde_collat_val_po`).
- **BDE_Name_Parser**: The component that extracts the BDE name from a Step Function execution name by removing the trailing `_{numeric_timestamp}_{uuid}` suffix.
- **BDE_Performance_View**: The UI component that displays aggregated performance metrics grouped by BDE name.
- **SFN_Data_Provider**: The existing module (`viz/sfn_data_provider.py`) that discovers state machines and fetches execution history from the AWS Step Functions API.
- **Execution_Name**: The name assigned to a Step Function execution, following the pattern `{bde_name}_{numeric_timestamp}_{uuid}` (e.g., `com_avaloq_acp_bde_doc_pay_3731604180_019cfaa4-6621-70fb-b7...`).
- **Sub_Tab**: A nested tab within the Base to Prepared section, following the pattern established in the Raw to Base section.

## Requirements

### Requirement 1: Base to Prepared Sub-Tab Navigation

**User Story:** As a data engineer, I want the Base to Prepared section to have sub-tabs for Step Functions and dbt Monitor, so that I can access both Step Function execution data and dbt monitoring from the same section.

#### Acceptance Criteria

1. WHEN a user navigates to the Base to Prepared section, THE Base_to_Prepared_Section SHALL display two sub-tabs labeled "Step Functions" and "dbt Monitor".
2. WHEN the user selects the "Step Functions" sub-tab, THE Base_to_Prepared_Section SHALL render the Step Functions monitoring view for base-to-prepared state machines.
3. WHEN the user selects the "dbt Monitor" sub-tab, THE Base_to_Prepared_Section SHALL render the existing dbt monitoring dashboard with all current functionality preserved.
4. THE Base_to_Prepared_Section SHALL share date/time range controls and auto-refresh settings across both sub-tabs, following the pattern established in the Raw to Base section.

### Requirement 2: BDE Name Extraction from Execution Names

**User Story:** As a data engineer, I want the system to extract BDE names from Step Function execution names, so that I can view performance metrics grouped by BDE.

#### Acceptance Criteria

1. WHEN a Step Function execution name follows the pattern `{bde_name}_{numeric_timestamp}_{uuid}`, THE BDE_Name_Parser SHALL extract the BDE name by removing the trailing numeric timestamp and UUID portions.
2. WHEN the execution name is `com_avaloq_acp_bde_collat_val_po_3731905182_019cfaa8-fde6-7570-0000-000000000000`, THE BDE_Name_Parser SHALL return `com_avaloq_acp_bde_collat_val_po`.
3. WHEN the execution name is `com_avaloq_acp_bde_doc_pay_3731604180_019cfaa4-6621-70fb-b700-000000000000`, THE BDE_Name_Parser SHALL return `com_avaloq_acp_bde_doc_pay`.
4. IF an execution name does not match the expected pattern, THEN THE BDE_Name_Parser SHALL return the full execution name as the BDE name.
5. FOR ALL valid execution names, parsing the BDE name and appending any timestamp-UUID suffix SHALL produce a string that starts with the original BDE name (prefix-preservation property).

### Requirement 3: Step Functions Discovery for Base-to-Prepared

**User Story:** As a data engineer, I want the dashboard to discover base-to-prepared Step Functions state machines, so that I can monitor their executions.

#### Acceptance Criteria

1. THE SFN_Data_Provider SHALL support discovering state machines matching a configurable naming pattern for base-to-prepared pipelines.
2. WHEN the Step Functions sub-tab is loaded, THE Base_to_Prepared_Section SHALL discover state machines using the base-to-prepared naming pattern.
3. IF no state machines match the base-to-prepared pattern, THEN THE Base_to_Prepared_Section SHALL display an informational message indicating no matching state machines were found.

### Requirement 4: Step Functions Execution Monitoring

**User Story:** As a data engineer, I want to see Step Function execution status and history for the base-to-prepared pipeline, so that I can monitor pipeline health.

#### Acceptance Criteria

1. WHEN execution data is fetched, THE Base_to_Prepared_Section SHALL display KPI cards showing total, running, succeeded, failed, timed-out, and aborted execution counts.
2. WHEN execution data is fetched, THE Base_to_Prepared_Section SHALL display an execution history table with environment, execution name, status, start time, stop time, and duration.
3. WHEN failed or timed-out executions exist, THE Base_to_Prepared_Section SHALL display an error analysis section with error frequency and detailed error information.
4. THE Base_to_Prepared_Section SHALL allow filtering executions by environment using a multi-select control.

### Requirement 5: Per-BDE Performance Analytics

**User Story:** As a data engineer, I want to see performance metrics grouped by BDE, so that I can identify slow or problematic BDEs and optimize pipeline performance.

#### Acceptance Criteria

1. WHEN execution data is fetched, THE BDE_Performance_View SHALL group executions by BDE name and display a summary table with execution count, average duration, minimum duration, maximum duration, and median duration per BDE.
2. WHEN execution data is fetched, THE BDE_Performance_View SHALL display a horizontal bar chart showing average execution duration per BDE, sorted by duration descending.
3. WHEN a user selects a specific BDE from the summary, THE BDE_Performance_View SHALL display a drill-down view showing individual execution details for that BDE.
4. WHEN execution data is fetched, THE BDE_Performance_View SHALL display a success rate percentage per BDE (succeeded executions divided by total executions for that BDE).
5. WHEN execution data is fetched, THE BDE_Performance_View SHALL display a scatter chart of execution duration over time, colored by BDE name.

### Requirement 6: Live Execution Monitoring for Base-to-Prepared

**User Story:** As a data engineer, I want to see currently running Step Function executions in the base-to-prepared pipeline, so that I can monitor active processing in real time.

#### Acceptance Criteria

1. WHEN auto-refresh is enabled and executions have status RUNNING, THE Base_to_Prepared_Section SHALL display a live monitoring view showing currently running executions grouped by BDE name.
2. WHEN a running execution is displayed, THE Base_to_Prepared_Section SHALL show the execution name, BDE name, start time, and elapsed duration.
3. WHILE auto-refresh is active, THE Base_to_Prepared_Section SHALL update the execution data at the configured refresh interval.

### Requirement 7: Shared Controls and Auto-Refresh

**User Story:** As a data engineer, I want shared date/time controls and auto-refresh for the Base to Prepared sub-tabs, so that I can control the time window and refresh behavior from a single place.

#### Acceptance Criteria

1. THE Base_to_Prepared_Section SHALL display date range, from time, to time, and auto-refresh controls above the sub-tabs.
2. WHEN auto-refresh is enabled, THE Base_to_Prepared_Section SHALL update the effective end time to the current time on each refresh cycle.
3. WHEN the user changes the date/time range or auto-refresh setting, THE Base_to_Prepared_Section SHALL apply the updated settings to both the Step Functions and dbt Monitor sub-tabs.
4. THE Base*to_Prepared_Section SHALL use session state keys prefixed with `b2p*` to avoid conflicts with the Raw to Base section controls.
