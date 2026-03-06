"""Test OM service SQL execution."""
import json
import boto3
from sqlalchemy import create_engine, text
from pathlib import Path

# Get DB credentials
session = boto3.Session(profile_name='appify-unshackle', region_name='us-west-1')
sm = session.client('secretsmanager')
secret = sm.get_secret_value(SecretId='appify/unshackle/tenants/admin')
creds = json.loads(secret['SecretString'])

# Create test schema
test_schema = "tenant_sqltest"
url = f"postgresql+psycopg2://{creds['username']}:{creds['password']}@{creds['host']}:{creds['port']}/tenants_db"

engine = create_engine(url, isolation_level="AUTOCOMMIT")

try:
    with engine.connect() as conn:
        # Drop test schema if exists
        conn.execute(text(f"DROP SCHEMA IF EXISTS {test_schema} CASCADE"))
        # Create test schema
        conn.execute(text(f"CREATE SCHEMA {test_schema}"))
        # Set search path
        conn.execute(text(f"SET search_path TO {test_schema}"))
        
        # Read and execute utility functions SQL
        sql_dir = Path(__file__).parent / "sql"
        functions_sql = (sql_dir / "tenant-utility-functions.sql").read_text()
        
        print("Executing utility functions SQL...")
        conn.execute(text(functions_sql))
        print("✅ Utility functions created")
        
        # Verify functions exist
        result = conn.execute(text("""
            SELECT proname FROM pg_proc 
            WHERE pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = :schema)
            AND proname IN ('update_modified_date', 'update_object_metadata_modified_date')
        """), {"schema": test_schema})
        
        functions = [row[0] for row in result]
        print(f"✅ Functions found: {functions}")
        
        if len(functions) == 2:
            print("✅ SQL execution test PASSED")
        else:
            print(f"❌ Expected 2 functions, found {len(functions)}")
            exit(1)
        
        # Cleanup
        conn.execute(text(f"DROP SCHEMA {test_schema} CASCADE"))
        print("✅ Cleanup complete")
        
finally:
    engine.dispose()
