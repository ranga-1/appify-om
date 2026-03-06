#!/usr/bin/env python3
"""Validate SQL execution fix for $$ delimited functions"""

import os
import psycopg2
from pathlib import Path

# Database connection
DB_HOST = "localhost"
DB_PORT = 5436  # SSH tunnel port
DB_NAME = "tenants_db"
DB_USER = "tenants_admin"
DB_PASSWORD = os.getenv("TENANTS_ADMIN_PASSWORD", "")

if not DB_PASSWORD:
    print("ERROR: Set TENANTS_ADMIN_PASSWORD environment variable")
    exit(1)

# Read SQL file
sql_file = Path(__file__).parent / "sql" / "tenant-utility-functions.sql"
utility_functions_sql = sql_file.read_text()

# Test connection and SQL execution
try:
    # Create test schema
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=10
    )
    conn.autocommit = True
    cursor = conn.cursor()
    
    test_schema = "test_sql_validation"
    
    print(f"Creating test schema: {test_schema}")
    cursor.execute(f"DROP SCHEMA IF EXISTS {test_schema} CASCADE")
    cursor.execute(f"CREATE SCHEMA {test_schema}")
    cursor.execute(f"SET search_path TO {test_schema}")
    
    print("Executing utility functions SQL using exec_driver_sql approach...")
    # This simulates: connection.connection.exec_driver_sql(utility_functions_sql)
    cursor.execute(utility_functions_sql)
    
    print("Verifying functions were created...")
    cursor.execute("""
        SELECT proname 
        FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = %s
        AND proname IN ('update_modified_date', 'update_object_metadata_modified_date')
        ORDER BY proname
    """, (test_schema,))
    
    functions = [row[0] for row in cursor.fetchall()]
    print(f"Functions found: {functions}")
    
    if len(functions) == 2:
        print("✅ SUCCESS: Both functions created correctly")
        print("✅ COMMENT statements executed without error")
        exit_code = 0
    else:
        print(f"❌ FAILED: Expected 2 functions, found {len(functions)}")
        exit_code = 1
    
    # Cleanup
    print(f"Cleaning up test schema...")
    cursor.execute(f"DROP SCHEMA IF EXISTS {test_schema} CASCADE")
    
    cursor.close()
    conn.close()
    exit(exit_code)
    
except Exception as e:
    print(f"❌ ERROR: {e}")
    exit(1)
