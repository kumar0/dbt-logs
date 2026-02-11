#!/usr/bin/env python3
"""
Script to populate Glue Iceberg source tables with sample data.
Uses AWS SDK for Pandas (awswrangler) to write data to Iceberg tables.
"""

import awswrangler as wr
import pandas as pd
import boto3
from datetime import datetime, timedelta
import random
import uuid
from decimal import Decimal

# AWS Configuration
AWS_PROFILE = 'mondayskills.development'
AWS_REGION = 'us-east-1'
DATABASE_NAME = 'etl_source_db'

# Initialize boto3 session
session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)


def generate_customers_df(count=50):
    """Generate sample customer data as DataFrame."""
    first_names = ['John', 'Jane', 'Michael', 'Sarah', 'David', 'Emily', 'Robert', 'Lisa', 'James', 'Mary']
    last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez']
    
    data = []
    for i in range(count):
        data.append({
            'customer_id': f'CUST-{str(uuid.uuid4())[:8]}',
            'first_name': random.choice(first_names),
            'last_name': random.choice(last_names),
            'email': f'customer{i}@example.com',
            'phone': f'+1-555-{random.randint(1000, 9999)}',
            'address': f'{random.randint(100, 9999)} Main St',
            'city': random.choice(['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix']),
            'state': random.choice(['NY', 'CA', 'IL', 'TX', 'AZ']),
            'zip_code': f'{random.randint(10000, 99999)}',
            'status': random.choice(['active', 'active', 'active', 'inactive']),
            'created_at': datetime.now() - timedelta(days=random.randint(1, 365)),
            'updated_at': datetime.now(),
        })
    
    return pd.DataFrame(data)


def generate_products_df(count=30):
    """Generate sample product data as DataFrame."""
    categories = ['Electronics', 'Clothing', 'Home & Garden', 'Sports', 'Books']
    product_names = {
        'Electronics': ['Laptop', 'Smartphone', 'Tablet', 'Headphones', 'Camera'],
        'Clothing': ['T-Shirt', 'Jeans', 'Jacket', 'Sneakers', 'Dress'],
        'Home & Garden': ['Lamp', 'Chair', 'Table', 'Plant', 'Rug'],
        'Sports': ['Basketball', 'Tennis Racket', 'Yoga Mat', 'Dumbbells', 'Bicycle'],
        'Books': ['Novel', 'Cookbook', 'Biography', 'Textbook', 'Magazine'],
    }
    
    data = []
    for i in range(count):
        category = random.choice(categories)
        data.append({
            'product_id': f'PROD-{str(uuid.uuid4())[:8]}',
            'name': f'{random.choice(product_names[category])} {random.randint(1, 100)}',
            'category': category,
            'price': round(random.uniform(9.99, 999.99), 2),
            'cost': round(random.uniform(5.00, 500.00), 2),
            'stock_quantity': random.randint(0, 500),
            'supplier': f'Supplier-{random.randint(1, 10)}',
            'status': random.choice(['active', 'active', 'discontinued']),
            'created_at': datetime.now() - timedelta(days=random.randint(1, 180)),
            'updated_at': datetime.now(),
        })
    
    return pd.DataFrame(data)


def generate_orders_df(customers_df, count=100):
    """Generate sample order data as DataFrame."""
    data = []
    customer_ids = customers_df['customer_id'].tolist()
    
    for i in range(count):
        order_date = datetime.now() - timedelta(days=random.randint(1, 90))
        data.append({
            'order_id': f'ORD-{str(uuid.uuid4())[:8]}',
            'customer_id': random.choice(customer_ids),
            'order_date': order_date,
            'order_status': random.choice(['pending', 'processing', 'shipped', 'delivered', 'cancelled']),
            'total_amount': 0.0,  # Will be calculated from order items
            'shipping_address': f'{random.randint(100, 9999)} Delivery St',
            'shipping_city': random.choice(['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix']),
            'shipping_state': random.choice(['NY', 'CA', 'IL', 'TX', 'AZ']),
            'shipping_zip': f'{random.randint(10000, 99999)}',
            'created_at': order_date,
            'updated_at': datetime.now(),
        })
    
    return pd.DataFrame(data)


