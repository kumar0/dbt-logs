# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

This repo is a self-healing dbt framework with three top-level subprojects that are deployed together but developed independently:

- `iac/` — AWS CDK (TypeScript) for all infrastructure: ECR, networking (existing VPC lookup), ECS Fargate cluster + dbt task definition, S3 data lake, Glue job, Step Functions orchestration, and an SFN test harness.
- `etl/` — dbt project (`etl_pipeline`) targeting AWS Glue (Iceberg). Container image is built from `etl/Dockerfile` and pushed to ECR; the ECS task runs `docker-entrypoint.sh` which executes `dbt $DBT_COMMAND` and then `publish_metrics.py` to push run-results to CloudWatch (namespace `ETL/dbt`).
- `viz/` — Streamlit dashboard ("Data Flow Monitor"). Deployed as an ECS service; in production it relies on the ECS task IAM role (no AWS profile).

`.kiro/specs/` contains feature specs (requirements/design/tasks). `.kiro/steering/project-conventions.md` is treated as authoritative for AWS profile/region/VPC conventions — see below.

## Common commands

### Deploy
```bash
./deploy-cdk.sh        # deploys all CDK stacks (intentionally destroys EtlOrchestrationStack first to release cross-stack refs)
./deploy-docker.sh     # builds linux/amd64 dbt image and pushes to ECR (etl-dbt:latest)
```

### CDK (run from `iac/`)
```bash
npm install
npm run synth          # cdk synth --profile mondayskills.development
npm run deploy         # cdk deploy --profile mondayskills.development
npx cdk deploy <StackName> --profile mondayskills.development
npx cdk destroy <StackName> --profile mondayskills.development --force
```

### Streamlit dashboard (run from `viz/`)
```bash
pip install -r requirements.txt
streamlit run dbt_run_dashboard.py -- --profile mondayskills.development
```
Tests use pytest + hypothesis:
```bash
cd viz && pytest tests/                          # all tests
cd viz && pytest tests/test_sfn_fetch_executions.py::test_name   # single test
```

### Generate test data for the dashboard
```bash
./iac/scripts/trigger-test-executions.sh --count 10 --state-machine-name raw-to-base-test-eu-west-1
```

### dbt (local, run from `etl/`)
```bash
dbt deps --profiles-dir .
dbt build --profiles-dir .
```
The Step Function passes `dbtCommand` (e.g. `build` or `build --select tag:customers`) and `entityName`/`runDate` which become `GLUE_SESSION_ID = hk_dbt_{entity}_{runDate}`.

## Architecture: end-to-end pipeline

The orchestration is a single Step Functions state machine (`EtlOrchestrationStack`):

```
StartAt → RunGlueJob (raw-to-base-dummy-eu-west-1, .sync) → RunDbtBuild (ECS Fargate) → DbtRunSucceeded
                                  ↓ Catch                          ↓ Catch
                                              DbtRunFailed
```

`RunDbtBuild` launches the `etl-dbt` container on ECS Fargate. Inside the container, `docker-entrypoint.sh` runs `dbt --log-format json` (so each CloudWatch log line is a structured event) and then `publish_metrics.py` parses `target/run_results.json` and emits per-model CloudWatch metrics under `ETL/dbt`.

State-machine inputs are documented in the JSDoc of `iac/lib/orchestration-stack.ts`. The dbt profile (`etl/profiles.yml`) targets Glue with Iceberg via the `dbt-glue` adapter; `WORKER_TYPE`, `NUM_WORKERS`, and `GLUE_SESSION_ID` are env-driven so the same image is reused across runs and reuses Glue sessions.

## Architecture: dashboard

`viz/dbt_run_dashboard.py` is a thin entry point that renders three top-level tabs via `viz/sections/`:

