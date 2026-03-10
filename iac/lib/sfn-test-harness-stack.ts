import * as cdk from 'aws-cdk-lib';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';

export interface SfnTestHarnessStackProps extends cdk.StackProps {
  /** Environment names to create state machines for, e.g. ['test', 'test2'] */
  environments: string[];
}

export class SfnTestHarnessStack extends cdk.Stack {
  public readonly stateMachines: sfn.StateMachine[] = [];

  constructor(scope: Construct, id: string, props: SfnTestHarnessStackProps) {
    super(scope, id, props);

    for (const env of props.environments) {
      const suffix = env.charAt(0).toUpperCase() + env.slice(1);

      // Use raw ASL JSON to avoid CDK adding "End":true to the Fail state
      const aslDefinition = {
        StartAt: `ConfigureParams${suffix}`,
        States: {
          [`ConfigureParams${suffix}`]: {
            Type: 'Pass',
            Result: {
              sleepSeconds: 10,
              shouldFail: false,
              errorType: 'TaskError',
              errorMessage: 'Task failed',
              entityName: 'all',
            },
            ResultPath: '$.defaults',
            Next: `RandomSleep${suffix}`,
          },
          [`RandomSleep${suffix}`]: {
            Type: 'Wait',
            SecondsPath: '$.sleepSeconds',
            Next: `ShouldFail${suffix}`,
          },
          [`ShouldFail${suffix}`]: {
            Type: 'Choice',
            Choices: [
              {
                Variable: '$.shouldFail',
                BooleanEquals: true,
                Next: `ExecutionFailed${suffix}`,
              },
            ],
            Default: `ExecutionSucceeded${suffix}`,
          },
          [`ExecutionFailed${suffix}`]: {
            Type: 'Fail',
            ErrorPath: '$.errorType',
            CausePath: '$.errorMessage',
          },
          [`ExecutionSucceeded${suffix}`]: {
            Type: 'Succeed',
          },
        },
        TimeoutSeconds: 600,
      };

      // CloudWatch log group for state machine execution logs
      const logGroup = new logs.LogGroup(this, `TestHarnessLogGroup${suffix}`, {
        logGroupName: `/aws/stepfunctions/raw-to-base-${env}-eu-west-1`,
        retention: logs.RetentionDays.TWO_WEEKS,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      });

      // State machine — one per environment
      const stateMachine = new sfn.StateMachine(
        this,
        `TestStateMachine${suffix}`,
        {
          stateMachineName: `raw-to-base-${env}-eu-west-1`,
          definitionBody: sfn.DefinitionBody.fromString(
            JSON.stringify(aslDefinition),
          ),
          logs: {
            destination: logGroup,
            level: sfn.LogLevel.ALL,
          },
        },
      );

      this.stateMachines.push(stateMachine);

      // CfnOutput for each state machine ARN
      new cdk.CfnOutput(this, `StateMachineArn${suffix}`, {
        value: stateMachine.stateMachineArn,
        description: `Test harness state machine ARN for ${env}`,
      });
    }
  }
}
