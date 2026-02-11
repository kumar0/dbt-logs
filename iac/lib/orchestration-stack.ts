import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';

export interface OrchestrationStackProps extends cdk.StackProps {
  cluster: ecs.ICluster;
  taskDefinition: ecs.FargateTaskDefinition;
  containerDefinition: ecs.ContainerDefinition;
  securityGroup: ec2.ISecurityGroup;
  subnets: ec2.SubnetSelection;
}

export class OrchestrationStack extends cdk.Stack {
  public readonly stateMachine: sfn.StateMachine;

  constructor(scope: Construct, id: string, props: OrchestrationStackProps) {
    super(scope, id, props);

    // ECS RunTask step
    const runDbtTask = new tasks.EcsRunTask(this, 'RunDbtBuild', {
      integrationPattern: sfn.IntegrationPattern.RUN_JOB,
      cluster: props.cluster,
      taskDefinition: props.taskDefinition,
      launchTarget: new tasks.EcsFargateLaunchTarget({
        platformVersion: ecs.FargatePlatformVersion.LATEST,
      }),
      containerOverrides: [
        {
          containerDefinition: props.containerDefinition,
          environment: [
            {
              name: 'DBT_COMMAND',
              value: sfn.JsonPath.stringAt('$.dbtCommand'),
            },
            {
              name: 'NUM_WORKERS',
              value: sfn.JsonPath.stringAt('$.numWorkers'),
            },
            {
              name: 'WORKER_TYPE',
              value: sfn.JsonPath.stringAt('$.workerType'),
            },
            {
              name: 'GLUE_SESSION_ID',
              value: sfn.JsonPath.stringAt('$.glueSessionId'),
            },
          ],
        },
      ],
      securityGroups: [props.securityGroup],
      subnets: props.subnets,
      resultPath: '$.taskResult',
    });

    // Success state
    const success = new sfn.Succeed(this, 'DbtRunSucceeded');

    // Failure state
    const failure = new sfn.Fail(this, 'DbtRunFailed', {
      cause: 'dbt ECS task failed',
      error: 'DbtTaskError',
    });

    // Wire up the state machine
    const definition = runDbtTask
      .addCatch(failure, { resultPath: '$.error' })
      .next(success);

    // Log group for state machine execution logs
    const logGroup = new logs.LogGroup(this, 'StateMachineLogGroup', {
      logGroupName: '/aws/stepfunctions/etl-dbt-pipeline',
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    this.stateMachine = new sfn.StateMachine(this, 'DbtPipelineStateMachine', {
      stateMachineName: 'etl-dbt-pipeline',
      definitionBody: sfn.DefinitionBody.fromChainable(definition),
      timeout: cdk.Duration.hours(2),
      logs: {
        destination: logGroup,
        level: sfn.LogLevel.ALL,
      },
    });

    // Outputs
    new cdk.CfnOutput(this, 'StateMachineArn', {
      value: this.stateMachine.stateMachineArn,
      description: 'Step Functions state machine ARN',
      exportName: 'EtlDbtStateMachineArn',
    });

    new cdk.CfnOutput(this, 'StateMachineName', {
      value: this.stateMachine.stateMachineName!,
      description: 'Step Functions state machine name',
    });
  }
}
