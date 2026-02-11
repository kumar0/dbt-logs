#!/usr/bin/env python3
"""
Refresh Iceberg table metadata by running REFRESH TABLE commands
"""
import boto3
import time
import sys

def run_query(glue_client, session_id, query):
    """Execute a query in the Glue session"""
    try:
        response = glue_client.run_statement(
            SessionId=session_id,
            Code=query
        )
        statement_id = response['Id']
        
        # Wait for statement to complete
        while True:
            status_response = glue_client.get_statement(
                SessionId=session_id,
                Id=statement_id
            )
            state = status_response['Statement']['State']
            
            if state == 'AVAILABLE':
                return True, status_response['Statement'].get('Output', {})
            elif state in ['ERROR', 'CANCELLED']:
                error_msg = status_response['Statement'].get('Output', {}).get('ErrorValue', 'Unknown error')
                return False, error_msg
            
            time.sleep(2)
            
    except Exception as e:
        return False, str(e)

def create_session(glue_client, role_arn):
    """Create a new Glue interactive session"""
    session_id = f"refresh-iceberg-{int(time.time())}"
    
    try:
        glue_client.create_session(
            Id=session_id,
            Role=role_arn,
            Command={
                'Name': 'glueetl',
                'PythonVersion': '3'
            },
            DefaultArguments={
                '--datalake-formats': 'iceberg'
            },
            MaxCapacity=2.0,
            GlueVersion='4.0',
            IdleTimeout=10
        )
        
        print(f"Creating Glue session: {session_id}")
        print("Waiting for session to be ready...")
        
        # Wait for session to be ready
        while True:
            response = glue_client.get_session(Id=session_id)
            state = response['Session']['Status']
            
            if state == 'READY':
                print("✓ Session is ready")
                return session_id
            elif state == 'FAILED':
                error = response['Session'].get('ErrorMessage', 'Unknown error')
                print(f"✗ Session failed: {error}")
                return None
            
            time.sleep(5)
            
    except Exception as e:
        print(f"✗ Error creating session: {str(e)}")
        return None

def main():
    # Initialize Glue client
    session = boto3.Session(profile_name='mondayskills.development', region_name='us-east-1')
    glue_client = session.client('glue')
    
    role_arn = 'arn:aws:iam::777334699019:role/etl-glue-job-role-us-east-1'
    tables = ['customers', 'products', 'orders', 'order_items', 'payments']
    
    # Create session
    session_id = create_session(glue_client, role_arn)
    if not session_id:
        return 1
    
    try:
        print()
        print("Refreshing Iceberg tables...")
        print()
        
        success_count = 0
        for table_name in tables:
            query = f"REFRESH TABLE etl_source_db.{table_name}"
            print(f"Running: {query}")
            
            success, output = run_query(glue_client, session_id, query)
            
            if success:
                print(f"✓ Refreshed {table_name}")
                success_count += 1
            else:
                print(f"✗ Failed to refresh {table_name}: {output}")
            print()
        
        print(f"Refreshed {success_count}/{len(tables)} tables")
        
        # Stop the session
        print()
        print("Stopping Glue session...")
        glue_client.stop_session(Id=session_id)
        
        return 0 if success_count == len(tables) else 1
        
    except Exception as e:
        print(f"Error: {str(e)}")
        # Try to stop session on error
        try:
            glue_client.stop_session(Id=session_id)
        except:
            pass
        return 1

if __name__ == '__main__':
    sys.exit(main())
