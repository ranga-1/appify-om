"""Tenant schema initialization service for Object Modeler metadata tables."""

import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

import boto3
import psycopg2
from psycopg2 import pool

from app.config import settings

logger = logging.getLogger(__name__)


class CredentialCache:
    """Cache for database credentials with TTL."""
    
    def __init__(self, ttl_seconds: int = 3600):
        """Initialize credential cache.
        
        Args:
            ttl_seconds: Time-to-live for cached credentials in seconds. Default 1 hour.
        """
        self._cache: Dict[str, Tuple[dict, datetime]] = {}
        self._ttl_seconds = ttl_seconds
    
    def get(self, key: str) -> Optional[dict]:
        """Get credentials from cache if not expired.
        
        Args:
            key: Cache key (e.g., secret ID)
            
        Returns:
            Cached credentials dict or None if expired/missing
        """
        if key not in self._cache:
            return None
            
        credentials, expiry = self._cache[key]
        if datetime.now() > expiry:
            logger.debug(f"Credential cache expired for key: {key}")
            del self._cache[key]
            return None
            
        logger.debug(f"Using cached credentials for key: {key}")
        return credentials
    
    def set(self, key: str, credentials: dict) -> None:
        """Store credentials in cache with expiry.
        
        Args:
            key: Cache key (e.g., secret ID)
            credentials: Credentials dict to cache
        """
        expiry = datetime.now() + timedelta(seconds=self._ttl_seconds)
        self._cache[key] = (credentials, expiry)
        logger.debug(f"Cached credentials for key: {key} (expires in {self._ttl_seconds}s)")
    
    def clear(self) -> None:
        """Clear all cached credentials."""
        self._cache.clear()
        logger.debug("Credential cache cleared")


