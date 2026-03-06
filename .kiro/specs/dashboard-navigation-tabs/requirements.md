# Requirements Document

## Introduction

The Data Flow Monitor Streamlit dashboard currently uses a flat tab layout with five inner tabs (Live/In Progress, Completed Runs, Performance Analytics, Execution Timeline, Glue Metrics). This feature restructures the dashboard to introduce sidebar navigation with three sections: "Raw to Base", "Base to Prepared", and "Notification". The entire existing dashboard content (all five tabs, KPIs, filters, data fetching, footer) moves into the "Base to Prepared" section. The other two sections are TBC placeholders for future development.

## Glossary

- **Dashboard**: The Streamlit application defined in `viz/dbt_run_dashboard.py` that monitors dbt view executions and Glue metrics.
- **Sidebar_Navigation**: A Streamlit sidebar-based navigation component where section links appear in the left sidebar panel, allowing the user to switch between the three main sections.
- **Section**: One of the three top-level areas of the Dashboard: "Raw to Base", "Base to Prepared", or "Notification".
- **Inner_Tabs**: The five existing content tabs within the current Dashboard: Live/In Progress, Completed Runs, Performance Analytics, Execution Timeline, and Glue Metrics.
- **Placeholder_Section**: A section that displays a title and a "TBC" (To Be Confirmed) message, with no functional content.

## Requirements

### Requirement 1: Sidebar Navigation

**User Story:** As a dashboard user, I want a sidebar-based navigation layer, so that I can switch between the three main sections of the Data Flow Monitor while keeping the full page width for content.

#### Acceptance Criteria

1. THE Sidebar_Navigation SHALL present exactly three items labeled "Raw to Base", "Base to Prepared", and "Notification" in that order.
2. WHEN the Dashboard loads, THE Sidebar_Navigation SHALL display the "Base to Prepared" section as the default active section.
3. WHEN the user selects a section in the Sidebar_Navigation, THE Dashboard SHALL display only the content of the selected section.
4. THE Dashboard SHALL visually indicate the currently active section in the Sidebar_Navigation.
5. THE Dashboard SHALL preserve the existing auto-refresh sidebar component alongside the navigation items.

### Requirement 2: Base to Prepared Section Content

**User Story:** As a dashboard user, I want the existing dashboard functionality preserved in the "Base to Prepared" section, so that I do not lose any current monitoring capabilities.

#### Acceptance Criteria

1. WHEN the "Base to Prepared" section is active, THE Dashboard SHALL display the page header, date/time range controls, and fetch button.
2. WHEN the "Base to Prepared" section is active, THE Dashboard SHALL display the KPI cards (Entities, Total Views, Succeeded, Failed, Skipped, In Progress, Tests).
3. WHEN the "Base to Prepared" section is active, THE Dashboard SHALL display all five Inner_Tabs with their existing content and behavior.
4. WHEN the "Base to Prepared" section is active, THE Dashboard SHALL display the footer with source information.
5. THE Dashboard SHALL preserve all existing data fetching, filtering, auto-refresh, and session state behavior when the "Base to Prepared" section is active.

### Requirement 3: Raw to Base Placeholder Section

**User Story:** As a dashboard user, I want to see a "Raw to Base" section placeholder, so that I know this section will be available in the future.

#### Acceptance Criteria

1. WHEN the "Raw to Base" section is active, THE Dashboard SHALL display the section title "Raw to Base".
2. WHEN the "Raw to Base" section is active, THE Dashboard SHALL display a "TBC" placeholder message indicating the section content is to be confirmed.
3. WHEN the "Raw to Base" section is active, THE Dashboard SHALL not trigger any data fetching or processing.

### Requirement 4: Notification Placeholder Section

**User Story:** As a dashboard user, I want to see a "Notification" section placeholder, so that I know this section will be available in the future.

#### Acceptance Criteria

1. WHEN the "Notification" section is active, THE Dashboard SHALL display the section title "Notification".
2. WHEN the "Notification" section is active, THE Dashboard SHALL display a "TBC" placeholder message indicating the section content is to be confirmed.
3. WHEN the "Notification" section is active, THE Dashboard SHALL not trigger any data fetching or processing.

### Requirement 5: Shared State Across Sections

**User Story:** As a dashboard user, I want the page configuration and global styling to remain consistent regardless of which section is active, so that the dashboard feels cohesive.

#### Acceptance Criteria

1. THE Dashboard SHALL apply the page configuration (title, icon, layout) once at startup, independent of the active section.
2. THE Dashboard SHALL apply the custom CSS styling globally, independent of the active section.
3. THE Dashboard SHALL maintain session state (fetched data, timestamps, auto-refresh settings) across section switches without data loss.
