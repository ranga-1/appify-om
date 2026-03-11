"""Database connection management with dual connection pools."""

import json
import logging
from typing import Dict, Optional, Generator

import boto3
from psycopg2 import pool
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages connections to both tenants and unshackle_core databases."""
    
    def __init__(self):
        """Initialize database manager with connection pools."""
        self._tenants_pool: Optional[pool.SimpleConnectionPool] = None
        self._core_pool: Optional[pool.SimpleConnectionPool] = None
        self._tenants_creds: Optional[Dict] = None
        self._core_creds: Optional[Dict] = None
    
    def _get_secret(self, secret_id: str) -> Dict:
        """
        Fetch secret from environment or AWS Secrets Manager.
        
        Args:
            secret_id: Secret ID in Secrets Manager
            
        Returns:
            Dictionary with database credentials
        """
        # Check if using local credentials mode
        if settings.use_local_credentials:
            logger.info(f"Using local database credentials for secret_id: {secret_id}")
            
            # Determine which database based on secret_id
            if secret_id == settings.db_secret_id:
                # Tenants database
                return {
                    'host': settings.tenants_db_host,
                    'port': settings.tenants_db_port,
                    'dbname': settings.tenants_db_name,
                    'username': settings.tenants_db_username,
                    'password': settings.tenants_db_password
                }
            elif secret_id == settings.core_db_secret_id:
                # Core database
                return {
                    'host': settings.core_db_host,
                    'port': settings.core_db_port,
                    'dbname': settings.core_db_name,
                    'username': settings.core_db_username,
                    'password': settings.core_db_password
                }
        
        # Otherwise, use AWS Secrets Manager
        logger.info(f"Fetching secret from AWS Secrets Manager: {secret_id}")
        session = boto3.Session(region_name=settings.aws_region)
        client = session.client('secretsmanager')
        response = client.get_secret_value(SecretId=secret_id)
        return json.loads(response['SecretString'])
    
    def get_tenants_connection(self):
        """
        Get connection from tenants database pool.
        
        Returns:
            psycopg2 connection object
        """
        if not self._tenants_pool:
            logger.info("Creating tenants database connection pool")
            self._tenants_creds = self._get_secret(settings.db_secret_id)
            self._tenants_pool = pool.SimpleConnectionPool(
                minconn=1,
                maxconn=10,
                host=self._tenants_creds['host'],
                port=self._tenants_creds['port'],
                database=self._tenants_creds['dbname'],
                user=self._tenants_creds['username'],
                password=self._tenants_creds['password']
            )
            logger.info("Tenants database connection pool created")
        
        return self._tenants_pool.getconn()
    
    def get_core_connection(self):
        """
        Get connection from unshackle_core database pool.
        
        Returns:
            psycopg2 connection object
        """
        if not self._core_pool:
            logger.info("Creating core database connection pool")
            self._core_creds = self._get_secret(settings.core_db_secret_id)
            self._core_pool = pool.SimpleConnectionPool(
                minconn=1,
                maxconn=10,
                host=self._core_creds['host'],
                port=self._core_creds['port'],
                database=self._core_creds['dbname'],
                user=self._core_creds['username'],
                password=self._core_creds['password']
            )
            logger.info("Core database connection pool created")
        
        return self._core_pool.getconn()
    
    def return_tenants_connection(self, conn):
        """
        Return connection to tenants pool.
        
        Args:
            conn: Connection to return to pool
        """
        if self._tenants_pool:
            self._tenants_pool.putconn(conn)
    
    def return_core_connection(self, conn):
        """
        Return connection to core pool.
        
        Args:
            conn: Connection to return to pool
        """
        if self._core_pool:
            self._core_pool.putconn(conn)
    
    def close_all(self):
        """Close all connection pools."""
        if self._tenants_pool:
            self._tenants_pool.closeall()
            logger.info("Closed tenants database connection pool")
        if self._core_pool:
            self._core_pool.closeall()
            logger.info("Closed core database connection pool")


# Global instance
db_manager = DatabaseManager()


# ============================================================================
# SQLAlchemy Session Management (for Data API)
# ============================================================================

def get_tenant_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a SQLAlchemy session for tenant database.
    
    This creates a new SQLAlchemy session using the tenant database credentials.
    The session is automatically closed after the request completes.
    
    Yields:
        SQLAlchemy Session object
    """
    # Get credentials
    if not db_manager._tenants_creds:
        db_manager._tenants_creds = db_manager._get_secret(settings.db_secret_id)
    
    creds = db_manager._tenants_creds
    
    # Create connection URL
    connection_url = (
        f"postgresql://{creds['username']}:{creds['password']}@"
        f"{creds['host']}:{creds['port']}/{creds['dbname']}"
    )
    
    # Create engine (NullPool = no connection pooling, create new connection per request)
    engine = create_engine(connection_url, poolclass=NullPool)
    
    # Create session factory
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Create session
    db = SessionLocal()
    
    try:
        yield db
    finally:
        db.close()
        engine.dispose()
