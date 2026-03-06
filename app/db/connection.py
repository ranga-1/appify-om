"""Database connection management with dual connection pools."""

import json
import logging
from typing import Dict, Optional

import boto3
from psycopg2 import pool

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
        Fetch secret from AWS Secrets Manager.
        
        Args:
            secret_id: Secret ID in Secrets Manager
            
        Returns:
            Dictionary with database credentials
        """
        logger.info(f"Fetching secret: {secret_id}")
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