class TenantSchemaInitializer:
    """Service to initialize Object Modeler metadata tables in tenant schemas."""
    
    def __init__(self):
        """Initialize the tenant schema initializer service."""
        self._credential_cache = CredentialCache(ttl_seconds=settings.credential_cache_ttl)
        sql_dir = Path(__file__).parent.parent.parent / "sql"
        self._utility_functions_path = sql_dir / "tenant-utility-functions.sql"
        self._schema_sql_path = sql_dir / "tenant-base-schema.sql"
        self._connection_pool: Optional[psycopg2.pool.SimpleConnectionPool] = None
        self._db_credentials: Optional[Dict[str, str]] = None
    
    def _get_db_credentials(self) -> dict:
        """Retrieve database credentials from environment or AWS Secrets Manager with caching.
        
        Returns:
            Dictionary containing database connection parameters
            
        Raises:
            Exception: If unable to retrieve credentials
        """
        # Check if using local credentials mode
        if settings.use_local_credentials:
            logger.info("Using local tenant database credentials from environment")
            return {
                'host': settings.tenants_db_host,
                'port': str(settings.tenants_db_port),
                'dbname': settings.tenants_db_name,
                'username': settings.tenants_db_username,
                'password': settings.tenants_db_password
            }
        
        # Check cache first
        cached_creds = self._credential_cache.get(settings.db_secret_id)
        if cached_creds:
            return cached_creds
        
        # Fetch from Secrets Manager
        try:
            logger.info(f"Fetching credentials from Secrets Manager: {settings.db_secret_id}")
            session = boto3.Session(
                region_name=settings.aws_region,
                profile_name=settings.aws_profile if settings.environment != "production" else None
            )
            client = session.client("secretsmanager")
            
            response = client.get_secret_value(SecretId=settings.db_secret_id)
            credentials = json.loads(response["SecretString"])
            
            # Cache credentials
            self._credential_cache.set(settings.db_secret_id, credentials)
            
            return credentials
            
        except Exception as e:
            logger.error(f"Failed to retrieve database credentials: {e}")
            raise Exception(f"Unable to retrieve database credentials: {str(e)}")
    
    def _get_connection(self):
        """Get database connection from pool.
        
        Returns:
            psycopg2 connection
        """
        if self._connection_pool is None:
            credentials = self._get_db_credentials()
            
            # Store credentials for psql execution
            self._db_credentials = credentials
            
            # Create connection pool
            self._connection_pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=10,
                host=credentials['host'],
                port=credentials['port'],
                database=settings.db_name,
                user=credentials['username'],
                password=credentials['password']
            )
            logger.info("Created database connection pool")
        
        return self._connection_pool.getconn()
    
    def _return_connection(self, conn):
        """Return connection to pool.
        
        Args:
            conn: psycopg2 connection to return
        """
        if self._connection_pool:
            self._connection_pool.putconn(conn)
    
    def _read_sql_file(self, file_path: Path) -> str:
        """Read a SQL file.
        
        Args:
            file_path: Path to the SQL file
        
        Returns:
            SQL file contents as string
            
        Raises:
            FileNotFoundError: If SQL file doesn't exist
            Exception: If unable to read file
        """
        if not file_path.exists():
            raise FileNotFoundError(f"SQL file not found: {file_path}")
        
        try:
            with open(file_path, "r") as f:
                sql_content = f.read()
            logger.debug(f"Read SQL file: {file_path}")
            return sql_content
        except Exception as e:
            logger.error(f"Failed to read SQL file: {e}")
            raise Exception(f"Unable to read SQL file: {str(e)}")
    
    def initialize_tenant_schema(
        self, 
        customer_id: str, 
        username: str, 
        password: str
    ) -> dict:
        """Initialize Object Modeler schema for a tenant.
        
        This method creates complete database infrastructure:
        1. Database schema
        2. Database user
        3. User permissions
        4. OM metadata tables and utility functions
        
        This operation is idempotent where possible.
        
        Args:
            customer_id: Customer identifier (e.g., 'acme', 'xyz')
            username: Database username for the tenant
            password: Database password for the tenant
            
        Returns:
            Dictionary with:
                - success: bool
                - message: str
                - tables_created: list of table names (if successful)
                - error: str (if failed)
                
        Raises:
            Exception: On critical failures that should trigger rollback
        """
        schema_name = f"tenant_{customer_id}"
        try:
            logger.info(f"Starting complete tenant infrastructure setup for: {customer_id}")
            logger.info(f"Target schema: {schema_name}")
            logger.info(f"Target username: {username}")
            
            # Read SQL files
            utility_functions_sql = self._read_sql_file(self._utility_functions_path)
            schema_sql = self._read_sql_file(self._schema_sql_path)
            
            # Ensure credentials are loaded
            if not self._db_credentials:
                conn = self._get_connection()
                self._return_connection(conn)
            
            # Execute everything in psql
            tables_created = []
            functions_created = []
            
            logger.info(f"Executing complete tenant setup via psql")
            self._execute_complete_setup(
                schema_name=schema_name,
                username=username,
                password=password,
                utility_functions_sql=utility_functions_sql,
                schema_sql=schema_sql
            )
            
            functions_created = ['update_modified_date', 'update_object_metadata_modified_date']
            tables_created = ['sys_object_metadata', 'sys_om_datatype_mappings', 'sys_users']
            logger.info(f"✅ Successfully initialized schema: {schema_name}")
            
            return {
                "success": True,
                "message": f"Schema initialized successfully for customer: {customer_id}",
                "tables_created": tables_created,
                "functions_created": functions_created,
                "schema_name": schema_name
            }
            
        except FileNotFoundError as e:
            logger.error(f"SQL file not found: {e}")
            if conn:
                conn.rollback()
            return {
                "success": False,
                "message": "SQL file not found",
                "error": str(e),
                "schema_name": schema_name
            }
            
        except psycopg2.Error as e:
            logger.error(f"Database error during schema initialization: {e}")
            if conn:
                conn.rollback()
            raise Exception(f"Database error: {str(e)}")
            
        except Exception as e:
            logger.error(f"Unexpected error during schema initialization: {e}")
            if conn:
                conn.rollback()
            raise Exception(f"Schema initialization failed: {str(e)}")
    
    def _execute_complete_setup(
        self,
        schema_name: str,
        username: str,
        password: str,
        utility_functions_sql: str,
        schema_sql: str
    ) -> None:
        """Execute complete tenant setup in single psql transaction.
        
        Args:
            schema_name: Schema name to create
            username: User name to create
            password: User password
            utility_functions_sql: SQL for utility functions
            schema_sql: SQL for base schema
            
        Raises:
            Exception: On SQL execution errors
        """
        if not self._db_credentials:
            raise Exception("Database credentials not loaded")
        
        # Escape single quotes in password for SQL
        escaped_password = password.replace("'", "''")
        
        # Build complete SQL script
        complete_sql = f"""-- Complete tenant setup
BEGIN;

-- Step 1: Create schema
CREATE SCHEMA IF NOT EXISTS {schema_name};

-- Step 2: Create user
CREATE USER {username} WITH PASSWORD '{escaped_password}';

-- Step 3: Grant permissions
GRANT USAGE ON SCHEMA {schema_name} TO {username};
GRANT ALL PRIVILEGES ON SCHEMA {schema_name} TO {username};
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA {schema_name} TO {username};
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {schema_name} TO {username};
ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_name} GRANT ALL ON TABLES TO {username};
ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_name} GRANT ALL ON SEQUENCES TO {username};

-- Step 4: Set search path
SET search_path TO {schema_name};

-- Step 5: Create utility functions
{utility_functions_sql}

-- Step 6: Create tables, indexes, triggers
{schema_sql}

COMMIT;
"""
        
        # Write to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
            f.write(complete_sql)
            temp_sql_file = f.name
        
        try:
            # Set environment variable for password
            env = os.environ.copy()
            env['PGPASSWORD'] = self._db_credentials['password']
            
            # Build psql command
            cmd = [
                'psql',
                '-h', self._db_credentials['host'],
                '-p', str(self._db_credentials['port']),
                '-U', self._db_credentials['username'],
                '-d', settings.db_name,
                '-f', temp_sql_file,
                '-v', 'ON_ERROR_STOP=1',  # Stop on first error
                '--quiet'  # Suppress NOTICE messages
            ]
            
            # Execute psql
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            # Check for errors
            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                logger.error(f"psql execution failed: {error_msg}")
                raise Exception(f"SQL execution failed: {error_msg}")
            
            # Log any output
            if result.stdout:
                logger.debug(f"psql output: {result.stdout}")
                
        except subprocess.TimeoutExpired:
            logger.error("SQL execution timed out after 5 minutes")
            raise Exception("SQL execution timed out")
        except FileNotFoundError:
            logger.error("psql command not found - postgresql-client not installed")
            raise Exception("psql command not found")
        finally:
            # Clean up temporary file
            try:
                Path(temp_sql_file).unlink()
            except Exception as e:
                logger.warning(f"Failed to delete temporary SQL file: {e}")
    
    def _extract_table_name(self, create_statement: str) -> str:
        """Extract table name from CREATE TABLE statement.
        
        Args:
            create_statement: SQL CREATE TABLE statement
            
        Returns:
            Table name extracted from statement
        """
        # Simple extraction: find text between "CREATE TABLE" and "("
        parts = create_statement.upper().split('CREATE TABLE')
        if len(parts) < 2:
            return "unknown"
        
        table_part = parts[1].split('(')[0].strip()
        # Remove IF NOT EXISTS and other keywords
        table_part = table_part.replace('IF NOT EXISTS', '').strip()
        
        return table_part.lower()
    
    def clear_cache(self) -> None:
        """Clear credential cache and close all database connections."""
        self._credential_cache.clear()
        if self._connection_pool:
            self._connection_pool.closeall()
            self._connection_pool = None
            logger.debug("Closed all database connections")


# Global singleton instance
_tenant_schema_initializer: Optional[TenantSchemaInitializer] = None


def get_tenant_schema_initializer() -> TenantSchemaInitializer:
    """Get or create the global TenantSchemaInitializer instance.
    
    Returns:
        TenantSchemaInitializer singleton instance
    """
    global _tenant_schema_initializer
    if _tenant_schema_initializer is None:
        _tenant_schema_initializer = TenantSchemaInitializer()
    return _tenant_schema_initializer
