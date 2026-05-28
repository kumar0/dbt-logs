# Changes — Dashboard Navigation Sections

## Latest — Athena SQL converter for dbt-glue compiled models

### Summary

New standalone CLI `athena_sql_version/convert_to_athena.py` that turns a dbt model folder's compiled Spark/Iceberg SQL into runnable Athena SQL. Given a folder name (e.g. `order_transform`), it auto-discovers that folder under any `target/run/` directory (printing a "please run `dbt run` first" message and exiting non-zero if missing), then for each `.sql` file: strips the dbt materialization wrapper (`CREATE OR REPLACE TABLE ... AS` / `INSERT INTO ... SELECT`) down to a bare query, drops the `glue_catalog.` catalog prefix, recursively inlines any referenced sibling views (other `.sql` files in the same folder, auto-discovered — no hardcoded list) as subqueries, and transpiles the fully-assembled query once with sqlglot (`read="spark", write="athena"`). Inlining runs on the raw Spark SQL *before* transpilation so dialect handling (notably date/time functions) is applied consistently. Outputs are written as `ath_<name>.sql` into `athena_sql_version/`, mirroring the folder's path from after the `models/` segment downward (e.g. `avqdf/order_transform`). Transpile failures fall back to the inlined pre-transpile SQL rather than dropping the file.

### Files Changed

- `athena_sql_version/convert_to_athena.py` — New: `find_model_folder()` (rglob for the folder under a `target/run` path), `strip_wrapper()`/`strip_catalog()`/`load_body()` (reduce a compiled file to a bare catalog-clean query), `inline_views()` (recursive sibling-view inlining with cycle/depth guards, preserving trailing aliases, matching both `FROM` and `JOIN`), `convert_file()` (inline-then-transpile), `mirror_output_dir()`, and the `argparse` driver.
- `athena_sql_version/requirements.txt` — New: pins `sqlglot`.

---

## Sankey notebook for `sankey_table_relationships.csv`

### Summary

New Jupyter notebook that renders Sankey diagrams from `sankey_table_relationships.csv`. Levels are discovered dynamically via regex `^level(\d+)_table$` on the column names, so dropping any `level*_table` column from the CSV leaves the rest of the chain functional (a self-check cell demonstrates this by removing `level2_table` and re-rendering). Produces both a hand-drawn matplotlib static Sankey (no `kaleido` dependency) and a Plotly interactive Sankey for each adjacent-level pair, plus a combined multi-stage view. Outputs land in `sankey_output/` (gitignored — regenerate by running the notebook).

### Files Changed

- `sankey_diagrams.ipynb` — New: notebook with `detect_levels()` regex-based discovery, `adjacent_flows()` aggregation, `draw_static_sankey()` matplotlib renderer with cubic-bezier ribbons, and `build_interactive_sankey()` Plotly renderer using stage-scoped node indexing so repeated table names across levels don't collapse.
- `.gitignore` — Added `sankey_output/` (generated PNG/HTML artifacts).

---

## rel-viz: Relationship Visualiser + Kibana Exporter + CLAUDE.md

### Summary

New `rel-viz/` subproject for visualising the BDE relationship spreadsheet (Entity → Model View → Base Bde trigger → Base BDE Dependancy → Parallel lookup) and exporting it to a Kibana-friendly CSV/NDJSON. Renders both a Graphviz directed graph and a Plotly Sankey, with a Streamlit app for interactive exploration. Layout is reversed — Parallel lookup (col G) on the left, Entity (col A) on the right. Also adds a top-level `CLAUDE.md` documenting the repo layout, common commands, and the dashboard architecture for future Claude Code sessions.

### Files Changed

