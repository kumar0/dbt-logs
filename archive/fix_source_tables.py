#!/usr/bin/env python3
"""
Fix Iceberg tables in etl_source_db by adding required InputFormat and OutputFormat
"""
import boto3
import sys

def fix_table(glue_client, database_name, table_name):
    """Fix a single table by adding InputFormat and OutputFormat"""
    try:
        # Get current table definition
        response = glue_client.get_table(DatabaseName=database_name, Name=table_name)
        table = response['Table']
        
        # Check if already has InputFormat
        storage_descriptor = table['StorageDescriptor']
        if storage_descriptor.get('InputFormat'):
            print(f"⊙ Table {table_name} already has InputFormat, skipping")
            return True
        
        # Update StorageDescriptor with required formats
        storage_descriptor['InputFormat'] = 'org.apache.iceberg.mr.hive.HiveIcebergInputFormat'
        storage_descriptor['OutputFormat'] = 'org.apache.iceberg.mr.hive.HiveIcebergOutputFormat'
        
        # Preserve or add SerdeInfo
        if 'SerdeInfo' not in storage_descriptor:
            storage_descriptor['SerdeInfo'] = {}
        storage_descriptor['SerdeInfo']['SerializationLibrary'] = 'org.apache.iceberg.mr.hive.HiveIcebergSerDe'
        if 'Parameters' not in storage_descriptor['SerdeInfo']:
            storage_descriptor['SerdeInfo']['Parameters'] = {}
        
        # Update the table
        table_input = {
            'Name': table['Name'],
            'StorageDescriptor': storage_descriptor,
            'Parameters': table.get('Parameters', {}),
        }
        
        # Add optional fields if they exist
        if 'Description' in table:
            table_input['Description'] = table['Description']
        if 'Owner' in table:
            table_input['Owner'] = table['Owner']
        if 'PartitionKeys' in table:
            table_input['PartitionKeys'] = table['PartitionKeys']
        if 'TableType' in table:
            table_input['TableType'] = table['TableType']
        
        glue_client.update_table(
            DatabaseName=database_name,
            TableInput=table_input
        )
        
        print(f"✓ Fixed table: {table_name}")
        return True
        
    except Exception as e:
        print(f"✗ Error fixing table {table_name}: {str(e)}")
        return False

def main():
    # Initialize Glue client with profile
    session = boto3.Session(profile_name='mondayskills.development', region_name='us-east-1')
    glue_client = session.client('glue')
    
    database_name = 'etl_source_db'
    tables = ['customers', 'products', 'orders', 'order_items', 'payments']
    
    print(f"Fixing Iceberg tables in {database_name}...")
    print()
    
    success_count = 0
    for table_name in tables:
        if fix_table(glue_client, database_name, table_name):
            success_count += 1
    
    print()
    print(f"Fixed {success_count}/{len(tables)} tables")
    
    if success_count == len(tables):
        print("All tables fixed successfully!")
        return 0
    else:
        print("Some tables failed to fix")
        return 1

if __name__ == '__main__':
    sys.exit(main())
