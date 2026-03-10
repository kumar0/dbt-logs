# Tasks

## Task 1: Create the SFN Test Harness CDK Stack

- [x] 1.1 Create `iac/lib/sfn-test-harness-stack.ts` with `SfnTestHarnessStack` class that accepts `environments` string array in props
- [x] 1.2 Define the state machine with 5 states: ConfigureParams (Pass), RandomSleep (Wait with SecondsPath), ShouldFail (Choice), ExecutionFailed (Fail), ExecutionSucceeded (Succeed)
- [x] 1.3 Configure the Pass state to set default values for all input fields (sleepSeconds=10, shouldFail=false, errorType="TaskError", errorMessage="Task failed", entityName="all")
- [x] 1.4 Configure the Fail state to use `$.errorType` as Error and `$.errorMessage` as Cause
- [x] 1.5 Create a CloudWatch log group with TWO_WEEKS retention and DESTROY removal policy, enable ALL-level logging on the state machine
- [x] 1.6 Set state machine timeout to 10 minutes
- [x] 1.7 Create one state machine per environment, named `raw-to-base-{env}-eu-west-1`
- [x] 1.8 Add CfnOutput for each state machine ARN

## Task 2: Integrate Stack into CDK App

- [x] 2.1 Add `SfnTestHarnessStack` import and instantiation to `iac/bin/app.ts` with environments `['test', 'test2']`

## Task 3: Create Trigger Script

- [x] 3.1 Create `iac/scripts/trigger-test-executions.sh` with argument parsing for `--count` (default 10) and `--state-machine-name` (default `raw-to-base-test-eu-west-1`)
- [x] 3.2 Add AWS CLI availability check at script start
- [x] 3.3 Implement randomized parameter generation: sleepSeconds (1-120), shouldFail (~30%), errorType (5 types), entityName (6 entities), runDate (recent dates)
- [x] 3.4 Implement execution loop calling `aws stepfunctions start-execution --profile=mondayskills.development` with unique execution names
- [x] 3.5 Add error handling: log failures, continue with remaining executions, exit non-zero if any failed
- [x] 3.6 Add summary output showing total started, configured to fail, and sleep range
- [x] 3.7 Make the script executable (`chmod +x`)

## Task 4: Update Changelog

- [x] 4.1 Add entry to `CHANGES.md` describing the SFN test harness with list of files created/modified