- `CLAUDE.md` — New: repo guidance for Claude Code (subproject layout, deploy/test commands, end-to-end pipeline + dashboard architecture, project conventions from `.kiro/steering/`).
- `rel-viz/create_sample_xlsx.py` — New: generates `relationship.xlsx` mirroring the source spreadsheet (9 columns, 35 rows: Transaction / Transaction-Charge / Order entities, with merged Entity + Status cells).
- `rel-viz/visualize_relationships.py` — New: reads the xlsx, builds 5-stage edge list (handles comma-split E and G; falls back to Trigger when E is empty), emits `relationship_graph.svg` (+ DOT source) and `relationship_sankey.html`. Reversed layout (`rankdir=RL`, explicit Sankey x-positions).
- `rel-viz/app.py` — New: Streamlit app (sidebar upload + Entity multi-select filter; Graphviz / Sankey / Data tabs; CSV download of derived edges).
- `rel-viz/xls_to_kibana_csv.py` — New: standalone CLI converting any `.xls`/`.xlsx` into Kibana-ready CSV or NDJSON. Forward-fills merged columns, explodes comma-separated columns, snake_cases headers, optional `@timestamp`.
- `rel-viz/requirements.txt`, `rel-viz/README.md`, `rel-viz/.gitignore` — Project metadata and ignore rules for generated artifacts.

---

## Remove Hardcoded AWS Profiles for ECS Deployment

### Summary

Removed hardcoded AWS profile names (`dev2`, `mondayskills.development`) from standalone scripts so the app uses the ECS task IAM role when deployed (no profile provided). All files now default to `None` for the profile, letting boto3 fall back to the standard credential chain. Local dev still works via `--profile` CLI arg or `AWS_PROFILE` env var.

### Files Changed

- `viz/extract_dbt_logs.py` — Changed `DEFAULT_PROFILE` from `"dev2"` to `None`; session creation handles `None` gracefully
- `viz/dump_debug_data.py` — Changed `--profile` default from `"dev2"` to `None`; conditional session creation
- `viz/query_dbt_errors.py` — Replaced hardcoded `"mondayskills.development"` with env-based resolution (`AWS_PROFILE` or `None`); made `LOG_GROUP` configurable via `DBT_LOG_GROUP` env var

---

## Rename Glue Job to Match Discovery Pattern

### Summary

Renamed the dummy Glue job from `raw-to-base-dummy-glue-job` to `raw-to-base-dummy-eu-west-1` so it matches the `raw-to-base-*-eu-west-1` discovery pattern used by the dashboard.

### Files Changed

- `iac/lib/orchestration-stack.ts` — Updated Glue job name from `raw-to-base-dummy-glue-job` to `raw-to-base-dummy-eu-west-1`
- `iac/lib/sfn-test-harness-stack.ts` — Updated mock Glue job name in test harness Pass state result

---

## Glue Job Dynamic Discovery + Multi-Environment Support

### Summary

Updated the Glue Job monitoring tab to dynamically discover Glue jobs matching `raw-to-base-*-eu-west-1` instead of using a hardcoded job name. Supports multiple environments per account — discovered jobs are shown in a multi-select, and runs from all selected jobs are aggregated. Added `list_matching_glue_jobs()` to the data provider. Run history and scatter chart now show the `job_name` column for environment visibility.

### Files Changed

- `viz/glue_job_data_provider.py` — Added `list_matching_glue_jobs(pattern)` for dynamic Glue job discovery
- `viz/sections/glue_job.py` — Replaced hardcoded `GLUE_JOB_NAME` with pattern-based discovery, multi-select job picker, aggregated runs across jobs, `job_name` column in history table and scatter chart

---

## BDE Performance Dashboard (Feature Complete)

### Summary

Extended the "Base to Prepared" section with sub-tab navigation (mirroring Raw to Base) and per-BDE Step Functions performance analytics. The section now has two sub-tabs: "Step Functions" and "dbt Monitor". The Step Functions sub-tab discovers `base-to-prepared-*-eu-west-1` state machines, extracts BDE names from execution names (stripping `_{timestamp}_{uuid}` suffix), and provides KPI cards, error analysis, execution history, BDE summary table with success rates, horizontal bar chart of average duration per BDE, scatter chart of duration over time by BDE, drill-down into individual BDE executions, and live execution monitoring grouped by BDE. Shared date/time controls and auto-refresh sit above both sub-tabs using `b2p_` prefixed session state keys.

### Files Changed

