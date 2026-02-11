import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as glue from 'aws-cdk-lib/aws-glue';
import * as athena from 'aws-cdk-lib/aws-athena';
import * as cr from 'aws-cdk-lib/custom-resources';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';

export class EtlDatabaseStack extends cdk.Stack {
  public readonly dataLakeBucket: s3.Bucket;
  public readonly athenaResultsBucket: s3.Bucket;
  public readonly sourceDatabase: glue.CfnDatabase;
  public readonly destDatabase: glue.CfnDatabase;
  public readonly glueJobRole: iam.Role;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // S3 bucket for data lake storage
    this.dataLakeBucket = new s3.Bucket(this, 'DataLakeBucket', {
      bucketName: `etl-datalake-${this.account}-${this.region}`,
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      lifecycleRules: [
        {
          id: 'archive-old-versions',
          noncurrentVersionExpiration: cdk.Duration.days(90),
        },
      ],
    });

    // S3 bucket for Athena query results
    this.athenaResultsBucket = new s3.Bucket(this, 'AthenaResultsBucket', {
      bucketName: `etl-athena-results-${this.account}-${this.region}`,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      lifecycleRules: [
        {
          id: 'cleanup-old-results',
          expiration: cdk.Duration.days(7),
        },
      ],
    });

    // Glue Database for source tables
    this.sourceDatabase = new glue.CfnDatabase(this, 'SourceDatabase', {
      catalogId: this.account,
      databaseInput: {
        name: 'etl_source_db',
        description: 'Source database for ETL platform - transactional data',
        locationUri: `s3://${this.dataLakeBucket.bucketName}/source/`,
      },
    });

    // Glue Database for destination tables
    this.destDatabase = new glue.CfnDatabase(this, 'DestDatabase', {
      catalogId: this.account,
      databaseInput: {
        name: 'etl_dest_db',
        description:
          'Destination database for ETL platform - analytical data with SCD Type 2',
        locationUri: `s3://${this.dataLakeBucket.bucketName}/destination/`,
      },
    });