def generate_order_items_df(orders_df, products_df, avg_items_per_order=3):
    """Generate sample order items data as DataFrame."""
    data = []
    product_ids = products_df['product_id'].tolist()
    product_prices = dict(zip(products_df['product_id'], products_df['price']))
    
    order_totals = {}
    
    for _, order in orders_df.iterrows():
        num_items = random.randint(1, avg_items_per_order * 2)
        order_total = 0.0
        
        for i in range(num_items):
            product_id = random.choice(product_ids)
            quantity = random.randint(1, 5)
            unit_price = product_prices[product_id]
            line_total = unit_price * quantity
            order_total += line_total
            
            data.append({
                'order_item_id': f'ITEM-{str(uuid.uuid4())[:8]}',
                'order_id': order['order_id'],
                'product_id': product_id,
                'quantity': quantity,
                'unit_price': unit_price,
                'line_total': line_total,
                'discount': round(random.uniform(0, 10), 2),
                'created_at': order['order_date'],
            })
        
        order_totals[order['order_id']] = order_total
    
    # Update order totals
    orders_df['total_amount'] = orders_df['order_id'].map(order_totals)
    
    return pd.DataFrame(data), orders_df


def generate_payments_df(orders_df):
    """Generate sample payment data as DataFrame."""
    data = []
    
    for _, order in orders_df.iterrows():
        if order['order_status'] not in ['cancelled', 'pending']:
            payment_date = order['order_date'] + timedelta(hours=random.randint(1, 48))
            data.append({
                'payment_id': f'PAY-{str(uuid.uuid4())[:8]}',
                'order_id': order['order_id'],
                'payment_method': random.choice(['credit_card', 'debit_card', 'paypal', 'bank_transfer']),
                'payment_status': random.choice(['completed', 'completed', 'completed', 'failed', 'refunded']),
                'amount': order['total_amount'],
                'payment_date': payment_date,
                'transaction_id': f'TXN-{str(uuid.uuid4())[:12]}',
                'created_at': payment_date,
            })
    
    return pd.DataFrame(data)


def write_to_iceberg(df, database, table_name, session):
    """Write DataFrame to Iceberg table using awswrangler."""
    print(f'\nWriting {len(df)} records to {database}.{table_name}...')
    
    account_id = session.client('sts').get_caller_identity()['Account']
    table_location = f's3://etl-datalake-{account_id}-{AWS_REGION}/source/{table_name}/'
    
    wr.athena.to_iceberg(
        df=df,
        database=database,
        table=table_name,
        table_location=table_location,
        temp_path=f's3://etl-datalake-{account_id}-{AWS_REGION}/temp/',
        boto3_session=session,
        keep_files=False,
    )
    
    print(f'✓ Successfully wrote {len(df)} records to {database}.{table_name}')


def main():
    """Main function to populate all source tables."""
    print('=' * 60)
    print('ETL Platform - Source Data Population Script')
    print('Glue Iceberg Tables')
    print('=' * 60)
    print(f'AWS Profile: {AWS_PROFILE}')
    print(f'AWS Region: {AWS_REGION}')
    print(f'Database: {DATABASE_NAME}')
    print('=' * 60)
    
    try:
        # Generate data
        print('\n[1/5] Generating customer data...')
        customers_df = generate_customers_df(50)
        
        print('[2/5] Generating product data...')
        products_df = generate_products_df(30)
        
        print('[3/5] Generating order data...')
        orders_df = generate_orders_df(customers_df, 100)
        
        print('[4/5] Generating order items data...')
        order_items_df, orders_df = generate_order_items_df(orders_df, products_df)
        
        print('[5/5] Generating payment data...')
        payments_df = generate_payments_df(orders_df)
        
        # Write to Iceberg tables
        print('\n' + '=' * 60)
        print('Writing data to Glue Iceberg tables...')
        print('=' * 60)
        
        write_to_iceberg(customers_df, DATABASE_NAME, 'customers', session)
        write_to_iceberg(products_df, DATABASE_NAME, 'products', session)
        write_to_iceberg(orders_df, DATABASE_NAME, 'orders', session)
        write_to_iceberg(order_items_df, DATABASE_NAME, 'order_items', session)
        write_to_iceberg(payments_df, DATABASE_NAME, 'payments', session)
        
        print('\n' + '=' * 60)
        print('✓ Data population completed successfully!')
        print('=' * 60)
        print(f'\nSummary:')
        print(f'  - Customers: {len(customers_df)}')
        print(f'  - Products: {len(products_df)}')
        print(f'  - Orders: {len(orders_df)}')
        print(f'  - Order Items: {len(order_items_df)}')
        print(f'  - Payments: {len(payments_df)}')
        print('=' * 60)
        
    except Exception as e:
        print(f'\n✗ Error: {str(e)}')
        import traceback
        traceback.print_exc()
        raise


if __name__ == '__main__':
    main()
