# Implementation Plan: Dashboard Navigation Tabs

## Overview

Add sidebar-based navigation to `viz/dbt_run_dashboard.py` with three sections ("Raw to Base", "Base to Prepared", "Notification"). Extract existing dashboard content into `render_base_to_prepared()`, create `render_placeholder(title)` for TBC sections, and wire conditional routing via `st.sidebar.radio`. All changes are in a single file plus test files.

## Tasks

- [x] 1. Add navigation constants and sidebar radio widget
  - [x] 1.1 Define `SECTIONS` list and add `st.sidebar.radio` navigation
    - Add `SECTIONS = ["Raw to Base", "Base to Prepared", "Notification"]` as a module-level constant
    - Add `st.sidebar.radio("Navigation", SECTIONS, index=1, key="nav_section")` in the sidebar, after session state init and CSS, before the auto-refresh timer block
    - Store the return value in `active_section`
    - _Requirements: 1.1, 1.2, 1.4, 5.1, 5.2_

- [x] 2. Extract existing content into render functions and add routing
  - [x] 2.1 Create `render_placeholder(title: str)` function
    - Add function at module level that renders `st.markdown(f"## {title}")` and `st.info("🚧 TBC — This section is under development.")`
    - _Requirements: 3.1, 3.2, 4.1, 4.2_

  - [x] 2.2 Extract existing dashboard body into `render_base_to_prepared()` function
    - Move all code from the header (`st.markdown` title) through the footer into a `render_base_to_prepared() -> None` function
    - This includes: header, date/time range controls, fetch button, data fetching logic, KPI cards, all five inner tabs, and footer
    - Ensure the function reads/writes `st.session_state` directly (no parameters needed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 2.3 Add conditional routing based on `active_section`
    - After the sidebar block, add routing: if "Base to Prepared" call `render_base_to_prepared()`, if "Raw to Base" or "Notification" call `render_placeholder(active_section)`
    - Ensure placeholder sections do not trigger any data fetching
    - _Requirements: 1.3, 3.3, 4.3, 5.3_

- [x] 3. Checkpoint — Verify dashboard runs correctly
  - Ensure the dashboard loads without errors, ask the user if questions arise.
  - Manually verify: default section is "Base to Prepared", switching sections works, existing functionality is preserved.

- [ ] 4. Add property-based and unit tests
  - [ ]\* 4.1 Write property test for section routing exclusivity
    - **Property 1: Section routing exclusivity**
    - Generate random section names from SECTIONS, mock the three renderers, verify only the correct one is called
    - Use `hypothesis` with `@settings(max_examples=100)`
    - **Validates: Requirement 1.3**

  - [ ]\* 4.2 Write property test for placeholder content completeness
    - **Property 2: Placeholder content completeness**
    - Generate random non-empty title strings, call `render_placeholder(title)`, verify output contains the title and a TBC message
    - Use `hypothesis` with `@settings(max_examples=100)`
    - **Validates: Requirements 3.1, 3.2, 4.1, 4.2**

  - [ ]\* 4.3 Write property test for placeholder sections not triggering data fetching
    - **Property 3: Placeholder sections do not trigger data fetching**
    - Generate random section names excluding "Base to Prepared", mock `fetch_dbt_run_logs` and `fetch_glue_job_metrics`, verify neither is called
    - Use `hypothesis` with `@settings(max_examples=100)`
    - **Validates: Requirements 3.3, 4.3**

  - [ ]\* 4.4 Write property test for session state preservation across section switches
    - **Property 4: Session state preservation across section switches**
    - Generate random sequences of section switches (length 1–20), initialize session state with random data, verify all data keys retain original values after switches
    - Use `hypothesis` with `@settings(max_examples=100)`
    - **Validates: Requirement 5.3**

  - [ ]\* 4.5 Write unit tests for navigation configuration and placeholder rendering
    - Verify `SECTIONS == ["Raw to Base", "Base to Prepared", "Notification"]` and default index is `1`
    - Verify `render_placeholder("Raw to Base")` and `render_placeholder("Notification")` produce expected output
    - _Requirements: 1.1, 1.2, 3.1, 3.2, 4.1, 4.2_

- [ ] 5. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All implementation changes are in `viz/dbt_run_dashboard.py` — no new source files needed
- Test files go in `viz/tests/` (or project test directory)
- Property tests use `hypothesis` library
- Each task references specific requirements for traceability