- `viz/bde_parser.py` — New module: `extract_bde_name()` with regex to parse BDE names from execution names
- `viz/sections/base_to_prepared.py` — Refactored: shared controls (`_render_shared_controls`) + sub-tabs (Step Functions, dbt Monitor) with `b2p_` session state prefix
- `viz/sections/b2p_step_functions.py` — New module: Step Functions monitoring with BDE performance analytics, KPIs, error analysis, execution history, BDE summary/bar/scatter charts, drill-down, live monitoring
- `viz/sections/b2p_dbt_monitor.py` — New module: extracted existing dbt monitoring logic from base_to_prepared.py into dedicated sub-tab
- `viz/sfn_data_provider.py` — Extended: added `_B2P_ENV_RE` pattern, `extract_environment_b2p()`, updated `extract_environment()` to try both raw-to-base and base-to-prepared patterns

---

## Glue Job Monitoring Dashboard (Feature Complete)

### Summary

Added end-to-end Glue job monitoring to the Raw to Base section of the Data Flow Monitor dashboard. Created a dummy Glue job (`raw-to-base-dummy-glue-job`) in CDK, wired it into the Step Function orchestration pipeline and the test harness, built a Glue data provider, and implemented a full Glue Job monitoring tab with sub-tab navigation alongside the existing Step Functions tab.

### Files Changed

- `iac/scripts/dummy_job.py` — Minimal PySpark Glue job script (sleeps 10s, accepts entity_name/run_date args)
- `iac/lib/orchestration-stack.ts` — Added Glue CfnJob, S3 script deployment, GlueStartJobRun step before ECS task with .sync pattern and Catch block
- `iac/bin/app.ts` — Passed dataLakeBucketName, glueJobRoleArn, vpc to OrchestrationStack
- `iac/lib/sfn-test-harness-stack.ts` — Added SimulateGlueJob Pass state to test state machines
- `viz/glue_job_data_provider.py` — New data provider: fetch_glue_job_runs() with retry, caching, pagination
- `viz/sections/raw_to_base.py` — Shared date/time controls + sub-tabs (Step Functions, Glue Job)
- `viz/sections/step_functions.py` — Refactored to accept shared parameters from parent section
- `viz/sections/glue_job.py` — New Glue Job tab: KPIs, duration metrics, error analysis, run history, cost estimation

---

## Implement Glue Job monitoring tab

### Summary

Created `viz/sections/glue_job.py` with the complete Glue Job monitoring tab including KPI cards (Total, SUCCEEDED, FAILED, TIMEOUT, RUNNING, STOPPED), duration metrics with scatter chart and summary statistics, error analysis table for FAILED/TIMEOUT runs, color-coded run history table sorted by start time descending, and cost estimation (DPU × hours × $0.44). Wired the tab into `raw_to_base.py` replacing the placeholder.

### Files Changed

- `viz/sections/glue_job.py` — New module with `render_glue_job()` and helper functions: `compute_status_counts`, `compute_duration_stats`, `filter_error_runs`, `sort_runs_by_start_time`, `compute_run_cost`, `compute_cost_summary`.
- `viz/sections/raw_to_base.py` — Imported `render_glue_job`; replaced placeholder with actual Glue Job tab rendering.

---

## Lift shared controls into Raw to Base section with sub-tabs

### Summary

Refactored the Raw to Base section to render shared date/time range controls and auto-refresh selector above two sub-tabs: "Step Functions" and "Glue Job". The date/time controls were extracted from `step_functions.py` into `raw_to_base.py` so both tabs share the same time window. The Step Functions render function was renamed from `render()` to `render_step_functions()` and now accepts shared parameters (`start_date`, `start_time`, `end_date`, `end_time`, `auto_refresh`) instead of rendering its own controls. The Glue Job tab shows a placeholder for now.

### Files Changed

- `viz/sections/raw_to_base.py` — Added `_render_shared_controls()` helper; `render()` now creates sub-tabs and passes shared time range to each tab renderer.
- `viz/sections/step_functions.py` — Renamed `render()` to `render_step_functions(start_date, start_time, end_date, end_time, auto_refresh)`; removed local date/time controls; removed unused imports.

---

## Add Glue job data provider module

### Summary

Created `viz/glue_job_data_provider.py` implementing `fetch_glue_job_runs()` to retrieve AWS Glue job run history. Follows the same patterns as `sfn_data_provider.py`: AWS profile resolution via `data_provider.AWS_PROFILE`, exponential backoff retry on throttling, module-level TTL cache (60s), pagination via `GetJobRuns`, time window filtering on `StartedOn`, and empty DataFrame with correct schema on errors.

### Files Changed

