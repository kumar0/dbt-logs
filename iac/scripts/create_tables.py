#!/usr/bin/env python3
"""
Script to create Iceberg tables in Glue using awswrangler.
This properly initializes Iceberg metadata.
"""

import awswrangler as wr
import pandas as pd
import boto3

# AWS Configuration
AWS_PROFILE = 'mondayskills.development'
AWS_REGION = 'us-east-1'
ACCOUNT_ID = boto3.Session(profile_name=AWS_PROFILE).client('sts').get_caller_identity()['Account']

# Initialize boto3 session
session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)

# Source table schemas
SOURCE_TABLES = {
    'customers': {
        'customer_id': 'string',
        'first_name': 'string',
        'last_name': 'string',
        'email': 'string',
        'phone': 'string',
        'address': 'string',
        'city': 'string',
        'state': 'string',
        'zip_code': 'string',
        'status': 'string',
        'created_at': 'timestamp',
        'updated_at': 'timestamp',
    },
    'products': {
        'product_id': 'string',
        'name': 'string',
        'category': 'string',
        'price': 'float',
        'cost': 'float',
        'stock_quantity': 'int',
        'supplier': 'string',
        'status': 'string',
        'created_at': 'timestamp',
        'updated_at': 'timestamp',
    },
    'orders': {
        'order_id': 'string',
        'customer_id': 'string',
        'order_date': 'timestamp',
        'order_status': 'string',
        'total_amount': 'float',
        'shipping_address': 'string',
        'shipping_city': 'string',
        'shipping_state': 'string',
        'shipping_zip': 'string',
        'created_at': 'timestamp',
        'updated_at': 'timestamp',
    },
    'order_items': {
        'order_item_id': 'string',
        'order_id': 'string',
        'product_id': 'string',
        'quantity': 'int',
        'unit_price': 'float',
        'line_total': 'float',
        'discount': 'float',
        'created_at': 'timestamp',
    },
    'payments': {
        'payment_id': 'string',
        'order_id': 'string',
        'payment_method': 'string',
        'payment_status': 'string',
        'amount': 'float',
        'payment_date': 'timestamp',
        'transaction_id': 'string',
        'created_at': 'timestamp',
    },
}

# Destination table schemas
DEST_TABLES = {
    'dim_customers': {
        'customer_sk': 'string',
        'customer_id': 'string',
        'first_name': 'string',
        'last_name': 'string',
        'email': 'string',
        'phone': 'string',
        'address': 'string',
        'city': 'string',
        'state': 'string',
        'zip_code': 'string',
        'status': 'string',
        'effective_date': 'timestamp',
        'end_date': 'timestamp',
        'is_current': 'string',
        'created_at': 'timestamp',
        'updated_at': 'timestamp',
    },
    'dim_products': {
        'product_sk': 'string',
        'product_id': 'string',
        'name': 'string',
        'category': 'string',
        'price': 'float',
        'cost': 'float',
        'supplier': 'string',
        'status': 'string',
        'effective_date': 'timestamp',
        'end_date': 'timestamp',
        'is_current': 'string',
        'created_at': 'timestamp',
        'updated_at': 'timestamp',
    },
    'fact_orders': {
        'order_sk': 'string',
        'order_id': 'string',
        'customer_sk': 'string',
        'order_date': 'timestamp',
        'order_status': 'string',
        'total_amount': 'float',
        'total_items': 'int',
        'shipping_city': 'string',
        'shipping_state': 'string',
        'created_at': 'timestamp',
    },
    'fact_order_items': {
        'order_item_sk': 'string',
        'order_sk': 'string',
        'product_sk': 'string',
        'order_id': 'string',
        'product_id': 'string',
        'quantity': 'int',
        'unit_price': 'float',
        'line_total': 'float',
        'discount': 'float',
        'created_at': 'timestamp',
    },
}


def create_empty_dataframe(schema):
    """Create an empty DataFrame with the specified schema."""
    dtype_map = {
        'string': 'object',
        'int': 'Int64',
        'float': 'float64',
        'timestamp': 'datetime64[ns]',
    }
    return pd.DataFrame({col: pd.Series(dtype=dtype_map.get(dtype, dtype)) for col, dtype in schema.items()})


def create_iceberg_table(database, table_name, schema, session, partition_cols=None):
    """Create an Iceberg table by writing an empty DataFrame."""
    print(f'Creating {database}.{table_name}...')
    
    try:
        # Create empty DataFrame with schema
        df = create_empty_dataframe(schema)
        
        # Write to Iceberg (this initializes the table)
        wr.athena.to_iceberg(
            df=df,
            database=database,
            table=table_name,
            table_location=f's3://etl-datalake-{ACCOUNT_ID}-{AWS_REGION}/{database.replace("etl_", "")}/{table_name}/',
            temp_path=f's3://etl-datalake-{ACCOUNT_ID}-{AWS_REGION}/temp/',
            partition_cols=partition_cols,
            boto3_session=session,
            keep_files=False,
        )
        
        print(f'✓ Created {database}.{table_name}')
        return True
        
    except Exception as e:
        if 'AlreadyExistsException' in str(e) or 'already exists' in str(e).lower():
            print(f'  Table {database}.{table_name} already exists, skipping...')
            return True
        else:
            print(f'✗ Error creating {database}.{table_name}: {str(e)}')
            return False


def main():
    """Main function to create all Iceberg tables."""
    print('=' * 60)
    print('ETL Platform - Iceberg Table Creation')
    print('=' * 60)
    print(f'AWS Profile: {AWS_PROFILE}')
    print(f'AWS Region: {AWS_REGION}')
    print(f'Account ID: {ACCOUNT_ID}')
    print('=' * 60)
    
    success_count = 0
    total_count = 0
    
    # Create source tables
    print('\n[1/2] Creating source tables...')
    for table_name, schema in SOURCE_TABLES.items():
        total_count += 1
        if create_iceberg_table('etl_source_db', table_name, schema, session):
            success_count += 1
    
    # Create destination tables
    print('\n[2/2] Creating destination tables...')
    for table_name, schema in DEST_TABLES.items():
        total_count += 1
        # Dimension tables are partitioned by is_current
        partition_cols = ['is_current'] if table_name.startswith('dim_') else None
        if create_iceberg_table('etl_dest_db', table_name, schema, session, partition_cols):
            success_count += 1
    
    print('\n' + '=' * 60)
    if success_count == total_count:
        print(f'✓ All {total_count} tables created successfully!')
    else:
        print(f'⚠ Created {success_count}/{total_count} tables')
    print('=' * 60)
    
    print('\nYou can now query tables in Athena:')
    print('  SELECT * FROM etl_source_db.customers LIMIT 10;')
    print('  SELECT * FROM etl_dest_db.dim_customers LIMIT 10;')


if __name__ == '__main__':
    main()
