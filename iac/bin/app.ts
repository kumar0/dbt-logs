#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { EtlDatabaseStack } from '../lib/etl-database-stack';
import { EcrStack } from '../lib/ecr-stack';
import { NetworkingStack } from '../lib/networking-stack';
import { ComputeStack } from '../lib/compute-stack';
import { OrchestrationStack } from '../lib/orchestration-stack';
import { SfnTestHarnessStack } from '../lib/sfn-test-harness-stack';

const app = new cdk.App();

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION || 'us-east-1',
};

// Existing database stack
const databaseStack = new EtlDatabaseStack(app, 'EtlDatabaseStack', {
  env,
  description: 'ETL Platform with source and destination tables (SCD Type 2)',
});

// ECR repository for dbt Docker image
const ecrStack = new EcrStack(app, 'EtlEcrStack', {
  env,
  description: 'ECR repository for ETL dbt Docker image',
});

// Networking — uses existing VPC, creates security group
const networkingStack = new NetworkingStack(app, 'EtlNetworkingStack', {
  env,
  description: 'Networking resources for ETL ECS Fargate tasks',
  vpcId: 'vpc-0a2290ed34b346805',
});

// ECS cluster + Fargate task definition
const computeStack = new ComputeStack(app, 'EtlComputeStack', {
  env,
  description: 'ECS Fargate cluster and dbt task definition',
  vpc: networkingStack.vpc,
  repository: ecrStack.repository,
  glueJobRoleArn: databaseStack.glueJobRole.roleArn,
  dataLakeBucketName: databaseStack.dataLakeBucket.bucketName,
});
computeStack.addDependency(networkingStack);
computeStack.addDependency(ecrStack);
computeStack.addDependency(databaseStack);

// Step Functions orchestration
const orchestrationStack = new OrchestrationStack(
  app,
  'EtlOrchestrationStack',
  {
    env,
    description: 'Step Functions state machine for dbt pipeline orchestration',
    cluster: computeStack.cluster,
    taskDefinition: computeStack.taskDefinition,
    containerDefinition: computeStack.containerDefinition,
    securityGroup: networkingStack.ecsSecurityGroup,
    subnets: { subnetType: cdk.aws_ec2.SubnetType.PRIVATE_WITH_EGRESS },
    dataLakeBucketName: databaseStack.dataLakeBucket.bucketName,
    glueJobRoleArn: databaseStack.glueJobRole.roleArn,
    vpc: networkingStack.vpc,
  },
);
orchestrationStack.addDependency(databaseStack);
orchestrationStack.addDependency(computeStack);

// SFN Test Harness — standalone test state machines for dashboard testing
new SfnTestHarnessStack(app, 'SfnTestHarnessStack', {
  env,
  description: 'Step Functions test harness for dashboard testing',
  environments: ['test', 'test2'],
});

app.synth();
