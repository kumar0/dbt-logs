import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as cw_actions from 'aws-cdk-lib/aws-cloudwatch-actions';
import { Construct } from 'constructs';

export interface ComputeStackProps extends cdk.StackProps {
  vpc: ec2.IVpc;
  repository: ecr.IRepository;
  glueJobRoleArn: string;
  dataLakeBucketName: string;
}

export class ComputeStack extends cdk.Stack {
  public readonly cluster: ecs.Cluster;
  public readonly taskDefinition: ecs.FargateTaskDefinition;
  public readonly containerDefinition: ecs.ContainerDefinition;

  constructor(scope: Construct, id: string, props: ComputeStackProps) {
    super(scope, id, props);

    // ECS Cluster
    this.cluster = new ecs.Cluster(this, 'EtlCluster', {
      clusterName: 'etl-dbt-cluster',
      vpc: props.vpc,
    });

    // Task execution role (for pulling images, writing logs)
    const executionRole = new iam.Role(this, 'TaskExecutionRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          'service-role/AmazonECSTaskExecutionRolePolicy',
        ),
      ],
    });

    // Task role (permissions the container needs at runtime)
    const taskRole = new iam.Role(this, 'TaskRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      description: 'Role for dbt ECS Fargate task to access Glue and S3',
    });

    // Glue permissions for dbt-glue adapter
    taskRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
          'glue:CreateSession',
          'glue:GetSession',
          'glue:ListSessions',
          'glue:DeleteSession',
          'glue:StopSession',
          'glue:RunStatement',
          'glue:GetStatement',
          'glue:ListStatements',
          'glue:CancelStatement',
          'glue:SearchTables',
          'glue:GetDatabase',
          'glue:GetDatabases',
          'glue:GetTable',
          'glue:GetTables',
          'glue:GetTableVersion',
          'glue:GetTableVersions',
          'glue:GetPartition',
          'glue:GetPartitions',
          'glue:CreateTable',
          'glue:UpdateTable',
          'glue:DeleteTable',
          'glue:BatchCreatePartition',
          'glue:BatchDeletePartition',
          'glue:BatchUpdatePartition',
          'glue:CreatePartition',
          'glue:DeletePartition',
          'glue:GetUserDefinedFunctions',
        ],
        resources: [
          `arn:aws:glue:${this.region}:${this.account}:catalog`,
          `arn:aws:glue:${this.region}:${this.account}:database/*`,
          `arn:aws:glue:${this.region}:${this.account}:table/*/*`,
          `arn:aws:glue:${this.region}:${this.account}:session/*`,
        ],
      }),
    );

    // S3 permissions for data lake
    taskRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
          's3:GetObject',
          's3:PutObject',
          's3:DeleteObject',
          's3:ListBucket',
          's3:GetBucketLocation',
        ],
        resources: [
          `arn:aws:s3:::${props.dataLakeBucketName}`,
          `arn:aws:s3:::${props.dataLakeBucketName}/*`,
        ],
      }),
    );

    // IAM PassRole for Glue sessions
    taskRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ['iam:PassRole'],
        resources: [props.glueJobRoleArn],
        conditions: {
          StringLike: {
            'iam:PassedToService': 'glue.amazonaws.com',
          },
        },
      }),
    );

    // CloudWatch Logs for Glue sessions
    taskRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
          'logs:CreateLogGroup',
          'logs:CreateLogStream',
          'logs:PutLogEvents',
        ],
        resources: [
          `arn:aws:logs:${this.region}:${this.account}:log-group:/aws-glue/sessions/*`,
        ],
      }),
    );

    // CloudWatch Metrics for dbt run results
    // Note: PutMetricData does not support resource-level or
    // condition-key restrictions — the namespace condition is silently
    // ignored by IAM, causing AccessDenied.  Use resource '*' only.
    taskRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ['cloudwatch:PutMetricData'],
        resources: ['*'],
      }),
    );

    // Fargate task definition
    this.taskDefinition = new ecs.FargateTaskDefinition(
      this,
      'DbtTaskDefinition',
      {
        family: 'etl-dbt-task',
        memoryLimitMiB: 2048,
        cpu: 1024,
        executionRole,
        taskRole,
      },
    );

    // Container definition — env vars are overridden at runtime via Step Functions
    this.containerDefinition = this.taskDefinition.addContainer(
      'DbtContainer',
      {
        containerName: 'dbt',
        image: ecs.ContainerImage.fromEcrRepository(props.repository, 'latest'),
        logging: ecs.LogDrivers.awsLogs({
          streamPrefix: 'etl-dbt',
          logRetention: logs.RetentionDays.TWO_WEEKS,
        }),
        environment: {
          DBT_COMMAND: 'build',
          NUM_WORKERS: '3',
          WORKER_TYPE: 'G.1X',
          AWS_DEFAULT_REGION: cdk.Aws.REGION,
          GLUE_ROLE_ARN: props.glueJobRoleArn,
          DATALAKE_S3_LOCATION: `s3://${props.dataLakeBucketName}/dbt/`,
          GLUE_SESSION_ID: 'etl-dbt-session',
        },
      },
    );

    // ── CloudWatch Alarms for dbt pipeline health ──────────

    // SNS topic for alarm notifications — subscribe via console or CLI
    const alarmTopic = new sns.Topic(this, 'DbtAlarmTopic', {
      topicName: 'etl-dbt-alarms',
      displayName: 'ETL dbt Pipeline Alarms',
    });

    // Alarm: any model failures in a run
    const failedModelsAlarm = new cloudwatch.Alarm(
      this,
      'DbtModelsFailedAlarm',
      {
        alarmName: 'etl-dbt-models-failed',
        alarmDescription:
          'Triggers when one or more dbt models fail during a run.',
        metric: new cloudwatch.Metric({
          namespace: 'ETL/dbt',
          metricName: 'ModelsFailed',
          dimensionsMap: {
            Project: 'etl_pipeline',
          },
          statistic: 'Maximum',
          period: cdk.Duration.minutes(5),
        }),
        threshold: 1,
        evaluationPeriods: 1,
        comparisonOperator:
          cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      },
    );
    failedModelsAlarm.addAlarmAction(new cw_actions.SnsAction(alarmTopic));

    // Alarm: total execution time exceeds 30 minutes
    const longRunAlarm = new cloudwatch.Alarm(this, 'DbtLongRunAlarm', {
      alarmName: 'etl-dbt-long-execution',
      alarmDescription:
        'Triggers when total dbt execution time exceeds 30 minutes.',
      metric: new cloudwatch.Metric({
        namespace: 'ETL/dbt',
        metricName: 'TotalExecutionTime',
        dimensionsMap: {
          Project: 'etl_pipeline',
        },
        statistic: 'Maximum',
        period: cdk.Duration.minutes(5),
      }),
      threshold: 1800,
      evaluationPeriods: 1,
      comparisonOperator:
        cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
    longRunAlarm.addAlarmAction(new cw_actions.SnsAction(alarmTopic));

    // Outputs
    new cdk.CfnOutput(this, 'AlarmTopicArn', {
      value: alarmTopic.topicArn,
      description:
        'SNS topic for dbt pipeline alarms — subscribe your email or Slack',
      exportName: 'EtlDbtAlarmTopicArn',
    });

    new cdk.CfnOutput(this, 'ClusterArn', {
      value: this.cluster.clusterArn,
      description: 'ECS cluster ARN',
      exportName: 'EtlEcsClusterArn',
    });

    new cdk.CfnOutput(this, 'TaskDefinitionArn', {
      value: this.taskDefinition.taskDefinitionArn,
      description: 'ECS task definition ARN',
      exportName: 'EtlDbtTaskDefinitionArn',
    });
  }
}