    // IAM role for Glue jobs and dbt
    this.glueJobRole = new iam.Role(this, 'GlueJobRole', {
      roleName: `etl-glue-job-role-${this.region}`,
      assumedBy: new iam.ServicePrincipal('glue.amazonaws.com'),
      description: 'IAM role for Glue jobs and dbt transformations',
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          'service-role/AWSGlueServiceRole',
        ),
      ],
    });

    // Grant Glue role access to data lake bucket
    this.dataLakeBucket.grantReadWrite(this.glueJobRole);
    this.athenaResultsBucket.grantReadWrite(this.glueJobRole);

    // Grant Glue role access to Glue catalog
    this.glueJobRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
          'glue:SearchTables',
          'glue:GetDatabase',
          'glue:GetDatabases',
          'glue:CreateDatabase',
          'glue:UpdateDatabase',
          'glue:GetTable',
          'glue:GetTables',
          'glue:GetTableVersion',
          'glue:GetTableVersions',
          'glue:GetPartition',
          'glue:GetPartitions',
          'glue:CreateTable',
          'glue:UpdateTable',
          'glue:DeleteTable',
          'glue:DeleteTableVersion',
          'glue:BatchDeleteTableVersion',
          'glue:BatchDeleteTable',
          'glue:BatchCreatePartition',
          'glue:BatchDeletePartition',
          'glue:BatchUpdatePartition',
          'glue:CreatePartition',
          'glue:DeletePartition',
          'glue:UpdateColumnStatisticsForTable',
          'glue:UpdateColumnStatisticsForPartition',
          'glue:GetUserDefinedFunctions',
        ],
        resources: [
          `arn:aws:glue:${this.region}:${this.account}:catalog`,
          `arn:aws:glue:${this.region}:${this.account}:database/*`,
          `arn:aws:glue:${this.region}:${this.account}:table/*/*`,
        ],
      }),
    );

    // Grant permissions for Glue Interactive Sessions (required for dbt-glue)
    this.glueJobRole.addToPolicy(
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
        ],
        resources: [`arn:aws:glue:${this.region}:${this.account}:session/*`],
      }),
    );

    // Grant CloudWatch Logs permissions for Glue sessions
    this.glueJobRole.addToPolicy(
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

    // Grant CloudWatch Metrics permissions (required for --enable-metrics=true)
    this.glueJobRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ['cloudwatch:PutMetricData'],
        resources: ['*'],
        conditions: {
          StringEquals: {
            'cloudwatch:namespace': 'Glue',
          },
        },
      }),
    );

    // Grant IAM PassRole permission (required for Glue to assume the role)
    this.glueJobRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ['iam:PassRole'],
        resources: [this.glueJobRole.roleArn],
        conditions: {
          StringLike: {
            'iam:PassedToService': 'glue.amazonaws.com',
          },
        },
      }),
    );

    // Athena Workgroup
    const workgroup = new athena.CfnWorkGroup(this, 'EtlWorkgroup', {
      name: 'etl-workgroup',
      workGroupConfiguration: {
        resultConfiguration: {
          outputLocation: `s3://${this.athenaResultsBucket.bucketName}/`,
        },
        engineVersion: {
          selectedEngineVersion: 'Athena engine version 3',
        },
      },
    });

    // IAM role for custom resource Lambda
    const customResourceRole = new iam.Role(this, 'CustomResourceRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          'service-role/AWSLambdaBasicExecutionRole',
        ),
      ],
    });

    customResourceRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
          'athena:StartQueryExecution',
          'athena:GetQueryExecution',
          'athena:GetQueryResults',
        ],
        resources: [
          `arn:aws:athena:${this.region}:${this.account}:workgroup/${workgroup.name}`,
        ],
      }),
    );

    customResourceRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
          'glue:GetDatabase',
          'glue:GetTable',
          'glue:CreateTable',
          'glue:UpdateTable',
          'glue:DeleteTable',
        ],
        resources: [
          `arn:aws:glue:${this.region}:${this.account}:catalog`,
          `arn:aws:glue:${this.region}:${this.account}:database/${this.sourceDatabase.ref}`,
          `arn:aws:glue:${this.region}:${this.account}:database/${this.destDatabase.ref}`,
          `arn:aws:glue:${this.region}:${this.account}:table/${this.sourceDatabase.ref}/*`,
          `arn:aws:glue:${this.region}:${this.account}:table/${this.destDatabase.ref}/*`,
        ],
      }),
    );

    customResourceRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
          's3:GetBucketLocation',
          's3:GetObject',
          's3:ListBucket',
          's3:PutObject',
          's3:DeleteObject',
        ],
        resources: [
          this.dataLakeBucket.bucketArn,
          `${this.dataLakeBucket.bucketArn}/*`,
          this.athenaResultsBucket.bucketArn,
          `${this.athenaResultsBucket.bucketArn}/*`,
        ],
      }),
    );

    // Create source tables using Athena
    this.createSourceTableViaAthena(
      'customers',
      `
      customer_id string,
      first_name string,
      last_name string,
      email string,
      phone string,
      address string,
      city string,
      state string,
      zip_code string,
      status string,
      created_at timestamp,
      updated_at timestamp
    `,
      workgroup,
      customResourceRole,
    );

    this.createSourceTableViaAthena(
      'products',
      `
      product_id string,
      name string,
      category string,
      price decimal(10,2),
      cost decimal(10,2),
      stock_quantity int,
      supplier string,
      status string,
      created_at timestamp,
      updated_at timestamp
    `,
      workgroup,
      customResourceRole,
    );

    this.createSourceTableViaAthena(
      'orders',
      `
      order_id string,
      customer_id string,
      order_date timestamp,
      order_status string,
      total_amount decimal(10,2),
      shipping_address string,
      shipping_city string,
      shipping_state string,
      shipping_zip string,
      created_at timestamp,
      updated_at timestamp
    `,
      workgroup,
      customResourceRole,
    );

    this.createSourceTableViaAthena(
      'order_items',
      `
      order_item_id string,
      order_id string,
      product_id string,
      quantity int,
      unit_price decimal(10,2),
      line_total decimal(10,2),
      discount decimal(10,2),
      created_at timestamp
    `,
      workgroup,
      customResourceRole,
    );

    this.createSourceTableViaAthena(
      'payments',
      `
      payment_id string,
      order_id string,
      payment_method string,
      payment_status string,
      amount decimal(10,2),
      payment_date timestamp,
      transaction_id string,
      created_at timestamp
    `,
      workgroup,
      customResourceRole,
    );

    // Create destination tables using Athena
    this.createDestTableViaAthena(
      'dim_customers',
      `
      customer_sk string,
      customer_id string,
      first_name string,
      last_name string,
      email string,
      phone string,
      address string,
      city string,
      state string,
      zip_code string,
      status string,
      effective_date timestamp,
      end_date timestamp,
      is_current string,
      created_at timestamp,
      updated_at timestamp
    `,
      'is_current',
      workgroup,
      customResourceRole,
    );

    this.createDestTableViaAthena(
      'dim_products',
      `
      product_sk string,
      product_id string,
      name string,
      category string,
      price decimal(10,2),
      cost decimal(10,2),
      supplier string,
      status string,
      effective_date timestamp,
      end_date timestamp,
      is_current string,
      created_at timestamp,
      updated_at timestamp
    `,
      'is_current',
      workgroup,
      customResourceRole,
    );

    this.createDestTableViaAthena(
      'fact_orders',
      `
      order_sk string,
      order_id string,
      customer_sk string,
      order_date timestamp,
      order_status string,
      total_amount decimal(10,2),
      total_items int,
      shipping_city string,
      shipping_state string,
      created_at timestamp
    `,
      null,
      workgroup,
      customResourceRole,
    );

    this.createDestTableViaAthena(
      'fact_order_items',
      `
      order_item_sk string,
      order_sk string,
      product_sk string,
      order_id string,
      product_id string,
      quantity int,
      unit_price decimal(10,2),
      line_total decimal(10,2),
      discount decimal(10,2),
      created_at timestamp
    `,
      null,
      workgroup,
      customResourceRole,
    );

    // Outputs
    new cdk.CfnOutput(this, 'DataLakeBucketName', {
      value: this.dataLakeBucket.bucketName,
      description: 'S3 bucket for data lake storage',
    });

    new cdk.CfnOutput(this, 'AthenaResultsBucketName', {
      value: this.athenaResultsBucket.bucketName,
      description: 'S3 bucket for Athena query results',
    });

    new cdk.CfnOutput(this, 'SourceDatabaseName', {
      value: this.sourceDatabase.ref,
      description: 'Glue database for source tables',
    });

    new cdk.CfnOutput(this, 'DestDatabaseName', {
      value: this.destDatabase.ref,
      description: 'Glue database for destination tables',
    });

    new cdk.CfnOutput(this, 'AthenaWorkgroupName', {
      value: workgroup.name!,
      description: 'Athena workgroup for queries',
    });

    new cdk.CfnOutput(this, 'GlueJobRoleArn', {
      value: this.glueJobRole.roleArn,
      description: 'IAM role ARN for Glue jobs and dbt',
      exportName: 'EtlGlueJobRoleArn',
    });

    new cdk.CfnOutput(this, 'DataLakeLocation', {
      value: `s3://${this.dataLakeBucket.bucketName}/dbt/`,
      description: 'S3 location for dbt outputs',
      exportName: 'EtlDataLakeLocation',
    });
  }

  private createSourceTableViaAthena(
    tableName: string,
    columns: string,
    workgroup: athena.CfnWorkGroup,
    role: iam.Role,
  ): void {
    const createTableQuery = `
      CREATE TABLE IF NOT EXISTS etl_source_db.${tableName} (
        ${columns}
      )
      LOCATION 's3://${this.dataLakeBucket.bucketName}/source/${tableName}/'
      TBLPROPERTIES (
        'table_type'='ICEBERG',
        'format'='parquet',
        'write_compression'='snappy'
      )
    `;

    new cr.AwsCustomResource(
      this,
      `CreateSourceTable${this.toPascalCase(tableName)}`,
      {
        onCreate: {
          service: 'Athena',
          action: 'startQueryExecution',
          parameters: {
            QueryString: createTableQuery,
            WorkGroup: workgroup.name,
            ResultConfiguration: {
              OutputLocation: `s3://${this.athenaResultsBucket.bucketName}/`,
            },
          },
          physicalResourceId: cr.PhysicalResourceId.of(
            `source-${tableName}-${Date.now()}`,
          ),
        },
        policy: cr.AwsCustomResourcePolicy.fromSdkCalls({
          resources: cr.AwsCustomResourcePolicy.ANY_RESOURCE,
        }),
        role: role,
        logRetention: logs.RetentionDays.ONE_DAY,
      },
    );
  }

  private createDestTableViaAthena(
    tableName: string,
    columns: string,
    partitionColumn: string | null,
    workgroup: athena.CfnWorkGroup,
    role: iam.Role,
  ): void {
    const partitionClause = partitionColumn
      ? `PARTITIONED BY (${partitionColumn})`
      : '';

    const createTableQuery = `
      CREATE TABLE IF NOT EXISTS etl_dest_db.${tableName} (
        ${columns}
      )
      ${partitionClause}
      LOCATION 's3://${this.dataLakeBucket.bucketName}/destination/${tableName}/'
      TBLPROPERTIES (
        'table_type'='ICEBERG',
        'format'='parquet',
        'write_compression'='snappy'
      )
    `;

    new cr.AwsCustomResource(
      this,
      `CreateDestTable${this.toPascalCase(tableName)}`,
      {
        onCreate: {
          service: 'Athena',
          action: 'startQueryExecution',
          parameters: {
            QueryString: createTableQuery,
            WorkGroup: workgroup.name,
            ResultConfiguration: {
              OutputLocation: `s3://${this.athenaResultsBucket.bucketName}/`,
            },
          },
          physicalResourceId: cr.PhysicalResourceId.of(
            `dest-${tableName}-${Date.now()}`,
          ),
        },
        policy: cr.AwsCustomResourcePolicy.fromSdkCalls({
          resources: cr.AwsCustomResourcePolicy.ANY_RESOURCE,
        }),
        role: role,
        logRetention: logs.RetentionDays.ONE_DAY,
      },
    );
  }

  private toPascalCase(str: string): string {
    return str
      .split('_')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join('');
  }
}
