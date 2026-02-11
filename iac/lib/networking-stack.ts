import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Construct } from 'constructs';

export interface NetworkingStackProps extends cdk.StackProps {
  vpcId: string;
}

export class NetworkingStack extends cdk.Stack {
  public readonly vpc: ec2.IVpc;
  public readonly ecsSecurityGroup: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props: NetworkingStackProps) {
    super(scope, id, props);

    // Look up the existing VPC
    this.vpc = ec2.Vpc.fromLookup(this, 'ExistingVpc', {
      vpcId: props.vpcId,
    });

    // Security group for ECS Fargate tasks
    this.ecsSecurityGroup = new ec2.SecurityGroup(this, 'EcsSecurityGroup', {
      vpc: this.vpc,
      description: 'Security group for ETL dbt ECS Fargate tasks',
      allowAllOutbound: true,
    });

    new cdk.CfnOutput(this, 'VpcId', {
      value: this.vpc.vpcId,
      description: 'VPC ID used for ECS tasks',
    });

    new cdk.CfnOutput(this, 'SecurityGroupId', {
      value: this.ecsSecurityGroup.securityGroupId,
      description: 'Security group ID for ECS tasks',
    });
  }
}
