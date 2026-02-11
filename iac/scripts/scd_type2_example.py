#!/usr/bin/env python3
"""
Example implementation of SCD Type 2 logic for dimension tables.
This demonstrates how to handle updates to dimension records.
"""

import boto3
from datetime import datetime
from decimal import Decimal
import uuid

AWS_PROFILE = 'mondayskills.development'
AWS_REGION = 'us-east-1'

session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
dynamodb = session.resource('dynamodb')


class SCDType2Handler:
    """Handler for SCD Type 2 operations on dimension tables."""
    
    def __init__(self, table_name):
        self.table = dynamodb.Table(table_name)
    
    def get_current_record(self, natural_key):
        """Get the current active record for a natural key."""
        response = self.table.query(
            IndexName='current-records-index',
            KeyConditionExpression='natural_key = :nk AND is_current = :curr',
            ExpressionAttributeValues={
                ':nk': natural_key,
                ':curr': 'Y'
            }
        )
        
        items = response.get('Items', [])
        return items[0] if items else None
    
    def expire_current_record(self, surrogate_key, effective_date, end_date):
        """Expire the current record by setting is_current to 'N' and adding end_date."""
        self.table.update_item(
            Key={
                'customer_sk': surrogate_key,
                'effective_date': effective_date
            },
            UpdateExpression='SET is_current = :n, end_date = :end',
            ExpressionAttributeValues={
                ':n': 'N',
                ':end': end_date
            }
        )
    
    def insert_new_record(self, record_data):
        """Insert a new dimension record."""
        self.table.put_item(Item=record_data)
    
    def handle_customer_change(self, customer_data):
        """
        Handle a customer change with SCD Type 2 logic.
        
        Process:
        1. Check if current record exists
        2. If exists and data changed:
           - Expire current record (set is_current='N', add end_date)
           - Insert new record (new surrogate key, is_current='Y')
        3. If not exists:
           - Insert new record
        """
        natural_key = customer_data['customer_id']
        current_record = self.get_current_record(natural_key)
        
        now = datetime.now().isoformat()
        
        if current_record:
            # Check if data has changed (compare tracked attributes)
            tracked_attrs = ['first_name', 'last_name', 'email', 'phone', 'address', 'city', 'state', 'zip_code']
            has_changed = any(
                current_record.get(attr) != customer_data.get(attr)
                for attr in tracked_attrs
            )
            
            if has_changed:
                print(f'Change detected for customer {natural_key}')
                
                # Expire current record
                self.expire_current_record(
                    current_record['customer_sk'],
                    current_record['effective_date'],
                    now
                )
                
                # Create new record
                new_record = {
                    'customer_sk': f'SK-{str(uuid.uuid4())}',
                    'effective_date': now,
                    'end_date': None,
                    'is_current': 'Y',
                    'natural_key': natural_key,
                    **customer_data
                }
                
                self.insert_new_record(new_record)
                print(f'✓ Created new version for customer {natural_key}')
            else:
                print(f'No change detected for customer {natural_key}')
        else:
            # New customer - insert first record
            new_record = {
                'customer_sk': f'SK-{str(uuid.uuid4())}',
                'effective_date': now,
                'end_date': None,
                'is_current': 'Y',
                'natural_key': natural_key,
                **customer_data
            }
            
            self.insert_new_record(new_record)
            print(f'✓ Created initial record for customer {natural_key}')


def example_usage():
    """Example of using SCD Type 2 handler."""
    handler = SCDType2Handler('etl_dest_dimcustomers')
    
    # Example 1: New customer
    print('\n--- Example 1: New Customer ---')
    customer1 = {
        'customer_id': 'CUST-12345',
        'first_name': 'John',
        'last_name': 'Doe',
        'email': 'john.doe@example.com',
        'phone': '+1-555-1234',
        'address': '123 Main St',
        'city': 'New York',
        'state': 'NY',
        'zip_code': '10001',
        'status': 'active'
    }
    handler.handle_customer_change(customer1)
    
    # Example 2: Customer address change
    print('\n--- Example 2: Customer Address Change ---')
    customer1_updated = {
        **customer1,
        'address': '456 Oak Ave',
        'city': 'Los Angeles',
        'state': 'CA',
        'zip_code': '90001'
    }
    handler.handle_customer_change(customer1_updated)
    
    # Example 3: No change (should not create new version)
    print('\n--- Example 3: No Change ---')
    handler.handle_customer_change(customer1_updated)
    
    print('\n✓ SCD Type 2 examples completed')


if __name__ == '__main__':
    print('=' * 60)
    print('SCD Type 2 Implementation Example')
    print('=' * 60)
    
    try:
        example_usage()
    except Exception as e:
        print(f'\n✗ Error: {str(e)}')
        raise