- `viz/glue_job_data_provider.py` — New module with `fetch_glue_job_runs(job_name, start_time, end_time)` returning a DataFrame with columns: `job_run_id`, `status`, `start_time`, `completion_time`, `execution_time_sec`, `dpu_count`, `error_message`.

---

## Add SimulateGlueJob Pass state to SfnTestHarnessStack

### Summary

Added a `SimulateGlueJob{Suffix}` Pass state to each test state machine in the SFN test harness. The new state is the entry point (`StartAt`) and sets mock `JobRunId` and `JobName` in `$.glueJobResult` before transitioning to `ConfigureParams{Suffix}`. This simulates a Glue job step in the test harness execution history.

### Files Changed

- `iac/lib/sfn-test-harness-stack.ts` — Inserted `SimulateGlueJob{Suffix}` Pass state with mock Glue job result payload; updated `StartAt` to point to the new state.

---

## Pass Glue job props to OrchestrationStack in CDK app entry point

### Summary

Updated the CDK app entry point to pass `dataLakeBucketName`, `glueJobRoleArn`, and `vpc` from existing stacks (`EtlDatabaseStack`, `EtlNetworkingStack`) to `OrchestrationStack`. Added an explicit dependency on `databaseStack` for the orchestration stack.

### Files Changed

- `iac/bin/app.ts` — Added `dataLakeBucketName`, `glueJobRoleArn`, and `vpc` props to `OrchestrationStack` instantiation; added `orchestrationStack.addDependency(databaseStack)`.

---

## Wire Glue job step into Step Function definition

### Summary

Added a `GlueStartJobRun` task with `.sync` integration pattern to the orchestration state machine. The Glue step runs before the existing `RunDbtBuild` ECS step, passing `entityName` and `runDate` as Glue job arguments (`--entity_name`, `--run_date`). Both the Glue step and ECS step have Catch blocks that transition to `DbtRunFailed` with error details in `$.error`. The new chain is: RunGlueJob → RunDbtBuild → DbtRunSucceeded.

### Files Changed

- `iac/lib/orchestration-stack.ts` — Added `GlueStartJobRun` task with `.sync` pattern; wired it before `RunDbtBuild` in the state machine chain; added Catch block transitioning to `DbtRunFailed`.

---

## Add Glue job and S3 script deployment to OrchestrationStack

### Summary

Extended `OrchestrationStack` with a dummy Glue job (`raw-to-base-dummy-glue-job`) and S3 script deployment. Added `dataLakeBucketName`, `glueJobRoleArn`, and `vpc` to the stack props. The Glue job uses worker type G.1X with 2 workers, Glue version 4.0, CloudWatch metrics enabled, and a 300s timeout. The dummy PySpark script is deployed to `s3://<dataLakeBucket>/glue-scripts/` via `BucketDeployment`. A `CfnOutput` exports the Glue job name.

### Files Changed

- `iac/lib/orchestration-stack.ts` — Extended `OrchestrationStackProps` with new props; added S3 `BucketDeployment` for Glue script; created `CfnJob` for `raw-to-base-dummy-glue-job`; added `CfnOutput` for Glue job name.

---

## Add PySpark dummy Glue job script

### Summary

Created a minimal PySpark dummy Glue job script for the Glue monitoring dashboard. The script accepts `--entity_name` and `--run_date` arguments, sleeps for 10 seconds to simulate work, and exits cleanly.

### Files Changed

- `iac/scripts/dummy_job.py` — New minimal PySpark Glue job script that initializes GlueContext, logs start/end messages, sleeps briefly, and commits.

---

## Fix trigger script region mismatch

### Summary

