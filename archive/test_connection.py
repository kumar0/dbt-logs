#!/usr/bin/env python3
"""
Test script to verify AWS Glue connection before running dbt
"""

import boto3
import sys
import os

def test_aws_credentials():
    """Test AWS credentials"""
    print("Testing AWS credentials...")
    try:
        session = boto3.Session(profile_name='mondayskills.development')
        sts = session.client('sts')
        identity = sts.get_caller_identity()
        print(f"✓ AWS Account: {identity['Account']}")
        print(f"✓ User/Role: {identity['Arn']}")
        return session
    except Exception as e:
        print(f"✗ AWS credentials failed: {e}")
        print("\nRun: aws sso login --profile mondayskills.development")
        return None

def test_glue_access(session):
    """Test Glue access"""
    print("\nTesting Glue access...")
    try:
        glue = session.client('glue', region_name='us-east-1')
        
        # Test database access
        db = glue.get_database(Name='etl_source_db')
        print(f"✓ Source database: {db['Database']['Name']}")
        
        db = glue.get_database(Name='etl_dest_db')
        print(f"✓ Destination database: {db['Database']['Name']}")
        
        return True
    except Exception as e:
        print(f"✗ Glue access failed: {e}")
        return False

def test_s3_access(session):
    """Test S3 access"""
    print("\nTesting S3 access...")
    try:
        s3 = session.client('s3', region_name='us-east-1')
        bucket = 'etl-datalake-777334699019-us-east-1'
        
        s3.head_bucket(Bucket=bucket)
        print(f"✓ S3 bucket accessible: {bucket}")
        
        return True
    except Exception as e:
        print(f"✗ S3 access failed: {e}")
        return False

def test_iam_role():
    """Test IAM role exists"""
    print("\nTesting IAM role...")
    try:
        session = boto3.Session(profile_name='mondayskills.development')
        iam = session.client('iam')
        
        role = iam.get_role(RoleName='etl-glue-job-role-us-east-1')
        print(f"✓ Glue role exists: {role['Role']['Arn']}")
        
        return True
    except Exception as e:
        print(f"✗ IAM role check failed: {e}")
        return False

def check_glue_sessions(session):
    """Check existing Glue sessions"""
    print("\nChecking Glue sessions...")
    try:
        glue = session.client('glue', region_name='us-east-1')
        response = glue.list_sessions()
        
        sessions = response.get('Ids', [])
        dbt_sessions = [s for s in sessions if 'dbt' in s.lower()]
        
        if dbt_sessions:
            print(f"⚠ Found {len(dbt_sessions)} existing dbt-glue sessions:")
            for s in dbt_sessions[:5]:
                print(f"  - {s}")
            print("\nNote: dbt-glue will reuse existing sessions if available")
        else:
            print("✓ No existing dbt-glue sessions (will create new one)")
        
        return True
    except Exception as e:
        print(f"⚠ Could not list sessions: {e}")
        return False

def main():
    print("=" * 60)
    print("dbt-glue Connection Test")
    print("=" * 60)
    print()
    
    # Test AWS credentials
    session = test_aws_credentials()
    if not session:
        sys.exit(1)
    
    # Test Glue access
    if not test_glue_access(session):
        sys.exit(1)
    
    # Test S3 access
    if not test_s3_access(session):
        sys.exit(1)
    
    # Test IAM role
    if not test_iam_role():
        sys.exit(1)
    
    # Check sessions
    check_glue_sessions(session)
    
    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    print("=" * 60)
    print("\nYou can now run dbt commands:")
    print("  ./run_dbt.sh debug")
    print("  ./run_dbt.sh run")
    print("\nNote: First run may take 3-5 minutes for Glue session provisioning")

if __name__ == '__main__':
    main()
