# Changes — Dashboard Navigation Sections

## Latest — Step Functions Monitoring Dashboard

### Summary

Added a "Step Functions" tab to the Data Flow Monitor dashboard. Auto-discovers `raw-to-base-*-eu-west-1` state machines across environments (dev2, dint1, uat1, prd1, etc.) and provides execution monitoring with KPI cards, error analysis, duration charts, status distribution, and a color-coded execution history table. Includes auto-refresh and environment filtering.

### Files Changed

- `viz/sfn_data_provider.py` — New data provider: discovers state machines, fetches execution history with error details via boto3.
- `viz/sections/step_functions.py` — New section renderer: controls, KPIs, error analysis, duration chart, status distribution, execution history table.
- `viz/sections/__init__.py` — Added `render_step_functions` import.
- `viz/dbt_run_dashboard.py` — Added "Step Functions" as fourth tab.
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
