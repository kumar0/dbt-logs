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

/**
 * Input schema for the state machine:
 *
 * Run all entities (full pipeline):
 * {
 *   "dbtCommand": "build",
 *   "numWorkers": "3",
 *   "workerType": "G.1X",
 *   "entityName": "all",          // special value — runs without --select filter
 *   "runDate": "18022026"         // ddmmyyyy — used in glue_session_id
 * }
 *
 * Run a single entity:
 * {
 *   "dbtCommand": "build --select tag:customers",
 *   "numWorkers": "3",
 *   "workerType": "G.1X",
 *   "entityName": "customers",    // used in glue_session_id
 *   "runDate": "18022026"         // ddmmyyyy
 * }
 *
 * The state machine computes GLUE_SESSION_ID as:  hk_dbt_{entityName}_{runDate}
 * e.g.  hk_dbt_customers_18022026
 */
export class OrchestrationStack extends cdk.Stack {
  public readonly stateMachine: sfn.StateMachine;

  constructor(scope: Construct, id: string, props: OrchestrationStackProps) {
    super(scope, id, props);

    // Build GLUE_SESSION_ID = "hk_dbt_" + entityName + "_" + runDate
    // States SDK format: States.Format('hk_dbt_{}_{}', $.entityName, $.runDate)
    const glueSessionIdExpr = sfn.JsonPath.format(
      'hk_dbt_{}_{}',
      sfn.JsonPath.stringAt('$.entityName'),
      sfn.JsonPath.stringAt('$.runDate'),
    );

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
              name: 'ENTITY_NAME',
              value: sfn.JsonPath.stringAt('$.entityName'),
            },
            {
              name: 'GLUE_SESSION_ID',
              value: glueSessionIdExpr,
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
