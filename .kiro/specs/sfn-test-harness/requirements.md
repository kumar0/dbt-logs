# Requirements Document

## Introduction

A Step Functions test harness that generates realistic execution data for testing the Step Functions monitoring dashboard. The harness consists of a CDK stack deploying state machines with configurable random sleep, random failures, and varied parameters, plus a trigger script to launch batches of randomized executions. All state machines follow the `raw-to-base-*-eu-west-1` naming pattern so the existing dashboard discovers them automatically.

## Glossary

- **Test_Harness_Stack**: The CDK stack (`SfnTestHarnessStack`) that deploys test state machines and associated CloudWatch log groups.
- **Test_State_Machine**: A Step Functions state machine created by the Test_Harness_Stack, named `raw-to-base-{env}-eu-west-1`.
- **Trigger_Script**: The bash script (`iac/scripts/trigger-test-executions.sh`) that starts batches of executions with randomized inputs.
- **Execution_Input**: The JSON input passed to each state machine execution, containing `sleepSeconds`, `shouldFail`, `errorType`, `errorMessage`, `entityName`, and `runDate`.
- **Dashboard**: The existing Streamlit monitoring dashboard in `/viz` that visualizes Step Functions execution data.

## Requirements

### Requirement 1: Deploy Test State Machines

**User Story:** As a developer, I want to deploy test state machines that the monitoring dashboard automatically discovers, so that I can generate test data without modifying the dashboard code.

#### Acceptance Criteria

1. THE Test_Harness_Stack SHALL create state machines named `raw-to-base-{env}-eu-west-1` for each configured environment, so that the Dashboard's `list_matching_state_machines(pattern="raw-to-base-*-eu-west-1")` discovers them.
2. THE Test_Harness_Stack SHALL create one state machine per configured environment entry.
3. THE Test_Harness_Stack SHALL be deployable via `npx cdk deploy SfnTestHarnessStack --profile=mondayskills.development` without requiring any other stack as a dependency.
4. THE Test_Harness_Stack SHALL be added to `iac/bin/app.ts` alongside the existing stacks.

### Requirement 2: State Machine with Random Sleep and Random Failure

**User Story:** As a developer, I want the test state machine to support configurable sleep durations and failure behavior, so that I can generate diverse execution patterns for dashboard testing.

#### Acceptance Criteria

1. THE Test_State_Machine SHALL include a Pass state that sets default values for all input fields when not provided.
2. THE Test_State_Machine SHALL include a Wait state that pauses execution for the number of seconds specified by `sleepSeconds` in the Execution_Input.
3. THE Test_State_Machine SHALL include a Choice state that routes to a Fail state when `shouldFail` is `true` and to a Succeed state when `shouldFail` is `false`.
4. WHEN the execution fails, THE Test_State_Machine SHALL use the `errorType` from Execution_Input as the error name and `errorMessage` as the error cause.
5. WHEN the execution succeeds, THE Test_State_Machine SHALL reach a terminal Succeed state.
6. THE Test_State_Machine SHALL have a timeout of 10 minutes.

### Requirement 3: CloudWatch Logging

**User Story:** As a developer, I want state machine executions to be logged to CloudWatch, so that I can debug test executions if needed.

#### Acceptance Criteria

1. THE Test_Harness_Stack SHALL create a CloudWatch log group for state machine execution logs.
2. THE Test_State_Machine SHALL have logging enabled at ALL level.
3. THE CloudWatch log group SHALL have a retention period of TWO_WEEKS and a DESTROY removal policy.

### Requirement 4: Trigger Script with Randomized Parameters

**User Story:** As a developer, I want a script that launches multiple test executions with randomized parameters, so that I can quickly populate the dashboard with diverse test data.

#### Acceptance Criteria

1. THE Trigger_Script SHALL accept a `--count` parameter (default: 10) specifying the number of executions to start.
2. THE Trigger_Script SHALL accept a `--state-machine-name` parameter (default: `raw-to-base-test-eu-west-1`).
3. THE Trigger_Script SHALL use `--profile=mondayskills.development` for all AWS CLI calls.
4. FOR each execution, THE Trigger_Script SHALL generate a random `sleepSeconds` value between 1 and 120.
5. FOR each execution, THE Trigger_Script SHALL set `shouldFail` to `true` with approximately 30% probability.
6. FOR each execution where `shouldFail` is `true`, THE Trigger_Script SHALL select a random `errorType` from: TaskError, TimeoutError, ValidationError, DataError, ConnectionError.
7. FOR each execution, THE Trigger_Script SHALL select a random `entityName` from: customers, orders, products, invoices, payments, shipments.
8. THE Trigger_Script SHALL generate a unique execution name for each execution to avoid name collisions.
9. THE Trigger_Script SHALL print a summary showing how many executions were started, how many were configured to fail, and the sleep range used.

### Requirement 5: Error Handling in Trigger Script

**User Story:** As a developer, I want the trigger script to handle errors gracefully, so that I know when something goes wrong during test execution triggering.

#### Acceptance Criteria

1. THE Trigger_Script SHALL verify that the `aws` CLI command is available before attempting to start executions.
2. IF a `start-execution` call fails, THE Trigger_Script SHALL log the error and continue with the remaining executions.
3. THE Trigger_Script SHALL exit with a non-zero status code if any executions failed to start.

### Requirement 6: CHANGES.md Update

**User Story:** As a developer, I want the changelog to reflect the addition of the test harness, so that the project history is maintained.

#### Acceptance Criteria

1. THE `CHANGES.md` file SHALL be updated with a new entry describing the SFN test harness addition, listing all files created or modified.
