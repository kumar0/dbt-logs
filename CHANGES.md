# Changes — Dashboard Navigation Sections

## Latest — Fix trigger script region mismatch

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
