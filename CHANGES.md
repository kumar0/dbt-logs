# Changes — Sidebar Navigation for Dashboard Sections

## Summary

Added sidebar-based navigation to the Data Flow Monitor dashboard with three sections: Raw to Base, Base to Prepared, and Notification. The existing dashboard content is now under "Base to Prepared". The other two sections are TBC placeholders.

## Files Changed

### Modified

- `viz/dbt_run_dashboard.py` — Slimmed down to entry point only: page config, session state init, global CSS, sidebar radio navigation, and section routing. All dashboard logic moved to `viz/sections/base_to_prepared.py`.

### Added

- `viz/sections/__init__.py` — Package init that re-exports all section renderers.
- `viz/sections/base_to_prepared.py` — Full existing dashboard (header, controls, data fetching, KPIs, inner tabs, footer).
- `viz/sections/raw_to_base.py` — TBC placeholder section.
- `viz/sections/notification.py` — TBC placeholder section.
- `.kiro/specs/dashboard-navigation-tabs/` — Spec files (requirements, design, tasks).