Fixed `trigger-test-executions.sh` failing to start executions due to hardcoded `eu-west-1` region in the state machine ARN. The state machines are deployed in `us-east-1` (the profile's default region). Updated the script to dynamically resolve the region and account ID upfront, and display the resolved ARN in output.

### Files Changed

- `iac/scripts/trigger-test-executions.sh` — Resolve region from AWS profile instead of hardcoding `eu-west-1`; pre-compute state machine ARN; show region and ARN in startup output.

---

## SFN Test Harness

### Summary

Added a Step Functions test harness for generating realistic execution data to test the monitoring dashboard. Includes a CDK stack that deploys test state machines (named `raw-to-base-{env}-eu-west-1`) with configurable random sleep, random failures, and CloudWatch logging, plus a trigger script to launch batches of randomized executions.

### Files Changed

- `iac/lib/sfn-test-harness-stack.ts` — New CDK stack (`SfnTestHarnessStack`) deploying test state machines with Pass, Wait, Choice, Fail, and Succeed states per environment.
- `iac/bin/app.ts` — Added `SfnTestHarnessStack` instantiation with `['test', 'test2']` environments.
- `iac/scripts/trigger-test-executions.sh` — New bash script to start batches of randomized test executions with configurable count, random sleep/failure/entity parameters, and error handling.
- `.kiro/specs/sfn-test-harness/` — Spec files (requirements, design, tasks).

---

## SFN API Throttling Fix

### Summary

Fixed AWS API rate limiting (`ThrottlingException`) in the Step Functions monitoring dashboard. Added exponential backoff with jitter retry logic for `ListExecutions` and `describe_execution` API calls, plus a 60-second TTL in-memory cache to reduce redundant API calls on dashboard auto-refresh.

### Files Changed

- `viz/sfn_data_provider.py` — Added `_retry_on_throttle()` helper, wrapped `ListExecutions` pagination and `describe_execution` with retry, added TTL cache for `fetch_executions()`.
- `viz/tests/test_sfn_throttle_bug_condition.py` — Bug condition exploration tests (PBT) confirming throttle-then-retry behavior.
- `viz/tests/test_sfn_preservation.py` — Preservation property tests (PBT) ensuring non-throttled behavior is unchanged.
- `.kiro/specs/sfn-api-throttling-fix/` — Bugfix spec files (requirements, design, tasks).

---

## Step Functions Monitoring Dashboard

### Summary

Added Step Functions monitoring inside the "Raw to Base" tab. Auto-discovers `raw-to-base-*-eu-west-1` state machines across environments (dev2, dint1, uat1, prd1, etc.) and provides execution monitoring with KPI cards, error analysis, duration charts, status distribution, and a color-coded execution history table. Includes auto-refresh and environment filtering.

### Files Changed

- `viz/sfn_data_provider.py` — New data provider: discovers state machines, fetches execution history with error details via boto3.
- `viz/sections/step_functions.py` — Section renderer: controls, KPIs, error analysis, duration chart, status distribution, execution history table.
- `viz/sections/raw_to_base.py` — Now renders Step Functions monitoring (replaces TBC placeholder).
- `viz/requirements.txt` — Added `hypothesis>=6.0.0` for property-based testing.
- `viz/tests/test_sfn_fetch_executions.py` — 10 unit tests for the data provider.

---

## Tab Navigation, Heading Fixes, Notification Tab Fix

### Summary

Switched from sidebar radio to top-level tabs. Added global "Data Flow Monitor" heading. Renamed section header to "DBT Monitor" (no icon, `###` size). Fixed Notification tab not rendering by replacing `st.stop()` with `return`.

### Files Changed

- `viz/dbt_run_dashboard.py` — Replaced sidebar nav with `st.tabs`, added global heading.
- `viz/sections/base_to_prepared.py` — Renamed header to "DBT Monitor" (`###`), replaced `st.stop()` with `return`.
- `viz/sections/raw_to_base.py` — Changed heading to `###` to match DBT Monitor size.
- `viz/sections/notification.py` — Changed heading to `###` to match DBT Monitor size.

---

## Initial — Sidebar Navigation for Dashboard Sections

### Summary

Added sidebar-based navigation to the Data Flow Monitor dashboard with three sections: Raw to Base, Base to Prepared, and Notification. The existing dashboard content is now under "Base to Prepared". The other two sections are TBC placeholders.

### Files Changed

- `viz/dbt_run_dashboard.py` — Slimmed down to entry point only: page config, session state init, global CSS, section routing.
- `viz/sections/__init__.py` — Package init that re-exports all section renderers.
- `viz/sections/base_to_prepared.py` — Full existing dashboard (header, controls, data fetching, KPIs, inner tabs, footer).
- `viz/sections/raw_to_base.py` — TBC placeholder section.
- `viz/sections/notification.py` — TBC placeholder section.
- `.kiro/specs/dashboard-navigation-tabs/` — Spec files (requirements, design, tasks).
