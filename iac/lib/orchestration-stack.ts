import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as glue from 'aws-cdk-lib/aws-glue';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import { Construct } from 'constructs';

export interface OrchestrationStackProps extends cdk.StackProps {
  cluster: ecs.ICluster;
  taskDefinition: ecs.FargateTaskDefinition;
  containerDefinition: ecs.ContainerDefinition;
  securityGroup: ec2.ISecurityGroup;
  subnets: ec2.SubnetSelection;
  dataLakeBucketName: string;
  glueJobRoleArn: string;
  vpc: ec2.IVpc;
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

    // --- Glue job script deployment to S3 ---
    const dataLakeBucket = s3.Bucket.fromBucketName(
      this,
      'DataLakeBucket',
      props.dataLakeBucketName,
    );

    new s3deploy.BucketDeployment(this, 'GlueScriptDeployment', {
      sources: [s3deploy.Source.asset('./scripts')],
      destinationBucket: dataLakeBucket,
      destinationKeyPrefix: 'glue-scripts',
    });

    // --- Dummy Glue job ---
    const glueJobRole = iam.Role.fromRoleArn(
      this,
      'GlueJobRole',
      props.glueJobRoleArn,
    );

    const glueJob = new glue.CfnJob(this, 'RawToBaseDummyGlueJob', {
      name: 'raw-to-base-dummy-eu-west-1',
      role: glueJobRole.roleArn,
      command: {
        name: 'glueetl',
        pythonVersion: '3',
        scriptLocation: `s3://${props.dataLakeBucketName}/glue-scripts/dummy_job.py`,
      },
      glueVersion: '4.0',
      workerType: 'G.1X',
      numberOfWorkers: 2,
      timeout: 300,
      defaultArguments: {
        '--enable-metrics': 'true',
        '--enable-continuous-cloudwatch-log': 'true',
      },
    });

    new cdk.CfnOutput(this, 'GlueJobName', {
      value: glueJob.name!,
      description: 'Glue job name for raw-to-base dummy job',
    });

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

    // Glue StartJobRun step (runs before ECS task)
    const runGlueJob = new tasks.GlueStartJobRun(this, 'RunGlueJob', {
      glueJobName: glueJob.name!,
      integrationPattern: sfn.IntegrationPattern.RUN_JOB,
      arguments: sfn.TaskInput.fromObject({
        '--entity_name.$': '$.entityName',
        '--run_date.$': '$.runDate',
      }),
      resultPath: '$.glueJobResult',
    });

    // Wire up the state machine: RunGlueJob -> RunDbtBuild -> Success
    const definition = runGlueJob
      .addCatch(failure, { resultPath: '$.error' })
      .next(
        runDbtTask.addCatch(failure, { resultPath: '$.error' }).next(success),
      );

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