- **Raw to Base** (`sections/raw_to_base.py`) — shared date/time + auto-refresh controls, then sub-tabs:
  - **Step Functions** (`sections/step_functions.py`) — discovers state machines matching `raw-to-base-*-eu-west-1`.
  - **Glue Job** (`sections/glue_job.py`) — discovers Glue jobs matching `raw-to-base-*-eu-west-1` (multi-select, runs aggregated).
- **Base to Prepared** (`sections/base_to_prepared.py`) — same shared-controls + sub-tabs pattern with `b2p_` session-state prefix:
  - **Step Functions** (`sections/b2p_step_functions.py`) — discovers `base-to-prepared-*-eu-west-1`. BDE name is parsed from the execution name via `bde_parser.extract_bde_name()` (strips `_{timestamp}_{uuid}` suffix), enabling per-BDE KPIs/charts.
  - **dbt Monitor** (`sections/b2p_dbt_monitor.py`) — original dbt log-based monitoring.
- **Notification** (`sections/notification.py`).

Two patterns repeat across sections and are load-bearing:

1. **Shared controls + `{prefix}_` session state** — each section renders date/time + auto-refresh once and passes the resolved `(start_date, start_time, end_date, end_time, auto_refresh)` tuple into both sub-tab renderers. Session-state keys are namespaced (`r2b_*`, `b2p_*`) so the two sections can coexist without colliding. `*_effective_to_time/date` are updated on auto-refresh ticks without touching the widget state.
2. **Auto-discovery by name pattern** — the dashboard never takes hardcoded ARNs. `sfn_data_provider.list_matching_state_machines()` and `glue_job_data_provider.list_matching_glue_jobs()` filter by glob, and environment is parsed out of the matched name via the regexes at the top of `sfn_data_provider.py`. To add a new environment, name the resource `raw-to-base-{env}-eu-west-1` (or `base-to-prepared-{env}-eu-west-1`) and it will appear in the dashboard automatically.

### Data providers

- `viz/data_provider.py` — dbt log fetching from CloudWatch Logs Insights. Resolves `AWS_PROFILE` via CLI `--profile` arg (after Streamlit's `--`) → env var → `None` (ECS IAM role). Default log group is the `EtlComputeStack-DbtTaskDefinitionDbtContainerLogGroup*` one (overridable with `DBT_LOG_GROUP`).
- `viz/sfn_data_provider.py` and `viz/glue_job_data_provider.py` — both share three patterns: a 60s module-level TTL cache (`_fetch_cache`), exponential-backoff retry on `ThrottlingException` via `_retry_on_throttle`, and an empty-DataFrame-with-fixed-schema return on errors so downstream Streamlit code never crashes. **All three providers import `AWS_PROFILE` from `data_provider`** — that single resolution is the source of truth.
- `viz/extract_dbt_logs.py` and `viz/query_dbt_errors.py` — standalone CLIs (not used by the live dashboard) for offline log extraction. Profile defaults to `None`; pass `--profile` for local dev.

### dbt run-log classification

`extract_dbt_logs.py` classifies dbt's structured JSON events at extraction time (not in pandas downstream): `Q011 → MODEL_START`, `Q012 → MODEL_END`, `Z038 → EXECUTION_STATUS`, plus computed `EXECUTION_DURATION`. If you change classification logic, do it in this extractor, not in the dashboard.

## Project conventions (from `.kiro/steering/project-conventions.md`)

- AWS CLI: always use `--profile=mondayskills.development`.
- Docker builds: always `--platform=linux/amd64` (Fargate is amd64).
- VPC: always reuse `vpc-0a2290ed34b346805` via `ec2.Vpc.fromLookup` — never create a new VPC.
- ECS/dbt CloudWatch log group: `EtlComputeStack-DbtTaskDefinitionDbtContainerLogGroupE420E81B-W7fZGqD3w8jD`.
- Default region: `us-east-1` (note: state-machine *names* end in `-eu-west-1` as a discovery convention only — the resources themselves are in `us-east-1`).
- After making code changes, add a new entry at the top of `CHANGES.md` (below the heading) summarising the change and listing files changed. Follow the format of existing entries.
